import json
import threading
from types import SimpleNamespace

import pytest

from gui_dev_v3.data import records
from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.models import SessionCapture


@pytest.fixture(autouse=True)
def isolate_legacy_capture_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(records, "LEGACY_CAPTURE_DIR", tmp_path / "no-legacy-captures")


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
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir(parents=True)
    monkeypatch.setattr(records, "CAPTURE_DIR", capture_dir)
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

def test_legacy_capture_is_readable_and_copied_without_deleting_source(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "legacy-captures"
    legacy_dir.mkdir()
    current_dir = tmp_path / "app-data-captures"
    monkeypatch.setattr(records, "LEGACY_CAPTURE_DIR", legacy_dir)
    monkeypatch.setattr(records, "CAPTURE_DIR", current_dir)
    legacy_path = legacy_dir / "session_88.json"
    original = {
        "tid": 88,
        "timestamp": "2026-10-01 10:00:00",
        "filename": "old.bin",
        "ber": 0.0,
        "crc_status": "PASS",
        "throughput_kbps": 0.0,
        "analog_time": [],
        "pvo_samples": [],
        "vref_samples": [],
        "margin_samples": [],
        "ook_bits": [],
        "protocol_events": [],
    }
    raw = json.dumps(original)
    legacy_path.write_text(raw, encoding="utf-8")

    capture = records.load_session_capture(88)

    assert capture is not None
    assert capture.filename == "old.bin"
    assert (current_dir / "session_88.json").read_text(encoding="utf-8") == raw
    assert legacy_path.read_text(encoding="utf-8") == raw


def test_method2_result_is_persisted_only_for_matching_capture(monkeypatch):
    import gui_dev_v3.data as data_module

    capture = SessionCapture(
        tid=42,
        timestamp="2026-11-13 12:00:00",
        filename="received.bin",
        ber=None,
        ber_method="unavailable",
        crc_status="PASS",
        throughput_kbps=10.0,
        analog_time=[],
        pvo_samples=[],
        vref_samples=[],
        margin_samples=[],
        ook_bits=[],
        protocol_events=[],
    )
    saved = []
    monkeypatch.setattr(data_module, "save_session_capture", saved.append)

    state = RXAppState.__new__(RXAppState)
    state._lock = threading.Lock()
    state.transfer = SimpleNamespace(tid=42)
    state.current_capture = capture
    state._method2_comparison = None

    result = {
        "overlap_ber": 0.0,
        "strict_ber": 11 / 24,
        "bit_accuracy": 13 / 24,
        "strict_bit_errors": 11,
        "overlap_bytes": 2,
        "expected_bytes": 3,
        "length_delta": -1,
    }
    state.set_method2_comparison(42, result)

    assert state.current_capture.ber == 11 / 24
    assert state.current_capture.ber_method == "method2_reference_file"
    assert saved == [state.current_capture]
    assert state.get_method2_comparison()["strict_ber"] == 11 / 24

    state.set_method2_comparison(99, {**result, "strict_ber": 0.0})
    assert state.current_capture.ber == 11 / 24
    assert state.get_method2_comparison()["strict_ber"] == 11 / 24


def test_app_state_reads_legacy_method2_capture():
    capture = SessionCapture(
        tid=71,
        timestamp="2026-11-12 12:00:00",
        filename="legacy-method2.bin",
        ber=0.0125,
        ber_method="method2",
        crc_status="PASS",
        throughput_kbps=5.0,
        analog_time=[],
        pvo_samples=[],
        vref_samples=[],
        margin_samples=[],
        ook_bits=[],
        protocol_events=[],
    )
    state = RXAppState.__new__(RXAppState)
    state._lock = threading.Lock()
    state.transfer = SimpleNamespace(tid=71)
    state.current_capture = capture
    state._method2_comparison = None

    comparison = state.get_method2_comparison()

    assert comparison is not None
    assert comparison["strict_ber"] == 0.0125



def test_save_session_capture_preserves_corrupt_existing_file(tmp_path, monkeypatch):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir(parents=True)
    monkeypatch.setattr(records, "CAPTURE_DIR", capture_dir)
    path = capture_dir / "session_42.json"
    original = b"{ broken capture record"
    path.write_bytes(original)

    capture = SessionCapture(
        tid=42,
        timestamp="2026-11-13 12:00:00",
        filename="capture.bin",
        ber=0.0,
        crc_status="PASS",
        throughput_kbps=1.0,
        analog_time=[],
        pvo_samples=[],
        vref_samples=[],
        margin_samples=[],
        ook_bits=[],
        protocol_events=[],
        ber_method="method2_reference_file",
    )

    records.save_session_capture(capture)

    assert path.read_bytes() == original
    assert list(capture_dir.glob("*.tmp")) == []
    assert list(capture_dir.glob(".*.tmp")) == []
