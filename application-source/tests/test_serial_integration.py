"""Mock serial integration tests for independent TX/RX ESP32 connections.

These tests exercise the host-side serial lifecycle without optical hardware.
They do not emulate USB drivers, ESP32 reset circuitry, or firmware timing.
"""
from __future__ import annotations

import multiprocessing
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from gui_dev_v3.serial.session import SerialSession


class FakeSerialPort:
    def __init__(
        self,
        registry: "FakeSerialRegistry",
        port: str | None = None,
        baudrate: int | None = None,
        timeout: float | None = None,
        **_kwargs: Any,
    ) -> None:
        self.registry = registry
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.dtr: bool | None = None
        self.rts: bool | None = None
        self.exclusive: bool | None = None
        self.is_open = False
        self._responses: list[bytes] = []

    def open(self) -> None:
        self._responses = list(
            self.registry.responses.get((self.port, self.baudrate), [])
        )
        if self.port in self.registry.fail_ports:
            raise OSError(f"mock port {self.port} is busy")
        with self.registry.lock:
            if self.port in self.registry.open_ports:
                raise OSError(f"mock port {self.port} is already open")
            self.registry.open_ports.add(self.port)
            self.registry.opens.append((self.port, self.baudrate, self.dtr, self.rts, self.exclusive))
        self.is_open = True

    def close(self) -> None:
        with self.registry.lock:
            self.registry.open_ports.discard(self.port)
        self.is_open = False

    def write(self, data: bytes) -> int:
        if self.port in self.registry.write_errors:
            raise OSError("mock serial write failed")
        with self.registry.lock:
            self.registry.active_writes += 1
            self.registry.max_active_writes = max(
                self.registry.max_active_writes, self.registry.active_writes
            )
        try:
            time.sleep(0.01)
            if data == b"\n" and not self._responses:
                if self.baudrate == 115200:
                    self._responses.append(b"TX Ready\n")
                elif self.baudrate == 460800:
                    self._responses.append(b"RX Ready\n")
            with self.registry.lock:
                self.registry.writes.append((self.port, data))
        finally:
            with self.registry.lock:
                self.registry.active_writes -= 1
        return len(data)

    def readline(self) -> bytes:
        time.sleep(0.002)
        if self.port in self.registry.read_errors:
            raise OSError("mock USB serial device removed")
        return self._responses.pop(0) if self._responses else b""

    def reset_input_buffer(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


class FakeSerialRegistry:
    def __init__(self, fail_ports: set[str] | None = None) -> None:
        self.fail_ports = fail_ports or set()
        self.read_errors: set[str] = set()
        self.write_errors: set[str] = set()
        self.responses: dict[tuple[str | None, int | None], list[bytes]] = {}
        self.open_ports: set[str] = set()
        self.opens: list[tuple[str | None, int | None, bool | None, bool | None, bool | None]] = []
        self.writes: list[tuple[str | None, bytes]] = []
        self.active_writes = 0
        self.max_active_writes = 0
        self.lock = threading.Lock()

    def module(self) -> types.ModuleType:
        module = types.ModuleType("serial")
        module.Serial = lambda *args, **kwargs: self._make(*args, **kwargs)
        module.SerialException = OSError
        return module

    def _make(self, *args: Any, **kwargs: Any) -> FakeSerialPort:
        if args:
            kwargs.setdefault("port", args[0])
        return FakeSerialPort(self, **kwargs)


def _serial_scan_lock_process(lock_path: str, entered, release) -> None:
    from gui_dev_v3.serial import detection

    detection._SERIAL_SCAN_LOCK_PATH = Path(lock_path)
    with detection.serial_scan_lock(timeout=5.0):
        entered.set()
        release.wait(timeout=5.0)


@pytest.fixture
def fake_serial(monkeypatch: pytest.MonkeyPatch) -> FakeSerialRegistry:
    registry = FakeSerialRegistry()
    monkeypatch.setitem(sys.modules, "serial", registry.module())
    monkeypatch.setattr(
        "gui_dev_v3.serial.session.write_status", lambda *_args, **_kwargs: None
    )
    return registry


def test_tx_and_rx_sessions_can_open_distinct_ports_concurrently(fake_serial):
    tx = SerialSession("tx")
    rx = SerialSession("rx")

    with ThreadPoolExecutor(max_workers=2) as pool:
        tx_future = pool.submit(tx.connect, "MOCK_TX")
        rx_future = pool.submit(rx.connect, "MOCK_RX")
        assert tx_future.result(timeout=2) is True
        assert rx_future.result(timeout=2) is True

    assert tx.is_connected
    assert rx.is_connected
    assert {entry[0]: entry[1] for entry in fake_serial.opens} == {
        "MOCK_TX": 115200,
        "MOCK_RX": 460800,
    }
    # The shared session explicitly suppresses DTR/RTS reset signaling.
    assert all(entry[2:] == (False, False, True) for entry in fake_serial.opens)

    tx.disconnect()
    rx.disconnect()
    assert not tx.is_connected
    assert not rx.is_connected
    assert fake_serial.open_ports == set()


def test_tx_reader_marks_connection_lost_after_unplug(fake_serial, monkeypatch):
    session = SerialSession("tx")

    assert session.connect("MOCK_TX") is True
    persisted_status = []
    monkeypatch.setattr(
        "gui_dev_v3.serial.session.write_status",
        lambda role, payload: persisted_status.append((role, dict(payload))),
    )
    fake_serial.read_errors.add("MOCK_TX")

    deadline = time.monotonic() + 1.0
    while session.is_connected and time.monotonic() < deadline:
        time.sleep(0.005)

    assert session.is_connected is False
    assert session.serial_obj is None
    assert fake_serial.open_ports == set()
    assert persisted_status == [
        (
            "tx",
            {
                "role": "tx",
                "stage": "Connection Lost",
                "detail": "OSError",
                "state": "error",
            },
        )
    ]
    session.disconnect()


def test_tx_session_serializes_concurrent_writes(fake_serial):
    session = SerialSession("tx")
    assert session.connect("MOCK_TX") is True

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(session.send_line, [f"CMD={i}" for i in range(24)]))

    assert all(results)
    assert fake_serial.max_active_writes == 1
    assert len(fake_serial.writes) == 24
    session.disconnect()


