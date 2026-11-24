from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gui_dev_v3 import app_state as rx_state_module
from gui_dev_v3 import settings as settings_module
from gui_dev_v3 import tx_app_state as tx_state_module
from gui_dev_v3.data.session import build_empty_session
from gui_dev_v3.rx.backends.simulation import RXSimulationSnapshot, VirtualChannelParams
from gui_dev_v3.settings import OperatingModeSelector, SettingsManager
from gui_dev_v3.tx_app_state import TXAppState
from gui_dev_v3.app_state import RXAppState


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    def open_settings(app_name, scope):
        return QSettings(str(tmp_path / f"{scope}.ini"), QSettings.Format.IniFormat)

    open_settings.Status = QSettings.Status
    monkeypatch.setattr(settings_module, "QSettings", open_settings)


def _tx_snapshot(connected=True):
    return SimpleNamespace(
        filename="No file",
        filetype="—",
        file_size_bytes=0,
        total_chunks=0,
        chunk_size=256,
        encoding="4B5B",
        modulation="NRZ-OOK",
        symbol_rate="15 kHz",
        led_pin=5,
        tx_power="12 W",
        pre_emphasis="Off",
        status_text="Ready to transmit",
        progress_percent=0,
        current_chunk=0,
        elapsed_time="00:00:00",
        estimated_time="00:00:00",
        data_rate="0 bps",
        port="—",
        serial_connected=connected,
        activity_log=[],
        record_count=0,
        tid=0,
        channel_params={},
    )


class FakeTXPhysical:
    instances = []

    def __init__(self):
        self.cleaned = False
        self.started = None
        self.connected_port = None
        self.__class__.instances.append(self)

    def refresh(self):
        return None

    def cleanup(self):
        self.cleaned = True

    def connect(self, port, force=False):
        self.connected_port = port
        return True

    def start_transmission(self, filepath):
        self.started = filepath

    def send_command(self, command):
        return False


class FakeTXSimulation:
    instances = []

    def __init__(self):
        self.stopped = False
        self.started = None
        self.params = {}
        self.__class__.instances.append(self)

    def refresh(self):
        return _tx_snapshot()

    def stop(self):
        self.stopped = True

    def start_transmission(self, filepath):
        self.started = filepath

    def set_params(self, **kwargs):
        self.params.update(kwargs)


def _rx_snapshot(tid=0):
    session = build_empty_session()
    transfer = replace(session.latest_transfer, tid=tid)
    return RXSimulationSnapshot(
        session=replace(session, latest_transfer=transfer),
        transfer=transfer,
        activity_log=[],
        channel_params=VirtualChannelParams(),
    )


class FakeRXPhysical:
    instances = []

    def __init__(self):
        self.cleaned = False
        self.connected_port = None
        self.__class__.instances.append(self)

    def refresh(self):
        return None

    def cleanup(self):
        self.cleaned = True

    def connect(self, port, force=False):
        self.connected_port = port
        return True

    def send_command(self, command):
        return False


class FakeRXSimulation:
    instances = []

    def __init__(self):
        self.cleaned = False
        self.expected_file = None
        self.params = {}
        self.__class__.instances.append(self)

    @property
    def _tx_connected(self):
        return True

    def refresh(self):
        return _rx_snapshot()

    def cleanup(self):
        self.cleaned = True

    def set_expected_file(self, data, filepath):
        self.expected_file = (data, filepath)

    def set_params(self, **kwargs):
        self.params.update(kwargs)

    def get_new_samples(self, last_idx):
        return [(0.1, 1.2, 0.8, 1)]


def test_tx_mode_switch_isolates_physical_and_simulation_backends(monkeypatch):
    FakeTXPhysical.instances.clear()
    FakeTXSimulation.instances.clear()
    monkeypatch.setattr(tx_state_module, "TXPhysicalBackend", FakeTXPhysical)
    monkeypatch.setattr(tx_state_module, "TXSimulationBackend", FakeTXSimulation)

    state = TXAppState()
    physical = state._physical
    state.set_mode("simulated")
    simulation = state._simulation

    assert physical.cleaned is True
    assert state.mode == "simulated"
    assert state.using_mock_data is True
    assert state.serial_connected is True
    assert state._physical is None
    assert simulation is not None

    state.start_transmission("sample.bin")
    assert simulation.started == "sample.bin"

    state.set_mode("physical")
    assert simulation.stopped is True
    assert state.mode == "physical"
    assert state.using_mock_data is False
    assert state._simulation is None
    assert state._physical is not None
    state.cleanup()


