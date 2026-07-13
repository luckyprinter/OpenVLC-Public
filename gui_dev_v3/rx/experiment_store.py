"""Experiment data store — JSON-backed CRUD for VLC test experiments."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

STORE_DIR = Path.home() / ".vlc_rx"
STORE_PATH = STORE_DIR / "experiments.json"


@dataclass
class Experiment:
    """A single VLC test experiment."""
    id: int
    name: str
    type: str
    created_at: str  # ISO 8601
    notes: str
    record_count: int = 0


def _default_experiments() -> list[dict[str, Any]]:
    """Seed data matching the design image."""
    return [
        dict(id=1, name="Distance Test - Day 1", type="Distance Test",
             created_at="2025-05-21 12:45:30", notes="Test with different distances", record_count=10),
        dict(id=2, name="Ambient Light Test", type="Ambient Light",
             created_at="2025-05-22 09:15:00", notes="", record_count=8),
        dict(id=3, name="LED Wattage Test", type="LED Wattage",
             created_at="2025-05-23 14:30:00", notes="", record_count=6),
        dict(id=4, name="BER Validation", type="BER Test",
             created_at="2025-05-24 11:00:00", notes="", record_count=12),
        dict(id=5, name="Payload Test", type="Payload Test",
             created_at="2025-05-25 16:20:00", notes="", record_count=9),
    ]


def _load_all() -> list[dict[str, Any]]:
    if STORE_PATH.exists():
        try:
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    # First run — seed default data
    seeds = _default_experiments()
    _save_all(seeds)
    return seeds


def _save_all(items: list[dict[str, Any]]) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


def list_experiments() -> list[Experiment]:
    return [Experiment(**d) for d in _load_all()]


def get_experiment(exp_id: int) -> Experiment | None:
    for d in _load_all():
        if d["id"] == exp_id:
            return Experiment(**d)
    return None


def create_experiment(name: str, exp_type: str, notes: str) -> Experiment:
    items = _load_all()
    next_id = max((d["id"] for d in items), default=0) + 1
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = dict(id=next_id, name=name, type=exp_type,
                 created_at=now, notes=notes, record_count=0)
    items.insert(0, entry)
    _save_all(items)
    return Experiment(**entry)


def update_experiment(exp_id: int, **kwargs: Any) -> Experiment | None:
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
