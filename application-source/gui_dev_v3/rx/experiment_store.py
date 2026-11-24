"""Experiment data store — JSON-backed CRUD for VLC test experiments."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gui_dev_v3.rx.receiver_storage import (
    EXPERIMENTS_FILENAME,
    ReceiverStorageError,
    lock_state,
    read_rows,
    write_json,
)


def _resolve_store_dir() -> Path:
    """Resolve experiment records to the application-owned state directory."""
    env = os.getenv("VLC_DATA_DIR")
    if env:
        return Path(env).expanduser() / "state"
    return Path(__file__).resolve().parents[2] / "state"


STORE_DIR = _resolve_store_dir()
STORE_PATH = STORE_DIR / EXPERIMENTS_FILENAME
LEGACY_STORE_PATH = Path.home() / ".vlc_rx" / EXPERIMENTS_FILENAME


class ExperimentStoreError(ReceiverStorageError):
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


def validate_experiments(data: object) -> list[dict[str, Any]]:
    """Validate stored and imported experiments using the same record schema."""
    text_fields = {"name", "type", "created_at", "notes"}
    required = text_fields | {"id"}
    allowed = required | {"record_count"}
    if not isinstance(data, list) or any(
        not isinstance(item, dict)
        or not required.issubset(item)
        or not set(item).issubset(allowed)
        or type(item["id"]) is not int
        or any(not isinstance(item[key], str) for key in text_fields)
        or type(item.get("record_count", 0)) is not int
        for item in data
    ):
        raise ExperimentStoreError("Invalid experiment records")
    if len({item["id"] for item in data}) != len(data):
        raise ExperimentStoreError("Duplicate experiment identifiers")
    return data


def read_experiments() -> list[dict[str, Any]]:
    """Read raw records from either location while the caller holds the database lock."""
    try:
        return read_rows(STORE_PATH, LEGACY_STORE_PATH, validate_experiments)
    except ReceiverStorageError as exc:
        raise ExperimentStoreError(str(exc)) from exc


def _save_all(items: list[dict[str, Any]]) -> None:
    try:
        write_json(STORE_PATH, validate_experiments(items))
    except (OSError, ValueError, ReceiverStorageError) as exc:
        raise ExperimentStoreError(f"Could not save experiment data: {exc}") from exc


@contextmanager
def _experiment_lock():
    try:
        with lock_state(STORE_PATH.parent):
            yield
    except ExperimentStoreError:
        raise
    except ReceiverStorageError as exc:
        raise ExperimentStoreError(str(exc)) from exc


def list_experiments() -> list[Experiment]:
    with _experiment_lock():
        return [Experiment(**d) for d in read_experiments()]


def get_experiment(exp_id: int) -> Experiment | None:
    with _experiment_lock():
        for d in read_experiments():
            if d["id"] == exp_id:
                return Experiment(**d)
        return None


def create_experiment(name: str, exp_type: str, notes: str) -> Experiment:
    with _experiment_lock():
        items = read_experiments()
        next_id = max((d["id"] for d in items), default=0) + 1
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = dict(id=next_id, name=name, type=exp_type,
                     created_at=now, notes=notes, record_count=0)
        items.insert(0, entry)
        _save_all(items)
        return Experiment(**entry)


def update_experiment(exp_id: int, **kwargs: Any) -> Experiment | None:
    with _experiment_lock():
        items = read_experiments()
        for d in items:
            if d["id"] == exp_id:
                for k, v in kwargs.items():
                    if k in d:
                        d[k] = v
                _save_all(items)
                return Experiment(**d)
        return None


def delete_experiment(exp_id: int) -> bool:
    with _experiment_lock():
        items = read_experiments()
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
