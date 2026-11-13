"""UI-facing regression tests for settings persistence failures."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QWidget

from gui_dev_v3 import settings


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class FakeQSettings:
    # Mirror the enum exposed by the real QSettings class because settings.py
    # checks the status through the patched class during these tests.
    Status = QSettings.Status
    status_value = QSettings.Status.NoError

    def __init__(self, *_args):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass

    def status(self):
        return self.status_value

    def clear(self):
        self.values.clear()


def test_settings_manager_reports_qsettings_write_failure(monkeypatch):
    FakeQSettings.status_value = QSettings.Status.AccessError
    monkeypatch.setattr(settings, "QSettings", FakeQSettings)
    manager = settings.SettingsManager("rx")

    assert manager.set("general/test", True) is False


def test_settings_manager_reports_successful_write(monkeypatch):
    FakeQSettings.status_value = QSettings.Status.NoError
    monkeypatch.setattr(settings, "QSettings", FakeQSettings)
    manager = settings.SettingsManager("rx")

    assert manager.set("general/test", True) is True


def test_bound_control_exposes_failed_save_accessibly(qapp, monkeypatch):
    monkeypatch.setattr(settings, "QSettings", FakeQSettings)
    FakeQSettings.status_value = QSettings.Status.AccessError
    manager = settings.SettingsManager("rx")
    control = QWidget()

    assert settings._persist_bound_value(control, manager, "general/test", True) is False
    assert control.property("settingsSaveFailed") is True
    assert "Could not save" in control.toolTip()
    assert "config folder permissions" in control.accessibleDescription()


def test_theme_picker_reverts_live_preview_when_json_save_fails(monkeypatch):
    from gui_dev_v3 import settings_store

    class FakePicker:
        def __init__(self):
            self.theme_changed = _Signal()
            self.current = None
            self.tooltip = ""
            self.description = ""

        def set_current(self, key):
            self.current = key

        def setToolTip(self, value):
            self.tooltip = value

        def setAccessibleDescription(self, value):
            self.description = value

    class _Signal:
        def connect(self, callback):
            self.callback = callback

    class FakeManager:
        def set(self, *_args):
            raise AssertionError("QSettings must not be updated after JSON save failure")

    class FakeAppSettings:
        theme = "graphite_lab"

    applied = []
    monkeypatch.setattr(settings_store, "load_settings", lambda: FakeAppSettings())
    monkeypatch.setattr(settings_store, "save_settings", lambda _settings: False)
    monkeypatch.setattr(settings, "apply_theme", lambda **kwargs: applied.append(kwargs["theme"]))
    picker = FakePicker()

    settings.bind_theme_picker(picker, FakeManager())
    picker.theme_changed.callback("arctic_light")

    assert picker.current == "graphite_lab"
    assert applied == ["graphite_lab"]
    assert "Theme could not be saved" in picker.tooltip