def test_rx_backend_serializes_concurrent_writes(fake_serial):
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    backend = RXPhysicalBackend()
    backend._port = "MOCK_RX"
    assert backend._open_serial() is True
    backend._connected = True

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(backend.send_command, [f"CMD={i}\n" for i in range(24)]))

    assert all(results)
    assert fake_serial.max_active_writes == 1
    backend._close_serial()


def test_tx_settings_apply_reports_serial_write_failure(fake_serial):
    from gui_dev_v3.serial.controllers import TXSerialController

    controller = TXSerialController()
    assert controller.connect("MOCK_TX", expected_role="VLC_TX") is True
    controller._dma_capable = False
    fake_serial.write_errors.add("MOCK_TX")

    assert controller.apply_4b5b_settings() is False
    controller.disconnect()


def test_tx_settings_apply_reports_success_when_all_writes_succeed(fake_serial):
    from gui_dev_v3.serial.controllers import TXSerialController

    controller = TXSerialController()
    assert controller.connect("MOCK_TX", expected_role="VLC_TX") is True
    controller._dma_capable = False

    assert controller.apply_4b5b_settings() is True
    controller.disconnect()


def test_failed_open_never_reports_connected(monkeypatch: pytest.MonkeyPatch):
    registry = FakeSerialRegistry(fail_ports={"MOCK_BUSY"})
    monkeypatch.setitem(sys.modules, "serial", registry.module())
    monkeypatch.setattr(
        "gui_dev_v3.serial.session.write_status", lambda *_args, **_kwargs: None
    )

    session = SerialSession("rx")
    assert session.connect("MOCK_BUSY") is False
    assert session.is_connected is False
    assert session.serial_obj is None
    assert registry.open_ports == set()




