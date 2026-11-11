"""Regression tests for robust settings parsing and atomic persistence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gui_dev_v3 import settings_store


@pytest.fixture
def settings_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    settings_dir = tmp_path / "settings"
    settings_path = settings_dir / "settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", settings_path)
    return settings_path


def test_string_false_is_not_loaded_as_true(settings_paths: Path) -> None:
    settings_paths.parent.mkdir(parents=True)
    settings_paths.write_text(
        json.dumps({"fullscreen": "false", "borderless": "0"}),
        encoding="utf-8",
    )

    loaded = settings_store.load_settings()

    assert loaded.fullscreen is False
    assert loaded.borderless is False


def test_true_boolean_strings_are_supported(settings_paths: Path) -> None:
    settings_paths.parent.mkdir(parents=True)
    settings_paths.write_text(
        json.dumps({"fullscreen": "true", "borderless": "yes"}),
        encoding="utf-8",
    )

    loaded = settings_store.load_settings()

    assert loaded.fullscreen is True
    assert loaded.borderless is True


@pytest.mark.parametrize("payload", ["[]", "null", "42", '"settings"'])
def test_non_object_json_returns_defaults(settings_paths: Path, payload: str) -> None:
    settings_paths.parent.mkdir(parents=True)
    settings_paths.write_text(payload, encoding="utf-8")

    assert settings_store.load_settings() == settings_store.AppSettings()


def test_save_settings_atomically_round_trips(settings_paths: Path) -> None:
    expected = settings_store.AppSettings(
        theme="charcoal",
        density="compact",
        accent="cyan",
        resolution="1366x768",
        fullscreen=True,
        borderless=False,
    )

    settings_store.save_settings(expected)

    assert settings_store.load_settings() == expected
    assert json.loads(settings_paths.read_text(encoding="utf-8"))["theme"] == "charcoal"
    assert list(settings_paths.parent.glob("*.tmp")) == []



def test_reset_clears_console_and_shared_display_settings(
    settings_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gui_dev_v3.settings import reset_all_settings

    class FakeManager:
        def __init__(self, scope: str = "rx") -> None:
            self.scope = scope
            self.cleared = False

        def clear(self) -> None:
            self.cleared = True

    cleared_scopes: list[str] = []

    class FakeScopedManager(FakeManager):
        def clear(self) -> None:
            cleared_scopes.append(self.scope)

    monkeypatch.setattr("gui_dev_v3.settings.SettingsManager", FakeScopedManager)

    class FakeWindow:
        settings = settings_store.AppSettings(
            theme="synthwave",
            resolution="1366x768",
            fullscreen=True,
            borderless=True,
        )

    manager = FakeManager()
    window = FakeWindow()

    reset_all_settings(manager, window)

    assert manager.cleared is True
    assert cleared_scopes == ["tx"]
    assert window.settings == settings_store.AppSettings()
    assert settings_store.load_settings() == settings_store.AppSettings()
