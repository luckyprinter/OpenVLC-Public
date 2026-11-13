"""Receiver application state backed exclusively by physical ESP32 hardware."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gui_dev_v3.data.session import build_empty_session
from gui_dev_v3.models import SessionState, SignalState, TransferRecord, SessionCapture
from gui_dev_v3.settings_store import AppSettings, load_settings

# Backend imports
from gui_dev_v3.rx.backends.physical import RXPhysicalBackend, RXPhysicalSnapshot
from gui_dev_v3.rx.backends.simulation import RXSimulationBackend, RXSimulationSnapshot

StateSubscriber = Callable[["RXAppState"], None]

POLL_INTERVAL_MS = 1000  # Refresh status every second


# Module-level empty defaults (built once)
_EMPTY_SESSION = build_empty_session()
_EMPTY_SIGNAL = _EMPTY_SESSION.signal
_EMPTY_TRANSFER = _EMPTY_SESSION.latest_transfer


@dataclass
class RXAppState:
    """Observable receiver state populated by the physical ESP32 backend."""

    settings: AppSettings = field(default_factory=load_settings)
    mode: str = "physical"
    session: SessionState = field(default_factory=build_empty_session)
    signal: SignalState = field(default=_EMPTY_SIGNAL)
    transfer: TransferRecord = field(default=_EMPTY_TRANSFER)
    activity_log: list[dict[str, str]] = field(default_factory=list)
    serial_connected: bool = False
    expected_file_path: str | None = None
    current_capture: SessionCapture | None = None
    using_mock_data: bool = False
    _expected_file_data: bytes | None = field(default=None, init=False, repr=False)
    _subscribers: list[StateSubscriber] = field(default_factory=list, init=False, repr=False)
    _lock: __import__("threading").Lock = field(default_factory=__import__("threading").Lock, init=False, repr=False)

    # Physical backend is initialized lazily when the application first refreshes.
    _physical: RXPhysicalBackend | None = field(default=None, init=False, repr=False)
    _simulation: RXSimulationBackend | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._last_tid = 0
        self._method2_comparison: dict[str, Any] | None = None
        self._phys_capture_active = False
        self._phys_capture_start_time = 0.0
        self._phys_pvo: list[float] = []
        self._phys_vref: list[float] = []
        self._phys_margin: list[float] = []
        self._phys_time: list[float] = []
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

    def set_mode(self, mode: str) -> None:
        """Switch between isolated physical and simulated RX backends."""
        if mode not in {"physical", "simulated"}:
            raise ValueError(f"Unsupported RX mode: {mode}")
        with self._lock:
            if mode == self.mode:
                return
            old_physical = self._physical if self.mode == "physical" else None
            old_simulation = self._simulation if self.mode == "simulated" else None
            if old_physical is not None:
                self._physical = None
            if old_simulation is not None:
                self._simulation = None
            self.mode = mode
            self.using_mock_data = mode == "simulated"
            self.activity_log = []
            self.current_capture = None
            self._method2_comparison = None
            self._phys_capture_active = False
        if old_physical is not None:
            try:
                old_physical.cleanup()
            except Exception:
                pass
        if old_simulation is not None:
            try:
                old_simulation.cleanup()
            except Exception:
                pass
        self._refresh()
        self.notify()

    def update_simulation_params(self, **kwargs: Any) -> None:
        """Update virtual-channel parameters without opening a serial port."""
        if self._simulation is None:
            self._simulation = RXSimulationBackend()
            if self._expected_file_data is not None:
                self._simulation.set_expected_file(
                    self._expected_file_data, self.expected_file_path
                )
        self._simulation.set_params(**kwargs)
        if self.mode == "simulated":
            self._refresh()
            self.notify()

    def load_expected_file(self, filepath: str) -> None:
        """Select the original reference file without loading it into memory."""
        from pathlib import Path
        try:
            path = Path(filepath).expanduser().resolve(strict=True)
            if not path.is_file():
                return
            data = path.read_bytes() if self.mode == "simulated" else None
            with self._lock:
                self.expected_file_path = str(path)
                self._expected_file_data = data
                simulation = self._simulation
            if simulation is not None:
                simulation.set_expected_file(data, str(path))
            self.notify()
        except (OSError, ValueError):
            return

    def clear_expected_file(self) -> None:
        """Clear the loaded expected/original reference file."""
        with self._lock:
            self.expected_file_path = None
            self._expected_file_data = None
            simulation = self._simulation
        if simulation is not None:
            simulation.set_expected_file(None, None)
        self._refresh()
        self.notify()

    def apply_method2_result(self, tid: int, strict_ber: float | None) -> None:
        """Persist a reference-file BER result on the matching completed capture."""
        from dataclasses import replace

        with self._lock:
            capture = self.current_capture
            if capture is None or capture.tid != int(tid):
                return
            method = "method2_reference_file"
            if capture.ber == strict_ber and capture.ber_method == method:
                return
            updated = replace(capture, ber=strict_ber, ber_method=method)
            self.current_capture = updated

        from gui_dev_v3.data import save_session_capture
        save_session_capture(updated)

    def set_method2_comparison(self, tid: int, comparison: dict[str, Any]) -> None:
        """Keep the full live Method 2 result and persist its strict BER."""
        with self._lock:
            if int(tid) != self.transfer.tid:
                return
            self._method2_comparison = {
                "tid": int(tid),
                "overlap_ber": comparison.get("overlap_ber"),
                "strict_ber": comparison.get("strict_ber"),
                "bit_accuracy": comparison.get("bit_accuracy"),
                "strict_bit_errors": comparison.get("strict_bit_errors"),
                "overlap_bytes": comparison.get("overlap_bytes"),
                "expected_bytes": comparison.get("expected_bytes"),
                "length_delta": comparison.get("length_delta"),
            }
        self.apply_method2_result(tid, comparison.get("strict_ber"))

    def get_method2_comparison(self) -> dict[str, Any] | None:
        """Return the current transfer's reference comparison, if available."""
        with self._lock:
            current = self._method2_comparison
            if current is not None and current.get("tid") == self.transfer.tid:
                return dict(current)
            capture = self.current_capture
            if (
                capture is not None
                and capture.tid == self.transfer.tid
                and capture.ber_method in {"method2", "method2_reference_file"}
            ):
                return {
                    "tid": capture.tid,
                    "overlap_ber": None,
                    "strict_ber": capture.ber,
                    "bit_accuracy": None,
                }
        return None

    def send_firmware_command(self, cmd: str) -> bool:
        """Send command to physical firmware if active."""
        with self._lock:
            physical = self._physical if self.mode == "physical" else None
        if physical:
            return physical.send_command(cmd)
        return False

    def _refresh(self) -> None:
        """Refresh receiver state from the currently selected backend."""
        with self._lock:
            mode = self.mode
        if mode == "simulated":
            if self._simulation is None:
                self._simulation = RXSimulationBackend()
                if self._expected_file_data is not None:
                    self._simulation.set_expected_file(
                        self._expected_file_data, self.expected_file_path
                    )
            snapshot = self._simulation.refresh()
            with self._lock:
                self._apply_sim_snapshot(snapshot)
        else:
            if self._physical is None:
                self._physical = RXPhysicalBackend()
            snapshot = self._physical.refresh()
            with self._lock:
                if snapshot:
                    self._apply_phy_snapshot(snapshot)
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

    def _apply_sim_snapshot(self, s: RXSimulationSnapshot) -> None:
        self.session = s.session
        self.signal = s.session.signal
        self.transfer = s.transfer
        self.activity_log = s.activity_log[-500:]
        self.serial_connected = bool(getattr(self._simulation, "_tx_connected", False))
        self.using_mock_data = True

    def _load_empty(self) -> None:
        import time
        now = time.strftime("%H:%M:%S")
        self.session = _EMPTY_SESSION
        self.signal = _EMPTY_SIGNAL
        self.transfer = _EMPTY_TRANSFER
        self.serial_connected = False
        self.using_mock_data = self.mode == "simulated"

    def force_connect_serial(self, port: str) -> bool:
        """Force connect physical backend to a port, bypassing detection."""
        if self.mode != "physical":
            self.set_mode("physical")
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
            self._method2_comparison = None
            self.current_capture = None
            self._phys_capture_active = False

        if self.mode == "physical" and current_tid > 0:
            is_rec = self.is_receiving
            if is_rec and not self._phys_capture_active:
                import time
                self._phys_capture_active = True
                self._phys_capture_start_time = time.time()
                self._phys_pvo = []
                self._phys_vref = []
                self._phys_margin = []
                self._phys_time = []
                self._phys_events = [{"time": 0.0, "event": "START", "details": f"Physical reception started for TID {current_tid}"}]
                print(f"Physical capture session started for TID {current_tid}")

            if self._phys_capture_active:
                import time
                elapsed = time.time() - self._phys_capture_start_time
                self._phys_time.append(elapsed)
                self._phys_pvo.append(self.signal.pvo)
                self._phys_vref.append(self.signal.vref)
                self._phys_margin.append(self.signal.margin)

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
                        ber=None,
                        crc_status=self.signal.crc_status,
                        throughput_kbps=round(throughput, 3),
                        analog_time=self._phys_time,
                        pvo_samples=self._phys_pvo,
                        vref_samples=self._phys_vref,
                        margin_samples=self._phys_margin,
                        # No raw comparator/bit samples are streamed by current firmware.
                        ook_bits=[],
                        protocol_events=self._phys_events,
                        ber_method="unavailable",
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

    def get_new_simulation_samples(self, last_idx: int) -> list[tuple[float, float, float, int]]:
        """Return analog samples generated by the RX simulation backend."""
        with self._lock:
            simulation = self._simulation
        if simulation is None:
            return []
        return simulation.get_new_samples(last_idx)

    def cleanup(self) -> None:
        """Clean up both backends; only the selected backend is active."""
        with self._lock:
            physical = self._physical
            simulation = self._simulation
            self._physical = None
            self._simulation = None
        if physical is not None:
            try:
                physical.cleanup()
            except Exception:
                pass
        if simulation is not None:
            try:
                simulation.cleanup()
            except Exception:
                pass


def build_default_state(mode: str = "physical") -> RXAppState:
    return RXAppState(mode=mode)
