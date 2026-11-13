"""Runtime status readers for the application-owned state directory."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

# Resolve state directory with VLC_DATA_DIR env var fallback
def _resolve_state_dir() -> Path:
    """Return the best available state directory, checking env var first."""
    env = os.getenv("VLC_DATA_DIR")
    if env:
        return Path(env).expanduser() / "state"
    project = Path(__file__).resolve().parents[2] / "state"
    project.mkdir(parents=True, exist_ok=True)
    return project

_STATE_DIR = _resolve_state_dir()
_WRITE_LOCK = threading.RLock()


def _state_dir() -> Path:
    """Return the best available state directory."""
    return _STATE_DIR


def status_path(role: str) -> Path:
    return _state_dir() / f"{role.lower()}_status.json"


def read_status(role: str) -> dict[str, Any] | None:
    """Read a status file from the application-owned state directory."""
    try:
        path = status_path(role)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        data: dict[str, Any] | None = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def read_runtime_status(role: str) -> dict[str, Any] | None:
    """Alias for read_status."""
    return read_status(role)


def read_beta_status(role: str) -> dict[str, Any] | None:
    return read_status(role)


def read_migration_status(role: str) -> dict[str, Any] | None:
    return read_status(role)


def write_status(role: str, stage: str, detail: str = "", percent: float | None = None, state: str = "idle", **extra: Any) -> bool:
    """Write a status file to the application-owned state directory."""
    import time

    target = status_path(role)
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

    temporary_path: Path | None = None
    with _WRITE_LOCK:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Unique same-directory temporaries prevent concurrent writers
            # from truncating or replacing one another's pending status file.
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(payload, temporary, separators=(",", ":"))
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
            return True
        except (OSError, TypeError, ValueError, OverflowError):
            return False
        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass
