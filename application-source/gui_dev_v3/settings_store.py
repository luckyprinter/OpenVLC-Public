from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from gui_dev_v3.runtime_paths import resolve_user_config_dir

ThemeMode = Literal["graphite_lab", "midnight_navy", "charcoal", "espresso", "synthwave", "arctic_light", "dark", "light"]
DensityMode = Literal["comfortable", "compact"]
AccentName = Literal["blue", "cyan", "green", "violet", "amber", "rose", "teal"]

SETTINGS_DIR = resolve_user_config_dir()
SETTINGS_PATH = SETTINGS_DIR / "settings.json"
# Previous releases stored this JSON file in a private home-directory folder.
# Keep it as a read-only migration source; successful saves write the new path
# and never remove or modify the original file.
LEGACY_SETTINGS_DIR = Path.home() / ".vlc_rx_app"
LEGACY_SETTINGS_PATH = LEGACY_SETTINGS_DIR / "settings.json"


def _settings_source_path() -> Path:
    """Prefer the current config file, falling back to the previous location."""
    if SETTINGS_PATH.exists():
        return SETTINGS_PATH
    if LEGACY_SETTINGS_PATH.exists():
        return LEGACY_SETTINGS_PATH
    return SETTINGS_PATH

# All 15 resolution presets as (key, width, height) tuples, sorted by increasing width
RESOLUTION_PRESETS: list[tuple[str, int, int]] = [
    ("320x200", 320, 200),
    ("640x400", 640, 400),
    ("720x400", 720, 400),
    ("720x480", 720, 480),
    ("768x480", 768, 480),
    ("800x500", 800, 500),
    ("800x600", 800, 600),
    ("928x580", 928, 580),
    ("960x600", 960, 600),
    ("1024x576", 1024, 576),
    ("1024x768", 1024, 768),
    ("1152x720", 1152, 720),
    ("1280x720", 1280, 720),
    ("1280x800", 1280, 800),
    ("1366x768", 1366, 768),
    ("1920x1080", 1920, 1080),
]

_VALID_RESOLUTION_KEYS = {key for key, _, _ in RESOLUTION_PRESETS}


_VALID_THEMES: set[str] = {"graphite_lab", "midnight_navy", "charcoal", "espresso", "synthwave", "arctic_light", "dark", "light"}
_LEGACY_THEME_MAP: dict[str, str] = {"dark": "midnight_navy", "light": "arctic_light"}
_VALID_ACCENTS: set[str] = {"blue", "cyan", "green", "violet", "amber", "rose", "teal"}


@dataclass
class AppSettings:
    theme: ThemeMode = "graphite_lab"
    density: DensityMode = "comfortable"
    accent: AccentName = "teal"
    resolution: str = "1280x800"
    fullscreen: bool = False
    borderless: bool = False


def _read_bool(value: object, default: bool = False) -> bool:
    """Parse persisted booleans without treating the string 'false' as true."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return default


def _read_settings_object() -> tuple[dict[str, object] | None, bool]:
    """Read the settings object and report whether an existing file is malformed."""
    source_path = _settings_source_path()
    if not source_path.exists():
        return None, False
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, True
    if not isinstance(data, dict):
        return None, True
    return data, False


def load_settings() -> AppSettings:
    data, malformed = _read_settings_object()
    if malformed or data is None:
        return AppSettings()

    raw_theme = data.get("theme", "graphite_lab")
    if not isinstance(raw_theme, str):
        raw_theme = "graphite_lab"
    # Remap legacy "dark"/"light" to new named presets.
    raw_theme = _LEGACY_THEME_MAP.get(raw_theme, raw_theme)
    valid_theme = raw_theme if raw_theme in _VALID_THEMES else "graphite_lab"

    raw_density = data.get("density", "comfortable")
    if not isinstance(raw_density, str) or raw_density not in {"comfortable", "compact"}:
        raw_density = "comfortable"

    raw_accent = data.get("accent", "teal")
    if not isinstance(raw_accent, str) or raw_accent not in _VALID_ACCENTS:
        raw_accent = "blue"

    raw_resolution = data.get("resolution", "1280x800")
    if not isinstance(raw_resolution, str) or raw_resolution not in _VALID_RESOLUTION_KEYS:
        raw_resolution = "1280x800"

    return AppSettings(
        theme=valid_theme,  # type: ignore[arg-type]
        density=raw_density,  # type: ignore[arg-type]
        accent=raw_accent,  # type: ignore[arg-type]
        resolution=raw_resolution,
        fullscreen=_read_bool(data.get("fullscreen", False)),
        borderless=_read_bool(data.get("borderless", False)),
    )


def save_settings(
    settings: AppSettings, *, allow_corrupt_recovery: bool = False
) -> bool:
    """Atomically save settings without silently replacing malformed user data.

    Normal autosaves refuse to overwrite an unreadable/non-object settings file.
    An explicit reset may opt into recovery; the original bytes are first copied
    to a timestamped backup and verified before the replacement is attempted.
    """
    _existing, malformed = _read_settings_object()
    if malformed:
        if not allow_corrupt_recovery:
            return False
        try:
            source_path = _settings_source_path()
            original_bytes = source_path.read_bytes()
            backup_path = source_path.with_name(
                f"{source_path.name}.corrupt-{time.time_ns()}.bak"
            )
            backup_path.write_bytes(original_bytes)
            if backup_path.read_bytes() != original_bytes:
                backup_path.unlink(missing_ok=True)
                return False
        except OSError:
            return False

    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=SETTINGS_DIR,
            prefix=f".{SETTINGS_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(asdict(settings), temp_file, indent=2)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, SETTINGS_PATH)
        return True
    except OSError:
        return False
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
