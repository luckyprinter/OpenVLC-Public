from types import SimpleNamespace

from gui_dev_v3 import app_state as rx_state_module
from gui_dev_v3 import tx_app_state as tx_state_module
from gui_dev_v3.data.session import build_empty_session
from gui_dev_v3.settings import OperatingModeSelector, SettingsManager
from gui_dev_v3.tx_app_state import TXAppState
from gui_dev_v3.app_state import RXAppState


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


def _rx_snapshot(connected=True):
    session = build_empty_session()
    return SimpleNamespace(
        session=session,
        transfer=session.latest_transfer,
        activity_log=[],
        channel_params={},
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
