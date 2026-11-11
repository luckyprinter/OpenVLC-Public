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
        self.is_open = False

    def open(self) -> None:
        if self.port in self.registry.fail_ports:
            raise OSError(f"mock port {self.port} is busy")
        with self.registry.lock:
            if self.port in self.registry.open_ports:
                raise OSError(f"mock port {self.port} is already open")
            self.registry.open_ports.add(self.port)
            self.registry.opens.append((self.port, self.baudrate, self.dtr, self.rts))
        self.is_open = True

    def close(self) -> None:
        with self.registry.lock:
            self.registry.open_ports.discard(self.port)
        self.is_open = False

    def write(self, data: bytes) -> int:
        return len(data)

    def readline(self) -> bytes:
        time.sleep(0.002)
        return b""


class FakeSerialRegistry:
    def __init__(self, fail_ports: set[str] | None = None) -> None:
        self.fail_ports = fail_ports or set()
        self.open_ports: set[str] = set()
        self.opens: list[tuple[str | None, int | None, bool | None, bool | None]] = []
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
    assert all(entry[2:] == (False, False) for entry in fake_serial.opens)

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
    assert fake_serial.opens == [("MOCK_RX", 460800, False, False)]

    backend._close_serial()
    assert fake_serial.open_ports == set()
