from gui_dev_v3.logic.ber_bridge import compare_files

def test_method2_compares_bits_and_counts_missing_bytes(tmp_path):
    expected = tmp_path / 'original.bin'
    received = tmp_path / 'received.bin'
    expected.write_bytes(bytes([0x00, 0x0F, 0xAA]))
    received.write_bytes(bytes([0x01, 0x03]))
    result = compare_files(expected, received, block_size=1)
    assert result['strict_bit_errors'] == 11
    assert result['strict_bits'] == 24
    assert result['strict_ber'] == 11 / 24
    assert result['length_delta'] == -1

def test_method2_empty_files_have_undefined_ber(tmp_path):
    expected = tmp_path / 'original.bin'
    received = tmp_path / 'received.bin'
    expected.write_bytes(b'')
    received.write_bytes(b'')
    result = compare_files(expected, received)
    assert result['strict_bits'] == 0
    assert result['strict_ber'] is None
    assert result['bit_accuracy'] is None

def test_method2_identical_large_files_are_streamed(tmp_path):
    expected = tmp_path / 'original.bin'
    received = tmp_path / 'received.bin'
    payload = bytes(range(256)) * 4096
    expected.write_bytes(payload)
    received.write_bytes(payload)
    result = compare_files(expected, received, block_size=4093)
    assert result['strict_bit_errors'] == 0
    assert result['strict_ber'] == 0.0
    assert result['preview'] == []
