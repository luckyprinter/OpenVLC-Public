# RX Backend Package

The receiver backend package contains the physical ESP32 implementation used by the desktop RX console.

## Physical backend

- `physical.py` communicates with real VLC_RX firmware over USB serial.
- It scans available serial ports, identifies compatible firmware, and maintains the receiver connection.
- It reads receiver status, signal measurements, transfer notices, and reconstructed file data.
- It provides immutable `RXPhysicalSnapshot` values to `RXAppState`.

## Data flow

```text
RX GUI
  -> RXAppState
      -> RXPhysicalBackend
          -> serial session / ESP32 receiver firmware
      <- RXPhysicalSnapshot
  <- refreshed state
```

There is no simulation backend. GUI smoke tests and mocked serial tests validate software behavior only; physical optical operation still requires the ESP32 hardware and VLC optical path.
