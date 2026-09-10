# tx/backends/ — TX Backend Implementations

## Responsibility
Provides the two pluggable backends for TX data acquisition. The `physical` backend reads from real VLC_TX firmware via serial (pyserial) and vlc_beta bridge files; the `simulation` backend generates data from a configurable virtual channel model. Both produce immutable snapshot dataclasses consumed by the TX application state.

## Design
- **Snapshot pattern**: Each backend produces a flat dataclass snapshot (`TXPhysicalSnapshot`, `TXSimulationSnapshot`) with fields for filename, encoding, modulation, progress, timing, log, and channel params.
- **Physical backend** (`TXPhysicalBackend`):
  - Port scanning via `serial.tools.list_ports`
  - Firmware detection via `IDENTIFY` command at 115200 baud (expects `VLC_TX`)
  - Reads `tx_status.json` and `latest_tx_record.json` from `vlc_beta/state/` and `vlc_beta/logs/tx/`
  - Parses TX record with payload/settings/batch structure
  - File type guessing via extension mapping
- **Simulation backend** (`TXSimulationBackend`):
  - `VirtualChannelParams` with distance, noise, lux, LED wattage, packet loss, symbol rate, encoding, chunk size, file size
  - Virtual channel model: signal ∝ LED_wattage / distance²
  - Simulated progress ramps up over ticks (`+0.5–3.0%` per refresh)
  - Data rate derived from symbol rate, packet loss, and SNR
  - Estimated remaining time calculation

## Flow
```
TXAppState._refresh()
  → if mode=="physical": TXPhysicalBackend.refresh()
      → scan_ports() → detect_firmware()
      → _read_tx_status() / _read_latest_tx_record()
      → TXPhysicalSnapshot
  → if mode=="simulated": TXSimulationBackend.refresh()
      → _compute_channel() → _build_log()
      → TXSimulationSnapshot
  → TXAppState._apply_phy_snapshot() / _apply_sim_snapshot()
```

## Integration
- **Depends on**: `tx_mock_data.py` (TX data types), `models.py` (indirect via state).
- **Depended by**: `tx_app_state.py` creates backend instances and calls `.refresh()`.
- **External**: pyserial (physical only, optional).
