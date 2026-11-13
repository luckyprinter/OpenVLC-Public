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



def test_transfer_parser_rejects_non_object_nested_fields():
    from gui_dev_v3.data.records import _parse_transfer_record

    base = {
        "tid": 9,
        "payload": {"name": "file.bin", "size_bytes": 1},
        "chunks": {"total": 1, "received": 1, "missing_indexes": [], "received_indexes": [0]},
        "signal": {},
        "status": "complete",
    }
    assert _parse_transfer_record([]) is None
    for field in ("payload", "chunks", "signal"):
        malformed = dict(base)
        malformed[field] = ["unexpected"]
        assert _parse_transfer_record(malformed) is None


def test_transfer_parser_rejects_malformed_chunk_index_arrays():
    from gui_dev_v3.data.records import _parse_transfer_record

    base = {
        "tid": 9,
        "payload": {"name": "file.bin", "size_bytes": 1},
        "chunks": {"total": 2, "received": 1, "missing_indexes": [], "received_indexes": [0]},
        "signal": {},
    }
    for indexes in ("0", {"0": 1}, [True], [-1], [2], [1.5]):
        malformed = json.loads(json.dumps(base))
        malformed["chunks"]["received_indexes"] = indexes
        assert _parse_transfer_record(malformed) is None


def test_history_keeps_distinct_records_when_firmware_reuses_tid(monkeypatch, tmp_path: Path):
    from gui_dev_v3.data import records

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()

    def payload(created_at: str, filename: str):
        return {
            "tid": 17,
            "payload": {"name": filename, "size_bytes": 4, "crc16_ccitt": "PASS"},
            "chunks": {"total": 1, "received": 1, "missing_indexes": [], "received_indexes": [0]},
            "signal": {"quality_status": "Good"},
            "status": "complete",
            "created_at": created_at,
        }

    first = payload("2026-11-13 03:00:00", "first.bin")
    second = payload("2026-11-13 04:00:00", "second.bin")
    (log_dir / "latest_rx_record.json").write_text(json.dumps(second), encoding="utf-8")
    (legacy_dir / "rx_transfer_17.json").write_text(json.dumps(first), encoding="utf-8")
    (legacy_dir / "rx_transfer_duplicate.json").write_text(json.dumps(second), encoding="utf-8")

    monkeypatch.setattr(records, "LOG_DIR", log_dir)
    monkeypatch.setattr(records, "LEGACY_TRANSFER_RECORDS_DIR", legacy_dir)

    history = records.load_real_transfer_history()

    assert {(record.tid, record.filename) for record in history} == {
        (17, "first.bin"),
        (17, "second.bin"),
    }
