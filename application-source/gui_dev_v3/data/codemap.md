# data/ — Data Layer

## Responsibility
Reads live runtime data from the filesystem bridge between the VLC Beta application and the new GUI. Provides session builders, transfer record parsers, and status file readers/writers. All data originates from JSON files written by the `vlc_beta` process (state files, log files, transfer records).

## Design
- **Status readers** (`status.py`): `read_status(role)` loads `{role}_status.json` from `vlc_beta/state/` (fallback to project `state/`). `write_status()` writes status files compatible with the vlc_beta protocol. All functions return `dict[str, Any] | None`.
- **Session builders** (`session.py`): `build_session_from_status(role, transfer)` constructs a `SessionState` from rx_status + signal_status JSON files. `build_empty_session()` returns a clean zeroed-out session for offline state.
- **Record parsers** (`records.py`): `load_real_transfer_history()` loads transfer records from three sources (latest_rx_record.json, transfer_records/ directory, and beta log files), deduplicating by TID. `_parse_transfer_record()` handles the `vlc-rx-transfer-record-v1` JSON schema. `parse_lq_detail()` extracts key=value pairs from LQ detail strings.
- **Re-exports**: `__init__.py` re-exports all public functions for clean imports.

## Flow
```
Physical backends call:
  read_status("rx") / read_status("signal")  → dict or None
  load_real_transfer_history()                → list[TransferRecord]
  build_session_from_status("rx", transfer)   → SessionState
  build_empty_session()                        → SessionState (offline)
  parse_lq_detail("PVo=2.846, Vref=2.481")    → {"PVo": 2.846, "Vref": 2.481}
```

## Integration
- **Depends on**: `models.py` (all domain types).
- **Depended by**: `rx/backends/physical.py`, `rx/backends/simulation.py` (indirect via models), `app_state.py` (via backends).
- **External**: Filesystem (`vlc_beta/state/`, `vlc_beta/logs/rx/`, `~/.vlc_rx/`, `~/.vlc_rx_app/`).
