# Firmware Code Map

## Purpose

This document provides a high-level map of the ESP32 firmware organization used by the OpenVLC System Suite prototype.

The purpose of the code map is to help readers, researchers, and developers locate the major firmware components without requiring the complete source code to be reproduced in the thesis.

---

## Directory Structure

```text
firmware/
├── rx/
│   └── rx.ino
├── tx/
│   └── tx.ino
├── specs/
│   └── protocol_spec.md
├── README.md
└── codemap.md
```

---

## Receiver Firmware

### `rx/rx.ino`

Primary responsibilities:

* optical signal sampling
* symbol timing and line decoding
* 4B5B decoding
* frame synchronization
* frame parsing
* CRC validation
* chunk validation
* payload reconstruction
* receiver margin monitoring
* adaptive Vref control
* USB serial status communication

Important receiver signal interfaces include:

| GPIO   | Function                    |
| ------ | --------------------------- |
| GPIO5  | LM393 recovered data signal |
| GPIO25 | PWM control for Vref        |
| GPIO34 | Scaled PVo monitor          |
| GPIO35 | Scaled Vref monitor         |

---

## Transmitter Firmware

### `tx/tx.ino`

Primary responsibilities:

* payload processing
* 4B5B encoding
* NRZ/OOK optical symbol generation
* GPIO-based optical output
* frame construction
* CRC generation
* chunk transmission
* USB serial communication with the desktop application

The transmitter firmware in this repository is the implementation used by the experimental prototype. Earlier transmitter alternatives are intentionally not included in the public thesis artifact.

---

## Communication Protocol

### `specs/protocol_spec.md`

Defines the communication protocol shared by the TX firmware, RX firmware, and desktop application.

The protocol specification includes:

* frame fields
* transfer identification
* chunk structure
* CRC fields
* payload handling
* batch filename handling
* transmission sequence
* BER comparison procedure

---

## Integration

The firmware interacts with the desktop application through USB serial communication.

The primary data path is:

```text
TX Application
  ↓
USB Serial
  ↓
TX ESP32 Firmware
  ↓
4B5B + NRZ/OOK
  ↓
LED Driver
  ↓
Visible Light Channel
  ↓
Photodiode / Analog Receiver
  ↓
Comparator
  ↓
RX ESP32 Firmware
  ↓
USB Serial
  ↓
RX Application
```

The communication protocol documentation provides the common reference between the desktop application and ESP32 firmware.

---

## Thesis Reference

Appendix O of the thesis contains selected source-code excerpts used to explain important firmware functions.

This repository contains the complete firmware implementation used by the prototype.

The thesis remains the authoritative reference for the experimental procedure and measured results.
