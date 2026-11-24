"""Observable receiver state for isolated physical and simulated backends."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from gui_dev_v3.data import load_session_capture, save_session_capture
from gui_dev_v3.data.session import build_empty_session
from gui_dev_v3.models import SessionCapture, SessionState, SignalState, TransferRecord, TransferStatus
from gui_dev_v3.settings_store import AppSettings, load_settings

# Backend imports
from gui_dev_v3.rx.backends.physical import RXPhysicalBackend, RXPhysicalSnapshot
from gui_dev_v3.rx.backends.simulation import RXSimulationBackend, RXSimulationSnapshot

StateSubscriber = Callable[["RXAppState"], None]


class RXShutdownPending(RuntimeError):
    """A physical receiver still owns an outstanding hardware operation."""


POLL_INTERVAL_MS = 1000  # Refresh status every second
MAX_SIMULATION_REFERENCE_BYTES = 80 * 1024 * 1024
_TERMINAL_RECEPTION_STATUSES = {
    TransferStatus.COMPLETE, TransferStatus.CRC_FAILED, TransferStatus.STALLED,
}


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
    completed_physical_transfers: tuple[TransferRecord, ...] = field(default=(), init=False)
    using_mock_data: bool = False
    _expected_file_data: bytes | None = field(default=None, init=False, repr=False)
    _subscribers: list[StateSubscriber] = field(default_factory=list, init=False, repr=False)
    _lock: __import__("threading").Lock = field(default_factory=__import__("threading").Lock, init=False, repr=False)

    # Physical backend is initialized lazily when the application first refreshes.
    _physical: RXPhysicalBackend | None = field(default=None, init=False, repr=False)
    _simulation: RXSimulationBackend | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.mode not in {"physical", "simulated"}:
            self.mode = "physical"
        self.using_mock_data = self.mode == "simulated"
        self._method2_comparison: dict[str, Any] | None = None
        self._physical_samples: dict[str, list[tuple[float, float, float, float]]] = {}
        self._refresh()

    @property
    def is_receiving(self) -> bool:
        with self._lock:
            status = self.session.latest_transfer.status
            if status in _TERMINAL_RECEPTION_STATUSES:
                return False
            return status == TransferStatus.INCOMPLETE or self.session.progress_percent not in (0, 100)

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
        simulation_reference: bytes | None = self._expected_file_data
        if mode == "simulated" and self.expected_file_path and simulation_reference is None:
            reference_path = Path(self.expected_file_path)
            if reference_path.stat().st_size > MAX_SIMULATION_REFERENCE_BYTES:
                raise ValueError(
                    "Simulation reference files are limited to 80 MiB; "
                    "the original file remains selected for hardware mode."
                )
            simulation_reference = reference_path.read_bytes()
        with self._lock:
            if mode == self.mode:
                return
            old_physical = self._physical if self.mode == "physical" else None
            old_simulation = self._simulation if self.mode == "simulated" else None
        if old_physical is not None:
            self._close_physical(old_physical)
        with self._lock:
            self._expected_file_data = simulation_reference
            if old_physical is not None:
                self._physical = None
            if old_simulation is not None:
                self._simulation = None
            self.mode = mode
            self.using_mock_data = mode == "simulated"
            self.activity_log = []
            self.current_capture = None
            self._method2_comparison = None
            self.completed_physical_transfers = ()
            self._physical_samples.clear()
        if old_simulation is not None:
            try:
                old_simulation.cleanup()
            except Exception:
                pass
        self._refresh()
        self.notify()

    def update_simulation_params(self, **kwargs: Any) -> bool:
        """Update virtual-channel parameters without opening a serial port."""
        if self.mode != "simulated":
            return False
        if self._simulation is None:
            self._simulation = RXSimulationBackend()
            if self._expected_file_data is not None:
                self._simulation.set_expected_file(
                    self._expected_file_data, self.expected_file_path
                )
        self._simulation.set_params(**kwargs)
        self._refresh()
        self.notify()
        return True

    def load_expected_file(self, filepath: str) -> None:
        """Select the original reference file without loading it into memory."""
        from pathlib import Path
        try:
            path = Path(filepath).expanduser().resolve(strict=True)
            if not path.is_file():
                return
            data = None
            if self.mode == "simulated":
                if path.stat().st_size > MAX_SIMULATION_REFERENCE_BYTES:
                    raise ValueError("Simulation reference files are limited to 80 MiB.")
                data = path.read_bytes()
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

    @staticmethod
    def _capture_matches_transfer(capture: SessionCapture, transfer: TransferRecord) -> bool:
        if capture.tid != transfer.tid or capture.filename != transfer.filename:
            return False
        if capture.capture_id is None:
            return transfer.capture_id is None
        return (
            capture.capture_id == transfer.capture_id
            and capture.received_path == transfer.received_path
        )

    def set_method2_comparison(
        self,
        tid: int,
        comparison: dict[str, Any],
        *,
        capture_id: str | None,
        received_path: str,
    ) -> None:
        """Publish a file comparison for the current payload and its exact capture."""
        with self._lock:
            transfer = self.transfer
            if (
                not received_path
                or tid != transfer.tid
                or capture_id != transfer.capture_id
                or received_path != transfer.received_path
            ):
                return
            self._method2_comparison = {
                "tid": tid,
                "capture_id": capture_id,
                "received_path": received_path,
                "overlap_ber": comparison.get("overlap_ber"),
                "strict_ber": comparison.get("strict_ber"),
                "bit_accuracy": comparison.get("bit_accuracy"),
                "strict_bit_errors": comparison.get("strict_bit_errors"),
                "overlap_bytes": comparison.get("overlap_bytes"),
                "expected_bytes": comparison.get("expected_bytes"),
                "length_delta": comparison.get("length_delta"),
            }
            capture = self.current_capture
            if (
                self.mode != "physical"
                or capture_id is None
                or capture is None
                or not self._capture_matches_transfer(capture, transfer)
            ):
                return
            strict_ber = comparison.get("strict_ber")
            method = "method2_reference_file"
            if capture.ber != strict_ber or capture.ber_method != method:
                updated = replace(capture, ber=strict_ber, ber_method=method)
                save_session_capture(updated)
                self.current_capture = updated

    def get_method2_comparison(self) -> dict[str, Any] | None:
        """Return the current transfer's reference comparison, if available."""
        with self._lock:
            current = self._method2_comparison
            transfer = self.transfer
            if (
                current is not None
                and current["tid"] == transfer.tid
                and current["capture_id"] == transfer.capture_id
                and current["received_path"] == transfer.received_path
            ):
                return dict(current)
            capture = self.current_capture
            if (
                capture is not None
                and self._capture_matches_transfer(capture, transfer)
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
        before = self.transfer
        after = s.transfer
        if (
            after.tid != before.tid
            or after.capture_id != before.capture_id
            or after.filename != before.filename
            or after.received_path != before.received_path
        ):
            self._method2_comparison = None
            self.current_capture = None
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
        self._record_physical_captures(s)

    def _record_physical_captures(self, snapshot: RXPhysicalSnapshot) -> None:
        self._accept_physical_events(snapshot.completed_transfers, snapshot.analog_sample)

        current = self.transfer
        if current.status == TransferStatus.INCOMPLETE and current.capture_id is not None:
            # A physical backend can have one active receipt between refreshes.
            samples = self._physical_samples.get(current.capture_id, [])
            self._physical_samples = {current.capture_id: samples}
        else:
            self._physical_samples.clear()

        if current.status not in _TERMINAL_RECEPTION_STATUSES or current.tid <= 0:
            self.current_capture = None
        elif self.current_capture is None:
            capture = load_session_capture(current.tid, capture_id=current.capture_id)
            if capture is not None and self._capture_matches_transfer(capture, current):
                self.current_capture = capture

    def _accept_physical_events(
        self,
        completed: tuple[TransferRecord, ...],
        sample: tuple[str, float, float, float, float] | None,
    ) -> None:
        if sample is not None:
            capture_id, elapsed, pvo, vref, margin = sample
            samples = self._physical_samples.setdefault(capture_id, [])
            if not samples or elapsed > samples[-1][0]:
                samples.append((elapsed, pvo, vref, margin))

        self.completed_physical_transfers = completed
        for transfer in completed:
            if transfer.capture_id is None:
                continue
            samples = self._physical_samples.pop(transfer.capture_id, [])
            capture = self._finish_physical_capture(transfer, samples)
            if self._capture_matches_transfer(capture, self.transfer):
                self.current_capture = capture

    @staticmethod
    def _finish_physical_capture(
        transfer: TransferRecord, samples: list[tuple[float, float, float, float]]
    ) -> SessionCapture:
        previous = load_session_capture(transfer.tid, capture_id=transfer.capture_id)
        if previous is not None:
            return previous

        duration = transfer.duration_seconds
        received_bytes = transfer.received_bytes
        throughput = None
        if duration is not None and duration > 0 and received_bytes is not None and transfer.received_path:
            throughput = received_bytes * 8 / (duration * 1000)
        events = []
        if duration is not None:
            events.append({"time": 0.0, "event": "START", "details": "Firmware announced reception"})
        events.append({
            "time": duration,
            "event": transfer.status.value,
            "details": transfer.quality.first_issue if transfer.quality.first_issue != "None" else "",
        })
        capture = SessionCapture(
            tid=transfer.tid,
            timestamp=datetime.now().astimezone().isoformat(timespec="milliseconds"),
            filename=transfer.filename,
            ber=None,
            crc_status=transfer.quality.crc_status or "Unknown",
            throughput_kbps=throughput,
            analog_time=[sample[0] for sample in samples],
            pvo_samples=[sample[1] for sample in samples],
            vref_samples=[sample[2] for sample in samples],
            margin_samples=[sample[3] for sample in samples],
            ook_bits=[],
            protocol_events=events,
            capture_id=transfer.capture_id,
            received_path=transfer.received_path,
            received_bytes=received_bytes,
            duration_seconds=duration,
            status=transfer.status.value,
        )
        save_session_capture(capture)
        return capture

    def _apply_sim_snapshot(self, s: RXSimulationSnapshot) -> None:
        self.session = s.session
        self.signal = s.session.signal
        self.transfer = s.transfer
        self.activity_log = s.activity_log[-500:]
        self.serial_connected = bool(getattr(self._simulation, "_tx_connected", False))
        self.current_capture = s.capture
        self.using_mock_data = True

    def _load_empty(self) -> None:
        self.session = _EMPTY_SESSION
        self.signal = _EMPTY_SIGNAL
        self.transfer = _EMPTY_TRANSFER
        self.serial_connected = False
        self.using_mock_data = self.mode == "simulated"
        self.current_capture = None
        self.completed_physical_transfers = ()
        self._method2_comparison = None
        self._physical_samples.clear()

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
        if physical is not None:
            self._close_physical(physical)
        with self._lock:
            self._physical = None
            self._simulation = None
        if simulation is not None:
            try:
                simulation.cleanup()
            except Exception:
                pass

    def _close_physical(self, backend: RXPhysicalBackend) -> None:
        stopped = backend.cleanup()
        drain = getattr(backend, "drain_capture_events", None)
        if drain is not None:
            completed, sample = drain()
            self._accept_physical_events(completed, sample)
            if completed:
                self.notify()
        if stopped is False:
            raise RXShutdownPending("The RX reader is still finishing. Retry after the serial session stops.")


def build_default_state(mode: str = "physical") -> RXAppState:
    return RXAppState(mode=mode)
