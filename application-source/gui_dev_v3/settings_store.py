from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

ThemeMode = Literal["midnight_navy", "charcoal", "espresso", "synthwave", "arctic_light", "dark", "light"]
DensityMode = Literal["comfortable", "compact"]
AccentName = Literal["blue", "cyan", "green", "violet", "amber", "rose"]

SETTINGS_DIR = Path.home() / ".vlc_rx_app"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

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


_VALID_THEMES: set[str] = {"midnight_navy", "charcoal", "espresso", "synthwave", "arctic_light", "dark", "light"}
_LEGACY_THEME_MAP: dict[str, str] = {"dark": "midnight_navy", "light": "arctic_light"}
_VALID_ACCENTS: set[str] = {"blue", "cyan", "green", "violet", "amber", "rose"}


@dataclass
class AppSettings:
    theme: ThemeMode = "midnight_navy"
    density: DensityMode = "comfortable"
    accent: AccentName = "blue"
    resolution: str = "1280x800"
    fullscreen: bool = False
    borderless: bool = False


def load_settings() -> AppSettings:
    if not SETTINGS_PATH.exists():
        return AppSettings()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppSettings()
    raw_theme = data.get("theme", "midnight_navy")
    # Remap legacy "dark"/"light" to new named presets
    if raw_theme in _LEGACY_THEME_MAP:
        raw_theme = _LEGACY_THEME_MAP[raw_theme]
    valid_theme = raw_theme if raw_theme in _VALID_THEMES else "midnight_navy"
    raw_accent = data.get("accent", "blue")
    return AppSettings(
        theme=valid_theme,  # type: ignore[arg-type]
        density=data.get("density", "comfortable") if data.get("density") in {"comfortable", "compact"} else "comfortable",
        accent=raw_accent if raw_accent in _VALID_ACCENTS else "blue",  # type: ignore[arg-type]
        resolution=data.get("resolution", "1280x800") if data.get("resolution") in _VALID_RESOLUTION_KEYS else "1280x800",
        fullscreen=bool(data.get("fullscreen", False)),
        borderless=bool(data.get("borderless", False)),
    )


def save_settings(settings: AppSettings) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
