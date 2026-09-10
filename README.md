# OpenVLC System Suite

[![GitHub Release](https://img.shields.io/github/v/release/luckyprinter/OpenVLC-Public?style=flat-square&color=blue)](../../releases)
[![GitHub Downloads](https://img.shields.io/github/downloads/luckyprinter/OpenVLC-Public/total?style=flat-square&color=orange)](../../releases)

### Low-Cost ESP32-Based Visible Light Communication Prototype

This repository contains the software, firmware, and communication-protocol implementation associated with the Visible Light Communication (VLC) prototype developed as part of a Bachelor of Science in Electronics Engineering thesis.

The repository serves as the software and firmware companion to the thesis. The thesis remains the primary academic reference for the research objectives, methodology, experimental procedures, measured results, analysis, conclusions, and recommendations.

> **Academic Research Repository**
>
> This repository documents an experimental VLC prototype. It is not presented as a commercial-grade LiFi product, a Wi-Fi replacement, or a certification of compliance with a VLC/LiFi standard.

---

## 1. Relationship to the Thesis

The repository is intended to complement the thesis by making the associated software and firmware implementation available for inspection and reproduction.

| Thesis Section | Repository Material |
|---|---|
| Appendix N: Prototype Operations and User Guide | Operational procedures and system-use guidance |
| Appendix O: Code Snippets of Firmware | Representative firmware implementation excerpts |
| Appendix P: Source Code and Software Repository | Complete software and firmware source repository |
| Chapter III: Methodology | Experimental configuration and implementation details |
| Chapter IV: Results and Discussion | Experimental results and analysis reported in the thesis |

Appendix O presents selected implementation excerpts for explanation. Appendix P provides access to the complete source repository.

---

## 2. System Overview

The OpenVLC System Suite is a low-cost short-range indoor VLC prototype based on ESP32 microcontrollers.

The system consists of an ESP32 transmitter, an ESP32 receiver, a commercial 12 V DC LED bulb used as the optical transmitter, a photodiode-based optical receiver, and desktop transmitter/receiver applications.

The communication implementation includes:

- 4B5B line coding
- NRZ/OOK optical signaling
- Frame synchronization
- CRC-based frame and chunk validation
- Chunk-based payload transmission and reconstruction
- Adaptive receiver threshold/Vref control
- USB serial communication between the ESP32 modules and desktop applications
- Receiver signal monitoring through the desktop GUI

---

## 3. System Architecture

```text
                 TRANSMITTER SIDE

      TX GUI / Desktop Application
                    |
                 USB Serial
                    |
              ESP32 TX Firmware
                    |
              4B5B + NRZ/OOK
                    |
                 GPIO Output
                    |
          2N3904 + MOSFET Driver
                    |
              12 V DC LED Bulb
                    |
             Visible Light Channel
                    |
                    v

                 RECEIVER SIDE

              BPW34 Photodiode
                    |
               OPA2604 TIA
                    |
                LM393 Comparator
                    |
              ESP32 RX Firmware
                    |
          CRC / Chunk Reconstruction
                    |
                 USB Serial
                    |
              RX GUI / Desktop App
```

---

## 4. Baseline Experimental Configuration

The thesis evaluates a controlled short-range indoor VLC configuration. The following values describe the baseline configuration; individual experiments may vary the independent variables as specified in the thesis.

| Parameter | Baseline Configuration |
|---|---|
| Microcontroller | ESP32 |
| Optical Source | 12 V DC LED bulb |
| Default LED Rating | 12 W |
| Additional LED Ratings | 6 W and 9 W |
| Line Coding | 4B5B |
| Modulation | NRZ/OOK |
| Symbol Rate | 15 ksymbols/s |
| Default Chunk Size | 256 bytes |
| Frame Gap | 1 ms |
| Receiver Photodiode | BPW34 |
| Transimpedance Amplifier | OPA2604 |
| Comparator | LM393 |
| LED Mounting Height | 2.40 m |
| Receiver Height | 0.30 m |
| Vertical Separation | 2.10 m |
| Communication Arrangement | Line-of-Sight (LOS) |
| Target Receiver Margin | 0.365 V |
| Stable Receiver Margin | 0.28–0.45 V |
| LED Idle State | ON |

---

## 5. Repository Structure

```text
OpenVLC-Public/
├── application-source/       # Python/PySide6 desktop applications
├── firmware/
│   ├── rx/                  # ESP32 receiver firmware
│   ├── tx_dma/              # DMA-based transmitter firmware
│   ├── tx_non_dma/          # Non-DMA transmitter firmware
│   ├── specs/               # Communication protocol specification
│   └── codemap.md            # Firmware organization reference
├── .github/workflows/       # Automated verification and release workflows
├── CITATION.cff             # Machine-readable citation metadata
├── LICENSE                  # Repository license
└── README.md
```

---

## 6. Desktop Applications

The `application-source/` directory contains the Python/PySide6 source code for the transmitter and receiver applications.

The application provides functionality for:

- Transmitter and receiver control
- USB serial communication
- Transmission/reception status monitoring
- Signal visualization
- Payload handling and reconstruction
- Session and experimental logging
- Simulation-related application components

For source-based installation and execution, see:

`application-source/README.md`

### Running from Source

```bash
cd application-source
pip install -r requirements.txt
python run_v3.py
```

Receiver mode:

```bash
python run_v3.py --rx
```

Transmitter mode:

```bash
python run_v3.py --tx
```

Application smoke test:

```bash
python run_v3.py --smoke-test
```

Precompiled desktop application packages are provided through GitHub Releases when available.

---

## 7. Firmware

The `firmware/` directory contains the ESP32 transmitter and receiver implementations.

### Receiver

```text
firmware/rx/rx.ino
```

### Transmitter — DMA

```text
firmware/tx_dma/tx_dma.ino
```

### Transmitter — Non-DMA

```text
firmware/tx_non_dma/tx_non_dma.ino
```

The repository maintains both transmitter variants as implementation alternatives. The exact transmitter and receiver firmware associated with the thesis experimental results are identified by the thesis artifact release.

The firmware includes 4B5B encoding/decoding, NRZ/OOK signaling, synchronization, CRC validation, chunk processing, payload reconstruction, receiver threshold/Vref control, and serial status/control functions.

---

## 8. Firmware Pin Reference

### Transmitter

| ESP32 Pin | Function |
|---|---|
| GPIO5 | 4B5B + NRZ/OOK optical output |

### Receiver

| ESP32 Pin | Function |
|---|---|
| GPIO5 | LM393 comparator digital output |
| GPIO25 | PWM output for adaptive Vref control |
| GPIO34 | Scaled PVo ADC input |
| GPIO35 | Scaled Vref ADC input |

Detailed firmware configuration and serial commands are provided in `firmware/README.md`.

---

## 9. Communication Protocol

The VLC system uses a framed communication protocol incorporating 4B5B line coding, NRZ/OOK signaling, chunk-based payload handling, and CRC validation.

The protocol specification is provided in:

`firmware/specs/protocol_spec.md`

The specification documents the frame structure, synchronization information, transfer identification, payload/chunk fields, CRC fields, filename handling, transmission flow, and BER comparison procedure.

---

## 10. BER Evaluation

For the thesis evaluation, Bit Error Rate (BER) is determined by comparing received or reconstructed data against the corresponding original reference data.

The repository provides the software/protocol implementation supporting the transfer and reconstruction process. The thesis provides the detailed BER methodology, calculations, experimental records, and interpreted results.

---

## 11. Automated Verification and Releases

GitHub Actions are used to verify firmware compilation and to build/package release software.

The firmware verification workflow compiles the receiver, DMA transmitter, and non-DMA transmitter implementations using the ESP32 Arduino core.

The desktop application release workflow in the associated development repository builds the PyInstaller application for Windows and Linux, performs application smoke tests, and publishes the resulting packages to the corresponding release in this repository.

Development releases and the thesis artifact release are treated separately. A development workflow must not overwrite the fixed thesis artifact release.

---

## 12. Thesis Artifact Release

A dedicated release will identify the software and firmware state associated with the experimental implementation reported in the thesis.

**Planned thesis artifact tag:** `v1.0.0-thesis`

The thesis artifact release is intended to provide a fixed reference for reproducibility. Subsequent changes to the `main` branch may contain development changes and should not automatically be assumed to represent the configuration used to obtain the reported experimental results.

After publication, use the thesis artifact release rather than the moving `main` branch when reproducing the reported software configuration.

---

## 13. Research Artifact Scope and Limitations

This repository is provided as a research and academic software artifact accompanying the VLC prototype.

Performance and operation depend on the hardware configuration, optical alignment, communication parameters, receiver circuit, LED source, ambient-light conditions, and other experimental conditions described in the thesis.

The presence of a feature or firmware variant in the repository does not imply that it was used in every experiment reported in the thesis.

For reproduction of a particular thesis result, use the experimental configuration and software version identified by the thesis artifact release.

---

## 14. Citation

When referencing this repository in academic work, cite the author and associated thesis according to the repository citation information and license requirements.

Machine-readable citation metadata is provided in:

`CITATION.cff`

---

## 15. License

This repository is subject to the terms specified in the included `LICENSE` file.

The software, firmware, and associated materials are provided under the stated license restrictions.

---

## 16. Author

**Reymart Martinez**

Bachelor of Science in Electronics Engineering

Copyright © 2026 Reymart Martinez. All rights reserved.