def test_connect_reader_start_failure_releases_open_serial_handle(fake_serial, monkeypatch):
    class FailingThread:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            raise RuntimeError("simulated reader startup failure")

        def is_alive(self):
            return False

    monkeypatch.setattr(
        "gui_dev_v3.serial.session.threading.Thread", FailingThread
    )
    session = SerialSession("tx")

    assert session.connect("MOCK_TX") is False
    assert session.is_connected is False
    assert session.serial_obj is None
    assert session._reader_thread is None
    assert fake_serial.open_ports == set()



def test_rx_persistent_open_disables_dtr_and_rts(fake_serial, monkeypatch):
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    monkeypatch.setattr(
        "gui_dev_v3.rx.backends.physical.time.sleep", lambda _seconds: None
    )
    backend = RXPhysicalBackend()
    backend._port = "MOCK_RX"

    assert backend._open_serial() is True
    assert fake_serial.opens == [("MOCK_RX", 460800, False, False, True)]

    backend._close_serial()
    assert fake_serial.open_ports == set()



def test_reconnect_stops_previous_reader_before_opening_new_port(fake_serial):
    session = SerialSession("tx")

    assert session.connect("MOCK_TX_1") is True
    previous_reader = session._reader_thread
    assert previous_reader is not None

    assert session.connect("MOCK_TX_2") is True
    assert previous_reader.is_alive() is False
    assert session.serial_obj.port == "MOCK_TX_2"
    assert fake_serial.open_ports == {"MOCK_TX_2"}

    session.disconnect()
    assert fake_serial.open_ports == set()



def test_tx_and_rx_identification_probes_use_exclusive_non_resetting_open(
    fake_serial, monkeypatch: pytest.MonkeyPatch
):
    from gui_dev_v3.rx.backends.physical import _send_identify as identify_rx
    from gui_dev_v3.tx.backends.physical import _send_identify as identify_tx

    fake_serial.responses[("MOCK_TX", 115200)] = [b"TX Ready\n"]
    fake_serial.responses[("MOCK_RX", 460800)] = [b"RX Ready\n"]
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    assert identify_tx("MOCK_TX", "VLC_TX")["device"] == "VLC_TX"
    assert identify_rx("MOCK_RX", "VLC_RX", 460800)["device"] == "VLC_RX"

    assert fake_serial.open_ports == set()
    assert fake_serial.opens == [
        ("MOCK_TX", 115200, False, False, True),
        ("MOCK_RX", 460800, False, False, True),
    ]



def test_general_role_scanner_probe_uses_safe_exclusive_open(fake_serial):
    from gui_dev_v3.serial.detection import probe_serial_port

    # The scanner probes RX baud first. Keep that attempt neutral so the
    # fake port does not incorrectly impersonate RX before the TX baud probe.
    fake_serial.responses[("MOCK_TX", 460800)] = [b"NO_MATCH\n"] * 6
    fake_serial.responses[("MOCK_TX", 115200)] = [b"TX Ready\n"]

    role, lines = probe_serial_port("MOCK_TX")

    assert role == "tx"
    assert "TX Ready" in lines
    assert fake_serial.opens == [
        ("MOCK_TX", 460800, False, False, True),
        ("MOCK_TX", 115200, False, False, True),
    ]
    assert fake_serial.open_ports == set()


def test_tx_persistent_connection_waits_for_firmware_ready(fake_serial):
    from gui_dev_v3.tx.backends.physical import TXPhysicalBackend

    backend = TXPhysicalBackend()
    backend._port = "MOCK_TX"

    assert backend._open_serial() is True
    assert backend._wait_for_firmware_ready(timeout=0.5) is True

    backend._controller.disconnect()
    assert fake_serial.open_ports == set()


