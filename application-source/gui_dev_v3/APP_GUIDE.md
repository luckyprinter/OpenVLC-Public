# OpenVLC Desktop Application — Beginner's Code Guide

This guide explains the Python desktop application in plain language. It is intended for new contributors, students, and anyone who needs to explain what a Python file does during a project review or thesis defense.

## 1. What is this software?

The application is a **Python desktop GUI** built with **PySide6 (Qt for Python)**. Its main entry point opens a unified launcher with two operational consoles:

- **TX (transmitter) console:** chooses a file, configures the transmitter, sends the file to the TX ESP32, and displays transmission progress.
- **RX (receiver) console:** connects to the RX ESP32, displays signal and receiver status, receives file data, checks integrity, and provides logs and analysis tools.

The TX and RX consoles have separate state and backend objects. The normal `main()` entry point hosts both in one `VLCMainWindow`; command-line flags can open a console directly. Two separately launched instances can also run independently.

The ESP32 firmware performs the real-time optical transmission and reception. The Python application controls the boards over USB serial, displays information, and manages files and test records. Python does not generate the optical waveform itself.

## 2. The big picture

Think of the application as layers:

```text
User clicks a button
       |
       v
GUI page (what the user sees)
       |
       v
App state (holds current application state)
       |
       v
Physical hardware backend
       |
       v
USB serial connection to ESP32
       |
       v
ESP32 firmware (real-time optical TX/RX)
       |
       v
LED transmitter  --->  optical channel  --->  photodiode receiver
```

The GUI and hardware code are deliberately separated. A dashboard should display state; it should not directly implement serial communication or optical decoding.

## 3. Where should I start reading?

If you are new to this codebase, read these files in this order:

1. `app.py` — application startup and which window is launched.
2. `app_state.py` and `tx_app_state.py` — how the application stores state and routes commands to physical hardware.
3. `rx/shell.py` or `tx/shell.py` — how navigation and pages are assembled.
4. `rx/dashboard.py` or `tx/dashboard.py` — how the main dashboard displays information.
5. `rx/backends/physical.py` or `tx/backends/physical.py` — how the GUI talks to real ESP32 hardware.
6. `serial/session.py`, `serial/controllers.py`, and `serial/detection.py` — lower-level serial communication and firmware command handling.
7. The matching firmware file under `firmware/rx/` or `firmware/tx/` — what the ESP32 does after receiving commands.

Do not start by reading the largest backend file from top to bottom. First understand the flow, then follow one action (for example, clicking Connect or Send).

## 4. Main Python files and what they do

### Application root: `gui_dev_v3/`

| File | Plain-language responsibility |
|---|---|
| `app.py` | Entry point. Creates the Qt application and opens the TX or RX main window. |
| `app_state.py` | Holds receiver application state and coordinates refreshes from the physical ESP32 backend. |
| `tx_app_state.py` | Holds transmitter application state and coordinates refreshes from the physical ESP32 backend. |
| `models.py` | Defines structured data objects used by the receiver, such as signal, session, and transfer information. |


| `widgets.py` | Shared reusable visual components such as cards, badges, progress bars, and waveform widgets. |
| `navigation.py` | Shared navigation definitions and labels. |
| `theme.py` | Colors, themes, spacing/density choices, and Qt stylesheet generation. |
| `settings.py` | Helpers for reading, writing, and binding application settings to GUI controls. |
| `settings_store.py` | Loads and saves the receiver's JSON-based appearance/window settings. |
| `diagnostics.py` | Optional local-only diagnostics queue. It is disabled unless the user opts in; it does not upload telemetry. |
| `logger.py` | Application logging helpers. |
| `version.py` | Application version information. |
| `patch_dashboard.py` | Compatibility or dashboard patch helper; inspect its call sites before changing it. |
| `codemap.md` | Short architecture map for the root package. |
| `APP_GUIDE.md` | This beginner-oriented guide. |

### Receiver pages: `gui_dev_v3/rx/`

