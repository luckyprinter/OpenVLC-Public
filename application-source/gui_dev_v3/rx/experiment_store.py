"""Experiment data store — JSON-backed CRUD for VLC test experiments."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

def _resolve_store_dir() -> Path:
    """Resolve experiment records to the application-owned state directory."""
    env = os.getenv("VLC_DATA_DIR")
    if env:
        return Path(env).expanduser() / "state"
    return Path(__file__).resolve().parents[2] / "state"


STORE_DIR = _resolve_store_dir()
STORE_PATH = STORE_DIR / "experiments.json"
LEGACY_STORE_PATH = Path.home() / ".vlc_rx" / "experiments.json"
_STORE_LOCK = threading.RLock()


class ExperimentStoreError(RuntimeError):
    """Raised when an unsafe store write would risk existing user data."""



@dataclass
class Experiment:
    """A single VLC test experiment."""
    id: int
    name: str
    type: str
    created_at: str  # ISO 8601
    notes: str
    record_count: int = 0


def _read_all() -> tuple[list[dict[str, Any]], bool]:
    """Return records and whether the existing store is unreadable or malformed."""
    source_path = STORE_PATH
    if not source_path.exists() and LEGACY_STORE_PATH.exists():
        # Read the previous user-owned store without deleting or modifying it.
        # A subsequent successful save writes the current app-data copy.
        source_path = LEGACY_STORE_PATH
    if not source_path.exists():
        return [], False
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return [], True
    required = {"id", "name", "type", "created_at", "notes"}
    allowed = required | {"record_count"}
    if not isinstance(data, list) or any(
        not isinstance(item, dict)
        or not required.issubset(item)
        or not set(item).issubset(allowed)
        or not isinstance(item.get("id"), int)
        for item in data
    ):
        return [], True
    return data, False


def _load_all() -> list[dict[str, Any]]:
    """Load user-created experiments without disguising corruption as an empty store."""
    records, corrupt = _read_all()
    if corrupt:
        source_path = STORE_PATH if STORE_PATH.exists() else LEGACY_STORE_PATH
        raise ExperimentStoreError(
            f"Experiment store is unreadable; existing data was left untouched: {source_path}"
        )
    return records


def _save_all(items: list[dict[str, Any]]) -> None:
    # Recheck the on-disk file immediately before writing. If it is corrupt,
    # never replace it with an empty list or a partial reconstruction.
    with _STORE_LOCK:
        _existing, corrupt = _read_all()
        if corrupt:
            raise ExperimentStoreError(
                f"Experiment store is unreadable; existing data was left untouched: {STORE_PATH}"
            )

        temporary_path: Path | None = None
        try:
            STORE_DIR.mkdir(parents=True, exist_ok=True)
            # A unique same-directory temporary avoids collisions with another
            # save and keeps os.replace atomic on the destination filesystem.
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=STORE_DIR,
                prefix=".experiments.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(items, temporary, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, STORE_PATH)
        except OSError as exc:
            raise ExperimentStoreError(
                f"Could not save experiment data; existing records were preserved: {exc}"
            ) from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass


def list_experiments() -> list[Experiment]:
    with _STORE_LOCK:
        return [Experiment(**d) for d in _load_all()]


def get_experiment(exp_id: int) -> Experiment | None:
    with _STORE_LOCK:
        for d in _load_all():
            if d["id"] == exp_id:
                return Experiment(**d)
        return None


def create_experiment(name: str, exp_type: str, notes: str) -> Experiment:
    with _STORE_LOCK:
        items = _load_all()
        next_id = max((d["id"] for d in items), default=0) + 1
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = dict(id=next_id, name=name, type=exp_type,
                     created_at=now, notes=notes, record_count=0)
        items.insert(0, entry)
        _save_all(items)
        return Experiment(**entry)


def update_experiment(exp_id: int, **kwargs: Any) -> Experiment | None:
    with _STORE_LOCK:
        items = _load_all()
        for d in items:
            if d["id"] == exp_id:
                for k, v in kwargs.items():
                    if k in d:
                        d[k] = v
                _save_all(items)
                return Experiment(**d)
        return None


def delete_experiment(exp_id: int) -> bool:
    with _STORE_LOCK:
        items = _load_all()
        new_items = [d for d in items if d["id"] != exp_id]
        if len(new_items) == len(items):
            return False
        _save_all(new_items)
        return True


# --- Table Builder data ---

AVAILABLE_CATEGORIES = [
    ("Transmission", [
        ("file_name", "File Name"),
        ("file_size", "File Size (KiB)"),
        ("transfer_time", "Total Transfer Time (s)"),
        ("data_rate", "Effective Data Rate (bps)"),
        ("file_category", "File Category"),
        ("file_type", "File Type / Ext"),
        ("chunks_count", "Number of Chunks"),
        ("transfer_path", "Transfer Path"),
    ]),
    ("BER / Reliability", [
        ("ber", "BER (%)"),
        ("strict_ber", "Strict BER (%)"),
        ("bit_errors", "Bit Errors"),
        ("crc_status", "CRC (Pass/Fail)"),
        ("chunk_completion", "Chunk Completion (%)"),
        ("reconstruction_result", "Reconstruction Result"),
        ("expected_behavior", "Expected Behavior"),
    ]),
    ("Receiver", [
        ("pvo", "PV0 (V)"),
        ("vref", "Vref (V)"),
        ("margin", "Receiver Margin (V)"),
        ("calibration_status", "Calibration Status"),
        ("receiver_sensor", "Receiver Sensor"),
        ("front_end", "Front End"),
    ]),
]

MANUAL_COLUMNS = [
    ("distance_m", "Distance (m)", True),
    ("optical_distance", "Optical Distance (m)", False),
    ("height_m", "Height (m)", False),
    ("led_wattage", "LED Wattage (W)", True),
    ("lux_level", "Lux Level (lx)", True),
    ("horizontal_offset", "Horizontal Offset (m)", False),
    ("notes_col", "Notes", False),
    ("trial_col", "Trial", False),
    ("test_id", "Test ID", False),
    ("viewing_distance", "Viewing Distance (m)", False),
    ("flicker_observed", "Flicker Observed", False),
    ("glare_observed", "Glare Observed", False),
    ("comfort_rating", "Comfort Rating", False),
    ("ambient_condition", "Ambient Condition", False),
    ("lux_tool", "Lux Tool", False),
    ("alignment", "Alignment", False),
]
