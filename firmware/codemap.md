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
├── tx_dma/
│   └── tx_dma.ino
├── tx_non_dma/
│   └── tx_non_dma.ino
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

## DMA Transmitter Firmware

### `tx_dma/tx_dma.ino`

Primary responsibilities:

* payload processing
* 4B5B encoding
* NRZ/OOK optical symbol generation
* DMA-based timing/output
* frame construction
* CRC generation
* chunk transmission
* USB serial communication with the desktop application

---

## Non-DMA Transmitter Firmware

### `tx_non_dma/tx_non_dma.ino`

Primary responsibilities:

* payload processing
* 4B5B encoding
* NRZ/OOK optical symbol generation
* GPIO-based optical output
* frame construction
* CRC generation
* chunk transmission
* USB serial communication with the desktop application

---

## Communication Protocol

### `specs/protocol_spec.md`

Defines the communication protocol shared by the TX firmware, RX firmware, and desktop applications.

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

The firmware interacts with the desktop applications through USB serial communication.

The primary data path is:

```text
TX GUI
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
RX GUI
```

The communication protocol documentation provides the common reference between the desktop applications and ESP32 firmware.

---

## Thesis Reference

Appendix O of the thesis contains selected source-code excerpts used to explain important firmware functions.

This repository contains the complete firmware implementation.

The thesis remains the authoritative reference for the experimental procedure and measured results.
