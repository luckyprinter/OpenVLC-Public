import pytest

from gui_dev_v3.serial.transfer_plan import (
    MAX_STREAM_CHUNKS,
    plan_stream_parts,
)
from gui_dev_v3.serial.session import crc16_ccitt


@pytest.mark.parametrize(
    ("chunk_size", "expected_part_size"),
    [
        (16, 16 * MAX_STREAM_CHUNKS),
        (128, 128 * MAX_STREAM_CHUNKS),
        (256, 80 * 1024),
        (512, 80 * 1024),
        (1024, 80 * 1024),
    ],
)
def test_part_size_respects_byte_and_chunk_limits(chunk_size, expected_part_size):
    part_size, part_count = plan_stream_parts(200_000, chunk_size)
    assert part_size == expected_part_size
    assert part_count >= 1
    assert (part_size + chunk_size - 1) // chunk_size <= MAX_STREAM_CHUNKS
    assert part_size <= 80 * 1024


def test_small_file_uses_one_part():
    assert plan_stream_parts(1024, 256) == (80 * 1024, 1)


def test_crc16_can_be_updated_incrementally():
    payload = bytes(range(256)) * 257
    whole = crc16_ccitt(payload)
    first = crc16_ccitt(payload[:12345])
    incremental = crc16_ccitt(payload[12345:], initial_crc=first)
    assert incremental == whole


@pytest.mark.parametrize(
    ("file_size", "chunk_size"),
    [(-1, 256), (100, 0), (100, 256)],
)
def test_invalid_transfer_plan_inputs(file_size, chunk_size):
    if file_size < 0 or chunk_size == 0:
        with pytest.raises(ValueError):
            plan_stream_parts(file_size, chunk_size)
