from gui_dev_v3.logic.ber_bridge import compare_files, compare_payload_bits


def test_compare_payload_bits_counts_bit_errors_and_length_delta():
    result = compare_payload_bits(b"\\x00\\xff", b"\\x01\\xfe\\x10")

    assert result["overlap_bytes"] == 2
    assert result["strict_bit_errors"] == 2 + 8
    assert result["length_delta"] == 1
    assert result["strict_bits"] == 24
    assert result["strict_ber"] == 11 / 24


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
    expected.write_bytes(b"\\x00\\x0f\\xaa")
    received.write_bytes(b"\\x01\\x03")

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
    assert result["strict_ber"] == 0.0
    assert result["bit_accuracy"] == 1.0
