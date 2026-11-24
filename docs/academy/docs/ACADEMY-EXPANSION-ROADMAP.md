# OpenVLC Engineering Academy — Expansion Roadmap

Historical expansion plan from `luckyprinter/lifi` at website baseline
`b0cb0200a6c2d5075e5f7bc738b247bc776de6fc`. The planning reference for
prototype source was `411f183a8592d8285118f613bb4909c5bbd9d3cc`, and the draft
UI research reference was `80ef4afa63a3fe571ffd5026560bf7d7d90fbecc`.
See the [Academy guide](../README.md) for the current build and lesson snapshot.

---

## 1. Product vision

Evolve the current Academy from an interactive field guide into a progressive engineering-learning environment that lets a reader:

1. Understand what the actual VLC prototype is and what problem it demonstrates.
2. Follow a realistic transfer from the moment a person opens the TX application, selects a file, and presses Start, through the LED/optical channel, to the RX application and final file inspection.
3. Understand what the TX and RX applications display, what their settings do, what their graphs and viewers represent, and how they relate to the hardware.
4. Learn the essential implementation without being overwhelmed by the whole repository.
5. Voluntarily open a complete repository explorer for a deeper, file-by-file and function-by-function study.
6. Test their understanding through short scenario questions and code-reading exercises.

The Academy must teach the physical prototype as the main product. It must not present a simulation as the real transmission path or make an illustrative animation look like measured hardware data.

### Two learning depths

**Guided learning — the default**
- Curated, ordered lessons for readers who want to understand the project and its important code.
- Only the code needed to explain each user action and system behavior appears inline.
- Every excerpt links to the exact file and line range in the pinned source revision.
- Explanations start with plain language, then progressively introduce programming and embedded-systems terminology.

**Deep Dive — optional**
- A complete catalog of executable source files and important configuration/build files.
- Search by file, symbol, responsibility, and workflow stage.
- Function/class index, line-by-line explanations, inbound/outbound relationships, and cross-file call paths.
- Explicit labels for active prototype code, supporting infrastructure, optional/legacy code, draft work, tests, and generated/assets/data.
- The deep dive must not be a prerequisite for completing the guided course.

---

## 2. Learning architecture and information design

Do not turn the site into one long scrolling document. Keep the current chapter/page approach, but improve the navigation and add clear relationships between pages.

### Proposed top-level navigation

1. **Start Here** — project purpose, physical prototype, what the reader will build mentally.
2. **How a Transfer Works** — the complete user-centered TX-to-RX story.
3. **Transmitter App** — TX screens, file selection, queue, dashboard, settings, logs.
4. **Optical Link & Hardware** — ESP32 TX, LED driver, LED, free-space optical path, receiver analog front-end and comparator.
5. **Receiver App** — RX dashboard, receiving, signal monitor, inspect, BER, experiments, export.
6. **Learn the Code** — guided code lessons and the optional Deep Dive repository explorer.
7. **Practice** — scenario checks, code reading, troubleshooting, and cumulative quiz.
8. **Reference** — glossary, protocol fields, pin map, settings index, source revisions, and bibliography.

Use a persistent but compact chapter navigator. On phones, use a clear drawer/menu and a visible reading-progress indicator. Keep breadcrumbs and previous/next lesson navigation consistent. Each lesson should have one learning objective, a short explanation, a meaningful model or diagram, relevant code, and a small checkpoint. Do not put every detail on every page.

### Reader modes

Offer a simple choice near the beginning:
- **Understand the prototype** — project overview and end-to-end operation.
- **Learn how it is coded** — guided implementation lessons.
- **Explore the whole repository** — Deep Dive.

These are different depths, not separate versions of the truth. A reader can move between them without losing their place.

---

## 3. The flagship feature: an end-to-end user scenario

Build a connected, interactive “Follow one file” experience. This should become the spine of the Academy and the main way the reader understands how the application, firmware, protocol, and hardware work together.

Every stage must show the same five layers:

1. **What the person does** — the visible action in the desktop application.
2. **What the application does** — UI event, state update, controller/backend call, and displayed feedback.
3. **What crosses USB serial** — actual command, response, or telemetry, where supported by the pinned code.
4. **What the firmware/hardware does** — actual function, buffer, GPIO, circuit, optical event, or receiver operation.
5. **What the reader should observe** — the UI status, graph, log, received file, or validation result.

Selecting a stage should highlight the corresponding nodes across all five layers. Tapping a code reference opens the exact Code Studio lesson. Tapping a hardware node opens the relevant hardware explanation. Include a compact event timeline and a “why this matters” explanation.

