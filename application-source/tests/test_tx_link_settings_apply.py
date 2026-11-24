from gui_dev_v3.tx.backends.physical import TXPhysicalBackend


class FakeController:
    is_connected = True

    def __init__(self, apply_result=True):
        self.apply_result = apply_result
        self.calls = []

    def apply_4b5b_settings(self, **kwargs):
        self.calls.append(kwargs)
        return self.apply_result


class FakeSettingsManager:
    def __init__(self, _scope):
        self.values = {
            "link/symbol_hz": 15000,
            "link/post_frame_idle_ms": 0,
            "link/frame_gap_ms": 1,
            "link/active_low": True,
            "link/idle_on": True,
            "link/quiet_mode": True,
            "link/cal_intensity_pct": 85,
        }

    def get(self, key, default=None):
        return self.values.get(key, default)


def _backend(monkeypatch, apply_result=True, intensity_result=True):
    from gui_dev_v3 import settings

    monkeypatch.setattr(settings, "SettingsManager", FakeSettingsManager)
    backend = TXPhysicalBackend()
    backend._connected = True
    backend._controller = FakeController(apply_result)
    commands = []
    monkeypatch.setattr(
        backend, "send_command",
        lambda command: commands.append(command) or intensity_result,
    )
    logs = []
    monkeypatch.setattr(
        backend, "log",
        lambda event, details: logs.append((event, details)),
    )
    return backend, commands, logs


def test_link_settings_reports_success_only_after_all_writes(monkeypatch):
    backend, commands, logs = _backend(monkeypatch)

    assert backend.apply_link_settings() is True
    assert commands == ["INTENSITY=85"]
    assert logs[-1][0] == "Settings applied"


def test_link_settings_reports_controller_failure(monkeypatch):
    backend, commands, logs = _backend(monkeypatch, apply_result=False)

    assert backend.apply_link_settings() is False
    assert commands == []
    assert logs[-1][0] == "Settings apply failed"


def test_link_settings_reports_intensity_write_failure(monkeypatch):
    backend, commands, logs = _backend(monkeypatch, intensity_result=False)

    assert backend.apply_link_settings() is False
    assert commands == ["INTENSITY=85"]
    assert logs[-1] == (
        "Settings apply failed",
        "Serial write failed at INTENSITY",
    )


def test_link_settings_rejects_invalid_saved_values(monkeypatch):
    from gui_dev_v3 import settings

    class InvalidSettingsManager(FakeSettingsManager):
        def get(self, key, default=None):
            if key == "link/symbol_hz":
                return "not-a-frequency"
            return super().get(key, default)

    monkeypatch.setattr(settings, "SettingsManager", InvalidSettingsManager)
    backend = TXPhysicalBackend()
    backend._connected = True
    backend._controller = FakeController()
    logs = []
    monkeypatch.setattr(backend, "log", lambda event, details: logs.append((event, details)))

    assert backend.apply_link_settings() is False
    assert backend._controller.calls == []
    assert logs[-1][0] == "Settings apply failed"


def test_link_settings_requires_connected_hardware():
    backend = TXPhysicalBackend()

    assert backend.apply_link_settings() is False
