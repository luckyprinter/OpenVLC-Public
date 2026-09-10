"""Serial session management — thread-safe, role-aware baud rates, bounded log."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .detection import BAUDRATE, BAUDRATE_RX, BAUDRATE_TX, baud_for_role

# ── Protocol constants (match firmware exactly) ────────────────────────────────
MAX_STREAM_FILE_BYTES = 81920   # 80 KB — matches firmware MAX_STREAM_FILE_BYTES
MAX_NAME_BYTES        = 80      # matches firmware MAX_NAME_BYTES (was wrongly 64)
STREAM_SERIAL_BLOCK   = 512    # bytes per STREAM_DATA chunk sent to firmware

LogCallback    = Callable[[str], None]
StatusCallback = Callable[[dict[str, Any]], None]

# How many serial lines to keep in memory (prevents unbounded growth).
_MAX_LOG_LINES = 2000

_STATUS_DIR = Path(__file__).resolve().parent.parent.parent / "state"


def crc16_ccitt(data: bytes, poly: int = 0x1021) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ poly if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def write_status(role: str, payload: dict[str, Any]) -> None:
    _STATUS_DIR.mkdir(parents=True, exist_ok=True)
    path = _STATUS_DIR / f"{role}_status.json"
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


class SerialSession:
    """Base serial session.

    Changes vs original:
    - last_lines backed by a deque(maxlen=2000) — fixes unbounded memory growth.
    - connect() accepts `role` kwarg and picks the correct baud rate automatically.
    - wait_for_line_containing uses time.sleep() instead of allocating a new
      threading.Event() on every iteration.
    - handle_line() is a no-op hook for subclasses (was logging only).
    """

    def __init__(
        self,
        role: str,
        on_log: LogCallback | None = None,
        on_status: StatusCallback | None = None,
    ) -> None:
        self.role       = role
        self.on_log     = on_log or (lambda line: None)
        self.on_status  = on_status or (lambda payload: None)
        self.serial_obj: Any = None
        self._lock      = threading.Lock()
        self._is_connected = False
        # Bounded deque — old entries dropped automatically at maxlen.
        self._last_lines: deque[str] = deque(maxlen=_MAX_LOG_LINES)
        self._reader_thread: threading.Thread | None = None
        self._running = False

    # ── last_lines public interface ─────────────────────────────────────────

    @property
    def last_lines(self) -> list[str]:
        """Return a snapshot list of the recent log lines (thread-safe)."""
        with self._lock:
            return list(self._last_lines)

    def _append_line(self, line: str) -> None:
        """Append a line to the bounded log (must be called under _lock or atomically)."""
        with self._lock:
            self._last_lines.append(line)
            self._line_counter = getattr(self, "_line_counter", 0) + 1

    # ── Connection state ────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    @is_connected.setter
    def is_connected(self, value: bool) -> None:
        with self._lock:
            self._is_connected = value

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def connect(self, device: str, expected_role: str = "") -> bool:
        """Open a serial connection.

        Baud rate is selected by `self.role` (or `expected_role` if provided):
          - "rx" / "VLC_RX" → 460800 baud
          - anything else   → 115200 baud (TX firmware)
        """
        role_key = (expected_role or self.role).lower()
        baud = BAUDRATE_RX if "rx" in role_key else BAUDRATE_TX
        try:
            import serial  # type: ignore[import-untyped]

            self.disconnect()
            ser = serial.Serial()
            ser.port = device
            ser.baudrate = baud
            ser.timeout = 0.1
            # Prevent Windows from resetting the ESP32 and dropping the handle
            ser.dtr = False
            ser.rts = False
            ser.open()
            self.serial_obj = ser
            self.is_connected = True
            self._running = True
            self._reader_thread = threading.Thread(
                target=self._reader_loop, daemon=True
            )
            self._reader_thread.start()
            self.log(f"Connected to {device} at {baud} baud")
            self.status("Connected", f"Serial link to {device}", state="ready")
            write_status(
                self.role,
                {"role": self.role, "stage": "Connected", "state": "active", "port": device},
            )
            return True
        except Exception as exc:
            self.log(f"Connection failed: {exc}")
            self.status("Connection Failed", str(exc), state="error")
            return False

    def disconnect(self) -> None:
        self._running = False
        if self.serial_obj and self.serial_obj.is_open:
            try:
                self.serial_obj.close()
            except Exception:
                pass
        self.serial_obj = None
        self.is_connected = False
        self.log("Disconnected")
        self.status("Disconnected", "", state="idle")
        write_status(self.role, {"role": self.role, "stage": "Idle", "state": "idle"})

    # ── I/O ─────────────────────────────────────────────────────────────────

    def send_line(self, line: str) -> bool:
        if not self.is_connected or self.serial_obj is None:
            self.log("Not connected")
            return False
        try:
            data = (line + "\n").encode("utf-8")
            self.serial_obj.write(data)
            self.log(f">> {line}")
            return True
        except Exception as exc:
            self.log(f"Send error: {exc}")
            self.disconnect()  # Handle hot unplug during send
            return False

    @property
    def line_counter(self) -> int:
        with self._lock:
            return getattr(self, "_line_counter", 0)

    def wait_for_line_containing(
        self, text: str, timeout: float = 5.0, start_counter: int = 0
    ) -> bool:
        """Poll last_lines until `text` is found or timeout expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_connected:
                return False
            with self._lock:
                current_counter = getattr(self, "_line_counter", 0)
                new_count = current_counter - start_counter
                if new_count > 0:
                    lines = list(self._last_lines)[-new_count:]
                else:
                    lines = []
            
            for line in lines:
                if text in line:
                    return True
            time.sleep(0.05)
        return False

    def _reader_loop(self) -> None:
        try:
            import serial
        except ImportError:
            return
        while self._running and self.serial_obj and self.serial_obj.is_open:
            try:
                raw = self.serial_obj.readline()
                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        self._append_line(line)
                        self.handle_line(line)
            except serial.SerialException as exc:
                self.log(f"Serial disconnected unexpectedly: {exc}")
                self.status("Connection Lost", str(exc), state="error")
                self.is_connected = False
                break
            except Exception as exc:
                self.log(f"Reader error: {exc}")
                break

    # ── Hooks for subclasses ─────────────────────────────────────────────────

    def handle_line(self, line: str) -> None:
        """Called for every line received from firmware. Override in subclasses."""
        self.log(line)

    # ── Utility ─────────────────────────────────────────────────────────────

    def status(self, stage: str, detail: str, state: str = "active", **extra: Any) -> None:
        payload: dict[str, Any] = {
            "role": self.role,
            "stage": stage,
            "detail": detail,
            "state": state,
        }
        payload.update(extra)
        self.on_status(payload)

    def log(self, line: str) -> None:
        self.on_log(line)

    def close(self) -> None:
        self.disconnect()
