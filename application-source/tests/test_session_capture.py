from dataclasses import replace
import json
import threading
from types import SimpleNamespace

import pytest

from gui_dev_v3.data import records
from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.data.session import build_empty_session
from gui_dev_v3.models import ChunkRecord, ChunkStatus, SessionCapture, TransferStatus


FIRST_CAPTURE_ID = "1" * 32
SECOND_CAPTURE_ID = "2" * 32


@pytest.fixture(autouse=True)
def isolate_legacy_capture_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(records, "LEGACY_CAPTURE_DIR", tmp_path / "no-legacy-captures")


@pytest.mark.parametrize("complete", [False, True])
def test_shutdown_drains_receiver_outcome_since_last_poll(monkeypatch, tmp_path, complete):
    from gui_dev_v3.rx.backends.physical import RXPhysicalBackend

    monkeypatch.setattr(records, "CAPTURE_DIR", tmp_path / "captures")
    state = RXAppState()
    backend = RXPhysicalBackend()
    backend._save_dir = tmp_path / "received"
    state._physical = backend
    published = []
    state.subscribe(lambda app: published.extend(app.completed_physical_transfers))
    name = b"file.bin".hex()
    backend._dispatch_line(f"RX_TRANSFER_NOTICE:23:9:1:29B1:{name}")
    capture_id = backend._active_capture_id
    assert capture_id is not None
    if complete:
        backend._dispatch_line(f"RX_FILE_HEX:23:DATA:9:1:29B1:{name}:{b'123456789'.hex()}")

    state.cleanup()

    capture = records.load_session_capture(23, capture_id=capture_id)
    assert capture is not None
    assert capture.status == ("Complete" if complete else "Stalled")
    assert [transfer.capture_id for transfer in published] == [capture_id]


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


def test_method2_result_is_persisted_only_for_matching_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(records, "CAPTURE_DIR", tmp_path / "captures")
    received_path = tmp_path / "received.bin"
    received_path.write_bytes(b"12")
    other_path = tmp_path / "different.bin"
    other_path.write_bytes(b"34")
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
        capture_id=SECOND_CAPTURE_ID,
        received_path=str(received_path),
    )
    first_capture = replace(
        capture, capture_id=FIRST_CAPTURE_ID, received_path=str(other_path)
    )
    records.save_session_capture(first_capture)
    records.save_session_capture(capture)

    state = RXAppState.__new__(RXAppState)
    state._lock = threading.Lock()
    state.transfer = replace(
        build_empty_session().latest_transfer,
        tid=42,
        filename=capture.filename,
        capture_id=SECOND_CAPTURE_ID,
        received_path=str(received_path),
    )
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
    state.set_method2_comparison(
        42, result, capture_id=FIRST_CAPTURE_ID, received_path=str(other_path)
    )
    state.set_method2_comparison(
        42, result, capture_id=SECOND_CAPTURE_ID, received_path=str(other_path)
    )
    assert state.get_method2_comparison() is None

    state.set_method2_comparison(
        42, result, capture_id=SECOND_CAPTURE_ID, received_path=str(received_path)
    )

    assert state.current_capture.ber == 11 / 24
    assert state.current_capture.ber_method == "method2_reference_file"
    assert records.load_session_capture(42, capture_id=SECOND_CAPTURE_ID).ber == 11 / 24
    assert records.load_session_capture(42, capture_id=FIRST_CAPTURE_ID).ber is None
    assert state.get_method2_comparison()["strict_ber"] == 11 / 24

    state.transfer = replace(
        state.transfer, capture_id=FIRST_CAPTURE_ID, received_path=str(other_path)
    )
    assert state.get_method2_comparison() is None


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
    state.transfer = replace(
        build_empty_session().latest_transfer, tid=71, filename="legacy-method2.bin"
    )
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


def _capture_payload(tid=42):
    return {
        "tid": tid,
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
    }


def test_load_session_capture_rejects_mismatched_embedded_tid(tmp_path, monkeypatch):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    monkeypatch.setattr(records, "CAPTURE_DIR", capture_dir)
    (capture_dir / "session_42.json").write_text(
        json.dumps(_capture_payload(tid=99)), encoding="utf-8"
    )

    assert records.load_session_capture(42) is None


