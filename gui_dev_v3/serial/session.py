"""Serial session management — copied from vlc_migration."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .detection import BAUDRATE

MAX_STREAM_FILE_BYTES = 81920
MAX_NAME_BYTES = 64
STREAM_SERIAL_BLOCK = 2048

LogCallback = Callable[[str], None]
StatusCallback = Callable[[dict[str, Any]], None]

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
    def __init__(self, role: str, on_log: LogCallback | None = None, on_status: StatusCallback | None = None) -> None:
        self.role = role
        self.on_log = on_log or (lambda line: None)
        self.on_status = on_status or (lambda payload: None)
        self.serial_obj: Any = None
        self._lock = threading.Lock()
        self.is_connected = False
        self.last_lines: list[str] = []
        self._reader_thread: threading.Thread | None = None
        self._running = False

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    @is_connected.setter
    def is_connected(self, value: bool) -> None:
        with self._lock:
            self._is_connected = value

    def connect(self, device: str, expected_role: str = "") -> bool:
        try:
            import serial  # type: ignore[import-untyped]

            self.disconnect()
            ser = serial.Serial(device, BAUDRATE, timeout=0.1)
            self.serial_obj = ser
            self.is_connected = True
            self._running = True
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
            self.log(f"Connected to {device} at {BAUDRATE} baud")
            self.status("Connected", f"Serial link to {device}", state="ready")
            write_status(self.role, {"role": self.role, "stage": "Connected", "state": "active", "port": device})
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
            self.disconnect() # Handle hot unplug during send
            return False

    def wait_for_line_containing(self, text: str, timeout: float = 5.0, start_index: int = 0) -> bool:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_connected:
                return False
            with self._lock:
                for line in self.last_lines[start_index:]:
                    if text in line:
                        return True
            threading.Event().wait(0.05)
        return False

    def _reader_loop(self) -> None:
        import serial
        while self._running and self.serial_obj and self.serial_obj.is_open:
            try:
                raw = self.serial_obj.readline()
                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        with self._lock:
                            self.last_lines.append(line)
                        self.handle_line(line)
            except serial.SerialException as exc:
                self.log(f"Serial disconnected unexpectedly: {exc}")
                self.status("Connection Lost", str(exc), state="error")
                self.is_connected = False
                break
            except Exception as exc:
                self.log(f"Reader error: {exc}")
                break

    def handle_line(self, line: str) -> None:
        self.log(line)

    def status(self, stage: str, detail: str, state: str = "active", **extra: Any) -> None:
        payload: dict[str, Any] = {"role": self.role, "stage": stage, "detail": detail, "state": state}
        payload.update(extra)
        self.on_status(payload)

    def log(self, line: str) -> None:
        self.on_log(line)

    def close(self) -> None:
        self.disconnect()