### Scenario A — Open and prepare a file in TX

Teach the actual launcher and TX application entry:
- Launch the application and choose Transmitter.
- Explain the launcher, TX window, TX shell, navigation, and dashboard.
- Explain how the dashboard's Select File action opens the file dialog.
- Follow the selected path into TX application state: filename, type, size, chunk count, estimated time, and pending file path.
- Explain the difference between selecting a file, adding a file to the File Manager queue, and actually starting a transmission.

**Important source distinction:** the current File Manager's Add to Transmit Queue action appends an item to a queue. The dashboard's FileDetailsWidget Select File and Start controls implement a separate direct-send path. The Academy must not imply that adding a queue item automatically transmits it unless the application code is changed and verified to do so.

Primary source candidates:
- application-source/gui_dev_v3/app.py
- application-source/gui_dev_v3/tx/shell.py
- application-source/gui_dev_v3/tx/dashboard.py
- application-source/gui_dev_v3/tx/file_manager_page.py
- application-source/gui_dev_v3/tx_app_state.py

### Scenario B — Start transmission and prepare data

Show:
- User presses Start.
- Dashboard calls the TX state object's start_transmission method.
- TX state delegates to the physical backend.
- Physical backend starts the serial controller's file-send operation on a background thread so the GUI remains responsive.
- The serial controller checks connection and file validity, reads the file, calculates file CRC, chooses the supported transfer path, creates transfer identifiers, and divides data into chunks.
- Explain the actual firmware capability check and the difference between supported stream and DMA protocol paths. The guided path should show the path used by the authoritative prototype configuration; alternative firmware capabilities belong in a clearly marked advanced note.
- Explain large-file batching and the 80 KiB firmware buffer boundary only after the normal file transfer is understood.

Primary source candidates:
- application-source/gui_dev_v3/tx_app_state.py
- application-source/gui_dev_v3/tx/backends/physical.py
- application-source/gui_dev_v3/serial/controllers.py
- application-source/gui_dev_v3/serial/session.py
- firmware/tx/tx.ino
- firmware/specs/protocol_spec.md

### Scenario C — USB serial transfer to TX ESP32

Animate actual serial command/acknowledgement flow:
- Connection and firmware identification.
- Configuration commands and response.
- STREAM_CLEAR / STREAM_BEGIN / STREAM_DATA / STREAM_START for the stream path, with the exact command syntax taken from the pinned code.
- Chunk index, payload bytes, transfer ID, and CRC fields.
- Acknowledgement and progress updates returning to the desktop application.

Show a small serial console that can step through the real message sequence. Explain baud rate and why TX and RX serial rates differ. Distinguish a command from a response and a log message from a firmware acknowledgement.

Primary source candidates:
- application-source/gui_dev_v3/serial/session.py
- application-source/gui_dev_v3/serial/controllers.py
- firmware/tx/tx.ino

### Scenario D — TX firmware turns bytes into light

Animate a single payload byte through:
- frame metadata and payload assembly,
- CRC calculation,
- 4B5B encoding,
- preamble and synchronization,
- NRZ/OOK symbol timing,
- GPIO5 output,
- active-low LED driver behavior,
- 12 V LED switching and optical emission.

Use a single traceable example byte and show its transformation at each step. Let the reader pause, step, inspect bit values, and compare logical symbols with electrical driver polarity. Do not imply that the LED is literally switching at an unrelated carrier frequency if the selected prototype path uses baseband intensity modulation.

Primary source candidates:
- firmware/tx/tx.ino
- firmware/specs/protocol_spec.md
- hardware schematic/pin documentation and thesis-grounded hardware descriptions.

### Scenario E — Light reaches the RX circuit

Animate the physical path:
- LED emits intensity-modulated light.
- BPW34 photodiode converts received optical power into photocurrent.
- OPA2604 transimpedance amplifier converts current into a voltage signal.
- LM393 comparator compares the signal against Vref and produces a digital output.
- ESP32 RX reads the comparator output and analog monitoring inputs.

Show the actual pin roles:
- RX GPIO5: comparator digital output.
- RX GPIO34: PVo ADC monitor.
- RX GPIO35: Vref ADC monitor.
- RX GPIO25: PWM output used to adjust comparator reference.

Explain line-of-sight, distance, alignment, ambient light, signal swing, threshold margin, and why the receiver must distinguish high and low levels. Use conceptual models for the circuit, but label them as explanatory unless backed by recorded measurements.