def test_rx_reader_marks_connection_lost_after_unplug(fake_serial, monkeypatch):
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    monkeypatch.setattr("gui_dev_v3.rx.backends.physical.time.sleep", lambda _seconds: None)
    backend = RXPhysicalBackend()
    backend._port = "MOCK_RX"
    backend._record_diag = lambda *_args, **_kwargs: None
    backend.log = lambda *_args, **_kwargs: None

    assert backend._open_serial() is True
    backend._connected = True
    fake_serial.read_errors.add("MOCK_RX")

    deadline = time.monotonic() + 1.0
    while backend.is_connected and time.monotonic() < deadline:
        time.sleep(0.005)

    assert backend.is_connected is False
    assert backend._ser is None
    assert backend._port is None
    assert fake_serial.open_ports == set()
    backend._close_serial()


def test_serial_scan_lock_serializes_separate_processes(tmp_path: Path):
    """TX/RX launched as separate processes must not probe ports concurrently."""
    ctx = multiprocessing.get_context("spawn")
    lock_path = str(tmp_path / "serial_scan.lock")
    first_entered = ctx.Event()
    first_release = ctx.Event()
    second_entered = ctx.Event()
    second_release = ctx.Event()

    first = ctx.Process(
        target=_serial_scan_lock_process,
        args=(lock_path, first_entered, first_release),
    )
    second = ctx.Process(
        target=_serial_scan_lock_process,
        args=(lock_path, second_entered, second_release),
    )
    first.start()
    try:
        assert first_entered.wait(timeout=5.0)
        second.start()
        # The second process must wait while the first owns the OS file lock.
        assert second_entered.wait(timeout=0.25) is False
        first_release.set()
        assert second_entered.wait(timeout=5.0)
    finally:
        first_release.set()
        second_release.set()
        first.join(timeout=5.0)
        if second.pid is not None:
            second.join(timeout=5.0)
        if first.is_alive():
            first.terminate()
            first.join(timeout=2.0)
        if second.is_alive():
            second.terminate()
            second.join(timeout=2.0)

    assert first.exitcode == 0
    assert second.exitcode == 0


def test_serial_reader_dispatches_only_complete_fragmented_lines(fake_serial):
    received: list[str] = []
    completed = threading.Event()
    fake_serial.responses[("MOCK_TX", 115200)] = [
        b"RX_FILE_HEX:17:DATA:",
        b"81920:320:ABCD:66696C652E62696E:",
        b"deadbeef" * 8,
        b"\n",
    ]
    session = SerialSession("tx")
    session.handle_line = lambda line: (received.append(line), completed.set())

    assert session.connect("MOCK_TX") is True
    assert completed.wait(timeout=2.0)
    session.disconnect()

    assert received == [
        "RX_FILE_HEX:17:DATA:81920:320:ABCD:66696C652E62696E:" + ("deadbeef" * 8)
    ]


def test_preferred_serial_port_is_tried_first_without_dropping_fallbacks():
    from gui_dev_v3.serial.detection import prioritize_preferred_port

    assert prioritize_preferred_port(["COM4", "COM7", "COM4"], "COM7") == [
        "COM7", "COM4"
    ]
    assert prioritize_preferred_port(["COM4", "COM7"], "COM9") == [
        "COM4", "COM7"
    ]
    assert prioritize_preferred_port(["COM4", "COM7"], "") == [
        "COM4", "COM7"
    ]


