# OpenVLC System Suite

An experimental Visible Light Communication (VLC) system developed in partial fulfillment of the requirements for the degree of Bachelor of Science in Electronics Engineering.

This repository contains the ESP32 microcontrollers firmware, system block diagrams, and academic thesis documentation.

## Precompiled GUI Desktop Applications

To run the OpenVLC GUI desktop application, download the precompiled binary for your operating system from the [Releases](../../releases/latest) page:
- **Windows**: Download `OpenVLC-Suite-Windows.exe` and double-click to run it.
- **Linux**: Download `OpenVLC-Suite-Linux`, mark it as executable (`chmod +x OpenVLC-Suite-Linux`), and run it.

> **Note on Permissions (Linux)**: To access the ESP32 via serial (e.g. `/dev/ttyUSB0`), ensure your user is in the `dialout` group. You can add your user by running:
> ```bash
> sudo usermod -a -G dialout $USER
> ```
> (You may need to log out and log back in for this to take effect).

## Firmware Setup

The required firmware for the ESP32 is located in the `firmware/` directory:
1. **Receiver (RX)**: Flash the RX ESP32 with `firmware/rx/rx.ino`.
2. **Transmitter (TX - DMA)**: Flash the TX ESP32 with `firmware/tx_dma/tx_dma.ino`. (Recommended for high symbol rates using DMA).
3. **Transmitter (TX - Non-DMA)**: Flash the TX ESP32 with `firmware/tx_non_dma/tx_non_dma.ino`. (Standard GPIO implementation).

## Architecture & Documents

For detailed diagrams and documentation regarding the VLC system:
- **Research Design Block Diagram**: Inspect the block diagram image at [docs/research_design_block_diagram.png](docs/research_design_block_diagram.png).
- **Academic Thesis Paper**: The thesis manuscript describing the hardware and software design is available in Word and PDF formats under [docs/vlcpaper.docx](docs/vlcpaper.docx) and [docs/vlcpaper.pdf](docs/vlcpaper.pdf).

## License & Legal

This project is proprietary and confidential. All rights are reserved by the author. Use, redistribution, and citation are regulated under the terms of the project [LICENSE](LICENSE).

Copyright © 2026 Reymart Martinez. All rights reserved.
