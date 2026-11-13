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
    monkeypatch.setattr(settings_store, "LEGACY_SETTINGS_PATH", tmp_path / "legacy" / "settings.json")
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

    assert reset_all_settings(manager, window) is True

    assert manager.cleared is True
    assert cleared_scopes == ["tx"]
    assert window.settings == settings_store.AppSettings()
    assert settings_store.load_settings() == settings_store.AppSettings()



@pytest.mark.parametrize("payload", ["{ invalid json", "[]", "null", "42", '"settings"'])
def test_automatic_save_preserves_malformed_settings_file(
    settings_paths: Path, payload: str
) -> None:
    settings_paths.parent.mkdir(parents=True)
    settings_paths.write_text(payload, encoding="utf-8")
    original = settings_paths.read_bytes()

    saved = settings_store.save_settings(
        settings_store.AppSettings(theme="charcoal")
    )

    assert saved is False
    assert settings_paths.read_bytes() == original
    assert list(settings_paths.parent.glob("*.corrupt-*.bak")) == []


def test_explicit_recovery_backs_up_corrupt_settings_before_replacing(
    settings_paths: Path,
) -> None:
    settings_paths.parent.mkdir(parents=True)
    original = b"{ damaged settings"
    settings_paths.write_bytes(original)

    saved = settings_store.save_settings(
        settings_store.AppSettings(),
        allow_corrupt_recovery=True,
    )

    backups = list(settings_paths.parent.glob("settings.json.corrupt-*.bak"))
    assert saved is True
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert settings_store.load_settings() == settings_store.AppSettings()



def test_legacy_settings_are_loaded_and_copied_to_new_config_path_without_deletion(
    settings_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "legacy" / "settings.json"
    legacy_path.parent.mkdir(parents=True)
    legacy_bytes = json.dumps({
        "theme": "charcoal",
        "density": "compact",
        "accent": "cyan",
        "resolution": "1366x768",
    }).encode("utf-8")
    legacy_path.write_bytes(legacy_bytes)
    monkeypatch.setattr(settings_store, "LEGACY_SETTINGS_PATH", legacy_path)

    assert settings_store.load_settings().theme == "charcoal"
    expected = settings_store.AppSettings(theme="charcoal", density="compact", accent="cyan", resolution="1366x768")
    assert settings_store.save_settings(expected) is True
    assert settings_store.load_settings() == expected
    assert json.loads(settings_paths.read_text(encoding="utf-8"))["theme"] == "charcoal"
    assert legacy_path.read_bytes() == legacy_bytes


def test_corrupt_legacy_settings_are_preserved_until_explicit_recovery(
    settings_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "legacy" / "settings.json"
    legacy_path.parent.mkdir(parents=True)
    original = b"{ broken legacy settings"
    legacy_path.write_bytes(original)
    monkeypatch.setattr(settings_store, "LEGACY_SETTINGS_PATH", legacy_path)

    assert settings_store.save_settings(settings_store.AppSettings(theme="charcoal")) is False
    assert legacy_path.read_bytes() == original
    assert not settings_paths.exists()

    assert settings_store.save_settings(
        settings_store.AppSettings(), allow_corrupt_recovery=True
    ) is True
    backups = list(legacy_path.parent.glob("settings.json.corrupt-*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert legacy_path.read_bytes() == original
    assert settings_paths.exists()



def test_reset_does_not_clear_preferences_when_default_settings_cannot_be_saved(
    settings_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gui_dev_v3.settings import reset_all_settings

    class FakeManager:
        scope = "rx"

        def __init__(self) -> None:
            self.cleared = False

        def clear(self) -> None:
            self.cleared = True

    class FakeWindow:
        settings = settings_store.AppSettings(
            theme="synthwave",
            resolution="1366x768",
            fullscreen=True,
            borderless=True,
        )

    manager = FakeManager()
    window = FakeWindow()
    original_window_settings = window.settings
    cleared_scopes: list[str] = []

    class FakeScopedManager:
        def __init__(self, scope: str = "rx") -> None:
            self.scope = scope

        def clear(self) -> None:
            cleared_scopes.append(self.scope)

    monkeypatch.setattr("gui_dev_v3.settings.SettingsManager", FakeScopedManager)
    monkeypatch.setattr(settings_store, "save_settings", lambda *_args, **_kwargs: False)

    assert reset_all_settings(manager, window) is False
    assert manager.cleared is False
    assert cleared_scopes == []
    assert window.settings == original_window_settings


def test_save_returns_false_when_config_directory_cannot_be_created(
    settings_paths: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blocked_directory = tmp_path / "not-a-directory"
    blocked_directory.write_text("preserve this file", encoding="utf-8")
    monkeypatch.setattr(settings_store, "SETTINGS_DIR", blocked_directory)
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", blocked_directory / "settings.json")

    assert settings_store.save_settings(settings_store.AppSettings(theme="charcoal")) is False
    assert blocked_directory.read_text(encoding="utf-8") == "preserve this file"