### Scenario F — RX firmware detects and reconstructs the file

Show the receiver state machine in an animated, inspectable sequence:
- idle/stable-level detection,
- start-edge acquisition,
- three-sample majority voting,
- preamble and synchronization detection,
- polarity handling,
- SOF alignment,
- 4B5B decoding and invalid codeword rejection,
- frame/header parsing,
- frame and chunk CRC checks,
- storing valid chunks by transfer/chunk identity,
- full-file completeness and CRC verification,
- serial output of the reconstructed file to the RX application.

Use a packet/chunk map that changes as chunks arrive. Let the reader inject a noisy sample or invalid 5-bit codeword and see why the decoder accepts, corrects by majority, or rejects it. Never claim the teaching model is a live capture.

Primary source candidates:
- firmware/rx/rx.ino
- application-source/gui_dev_v3/serial/controllers.py
- application-source/gui_dev_v3/rx/backends/physical.py

### Scenario G — RX application receives and presents the result

Explain that the receiver is already listening after its hardware connection is established; reception is not necessarily initiated by selecting a file in the RX GUI. Show:
- RX app launch and serial device identification.
- Live RX serial reader and line dispatch.
- RX_FILE_HEX / transfer notices / link-quality telemetry handling, as confirmed by the pinned source.
- RX application state and dashboard updates.
- Received filename, total/received chunks, progress, transfer status, and activity log.
- Difference between receiving a payload and rendering it as readable UTF-8 text. Binary files should be treated as files, not as meaningful terminal text.

Primary source candidates:
- application-source/gui_dev_v3/app.py
- application-source/gui_dev_v3/rx/shell.py
- application-source/gui_dev_v3/app_state.py
- application-source/gui_dev_v3/rx/backends/physical.py
- application-source/gui_dev_v3/serial/controllers.py
- application-source/gui_dev_v3/rx/receive_page.py
- application-source/gui_dev_v3/rx/dashboard.py

### Scenario H — Inspect, compare, validate, and export

Make the post-transfer actions explicit:
- Open the received transfer in Inspect.
- Explain transfer/chunk selection, chunk integrity map, hex/byte/bit views, and any available waveform or protocol timeline.
- Load the original reference file when performing Method 2 BER comparison.
- Explain overlap BER versus strict BER, bit errors, compared bytes/bits, missing data, and the difference between CRC integrity checks and BER comparison.
- Show how a complete transfer with valid CRC and BER 0.00% should be interpreted.
- Open history/export, select a session, inspect the capture, save the received file, export CSV, and back up or restore the local database where supported.

Do not conflate:
- per-frame CRC,
- per-chunk CRC,
- whole-file CRC,
- BER computed by comparing received bytes against the receiver-side original reference file.

Primary source candidates:
- application-source/gui_dev_v3/rx/inspect_page.py
- application-source/gui_dev_v3/rx/ber_analyzer_page.py
- application-source/gui_dev_v3/logic/ber_bridge.py
- application-source/gui_dev_v3/rx/export_page.py
- application-source/gui_dev_v3/data/records.py
- application-source/gui_dev_v3/data/session.py

---

## 4. Application UI and interaction atlas

Create a dedicated visual guide to the actual TX and RX applications. Do not treat the GUI as a decorative screenshot: make each visible panel explorable.

### TX application

Cover the launcher and each actual TX navigation destination:
- Dashboard: device status, pipeline, current session, file details, Start/Cancel, bitstream panel, transmission logs.
- Transmit: verify whether this page is a functional page or placeholder in the chosen source revision; label it honestly.
- File Manager: browse/drag-and-drop, file metadata, CRC display, estimated duration, compression, queue action.
- Settings: General & Display, Hardware Connection, Firmware, Transmission/Link, Logging, Developer sections as present in the actual file.
- Logs: actual implementation status and where logs are written.
- About/version and firmware identity.

For each control, show:
- its purpose,
- default/current value,
- where it is persisted,
- whether it affects the desktop UI, serial command, or firmware behavior,
- whether it takes effect immediately or only after Apply/reconnect/restart,
- safe recommended prototype values,
- what can go wrong when changed.

### RX application

