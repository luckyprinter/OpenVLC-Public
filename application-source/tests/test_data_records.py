"""Regression tests for read-only legacy RX transfer-history compatibility."""
from __future__ import annotations

import json
from pathlib import Path


def test_legacy_transfer_history_is_loaded_without_modifying_source(
    monkeypatch, tmp_path: Path
) -> None:
    from gui_dev_v3.data import records

    legacy_dir = tmp_path / "LiFiReceived" / "transfer_records"
    legacy_dir.mkdir(parents=True)
    source = legacy_dir / "rx_transfer_17.json"
    original = {
        "tid": 17,
        "payload": {
            "name": "legacy-payload.bin",
            "size_bytes": 4,
            "crc16_ccitt": "PASS",
        },
        "chunks": {
            "total": 1,
            "received": 1,
            "missing_indexes": [],
            "received_indexes": [0],
        },
        "signal": {"quality_status": "Good"},
        "status": "complete",
        "created_at": "2026-11-13 03:00:00",
    }
    original_bytes = json.dumps(original).encode("utf-8")
    source.write_bytes(original_bytes)

    monkeypatch.setattr(records, "LEGACY_TRANSFER_RECORDS_DIR", legacy_dir)
    monkeypatch.setattr(records, "_log_dir", lambda: tmp_path / "current-logs")

    history = records.load_real_transfer_history()

    assert len(history) == 1
    assert history[0].tid == 17
    assert history[0].filename == "legacy-payload.bin"
    assert history[0].quality.strict_ber is None
    assert source.read_bytes() == original_bytes
