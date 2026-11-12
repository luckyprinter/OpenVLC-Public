"""RX Physical Backend — live serial communication with ESP32 VLC_RX.

Communicates with actual VLC_RX firmware at 460800 baud (RX) or 115200 baud (TX).
- Sends IDENTIFY to detect and read firmware version
- Opens persistent serial connection after detection
- Background thread reads ALL serial lines continuously (in a dedicated reader thread)
- Dispatches RX_FILE_HEX, RX_TRANSFER_NOTICE, RX_RAM_STORE, LQ, VREF_* to handlers
- _poll_lq() drains the line queue instead of calling reset_input_buffer() which
  would destroy async firmware messages before they are processed
- No mock data, no simulated values
"""

from __future__ import annotations

import binascii
import json
import queue
from collections import deque
from pathlib import Path
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from gui_dev_v3.data.session import build_empty_session
from gui_dev_v3.models import SessionState, SignalState, TransferRecord, TransferStatus
from gui_dev_v3.serial.line_buffer import SerialLineBuffer
from gui_dev_v3.logic.batch_assembler import BatchAssembler
from gui_dev_v3.serial.session import MAX_STREAM_FILE_BYTES

# RX firmware runs at 460800, TX at 115200 — try both for IDENTIFY
BAUD_RATES = (460800, 115200)
RX_BAUD = 460800
LQ_POLL_CMD = b"LQ?\n"