def test_rx_auto_connect_prioritizes_only_rx_saved_port(monkeypatch):
    from gui_dev_v3.settings import SettingsManager
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    monkeypatch.setattr(
        SettingsManager,
        "get",
        lambda self, key, default=None: "RX_PREFERRED" if key == "connection/port" else default,
    )
    saved = []
    monkeypatch.setattr(SettingsManager, "set", lambda self, key, value: saved.append((self.scope, key, value)))
    backend = RXPhysicalBackend()
    attempts = []
    backend.scan_ports = lambda: ["OTHER", "RX_PREFERRED"]
    backend.detect_firmware = lambda port: (
        attempts.append(port) or
        ({"device": "VLC_RX", "firmware": "rx_test", "board": "test"}
         if port == "RX_PREFERRED" else None)
    )
    backend._open_serial = lambda: True
    backend.apply_link_settings = lambda: None
    backend.log = lambda *_args, **_kwargs: None
    backend._record_diag = lambda *_args, **_kwargs: None

    assert backend._auto_connect_locked() is True
    assert attempts == ["RX_PREFERRED"]
    assert backend.port == "RX_PREFERRED"
    assert saved == [("rx", "connection/port", "RX_PREFERRED")]
    backend._connected = False


def test_tx_auto_connect_prioritizes_only_tx_saved_port(monkeypatch):
    from gui_dev_v3.settings import SettingsManager
    from gui_dev_v3.tx.backends.physical import TXPhysicalBackend

    monkeypatch.setattr(
        SettingsManager,
        "get",
        lambda self, key, default=None: "TX_PREFERRED" if key == "connection/port" else default,
    )
    saved = []
    monkeypatch.setattr(SettingsManager, "set", lambda self, key, value: saved.append((self.scope, key, value)))
    backend = TXPhysicalBackend()
    attempts = []
    backend.scan_ports = lambda: ["OTHER", "TX_PREFERRED"]
    backend.detect_firmware = lambda port: (
        attempts.append(port) or
        ({"device": "VLC_TX", "firmware": "tx_test", "board": "test"}
         if port == "TX_PREFERRED" else None)
    )
    backend._open_serial = lambda: True
    backend._wait_for_firmware_ready = lambda: True
    backend.apply_link_settings = lambda: None
    backend.log = lambda *_args, **_kwargs: None
    backend._record_diag = lambda *_args, **_kwargs: None

    assert backend._auto_connect_locked() is True
    assert attempts == ["TX_PREFERRED"]
    assert backend.port == "TX_PREFERRED"
    assert saved == [("tx", "connection/port", "TX_PREFERRED")]
    backend._connected = False



def test_legacy_rx_serial_controller_uses_application_owned_receive_directory(monkeypatch, tmp_path):
    from gui_dev_v3.serial.controllers import RXSerialController

    monkeypatch.setenv("VLC_DATA_DIR", str(tmp_path / "openvlc-data"))
    controller = RXSerialController()

    assert controller._save_dir == tmp_path / "openvlc-data" / "received"



def test_rx_manual_connect_uses_only_the_explicitly_selected_port(monkeypatch):
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    backend = RXPhysicalBackend()
    attempted = []

    def detect(port):
        attempted.append(port)
        return {"device": "VLC_RX", "firmware": "rx_test", "board": "test"}

    backend.scan_ports = lambda: pytest.fail("manual connection must not scan fallback ports")
    backend.detect_firmware = detect
    backend._open_serial = lambda: True
    backend.apply_link_settings = lambda: None
    backend.log = lambda *_args, **_kwargs: None
    backend._record_diag = lambda *_args, **_kwargs: None

    assert backend._connect_locked("MANUAL_RX_PORT") is True
    assert attempted == ["MANUAL_RX_PORT"]
    assert backend.port == "MANUAL_RX_PORT"
    backend.disconnect()


def test_tx_manual_connect_uses_only_the_explicitly_selected_port(monkeypatch):
    from gui_dev_v3.tx.backends.physical import TXPhysicalBackend

    backend = TXPhysicalBackend()
    attempted = []

    def detect(port):
        attempted.append(port)
        return {"device": "VLC_TX", "firmware": "tx_test", "board": "test"}

    backend.scan_ports = lambda: pytest.fail("manual connection must not scan fallback ports")
    backend.detect_firmware = detect
    backend._open_serial = lambda: True
    backend._wait_for_firmware_ready = lambda: True
    backend.apply_link_settings = lambda: None
    backend.log = lambda *_args, **_kwargs: None
    backend._record_diag = lambda *_args, **_kwargs: None

    assert backend._connect_locked("MANUAL_TX_PORT") is True
    assert attempted == ["MANUAL_TX_PORT"]
    assert backend.port == "MANUAL_TX_PORT"
    backend.disconnect()


