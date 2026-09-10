# rx/backends/ — RX Backend Implementations

## Responsibility
Provides the two pluggable backends for RX data acquisition. The `physical` backend communicates with real ESP32 VLC_RX firmware via serial (pyserial); the `simulation` backend generates all data from a virtual VLC channel model with tunable parameters. Both produce immutable snapshot dataclasses consumed by the application state.

## Design
- **Snapshot pattern**: Each backend produces a frozen dataclass snapshot (`RXPhysicalSnapshot`, `RXSimulationSnapshot`) containing `SessionState`, `TransferRecord`, `activity_log`, and metadata.
- **Physical backend** (`RXPhysicalBackend`):
  - Port scanning via `serial.tools.list_ports` (USB/UART keywords)
  - Firmware detection via `IDENTIFY` command at 460800/115200 baud
  - Persistent serial connection for `LQ?` polling (PVo, Vref, Margin, SWING)
  - Fallback to `vlc_beta/state/` bridge files when serial unavailable
  - Response parsing with regex-based key normalization
- **Simulation backend** (`RXSimulationBackend`):
  - Virtual channel model: signal voltage ∝ √(LED wattage) / distance^1.5
  - SNR, BER estimate via `math.erfc` (OOK, AWGN model)
  - Chunk generation with configurable packet loss and BER-induced bit errors
  - `VirtualChannelParams` dataclass with distance, noise, lux, LED wattage, packet loss

## Flow
```
RXAppState._refresh()
  → if mode=="physical": RXPhysicalBackend.refresh()
      → scan_ports() → detect_firmware() → open serial → poll LQ?
      → RXPhysicalSnapshot
  → if mode=="simulated": RXSimulationBackend.refresh()
      → compute_channel() → generate_chunks() → build_signal()
      → RXSimulationSnapshot
  → RXAppState._apply_phy_snapshot() / _apply_sim_snapshot()
```

## Integration
- **Depends on**: `models.py` (all domain types), `logic/ber_bridge.py` (quality computation, sim only), `data/records.py`, `data/session.py`, `data/status.py` (physical fallback).
- **Depended by**: `app_state.py` creates backend instances in `__post_init__` and calls `.refresh()`.
- **External**: pyserial (physical only — optional import with graceful fallback).
