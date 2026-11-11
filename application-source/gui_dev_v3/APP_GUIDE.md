# OpenVLC Desktop Application — Beginner's Code Guide

This guide explains the Python desktop application in plain language. It is intended for new contributors, students, and anyone who needs to explain what a Python file does during a project review or thesis defense.

## 1. What is this software?

The application is a **Python desktop GUI** built with **PySide6 (Qt for Python)**. It has two separate user-facing applications:

- **TX (transmitter):** chooses a file, configures the transmitter, sends the file to the TX ESP32, and displays transmission progress.
- **RX (receiver):** connects to the RX ESP32, displays signal and receiver status, receives file data, checks integrity, and provides logs and analysis tools.

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
Backend (physical hardware OR simulation)
       |
       +---- Physical: serial connection to ESP32
       |
       +---- Simulation: generated/mock behavior for UI development
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
2. `app_state.py` and `tx_app_state.py` — how the application stores state and chooses a backend.
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
| `app_state.py` | Holds receiver application state and coordinates refreshes and backend selection. |
| `tx_app_state.py` | Holds transmitter application state and coordinates its backend. |
| `models.py` | Defines structured data objects used by the receiver, such as signal, session, and transfer information. |
| `mock_data.py` | Supplies sample receiver data for simulation and UI development. |
| `tx_mock_data.py` | Supplies sample transmitter data and state types. |
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
| Simulation | A software-only mode that imitates application behavior without controlling the physical VLC hardware. |
| Physical backend | The implementation that communicates with real ESP32 boards. |

## 8. A simple way to explain the architecture during a presentation

> "The Python application is the control and monitoring interface. PySide6 builds the graphical interface. The application state keeps track of the current TX or RX status. The physical backend connects that state to the ESP32 through USB serial, while the simulation backend allows the interface to be tested without hardware. The ESP32 firmware performs the time-critical optical transmission and reception. This separation keeps the user interface, hardware communication, and optical signal processing organized into different parts."

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