def test_load_session_capture_rejects_malformed_sample_arrays(tmp_path, monkeypatch):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    monkeypatch.setattr(records, "CAPTURE_DIR", capture_dir)
    payload = _capture_payload()
    payload["pvo_samples"] = {"not": "an array"}
    (capture_dir / "session_42.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    assert records.load_session_capture(42) is None


def test_legacy_capture_migration_uses_unique_temporary_file(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "legacy-captures"
    legacy_dir.mkdir()
    current_dir = tmp_path / "current-captures"
    monkeypatch.setattr(records, "LEGACY_CAPTURE_DIR", legacy_dir)
    monkeypatch.setattr(records, "CAPTURE_DIR", current_dir)
    legacy_path = legacy_dir / "session_73.json"
    raw = json.dumps(_capture_payload(tid=73))
    legacy_path.write_text(raw, encoding="utf-8")

    capture = records.load_session_capture(73)

    assert capture is not None
    assert (current_dir / "session_73.json").read_text(encoding="utf-8") == raw
    assert legacy_path.read_text(encoding="utf-8") == raw
    assert not list(current_dir.glob(".*.tmp"))


def test_save_session_capture_preserves_structurally_malformed_existing_file(
    tmp_path, monkeypatch
):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    monkeypatch.setattr(records, "CAPTURE_DIR", capture_dir)
    path = capture_dir / "session_42.json"
    payload = _capture_payload()
    payload["pvo_samples"] = {"corrupt": "array"}
    original = json.dumps(payload).encode("utf-8")
    path.write_bytes(original)

    capture = SessionCapture(
        tid=42,
        timestamp="2026-11-13 12:00:00",
        filename="new-capture.bin",
        ber=None,
        crc_status="PASS",
        throughput_kbps=1.0,
        analog_time=[],
        pvo_samples=[],
        vref_samples=[],
        margin_samples=[],
        ook_bits=[],
        protocol_events=[],
    )

    records.save_session_capture(capture)

    assert path.read_bytes() == original
    assert not list(capture_dir.glob(".*.tmp"))


def test_exact_capture_lookup_never_uses_legacy_tid_match(tmp_path, monkeypatch):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    monkeypatch.setattr(records, "CAPTURE_DIR", capture_dir)
    (capture_dir / "session_42.json").write_text(json.dumps(_capture_payload()))

    assert records.load_session_capture(42, capture_id=FIRST_CAPTURE_ID) is None
    assert records.load_session_capture(42).filename == "capture.bin"


@pytest.mark.parametrize(
    ("failure_status", "failure_crc"),
    [(TransferStatus.STALLED, "Unknown"), (TransferStatus.CRC_FAILED, "FAIL")],
)
def test_physical_refresh_captures_fast_same_tid_outcomes_and_actual_telemetry(
    tmp_path, monkeypatch, failure_status, failure_crc
):
    monkeypatch.setattr(records, "CAPTURE_DIR", tmp_path / "captures")
    empty_session = build_empty_session()
    received_path = tmp_path / "received.bin"
    received_path.write_bytes(b"0123456789")
    complete = replace(
        empty_session.latest_transfer,
        tid=42,
        capture_id=FIRST_CAPTURE_ID,
        filename="received.bin",
        status=TransferStatus.COMPLETE,
        quality=replace(empty_session.latest_transfer.quality, crc_status="PASS"),
        size_bytes=10,
        received_path=str(received_path),
        received_bytes=10,
        duration_seconds=2.0,
    )
    failed = replace(
        complete,
        capture_id=SECOND_CAPTURE_ID,
        filename="failed.bin",
        status=failure_status,
        quality=replace(complete.quality, crc_status=failure_crc),
        size_bytes=500,
        received_path=None,
        received_bytes=None,
        duration_seconds=3.0,
    )
    backend = SimpleNamespace(refresh=lambda: SimpleNamespace(
        session=replace(empty_session, latest_transfer=failed, progress_percent=50),
        transfer=failed,
        activity_log=[],
        serial_connected=True,
        completed_transfers=(complete, failed),
        analog_sample=(FIRST_CAPTURE_ID, 0.5, 1.1, 0.7, 0.4),
    ))
    monkeypatch.setattr("gui_dev_v3.app_state.RXPhysicalBackend", lambda: backend)
    state = RXAppState()
    state.refresh()

    capture = records.load_session_capture(42, capture_id=FIRST_CAPTURE_ID)
    assert capture.status == "Complete"
    assert capture.crc_status == "PASS"
    assert capture.received_path == str(received_path)
    assert capture.received_bytes == 10
    assert capture.throughput_kbps == 0.04
    assert capture.analog_time == [0.5]
    assert capture.pvo_samples == [1.1]
    assert capture.ook_bits == []
    assert capture.ber is None

    failure = records.load_session_capture(42, capture_id=SECOND_CAPTURE_ID)
    assert failure.status == failure_status.value
    assert failure.crc_status == failure_crc
    assert failure.throughput_kbps is None
    assert failure.analog_time == []
    assert failure.protocol_events[-1]["event"] == failure_status.value
    assert state.current_capture == failure
    assert not state.is_receiving


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_inspect_refreshes_byte_explorer_for_reused_tid(qapp):
    from gui_dev_v3.rx.inspect_page import InspectPage

    page = InspectPage()
    transfer = replace(
        build_empty_session().latest_transfer,
        tid=42,
        capture_id=FIRST_CAPTURE_ID,
        filename="same-name.bin",
        chunks=[ChunkRecord(0, ChunkStatus.RECEIVED, received=b"x")],
    )
    state = SimpleNamespace(transfer=transfer, expected_file_path=None)
    page.refresh(state)
    assert page.chunk_table.item(0, 2).text() == "1 / 0 B"

    state.transfer = replace(
        transfer,
        capture_id=SECOND_CAPTURE_ID,
        chunks=[ChunkRecord(0, ChunkStatus.RECEIVED, received=b"yz")],
    )
    page.refresh(state)
    assert page.chunk_table.item(0, 2).text() == "2 / 0 B"
    page.close()


def test_analyzer_requires_reference_and_received_payload(qapp, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QWidget

    from gui_dev_v3.rx.ber_analyzer_page import BERAnalyzerPage
    from gui_dev_v3.rx.inspect_page import InspectPage

    monkeypatch.setattr(records, "CAPTURE_DIR", tmp_path / "captures")
    monkeypatch.setattr(
        "gui_dev_v3.app_state.RXPhysicalBackend",
        lambda: SimpleNamespace(refresh=lambda: None),
    )
    state = RXAppState()
    reference = tmp_path / "reference.bin"
    reference.write_bytes(bytes([0x0F]))
    received = tmp_path / "received.bin"
    received.write_bytes(bytes([0x0E]))
    state.transfer = replace(
        state.transfer,
        tid=42,
        capture_id=FIRST_CAPTURE_ID,
        filename="received.bin",
        status=TransferStatus.COMPLETE,
        received_path=str(received),
    )
    page = BERAnalyzerPage()
    page.refresh(state)
    assert state.get_method2_comparison() is None

    host = QWidget()
    host.state = state
    inspect = InspectPage(host)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(received), ""))
    inspect.inspect_load_btn.click()
    page.refresh(state)
    assert state.get_method2_comparison() is None

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(reference), ""))
    inspect.inspect_load_btn.click()
    inspect.refresh(state)
    assert inspect.ref_status_lbl.text() == "Original reference: reference.bin (1 B)"

    state.transfer = replace(state.transfer, received_path=str(tmp_path / "missing.bin"))
    page.refresh(state)
    assert state.get_method2_comparison() is None

    state.transfer = replace(state.transfer, received_path=str(received))
    page.refresh(state)
    assert state.get_method2_comparison()["strict_ber"] == 1 / 8
    assert page.lbl_strict_ber.text() == "12.500000 %"
    page.close()
    host.close()