Cover:
- Dashboard and live status cards.
- Receive page and payload/terminal behavior.
- Signal page: live traces, receiver diagnostics, margin analysis, historical trends, transfer statistics, signal-quality metrics.
- Inspect: chunk health map, selected chunk, hex/bit analysis, waveform/protocol views where supported.
- BER Analyzer: original reference file, comparison results, strict/overlap metrics.
- Experiments: create, search, view, edit, delete, experiment categories and their actual execution status.
- Table Builder: selectable/reorderable columns and preview, clearly distinguishing actual recorded values from seeded/demo values.
- Export/History: transfer selection, session inspector, waveform/log tabs, file saving, CSV, database backup/restore.
- Settings: General/Display, Connection, Firmware, Signal Monitoring, Experiments, Database, Table Generator, Logging, Developer sections as present in the pinned source.
- About/version and firmware identity.

### Settings explorer

Build an interactive settings catalog with:
- Search and category filters.
- Plain-language explanation and units.
- Actual default value and recommended prototype value, only where verified.
- Exact persistence key.
- UI control source file and handler.
- Serial command emitted, if any.
- Firmware command handler and effect, if any.
- Whether the setting is live, apply-on-click, reconnect-only, or restart-only.
- Safety note for values that can break synchronization or receiver thresholding.

Explain important receiver settings individually: symbol frequency, preamble length, sample phase, Vref target, margin target, PWM full-scale calibration, settling time, Vref auto-calibration, majority sampling, report-chunks, and symbol inversion. Explain the TX matching settings: symbol rate, frame/post-frame gaps, active-low driver, idle-on behavior, intensity, and firmware capability-dependent options.

Avoid showing a setting as physically effective merely because it is saved in QSettings. Verify that the handler actually sends it and the firmware accepts it.

---

## 5. Graphs, signal viewers, and data provenance

The graphs and viewers deserve their own learning section because they are central to engineering understanding.

### RX Signal Monitor

Explain:
- PVo, Vref, and margin traces and their physical meaning.
- Trace toggles, time window, refresh interval, pan/zoom/reset if implemented.
- Receiver diagnostics and signal quality metrics.
- Historical trend charts and their data source.
- How ambient light, distance, angle, and threshold changes can affect the observed signal.
- What a healthy margin looks like and why a threshold too close to the signal can cause bit errors.

The source includes a live SignalWaveform widget with trace selection and refresh controls. Connect the visual elements to the actual telemetry pipeline rather than inventing graph behavior.

### Inspect and session viewers

Teach:
- Chunk-health grid and status colors.
- Chunk selection and its relation to file offset/index.
- Hex and bit representation.
- Decoded payload and protocol fields.
- Recorded waveform playback when a real capture exists.
- Session logs and event timeline.

### Strict data-provenance rules

Every visualized dataset must have one of these labels:
- **Live hardware telemetry** — received from the connected physical device.
- **Recorded capture** — loaded from a real saved session.
- **Source-derived example** — calculated from the pinned source code for teaching.
- **Illustrative animation** — a conceptual model, not measured data.
- **Demo/seed data** — sample content used by the application itself.

This distinction is essential. The source currently includes places where UI visuals can be generated from simplified or synthetic values. For example, the TX dashboard's DigitalBitstreamWidget constructs a deterministic illustrative bit array from file size rather than reading the exact firmware output stream. The RX export inspector can display synthesized waveform data when no saved capture exists, and some history/experiment paths contain seeded records. The Academy must disclose this rather than presenting these visuals as recorded prototype measurements.

Where possible, prefer:
1. actual firmware/serial telemetry,
2. actual saved session capture,
3. source-derived deterministic examples,
4. conceptual animation only when the first three are unavailable.

---

## 6. Code learning system

### Guided code curriculum

The normal course should teach a manageable, carefully chosen set of code:
1. App launcher and TX/RX window creation.
2. TX and RX shells/navigation.
3. TX dashboard file selection and Start event.
4. TX application state and observer/update model.
5. TX physical backend and serial controller.
6. Serial session, framing, acknowledgements, and progress.
7. TX firmware serial command parser.
8. Frame construction and CRC.
9. 4B5B encoding and OOK/GPIO output.
10. Physical LED driver path.
11. Photodiode/amplifier/comparator and RX pin mapping.
12. RX sampling, majority vote, sync, and 4B5B decode.
13. RX frame parser, chunk storage, and CRC validation.
14. RX physical backend and serial line dispatch.
15. RX application state and dashboard/receive page.
16. Signal monitor and waveform widgets.
17. Inspect and BER comparison.
18. Experiment/history/export and data persistence.
19. Settings persistence and firmware command application.
20. End-to-end error handling and troubleshooting.