def _diagnostic_size_bucket(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "empty"
    if size_bytes < 1024:
        return "under_1kib"
    if size_bytes < 16 * 1024:
        return "1_to_16kib"
    if size_bytes <= 80 * 1024:
        return "16_to_80kib"
    return "over_80kib"


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


@dataclass
class RXPhysicalSnapshot:
    """Immutable data packet from the physical backend."""
    session: SessionState
    transfer: TransferRecord
    activity_log: list[dict[str, str]]
    serial_connected: bool
    device_port: str
    firmware_version: str = ""
    board_type: str = ""
    ports_scanned: int = 0
    firmware_found: bool = False


class RXPhysicalBackend:
    """Physical mode backend — live serial with ESP32 VLC_RX firmware.

    - Scans USB serial ports
    - Sends IDENTIFY at 460800 / 115200 baud to detect VLC_RX
    - Opens persistent serial connection for live LQ polling
    - Reads firmware version from IDENTIFY response
    - Reads pins 34 (PVo ADC) and 35 (Vref ADC) and 5 (data in)
    """

    def __init__(self) -> None:
        self._port: str | None = None
        self._connected: bool = False
        self._firmware_info: dict[str, str] | None = None
        self._ser: Any = None  # pyserial Serial object
        self._baud_rate: int = RX_BAUD
        self._log_queue: list[dict[str, str]] = []
        self._last_logged: dict[str, str] = {}
        # Background auto-connect state — prevents GUI thread from blocking
        self._connect_thread: Any = None
        self._connecting: bool = False
        # Background serial reader thread — reads ALL lines from ESP32 continuously
        self._line_queue: queue.Queue[str] = queue.Queue(maxsize=2048)
        self._last_lq_line: str | None = None  # most recent LQ line seen by reader
        # Keep command acknowledgements separate from the UI's line queue so a
        # concurrent refresh cannot consume a response before settings apply sees it.
        self._command_response_condition = threading.Condition()
        self._command_response_lines: deque[str] = deque(maxlen=128)
        self._reader_thread: threading.Thread | None = None
        self._reader_stop: threading.Event = threading.Event()
        # Prevent concurrent GUI/calibration writes from interleaving and
        # prevent cleanup from closing the port during a write.
        self._write_lock = threading.Lock()
        # Set only after the persistent RX command loop answers the ready ping.
        self._ready_event: threading.Event = threading.Event()
        # Active transfer tracking
        self._active_tid: int | None = None
        self._active_total_chunks: int = 0
        self._active_received_chunks: int = 0
        self._active_filename: str = ""
        # Preserve batch identity from RX_TRANSFER_NOTICE for CRC-failure handling.
        # The display filename is decorated below and no longer carries the VLCB1~ prefix.
        self._active_is_batch: bool = False
        self._active_total_size: int = 0
        self._save_dir: Path = Path.home() / "vlc_rx_captures"
        # Last completed transfer — persisted so UI tabs can read it after reception
        self._last_completed_transfer: TransferRecord | None = None
        # Vref PWM auto-calibrator state
        # Adjusts PWM duty ±1 count until measured Vref ≈ user target, then locks.
        # Separate from the margin-based auto-tune — this is purely "make Vref hit the target".
        self._pwm_autocal_target_mv: int = 0   # the target the calibrator is chasing
        self._pwm_autocal_converged: bool = False  # True once within tolerance
        self._pwm_autocal_last_step: float = 0.0   # time of last PWM step
        self._pwm_autocal_last_pwm: int = -1        # last known PWM duty from firmware
        self._pwm_autocal_iterations: int = 0
        self._active_started_monotonic: float | None = None
        # Batch reconstruction state for large files
        self._batch_assembler = BatchAssembler()
        self._serial_line_buffer = SerialLineBuffer(max_line_bytes=MAX_STREAM_FILE_BYTES * 2 + 1024)

    def log(self, event: str, details: str) -> None:
        if self._last_logged.get(event) == details:
            return
        self._last_logged[event] = details
        import time
        now = time.strftime("%H:%M:%S")
        self._log_queue.append({"time": now, "event": event, "details": details})
        from gui_dev_v3.logger import file_log
        file_log("RX", event, details)

    def _prune_expired_batches(self) -> None:
        """Release memory held by incomplete batches after their TTL expires."""
        expired = self._batch_assembler.prune_expired()
        for group_id in expired:
            self._log_queue.append({
                "time": time.strftime("%H:%M:%S"),
                "event": "Batch Expired",
                "details": f"Incomplete batch {group_id} expired and was discarded",
            })

    # ── Port detection ──

    def _record_diag(self, event: str, **fields: Any) -> None:
        # Diagnostics must never interfere with hardware control or transfers.
        try:
            from gui_dev_v3.diagnostics import record_local_event
            record_local_event("rx", event, **fields)
        except Exception:
            pass

    def scan_ports(self) -> list[str]:
        started = time.monotonic()
        ports = _list_usb_serial_ports()
        self._record_diag("serial_scan", role="rx", ports_seen=len(ports),
                          duration_ms=int((time.monotonic() - started) * 1000))
        return ports

    def detect_firmware(self, port: str) -> dict[str, str] | None:
        """Try IDENTIFY at all known baud rates."""
        for baud in BAUD_RATES:
            started = time.monotonic()
            info = _send_identify(port, "VLC_RX", baud)
            self._record_diag(
                "serial_probe", role="rx",
                result="success" if info else "timeout",
                baud_rate=baud,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            if info:
                self._firmware_info = info
                return info
        return None

    # ── Connection lifecycle ──

    def auto_connect(self) -> bool:
        """Auto-detect: scan → IDENTIFY → open persistent serial."""
        from gui_dev_v3.serial.detection import serial_scan_lock
        try:
            with serial_scan_lock():
                return self._auto_connect_locked()
        except TimeoutError:
            self.log("Scan Busy", "Another VLC console is still scanning serial devices")
            return False

    def _auto_connect_locked(self) -> bool:
        """Perform discovery and persistent connection while holding the shared lock."""
        ports = self.scan_ports()
        if ports:
            self.log("Scan", f"Found {len(ports)} ports: {', '.join(ports)}")
        for port in ports:
            self.log("Detect", f"Probing {port}...")
            info = self.detect_firmware(port)
            if info and info.get("device") == "VLC_RX":
                self._port = port
                if not self._open_serial():
                    self._record_diag("serial_probe", role="rx", result="busy",
                                      baud_rate=RX_BAUD, duration_ms=0)
                    self.log("Error [C02]", f"PySerial failed to open {port}; continuing scan")
                    self._port = None
                    continue
                self._connected = True
                self._record_diag("serial_connected", role="rx", baud_rate=RX_BAUD,
                                  firmware_family="rx")
                self.log("Connected", f"Auto-connected to {port} (VLC_RX)")
                if not self.apply_link_settings():
                    self.log(
                        "Connected with Settings Warning",
                        "RX serial connection is active, but one or more saved link settings were not applied. Review the Settings Apply Failed entry.",
                    )
                return True
        if ports:
            self.log("Failed", "No VLC_RX devices found.")
        return False

    def connect(self, port: str, force: bool = False) -> bool:
        from gui_dev_v3.serial.detection import serial_scan_lock
        try:
            with serial_scan_lock():
                return self._connect_locked(port, force=force)
        except TimeoutError:
            self.log("Scan Busy", "Another VLC console is still scanning serial devices")
            return False

    def _connect_locked(self, port: str, force: bool = False) -> bool:
        """Connect to a specific port after firmware detection."""
        if not force:
            self.log("Connect", f"Detecting firmware on {port}...")
            info = self.detect_firmware(port)
            if not info:
                self.log("Error [C01]", f"Firmware detection failed on {port}")
                return False
        else:
            self.log("Force Connect", f"Bypassing handshake for {port}")
            info = {"device": "VLC_RX", "firmware": "rx_forced", "board": "Unknown"}
            self._firmware_info = info

        self._port = port
        if not self._open_serial():
            self._record_diag("serial_probe", role="rx", result="busy",
                              baud_rate=RX_BAUD, duration_ms=0)
            self._port = None
            self._connected = False
            self.log("Error [C02]", f"PySerial failed to open {port}")
            return False

        self._connected = True
        self._record_diag("serial_connected", role="rx", baud_rate=RX_BAUD,
                          firmware_family="rx")
        self.log("Connected", f"Opened {port} successfully")
        if not self.apply_link_settings():
            self.log(
                "Connected with Settings Warning",
                "RX serial connection is active, but one or more saved link settings were not applied. Review the Settings Apply Failed entry.",
            )
        return True

    def disconnect(self) -> None:
        was_connected = self._connected
        self._close_serial()
        if was_connected:
            self._record_diag("serial_disconnected", role="rx", reason_code="user_disconnect")
        self._port = None
        self._connected = False
        self._firmware_info = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def port(self) -> str | None:
        return self._port

    @property
    def firmware_version(self) -> str:
        return self._firmware_info.get("firmware", "") if self._firmware_info else ""

    @property
    def board_type(self) -> str:
        return self._firmware_info.get("board", "") if self._firmware_info else ""

    def _open_serial(self) -> bool:
        """Open persistent serial connection at RX baud rate and start reader thread."""
        self._close_serial()
        if not self._port:
            return False
        try:
            import serial
            # Configure modem-control lines before opening. Some ESP32 USB-UART
            # adapters wire DTR/RTS to reset/boot circuitry; opening with the
            # driver's default line state can unexpectedly reset the board.
            ser = serial.Serial()
            ser.port = self._port
            ser.baudrate = RX_BAUD
            ser.timeout = 0.5
            ser.write_timeout = 0.5
            ser.dtr = False
            ser.rts = False
            ser.exclusive = True
            ser.open()
            self._ser = ser
            # Brief settle — do NOT reset_input_buffer here as the firmware may
            # already be sending data we want to capture
            time.sleep(0.2)
            if not self._ser.is_open:
                self._ser = None
                return False
            # Start the reader before pinging so the readiness response is not lost.
            self._ready_event.clear()
            self._reader_stop.clear()
            self._reader_thread = threading.Thread(
                target=self._serial_reader_loop, daemon=True, name="rx-serial-reader"
            )
            self._reader_thread.start()

            # The firmware answers a blank line only after setup() has completed
            # and loop() is processing serial commands. This replaces reliance
            # on a fixed startup sleep as the readiness signal.
            with self._write_lock:
                ser.write(b"\n")
                ser.flush()
            from gui_dev_v3.settings import SettingsManager
            try:
                ready_timeout = float(SettingsManager("rx").get("connection/timeout", 5))
            except (TypeError, ValueError):
                ready_timeout = 5.0
            ready_timeout = max(1.0, min(ready_timeout, 120.0))
            if not self._ready_event.wait(timeout=ready_timeout):
                self.log("Readiness Timeout", f"RX firmware did not answer ready ping on {self._port} within {ready_timeout:g}s")
                self._close_serial()
                return False
            return True
        except Exception as exc:
            # If opening succeeded but the readiness ping failed, stop the
            # reader and release the port before reporting connection failure.
            self._close_serial()
            self.log("Serial Open Failed", f"{self._port}: {type(exc).__name__}: {exc}")
            return False

    def _serial_reader_loop(self) -> None:
        """Read complete firmware lines, buffering fragments across timeouts."""
        self._serial_line_buffer.clear()
        while not self._reader_stop.is_set():
            ser = self._ser
            if ser is None:
                break
            if not ser.is_open:
                self._mark_serial_lost(ser, ConnectionError("Serial port closed"))
                break
            try:
                waiting = int(getattr(ser, "in_waiting", 0) or 0)
                raw = ser.read(max(1, min(waiting, 65536)))
                if raw:
                    previous_overflows = self._serial_line_buffer.overflow_count
                    for line in self._serial_line_buffer.feed(raw):
                        self._dispatch_line(line)
                    if self._serial_line_buffer.overflow_count > previous_overflows:
                        self._log_queue.append({
                            "time": time.strftime("%H:%M:%S"),
                            "event": "Serial Line Overflow",
                            "details": "Discarded an overlong or malformed serial line",
                        })
                for group_id in self._batch_assembler.prune_expired():
                    self._log_queue.append({
                        "time": time.strftime("%H:%M:%S"),
                        "event": "Batch Expired",
                        "details": f"Incomplete file batch {group_id} expired before all parts arrived",
                    })
            except Exception as exc:
                if self._reader_stop.is_set():
                    break
                self._mark_serial_lost(ser, exc)
                break

    def _mark_serial_lost(self, ser: Any, exc: Exception) -> None:
        """Invalidate and release an unexpectedly failed RX serial connection."""
        if self._reader_stop.is_set():
            return
        self._reader_stop.set()
        with self._write_lock:
            if self._ser is ser:
                self._ser = None
                self._connected = False
                self._port = None
            try:
                ser.close()
            except Exception:
                pass
        self._record_diag("serial_disconnected", role="rx", reason_code="serial_error")
        self.log("Serial Disconnected", f"RX serial reader stopped ({type(exc).__name__}: {exc})")

    def _dispatch_line(self, line: str) -> None:
        """Dispatch a firmware line to the appropriate handler.

        LQ lines are cached for _poll_lq(). File-data lines are handled immediately.
        All lines are also pushed to _line_queue for the refresh() caller.
        """
        with self._command_response_condition:
            self._command_response_lines.append(line)
            self._command_response_condition.notify_all()

        if line.strip() == "RX Ready":
            self._ready_event.set()
            return

        # Strip noise prefix that can appear at the start of lines (e.g. after reset)
        for marker in (
            "RX_FILE_HEX:", "RX_TRANSFER_NOTICE:", "RX_RAM_STORE:",
            "RX_RAM_TIMEOUT:", "RX_FILE_CRC_FAIL:", "RX_FILE_DUMPED:",
            "RX_4B5B_SYNC", "RX_4B5B_SYNC_FAIL", "RX_DUPLICATE",
            "VREF_STATE:", "LQ,", "LQ snapshot:", "CAL_LQ:",
        ):
            idx = line.find(marker)
            if idx > 0:
                line = line[idx:]
                break

        if line.startswith("LQ,") or line.startswith("LQ snapshot:") or line.startswith("CAL_LQ:"):
            self._last_lq_line = line
        elif line.startswith("RX_FILE_HEX:"):
            self._handle_file_hex(line)
        elif line.startswith("RX_TRANSFER_NOTICE:"):
            self._handle_transfer_notice(line)
        elif line.startswith("RX_RAM_STORE:"):
            self._handle_ram_store(line)
        elif line.startswith("RX_RAM_TIMEOUT:"):
            now = time.strftime("%H:%M:%S")
            self._log_queue.append({"time": now, "event": "RX Timeout", "details": line})
        elif line.startswith("RX_4B5B_SYNC"):
            now = time.strftime("%H:%M:%S")
            status = "inverted" if "inverted" in line else "normal"
            self._log_queue.append({"time": now, "event": "SYNC", "details": f"4B5B sync locked ({status})"})
        elif line.startswith("RX_4B5B_SYNC_FAIL"):
            now = time.strftime("%H:%M:%S")
            self._log_queue.append({"time": now, "event": "SYNC FAIL", "details": "4B5B sync failed — preamble not detected"})
        elif line.startswith("RX_FILE_CRC_FAIL:"):
            self._handle_file_crc_fail(line)
        elif line.startswith("VREF_STATE:"):
            now = time.strftime("%H:%M:%S")
            self._log_queue.append({"time": now, "event": "Vref", "details": line[11:60]})
        elif line:
            try:
                self._line_queue.put_nowait(line)
            except queue.Full:
                pass

    def _handle_transfer_notice(self, line: str) -> None:
        """Parse RX_TRANSFER_NOTICE and update active transfer state."""
        # Format: RX_TRANSFER_NOTICE:<tid>:<total_size>:<total_chunks>:<crc_hex>:<name_hex>
        now = time.strftime("%H:%M:%S")
        try:
            parts = line.split(":")
            if len(parts) >= 5:
                tid = int(parts[1])
                total_size = int(parts[2])
                total_chunks = int(parts[3])
                name_hex = parts[5] if len(parts) > 5 else ""
                filename = bytes.fromhex(name_hex).decode("utf-8", errors="replace") if name_hex else "unknown"
                
                is_batch = False
                batch_info = ""
                if filename.startswith("VLCB1~"):
                    b_parts = filename.split("~", 5)
                    if len(b_parts) == 6:
                        part_index = int(b_parts[2])
                        part_count = int(b_parts[3])
                        orig_name = b_parts[5]
                        filename = f"{orig_name} (Part {part_index}/{part_count})"
                        is_batch = True
                        batch_info = f" [Batch Part {part_index}/{part_count}]"

                self._active_tid = tid
                self._active_is_batch = is_batch
                self._active_started_monotonic = time.monotonic()
                self._active_total_chunks = total_chunks
                self._active_received_chunks = 0
                self._active_filename = filename
                self._active_total_size = total_size
                self._log_queue.append({
                    "time": now,
                    "event": "Transfer Start",
                    "details": f"TID={tid} file='{filename}' size={total_size}B chunks={total_chunks}{batch_info}"
                })
        except Exception as e:
            self._log_queue.append({"time": now, "event": "Transfer Notice", "details": line[:80]})

    def _handle_ram_store(self, line: str) -> None:
        """Parse RX_RAM_STORE and update progress."""
        # Format: RX_RAM_STORE:<tid>:<chunk_index>:<received_count>:<total_chunks>
        now = time.strftime("%H:%M:%S")
        try:
            parts = line.split(":")
            if len(parts) >= 5:
                received = int(parts[3])
                total = int(parts[4])
                self._active_received_chunks = received
                pct = int(received * 100 / total) if total > 0 else 0
                self._log_queue.append({
                    "time": now,
                    "event": "Chunk Received",
                    "details": f"chunk {parts[2]}/{total} ({pct}%)"
                })
        except Exception:
            self._log_queue.append({"time": now, "event": "RAM Store", "details": line[:80]})

    def _handle_file_hex(self, line: str) -> None:
        """Handle a complete RX_FILE_HEX line and reconstruct optional batches."""
        try:
            parts = line.split(":")
            if len(parts) < 8:
                return
            tid = int(parts[1])
            frame_type = int(parts[2])
            part_size = int(parts[3])
            part_total_chunks = int(parts[4])
            part_crc_expected = int(parts[5], 16)
            name_hex = parts[6]
            data_hex = parts[7]

            name_bytes = bytes.fromhex(name_hex) if name_hex else b""
            filename = name_bytes.decode("utf-8", errors="replace") if name_bytes else "unknown.bin"
            file_bytes = bytes.fromhex(data_hex) if data_hex else b""

            if len(file_bytes) != part_size:
                self._log_queue.append({
                    "time": time.strftime("%H:%M:%S"),
                    "event": "RX File Truncated",
                    "details": f"Part {tid}: expected {part_size} B, received {len(file_bytes)} B",
                })
                self._active_tid = None
                self._active_is_batch = False
                self._active_started_monotonic = None
                return

            part_crc_ok = crc16_ccitt(file_bytes) == part_crc_expected
            if not part_crc_ok:
                self._log_queue.append({
                    "time": time.strftime("%H:%M:%S"),
                    "event": "RX Part CRC Fail",
                    "details": f"Part {tid} failed its CRC and was not added to the batch",
                })
                self._active_tid = None
                self._active_is_batch = False
                self._active_started_monotonic = None
                return

            full_crc_expected = part_crc_expected
            if filename.startswith("VLCB1~"):
                metadata = filename.split("~", 5)
                if len(metadata) != 6:
                    raise ValueError("Malformed VLCB1 batch metadata")
                assembled = self._batch_assembler.add_part(
                    group_id=metadata[1],
                    part_index=int(metadata[2]),
                    part_count=int(metadata[3]),
                    full_crc=int(metadata[4], 16),
                    filename=metadata[5],
                    part_data=file_bytes,
                    part_crc_ok=True,
                    part_chunks=part_total_chunks,
                    tid=tid,
                    started_monotonic=self._active_started_monotonic,
                )
                if assembled is None:
                    self._active_tid = None
                    self._active_filename = None
                    self._active_is_batch = False
                    self._active_started_monotonic = None
                    return
                file_bytes = assembled["data"]
                filename = assembled["filename"]
                full_crc_expected = assembled["full_crc"]
                tid = assembled["last_tid"]
                self._active_started_monotonic = assembled["started_monotonic"]
                self._active_total_chunks = assembled["total_chunks"]
                self._active_received_chunks = assembled["total_chunks"]
                self._active_total_size = len(file_bytes)
            else:
                self._active_total_chunks = part_total_chunks
                self._active_received_chunks = part_total_chunks
                self._active_total_size = len(file_bytes)

            crc_ok = crc16_ccitt(file_bytes) == full_crc_expected
            safe_name = Path(filename).name or f"rx_{tid}.bin"
            out_path = RECEIVE_FOLDER / safe_name
            if out_path.exists():
                out_path = RECEIVE_FOLDER / f"{out_path.stem}_{tid}{out_path.suffix}"
            out_path.write_bytes(file_bytes)

            n_chunks = max(int(self._active_total_chunks or part_total_chunks), 1)
            chunks = []
            for index in range(n_chunks):
                start = (index * len(file_bytes)) // n_chunks
                end = ((index + 1) * len(file_bytes)) // n_chunks
                if end <= start:
                    continue
                chunks.append(ChunkRecord(
                    index=index,
                    expected=b"",
                    received=file_bytes[start:end],
                    status="RECEIVED",
                    crc_ok=crc_ok,
                ))

            from gui_dev_v3.models import TransferQuality, TransferStatus, TransferRecord
            import time as _time
            quality = TransferQuality(
                label="CRC OK — Method 2 reference comparison pending" if crc_ok else "CRC Failed — Method 2 reference comparison pending",
                strict_ber=None,
                bit_accuracy=None,
                bit_errors=None,
                total_bits=0,
                compared_bytes=0,
                missing_chunks=0,
                missing_bytes=0,
                first_issue=None if crc_ok else "CRC mismatch",
                crc_status="PASS" if crc_ok else "FAIL",
                recovery_rate=100.0 if crc_ok else 0.0,
            )
            duration_ms = (
                int((time.monotonic() - self._active_started_monotonic) * 1000)
                if self._active_started_monotonic is not None else 0
            )
            self._record_diag(
                "transfer_completed" if crc_ok else "transfer_failed",
                role="rx",
                reason_code="success" if crc_ok else "crc_mismatch",
                size_bucket=_diagnostic_size_bucket(len(file_bytes)),
                duration_ms=duration_ms,
                retry_count=0,
            )
            self._last_completed_transfer = TransferRecord(
                tid=tid,
                filename=safe_name,
                status=TransferStatus.COMPLETE if crc_ok else TransferStatus.CRC_FAILED,
                time_label=_time.strftime("%H:%M:%S"),
                size_bytes=len(file_bytes),
                total_chunks=n_chunks,
                received_chunks=len(chunks),
                chunks=chunks,
                quality=quality,
                received_path=str(out_path),
            )
            self._active_tid = None
            self._active_filename = None
            self._active_is_batch = False
            self._active_started_monotonic = None
            self._active_total_chunks = 0
            self._active_received_chunks = 0
            self._active_total_size = 0
            self._log_queue.append({
                "time": time.strftime("%H:%M:%S"),
                "event": "File Received",
                "details": f"{safe_name} ({len(file_bytes):,} B) — {'CRC PASS' if crc_ok else 'CRC FAIL'}",
            })
        except Exception as exc:
            self._log_queue.append({
                "time": time.strftime("%H:%M:%S"),
                "event": "RX File Error",
                "details": str(exc)[:160],
            })
            self._active_tid = None
            self._active_filename = None
            self._active_is_batch = False
            self._active_started_monotonic = None
            self._active_total_chunks = 0
            self._active_received_chunks = 0
            self._active_total_size = 0

    def _handle_file_crc_fail(self, line: str) -> None:
        """Handle RX_FILE_CRC_FAIL from firmware (firmware detected CRC mismatch)."""
        # Format: RX_FILE_CRC_FAIL:<tid>:got=<calc>:expected=<expected>
        now = time.strftime("%H:%M:%S")
        self._log_queue.append({"time": now, "event": "Firmware CRC Fail", "details": line.strip()})
        from gui_dev_v3.logger import file_log
        file_log("RX", "Firmware CRC Fail", line.strip())
        
        try:
            parts = line.split(":")
            if len(parts) >= 2:
                tid = int(parts[1])
                
                # Update the active transfer if it matches
                if self._active_tid == tid:
                    if self._active_is_batch:
                        self._active_tid = None
                        self._active_filename = None
                        self._active_is_batch = False
                        self._active_started_monotonic = None
                        self._active_total_chunks = 0
                        self._active_received_chunks = 0
                        self._active_total_size = 0
                        return
                    from gui_dev_v3.models import TransferQuality, TransferStatus, TransferRecord
                    import time as _time
                    quality = TransferQuality(
                        label="Firmware CRC Failed",
                        strict_ber=None,
                        bit_accuracy=None,
                        bit_errors=None,
                        total_bits=0,
                        compared_bytes=0,
                        missing_chunks=0,
                        missing_bytes=0,
                        first_issue="Firmware CRC mismatch",
                        crc_status="FAIL",
                        recovery_rate=0.0,
                    )
                    duration_ms = int((time.monotonic() - self._active_started_monotonic) * 1000) if self._active_started_monotonic is not None else 0
                    self._record_diag(
                        "transfer_failed", role="rx", reason_code="crc_mismatch",
                        size_bucket=_diagnostic_size_bucket(self._active_total_size),
                        duration_ms=duration_ms, retry_count=0,
                    )
                    self._last_completed_transfer = TransferRecord(
                        tid=tid,
                        filename=self._active_filename or f"rx_{tid}.bin",
                        status=TransferStatus.CRC_FAILED,
                        time_label=_time.strftime("%H:%M:%S"),
                        size_bytes=self._active_total_size,
                        total_chunks=self._active_total_chunks,
                        received_chunks=self._active_received_chunks,
                        quality=quality,
                        chunks=[],
                    )
                    self._active_tid = None
                    self._active_is_batch = False
                    self._active_started_monotonic = None
        except Exception as e:
            self._log_queue.append({"time": now, "event": "RX CRC Fail Error", "details": str(e)[:120]})

    def _close_serial(self) -> None:
        # Signal and join the reader thread first
        self._reader_stop.set()
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        self._reader_thread = None
        with self._write_lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None

    def send_command(self, cmd: str) -> bool:
        """Write a complete command without interleaving concurrent writers."""
        with self._write_lock:
            ser = self._ser
            if not self._connected or ser is None:
                return False
            try:
                ser.write(cmd.encode("utf-8"))
                ser.flush()
                return True
            except Exception:
                return False

    def _send_command_and_confirm(
        self, command: str, response_prefix: str, timeout: float = 2.0
    ) -> bool:
        """Send one RX setting and wait for its firmware acknowledgement."""
        with self._command_response_condition:
            self._command_response_lines.clear()

        if not self.send_command(command):
            self.log(
                "Settings Apply Failed",
                f"Could not write RX setting: {command.strip()}",
            )
            return False

        deadline = time.monotonic() + timeout
        error_prefixes = (
            "RX_ERROR:", "VREF_MODE_ERROR:", "VREF_SET_SKIP:",
            "VREF_PWM_SKIP:", "VREF_PWM_FS_ERROR:",
        )
        with self._command_response_condition:
            while True:
                while self._command_response_lines:
                    line = self._command_response_lines.popleft()
                    if line.startswith(response_prefix):
                        return True
                    if line.startswith(error_prefixes):
                        self.log(
                            "Settings Apply Failed",
                            f"RX firmware rejected {command.strip()}: {line}",
                        )
                        return False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.log(
                        "Settings Apply Failed",
                        f"No firmware acknowledgement for {command.strip()} "
                        f"(expected {response_prefix}).",
                    )
                    return False
                self._command_response_condition.wait(timeout=remaining)

    def apply_link_settings(self) -> bool:
        """Apply saved settings and require firmware acknowledgement per setting."""
        if not self._connected or not self._ser:
            return False
        from gui_dev_v3.settings import SettingsManager
        mgr = SettingsManager("rx")

        symbol_hz = int(mgr.get("link/symbol_hz", 15000))
        sample_phase_pct = int(mgr.get("link/sample_phase_pct", 50))
        vref_target_mv = int(mgr.get("link/vref_target_mv", 1700))
        vref_margin_mv = int(mgr.get("link/vref_margin_mv", 365))
        vref_pwm_full_scale_mv = int(mgr.get("link/vref_pwm_full_scale_mv", 2625))
        vref_settle_ms = int(mgr.get("link/vref_settle_ms", 120))
        vref_auto = 1 if mgr.get("link/vref_auto", False) else 0
        majority_sampling = 1 if mgr.get("link/majority_sampling", True) else 0
        commands = [
            (f"FREQ={symbol_hz}\n", "RX 4B5B FREQ ="),
            (f"PHASE={sample_phase_pct}\n", "RX 4B5B PHASE ="),
            (f"MAJ={majority_sampling}\n", "RX 4B5B MAJ ="),
            ("REPORT=1\n", "RX REPORT ="),
            (f"VREF_MARGIN={vref_margin_mv}\n", "VREF_MARGIN_OK:"),
            (f"VREF_PWM_FS={vref_pwm_full_scale_mv}\n", "VREF_PWM_FS_OK:"),
            (f"VREF_SETTLE_MS={vref_settle_ms}\n", "VREF_SETTLE_OK:"),
            (
                "VREF_MODE=AUTO\n" if vref_auto else "VREF_MODE=MANUAL\n",
                "VREF_MODE_OK:",
            ),
        ]
        if not vref_auto:
            # VREF_SET must be last: firmware delays while the RC filter settles.
            commands.append((f"VREF_SET={vref_target_mv}\n", "VREF_SET_OK:"))

        for command, response_prefix in commands:
            timeout = 2.0
            if response_prefix == "VREF_SET_OK:":
                # Firmware blocks while the PWM/RC output settles; honor the
                # configured delay plus margin instead of timing out early.
                timeout = max(2.0, min(vref_settle_ms / 1000.0 + 1.0, 7.0))
            if not self._send_command_and_confirm(command, response_prefix, timeout):
                return False

        if not vref_auto:
            # Reset PWM autocal so it will re-converge after the target changes.
            self._pwm_autocal_target_mv = 0
            self._pwm_autocal_converged = False
        return True

    def cleanup(self) -> None:
        """Close serial connection and release port."""
        self._close_serial()

    # ── Live data acquisition ──

    def _poll_lq(self) -> dict[str, float] | None:
        """Return the most recent LQ data from the background reader thread.

        The reader thread captures LQ lines continuously without needing to
        send LQ? commands or call reset_input_buffer() (which would destroy
        async firmware messages like RX_FILE_HEX and RX_4B5B_SYNC).

        Returns dict with keys: SIGNAL, VREF, MARGIN, SWING, PASS_RATE (floats).
        """
        # If we have a cached LQ line from the reader thread, use it
        lq_line = self._last_lq_line
        if lq_line:
            self._last_lq_line = None  # consume it
            return _parse_lq_response(lq_line)

        # Fallback: send LQ? and wait briefly for a response
        # (used when the reader hasn't cached one yet, e.g. right after connect)
        if self._ser is None:
            return None
        try:
            if not self.send_command(LQ_POLL_CMD.decode("ascii")):
                return None
            # Wait briefly for reader thread to catch the response
            deadline = time.time() + 0.6
            while time.time() < deadline:
                time.sleep(0.05)
                if self._last_lq_line:
                    lq_line = self._last_lq_line
                    self._last_lq_line = None
                    return _parse_lq_response(lq_line)
        except Exception:
            pass
        return None

    def refresh(self) -> RXPhysicalSnapshot:
        """Read current state from the live ESP32 serial connection."""
        self._prune_expired_batches()
        if not self._connected:
            from gui_dev_v3.settings import SettingsManager
            mgr = SettingsManager("rx")
            mode = mgr.get("connection/mode", "Auto Detect (Recommended)")
            auto_conn = mgr.get("connection/auto_connect", True)
            
            if auto_conn and not self._connecting:
                # Throttle scans to avoid spamming serial ports every poll tick
                now = time.time()
                if not hasattr(self, "_last_scan_time"):
                    self._last_scan_time = 0
                scan_interval = mgr.get("connection/scan_interval", 3)
                
                if (now - self._last_scan_time) > scan_interval:
                    self._last_scan_time = now
                    # Run detection in a background thread so the GUI never freezes
                    import threading
                    target_port = mgr.get("connection/port", "") if mode == "Manual" else None
                    self._connecting = True

                    def _bg_connect():
                        try:
                            if target_port:
                                self.connect(target_port)
                            else:
                                self.auto_connect()
                        finally:
                            self._connecting = False

                    self._connect_thread = threading.Thread(target=_bg_connect, daemon=True)
                    self._connect_thread.start()

        if not self._connected:
            log = list(self._log_queue)
            self._log_queue.clear()
            return self._empty_snapshot(log)

        # Try live serial first
        if self._ser is not None:
            import serial
            try:
                _ensure_serial(self._ser)
            except serial.SerialException:
                # Hot plug / disconnect detected
                self.disconnect()
                log_out = list(self._log_queue)
                self._log_queue.clear()
                return self._empty_snapshot(log_out)
            except Exception as e:
                self.log("Error [S01]", f"Serial read failure: {e}")
                self._close_serial()

        if self._ser is not None:
            lq_data = self._poll_lq()
            if lq_data:
                from gui_dev_v3.settings import SettingsManager
                mgr = SettingsManager("rx")
                vref_auto = mgr.get("link/vref_auto", False)
                if vref_auto and "REASON" not in lq_data:
                    status = str(lq_data.get("STATUS", ""))
                    margin = float(lq_data.get("MARGIN", 0.0))
                    pvo = float(lq_data.get("SIGNAL", 0.0))
                    target_margin = mgr.get("link/vref_margin_mv", 365) / 1000.0
                    error = margin - target_margin
                    
                    # If the error is large enough to warrant an adjustment.
                    # Note: Because the hardware S-curve can jump by ~270mV per single PWM step at its steepest point,
                    # we MUST use a deadband larger than half the step size (e.g. 160mV) to prevent it from perpetually 
                    # toggling between two adjacent PWM steps when the perfect voltage is physically impossible.
                    if pvo > 0.01 and abs(error) > 0.160:
                        now = time.time()
                        # Adjust at most once every 1.5 seconds for a smooth gradual track
                        if not hasattr(self, "_last_auto_cal") or (now - self._last_auto_cal) > 1.5:
                            self._last_auto_cal = now
                            
                            # Grab current internal target from firmware (or fallback to measured VREF)
                            current_target_mv_str = lq_data.get("VREF_TARGET_MV")
                            if current_target_mv_str is not None:
                                current_target_v = float(current_target_mv_str) / 1000.0
                            else:
                                current_target_v = float(lq_data.get("VREF", 1.5))
                            
                            # Fixed-step tracking with toggle-lock
                            # The hardware S-curve can jump by up to ~450mV per single PWM step!
                            # To prevent perpetual toggling, we detect direction changes and lock for 10 seconds.
                            pwm_step_mv = 0.013
                            error_sign = 1 if error > 0 else -1
                            last_sign = getattr(self, "_last_error_sign", 0)
                            
                            if last_sign != 0 and last_sign != error_sign:
                                self._toggle_lock_time = now
                                
                            self._last_error_sign = error_sign
                            is_locked = hasattr(self, "_toggle_lock_time") and (now - self._toggle_lock_time) < 10.0
                            
                            if not is_locked:
                                if error > 0:
                                    new_target_v = current_target_v + pwm_step_mv
                                else:
                                    new_target_v = current_target_v - pwm_step_mv
                                    
                                new_target_mv = int(new_target_v * 1000)
                                new_target_mv = max(100, min(3200, new_target_mv))
                                
                                self.send_command(f"VREF_SET={new_target_mv}\n")
                                self.log("Auto-Tune", f"Margin {margin:.3f}V (err {error*1000:+.0f}mV). Nudging target to {new_target_mv}mV")
                            else:
                                pass # Locked to prevent oscillation
                
                # Run Vref PWM auto-calibrator (separate from margin-based auto-tune)
                self._run_vref_pwm_autocal(lq_data)

                # Cache LQ data so we don't zero-out during a transfer (when firmware sends LQ_SKIP)
                if "REASON" in lq_data and hasattr(self, "_last_lq_data"):
                    return self._build_from_lq(self._last_lq_data)
                
                self._last_lq_data = lq_data
                return self._build_from_lq(lq_data)

        # Check if serial connection looks alive
        if self._ser and not self._ser.closed:
            return self._build_stale()

        return self._empty_snapshot()

    def _run_vref_pwm_autocal(self, lq_data: dict) -> None:
        """PWM auto-calibrator: nudge PWM duty ±1 until measured Vref reaches user target.

        Logic:
          - Only runs in MANUAL vref mode and when 'link/vref_pwm_autocal' is enabled.
          - Reads target from settings, compares to measured VREF from LQ data.
          - Steps firmware PWM by ±1 duty count (VREF_PWM=N) every settle_ms.
          - Locks when |error| < tolerance_mv (default 50mV) — no more commands sent
            until user changes the target in settings and re-applies.
          - Halts during active file transfer (transmission lock).
        """
        from gui_dev_v3.settings import SettingsManager
        mgr = SettingsManager("rx")

        # Feature gate
        if not mgr.get("link/vref_pwm_autocal", True):
            return
        # Don't run in AUTO vref mode (firmware handles it)
        if mgr.get("link/vref_auto", False):
            return
        # Transmission lock: halt during active file reception
        if self._active_tid is not None:
            return

        target_mv = int(mgr.get("link/vref_target_mv", 1700))
        measured_v = float(lq_data.get("VREF", 0.0))
        measured_mv = int(measured_v * 1000)

        if measured_mv == 0:
            return  # No valid reading yet

        # If the target changed, reset convergence so we chase the new goal
        if target_mv != self._pwm_autocal_target_mv:
            self._pwm_autocal_target_mv = target_mv
            self._pwm_autocal_converged = False
            self._pwm_autocal_iterations = 0

        if self._pwm_autocal_converged:
            return  # Already at target — nothing to do

        TOLERANCE_MV = 50   # ±50mV dead-band — stops oscillation
        error_mv = target_mv - measured_mv

        if abs(error_mv) <= TOLERANCE_MV:
            # Converged!
            self._pwm_autocal_converged = True
            self._record_diag(
                "calibration_completed", result="success",
                iterations=self._pwm_autocal_iterations,
                target_vref_mv=target_mv, measured_vref_mv=measured_mv,
                pwm_percent=int(float(lq_data.get("VREF_PWM_PERCENT", self._pwm_autocal_last_pwm if self._pwm_autocal_last_pwm >= 0 else 0))),
            )
            self.log(
                "Vref Calibrated",
                f"Target {target_mv}mV reached (measured {measured_mv}mV, error {error_mv:+d}mV) — PWM locked"
            )
            return

        # Rate-limit: wait at least settle_ms between steps
        settle_ms = int(mgr.get("link/vref_settle_ms", 120))
        step_interval = max(settle_ms / 1000.0, 0.12)  # minimum 120ms
        now = time.time()
        if (now - self._pwm_autocal_last_step) < step_interval:
            return

        # Read current PWM percentage from LQ data
        current_pwm_pct = lq_data.get("VREF_PWM_PERCENT", None)

        if current_pwm_pct is not None:
            current_pct = float(current_pwm_pct)
        elif self._pwm_autocal_last_pwm >= 0:
            current_pct = self._pwm_autocal_last_pwm
        else:
            current_pct = 54.0

        # Step ±1 percentage point toward target
        if error_mv > 0:
            new_pct = min(100.0, current_pct + 1.0)  # need higher Vref → more PWM
        else:
            new_pct = max(0.0, current_pct - 1.0)    # need lower Vref → less PWM

        if new_pct == current_pct:
            # Already at hardware limit, can't go further
            self._pwm_autocal_converged = True
            self._record_diag(
                "calibration_completed", result="failure",
                iterations=self._pwm_autocal_iterations,
                target_vref_mv=target_mv, measured_vref_mv=measured_mv,
                pwm_percent=int(current_pct),
            )
            self.log(
                "Vref Cal Limit",
                f"PWM at limit ({current_pct:.1f}%). Measured {measured_mv}mV, target {target_mv}mV"
            )
            return

        self._pwm_autocal_last_pwm = new_pct
        self._pwm_autocal_last_step = now
        self._pwm_autocal_iterations += 1
        self.send_command(f"VREF_PWM={new_pct:.1f}\n")
        self.log(
            "Vref Cal Step",
            f"PWM {current_pwm}→{new_pwm} ({new_pct:.1f}%) | measured {measured_mv}mV, target {target_mv}mV, error {error_mv:+d}mV"
        )

    def _build_from_lq(self, lq: dict[str, float]) -> RXPhysicalSnapshot:
        """Build a snapshot from live LQ poll data (pins 34, 35, 5)."""
        now = time.strftime("%H:%M:%S")
        pvo = lq.get("SIGNAL", 0.0)
        vref = lq.get("VREF", 0.0)
        margin = lq.get("MARGIN", 0.0)
        swing = lq.get("SWING", 0.0)
        pass_rate = lq.get("PASS_RATE", 100.0)
        status_str = lq.get("STATUS", "SUCCESS_RANGE")

        # Quality label from margin
        if margin > 0.3:
            label = "Excellent"
        elif margin > 0.2:
            label = "Good"
        elif margin > 0.1:
            label = "Fair"
        elif margin > 0.05:
            label = "Poor"
        else:
            label = "No Signal"

        signal = SignalState(
            label=label,
            pvo=round(pvo, 3),
            vref=round(vref, 3),
            margin=round(margin, 3),
            target_margin=0.365,
            adc_vref=3.300,
            lux=int(pvo * 150) if pvo > 0 else 0,  # rough lux estimate from PVo
            data_rate=0.0,  # updated by transfer activity
            ber=None,
            strict_ber=None,
            crc_status="Unknown",
            time_elapsed="--",
        )

        # Determine the best transfer record to surface to the UI:
        #  1. If a transfer is actively being received, show live progress
        #  2. If we have a recently completed transfer, keep showing it
        #  3. Otherwise fall back to the empty placeholder
        if self._active_tid is not None:
            from gui_dev_v3.models import TransferQuality, TransferStatus
            in_progress_quality = TransferQuality(
                label="Receiving…", strict_ber=None, bit_accuracy=None, bit_errors=None,
                total_bits=0, compared_bytes=0, missing_chunks=0, missing_bytes=0,
                first_issue="None", crc_status="", recovery_rate=0.0,
            )
            active_tr = TransferRecord(
                tid=self._active_tid,
                filename=self._active_filename or "receiving…",
                status=TransferStatus.INCOMPLETE,
                time_label=now,
                size_bytes=self._active_total_size,
                total_chunks=self._active_total_chunks,
                received_chunks=self._active_received_chunks,
                quality=in_progress_quality,
                chunks=[],
            )
            best_transfer = active_tr
            current_file = self._active_filename or "receiving…"
            pct = int(self._active_received_chunks * 100 / max(self._active_total_chunks, 1))
        elif self._last_completed_transfer is not None:
            best_transfer = self._last_completed_transfer
            current_file = self._last_completed_transfer.filename
            pct = 100
        else:
            best_transfer = _empty_transfer()
            current_file = "No active transfer"
            pct = 0

        session = SessionState(
            role="RX",
            connected_device=f"{self._port or ''} @ {RX_BAUD} baud",
            current_file=current_file,
            progress_percent=pct,
            signal=signal,
            latest_transfer=best_transfer,
        )

        log = [
            {"time": now, "event": "Connected", "details": f"Port {self._port} @ {RX_BAUD} baud"},
            {"time": now, "event": "LQ Poll", "details": f"PVo={pvo:.3f}V Vref={vref:.3f}V Margin={margin:.3f}V"},
        ]
        
        # Log LQ to file once every 5 seconds to prevent spam, but always show in UI
        if not hasattr(self, "_last_lq_log") or time.time() - self._last_lq_log > 5.0:
            self._last_lq_log = time.time()
            from gui_dev_v3.logger import file_log
            file_log("RX", "LQ Poll", f"PVo={pvo:.3f}V Vref={vref:.3f}V Margin={margin:.3f}V")
            
        if self._firmware_info:
            fw = self._firmware_info.get("firmware", "")
            board = self._firmware_info.get("board", "")
            log.append({"time": now, "event": "Firmware", "details": f"v{fw} on {board}"})
        
        if self._log_queue:
            log.extend(self._log_queue)
            self._log_queue.clear()

        return RXPhysicalSnapshot(
            session=session,
            transfer=session.latest_transfer,
            activity_log=log,
            serial_connected=True,
            device_port=self._port or "",
            firmware_version=self._firmware_info.get("firmware", "") if self._firmware_info else "",
            board_type=self._firmware_info.get("board", "") if self._firmware_info else "",
            ports_scanned=len(self.scan_ports()),
            firmware_found=True,
        )

    def _build_stale(self) -> RXPhysicalSnapshot:
        """Serial open but no fresh data yet."""
        now = time.strftime("%H:%M:%S")
        session = build_empty_session()
        log = [
            {"time": now, "event": "Connected", "details": f"Serial open on {self._port}"},
            {"time": now, "event": "Waiting", "details": "Polling LQ... (no response yet)"},
        ]
        if self._log_queue:
            log.extend(self._log_queue)
            self._log_queue.clear()
        return RXPhysicalSnapshot(
            session=session,
            transfer=session.latest_transfer,
            activity_log=log,
            serial_connected=True,
            device_port=self._port or "",
            firmware_version=self._firmware_info.get("firmware", "") if self._firmware_info else "",
            board_type=self._firmware_info.get("board", "") if self._firmware_info else "",
            ports_scanned=0,
            firmware_found=True,
        )

    def _empty_snapshot(self, extra_log: list[dict[str, str]] | None = None) -> RXPhysicalSnapshot:
        now = time.strftime("%H:%M:%S")
        session = build_empty_session()
        log = extra_log or []
        if self._log_queue:
            log.extend(self._log_queue)
            self._log_queue.clear()
        return RXPhysicalSnapshot(
            session=session,
            transfer=session.latest_transfer,
            activity_log=log,
            serial_connected=False,
            device_port="—",
            firmware_version="",
            board_type="",
            ports_scanned=len(self.scan_ports()),
            firmware_found=False,
        )

    def _build_log(self, rx_status: dict | None,
                   sig_status: dict | None) -> list[dict[str, str]]:
        log = []
        now = time.strftime("%H:%M:%S")
        if rx_status:
            stage = str(rx_status.get("stage", ""))
            detail = str(rx_status.get("detail", ""))
            percent = rx_status.get("percent")
            if stage:
                log.append({"time": now, "event": str(stage), "details": str(detail)[:80]})
            if percent is not None and float(percent) > 0:
                log.append({"time": now, "event": "Progress", "details": f"{float(percent):.0f}% complete"})
        if sig_status:
            margin = sig_status.get("margin_v")
            pvo = sig_status.get("pvo_v")
            if margin is not None:
                log.append({"time": now, "event": "Signal", "details": f"Margin: {float(margin):.3f}V"})
            if pvo is not None:
                log.append({"time": now, "event": "Signal", "details": f"PVo: {float(pvo):.3f}V"})
        if not log:
            log.append({"time": now, "event": "Status", "details": "No active transfer data"})
        return log


# ── Helpers ──


def _list_usb_serial_ports() -> list[str]:
    """Return serial ports, prioritising true USB/ACM adapters (ESP32) first.

    Port priority order:
      1. ttyUSB* / ttyACM* — real USB-serial adapters (CP2102, CH340, FTDI)
      2. COM* — Windows virtual COM ports
      3. Everything else with USB VID/PID
    Native kernel ttyS* ports are excluded unless they have a USB VID/PID.
    """
    try:
        import serial.tools.list_ports
        usb_ports: list[str] = []
        other_ports: list[str] = []
        for port in serial.tools.list_ports.comports():
            dev = port.device or ""
            meta = f"{dev} {port.description or ''} {port.hwid or ''}".lower()
            is_usb_adapter = any(
                dev.startswith(p) for p in ("/dev/ttyUSB", "/dev/ttyACM")
            ) or (
                # Windows: COM ports with a real USB VID/PID
                dev.upper().startswith("COM") and port.vid is not None
            )
            has_vid_pid = port.vid is not None and port.pid is not None
            keywords = ("usb", "cp210", "ch340", "ftdi", "arduino", "esp32", "uart")

            if is_usb_adapter:
                usb_ports.append(dev)
            elif has_vid_pid and any(k in meta for k in keywords):
                other_ports.append(dev)
            # Deliberately skip plain ttyS* with no VID/PID — they're kernel ghost ports

        # USB adapters first, then others — both sorted alphabetically within group
        return sorted(set(usb_ports)) + sorted(set(other_ports))
    except ImportError:
        return []
    except (OSError, RuntimeError) as exc:
        import sys
        print(f"Serial port scan failed: {exc}", file=sys.stderr)
        return []


def _send_identify(port: str, expected_device: str, baud: int = 115200) -> dict[str, str] | None:
    """Send empty string ping at a specific baud rate, fallback to JSON response."""
    try:
        import serial
        import time
        import json
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baud
        ser.timeout = 0.5
        ser.dtr = False
        ser.rts = False
        ser.exclusive = True
        ser.open()
        with ser:
            time.sleep(0.2)
            ser.reset_input_buffer()
            # Send the empty string ping to trigger "TX Ready" or "RX Ready"
            ser.write(b"\n")
            ser.flush()
            
            for _ in range(5):
                raw = ser.readline().strip()
                if raw:
                    resp = raw.decode("utf-8", errors="replace").strip()
                    
                    # Check for the new ping response format
                    if ("TX Ready" in resp or "TX Stream Ready" in resp) and expected_device == "VLC_TX":
                        return {
                            "device": "VLC_TX",
                            "firmware": "tx_unknown",
                            "board": "ESP32",
                        }
                    elif ("RX Ready" in resp or "RX Stream Ready" in resp) and expected_device == "VLC_RX":
                        return {
                            "device": "VLC_RX",
                            "firmware": "rx_unknown",
                            "board": "ESP32",
                        }
                        
                    # Fallback to the old IDENTIFY JSON format
                    if resp.startswith("{"):
                        j = json.loads(resp)
                        if isinstance(j, dict) and j.get("device") == expected_device:
                            return {
                                "device": str(j.get("device", "")),
                                "firmware": str(j.get("firmware", "")),
                                "board": str(j.get("board", "")),
                            }
    except Exception:
        pass
    return None


def _parse_lq_response(line: str) -> dict[str, float] | None:
    """Parse LQ telemetry line from RX firmware.

    Handles formats:
      LQ, SIGNAL=2.846, VREF=2.481, MARGIN=0.365, SWING=0.120, STATUS=...
      LQ snapshot: SIGNAL=2.846, VREF=2.481, MARGIN=0.365, ...
      CAL_LQ: SIGNAL=...
    """
    # Strip prefix
    for prefix in ("LQ,", "LQ snapshot:", "CAL_LQ:", "LQ "):
        idx = line.find(prefix)
        if idx >= 0:
            line = line[idx + len(prefix):]
            break

    pairs = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=([^,\s]+)", line)
    if not pairs:
        return None

    # Normalise keys
    key_map = {
        "SIGNAL": "SIGNAL", "PVO": "SIGNAL", "PV0": "SIGNAL", "SIG": "SIGNAL", "SIG_MAX": "SIGNAL",
        "VREF": "VREF", "MEASURED_V": "VREF",
        "MARGIN": "MARGIN", "ACHIEVED_MARGIN": "MARGIN",
        "SWING": "SWING",
        "PASS_RATE": "PASS_RATE", "PASS": "PASS_RATE", "PASSRATE": "PASS_RATE",
        "STATUS": "STATUS",
        # Extended fields used by PWM auto-calibrator and UI display
        "VREF_TARGET_MV": "VREF_TARGET_MV",
        "VREF_PWM": "VREF_PWM",
        "VREF_PWM_PERCENT": "VREF_PWM_PERCENT",
        "VREF_MODE": "VREF_MODE",
        "VREF_PWM_FS_ADC_MV": "VREF_PWM_FS_ADC_MV",
    }
    result: dict[str, Any] = {}
    for key, raw_val in pairs:
        upper_key = key.strip().upper()
        norm: str = upper_key  # explicit str type
        if upper_key in key_map:
            norm = key_map[upper_key]
        try:
            # Extract first float from value
            match = re.search(r"[-+]?\d+(?:\.\d+)?", raw_val)
            if match:
                result[norm] = float(match.group(0))
            else:
                result[norm] = raw_val.strip()
        except (ValueError, TypeError):
            result[norm] = raw_val.strip()
            
    return result if result else None


def _ensure_serial(ser: Any) -> None:
    """Check serial is still open. Raises if not."""
    if ser is None or ser.closed:
        raise ConnectionError("Serial closed")


def _empty_transfer() -> TransferRecord:
    """Build an empty TransferRecord for offline state."""
    from gui_dev_v3.models import TransferQuality, TransferStatus
    return TransferRecord(
        tid=0, filename="No data",
        status=TransferStatus.PENDING,
        time_label="", size_bytes=0,
        total_chunks=0, received_chunks=0,
        quality=TransferQuality(
            label="No Data", strict_ber=None, bit_accuracy=None,
            bit_errors=None, total_bits=0, compared_bytes=0,
            missing_chunks=0, missing_bytes=0,
            first_issue="None", crc_status="", recovery_rate=0.0,
        ),
    )
