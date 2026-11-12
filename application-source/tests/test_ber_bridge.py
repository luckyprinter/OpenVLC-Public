"""Method 2 file-comparison regression tests."""
from __future__ import annotations

from pathlib import Path

from gui_dev_v3.logic.ber_bridge import compare_files


def test_compare_files_counts_bit_errors_and_length_delta(tmp_path: Path) -> None:
    expected = tmp_path / "expected.bin"
    received = tmp_path / "received.bin"
    expected.write_bytes(bytes([0x00, 0xFF]))
    received.write_bytes(bytes([0x01, 0xFE, 0xAA]))

    result = compare_files(expected, received, mismatch_limit=10, block_size=1)

    assert result["expected_bytes"] == 2
    assert result["received_bytes"] == 3
    assert result["overlap_bytes"] == 2
    assert result["length_delta"] == 1
    assert result["overlap_bit_errors"] == 2
    assert result["strict_bit_errors"] == 10
    assert result["strict_bits"] == 24
    assert result["strict_ber"] == 10 / 24
    assert result["first_mismatch"] == 0
    assert [item["offset"] for item in result["preview"]] == [0, 1, 2]


def test_compare_files_tracks_first_mismatch_even_when_preview_is_disabled(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected.bin"
    received = tmp_path / "received.bin"
    expected.write_bytes(b"OpenVLC")
    received.write_bytes(b"OpenWLC")

    result = compare_files(expected, received, mismatch_limit=0)

    assert result["strict_bit_errors"] > 0
    assert result["first_mismatch"] == 4
    assert result["preview"] == []


def test_compare_files_reports_length_mismatch_without_overlap_errors(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected.bin"
    received = tmp_path / "received.bin"
    expected.write_bytes(b"")
    received.write_bytes(b"extra")

    result = compare_files(expected, received)

    assert result["overlap_bytes"] == 0
    assert result["overlap_bit_errors"] == 0
    assert result["strict_bit_errors"] == 40
    assert result["strict_ber"] == 1.0
    assert result["first_mismatch"] == 0


def test_compare_files_returns_unavailable_ber_for_two_empty_files(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected.bin"
    received = tmp_path / "received.bin"
    expected.write_bytes(b"")
    received.write_bytes(b"")

    result = compare_files(expected, received)

    assert result["strict_bits"] == 0
    assert result["strict_ber"] is None
    assert result["bit_accuracy"] is None
    assert result["first_mismatch"] is None