Each lesson should follow a consistent structure:
- What user-visible behavior are we explaining?
- Where does execution begin?
- What does each important line do?
- What values enter and leave the function?
- Which function/file calls it next?
- Which state or hardware changes?
- What happens if this code is removed or changed?
- What should the reader remember?

Beginner explanations should introduce concepts in context: event handlers, functions, classes, state, callbacks, threads, serial protocols, buffers, bitwise operations, CRC, state machines, ADC, PWM, and GPIO.

### Deep Dive repository explorer

Build a separate searchable source browser that covers all relevant tracked code, not just selected snippets.

Initial inventory groups:
- Application entry, windows, launcher, theme, settings, shared widgets, state, models, and navigation.
- TX UI pages, TX backend, TX application state, TX settings, TX serial controller behavior.
- RX UI pages, RX backend, RX application state, signal widgets, inspect, BER, experiments, table builder, export, data stores.
- Shared serial session, detection, controllers, logging, and BER logic.
- TX firmware, RX firmware, protocol specification, and hardware documentation.
- Build, packaging, and CI workflows that are part of how the application/firmware is delivered.

For each source file:
- Display repository path and pinned commit.
- Explain file responsibility and whether it is active in the physical prototype.
- List classes, functions, constants, and important global state.
- Explain each function's inputs, outputs, side effects, and callers.
- Provide line-anchored source links and a line-by-line reading mode.
- Show outgoing calls/dependencies and incoming callers.
- Link related application, firmware, protocol, and hardware concepts.
- Mark tests, build scripts, assets, generated files, database files, and documentation separately from runtime code.

Use progressive disclosure: show a short responsibility summary first; expand into symbols, then line-level explanation. Do not dump entire large files by default.

### Cross-file execution graph

Provide interactive graphs for:
- TX UI event → TXAppState → TXPhysicalBackend → TXSerialController → SerialSession → TX firmware.
- TX firmware → GPIO5 → LED driver → LED → optical channel.
- Photodiode → OPA2604 → LM393 → RX GPIO5/ADC/PWM pins → RX firmware.
- RX firmware → serial output → RXPhysicalBackend → RXAppState → dashboard/inspect/export.
- Settings UI → SettingsManager/QSettings → serial command → firmware setting handler.

Each graph node must open its source file at the relevant line range. Each edge must be supported by a verified call, message, signal, or physical connection. Mark inferred conceptual relationships as such; do not invent call edges.

### Source revision and line-number policy

- Firmware/protocol teaching baseline: OpenVLC-Public main, 411f183a8592d8285118f613bb4909c5bbd9d3cc.
- Desktop application lessons should use the exact repository revision selected after a source audit. The main branch currently contains the application source files, but alternate redesign branches and draft snapshots exist.
- The application UI snapshot at 80ef4afa63a3fe571ffd5026560bf7d7d90fbecc is not the same as the current main baseline; mark it experimental if used.
- Generate line numbers from the pinned file revision; never type line numbers by hand without verifying them against that exact commit.
- Deep Dive links should use immutable commit URLs, not moving main-branch URLs.
- If the source changes, preserve the old snapshot and add a new version rather than silently shifting the meaning of old lessons.

---

## 7. Visual design, typography, and interaction improvements

### Typography

Adopt a deliberate two-family system:
- Reading/UI: a highly legible sans-serif such as Inter or Plus Jakarta Sans.
- Code/technical data: JetBrains Mono or Fira Code, with a consistent fallback.

Use the source repository's bundled font assets as candidates, but verify license, subset, loading, and rendering before copying them. Do not add unnecessary remote font dependencies.

Improve:
- body text size and line height,
- heading scale and weight,
- contrast between headings, explanations, captions, labels, and metadata,
- paragraph width and whitespace,
- code line height and indentation,
- syntax highlighting contrast,
- line-number legibility,
- inline code appearance,
- long path/identifier wrapping,
- code panel padding and mobile font sizing.

Code should look and read like code, not ordinary body text with colored words. Keep code blocks horizontally scrollable when needed, but keep the surrounding explanation responsive and readable.

### Page transitions and navigation

- Use subtle route transitions (short fade/slide) rather than abrupt content replacement.
- Preserve scroll position when returning to a lesson; reset or restore deliberately when entering a different chapter.
- Keep transitions fast and consistent; avoid animation that delays reading.
- Respect reduced-motion preferences.
- Animate page headers and lesson content with restrained stagger, not every element at once.
- Add clear active states and a small progress indicator.
- Avoid scroll hijacking and surprise auto-advance.

