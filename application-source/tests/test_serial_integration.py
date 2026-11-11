"""Mock serial integration tests for independent TX/RX ESP32 connections.

These tests exercise the host-side serial lifecycle without optical hardware.
They do not emulate USB drivers, ESP32 reset circuitry, or firmware timing.
"""
from __future__ import annotations

import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
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
        if data == b"\n" and not self._responses:
            if self.baudrate == 115200:
                self._responses.append(b"TX Ready\n")
            elif self.baudrate == 460800:
                self._responses.append(b"RX Ready\n")
        return len(data)

    def readline(self) -> bytes:
        time.sleep(0.002)
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
        self.responses: dict[tuple[str | None, int | None], list[bytes]] = {}
        self.open_ports: set[str] = set()
        self.opens: list[tuple[str | None, int | None, bool | None, bool | None, bool | None]] = []
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