| File | Plain-language responsibility |
|---|---|
| `shell.py` | Builds the receiver window layout, sidebar, page stack, and refresh timer. |
| `navigation.py` | Defines receiver navigation tabs. |
| `dashboard.py` | Displays receiver status, transfer progress, signal metrics, waveform, and activity log. |
| `receive_page.py` | Receiver-focused file reception page and controls. |
| `signal_page.py` | Signal monitoring and Vref-related display. |
| `signal_widgets.py` | Reusable receiver signal visualizations. |
| `ber_analyzer_page.py` | Displays BER/file comparison analysis. |
| `inspect_page.py` | Lets the user inspect received transfer information. |
| `experiments_page.py` | Experiment/test management UI. |
| `experiment_store.py` | Saves and retrieves experiment metadata. |
| `table_builder_page.py` | Builds custom tables for organizing test results. |
| `study_data_page.py` | Displays study/test data. |
| `export_page.py` | Export-related UI and actions. |
| `settings.py` | Assembles receiver-specific settings pages. |
| `placeholders.py` | Placeholder pages for sections that are not fully implemented. |
| `codemap.md` | Receiver package architecture map. |

### Transmitter pages: `gui_dev_v3/tx/`

| File | Plain-language responsibility |
|---|---|
| `shell.py` | Builds the transmitter window, navigation, page stack, and refresh timer. |
| `navigation.py` | Defines transmitter navigation tabs. |
| `dashboard.py` | Displays selected file, TX settings, send controls, progress, and logs. |
| `file_manager_page.py` | File selection and file-management UI. |
| `settings.py` | Assembles transmitter-specific settings pages. |
| `placeholders.py` | Placeholder pages for unfinished sections. |
| `codemap.md` | Transmitter package architecture map. |

### Hardware communication: `gui_dev_v3/serial/`

| File | Plain-language responsibility |
|---|---|
| `detection.py` | Lists serial ports, probes ESP32 devices, and identifies whether a port is TX or RX. |
| `session.py` | Shared serial connection foundation: open/close, background reading, sending lines, waiting for responses, and CRC helper. |
| `controllers.py` | Higher-level TX/RX command logic. TX prepares and sends file data; RX controller helpers parse receiver messages and issue receiver commands. |
| `codemap.md` | Serial package architecture map. |

### Physical hardware backends

| File | Plain-language responsibility |
|---|---|
| `tx/backends/physical.py` | Connects the TX GUI to the TX ESP32, applies TX settings, starts file transmission, and converts hardware status into dashboard data. |
| `rx/backends/physical.py` | Connects the RX GUI to the RX ESP32, continuously reads receiver messages, updates signal/transfer state, handles received file data, and manages Vref behavior. |

The physical backends are the bridge between the GUI's application state and the serial communication layer. The RX backend currently owns its persistent serial reader directly; TX uses `TXSerialController`, which inherits from `SerialSession`.


### Supporting packages

#### Data layer: `gui_dev_v3/data/`

| File | Plain-language responsibility |
|---|---|
| `status.py` | Reads runtime status JSON files produced by the hardware/legacy bridge. |
| `records.py` | Loads and parses transfer records, logs, and signal-quality details. |
| `session.py` | Converts status and transfer information into the structured session model shown by the GUI. |
| `codemap.md` | Explains the data package. |
| `experiments.db` | SQLite database file, not a Python module. |

#### Logic layer: `gui_dev_v3/logic/`

| File | Plain-language responsibility |
|---|---|
| `ber_bridge.py` | Pure data-quality calculations and helpers, including BER test payload generation, file comparison, and transfer-quality calculations. |
| `codemap.md` | Explains the logic package. |

#### Backend implementations

| File | Plain-language responsibility |
|---|---|
| `rx/backends/physical.py` | Real receiver hardware implementation. |

| `tx/backends/physical.py` | Real transmitter hardware implementation. |

| `rx/backends/codemap.md`, `tx/backends/codemap.md` | Architecture notes for the corresponding backend packages. |

A file named `__init__.py` marks a folder as a Python package and may expose selected classes/functions for easier imports. It is not normally where the main hardware logic lives.

## 5. What happens when the user connects?

### TX connection

1. The TX backend scans available serial ports.
2. It probes a candidate port at the TX firmware baud rate (115200).
3. The ESP32 responds to a blank-line ping with `TX Ready`.
4. The application opens the persistent serial session.
5. It sends another blank-line ping and waits for `TX Ready` on that persistent connection.
6. Only after the response does it mark the physical backend connected and apply saved TX settings.

