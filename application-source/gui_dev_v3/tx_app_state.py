"""Transmitter application state backed exclusively by physical ESP32 hardware."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gui_dev_v3.settings_store import AppSettings, load_settings
from gui_dev_v3.models import SessionCapture
from gui_dev_v3.tx.backends.physical import TXPhysicalBackend, TXPhysicalSnapshot
from gui_dev_v3.tx.backends.simulation import TXSimulationBackend, TXSimulationSnapshot

TXStateSubscriber = Callable[["TXAppState"], None]

POLL_INTERVAL_MS = 1000



@dataclass
class TXAppState:
    """Observable transmitter state populated by the physical ESP32 backend."""

    settings: AppSettings = field(default_factory=load_settings)
    mode: str = "physical"
    filename: str = "No file"
    filetype: str = ""
    file_size_bytes: int = 0
    total_chunks: int = 0
    chunk_size: int = 256
    encoding: str = "4B5B"
    modulation: str = "NRZ / OOK"
    symbol_rate: str = "15,000 sym/s"
    led_pin: int = 5
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
    record_count: int = 0
    tid: int = 0
    current_capture: SessionCapture | None = None
    using_mock_data: bool = False
    transmission_queue: list[dict[str, Any]] = field(default_factory=list)
    session_history: list[dict[str, Any]] = field(default_factory=list)
    _subscribers: list[TXStateSubscriber] = field(default_factory=list, init=False, repr=False)
    _lock: __import__("threading").Lock = field(default_factory=__import__("threading").Lock, init=False, repr=False)

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

    def set_mode(self, mode: str) -> None:
        """Switch between isolated physical and simulated TX backends."""
        if mode not in {"physical", "simulated"}:
            raise ValueError(f"Unsupported TX mode: {mode}")
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
            self._last_status_text = ""
        if old_physical is not None:
            old_physical.cleanup()
        if old_simulation is not None:
            old_simulation.stop()
        self._refresh()
        self.notify()

    def _refresh(self) -> None:
        """Refresh state from the currently selected backend."""
        with self._lock:
            mode = self.mode
        if mode == "simulated":
            if self._simulation is None:
                self._simulation = TXSimulationBackend()
            snapshot = self._simulation.refresh()
            with self._lock:
                self._apply_sim_snapshot(snapshot)
        else:
            if self._physical is None:
                self._physical = TXPhysicalBackend()
            snapshot = self._physical.refresh()
            with self._lock:
                if snapshot:
                    self._apply_phy_snapshot(snapshot)
                else:
                    self._load_empty()

        if hasattr(self, "status_text") and self.status_text:
            if self._last_status_text != self.status_text:
                if self.filename and self.filename not in ("No file", "No file transfer"):
                    import time
                    if "complete" in self.status_text.lower():
                        self.session_history.insert(0, {"time": time.strftime("%H:%M:%S"), "file": self.filename, "throughput": self.data_rate, "outcome": "SUCCESS", "chunks": f"{self.total_chunks}/{self.total_chunks}", "duration": f"{self.elapsed_time}"})
                    elif "failed" in self.status_text.lower():
                        self.session_history.insert(0, {"time": time.strftime("%H:%M:%S"), "file": self.filename, "throughput": self.data_rate, "outcome": "FAILED", "chunks": f"{self.current_chunk}/{self.total_chunks}", "duration": f"{self.elapsed_time}"})
                self._last_status_text = self.status_text

    def _apply_phy_snapshot(self, s: TXPhysicalSnapshot) -> None:
        _snap_status = s.status_text or ""
        _is_idle = _snap_status.strip().lower() in ("idle:", "idle", "connected:", "") or _snap_status.startswith("Idle:") or _snap_status.startswith("Connected:")
        _is_transmitting = s.filename not in ("No file", "", None) and not _is_idle
        if _is_transmitting:
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
        if not _is_idle:
            self.status_text = _snap_status
        self.progress_percent = s.progress_percent
        self.current_chunk = s.current_chunk
        if _is_transmitting:
            self.elapsed_time = s.elapsed_time
            self.estimated_time = s.estimated_time
        self.data_rate = s.data_rate
        self.port = s.port
        self.serial_connected = s.serial_connected
        for log_item in s.activity_log:
            if self.activity_log:
                last_log = self.activity_log[0]
                if last_log["event"] == log_item["event"] and last_log["details"] == log_item["details"]:
                    continue
            if log_item not in self.activity_log:
                self.activity_log.insert(0, log_item)
        self.activity_log = self.activity_log[:500]
        self.record_count = s.record_count
        self.tid = getattr(s, 'tid', 0)

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
        self.port = "—"
        self.serial_connected = bool(getattr(self._simulation, "_rx_connected", False))
        self.activity_log = s.activity_log[-500:]
        self.record_count = s.record_count
        self.tid = s.tid
        self.using_mock_data = True

    def _load_empty(self) -> None:
        self.filename = "No file"
        self.filetype = ""
        self.file_size_bytes = 0
        self.total_chunks = 0
        self.chunk_size = 256
        self.encoding = "4B5B"
        self.modulation = "NRZ / OOK"
        self.symbol_rate = "15,000 sym/s"
        self.led_pin = 5
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
        self.record_count = 0
        self.using_mock_data = self.mode == "simulated"

    def update_simulation_params(self, **kwargs: Any) -> None:
        """Update virtual-channel parameters without opening a serial port."""
        if self._simulation is None:
            self._simulation = TXSimulationBackend()
        self._simulation.set_params(**kwargs)
        if self.mode == "simulated":
            self._refresh()
            self.notify()

    def start_transmission(self, filepath: str) -> None:
        """Start a file transmission through the selected backend."""
        if self.mode == "simulated":
            if self._simulation is None:
                self._simulation = TXSimulationBackend()
            self._simulation.start_transmission(filepath)
        else:
            if self._physical is None:
                self._physical = TXPhysicalBackend()
            self._physical.start_transmission(filepath)
        self._refresh()
        self.notify()

    def send_firmware_command(self, cmd: str) -> bool:
        """Send a raw command to physical firmware if active."""
        with self._lock:
            physical = self._physical if self.mode == "physical" else None
        if physical:
            return physical.send_command(cmd)
        return False

    def is_dma_capable(self) -> bool:
        """Return True when connected firmware reports DMA capability."""
        with self._lock:
            physical = self._physical if self.mode == "physical" else None
        if physical and hasattr(physical, "_controller"):
            return physical._controller.dma_capable
        return False

    def apply_link_settings_from_ui(self, freq: int, preamble: int, gap: int, fgap: int, active_low: bool, idle_on: bool, intensity: int, quiet: bool, dma_mode: bool) -> bool:
        """Apply TX link settings and report whether all serial writes succeeded."""
        with self._lock:
            mode = self.mode
            physical = self._physical
        if mode == "simulated":
            self.update_simulation_params(
                symbol_hz=freq,
                preamble_bits=preamble,
                post_frame_idle_ms=gap,
                frame_gap_ms=fgap,
                active_low=active_low,
                idle_on=idle_on,
                cal_intensity_pct=intensity,
                quiet_mode=quiet,
            )
            return True
        if physical is None:
            return False
        ctrl = getattr(physical, "_controller", None)
        if ctrl is None or not ctrl.is_connected:
            return False
        if not ctrl.apply_4b5b_settings(freq=freq, gap=gap, fgap=fgap, active_low=active_low, idle_on=idle_on, quiet=quiet):
            return False
        return physical.send_command(f"INTENSITY={intensity}")

    def force_connect_serial(self, port: str) -> bool:
        """Force connect physical backend to a port, bypassing detection."""
        if self.mode != "physical":
            self.set_mode("physical")
        with self._lock:
            if self._physical is None:
                self._physical = TXPhysicalBackend()
            res = self._physical.connect(port, force=True)
        self._refresh()
        self.notify()
        return res

    def refresh(self) -> None:
        self._refresh()
        if self.mode == "physical" and self.current_capture is None and self.tid > 0:
            from gui_dev_v3.data import load_session_capture
            loaded = load_session_capture(self.tid)
            if loaded:
                self.current_capture = loaded
                print(f"TX loaded completed capture session for TID {self.tid}")
        self.notify()

    def rebuild_backends(self) -> None:
        """Recreate backend instances."""
        self.cleanup()

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
                simulation.stop()
            except Exception:
                pass



def build_default_tx_state(mode: str = "physical") -> TXAppState:
    return TXAppState(mode=mode)
