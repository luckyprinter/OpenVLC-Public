# TX Backend Package

The transmitter backend package contains the physical ESP32 implementation used by the desktop TX console.

## Physical backend

- `physical.py` communicates with real VLC_TX firmware over USB serial.
- It identifies compatible TX firmware and maintains the serial controller.
- It sends files, applies supported link settings, and converts firmware status into application snapshots.
- It provides `TXPhysicalSnapshot` values to `TXAppState`.

## Data flow

```text
TX GUI
  -> TXAppState
      -> TXPhysicalBackend
          -> TXSerialController / ESP32 transmitter firmware
      <- TXPhysicalSnapshot
  <- refreshed state
```

There is no simulation backend. GUI smoke tests and mocked serial tests validate software behavior only; they do not establish physical LED or optical-channel performance.
