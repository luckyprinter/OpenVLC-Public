# OpenVLC System Suite — ESP32 Firmware

This directory contains the ESP32 firmware used by the transmitter and receiver portions of the OpenVLC System Suite Visible Light Communication prototype.

The firmware implements 4B5B line coding, NRZ/OOK optical signaling, frame synchronization, CRC validation, chunk handling, receiver threshold control, and USB serial communication with the desktop application.

---

## 1. Firmware Components

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

### Transmitter

`tx/tx.ino`

The transmitter firmware provides the GPIO-based optical transmission path used by the experimental prototype. It receives preloaded file data from the TX application, encodes payload bytes using 4B5B, and transmits the resulting NRZ/OOK signal through GPIO5.

This repository intentionally provides one transmitter implementation: the firmware used by the experimental prototype. Alternative transmitter implementations developed during earlier stages are not part of the public thesis artifact.

---

## 2. Thesis Experimental Firmware

The firmware in this directory represents the transmitter and receiver implementation associated with the thesis prototype.

For reproduction of the reported experimental results, use the firmware state identified by the thesis artifact release.

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

The adaptive Vref implementation measures the received signal and adjusts the receiver reference threshold to support the desired operating margin.

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

See `specs/protocol_spec.md` for the protocol definition.

---

## 8. Buffer and File Handling

The firmware uses fixed-size stream buffers.

Current implementation limits include:

* TX stream buffer: 80 KiB
* RX stream buffer: 80 KiB

The desktop application can split larger files into batches when required by the transfer workflow.

---

## 9. Compilation and Upload

The firmware is intended for ESP32 development environments compatible with the source code, including the Arduino development environment used during the project.

Before uploading firmware:

1. Connect the appropriate ESP32 board by USB.
2. Open `rx/rx.ino` for the receiver or `tx/tx.ino` for the transmitter.
3. Select the correct ESP32 board configuration.
4. Select the appropriate serial port.
5. Compile the firmware.
6. Upload the firmware to the ESP32.
7. Verify the serial startup/status response before connecting it to the optical hardware.

---

## 10. Supporting Documentation

### Protocol Specification

`specs/protocol_spec.md`

Defines the frame structure, data fields, transmission flow, and BER comparison procedure.

### Firmware Codemap

`codemap.md`

Provides a high-level description of the firmware organization and its integration with the desktop application and protocol documentation.

---

## 11. Relationship to the Thesis

The firmware implementation corresponds to the software side of the prototype described in the thesis.

Appendix O of the thesis provides selected firmware code snippets for explanation and documentation. This directory contains the complete firmware source.

The thesis remains the primary reference for the experimental procedures, measured values, test conditions, performance results, analysis, conclusions, and recommendations.
