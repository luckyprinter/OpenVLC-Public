# OpenVLC System Suite — Application Source Code

Python/PySide6 desktop application source code for the transmitter and receiver interfaces of the OpenVLC System Suite Visible Light Communication prototype.

This directory contains the complete Python/PySide6 source code for the OpenVLC System Suite GUI application.

## Overview

The OpenVLC GUI v3 is a modern desktop application built with:
- **PySide6** (Qt 6 for Python) — UI framework
- **PyInstaller** — Compiled to standalone executables
- **pyserial** — Hardware communication with ESP32
- **pyqtgraph** — Real-time signal visualization

## Relationship to the Thesis

This application source code provides the desktop software used to interface with the ESP32 transmitter and receiver hardware.

The transmitter application is responsible for preparing and initiating payload transmission through the TX ESP32, while the receiver application communicates with the RX ESP32 and provides reception status, signal monitoring, payload reconstruction, and related interface functions.

The application source is provided as the complete implementation accompanying the thesis.

The thesis remains the primary reference for the experimental procedures, fixed test parameters, measured results, and evaluation.

For the exact software version associated with the reported experimental results, use the thesis artifact release.

## Structure

```text
application-source/
├── gui_dev_v3/
│   ├── app.py                  # Application entry points and window setup
│   ├── app_state.py            # RX hardware state and receiver data
│   ├── tx_app_state.py         # TX hardware state and transmission data
│   ├── models.py               # Shared RX/session data models
│   ├── settings_store.py       # Persistent user settings
│   ├── theme.py                # Application theme and design tokens
│   ├── rx/
│   │   ├── shell.py            # RX navigation and main window
│   │   ├── dashboard.py        # Receiver overview
│   │   ├── receive_page.py     # Received payload view
│   │   ├── signal_page.py      # Signal and waveform monitoring
│   │   ├── export_page.py      # Transfer history and export tools
│   │   └── backends/physical.py
│   ├── tx/
│   │   ├── shell.py            # TX navigation and main window
│   │   ├── dashboard.py        # Transmitter overview
│   │   ├── settings.py         # Hardware link settings
│   │   ├── file_manager_page.py
│   │   └── backends/physical.py
│   ├── serial/                 # Port detection and serial sessions
│   ├── logic/                  # BER and protocol-related application logic
│   └── assets/                 # Fonts and static resources
├── run_v3.py                   # Application launcher
├── OpenVLC-v3.spec             # PyInstaller packaging configuration
├── requirements.txt            # Runtime dependencies
├── requirements-dev.txt        # Runtime + test dependencies
└── requirements-build.txt      # Runtime + test + packaging dependencies
```

## Installation & Running from Source

### Prerequisites
- Python 3.10+
- pip

### Install Dependencies

```bash
cd application-source
pip install -r requirements.txt
```

### Run the Application

```bash
python run_v3.py
python run_v3.py --rx
python run_v3.py --tx
```

### Run Smoke Tests and Automated Tests

The smoke test checks that the application can initialize. The automated test suite also checks hardware contracts and serial behavior.

```bash
python run_v3.py --smoke-test
pip install -r requirements-dev.txt
python -m pytest tests -q
```

## Building Standalone Executables

### Using PyInstaller

Install build and test tools, then package the application:

```bash
pip install -r requirements-build.txt
pyinstaller OpenVLC-v3.spec --clean
```

The built executable will be in `dist/OpenVLC-v3/`.

### Linux-specific Build Dependencies

For Linux builds, the CI workflow installs the required Qt/XCB libraries and uses a virtual display for the packaged smoke test. A typical Ubuntu environment may require:

```bash
sudo apt-get install -y libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0 \
    libxcb-xfixes0 libxcb-shape0 libxcb-randr0 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-icccm4 libxcb-sync1 libx11-xcb1 libxrender1 libegl1 xvfb
```

## Architecture

### State Management
- **RXAppState** (`app_state.py`) — Manages RX session state from the physical ESP32 backend
- **TXAppState** (`tx_app_state.py`) — Manages TX session state and file transmission
- **AppSettings** (`settings_store.py`) — Persistent user preferences

### Backends
- **Physical Backend** — Communicates with real ESP32 hardware via serial
- **Hardware-only operation** — Connects to real ESP32 transmitter and receiver boards through USB serial

### UI Shells
- **RXShell** (`rx/shell.py`) — Receiver console with signal analysis, BER calculation, and Vref control
- **TXShell** (`tx/shell.py`) — Transmitter console with file upload, symbol-rate configuration, and batch handling

## Key Features

- 🎨 **Dark/Light Themes** — Customizable appearance
- 📊 **Real-time Signal Visualization** — Live waveform plots
- 🔧 **Hardware Control** — Vref PWM adjustment and serial command interface
- 📁 **File Transfer** — Application-level handling for larger files
- 🔌 **Hardware-first** — Communicates with real ESP32 transmitter and receiver boards
- ⚙️ **Persistent Settings** — Resolution, theme, and connection settings saved locally

## Development Guidelines

- UI logic lives in the PySide6 widgets under `rx/` and `tx/`.
- State is managed centrally through `RXAppState` and `TXAppState`.
- Settings persist through the application settings layer.
- Serial communication is isolated in the `serial/` package.
- Business logic is organized in the `logic/` package.

## Debugging

Enable verbose Qt plugin logging:

```bash
QT_DEBUG_PLUGINS=1 python run_v3.py
```

Application logs are written to the `logs/` directory relative to the application base directory (or packaged executable directory).

## License

This application source is distributed under the license provided in the repository root. The repository license permits use and redistribution for academic evaluation or peer review subject to its stated conditions.

See the [LICENSE](../LICENSE) file in the root of the repository for the complete terms.

---

**Built for:** ESP32-based Visible Light Communication (VLC) / LiFi Research  
**Framework:** PySide6 6.10.1+  
**Python:** 3.10+