### RX connection

1. The RX backend scans available serial ports.
2. It probes a candidate port at the RX firmware baud rate (460800).
3. The ESP32 responds to a blank-line ping with `RX Ready`.
4. The application opens the persistent RX serial port and starts its reader thread.
5. It sends a blank-line ping and waits for `RX Ready` from that persistent connection.
6. Only after the response does it report the connection as successful and apply saved RX settings.

The persistent ready ping is a **USB serial/firmware command-loop readiness check**. It confirms that the ESP32 has finished setup and is processing serial commands. It is not an optical sync signal and does not change preamble, symbol rate, frame gap, or the optical receiver's synchronization algorithm.

The TX and RX applications are separate programs. Their current readiness checks confirm each board to its own GUI; they do **not** create a direct TX-to-RX inter-device handshake. An operator still needs to ensure the RX side is ready before starting a TX test.

## 6. What happens when a file is transmitted?

1. The user selects a file in the TX GUI.
2. The TX application state passes the action to the TX physical backend.
3. The backend starts the controller's send operation in a background thread so the GUI remains responsive.
4. The controller sends serial commands to preload the file into the TX ESP32 (clear stream, begin stream, send data blocks).
5. The controller waits for firmware acknowledgements.
6. The controller sends `STREAM_START`.
7. The TX ESP32 generates the optical 4B5B NRZ/OOK signal through its LED driver.
8. The RX ESP32 detects and decodes the optical signal, checks frames/chunks, and reports received data over its USB serial connection.
9. The RX application reconstructs the file and checks integrity.
10. The TX and RX GUIs display their respective progress and results.

The Python serial transfer to the TX board is not the optical transmission itself. The ESP32 performs the time-sensitive optical signaling.

## 7. Common programming terms in this project

| Term | Beginner-friendly meaning |
|---|---|
| Module | One Python `.py` file that groups related code. |
| Package | A folder of Python modules, usually containing `__init__.py`. |
| Class | A blueprint for an object that groups related data and functions. |
| Function / method | A named block of code that performs a task. A method is a function belonging to a class. |
| Import | Makes code from another module available in the current file. |
| GUI | Graphical user interface: buttons, pages, tables, labels, and windows. |
| Backend | The part that performs work behind the GUI, such as talking to hardware. |
| State | The current values the application is tracking, such as connection status or transfer progress. |
| Callback | A function passed to another part of the program so it can notify the caller when something happens. |
| Signal / slot | Qt's event mechanism: a signal announces an event and a connected slot/function reacts. |
| Thread | A separate path of execution. Used here so serial reading and file sending do not freeze the GUI. |
| Serial / UART | A byte-based communication link between the computer and ESP32 over USB. |
| Protocol | The agreed message format and command sequence used by the Python app and firmware. |
| CRC | A checksum used to detect corrupted data. It is not encryption. |
| Hardware-only mode | The desktop application reads and controls real ESP32 boards through USB serial. |
| Physical backend | The implementation that communicates with real ESP32 boards. |

## 8. A simple way to explain the architecture during a presentation

> "The Python application is the control and monitoring interface. PySide6 builds the graphical interface. The application state keeps track of the current TX or RX status. The physical backend connects that state to the ESP32 through USB serial. The application has no virtual hardware mode. The ESP32 firmware performs the time-critical optical transmission and reception. This separation keeps the user interface, hardware communication, and optical signal processing organized into different parts."

## 9. Safe code-reading workflow

When asked what a file does:

1. Read the module's opening docstring and imports.
2. Find its main class or public functions.
3. Look for where that class is created (search for its name).
4. Follow one action from the GUI to the backend and then to the serial command.
5. Check the corresponding ESP32 firmware command handler.
6. Check tests before changing behavior.

When explaining a function, use this pattern:

- **Purpose:** What task does it perform?
- **Input:** What information does it receive?
- **Process:** What are the important steps?
- **Output/effect:** What does it return, change, send, or display?
- **Dependencies:** Which other modules or hardware does it rely on?

