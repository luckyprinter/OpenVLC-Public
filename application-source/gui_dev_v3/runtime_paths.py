"""Cross-platform writable locations for OpenVLC runtime data.

Runtime records must never be written beside a packaged executable: that
location may be read-only (for example, under Program Files or /opt).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


def resolve_user_data_dir(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the conventional per-user application-data directory."""
    platform = platform or sys.platform
    environ = environ if environ is not None else os.environ
    home = home or Path.home()

    if platform == "win32":
        root = environ.get("LOCALAPPDATA") or environ.get("APPDATA")
        return (Path(root) if root else home / "AppData" / "Local") / "OpenVLC"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "OpenVLC"

    root = environ.get("XDG_DATA_HOME")
    return (Path(root) if root else home / ".local" / "share") / "OpenVLC"


def configure_runtime_data_dir() -> Path:
    """Set VLC_DATA_DIR once, preserving an explicit user override."""
    configured = os.environ.get("VLC_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    resolved = resolve_user_data_dir()
    os.environ["VLC_DATA_DIR"] = str(resolved)
    return resolved
