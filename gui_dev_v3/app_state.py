"""Application state — delegates to Physical or Simulation backend.

Modes:
  - "physical": reads real data from ESP32 hardware via serial.
  - "simulated": generates all data from virtual channel model (no hardware).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Any

from gui_dev_v3.data.session import build_empty_session
from gui_dev_v3.models import SessionState, SignalState, TransferRecord, SessionCapture
from gui_dev_v3.settings_store import AppSettings, load_settings

# Backend imports
from gui_dev_v3.rx.backends.physical import RXPhysicalBackend, RXPhysicalSnapshot
from gui_dev_v3.rx.backends.simulation import RXSimulationBackend, RXSimulationSnapshot

StateSubscriber = Callable[["RXAppState"], None]

POLL_INTERVAL_MS = 1000  # Refresh status every second

AppMode = Literal["physical", "simulated"]

# Module-level empty defaults (built once)
_EMPTY_SESSION = build_empty_session()
_EMPTY_SIGNAL = _EMPTY_SESSION.signal
_EMPTY_TRANSFER = _EMPTY_SESSION.latest_transfer


@dataclass
class RXAppState:
    """Observable state store with physical/simulated mode.

    - physical: reads real data from ESP32 via serial (RXPhysicalBackend).
    - simulated: generates all data from virtual channel model (RXSimulationBackend).
    """

    settings: AppSettings = field(default_factory=load_settings)
    session: SessionState = field(default_factory=build_empty_session)
    signal: SignalState = field(default=_EMPTY_SIGNAL)
    transfer: TransferRecord = field(default=_EMPTY_TRANSFER)
    activity_log: list[dict[str, str]] = field(default_factory=list)
    using_mock_data: bool = True
    serial_connected: bool = False
    mode: AppMode = "physical"
    expected_file_path: str | None = None
    expected_file_data: bytes | None = None
    current_capture: SessionCapture | None = None
    _subscribers: list[StateSubscriber] = field(default_factory=list, init=False, repr=False)
    _lock: __import__("threading").Lock = field(default_factory=__import__("threading").Lock, init=False, repr=False)

    # Backend instances (initialized lazily, default to None)
    _physical: RXPhysicalBackend | None = field(default=None, init=False, repr=False)
    _simulation: RXSimulationBackend | None = field(default=None, init=False, repr=False)

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

    def set_mode(self, mode: AppMode) -> None:
        """Switch between physical and simulated mode, then refresh."""
        if mode == self.mode:
            return
        # If switching away from simulation, stop/cleanup first
        with self._lock:
            if self.mode == "simulated" and self._simulation:
                self._simulation.cleanup()
                self._simulation = None
            self.mode = mode
        self._refresh()
        self.notify()

    def update_simulation_params(self, **kwargs: Any) -> None:
        """Safely update simulation backend parameters and notify subscribers."""
        with self._lock:
            if self._simulation is None:
                self._simulation = RXSimulationBackend()
                if self.expected_file_data is not None:
                    self._simulation.set_expected_file(self.expected_file_data, self.expected_file_path)
            self._simulation.set_params(**kwargs)
            mode = self.mode
        if mode == "simulated":
            self._refresh()
            self.notify()

    def load_expected_file(self, filepath: str) -> None:
        """Load expected/original reference file bytes for BER comparison."""
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            with self._lock:
                self.expected_file_data = data
                self.expected_file_path = filepath
                if self._simulation:
                    self._simulation.set_expected_file(self.expected_file_data, self.expected_file_path)
            self._refresh()
            self.notify()
        except Exception:
            pass

    def clear_expected_file(self) -> None:
        """Clear the loaded expected/original reference file."""
        with self._lock:
            self.expected_file_path = None
            self.expected_file_data = None
            if self._simulation:
                self._simulation.set_expected_file(None, None)
        self._refresh()
        self.notify()

    def send_firmware_command(self, cmd: str) -> bool:
        """Send command to physical firmware if active."""
        with self._lock:
            mode = self.mode
            physical = self._physical
        if mode == "physical" and physical:
            return physical.send_command(cmd)
        return False

    def _refresh(self) -> None:
        """Refresh state by delegating to the active backend."""
        with self._lock:
            mode = self.mode
        if mode == "simulated":
            if self._simulation is None:
                self._simulation = RXSimulationBackend()
                if self.expected_file_data is not None:
                    self._simulation.set_expected_file(self.expected_file_data, self.expected_file_path)
            snap = self._simulation.refresh() if self._simulation else None
            with self._lock:
                if snap:
                    self._apply_sim_snapshot(snap)
                else:
                    self._load_empty()
        else:
            if self._physical is None:
                self._physical = RXPhysicalBackend()
            snap = self._physical.refresh() if self._physical else None
            with self._lock:
                if snap and snap.serial_connected:
                    self._apply_phy_snapshot(snap)
                else:
                    self._load_empty()

    def _apply_phy_snapshot(self, s: RXPhysicalSnapshot) -> None:
        self.session = s.session
        self.signal = s.session.signal
        self.transfer = s.transfer
        self.activity_log = s.activity_log[-500:]
        self.serial_connected = True
        self.using_mock_data = False

    def _apply_sim_snapshot(self, s: RXSimulationSnapshot) -> None:
        self.session = s.session
        self.signal = s.session.signal
        self.transfer = s.transfer
        self.activity_log = s.activity_log[-500:]
        self.serial_connected = getattr(self._simulation, "_tx_connected", False)
        self.using_mock_data = True

    def _load_empty(self) -> None:
        import time
        now = time.strftime("%H:%M:%S")
        self.session = _EMPTY_SESSION
        self.signal = _EMPTY_SIGNAL
        self.transfer = _EMPTY_TRANSFER
        self.activity_log = [
            {"time": now, "event": "Offline", "details": "No hardware connected"},
            {"time": now, "event": "Tip", "details": "Switch to Simulation mode for virtual data"},
        ]
        self.using_mock_data = True
        self.serial_connected = False

    def refresh(self) -> None:
        """Public refresh — called by QTimer."""
        self._refresh()

        current_tid = self.session.latest_transfer.tid if (self.session and self.session.latest_transfer) else 0
        if current_tid != self._last_tid:
            self._last_tid = current_tid
            self.current_capture = None
            if self.mode == "physical":
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
                        ber=self.signal.ber,
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
            if self._simulation:
                try:
                    self._simulation.cleanup()
                except Exception:
                    pass
                self._simulation = None

    def get_new_simulation_samples(self, last_idx: int) -> list[tuple[float, float, float, int]]:
        """Get new simulation samples from simulation backend, if available."""
        with self._lock:
            if not self._simulation:
                return []
            return self._simulation.get_new_samples(last_idx)


def build_default_state() -> RXAppState:
    return RXAppState()
