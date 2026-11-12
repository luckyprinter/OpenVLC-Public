"""Serial session management — thread-safe, role-aware baud rates, bounded log."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from .detection import BAUDRATE, BAUDRATE_RX, BAUDRATE_TX, baud_for_role
from .line_buffer import SerialLineBuffer

# ── Protocol constants (match firmware exactly) ────────────────────────────────
MAX_STREAM_FILE_BYTES = 81920   # 80 KB — matches firmware MAX_STREAM_FILE_BYTES
MAX_NAME_BYTES        = 80      # matches firmware MAX_NAME_BYTES (was wrongly 64)
STREAM_SERIAL_BLOCK   = 512    # bytes per STREAM_DATA chunk sent to firmware

LogCallback    = Callable[[str], None]
StatusCallback = Callable[[dict[str, Any]], None]

# How many serial lines to keep in memory (prevents unbounded growth).
_MAX_LOG_LINES = 2000

def crc16_ccitt(
    data: bytes, poly: int = 0x1021, initial_crc: int = 0xFFFF
) -> int:
    """Calculate CRC-16/CCITT, optionally continuing from a prior CRC."""
    crc = initial_crc & 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ poly if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def write_status(role: str, payload: dict[str, Any]) -> None:
    """Write serial status through the application-owned runtime data layer."""
    from gui_dev_v3.data.status import write_status as write_runtime_status

    reserved = {"role", "stage", "detail", "state", "updated_at", "percent"}
    extras = {key: value for key, value in payload.items() if key not in reserved}
    write_runtime_status(
        role,
        str(payload.get("stage", "")),
        str(payload.get("detail", "")),
        percent=payload.get("percent"),
        state=str(payload.get("state", "idle")),
        **extras,
    )


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
        # Serialize writes and prevent disconnect from closing a port mid-write.
        self._write_lock = threading.Lock()
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
            if self._reader_thread is not None and self._reader_thread.is_alive():
                raise RuntimeError("Previous serial reader did not stop; refusing overlapping connection")
            ser = serial.Serial()
            ser.port = device
            ser.baudrate = baud
            ser.timeout = 0.1
            # Prevent Windows from resetting the ESP32 and dropping the handle
            ser.dtr = False
            ser.rts = False
            # POSIX pySerial uses an exclusive OS lock; Windows serial handles
            # are exclusive at the driver level.
            ser.exclusive = True
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
        # Wait for an in-flight write before closing the underlying handle.
        with self._write_lock:
            ser = self.serial_obj
            self.serial_obj = None
            if ser is not None and getattr(ser, "is_open", False):
                try:
                    ser.close()
                except Exception:
                    pass

        # A reader from the previous connection must stop before a new port
        # can be installed, otherwise reconnects can create two readers on the
        # same new serial object.
        reader = self._reader_thread
        if reader is not None and reader.is_alive() and reader is not threading.current_thread():
            reader.join(timeout=1.0)
        if reader is None or not reader.is_alive():
            self._reader_thread = None

        self.is_connected = False
        self.log("Disconnected")
        self.status("Disconnected", "", state="idle")
        write_status(self.role, {"role": self.role, "stage": "Idle", "state": "idle"})

    # ── I/O ─────────────────────────────────────────────────────────────────

    def send_line(self, line: str) -> bool:
        error: Exception | None = None
        with self._write_lock:
            ser = self.serial_obj
            if not self.is_connected or ser is None:
                self.log("Not connected")
                return False
            try:
                data = (line + "\n").encode("utf-8")
                ser.write(data)
            except Exception as exc:
                error = exc

        if error is not None:
            self.log(f"Send error: {error}")
            self.disconnect()  # Handle hot unplug during send
            return False
        self.log(f">> {line}")
        return True

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

        # PySerial readline() may return a partial fragment when its timeout
        # expires. Do not dispatch that fragment as a complete protocol line:
        # large RX_FILE_HEX messages can span many reads.
        line_buffer = SerialLineBuffer()
        while self._running and self.serial_obj and self.serial_obj.is_open:
            try:
                raw = self.serial_obj.readline()
                if raw:
                    previous_overflows = line_buffer.overflow_count
                    for line in line_buffer.feed(raw):
                        self._append_line(line)
                        self.handle_line(line)
                    if line_buffer.overflow_count > previous_overflows:
                        self.log("Discarded an overlong or malformed serial line")
            except serial.SerialException as exc:
                if self._running:
                    self._mark_reader_failed(exc)
                break
            except Exception as exc:
                if self._running:
                    self._mark_reader_failed(exc)
                break
        line_buffer.clear()

    def _mark_reader_failed(self, exc: Exception) -> None:
        """Invalidate and release a TX serial handle after an unexpected read failure."""
        self._running = False
        with self._write_lock:
            ser = self.serial_obj
            self.serial_obj = None
            if ser is not None and getattr(ser, "is_open", False):
                try:
                    ser.close()
                except Exception:
                    pass
        self.is_connected = False
        self.log(f"Serial disconnected unexpectedly: {type(exc).__name__}")
        self.status("Connection Lost", type(exc).__name__, state="error")

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