### Responsive interactive models

Rebuild models for touch-first use:
- The animation viewport must adapt to the device width and height; do not shrink a desktop diagram until labels become unreadable.
- Offer drag/pan, pinch or explicit zoom controls where appropriate, reset view, and fit-to-screen.
- Provide touch-sized stage controls, scrub/step controls, pause/resume, and a compact legend.
- Use progressive detail: overview on the first view, tap a node to inspect deeper.
- Allow a model to become full-screen on mobile when detailed inspection requires space.
- Keep labels readable and avoid clipping, cramped model frames, or excessive horizontal scrolling.
- Ensure animation remains usable without hover.

### Distinct animations with engineering meaning

Avoid reusing the same generic node diagram for every lesson. Give each concept a visual grammar:
- File selection: file card, metadata, CRC calculation, queue vs active-send distinction.
- Serial transfer: command/ACK packets moving through a USB cable with a terminal.
- 4B5B: nibble-to-codeword transformation with bit slots.
- OOK: light intensity/pulse train synchronized to bit timing.
- LED driver: GPIO polarity, transistor/MOSFET switching, 12 V load.
- Optical path: beam/field-of-view, distance, alignment.
- RX analog chain: photocurrent → amplifier voltage → comparator threshold.
- Sampling: three sample points and majority decision.
- Frame parsing: header fields, chunk indexes, CRC pass/fail.
- Reconstruction: chunks assembling into a file, with missing/corrupt chunks visibly distinct.
- Signal monitor: live traces with labels and clearly marked sample provenance.

Animations must be controllable and explanatory: pause, step, replay, speed, focus a stage, and reveal the corresponding code. Use motion to explain cause and effect, not as decoration.

---

## 8. Practice and assessment

Add practice after the relevant concepts are taught, not as a replacement for explanations.

### Micro-checks
- After a user selects a file: distinguish selection, queueing, and starting.
- After serial setup: identify which device and baud rate are used.
- After 4B5B: decode a nibble and reject an invalid codeword.
- After OOK: explain the meaning of a logical one/zero and active-low hardware.
- After RX sampling: determine the majority of three samples.
- After CRC: distinguish chunk validity from whole-file completeness.
- After BER: identify why the receiver needs the original reference file.

### Scenario labs
- TX device not detected.
- Wrong serial port or firmware role.
- TX start attempted while disconnected.
- Receiver has no signal swing.
- PVo/Vref margin is too small.
- Sync is found but a codeword is invalid.
- Some chunks arrive but the file is incomplete.
- CRC passes but the selected reference file is wrong.
- Large file is split into batches.

Each question should explain why the answer is correct and link back to the relevant visual stage and source code. Avoid punitive scoring; prioritize understanding and retrying.

---

## 9. Accuracy, source audit, and fixes required before content expansion

The source repository contains useful codemap documents, but some descriptions appear stale relative to the actual implementation. For example, the TX/RX codemaps describe some pages as placeholders or describe a physical/simulated mode toggle while the corresponding page files contain substantial implemented behavior. Do not use codemaps as the sole authority.

Before writing detailed lessons:
1. Audit actual UI navigation and which page constructors are registered in each shell.
2. Trace actual button/signal connections to their handlers.
3. Trace state/backend/controller boundaries.
4. Trace serial commands and response parsing on both sides.
5. Trace firmware handlers and hardware pins.
6. Compare all codemaps with executable source and record corrections.
7. Classify active prototype behavior versus legacy, optional, experimental, placeholder, and demo behavior.
8. Identify code paths that exist but are not reachable through the current UI.
9. Verify every setting's actual handler and firmware effect.
10. Verify each graph/viewer's real data source.

Specific known documentation risks:
- TX File Manager's Add to Transmit Queue and Dashboard's Select File/Start path are distinct.
- The TX dashboard's DigitalBitstreamWidget uses a deterministic illustrative bit sequence derived from file size; it is not a capture of the exact outgoing firmware bitstream.
- RX export/session inspection can fall back to synthesized waveform data when no saved capture is present.
- Seed/demo data exists in parts of the RX history/experiment path.
- The application source has physical and simulation backend classes/branches even though the Academy's default learning experience must be physical-prototype-first. Keep simulation out of the normal story; if the full repository explorer exposes it, label it as alternate/test infrastructure, not as the real prototype's signal path.
- The separate application redesign branch at 80ef4afa63a3fe571ffd5026560bf7d7d90fbecc must not be presented as the stable thesis-tested app without reconciliation.