def test_rx_close_releases_serial_handle_before_joining_reader():
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    backend = RXPhysicalBackend()
    reader_started = threading.Event()
    handle_closed = threading.Event()

    class BlockingReadHandle:
        is_open = True

        def close(self):
            self.is_open = False
            handle_closed.set()

    def reader():
        reader_started.set()
        handle_closed.wait(timeout=5.0)

    backend._ser = BlockingReadHandle()
    backend._reader_thread = threading.Thread(target=reader, daemon=True)
    backend._reader_thread.start()
    assert reader_started.wait(timeout=1.0)

    assert backend._close_serial() is True
    assert handle_closed.is_set()
    assert backend._ser is None
    assert backend._reader_thread is None


def test_rx_auto_connect_falls_back_when_preferred_port_is_busy(monkeypatch):
    from gui_dev_v3.settings import SettingsManager
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    monkeypatch.setattr(
        SettingsManager,
        "get",
        lambda self, key, default=None: "RX_PREFERRED" if key == "connection/port" else default,
    )
    saved = []
    monkeypatch.setattr(
        SettingsManager,
        "set",
        lambda self, key, value: saved.append((self.scope, key, value)),
    )
    backend = RXPhysicalBackend()
    attempts = []
    opened = []
    backend.scan_ports = lambda: ["RX_PREFERRED", "RX_FALLBACK"]
    backend.detect_firmware = lambda port: (
        attempts.append(port)
        or {"device": "VLC_RX", "firmware": "rx_test", "board": "test"}
    )

    def open_selected():
        opened.append(backend.port)
        return backend.port == "RX_FALLBACK"

    backend._open_serial = open_selected
    backend.apply_link_settings = lambda: None
    backend.log = lambda *_args, **_kwargs: None
    backend._record_diag = lambda *_args, **_kwargs: None

    assert backend._auto_connect_locked() is True
    assert attempts == ["RX_PREFERRED", "RX_FALLBACK"]
    assert opened == ["RX_PREFERRED", "RX_FALLBACK"]
    assert backend.port == "RX_FALLBACK"
    assert saved == [("rx", "connection/port", "RX_FALLBACK")]
    backend._connected = False


def test_tx_auto_connect_falls_back_when_preferred_port_is_busy(monkeypatch):
    from gui_dev_v3.settings import SettingsManager
    from gui_dev_v3.tx.backends.physical import TXPhysicalBackend

    monkeypatch.setattr(
        SettingsManager,
        "get",
        lambda self, key, default=None: "TX_PREFERRED" if key == "connection/port" else default,
    )
    saved = []
    monkeypatch.setattr(
        SettingsManager,
        "set",
        lambda self, key, value: saved.append((self.scope, key, value)),
    )
    backend = TXPhysicalBackend()
    attempts = []
    opened = []
    backend.scan_ports = lambda: ["TX_PREFERRED", "TX_FALLBACK"]
    backend.detect_firmware = lambda port: (
        attempts.append(port)
        or {"device": "VLC_TX", "firmware": "tx_test", "board": "test"}
    )

    def open_selected():
        opened.append(backend.port)
        return backend.port == "TX_FALLBACK"

    backend._open_serial = open_selected
    backend._wait_for_firmware_ready = lambda: True
    backend.apply_link_settings = lambda: None
    backend.log = lambda *_args, **_kwargs: None
    backend._record_diag = lambda *_args, **_kwargs: None

    assert backend._auto_connect_locked() is True
    assert attempts == ["TX_PREFERRED", "TX_FALLBACK"]
    assert opened == ["TX_PREFERRED", "TX_FALLBACK"]
    assert backend.port == "TX_FALLBACK"
    assert saved == [("tx", "connection/port", "TX_FALLBACK")]
    backend._connected = False


