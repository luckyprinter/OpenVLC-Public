"""TX Application state — delegates to Physical or Simulation backend.

Modes:
  - "physical": reads real data from ESP32 hardware via serial.
  - "simulated": generates all data from virtual channel model (no hardware).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Any

from gui_dev_v3.settings_store import AppSettings, load_settings
from gui_dev_v3.models import SessionCapture
from gui_dev_v3.tx.backends.physical import TXPhysicalBackend, TXPhysicalSnapshot
from gui_dev_v3.tx.backends.simulation import TXSimulationBackend, TXSimulationSnapshot

TXStateSubscriber = Callable[["TXAppState"], None]

POLL_INTERVAL_MS = 1000

AppMode = Literal["physical", "simulated"]


@dataclass
class TXAppState:
    """Observable TX state store with physical/simulated mode.

    - physical: reads real data from ESP32 via serial (TXPhysicalBackend).
    - simulated: generates all data from virtual channel model (TXSimulationBackend).
    """

    settings: AppSettings = field(default_factory=load_settings)
    filename: str = "No file"
    filetype: str = ""
    file_size_bytes: int = 0
    total_chunks: int = 0
    chunk_size: int = 256
    encoding: str = "4B5B"
    modulation: str = "NRZ / OOK"
    symbol_rate: str = "15,000 sym/s"
    led_pin: int = 25
    tx_power: str = "100 %"
    pre_emphasis: str = "Disabled"
    status_text: str = "Offline — no hardware"
    progress_percent: int = 0
    current_chunk: int = 0
    elapsed_time: str = "00:00:00"
    estimated_time: str = "00:00:00"
    data_rate: str = "0 bps"
    port: str = "—"
    serial_connected: bool = False
    activity_log: list[dict[str, str]] = field(default_factory=list)
    using_mock_data: bool = True
    record_count: int = 0
    tid: int = 0
    mode: AppMode = "physical"
    current_capture: SessionCapture | None = None
    transmission_queue: list[dict[str, Any]] = field(default_factory=list)
    session_history: list[dict[str, Any]] = field(default_factory=list)
    _subscribers: list[TXStateSubscriber] = field(default_factory=list, init=False, repr=False)
    _lock: __import__("threading").Lock = field(default_factory=__import__("threading").Lock, init=False, repr=False)

    # Backend instances (initialized lazily, default to None)
    _physical: TXPhysicalBackend | None = field(default=None, init=False, repr=False)
    _simulation: TXSimulationBackend | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._last_status_text = ""
        self._refresh()

    def subscribe(self, callback: TXStateSubscriber) -> None:
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: TXStateSubscriber) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def notify(self) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for callback in subs:
            callback(self)

    def set_mode(self, mode: AppMode) -> None:
        """Switch between physical and simulated mode, then refresh."""
        if mode == self.mode:
            return
        # If switching away from simulation, stop first
        with self._lock:
            if self.mode == "simulated" and self._simulation:
                self._simulation.stop()
                self._simulation = None
            self.mode = mode
        self._refresh()
        self.notify()

    def _refresh(self) -> None:
        """Refresh state by delegating to the active backend."""
        with self._lock:
            mode = self.mode
        if mode == "simulated":
            if self._simulation is None:
                self._simulation = TXSimulationBackend()
            snap = self._simulation.refresh() if self._simulation else None
            with self._lock:
                if snap:
                    self._apply_sim_snapshot(snap)
                else:
                    self._load_empty()
        else:
            if self._physical is None:
                self._physical = TXPhysicalBackend()
            snap = self._physical.refresh() if self._physical else None
            with self._lock:
                if snap and snap.serial_connected:
                    self._apply_phy_snapshot(snap)
                else:
                    self._load_empty()

        # Check for status transitions and insert completion/failure to history
        if hasattr(self, "status_text") and self.status_text:
            if self._last_status_text != self.status_text:
                if self.filename and self.filename not in ("No file", "No file transfer"):
                    import time
                    if "complete" in self.status_text.lower():
                        self.session_history.insert(0, {
                            "time": time.strftime("%H:%M:%S"),
                            "file": self.filename,
                            "throughput": self.data_rate,
                            "outcome": "SUCCESS",
                            "chunks": f"{self.total_chunks}/{self.total_chunks}",
                            "duration": f"{self.elapsed_time}"
                        })
                    elif "failed" in self.status_text.lower():
                        self.session_history.insert(0, {
                            "time": time.strftime("%H:%M:%S"),
                            "file": self.filename,
                            "throughput": self.data_rate,
                            "outcome": "FAILED",
                            "chunks": f"{self.current_chunk}/{self.total_chunks}",
                            "duration": f"{self.elapsed_time}"
                        })
                self._last_status_text = self.status_text

    def _apply_phy_snapshot(self, s: TXPhysicalSnapshot) -> None:
        self.filename = s.filename
        self.filetype = s.filetype
        self.file_size_bytes = s.file_size_bytes
        self.total_chunks = s.total_chunks
        self.chunk_size = s.chunk_size
        self.encoding = s.encoding
        self.modulation = s.modulation
        self.symbol_rate = s.symbol_rate
        self.led_pin = s.led_pin
        self.tx_power = s.tx_power
        self.pre_emphasis = s.pre_emphasis
        self.status_text = s.status_text
        self.progress_percent = s.progress_percent
        self.current_chunk = s.current_chunk
        self.elapsed_time = s.elapsed_time
        self.estimated_time = s.estimated_time
        self.data_rate = s.data_rate
        self.port = s.port
        self.serial_connected = True
        
        # Limit activity log
        self.activity_log = s.activity_log[-500:]
        self.record_count = s.record_count
        self.tid = getattr(s, 'tid', 0)
        self.using_mock_data = False

    def _apply_sim_snapshot(self, s: TXSimulationSnapshot) -> None:
        self.filename = s.filename
        self.filetype = s.filetype
        self.file_size_bytes = s.file_size_bytes
        self.total_chunks = s.total_chunks
        self.chunk_size = s.chunk_size
        self.encoding = s.encoding
        self.modulation = s.modulation
        self.symbol_rate = s.symbol_rate
        self.led_pin = s.led_pin
        self.tx_power = s.tx_power
        self.pre_emphasis = s.pre_emphasis
        self.status_text = s.status_text
        self.progress_percent = s.progress_percent
        self.current_chunk = s.current_chunk
        self.elapsed_time = s.elapsed_time
        self.estimated_time = s.estimated_time
        self.data_rate = s.data_rate
        self.port = "—"  # no serial port in simulation
        self.serial_connected = getattr(self._simulation, "_rx_connected", False)
        
        # Limit activity log
        self.activity_log = s.activity_log[-500:]
        self.record_count = s.record_count
        self.tid = getattr(s, 'tid', 0)
        self.using_mock_data = True

    def _load_empty(self) -> None:
        import time
        now = time.strftime("%H:%M:%S")
        self.filename = "No file"
        self.filetype = ""
        self.file_size_bytes = 0
        self.total_chunks = 0
        self.chunk_size = 256
        self.encoding = "4B5B"
        self.modulation = "NRZ / OOK"
        self.symbol_rate = "15,000 sym/s"
        self.led_pin = 25
        self.tx_power = "100 %"
        self.pre_emphasis = "Disabled"
        self.status_text = "Offline — no hardware"
        self.progress_percent = 0
        self.current_chunk = 0
        self.elapsed_time = "00:00:00"
        self.estimated_time = "00:00:00"
        self.data_rate = "0 bps"
        self.port = "—"
        self.serial_connected = False
        self.activity_log = [
            {"time": now, "event": "Offline", "details": "No hardware connected"},
            {"time": now, "event": "Tip", "details": "Switch to Simulation mode for virtual data"},
        ]
        self.using_mock_data = True
        self.record_count = 0

    def update_simulation_params(self, **kwargs: Any) -> None:
        """Safely update simulation backend parameters and notify subscribers."""
        with self._lock:
            if self._simulation is None:
                self._simulation = TXSimulationBackend()
            self._simulation.set_params(**kwargs)
            mode = self.mode
        if mode == "simulated":
            self._refresh()
            self.notify()

    def start_transmission(self, filepath: str) -> None:
        """Start transmitting a file in simulated or physical mode."""
        with self._lock:
            mode = self.mode
            if mode == "simulated":
                if self._simulation is None:
                    self._simulation = TXSimulationBackend()
                self._simulation.start_transmission(filepath)
            elif mode == "physical":
                if self._physical is None:
                    self._physical = TXPhysicalBackend()
                self._physical.start_transmission(filepath)
                
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

    def refresh(self) -> None:
        self._refresh()

        if self.current_capture is None and self.tid > 0:
            from gui_dev_v3.data import load_session_capture
            loaded = load_session_capture(self.tid)
            if loaded:
                self.current_capture = loaded
                print(f"TX loaded completed capture session for TID {self.tid}")

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
                    self._simulation.stop()
                except Exception:
                    pass
                self._simulation = None


def build_default_tx_state() -> TXAppState:
    return TXAppState()
