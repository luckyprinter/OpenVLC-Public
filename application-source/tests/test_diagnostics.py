"""Tests for opt-in, schema-limited local diagnostics."""
from __future__ import annotations

import json
import multiprocessing

from gui_dev_v3.diagnostics import LocalDiagnostics


def test_diagnostics_are_disabled_by_default(tmp_path):
    store = LocalDiagnostics(tmp_path / "diag.jsonl")
    assert store.enabled is False
    assert store.record("app_started", app_version="1.2.3") is False
    assert not store.path.exists()


def test_opt_in_records_only_allowlisted_typed_metadata(tmp_path):
    store = LocalDiagnostics(tmp_path / "diag.jsonl")
    store.set_enabled(True)

    assert store.record(
        "transfer_completed",
        role="tx",
        size_bucket="1_to_16kib",
        duration_ms=1200,
        chunk_count=8,
        crc_ok=True,
        ber_zero=True,
        filename="private-document.pdf",
        file_path="/home/user/private-document.pdf",
        payload="secret bytes",
        serial_output="RX_FILE_HEX:...",
    )

    entry = json.loads(store.export_text())
    assert entry["event"] == "transfer_completed"
    assert entry["data"] == {
        "role": "tx",
        "size_bucket": "1_to_16kib",
        "duration_ms": 1200,
        "chunk_count": 8,
        "crc_ok": True,
        "ber_zero": True,
    }
    assert "private-document" not in store.export_text()
    assert "secret bytes" not in store.export_text()


def test_invalid_enums_and_out_of_range_values_are_dropped(tmp_path):
    store = LocalDiagnostics(tmp_path / "diag.jsonl", enabled=True)
    store.record(
        "serial_probe",
        role="administrator",
        result="port /dev/ttyUSB0",
        baud_rate=999999999,
        duration_ms=-1,
    )
    entry = json.loads(store.export_text())
    assert entry["data"] == {}


def test_disable_stops_recording_and_clear_deletes_queue(tmp_path):
    store = LocalDiagnostics(tmp_path / "diag.jsonl", enabled=True)
    assert store.record("serial_disconnected", role="rx", reason_code="user_disconnect")
    store.set_enabled(False)
    assert store.record("app_started", app_version="1.0") is False
    assert len(store.export_text().splitlines()) == 1
    store.clear()
    assert store.export_text() == ""



def test_non_finite_numeric_values_are_rejected(tmp_path):
    store = LocalDiagnostics(tmp_path / "diag.jsonl", enabled=True)
    store.record("serial_scan", role="rx", ports_seen=float("nan"), duration_ms=float("inf"))
    entry = json.loads(store.export_text())
    assert entry["data"] == {"role": "rx"}



def _write_diagnostics_from_process(path: str, role: str, count: int) -> None:
    store = LocalDiagnostics(path, enabled=True)
    for _ in range(count):
        assert store.record("serial_disconnected", role=role, reason_code="user_disconnect")


def test_tx_and_rx_processes_can_append_to_one_queue_without_corruption(tmp_path):
    path = str(tmp_path / "shared-diagnostics.jsonl")
    context = multiprocessing.get_context("spawn")
    tx = context.Process(target=_write_diagnostics_from_process, args=(path, "tx", 60))
    rx = context.Process(target=_write_diagnostics_from_process, args=(path, "rx", 60))

    tx.start()
    rx.start()
    tx.join(timeout=20)
    rx.join(timeout=20)

    if tx.is_alive():
        tx.terminate()
        tx.join()
        raise AssertionError("TX diagnostics writer did not finish")
    if rx.is_alive():
        rx.terminate()
        rx.join()
        raise AssertionError("RX diagnostics writer did not finish")
    assert tx.exitcode == 0
    assert rx.exitcode == 0

    lines = (tmp_path / "shared-diagnostics.jsonl").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines]
    assert len(entries) == 120
    assert sum(entry["data"]["role"] == "tx" for entry in entries) == 60
    assert sum(entry["data"]["role"] == "rx" for entry in entries) == 60
