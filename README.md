# OpenVLC System Suite

[![GitHub Release](https://img.shields.io/github/v/release/luckyprinter/OpenVLC-Public?style=flat-square&color=blue)](../../releases/latest)
[![GitHub Downloads](https://img.shields.io/github/downloads/luckyprinter/OpenVLC-Public/total?style=flat-square&color=orange)](../../releases)

### Low-Cost ESP32-Based Visible Light Communication Prototype

This repository contains the software, firmware, communication protocol documentation, and supporting technical materials associated with the Visible Light Communication (VLC) prototype developed as part of a Bachelor of Science in Electronics Engineering thesis.

The repository serves as the software and firmware companion to the thesis and provides the implementation used in the development, testing, and evaluation of the prototype.

> **Academic Research Repository**
>
> This repository is maintained as a public research artifact accompanying the thesis. The source code and associated materials are provided for academic evaluation, research, and peer-review purposes subject to the terms of the included license.

---

## 1. Project Overview

The OpenVLC System Suite is a low-cost short-range indoor Visible Light Communication prototype based on ESP32 microcontrollers.

The system consists of an ESP32 transmitter, an ESP32 receiver, a visible-light communication channel using a commercial 12 V DC LED bulb, a photodiode-based optical receiver, and desktop transmitter and receiver applications.

The communication system uses:

* 4B5B line coding
* NRZ/OOK optical signaling
* ESP32-based transmitter and receiver processing
* CRC-based frame and payload validation
* Chunk-based payload transmission and reconstruction
* Adaptive receiver threshold/Vref control
* USB serial communication between the ESP32 modules and desktop applications
* Real-time receiver signal monitoring through the desktop GUI

The system was developed as an experimental prototype for evaluating the feasibility and communication performance of a low-cost indoor VLC implementation.

---

## 2. Relationship to the Thesis

This repository accompanies the thesis manuscript describing the design, development, and evaluation of the VLC prototype.

The thesis contains the methodology, experimental procedures, measured results, analysis, conclusions, and recommendations. This repository provides the corresponding software and firmware implementation used to support the prototype.

The relationship between the thesis appendices and this repository is as follows:

| Thesis Section                                  | Repository Material                                   |
| ----------------------------------------------- | ----------------------------------------------------- |
| Appendix N: Prototype Operations and User Guide | Operational procedures for using the prototype        |
| Appendix O: Selected Firmware and Code Snippets | Representative firmware implementation excerpts       |
| Appendix P: Source Code and Software Repository | Complete software and firmware repository             |
| Chapter III: Methodology                        | Experimental configuration and implementation details |
| Chapter IV: Results and Discussion              | Experimental results reported in the thesis           |

The repository should therefore be treated as a technical companion to the thesis rather than as a replacement for the thesis itself.

---

## 3. System Architecture

The prototype is composed of the following major layers:

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

Detailed system diagrams and technical documentation are provided in the `docs/` and `firmware/` directories.

---

## 4. Experimental Configuration

The thesis experiments used a controlled short-range indoor VLC configuration.

| Parameter                 | Baseline Configuration |
| ------------------------- | ---------------------- |
| Microcontroller           | ESP32                  |
| Optical Source            | 12 V DC LED bulb       |
| Default LED Rating        | 12 W                   |
| Additional LED Ratings    | 6 W and 9 W            |
| Line Coding               | 4B5B                   |
| Modulation                | NRZ/OOK                |
| Symbol Rate               | 15 ksymbols/s          |
| Default Chunk Size        | 256 bytes              |
| Frame Gap                 | 1 ms                   |
| Receiver Photodiode       | BPW34                  |
| Transimpedance Amplifier  | OPA2604                |
| Comparator                | LM393                  |
| LED Mounting Height       | 2.40 m                 |
| Receiver Height           | 0.30 m                 |
| Vertical Separation       | 2.10 m                 |
| Communication Arrangement | Line-of-Sight (LOS)    |
| Target Receiver Margin    | 0.365 V                |
| Stable Receiver Margin    | 0.28–0.45 V            |
| LED Idle State            | ON                     |

These values represent the baseline configuration described in the thesis. Individual experiments may use different independent-variable conditions as specified in the experimental procedures.

---

## 5. Repository Structure

### `application-source/`

Contains the complete Python/PySide6 desktop application source code for the transmitter and receiver interfaces.

The application provides:

* Transmitter control
* Receiver control
* USB serial communication
* Transmission and reception status monitoring
* Signal visualization
* Payload handling
* Session and logging functionality
* Simulation-related application components
* Application settings and interface components

Detailed application installation and development instructions are available in:

`application-source/README.md`

---

### `firmware/`

Contains the ESP32 firmware used by the optical communication system.

```text
firmware/
├── rx/
├── tx_dma/
├── tx_non_dma/
├── specs/
├── README.md
└── codemap.md
```

The firmware includes:

* 4B5B encoding and decoding
* NRZ/OOK optical signaling
* Frame synchronization
* CRC validation
* Chunk processing
* Payload reconstruction
* Receiver threshold/Vref control
* Serial control and status communication

The communication protocol is documented in:

`firmware/specs/protocol_spec.md`

---

### `docs/`

Contains the thesis manuscript and selected supporting technical documentation.

The thesis document is the primary reference for the methodology, experimental procedures, measured results, analysis, conclusions, and recommendations.

---

## 6. Firmware Configuration

The repository currently contains separate transmitter implementations for DMA and non-DMA operation.

```text
firmware/tx_dma/
firmware/tx_non_dma/
```

The receiver firmware is located in:

```text
firmware/rx/
```

### Experimental Firmware Identification

The exact transmitter and receiver firmware used for the experimental results reported in the thesis are identified in the corresponding thesis release.

**IMPORTANT:** The thesis release should be treated as the authoritative software snapshot for reproduction of the reported experiments.

Development versions or subsequent changes to the `main` branch may not correspond to the exact implementation used to obtain the reported experimental results.

---

## 7. Firmware Pin Reference

### Transmitter

| ESP32 Pin | Function                      |
| --------- | ----------------------------- |
| GPIO5     | 4B5B + NRZ/OOK optical output |

### Receiver

| ESP32 Pin | Function                             |
| --------- | ------------------------------------ |
| GPIO5     | LM393 comparator digital output      |
| GPIO25    | PWM output for adaptive Vref control |
| GPIO34    | Scaled PVo ADC input                 |
| GPIO35    | Scaled Vref ADC input                |

The receiver uses the ESP32 ADC inputs to monitor the scaled photodiode-output and comparator-reference voltages.

Detailed firmware configuration and serial commands are provided in `firmware/README.md`.

---

## 8. Communication Protocol

The VLC system uses a framed communication protocol incorporating 4B5B line coding, NRZ/OOK signaling, chunk-based payload handling, and CRC validation.

A complete description of the protocol is provided in:

`firmware/specs/protocol_spec.md`

The protocol documentation describes:

* Frame structure
* Start-of-frame information
* Transfer identification
* Frame type
* Payload size
* Chunk indexing
* File CRC
* Chunk CRC
* Frame CRC
* Filename handling
* Transmission flow
* BER comparison procedure

---

## 9. BER Evaluation

For the thesis evaluation, Bit Error Rate (BER) is determined by comparing the received or reconstructed data against the corresponding original reference data.

The repository protocol documentation describes the corresponding comparison procedure.

The thesis provides the detailed BER methodology, calculations, experimental records, and interpreted results.

---

## 10. Desktop Applications

Precompiled desktop applications are provided through the GitHub Releases page when available.

### Windows

Download the Windows executable from the Releases page and launch the application.

### Linux

Download the Linux executable from the Releases page.

If serial-port permission is required on Linux, ensure that the current user has access to the appropriate serial device.

For running the application directly from source, see:

`application-source/README.md`

---

## 11. Running the Application from Source

### Requirements

* Python 3.10 or later
* pip
* Python packages listed in `application-source/requirements.txt`

### Installation

```bash
cd application-source
pip install -r requirements.txt
```

### Launch

```bash
python run_v3.py
```

### Launch Receiver

```bash
python run_v3.py --rx
```

### Launch Transmitter

```bash
python run_v3.py --tx
```

### Run Smoke Test

```bash
python run_v3.py --smoke-test
```

For complete build and development instructions, refer to:

`application-source/README.md`

---

## 12. Thesis Documentation

The thesis manuscript and supporting documents are located in the `docs/` directory.

The thesis should be considered the primary source for:

* Research objectives
* Research methodology
* Experimental design
* Test procedures
* Experimental measurements
* Results
* Data analysis
* Conclusions
* Recommendations

The repository supplements the thesis by providing the associated software and firmware implementation.

---

## 13. Releases

Releases are used to preserve identifiable versions of the software and supporting research materials.

For thesis reproducibility, the release identified as the **thesis artifact release** should be used when reproducing the software configuration associated with the reported experimental results.

Later development versions may contain changes that are not represented in the thesis.

---

## 14. Citation

When referring to this software repository in an academic work, please cite the author and the associated thesis.

A machine-readable citation record is provided in:

`CITATION.cff`

The repository license also specifies the citation requirement for academic use.

---

## 15. Research Artifact Scope

This repository is intended to document the software and firmware implementation of an experimental VLC prototype.

It is not presented as a commercial-grade LiFi/VLC product or as a production communication platform.

System performance depends on the hardware configuration, optical alignment, receiver electronics, LED source, symbol rate, ambient-light conditions, and other experimental parameters described in the thesis.

---

## 16. Known Limitations

The prototype was developed for experimental and academic evaluation.

The implementation may require the specific hardware, electrical interfaces, firmware configuration, and communication settings documented in the repository and thesis.

The existence of a software feature in the repository does not imply that the feature was used in every experiment reported in the thesis.

For reproduction of a particular thesis result, use the experimental configuration and software version associated with the corresponding thesis release.

---

## 17. License

This repository is subject to the terms specified in the included `LICENSE` file.

The software, firmware, and associated documentation are provided for academic evaluation and peer-review purposes under the stated license restrictions.

---

## 18. Author

**Reymart Martinez**

Bachelor of Science in Electronics Engineering

Copyright © 2026 Reymart Martinez. All rights reserved.
