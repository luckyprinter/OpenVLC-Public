"""Observable receiver application state backed by physical ESP32 hardware."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gui_dev_v3.data.session import build_empty_session
from gui_dev_v3.models import SessionState, SignalState, TransferRecord, SessionCapture
from gui_dev_v3.settings_store import AppSettings, load_settings

# Backend imports
from gui_dev_v3.rx.backends.physical import RXPhysicalBackend, RXPhysicalSnapshot

StateSubscriber = Callable[["RXAppState"], None]

POLL_INTERVAL_MS = 1000  # Refresh status every second


# Module-level empty defaults (built once)
_EMPTY_SESSION = build_empty_session()
_EMPTY_SIGNAL = _EMPTY_SESSION.signal
_EMPTY_TRANSFER = _EMPTY_SESSION.latest_transfer


@dataclass
class RXAppState:
    """Observable receiver state store backed by the physical serial backend."""

    settings: AppSettings = field(default_factory=load_settings)
    session: SessionState = field(default_factory=build_empty_session)
    signal: SignalState = field(default=_EMPTY_SIGNAL)
    transfer: TransferRecord = field(default=_EMPTY_TRANSFER)
    activity_log: list[dict[str, str]] = field(default_factory=list)
    using_mock_data: bool = False
    serial_connected: bool = False
    expected_file_path: str | None = None
    expected_file_data: bytes | None = None
    _method2_cache_key: tuple | None = field(default=None, init=False, repr=False)
    _method2_cache: dict | None = field(default=None, init=False, repr=False)
    current_capture: SessionCapture | None = None
    _subscribers: list[StateSubscriber] = field(default_factory=list, init=False, repr=False)
    _lock: __import__("threading").Lock = field(default_factory=__import__("threading").Lock, init=False, repr=False)

    # Backend instances (initialized lazily, default to None)
    _physical: RXPhysicalBackend | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._last_tid = 0
        self._phys_capture_active = False
        self._phys_capture_start_time = 0.0
        self._phys_pvo: list[float] = []
        self._phys_vref: list[float] = []
        self._phys_margin: list[float] = []
        self._phys_time: list[float] = []
        self._phys_bits: list[int] = []
        self._phys_events: list[dict[str, Any]] = []
        self._refresh()

    @property
    def is_receiving(self) -> bool:
        with self._lock:
            stage = str(self.session.latest_transfer.status.value if self.session.latest_transfer else "").lower()
            return "incomplete" in stage or "receiving" in stage or self.session.progress_percent not in (0, 100)

    @property
    def progress_percent(self) -> int:
        with self._lock:
            return self.session.progress_percent

    @property
    def current_file(self) -> str:
        with self._lock:
            return self.session.current_file

    def subscribe(self, callback: StateSubscriber) -> None:
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: StateSubscriber) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def notify(self) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for callback in subs:
            callback(self)

    def apply_settings(self, settings: AppSettings) -> None:
        with self._lock:
            self.settings = settings
        self.notify()

    def get_method2_comparison(self) -> dict | None:
        """Return a cached byte-for-byte comparison against the selected reference file."""
        with self._lock:
            expected_path = self.expected_file_path
            transfer = self.session.latest_transfer if self.session else None
        if not expected_path or transfer is None or not transfer.received_path:
            return None
        expected, received = Path(expected_path), Path(transfer.received_path)
        try:
            expected_stat, received_stat = expected.stat(), received.stat()
        except OSError:
            return None
        key = (transfer.tid, str(expected), str(received), expected_stat.st_size,
               expected_stat.st_mtime_ns, received_stat.st_size, received_stat.st_mtime_ns)
        with self._lock:
            if key == self._method2_cache_key:
                return self._method2_cache
        try:
            from gui_dev_v3.logic.ber_bridge import compare_files
            result = compare_files(expected, received)
        except (OSError, ValueError):
            return None
        with self._lock:
            self._method2_cache_key, self._method2_cache = key, result
        return result

    def load_expected_file(self, filepath: str) -> None:
        """Set the original reference path without loading a large file into RAM."""
        path = Path(filepath).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Reference file not found: {path}")
        with self._lock:
            self.expected_file_path = str(path)
            self.expected_file_data = None
            self._method2_cache_key = None
            self._method2_cache = None
        self._update_current_capture_method2()
        self.notify()

    def _update_current_capture_method2(self) -> None:
        """Persist Method 2 when a reference is selected after reception."""
        with self._lock:
            capture = self.current_capture
            transfer = self.session.latest_transfer if self.session else None
        if capture is None or transfer is None or capture.tid != transfer.tid:
            return
        result = self.get_method2_comparison()
        if result is None:
            return
        updated = replace(capture, ber=result["strict_ber"], ber_method="method2")
        with self._lock:
            if self.current_capture is not capture:
                return
            self.current_capture = updated
        from gui_dev_v3.data import save_session_capture
        save_session_capture(updated)

    def clear_expected_file(self) -> None:
        with self._lock:
            self.expected_file_path = None
            self.expected_file_data = None
            self._method2_cache_key = None
            self._method2_cache = None
        self.notify()


    def send_firmware_command(self, cmd: str) -> bool:
        """Send command to the connected physical firmware."""
        with self._lock:
            physical = self._physical
        return physical.send_command(cmd) if physical else False

    def _refresh(self) -> None:
        """Refresh state from the physical ESP32 receiver backend."""
        if self._physical is None:
            self._physical = RXPhysicalBackend()
        snap = self._physical.refresh() if self._physical else None
        with self._lock:
            if snap:
                self._apply_phy_snapshot(snap)
            else:
                self._load_empty()

    def _apply_phy_snapshot(self, s: RXPhysicalSnapshot) -> None:
        self.session = s.session
        self.signal = s.session.signal
        self.transfer = s.transfer
        for log_item in s.activity_log:
            if self.activity_log:
                last_log = self.activity_log[0]
                if last_log["event"] == log_item["event"] and last_log["details"] == log_item["details"]:
                    continue
            if log_item not in self.activity_log:
                self.activity_log.insert(0, log_item)
        self.activity_log = self.activity_log[:500]
        self.serial_connected = s.serial_connected
        self.using_mock_data = False

    def _load_empty(self) -> None:
        import time
        now = time.strftime("%H:%M:%S")
        self.session = _EMPTY_SESSION
        self.signal = _EMPTY_SIGNAL
        self.transfer = _EMPTY_TRANSFER
        # An offline physical backend is not simulated or mock data.
        self.using_mock_data = False
        self.serial_connected = False

    def force_connect_serial(self, port: str) -> bool:
        """Force connect physical backend to a port, bypassing detection."""
        with self._lock:
            if self._physical is None:
                self._physical = RXPhysicalBackend()
            res = self._physical.connect(port, force=True)
        self._refresh()
        self.notify()
        return res

    def refresh(self) -> None:
        """Public refresh — called by QTimer."""
        self._refresh()

        current_tid = self.session.latest_transfer.tid if (self.session and self.session.latest_transfer) else 0
        if current_tid != self._last_tid:
            self._last_tid = current_tid
            self.current_capture = None
            self._phys_capture_active = False

        if current_tid > 0:
            is_rec = self.is_receiving
            if is_rec and not self._phys_capture_active:
                import time
                self._phys_capture_active = True
                self._phys_capture_start_time = time.time()
                self._phys_pvo = []
                self._phys_vref = []
                self._phys_margin = []
                self._phys_time = []
                self._phys_bits = []
                self._phys_events = [{"time": 0.0, "event": "START", "details": f"Physical reception started for TID {current_tid}"}]
                print(f"Physical capture session started for TID {current_tid}")

            if self._phys_capture_active:
                import time
                elapsed = time.time() - self._phys_capture_start_time
                self._phys_time.append(elapsed)
                self._phys_pvo.append(self.signal.pvo)
                self._phys_vref.append(self.signal.vref)
                self._phys_margin.append(self.signal.margin)

                bit = 1 if self.signal.pvo > self.signal.vref else 0
                self._phys_bits.append(bit)

                if not is_rec:
                    self._phys_capture_active = False
                    self._phys_events.append({"time": elapsed, "event": "COMPLETE", "details": "Physical reception finished"})

                    import datetime
                    from gui_dev_v3.data import save_session_capture
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    size = self.session.latest_transfer.size_bytes if self.session.latest_transfer else 0
                    duration = elapsed if elapsed > 0 else 1.0
                    throughput = (size * 8) / (duration * 1000.0)

                    cap = SessionCapture(
                        tid=current_tid,
                        timestamp=timestamp,
                        filename=self.session.latest_transfer.filename if self.session.latest_transfer else "unknown.bin",
                        ber=(self.get_method2_comparison() or {}).get("strict_ber"),
                        ber_method="method2" if self.get_method2_comparison() is not None else None,
                        crc_status=self.signal.crc_status,
                        throughput_kbps=round(throughput, 3),
                        analog_time=self._phys_time,
                        pvo_samples=self._phys_pvo,
                        vref_samples=self._phys_vref,
                        margin_samples=self._phys_margin,
                        ook_bits=self._phys_bits,
                        protocol_events=self._phys_events,
                    )
                    save_session_capture(cap)
                    self.current_capture = cap
                    print(f"Physical capture session saved for TID {current_tid}")

        if self.current_capture is None and current_tid > 0:
            from gui_dev_v3.data import load_session_capture
            loaded = load_session_capture(current_tid)
            if loaded:
                self.current_capture = loaded
                print(f"Loaded session capture from disk for TID {current_tid}")

        self.notify()

    def rebuild_backends(self) -> None:
        """Recreate backend instances (useful after serial port changes)."""
        self.cleanup()

    def cleanup(self) -> None:
        """Clean up and stop active backends."""
        with self._lock:
            if self._physical:
                try:
                    self._physical.cleanup()
                except Exception:
                    pass
                self._physical = None



def build_default_state() -> RXAppState:
    return RXAppState()
