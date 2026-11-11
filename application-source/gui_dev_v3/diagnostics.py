"""Privacy-first local diagnostics primitives.

Nothing is collected or uploaded unless the application explicitly enables
this store. Events are schema-limited: arbitrary strings, file paths, payloads,
serial output, and exception messages are never accepted.
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
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
        try:
            number = int(value)
        except (ValueError, OverflowError):
            return None
        return number if low <= number <= high else None
    if key in {"app_version", "python_version", "qt_version", "pyserial_version"}:
        if not isinstance(value, str) or len(value) > 32:
            return None
        # Version strings only; reject anything that looks like a path or free text.
        import re
        return value if re.fullmatch(r"[0-9A-Za-z.+_-]{1,32}", value) else None
    return None


@contextmanager
def _cross_process_file_lock(path: Path):
    """Lock a sidecar file so TX and RX processes can safely share one JSONL queue.

    Uses the native advisory lock on each supported platform. The lock file is
    intentionally persistent: deleting it while another process has it open
    could create two independently locked inodes.
    """
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_stream:
        if os.name == "nt":
            import msvcrt
            lock_stream.seek(0, os.SEEK_END)
            if lock_stream.tell() == 0:
                lock_stream.write(b"\\0")
                lock_stream.flush()
            lock_stream.seek(0)
            msvcrt.locking(lock_stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_stream.seek(0)
                msvcrt.locking(lock_stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)


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
            with _cross_process_file_lock(self.path):
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(encoded + "\n")
                    stream.flush()
        return True

    def export_text(self) -> str:
        """Return the local queue for user review/export; never uploads it."""
        with self._lock, _cross_process_file_lock(self.path):
            if not self.path.exists():
                return ""
            return self.path.read_text(encoding="utf-8")

    def clear(self) -> None:
        """Delete locally queued diagnostics."""
        with self._lock, _cross_process_file_lock(self.path):
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass



_STORE_CACHE: dict[str, LocalDiagnostics] = {}


def get_diagnostics_store(role: str, mgr: Any | None = None) -> LocalDiagnostics:
    """Return the process-wide store shared by a role's UI and backend."""
    normalized = role.lower()
    if normalized not in {"tx", "rx"}:
        raise ValueError("Diagnostics role must be 'tx' or 'rx'.")
    store = _STORE_CACHE.get(normalized)
    if store is None:
        if mgr is None:
            from gui_dev_v3.settings import SettingsManager
            mgr = SettingsManager(normalized)
        store = LocalDiagnostics(enabled=bool(mgr.get("diagnostics/consent", False)))
        _STORE_CACHE[normalized] = store
    return store


def record_local_event(role: str, event: str, **fields: Any) -> bool:
    """Record an event only when this role's explicit local-consent setting is on."""
    return get_diagnostics_store(role).record(event, **fields)


def build_diagnostics_controls(mgr: Any, role: str):
    """Build the explicit opt-in and local data controls used by TX and RX."""
    from PySide6.QtWidgets import (
        QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
        QPlainTextEdit, QPushButton, QVBoxLayout,
    )
    from gui_dev_v3.widgets import Card, muted_label, primary_button

    enabled = bool(mgr.get("diagnostics/consent", False))
    store = get_diagnostics_store(role, mgr)
    store.set_enabled(enabled)
    card = Card("Optional Local Diagnostics")
    card.body.addWidget(muted_label(
        "Off by default. When enabled, the app may save limited technical event "
        "metadata locally to help diagnose connection, calibration, and transfer "
        "reliability. No files, filenames, payloads, raw serial output, or uploads."
    ))

    consent = QCheckBox("Allow local diagnostics on this computer")
    consent.setChecked(enabled)
    card.body.addWidget(consent)

    status = QLabel("Local queue: " + ("enabled" if enabled else "disabled"))
    card.body.addWidget(status)

    def update_consent(checked: bool) -> None:
        store.set_enabled(checked)
        mgr.set("diagnostics/consent", checked)
        status.setText("Local queue: " + ("enabled" if checked else "disabled"))

    consent.toggled.connect(update_consent)

    actions = QHBoxLayout()
    review = primary_button("Review Local Data")
    export = primary_button("Export Local Data")
    clear = QPushButton("Delete Local Data")
    clear.setObjectName("Danger")
    actions.addWidget(review)
    actions.addWidget(export)
    actions.addWidget(clear)
    card.body.addLayout(actions)

    def require_enabled() -> bool:
        if not store.enabled:
            QMessageBox.information(card, "Diagnostics Disabled", "Enable local diagnostics first. No events are collected while it is disabled.")
            return False
        return True

    def review_data() -> None:
        if not require_enabled():
            return
        dialog = QDialog(card)
        dialog.setWindowTitle("Review Local Diagnostics")
        dialog.resize(680, 480)
        layout = QVBoxLayout(dialog)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(store.export_text() or "No diagnostic events have been recorded.")
        layout.addWidget(viewer)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()

    def export_data() -> None:
        if not require_enabled():
            return
        content = store.export_text()
        if not content:
            QMessageBox.information(card, "Nothing to Export", "There are no local diagnostic events yet.")
            return
        path, _ = QFileDialog.getSaveFileName(card, "Export Diagnostics", "vlc-diagnostics.jsonl", "JSON Lines (*.jsonl);;Text files (*.txt)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(content)
            except OSError as exc:
                QMessageBox.warning(card, "Export Failed", f"Could not save the diagnostic file: {type(exc).__name__}")

    def delete_data() -> None:
        if not store.path.exists():
            QMessageBox.information(card, "No Local Data", "There is no local diagnostic queue to delete.")
            return
        answer = QMessageBox.question(card, "Delete Local Diagnostics", "Permanently delete the locally stored diagnostic events?")
        if answer == QMessageBox.StandardButton.Yes:
            store.clear()
            QMessageBox.information(card, "Deleted", "Local diagnostic data has been deleted.")

    review.clicked.connect(review_data)
    export.clicked.connect(export_data)
    clear.clicked.connect(delete_data)
    return card