---

## 10. Prioritized delivery plan

### Phase 0 — Source truth and content map
- Freeze firmware/protocol baseline and choose the exact application source revision.
- Audit all UI routes, event handlers, state transitions, serial messages, firmware handlers, and hardware links.
- Correct stale codemaps and produce a machine-readable source inventory.
- Build a source evidence ledger: claim → file → exact lines → revision → confidence/provenance.
- Deliverable: verified architecture and user-flow map; no new decorative content before this is complete.

### Phase 1 — Information architecture and design system
- Finalize navigation and guided/deep-dive separation.
- Establish typography, code styling, spacing, colors, responsive breakpoints, interaction patterns, page transitions, and accessibility rules.
- Create reusable lesson, source excerpt, timeline, settings explainer, model, and checkpoint components.
- Deliverable: design-system implementation and one representative lesson on mobile and desktop.

### Phase 2 — End-to-end TX-to-RX scenario
- Build the flagship “Follow one file” experience across all application, serial, firmware, and hardware layers.
- Add stage-specific animated models and event timeline.
- Add source links from each stage.
- Cover normal transfer and key failure branches.
- Deliverable: complete end-to-end scenario that can be followed without prior programming knowledge.

### Phase 3 — TX and RX application atlas
- Document all actual pages and navigation destinations.
- Explain dashboard, file manager, receive, signal, inspect, BER, experiments, table builder, export, and logs.
- Add interactive screen maps and control explanations.
- Deliverable: readers can explain what each application screen is for and what happens when they use it.

### Phase 4 — Settings and observability
- Build TX/RX settings catalog and map each setting to persistence, handler, serial command, firmware, and physical effect.
- Add Signal Monitor, waveform, chunk map, hex/bit, history, and export viewer lessons.
- Enforce telemetry/capture/example/demo provenance labels.
- Deliverable: readers can interpret the important diagnostics and understand what changing a setting actually does.

### Phase 5 — Guided code curriculum
- Implement the 20-step curated code path.
- Explain the important lines and their caller/callee relationships.
- Add “what if this changes?” experiments and source-grounded examples.
- Deliverable: a beginner can trace the most important behavior without opening every source file.

### Phase 6 — Deep Dive repository explorer
- Inventory every tracked executable source and relevant build/config file.
- Add file search, symbol index, function details, line-by-line mode, dependency graph, and cross-file call paths.
- Distinguish active prototype code, infrastructure, tests, legacy/simulation, experimental branches, and assets/data.
- Deliverable: complete repository coverage with progressive disclosure and immutable source links.

### Phase 7 — Practice and knowledge checks
- Add micro-checks, scenario labs, code-reading questions, and cumulative review.
- Link each explanation back to the source and lesson.
- Deliverable: meaningful practice integrated into the learning path.

### Phase 8 — Visual polish, accessibility, and release validation
- Refine animations, mobile interaction, page transitions, typography, diagrams, and responsive behavior.
- Test keyboard navigation, touch, screen readers/labels, contrast, reduced motion, and narrow screens.
- Run browser tests at small phone, large phone, tablet, laptop, and desktop widths.
- Capture screenshots for each major route and inspect them, not just rely on a successful build.
- Verify every source link and line range against the pinned revision.
- Deliverable: production release with documented test evidence.

---

## 11. Acceptance criteria

The expansion is not complete until all of the following are true:

- A first-time reader can describe the complete physical TX-to-RX process in their own words.
- A reader can explain what happens after selecting a file and pressing Start, including the application-to-firmware handoff.
- The Academy accurately distinguishes File Manager queueing from dashboard direct transmission.
- The reader can follow one data unit through framing, 4B5B, OOK, optical reception, decoding, CRC, and reconstruction.
- RX auto-listening and post-reception user actions are clearly distinguished.
- Every major TX/RX screen, settings category, and engineering viewer has an explanation grounded in its actual implementation.
- Important settings are traced to their persisted key, UI handler, serial command, firmware handler, and hardware effect where applicable.
- Every graph and waveform clearly states whether it is live, recorded, source-derived, illustrative, or demo data.
- Guided code is concise and beginner-friendly.
- Deep Dive covers the complete relevant repository inventory without forcing it into the guided path.
- Every code lesson links to immutable source revisions and verified line ranges.
- Cross-file diagrams show only verified relationships or explicitly mark conceptual inferences.
- Animations are distinct, touch-friendly, controllable, and technically faithful.
- Page transitions are polished but do not obstruct reading or violate reduced-motion preferences.
- Mobile and desktop layouts are visually inspected at representative sizes; build success alone is not accepted as visual QA.
- No simulation is presented as the physical prototype's actual behavior.
- No Vercel deployment or configuration is performed unless separately requested.

