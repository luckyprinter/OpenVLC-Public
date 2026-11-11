"""Guard the existing TX/RX link configuration defaults and command order.

These tests protect the application-to-firmware configuration contract. They do
not simulate or certify optical synchronization.
"""
from __future__ import annotations

from gui_dev_v3 import settings
from gui_dev_v3.serial.controllers import TXSerialController
from gui_dev_v3.rx.backends.physical import RXPhysicalBackend


class _DefaultSettings:
    def __init__(self, role: str) -> None:
        self.role = role

    def get(self, key: str, default=None):
        return default


def test_tx_default_link_configuration_command_order(monkeypatch):
    monkeypatch.setattr(settings, "SettingsManager", _DefaultSettings)
    controller = TXSerialController()
    controller._dma_capable = False
    commands = []
    controller.send_line = commands.append
    controller.status = lambda *_args, **_kwargs: None

    controller.apply_4b5b_settings()

    assert commands == [
        "MODE=4B5B",
        "QUIET=1",
        "FREQ=15000",
        "GAP=0",
        "FGAP=1",
        "ACTIVE_LOW=1",
        "IDLE_ON=1",
        "CONFIG?",
    ]


def test_rx_default_link_configuration_command_order(monkeypatch):
    monkeypatch.setattr(settings, "SettingsManager", _DefaultSettings)
    backend = object.__new__(RXPhysicalBackend)
    backend._connected = True
    backend._ser = object()
    backend._pwm_autocal_target_mv = 0
    backend._pwm_autocal_converged = False
    commands = []
    backend.send_command = commands.append

    backend.apply_link_settings()

    assert commands == [
        "FREQ=15000\n",
        "PHASE=50\n",
        "MAJ=1\n",
        "REPORT=1\n",
        "VREF_MARGIN=365\n",
        "VREF_PWM_FS=2625\n",
        "VREF_SETTLE_MS=120\n",
        "VREF_MODE=MANUAL\n",
        "VREF_SET=1700\n",
    ]