def test_rx_manual_mode_without_selected_port_never_starts_auto_discovery(monkeypatch):
    from gui_dev_v3.settings import SettingsManager
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    values = {
        "connection/mode": "Manual",
        "connection/auto_connect": True,
        "connection/scan_interval": 1,
        "connection/port": "",
    }
    monkeypatch.setattr(
        SettingsManager, "get", lambda self, key, default=None: values.get(key, default)
    )
    monkeypatch.setattr(
        "gui_dev_v3.rx.backends.physical.read_status", lambda _role: {}
    )
    backend = RXPhysicalBackend()
    # The offline snapshot may enumerate ports to populate the UI's port
    # count. It must not probe firmware or initiate an automatic connection.
    backend.scan_ports = lambda: []
    backend.detect_firmware = lambda _port: pytest.fail(
        "empty manual mode must not probe firmware"
    )
    backend.auto_connect = lambda: pytest.fail("empty manual mode must not auto-connect")
    backend.connect = lambda _port: pytest.fail("empty manual mode has no port to connect")

    snapshot = backend.refresh()

    assert backend._connecting is False
    assert backend._connect_thread is None
    assert any(entry["event"] == "Manual Port Required" for entry in snapshot.activity_log)

def test_rx_auto_connect_skips_wrong_firmware_and_uses_later_rx_candidate(monkeypatch):
    from gui_dev_v3.settings import SettingsManager
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    monkeypatch.setattr(
        SettingsManager,
        "get",
        lambda self, key, default=None: "" if key == "connection/port" else default,
    )
    saved = []
    monkeypatch.setattr(
        SettingsManager,
        "set",
        lambda self, key, value: saved.append((self.scope, key, value)),
    )
    backend = RXPhysicalBackend()
    attempts = []
    backend.scan_ports = lambda: ["TX_BOARD", "RX_BOARD"]
    backend.detect_firmware = lambda port: (
        attempts.append(port)
        or {
            "device": "VLC_TX" if port == "TX_BOARD" else "VLC_RX",
            "firmware": "test",
            "board": "test",
        }
    )
    backend._open_serial = lambda: True
    backend.apply_link_settings = lambda: None
    backend.log = lambda *_args, **_kwargs: None
    backend._record_diag = lambda *_args, **_kwargs: None

    assert backend._auto_connect_locked() is True
    assert attempts == ["TX_BOARD", "RX_BOARD"]
    assert backend.port == "RX_BOARD"
    assert saved == [("rx", "connection/port", "RX_BOARD")]
    backend._connected = False


def test_tx_auto_connect_skips_wrong_firmware_and_uses_later_tx_candidate(monkeypatch):
    from gui_dev_v3.settings import SettingsManager
    from gui_dev_v3.tx.backends.physical import TXPhysicalBackend

    monkeypatch.setattr(
        SettingsManager,
        "get",
        lambda self, key, default=None: "" if key == "connection/port" else default,
    )
    saved = []
    monkeypatch.setattr(
        SettingsManager,
        "set",
        lambda self, key, value: saved.append((self.scope, key, value)),
    )
    backend = TXPhysicalBackend()
    attempts = []
    backend.scan_ports = lambda: ["RX_BOARD", "TX_BOARD"]
    backend.detect_firmware = lambda port: (
        attempts.append(port)
        or {
            "device": "VLC_RX" if port == "RX_BOARD" else "VLC_TX",
            "firmware": "test",
            "board": "test",
        }
    )
    backend._open_serial = lambda: True
    backend._wait_for_firmware_ready = lambda: True
    backend.apply_link_settings = lambda: None
    backend.log = lambda *_args, **_kwargs: None
    backend._record_diag = lambda *_args, **_kwargs: None

    assert backend._auto_connect_locked() is True
    assert attempts == ["RX_BOARD", "TX_BOARD"]
    assert backend.port == "TX_BOARD"
    assert saved == [("tx", "connection/port", "TX_BOARD")]
    backend._connected = False


