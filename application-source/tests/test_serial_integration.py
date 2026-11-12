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

    @property
    def in_waiting(self) -> int:
        return len(self._responses[0]) if self._responses else 0

    def read(self, size: int = 1) -> bytes:
        time.sleep(0.002)
        if self.port in self.registry.read_errors:
            raise OSError("mock USB serial device removed")
        if not self._responses:
            return b""
        response = self._responses.pop(0)
        data, remainder = response[:size], response[size:]
        if remainder:
            self._responses.insert(0, remainder)
        return data

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


def test_tx_reader_marks_connection_lost_after_unplug(fake_serial):
    session = SerialSession("tx")

    assert session.connect("MOCK_TX") is True
    fake_serial.read_errors.add("MOCK_TX")

    deadline = time.monotonic() + 1.0
    while session.is_connected and time.monotonic() < deadline:
        time.sleep(0.005)

    assert session.is_connected is False
    assert session.serial_obj is None
    assert fake_serial.open_ports == set()
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

def test_stream_start_captures_completion_counter_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """An immediate TX_STREAM_DONE response must not be lost after STREAM_START."""
    from gui_dev_v3.serial.controllers import TXSerialController

    class FakeSettings:
        def __init__(self, _role: str) -> None:
            pass

        def get(self, key: str, default: Any = None) -> Any:
            return 15000 if key == "link/symbol_hz" else default

    monkeypatch.setattr("gui_dev_v3.settings.SettingsManager", FakeSettings)
    controller = TXSerialController()
    controller.is_connected = True
    statuses: list[dict[str, Any]] = []
    controller.on_status = statuses.append

    def immediate_firmware_response(command: str) -> bool:
        if command == "STREAM_BEGIN:1:1:5:16:0000:1:66696C652E62696E":
            controller._append_line("TX_STREAM_BEGIN_OK")
        elif command.startswith("STREAM_DATA:"):
            controller._append_line("TX_STREAM_DATA_OK")
        elif command == "STREAM_START":
            # Simulate firmware replying before send_line() returns.
            controller._append_line("TX_STREAM_DONE")
        return True

    controller.send_line = immediate_firmware_response  # type: ignore[method-assign]
    payload = tmp_path / "file.bin"
    payload.write_bytes(b"hello")

    assert controller._send_stream(
        payload,
        b"hello",
        b"file.bin",
        chunk_size=16,
        tid=1,
        file_crc=0,
        round_count=1,
    ) is True
    assert any(item.get("stage") == "Send complete" for item in statuses)

def test_rx_link_settings_stop_and_report_when_a_write_fails(
    monkeypatch: pytest.MonkeyPatch
):
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    class FakeSettings:
        def __init__(self, _role: str) -> None:
            pass

        def get(self, _key: str, default: Any = None) -> Any:
            return default

    monkeypatch.setattr("gui_dev_v3.settings.SettingsManager", FakeSettings)
    backend = RXPhysicalBackend()
    backend._connected = True
    backend._ser = object()
    sent: list[str] = []
    logged: list[tuple[str, str]] = []

    def fail_second_write(command: str) -> bool:
        sent.append(command)
        return len(sent) < 2

    backend.send_command = fail_second_write  # type: ignore[method-assign]
    backend.log = lambda stage, detail="": logged.append((stage, detail))  # type: ignore[method-assign]

    assert backend.apply_link_settings() is False
    assert sent == ["FREQ=15000\n", "PHASE=50\n"]
    assert logged and logged[0][0] == "Settings Apply Failed"
