# OpenVLC System Suite — ESP32 Firmware

This directory contains the ESP32 firmware used by the transmitter and receiver portions of the OpenVLC System Suite Visible Light Communication prototype.

The firmware implements the optical communication functions required for the experimental VLC link, including line coding, optical signaling, frame processing, CRC validation, chunk handling, receiver threshold control, and USB serial communication with the desktop applications.

---

## 1. Firmware Components

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

### Receiver

`rx/rx.ino`

The receiver firmware:

* acquires the optical data signal
* decodes 4B5B symbols
* reconstructs received bytes
* validates frame and chunk CRC values
* manages received chunks
* supports adaptive and manual receiver threshold control
* reports receiver status through USB serial communication

### Transmitter — DMA

`tx_dma/tx_dma.ino`

The DMA transmitter implementation provides scheduled optical symbol output using the ESP32 DMA-based transmission approach.

### Transmitter — Non-DMA

`tx_non_dma/tx_non_dma.ino`

The non-DMA transmitter implementation provides the standard GPIO-based optical transmission path.

---

## 2. Thesis Experimental Firmware

This repository contains both DMA and non-DMA transmitter implementations because they represent different firmware implementations developed during the project.

For the experimental results reported in the thesis, use the transmitter and receiver firmware identified in the corresponding thesis artifact release.

> **Do not assume that the presence of a firmware variant means that it was used in every thesis experiment.**

The thesis release is the authoritative software snapshot for reproducing the reported experiments.

---

## 3. Communication Configuration

The baseline thesis communication configuration is:

| Parameter          | Value         |
| ------------------ | ------------- |
| Line Coding        | 4B5B          |
| Modulation         | NRZ/OOK       |
| Symbol Rate        | 15 ksymbols/s |
| Default Chunk Size | 256 bytes     |
| Frame Gap          | 1 ms          |
| LED Idle State     | ON            |

The communication protocol is documented in:

`specs/protocol_spec.md`

---

## 4. Transmitter Pin Configuration

| ESP32 GPIO | Function                      |
| ---------- | ----------------------------- |
| GPIO5      | 4B5B + NRZ/OOK optical output |

GPIO5 is connected to the transmitter driver stage used to switch the 12 V DC LED source.

The firmware supports the active-low driver configuration required by the implemented driver circuitry.

---

## 5. Receiver Pin Configuration

| ESP32 GPIO | Function                                           |
| ---------- | -------------------------------------------------- |
| GPIO5      | LM393 Channel A digital output / recovered RX data |
| GPIO25     | PWM output for adaptive Vref control               |
| GPIO34     | Scaled PVo ADC input                               |
| GPIO35     | Scaled Vref ADC input                              |

The receiver ADC inputs monitor scaled analog voltages from the receiver circuit to keep the monitored signal within the ESP32 ADC input range.

---

## 6. Receiver Threshold and Vref Control

The receiver firmware provides serial commands for controlling and evaluating the comparator reference voltage.

Available commands include:

```text
VREF_MODE=AUTO|MANUAL
VREF_PWM=<gpio25_pwm_percent>
VREF_SET=<target_mV>
VREF_PWM_FS=<gpio35_full_scale_mV>
VREF_SETTLE_MS=<delay_ms>
VREF_GET
VREF_MARGIN=<target_margin_mV>
VREF_CAL
VREF_CAL_SWING
VREF_SWEEP=<start_mV>,<end_mV>,<step_mV>
```

The adaptive Vref implementation measures the received signal and adjusts the receiver reference threshold to maintain the desired operating margin.

The experimental calibration procedure and measurements are documented in the thesis.

---

## 7. Protocol Processing

The firmware uses a framed optical communication protocol incorporating:

* frame synchronization
* 4B5B line coding
* NRZ/OOK signaling
* chunked payload transfer
* chunk CRC
* frame CRC
* file CRC
* payload reconstruction

See:

`specs/protocol_spec.md`

for the protocol definition.

---

## 8. Buffer and File Handling

The firmware uses fixed-size stream buffers.

Current implementation limits include:

* TX stream buffer: 80 KiB
* RX stream buffer: 80 KiB

The desktop application can split larger files into batches for transmission when supported by the corresponding application and firmware implementation.

Large-file handling and maximum-file behavior are discussed in the thesis experimental documentation.

---

## 9. Compilation and Upload

The firmware is intended for ESP32 development environments compatible with the source code, including the Arduino development environment used during the project.

Before uploading firmware:

1. Connect the appropriate ESP32 board by USB.
2. Open the corresponding `.ino` source file.
3. Select the correct ESP32 board configuration.
4. Select the appropriate serial port.
5. Compile the firmware.
6. Upload the firmware to the ESP32.
7. Verify the serial startup/status response before connecting it to the optical hardware.

Use the firmware variant specified by the thesis artifact release when reproducing the reported experimental configuration.

---

## 10. Supporting Documentation

### Protocol Specification

`specs/protocol_spec.md`

Defines the frame structure, data fields, transmission flow, and BER comparison procedure.

### Firmware Codemap

`codemap.md`

Provides a high-level description of the firmware directory and its integration with the desktop applications and protocol documentation.

---

## 11. Relationship to the Thesis

The firmware implementation corresponds to the software side of the prototype described in the thesis.

Appendix O of the thesis provides selected firmware and code snippets for explanation and documentation. This directory contains the complete firmware source.

The thesis remains the primary reference for:

* experimental procedures
* measured values
* test conditions
* performance results
* statistical or comparative analysis
* conclusions

The repository provides the implementation needed to understand and reproduce the software portion of the prototype.
