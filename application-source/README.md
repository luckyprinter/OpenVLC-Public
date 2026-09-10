# OpenVLC GUI v3 Application Source Code

This directory contains the complete Python/PySide6 source code for the OpenVLC System Suite GUI application.

## Overview

The OpenVLC GUI v3 is a modern desktop application built with:
- **PySide6** (Qt 6 for Python) — UI framework
- **PyInstaller** — Compiled to standalone executables
- **pyserial** — Hardware communication with ESP32
- **pyqtgraph** — Real-time signal visualization

## Structure

```
application-source/
├── gui_dev_v3/              # Main GUI application package
│   ├── __init__.py
│   ├── app.py               # Main entry points (main(), main_tx())
│   ├── app_state.py         # RX state management & backends
│   ├── tx_app_state.py      # TX state management
│   ├── theme.py             # QSS styling & color schemes
│   ├── widgets.py           # Reusable UI components
│   ├── settings.py          # Settings UI panels
│   ├── settings_store.py    # Persistent app settings
│   ├── navigation.py        # Navigation logic
│   ├── logger.py            # Logging infrastructure
│   ├── models.py            # Data models (SessionState, SignalState, etc.)
│   ├── version.py           # Version & build metadata
│   │
│   ├── rx/                  # Receiver (RX) console UI
│   │   ├── shell.py         # RX main window
│   │   ├── panels/          # RX panel modules
│   │   └── backends/        # Physical & simulation backends
│   │
│   ├── tx/                  # Transmitter (TX) console UI
│   │   ├── shell.py         # TX main window
│   │   └── panels/          # TX panel modules
│   │
│   ├── serial/              # Serial communication layer
│   ├── data/                # Data persistence & session management
│   ├── logic/               # Business logic & signal processing
│   ├── assets/              # Fonts & static resources
│   │
│   ├── mock_data.py         # Mock data for RX testing
│   ├── tx_mock_data.py      # Mock data for TX testing
│   ├── codemap.md           # Code organization reference
│   └── patch_dashboard.py   # Dashboard patching utilities
│
├── OpenVLC-v3.spec         # PyInstaller spec file
├── run_v3.py               # Application entry point
└── requirements.txt        # Python dependencies
```

## Installation & Running from Source

### Prerequisites
- Python 3.10+
- pip

### Install Dependencies

```bash
# Navigate to the source directory
cd application-source

# Install required packages
pip install -r requirements.txt
```

### Run the Application

```bash
# Launch the unified VLC System Suite (launcher mode)
python run_v3.py

# Or launch directly to RX console
python run_v3.py --rx

# Or launch directly to TX console
python run_v3.py --tx
```

### Run Smoke Tests

```bash
python run_v3.py --smoke-test
```

## Building Standalone Executables

### Using PyInstaller

```bash
# Windows
pyinstaller OpenVLC-v3.spec --clean

# Linux
pyinstaller OpenVLC-v3.spec --clean

# The built executable will be in: dist/OpenVLC-v3/
```

### Linux-specific Build

For Linux builds, you may need additional system dependencies:

```bash
sudo apt-get install -y libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0 \
    libxcb-xfixes0 libxcb-shape0 libxcb-randr0 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-icccm4 libx11-xcb1 libxrender1 libegl1
```

## Architecture

### State Management
- **RXAppState** (`app_state.py`) — Manages RX session state with physical/simulated backend switching
- **TXAppState** (`tx_app_state.py`) — Manages TX session state and file transmission
- **AppSettings** (`settings_store.py`) — Persistent user preferences (theme, resolution, serial ports, etc.)

### Backends
- **Physical Backend** — Communicates with real ESP32 hardware via serial
- **Simulation Backend** — Generates synthetic signals for testing without hardware

### UI Shells
- **RXShell** (`rx/shell.py`) — Receiver console with signal analysis, BER calculation, Vref control
- **TXShell** (`tx/shell.py`) — Transmitter console with file upload, symbol rate configuration, batch splitting

## Key Features

- 🎨 **Dark/Light Themes** — Customizable appearance
- 📊 **Real-time Signal Visualization** — Live waveform plots
- 🔧 **Hardware Control** — Vref PWM adjustment, serial command interface
- 📁 **File Transfer** — Automatic batching for files >80 KiB
- 🧪 **Simulation Mode** — Test without hardware
- ⚙️ **Persistent Settings** — Resolution, theme, recent ports saved

## Development Guidelines

- All UI logic lives in PySide6 widgets under `rx/` and `tx/` subdirectories
- State is managed centrally via `RXAppState` and `TXAppState`
- Settings persist to JSON via `AppSettings`
- Serial communication is isolated in the `serial/` package
- Business logic is in the `logic/` package

## Debugging

Enable verbose logging:
```bash
QT_DEBUG_PLUGINS=1 python run_v3.py
```

Check application logs:
```bash
# Logs are saved to the session data directory
# (Usually ~/.openvlc/logs/ on Linux/Mac, %APPDATA%\OpenVLC\logs\ on Windows)
```

## License

This application source code is proprietary and confidential. All rights are reserved by the author.

See the [LICENSE](../LICENSE) file in the root of the repository for full terms.

---

**Built for:** ESP32-based Visible Light Communication (VLC) / LiFi Research  
**Framework:** PySide6 6.10.1+  
**Python:** 3.10+
