import json
from pathlib import Path

from gui_dev_v3.data import records


def test_load_session_capture_preserves_unavailable_ber(tmp_path, monkeypatch):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir(parents=True)
    monkeypatch.setattr(records, "CAPTURE_DIR", capture_dir)
    (capture_dir / "session_42.json").write_text(
        json.dumps({
            "tid": 42,
            "timestamp": "2026-11-13 12:00:00",
            "filename": "capture.bin",
            "ber": None,
            "crc_status": "PASS",
            "throughput_kbps": 1.25,
            "analog_time": [],
            "pvo_samples": [],
            "vref_samples": [],
            "margin_samples": [],
            "ook_bits": [],
            "protocol_events": [],
            "ber_method": "unavailable",
        }),
        encoding="utf-8",
    )

    capture = records.load_session_capture(42)

    assert capture is not None
    assert capture.ber is None
    assert capture.ber_method == "unavailable"

def test_load_legacy_capture_defaults_missing_ber_method(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    capture_dir = tmp_path / ".vlc_rx" / "captures"
    capture_dir.mkdir(parents=True)
    (capture_dir / "session_7.json").write_text(
        json.dumps({
            "tid": 7,
            "timestamp": "2026-11-13 12:00:00",
            "filename": "legacy.bin",
            "ber": 0.0,
            "crc_status": "PASS",
            "throughput_kbps": 0.0,
            "analog_time": [],
            "pvo_samples": [],
            "vref_samples": [],
            "margin_samples": [],
            "ook_bits": [],
            "protocol_events": [],
        }),
        encoding="utf-8",
    )

    capture = records.load_session_capture(7)

    assert capture is not None
    assert capture.ber == 0.0
    assert capture.ber_method == "unavailable"

def test_transfer_history_does_not_infer_ber_from_crc_or_chunks():
    record = records._parse_transfer_record({
        "tid": 21,
        "status": "complete",
        "created_at": "2026-11-13 12:00:00",
        "payload": {
            "name": "received.bin",
            "size_bytes": 16,
            "crc16_ccitt": "PASS",
        },
        "chunks": {
            "total": 2,
            "received": 2,
            "received_indexes": [0, 1],
            "missing_indexes": [],
        },
        "signal": {"quality_status": "Good"},
    })

    assert record is not None
    assert record.quality.crc_status == "PASS"
    assert record.quality.strict_ber is None
    assert record.quality.bit_accuracy is None
    assert record.quality.bit_errors is None