---

## 12. Recommended order of reader experience

The ideal reader journey is:

**What is this project?** → **What hardware is on the table?** → **What does a person do in TX?** → **What does the TX app do with the file?** → **What crosses USB?** → **How does the ESP32 turn bytes into light?** → **What happens in the receiver circuit?** → **How does RX decode and rebuild the file?** → **What does the RX app show?** → **How do I inspect and verify the result?** → **How is the code organized?** → **Can I read and explain the important code?** → **Can I explore the whole repository?** → **Can I solve a troubleshooting scenario?**

This sequence should determine the navigation, content, animations, source links, and quizzes. The code is not an appendix disconnected from the project story; it is revealed exactly when the reader needs to understand how the visible behavior is implemented.


---

## 13. External design references and transferable ideas

These are references for learning interaction patterns, not templates to copy or code to rehost.

- **Agily — visual programming lessons:** synchronize animation, the highlighted code line, and a plain-language explanation; let the learner pause, step, alter inputs, predict outcomes, and check understanding. Apply this to the TX/RX execution trace and code lessons.
- **CircuitVerse — interactive digital logic learning:** let learners inspect and manipulate a circuit rather than only reading a static schematic. Apply this to the LED driver, photodiode amplifier/comparator chain, and threshold/sampling lessons; keep our model tied to the actual prototype circuit.
- **Wokwi documentation — embedded systems learning:** organize practical examples around real boards, pins, serial monitors, and hardware/software boundaries. Borrow the clarity of its hardware-first explanations, not its simulation-first product model.
- **3Blue1Brown — visual explanation craft:** introduce one idea at a time, build a model progressively, and use motion to expose relationships that are difficult to see in a static diagram. Apply this to 4B5B, OOK timing, sampling, CRC, and chunk reconstruction.

The Academy should combine these principles into its own identity: editorial engineering documentation, interactive hardware models, synchronized code explanations, and realistic user scenarios. Do not reproduce another site's layout, artwork, copy, or private implementation.


---

## 14. Implementation progress — first workflow milestone

**In progress on branch: feature/end-to-end-transfer-walkthrough.**

The first implementation milestone expands the existing Signal Journey into an end-to-end user-to-hardware walkthrough with five selectable explanation layers:

1. User action
2. Application behavior
3. USB serial messages
4. Firmware / physical hardware
5. What the reader sees in the GUI

The eight stages now follow the actual order of the pinned STREAM firmware path:

1. TX Dashboard file selection and Start
2. TX application state, physical backend, and USB preload
3. Firmware frame and chunk construction
4. 4B5B line coding
5. GPIO5 / LED driver / optical transmission
6. Photodiode and analog receiver front end
7. RX sampling, decoding, frame validation, and chunk storage
8. RX_FILE_HEX handoff, desktop save, Inspect, reference-file selection, and BER

The source baseline for application and firmware lessons is aligned to OpenVLC-Public main at 411f183a8592d8285118f613bb4909c5bbd9d3cc. The earlier experimental application snapshot is no longer used for the guided lessons.

New guided code lessons cover:
- TX Dashboard file selection
- TX Dashboard Start handler
- RX completed-file parsing and saving
- Method 2 reference-file BER comparison

The repository map is expanded with the TX File Manager, TX/RX settings, RX dashboard, signal monitor, Inspect, BER Analyzer, and export pages. Code typography has been moved to an Inter + JetBrains Mono system, and the page route has a short motion transition.

**Accuracy details included:**
- File Manager queueing is explicitly distinguished from Dashboard direct Start.
- The default teaching story follows the physical backend; simulation is described only as alternate/test infrastructure.
- DMA is described as a capability-gated alternate route; the walkthrough uses the STREAM path.
- The TX Dashboard bitstream widget is labeled as illustrative, not a physical capture.
- RX does not require a receive-file picker. The user chooses the original reference file later when performing BER comparison.
- Firmware CRC validation and reference-file BER comparison are kept conceptually separate.

**Still outstanding after this milestone:** the full TX/RX screen atlas, complete settings-to-firmware mapping, signal graph and viewer provenance lessons, repository-wide Deep Dive inventory and symbol explorer, more scenario labs, and expanded visual QA. These remain separate phases and are not claimed as complete.