def test_rx_mode_switch_and_reference_file_are_simulation_only(monkeypatch, tmp_path):
    FakeRXPhysical.instances.clear()
    FakeRXSimulation.instances.clear()
    monkeypatch.setattr(rx_state_module, "RXPhysicalBackend", FakeRXPhysical)
    monkeypatch.setattr(rx_state_module, "RXSimulationBackend", FakeRXSimulation)

    state = RXAppState()
    physical = state._physical
    reference = tmp_path / "reference.bin"
    reference.write_bytes(b"reference payload")

    state.set_mode("simulated")
    simulation = state._simulation
    assert physical.cleaned is True
    assert state.mode == "simulated"
    assert state.using_mock_data is True
    assert state.serial_connected is True
    assert state._physical is None

    state.load_expected_file(str(reference))
    assert simulation.expected_file == (b"reference payload", str(reference))
    state.update_simulation_params(distance_m=2.5, packet_loss_pct=3.0)
    assert simulation.params == {"distance_m": 2.5, "packet_loss_pct": 3.0}
    assert state.get_new_simulation_samples(0) == [(0.1, 1.2, 0.8, 1)]
    assert state.send_firmware_command("RESET") is False

    state.set_mode("physical")
    assert simulation.cleaned is True
    assert state.mode == "physical"
    assert state.using_mock_data is False
    assert state._simulation is None
    assert state._physical is not None
    state.cleanup()


def test_operating_mode_selector_persists_and_switches_backend(monkeypatch, qapp):
    FakeTXPhysical.instances.clear()
    FakeTXSimulation.instances.clear()
    monkeypatch.setattr(tx_state_module, "TXPhysicalBackend", FakeTXPhysical)
    monkeypatch.setattr(tx_state_module, "TXSimulationBackend", FakeTXSimulation)

    manager = SettingsManager("tx")
    assert manager.set("general/mode", "physical")
    state = TXAppState()
    selector = OperatingModeSelector(manager, state=state)

    selector.combo.setCurrentIndex(selector.combo.findData("simulated"))
    qapp.processEvents()
    assert state.mode == "simulated"
    assert manager.get("general/mode") == "simulated"

    selector.combo.setCurrentIndex(selector.combo.findData("physical"))
    qapp.processEvents()
    assert state.mode == "physical"
    assert manager.get("general/mode") == "physical"

    selector.close()
    state.cleanup()


def test_local_udp_simulation_backends_transfer_original_bytes(qapp, tmp_path):
    from PySide6.QtCore import QEventLoop, QTimer
    from gui_dev_v3.rx.backends.simulation import RXSimulationBackend
    from gui_dev_v3.tx.backends.simulation import TXSimulationBackend

    rx = RXSimulationBackend()
    tx = TXSimulationBackend()
    rx.set_params(packet_loss_pct=0, distance_m=0.1, noise_floor_mv=0)
    tx.set_params(packet_loss_pct=0)
    assert SettingsManager("rx").set("general/default_export_folder", str(tmp_path))
    source = tmp_path / "reference.bin"
    payload = bytes(range(256)) + b"OpenVLC"
    source.write_bytes(payload)
    rx.set_expected_file(payload, str(source))
    try:
        assert rx._socket is not None
        assert tx._socket is not None
        assert rx._socket.localPort() == 9901
        assert tx._socket.localPort() == 9902

        loop = QEventLoop()
        QTimer.singleShot(1800, loop.quit)
        loop.exec()

        idle = tx.refresh()
        assert idle.serial_connected is True
        assert idle.filename == "No file"
        assert idle.file_size_bytes == idle.total_chunks == 0
        assert rx._tx_connected is True
        assert rx.get_new_samples(0)

        tx.start_transmission(str(source))
        QTimer.singleShot(800, loop.quit)
        loop.exec()

        assert tx.refresh().file_size_bytes == len(payload)
        transfer = rx.refresh().transfer
        received = Path(transfer.received_path)
        assert received.parent == tmp_path / "simulation"
        assert received.read_bytes() == payload
        assert transfer.quality.crc_status == "PASS"
    finally:
        tx.stop()
        rx.cleanup()
        qapp.processEvents()


def test_simulated_rx_never_loads_physical_capture_with_matching_tid(monkeypatch):
    from gui_dev_v3 import data

    class SimulationWithTransfer(FakeRXSimulation):
        def refresh(self):
            return _rx_snapshot(tid=42)

    def load_physical_capture(tid):
        pytest.fail(f"Tried to load physical capture {tid} from simulation")

    monkeypatch.setattr(rx_state_module, "RXSimulationBackend", SimulationWithTransfer)
    monkeypatch.setattr(data, "load_session_capture", load_physical_capture)
    state = RXAppState(mode="simulated")
    try:
        state.refresh()
        assert state.transfer.tid == 42
        assert state.current_capture is None
    finally:
        state.cleanup()
