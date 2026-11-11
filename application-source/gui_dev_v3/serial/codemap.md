# serial/ — Serial Communication Module

## Responsibility
The serial package handles USB serial communication between the Python desktop applications and the ESP32 boards. It discovers ports, identifies TX/RX firmware, manages persistent serial sessions, sends firmware commands, reads responses, and supports the file-transfer protocol.

## Files

- **`detection.py`** — lists serial ports, probes them with a blank-line ping, identifies TX versus RX firmware, and selects the correct baud rate (TX 115200, RX 460800).
- **`session.py`** — shared serial-session foundation. Opens/closes a port, configures safe DTR/RTS states, requests exclusive access where supported, starts a background reader, stores received lines, sends newline-terminated commands, waits for firmware responses, and provides CRC-16/CCITT.
- **`controllers.py`** — higher-level command and transfer logic. `TXSerialController` applies TX settings and performs the file preload/start/acknowledgement flow. `RXSerialController` contains receiver command and response helpers used by serial-based integrations.
- **`codemap.md`** — this package map.

## Connection flow

The physical backends first scan and identify a candidate port. The firmware answers a blank line with `TX Ready` or `RX Ready`. The backend then opens a persistent serial handle and performs a second ready ping on that handle.

- TX uses `TXSerialController`, which inherits from `SerialSession`. Its reader thread receives `TX Ready`, and the backend waits for that response before applying settings.
- RX currently manages its persistent serial reader in `rx/backends/physical.py`. It waits for `RX Ready` before applying settings.

This second ping confirms that the persistent serial connection reaches the firmware command loop. It is not an optical synchronization handshake and does not alter the optical preamble, symbol rate, or frame timing.

## TX file-transfer sequence

```text
STREAM_CLEAR
    ↓ acknowledgement
STREAM_BEGIN:<metadata>
    ↓ TX_STREAM_BEGIN_OK
STREAM_DATA:<offset>:<hex-data>  (one or more blocks)
    ↓ TX_STREAM_DATA_OK per block
STREAM_START
    ↓ optical transfer runs on TX ESP32
TX_STREAM_DONE
```

The Python application preloads bytes over USB serial. The TX ESP32 performs time-sensitive 4B5B NRZ/OOK optical signaling. The receiver ESP32 independently detects and decodes the optical signal.

## Threading

The serial reader runs in a background thread so incoming firmware messages can be collected without blocking the Qt GUI. TX file sending also runs in a background thread. Disconnect/reconnect logic stops and joins the previous reader before reusing a connection.

## Important distinction

The TX and RX desktop applications are separate processes. Their ready pings confirm each board to its own application. There is no direct TX-app-to-RX-app readiness channel in this architecture, so the operator must still ensure the RX is ready before starting an optical test.

## Testing boundary

Mock serial tests verify host-side command handling, response parsing, connection lifecycle, and safe port configuration. They do not emulate the USB-UART chip, physical DTR/RTS wiring, ESP32 timing, or the optical channel. Real hardware testing remains necessary.