Do not assume a function controls the optical signal just because it is in the TX or RX folder. Check whether it only updates the GUI, sends a USB serial command, or actually runs on the ESP32.

## 10. Testing limitation

Mock serial tests can verify host-side connection logic, command ordering, parsing, and error handling. They cannot prove that the ESP32 USB-UART adapter behaves exactly like the mock, that DTR/RTS wiring does not reset a particular board, or that the optical link works. Those require physical validation with both ESP32 boards and the LED/photodiode setup.


## 10. Execution walkthrough: from launching the program to showing a page

This section follows the actual call path in the current source.

### A. `app.py`: the entry point

Start with `main()`. In simplified order, it:

1. Loads optional design tokens and applies them to the theme.
2. Configures Qt high-DPI behavior.
3. Creates the `QApplication` object. This is the Qt application runtime; there should normally be one per process.
4. Loads bundled fonts, selects the Fusion widget style, and applies the stylesheet.
5. Creates `VLCMainWindow`.
6. Checks command-line flags such as `--tx`, `--rx`, or `--smoke-test`.
7. Shows the window and enters `app.exec()`, Qt's event loop.

**Important distinction:** `app.exec()` is not an infinite loop written by the developer. It is Qt's event loop. It waits for events such as mouse clicks, key presses, timers, and signals, then dispatches the connected handlers.

`VLCMainWindow` owns a `QStackedWidget`. Think of this as a deck of pages where only one page is visible at a time. The launcher is added first. When the user chooses TX or RX, `launch_mode()` creates that console only if it has not already been created, then makes it the visible widget.

Useful methods:
- `load_bundled_fonts()`: registers local TTF font files with Qt.
- `load_design_tokens()`: reads optional design configuration from `design.json`.
- `_BaseWindow.__init__()`: loads window settings and applies the display mode and theme.
- `VLCMainWindow.launch_mode(mode)`: lazily creates the selected TX or RX state and shell.
- `VLCMainWindow.return_to_launcher()`: calls console cleanup before removing its widget.
- `main()`: creates the runtime and starts the event loop.

### B. State files: the application's working memory

The GUI should not be responsible for opening serial ports or parsing firmware messages. Instead, it reads values from a state object.

#### `app_state.py` — RX state

The main class is `RXAppState`. It stores receiver-facing values such as:
- the current session and latest transfer;
- signal measurements and activity log;
- whether the serial device is connected;
- the fixed hardware-only operating mode;
- the reference/original file used for comparison;
- captured signal samples for a reception session.

The most important methods are:

| Method | Meaning |
|---|---|
| `__post_init__()` | Initializes capture bookkeeping and performs the first refresh. |
| `subscribe(callback)` | Registers a GUI listener that wants to know when state changes. |
| `notify()` | Calls a snapshot of the registered listeners. |

| `_refresh()` | Asks the physical ESP32 backend for the latest snapshot. |
| `_apply_phy_snapshot(snapshot)` | Copies real-hardware results into RX state. |

| `refresh()` | Public periodic refresh; also tracks and saves reception captures. |
| `send_firmware_command(cmd)` | Sends a command to the connected physical receiver. |
| `cleanup()` | Stops and releases the backend resources. |

A **snapshot** is a package of values representing the backend's current view at a particular refresh. The state layer copies that package into fields that the GUI can display.

The `subscribe` / `notify` pattern is an observer pattern: a page registers interest, and the state tells its listeners when updated. A callback is simply a function that is called later in response to an event.

#### `tx_app_state.py` — TX state

The main class is `TXAppState`. It stores transmitter-facing values such as selected filename, file size, encoding, symbol rate, progress, elapsed time, data rate, connection status, activity log, and session history.

Important methods:
- `_refresh()`: asks the physical ESP32 backend for the latest snapshot.
- `_apply_phy_snapshot()`: copies hardware values into the TX state.
- `start_transmission(filepath)`: forwards the selected file to the physical TX backend.
- `send_firmware_command(cmd)`: forwards a raw command only to a connected physical backend.
- `apply_link_settings_from_ui(...)`: applies UI settings through the connected TX controller.
- `refresh()`: refreshes values, loads a saved capture when available, and notifies listeners.
- `cleanup()`: closes and releases physical serial resources.

