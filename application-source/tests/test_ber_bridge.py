import threading
from types import SimpleNamespace

from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.logic.ber_bridge import compare_files, compare_payload_bits
from gui_dev_v3.models import SessionCapture


def test_compare_payload_bits_counts_bit_errors_and_length_delta():
    result = compare_payload_bits(b"\x00\xff", b"\x01\xfe\x10")

    assert result["overlap_bytes"] == 2
    assert result["strict_bit_errors"] == 2 + 8
    assert result["length_delta"] == 1
    assert result["strict_bits"] == 24
    assert result["strict_ber"] == 10 / 24


def test_compare_files_streams_identical_files(tmp_path):
    expected = tmp_path / "original.bin"
    received = tmp_path / "received.bin"
    payload = bytes(range(256)) * 5
    expected.write_bytes(payload)
    received.write_bytes(payload)

    result = compare_files(expected, received, block_size=127)

    assert result["expected_bytes"] == len(payload)
    assert result["received_bytes"] == len(payload)
    assert result["strict_bit_errors"] == 0
    assert result["strict_ber"] == 0.0
    assert result["bit_accuracy"] == 1.0
    assert result["preview"] == []


def test_compare_files_reports_bit_and_size_errors(tmp_path):
    expected = tmp_path / "original.bin"
    received = tmp_path / "received.bin"
    expected.write_bytes(b"\x00\x0f\xaa")
    received.write_bytes(b"\x01\x03")

    result = compare_files(expected, received, block_size=1)

    # 1 bit in byte 0, 2 bits in byte 1, and one missing byte (8 bits).
    assert result["strict_bit_errors"] == 11
    assert result["length_delta"] == -1
    assert result["strict_bits"] == 24
    assert result["strict_ber"] == 11 / 24
    assert result["first_mismatch"] == 0
    assert len(result["preview"]) == 3


def test_compare_files_handles_empty_reference(tmp_path):
    expected = tmp_path / "empty.bin"
    received = tmp_path / "received.bin"
    expected.write_bytes(b"")
    received.write_bytes(b"")

    result = compare_files(expected, received)

    assert result["strict_bits"] == 0
    assert result["strict_ber"] is None
    assert result["overlap_ber"] is None
    assert result["bit_accuracy"] is None



def test_app_state_method2_uses_selected_reference_and_received_path(tmp_path):
    expected = tmp_path / "original.bin"
    received = tmp_path / "received.bin"
    expected.write_bytes(b"\x00\x0f\xaa")
    received.write_bytes(bytes([0x01, 0x03]))

    # Avoid constructing a serial backend; exercise only the comparison method.
    state = RXAppState.__new__(RXAppState)
    state._lock = threading.Lock()
    state._subscribers = []
    state.expected_file_path = str(expected)
    state.session = SimpleNamespace(
        latest_transfer=SimpleNamespace(tid=42, received_path=str(received))
    )
    state._method2_cache_key = None
    state._method2_cache = None

    result = state.get_method2_comparison()

    assert result is not None
    assert result["strict_bit_errors"] == 11
    assert result["strict_ber"] == 11 / 24


def test_late_reference_selection_updates_and_persists_completed_capture(tmp_path, monkeypatch):
    expected = tmp_path / "original.bin"
    received = tmp_path / "received.bin"
    expected.write_bytes(bytes([0x00, 0x0F, 0xAA]))
    received.write_bytes(bytes([0x01, 0x03]))
    capture = SessionCapture(
        tid=42, timestamp="2026-11-12 12:00:00", filename="received.bin",
        ber=None, ber_method=None, crc_status="PASS", throughput_kbps=10.0,
        analog_time=[], pvo_samples=[], vref_samples=[], margin_samples=[],
        ook_bits=[], protocol_events=[],
    )
    saved = []
    monkeypatch.setattr("gui_dev_v3.data.save_session_capture", saved.append)

    state = RXAppState.__new__(RXAppState)
    state._lock = threading.Lock()
    state._subscribers = []
    state.expected_file_path = None
    state.expected_file_data = None
    state._method2_cache_key = None
    state._method2_cache = None
    state.session = SimpleNamespace(
        latest_transfer=SimpleNamespace(tid=42, received_path=str(received))
    )
    state.current_capture = capture

    state.load_expected_file(str(expected))

    assert state.current_capture is not capture
    assert state.current_capture.ber_method == "method2"
    assert state.current_capture.ber == 11 / 24
    assert saved == [state.current_capture]
