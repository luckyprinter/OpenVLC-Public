"""Reference-file comparison helpers for Method 2 BER measurement."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from gui_dev_v3.models import ChunkRecord, TransferQuality


def _build_result(expected_size: int, received_size: int, overlap_bit_errors: int,
                  overlap_byte_mismatches: int, preview: list[dict]) -> dict:
    overlap_bytes = min(expected_size, received_size)
    overlap_bits = overlap_bytes * 8
    strict_bits = max(expected_size, received_size) * 8
    length_delta = received_size - expected_size
    strict_bit_errors = overlap_bit_errors + abs(length_delta) * 8
    strict_ber = strict_bit_errors / strict_bits if strict_bits else 0.0
    overlap_ber = overlap_bit_errors / overlap_bits if overlap_bits else 0.0
    return {
        "expected_bytes": expected_size, "received_bytes": received_size,
        "overlap_bytes": overlap_bytes, "overlap_ber": overlap_ber,
        "strict_ber": strict_ber, "bit_accuracy": 1.0 - strict_ber,
        "overlap_bit_errors": overlap_bit_errors,
        "strict_bit_errors": strict_bit_errors, "strict_bits": strict_bits,
        "byte_mismatches": overlap_byte_mismatches + abs(length_delta),
        "length_delta": length_delta,
        "first_mismatch": preview[0]["offset"] if preview else None,
        "preview": preview,
    }


def compare_payload_bits(expected: bytes, received: bytes, mismatch_limit: int = 50) -> dict:
    """Compare two byte payloads bit-for-bit, including missing/extra length."""
    if mismatch_limit < 0:
        raise ValueError("mismatch_limit cannot be negative")
    expected, received = bytes(expected), bytes(received)
    overlap = min(len(expected), len(received))
    bit_errors = byte_mismatches = 0
    preview: list[dict] = []
    for offset in range(overlap):
        exp_val, rec_val = expected[offset], received[offset]
        xor = exp_val ^ rec_val
        if xor:
            errors = xor.bit_count()
            bit_errors += errors
            byte_mismatches += 1
            if len(preview) < mismatch_limit:
                preview.append({"offset": offset, "expected": exp_val, "received": rec_val, "bit_errors": errors})
    if len(expected) != len(received) and len(preview) < mismatch_limit:
        preview.append({"offset": overlap,
                        "expected": "EOF" if overlap >= len(expected) else expected[overlap],
                        "received": "EOF" if overlap >= len(received) else received[overlap],
                        "bit_errors": abs(len(expected) - len(received)) * 8})
    return _build_result(len(expected), len(received), bit_errors, byte_mismatches, preview)


def compare_files(expected_path: str | Path, received_path: str | Path,
                  mismatch_limit: int = 50, block_size: int = 64 * 1024) -> dict:
    """Stream-compare the original reference and reconstructed RX file."""
    expected_path, received_path = Path(expected_path), Path(received_path)
    if mismatch_limit < 0:
        raise ValueError("mismatch_limit cannot be negative")
    if block_size < 1:
        raise ValueError("block_size must be positive")
    expected_before, received_before = expected_path.stat(), received_path.stat()
    expected_size, received_size = expected_before.st_size, received_before.st_size
    overlap = min(expected_size, received_size)
    remaining, offset = overlap, 0
    bit_errors = byte_mismatches = 0
    preview: list[dict] = []
    with expected_path.open("rb") as expected_file, received_path.open("rb") as received_file:
        while remaining:
            count = min(int(block_size), remaining)
            expected_block, received_block = expected_file.read(count), received_file.read(count)
            if len(expected_block) != count or len(received_block) != count:
                raise OSError("A comparison file changed during Method 2 BER calculation")
            for index, (exp_val, rec_val) in enumerate(zip(expected_block, received_block)):
                xor = exp_val ^ rec_val
                if xor:
                    errors = xor.bit_count()
                    bit_errors += errors
                    byte_mismatches += 1
                    if len(preview) < mismatch_limit:
                        preview.append({"offset": offset + index, "expected": exp_val,
                                        "received": rec_val, "bit_errors": errors})
            offset += count
            remaining -= count
    expected_after, received_after = expected_path.stat(), received_path.stat()
    if (
        expected_before.st_size != expected_after.st_size
        or expected_before.st_mtime_ns != expected_after.st_mtime_ns
        or received_before.st_size != received_after.st_size
        or received_before.st_mtime_ns != received_after.st_mtime_ns
    ):
        raise OSError("A comparison file changed during Method 2 BER calculation")
    if expected_size != received_size and len(preview) < mismatch_limit:
        preview.append({"offset": overlap,
                        "expected": "EOF" if overlap >= expected_size else "additional data",
                        "received": "EOF" if overlap >= received_size else "additional data",
                        "bit_errors": abs(expected_size - received_size) * 8})
    return _build_result(expected_size, received_size, bit_errors, byte_mismatches, preview)


def transfer_quality_from_chunks(chunks: Iterable[ChunkRecord]) -> TransferQuality:
    """Build Method 2 quality only when chunks contain reference bytes."""
    chunks = list(chunks)
    expected = b"".join(chunk.expected for chunk in chunks)
    received = b"".join(chunk.received for chunk in chunks)
    missing = sum(1 for chunk in chunks if str(chunk.status).lower().endswith("missing"))
    crc_values = [chunk.crc_ok for chunk in chunks if chunk.crc_ok is not None]
    crc_status = "PASS" if crc_values and all(crc_values) else "FAIL" if crc_values else "Unknown"
    if not expected:
        return TransferQuality(label="Reference comparison unavailable", strict_ber=None,
                               bit_accuracy=None, bit_errors=None, total_bits=0,
                               compared_bytes=0, missing_chunks=missing, missing_bytes=0,
                               first_issue="Load the original reference file",
                               crc_status=crc_status, recovery_rate=0.0)
    result = compare_payload_bits(expected, received)
    return TransferQuality(
        label="Reference match" if result["strict_ber"] == 0 else "Reference mismatch",
        strict_ber=result["strict_ber"], bit_accuracy=result["bit_accuracy"] * 100.0,
        bit_errors=result["strict_bit_errors"], total_bits=result["strict_bits"],
        compared_bytes=result["overlap_bytes"], missing_chunks=missing,
        missing_bytes=abs(result["length_delta"]),
        first_issue=f"Byte offset {result['first_mismatch']}" if result["first_mismatch"] is not None else None,
        crc_status=crc_status, recovery_rate=(len(received) / max(len(expected), 1)) * 100.0,
    )
