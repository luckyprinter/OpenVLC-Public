"""Runtime status readers — reads from vlc_beta state/ directory for live data."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Resolve state directory with VLC_DATA_DIR env var fallback
def _resolve_state_dir() -> Path:
    """Return the best available state directory, checking env var first."""
    env = os.getenv("VLC_DATA_DIR")
    if env:
        return Path(env).expanduser() / "state"
    beta = Path(__file__).resolve().parents[3] / "vlc_beta" / "state"
    if beta.exists():
        return beta
    project = Path(__file__).resolve().parents[2] / "state"
    project.mkdir(parents=True, exist_ok=True)
    return project

_STATE_DIR = _resolve_state_dir()


def _state_dir() -> Path:
    """Return the best available state directory."""
    return _STATE_DIR


def status_path(role: str) -> Path:
    return _state_dir() / f"{role.lower()}_status.json"


def read_status(role: str) -> dict[str, Any] | None:
    """Read a status file from the vlc_beta state directory."""
    try:
        path = status_path(role)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        data: dict[str, Any] | None = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def read_runtime_status(role: str) -> dict[str, Any] | None:
    """Alias for read_status."""
    return read_status(role)


def read_beta_status(role: str) -> dict[str, Any] | None:
    return read_status(role)


def read_migration_status(role: str) -> dict[str, Any] | None:
    return read_status(role)


def write_status(role: str, stage: str, detail: str = "", percent: float | None = None, state: str = "idle", **extra: Any) -> None:
    """Write a status file (compatible with vlc_beta's write_status)."""
    import time

    target = status_path(role)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "role": role.lower(),
        "stage": stage,
        "detail": detail,
        "state": state,
        "updated_at": time.time(),
    }
    if percent is not None:
        payload["percent"] = max(0.0, min(100.0, float(percent)))
    payload.update({k: v for k, v in extra.items() if v is not None})
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        pass
