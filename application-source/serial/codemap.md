# serial/ — Serial Communication Module

## Responsibility
Low-level serial communication with ESP32 VLC firmware. Provides session management (connect/disconnect/read/write with background reader thread), port detection and firmware role inference, and higher-level TX/RX serial controllers that implement the VLC Beta protocol commands (STREAM_BEGIN, STREAM_DATA, LQ?, VREF_SET, etc.). Code was ported from `vlc_migration`.

## Design
- **`SerialSession`** (base class in `session.py`):
  - Thread-based reader loop (`_reader_loop`) that reads lines from serial in a daemon thread
  - `send_line()` with UTF-8 encoding + `\n` termination
  - `wait_for_line_containing()` with timeout and start_index for response matching
  - `write_status()` persists state JSON to filesystem
  - `crc16_ccitt()` utility for file integrity checks
  - Callback-based: `on_log(line)` and `on_status(payload)` for integration
- **`TXSerialController`** (in `controllers.py`):
  - Extends `SerialSession` with TX-specific commands: `apply_4b5b_settings()`, `bulb_on/off/idle()`, `send_file()` (streaming with chunked STREAM_DATA protocol, ACK waiting, CRC validation)
  - `send_file()` handles the full optical TX lifecycle: STREAM_CLEAR → STREAM_BEGIN → STREAM_DATA blocks → STREAM_START → wait for TX_STREAM_DONE
- **`RXSerialController`** (in `controllers.py`):
  - Extends `SerialSession` with RX-specific commands: `request_config()` (LQ? + VREF_GET), `lock_vref()`, `set_vref_mv()`, `start_receive()`, `stop_receive()`, `dump_chunk()`
- **Detection** (`detection.py`):
  - `list_serial_ports()` returns `list[SerialPortInfo]` via pyserial
  - `probe_serial_port(device)` sends `\n` and reads up to 5 lines to infer firmware role ("rx"/"tx"/"unknown"/"error")

## Flow
```
Controller.connect(device)
  → pyserial.Serial() at 115200 baud
  → start reader thread (daemon)
  → write_status("connected")
Controller.send_line("STREAM_BEGIN:...")
  → serial write + \n
  → background thread reads response
  → wait_for_line_containing() polls last_lines list
Controller.disconnect()
  → stop reader thread, close serial
  → write_status("idle")
```

## Integration
- **Depends on**: `serial/__init__.py` re-exports all public API.
- **Depended by**: Physical backends (`rx/backends/physical.py`, `tx/backends/physical.py`) perform firmware detection and serial I/O; `app.py` and shell pages may use controllers for direct hardware interaction.
- **External**: pyserial (required for actual hardware, graceful fallback when absent).