**Why have a separate state class for TX and RX?** They display different information and have different actions. Keeping them separate avoids one large state object full of unrelated transmitter and receiver fields.

### C. Shell files: assembling the window

`rx/shell.py` and `tx/shell.py` are the top-level layouts for their respective consoles. A shell is the frame around the pages, not the code that performs optical transmission.

Each shell:
1. Receives its state object.
2. Initializes the hardware-only operating mode.
3. Builds the sidebar and navigation list.
4. Creates a `QStackedWidget` to hold the pages.
5. Builds the footer and connection-status area.
6. Connects the navigation selection signal to `_on_nav_changed()`.
7. Starts a `QTimer` that periodically calls `_on_poll_timer()`.

The shell's `_build_pages()` method creates the actual page objects and adds them to the page stack. The page map connects a stable key such as `dashboard` or `settings` to its widget.

The timer is important:
- RX shell currently polls at `POLL_INTERVAL_MS`, which is 1000 ms (one second).
- TX shell currently polls every 100 ms (ten times per second).

On each tick, `_on_poll_timer()` calls `state.refresh()`, updates the connection indicators, and asks the visible page to refresh if it provides a `refresh()` method. This is why a dashboard can update without the user manually pressing a refresh button.

When leaving a console, `cleanup()` stops its timers and calls `state.cleanup()`. Cleanup is essential: a serial reader or timer left running after a window is removed can continue using resources unexpectedly.

### D. One complete example: clicking Send in TX

Use this chain when tracing a button:

```text
TX dashboard / transmit page
        |
        | user clicks Send
        v
TXAppState.start_transmission(filepath)
        |
        v
TXPhysicalBackend.start_transmission(filepath)
        |
        | creates a background thread
        v
TXSerialController.send_file(path)
        |
        | sends serial commands and file blocks
        v
TX ESP32 firmware
        |
        | generates the optical signal
        v
LED driver and LED
```

The key concept is **delegation**. Each layer passes work to the layer responsible for it:
- The page handles the user interaction.
- The state object routes the action to the physical hardware backend.
- The physical backend prepares the hardware operation and manages its lifecycle.
- The serial controller implements the command/transfer protocol.
- The firmware performs the time-sensitive optical work.

The background thread is important because sending a file may involve many serial writes and waits for acknowledgements. Running that work on the GUI thread could make the window stop responding until the operation finishes.

### E. How to trace any button or setting

For any control, use this five-step method:

1. **Find the widget:** search the page file for the button or input label.
2. **Find its signal connection:** look for `.clicked.connect(...)`, `.valueChanged.connect(...)`, or a Qt signal/slot connection.
3. **Follow the callback:** identify the function that runs after the click or value change.
4. **Follow delegation:** check whether it calls the state object, a backend, or a settings manager.
5. **Find the side effect:** determine whether it changes a displayed value, writes a settings file, sends a serial command, starts a thread, or saves a record.

Do not assume a button talks directly to the ESP32. Follow the function calls until you reach the serial write.

## 11. Important boundaries and details to explain accurately

- **The GUI does not create the optical waveform.** The Python application sends commands and file bytes to the ESP32; firmware handles the time-sensitive optical signaling.
- **The application is hardware-only.** GUI smoke tests and mocked serial tests can verify software behavior, but they are not evidence that the LED, photodiode, analog front end, or optical channel works.
- **TX completion is not the same as RX verification.** A TX-side completion status means the TX-side operation finished; receiver CRC and BER results must come from the RX-side data and comparison.
- **The readiness ping is a serial check.** `TX Ready` or `RX Ready` confirms that the firmware command loop responds over USB serial. It is not an optical synchronization signal.
- **No cross-console readiness coordinator currently exists.** TX and RX each check their own board. The operator still needs to make sure the receiver is ready before starting a test.
- **Mock serial tests are host-side tests.** They can test Python command handling and connection cleanup, but they cannot reproduce USB-UART electrical behavior, ESP32 boot/reset behavior, firmware timing, or light transmission.
- **Do not explain a Python-side setting as a measured hardware value unless the firmware or hardware path confirms it.** Some dashboard fields are presentation defaults or status summaries. Trace the source before claiming a value is being measured.
