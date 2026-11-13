"""Firmware-aligned limits for multi-part optical transfers."""

MAX_STREAM_CHUNKS = 512
MAX_BATCH_PARTS = 1024


def plan_stream_parts(
    file_size: int,
    chunk_size: int,
    max_file_bytes: int = 80 * 1024,
    max_chunks: int = MAX_STREAM_CHUNKS,
) -> tuple[int, int]:
    """Return a part size/count that obeys both ESP32 receive limits."""
    if file_size < 0:
        raise ValueError("file_size cannot be negative")
    if chunk_size < 1 or max_file_bytes < 1 or max_chunks < 1:
        raise ValueError("chunk size and firmware limits must be positive")
    part_size = min(int(max_file_bytes), int(chunk_size) * int(max_chunks))
    part_count = max(1, (int(file_size) + part_size - 1) // part_size)
    return part_size, part_count
