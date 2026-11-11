"""Privacy-first local diagnostics primitives.

Nothing is collected or uploaded unless the application explicitly enables
this store. Events are schema-limited: arbitrary strings, file paths, payloads,
serial output, and exception messages are never accepted.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
_ALLOWED_EVENTS = frozenset({
    "app_started",
    "serial_scan",
    "serial_probe",
    "serial_connected",
    "serial_disconnected",
    "calibration_completed",
    "transfer_completed",
    "transfer_failed",
})
_ALLOWED_FIELDS: dict[str, frozenset[str]] = {
    "app_started": frozenset({"app_version", "os_family", "python_version", "qt_version", "pyserial_version"}),
    "serial_scan": frozenset({"role", "ports_seen", "duration_ms"}),
    "serial_probe": frozenset({"role", "result", "baud_rate", "duration_ms"}),
    "serial_connected": frozenset({"role", "baud_rate", "firmware_family"}),
    "serial_disconnected": frozenset({"role", "reason_code"}),
    "calibration_completed": frozenset({"result", "iterations", "target_margin_mv", "measured_margin_mv", "pwm_duty"}),
    "transfer_completed": frozenset({"role", "size_bucket", "duration_ms", "chunk_count", "crc_ok", "ber_zero"}),
    "transfer_failed": frozenset({"role", "reason_code", "size_bucket", "duration_ms", "retry_count"}),
}
_ENUMS: dict[str, frozenset[str]] = {
    "role": frozenset({"tx", "rx"}),
    "os_family": frozenset({"windows", "linux", "macos", "other"}),
    "result": frozenset({"success", "failure", "timeout", "busy", "unknown"}),
    "firmware_family": frozenset({"tx_dma", "tx_non_dma", "rx", "unknown"}),
    "reason_code": frozenset({
        "user_disconnect", "port_busy", "device_removed", "identify_timeout",
        "serial_error", "transfer_timeout", "crc_mismatch", "unknown",
    }),
    "size_bucket": frozenset({"empty", "under_1kib", "1_to_16kib", "16_to_80kib", "over_80kib"}),
}
_BOOL_FIELDS = frozenset({"crc_ok", "ber_zero"})
_INT_RANGES = {
    "ports_seen": (0, 64),
    "duration_ms": (0, 86_400_000),
    "baud_rate": (1200, 4_000_000),
    "iterations": (0, 100_000),
    "target_margin_mv": (0, 5000),
    "measured_margin_mv": (0, 5000),
    "pwm_duty": (0, 255),
    "chunk_count": (0, 1_000_000),
    "retry_count": (0, 100_000),
}


def _safe_value(key: str, value: Any) -> str | int | float | bool | None:
    if key in _ENUMS:
        return value if isinstance(value, str) and value in _ENUMS[key] else None
    if key in _BOOL_FIELDS:
        return value if isinstance(value, bool) else None
    if key in _INT_RANGES:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        low, high = _INT_RANGES[key]
        number = int(value)
        return number if low <= number <= high else None
    if key in {"app_version", "python_version", "qt_version", "pyserial_version"}:
        if not isinstance(value, str) or len(value) > 32:
            return None
        # Version strings only; reject anything that looks like a path or free text.
        import re
        return value if re.fullmatch(r"[0-9A-Za-z.+_-]{1,32}", value) else None
    return None


class LocalDiagnostics:
    """Append-only JSONL diagnostic queue, disabled until explicit opt-in."""

    def __init__(self, path: str | os.PathLike[str] | None = None, *, enabled: bool = False) -> None:
        self.path = Path(path).expanduser() if path is not None else (
            Path.home() / ".vlc_app" / "diagnostics.jsonl"
        )
        self._enabled = bool(enabled)
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def record(self, event: str, **fields: Any) -> bool:
        """Record only allowlisted, typed metadata. Returns False when disabled/invalid."""
        if not self._enabled or event not in _ALLOWED_EVENTS:
            return False
        allowed = _ALLOWED_FIELDS[event]
        clean: dict[str, Any] = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            safe = _safe_value(key, value)
            if safe is not None:
                clean[key] = safe
        entry = {
            "schema_version": SCHEMA_VERSION,
            "timestamp": int(time.time()),
            "event": event,
            "data": clean,
        }
        encoded = json.dumps(entry, separators=(",", ":"), sort_keys=True)
        with self._lock:
            if not self._enabled:
                return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
                stream.flush()
        return True

    def export_text(self) -> str:
        """Return the local queue for user review/export; never uploads it."""
        with self._lock:
            if not self.path.exists():
                return ""
            return self.path.read_text(encoding="utf-8")

    def clear(self) -> None:
        """Delete locally queued diagnostics."""
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
