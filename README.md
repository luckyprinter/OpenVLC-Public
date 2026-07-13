# OpenVLC System Suite

An experimental Visible Light Communication (VLC) graphical user interface developed in partial fulfillment of the requirements for the degree of Bachelor of Science in Electronics Engineering.

This application is designed to monitor, encode, and reconstruct 4B5B + NRZ/OOK optical payloads via ESP32 microcontrollers.

## Features

- **Unified Launcher**: Choose between Transmitter (TX) and Receiver (RX) modes from a single application.
- **Transmitter Console (TX)**: Configure payloads, set symbol rates, and stream visible light data from your TX hardware.
- **Receiver Console (RX)**: Capture optical signals, inspect bit streams, run BER analysis, and build test matrices.
- **Hardware Integration**: Built for ESP32 microcontrollers using simple UART/Serial communication.

## Download & Installation

The easiest way to use the OpenVLC System Suite is to download the compiled executables from the [Releases](../../releases/latest) page.
- **Windows**: Download `OpenVLC-Suite-Windows.exe` and run it directly.
- **Linux**: Download `OpenVLC-Suite-Linux`, mark it as executable (`chmod +x OpenVLC-Suite-Linux`), and run it.

> **Note on Permissions (Linux)**: To access the ESP32 via serial (e.g. `/dev/ttyUSB0`), ensure your user is in the `dialout` group. You can add your user by running:
> ```bash
> sudo usermod -a -G dialout $USER
> ```
> (You may need to log out and log back in for this to take effect).

## Running from Source

If you prefer to run the application from source (e.g. on macOS or for development):

1. **Install Python 3.10+**.
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the launcher**:
   ```bash
   python run_v3.py
   ```

## Firmware Setup

The required firmware for the ESP32 is located in the `firmware/` directory.
1. Flash the ESP32 Transmitter with the `.ino` file in `firmware/tx_esp32_lifi_dual_mode_dma/`.
2. Flash the ESP32 Receiver with the `.ino` file in `firmware/rx/`.

## License & Legal

Copyright © 2026 Reymart Martinez. All rights reserved.
This software is provided "as-is", without warranty of any kind, express or implied. For academic and experimental use only.