def test_serial_scan_lock_times_out_without_entering_critical_section(tmp_path, monkeypatch):
    import gui_dev_v3.serial.detection as detection

    lock_path = tmp_path / "serial_scan.lock"
    monkeypatch.setattr(detection, "_SERIAL_SCAN_LOCK_PATH", lock_path)
    entered = False

    with detection.serial_scan_lock(timeout=1.0):
        with pytest.raises(TimeoutError, match="serial scan lock"):
            with detection.serial_scan_lock(timeout=0.0):
                entered = True

    assert entered is False




def test_tx_auto_connect_stops_before_open_if_shutdown_begins_during_probe(monkeypatch):
    from gui_dev_v3.settings import SettingsManager
    from gui_dev_v3.tx.backends.physical import TXPhysicalBackend

    monkeypatch.setattr(
        SettingsManager, "get", lambda self, key, default=None: default
    )
    backend = TXPhysicalBackend()
    backend.scan_ports = lambda: ["MOCK_TX"]
    backend.detect_firmware = lambda _port: (
        setattr(backend, "_shutting_down", True)
        or {"device": "VLC_TX", "firmware": "test", "board": "test"}
    )
    backend._open_serial = lambda: pytest.fail(
        "TX must not open a port after shutdown begins"
    )

    assert backend._auto_connect_locked() is False


def test_rx_auto_connect_stops_before_open_if_shutdown_begins_during_probe(monkeypatch):
    from gui_dev_v3.settings import SettingsManager
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    monkeypatch.setattr(
        SettingsManager, "get", lambda self, key, default=None: default
    )
    backend = RXPhysicalBackend()
    backend.scan_ports = lambda: ["MOCK_RX"]
    backend.detect_firmware = lambda _port: (
        setattr(backend, "_shutting_down", True)
        or {"device": "VLC_RX", "firmware": "test", "board": "test"}
    )
    backend._open_serial = lambda: pytest.fail(
        "RX must not open a port after shutdown begins"
    )

    assert backend._auto_connect_locked() is False


def test_tx_firmware_readiness_wait_is_cancellable_during_shutdown(monkeypatch):
    from gui_dev_v3.tx.backends.physical import TXPhysicalBackend

    backend = TXPhysicalBackend()
    calls = []

    class Controller:
        is_connected = True
        line_counter = 0

        def send_line(self, _line):
            return True

        def wait_for_line_containing(self, *_args, **_kwargs):
            calls.append(True)
            backend._shutting_down = True
            return False

    backend._controller = Controller()

    assert backend._wait_for_firmware_ready(timeout=5.0) is False
    assert len(calls) == 1


def test_serial_sessions_set_bounded_write_timeout(fake_serial):
    session = SerialSession("tx")

    assert session.connect("MOCK_TX") is True
    assert session.serial_obj.write_timeout == 0.5

    session.disconnect()
    assert fake_serial.open_ports == set()


def test_tx_cleanup_disconnects_then_joins_active_transmission_worker(monkeypatch):
    from gui_dev_v3.tx.backends.physical import TXPhysicalBackend

    backend = TXPhysicalBackend()
    order = []

    class ActiveWorker:
        alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            order.append(("join", timeout))
            self.alive = False

    worker = ActiveWorker()
    backend._transmission_thread = worker
    backend.disconnect = lambda: order.append(("disconnect", None))

    backend.cleanup()

    assert backend._shutting_down is True
    assert order == [("disconnect", None), ("join", 2.0)]
    assert backend._transmission_thread is None
