"""BER and transfer quality logic — copied from vlc_migration and enhanced with beta helpers."""

from __future__ import annotations
from pathlib import Path
import os
from gui_dev_v3.models import ChunkRecord, ChunkStatus, TransferQuality


def generate_ber_test_payload(size: int, seed: int) -> bytes:
    """Generate reference payload using Linear Congruential Generator (LCG) seed."""
    size = max(0, int(size))
    state = int(seed) & 0xFFFFFFFF
    out = bytearray()
    for _ in range(size):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        out.append((state >> 24) & 0xFF)
    return bytes(out)


def parse_ber_test_name(name: str) -> tuple[int, int] | None:
    """Parse filename in format 'BERTEST~<size>~<seed_hex>.bin'."""
    base = (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." in base:
        base = base.rsplit(".", 1)[0]
    parts = base.split("~")
    if len(parts) != 3 or parts[0] != "BERTEST":
        return None
    try:
        size = int(parts[1])
        seed = int(parts[2], 16)
    except ValueError:
        return None
    if size < 0:
        return None
    return size, seed


def compare_payload_bits(expected: bytes, received: bytes, mismatch_limit: int = 50) -> dict:
    """Perform detailed bit-level and byte-level comparison between expected and received payloads."""
    expected = expected or b""
    received = received or b""
    overlap = min(len(expected), len(received))
    overlap_bit_errors = 0
    byte_mismatches = 0
    first_mismatch = None
    preview = []

    for index in range(overlap):
        xor = expected[index] ^ received[index]
        if xor:
            byte_mismatches += 1
            overlap_bit_errors += bin(xor).count("1")
            if first_mismatch is None:
                first_mismatch = index
            if len(preview) < mismatch_limit:
                preview.append({
                    "offset": index,
                    "expected": expected[index],
                    "received": received[index],
                    "bit_errors": bin(xor).count("1"),
                })

    length_delta = len(received) - len(expected)
    missing_or_extra_bits = abs(length_delta) * 8
    strict_bit_errors = overlap_bit_errors + missing_or_extra_bits
    overlap_bits = overlap * 8
    strict_bits = max(len(expected), len(received)) * 8

    if first_mismatch is None and length_delta:
        first_mismatch = overlap
    if length_delta and len(preview) < mismatch_limit:
        preview.append({
            "offset": overlap,
            "expected": None if length_delta > 0 else "missing",
            "received": "extra" if length_delta > 0 else None,
            "bit_errors": missing_or_extra_bits,
        })

    return {
        "expected_bytes": len(expected),
        "received_bytes": len(received),
        "overlap_bytes": overlap,
        "length_delta": length_delta,
        "byte_mismatches": byte_mismatches + abs(length_delta),
        "overlap_bit_errors": overlap_bit_errors,
        "strict_bit_errors": strict_bit_errors,
        "overlap_bits": overlap_bits,
        "strict_bits": strict_bits,
        "overlap_ber": (overlap_bit_errors / overlap_bits) if overlap_bits else None,
        "strict_ber": (strict_bit_errors / strict_bits) if strict_bits else None,
        "bit_accuracy": (1.0 - (strict_bit_errors / strict_bits)) if strict_bits else None,
        "first_mismatch": first_mismatch,
        "preview": preview,
    }


def transfer_quality_from_chunks(
    chunks: list[ChunkRecord],
    label: str = "Unknown",
    crc_status: str = "Unknown",
) -> TransferQuality:
    total_bits = sum(chunk.expected_size * 8 for chunk in chunks)
    bit_errors = sum(chunk.different_bytes * 8 for chunk in chunks)
    compared_bytes = sum(min(len(chunk.expected), len(chunk.received)) for chunk in chunks if chunk.received)
    missing_chunks = sum(1 for chunk in chunks if chunk.status == ChunkStatus.MISSING)
    missing_bytes = sum(chunk.missing_bytes for chunk in chunks)
    strict_ber = bit_errors / max(total_bits, 1)
    bit_accuracy = 100.0 - (bit_errors / max(total_bits, 1)) * 100.0
    recovered = sum(1 for c in chunks if c.status == ChunkStatus.MATCH)
    recovery_rate = (recovered / max(len(chunks), 1)) * 100.0
    issues = [chunk for chunk in chunks if chunk.status in (ChunkStatus.MISSING, ChunkStatus.DIFFERENT)]
    first_issue = f"Chunk {issues[0].index}: {issues[0].status.value}" if issues else "None"
    return TransferQuality(
        label=label,
        strict_ber=strict_ber,
        bit_accuracy=bit_accuracy,
        bit_errors=bit_errors,
        total_bits=total_bits,
        compared_bytes=compared_bytes,
        missing_chunks=missing_chunks,
        missing_bytes=missing_bytes,
        first_issue=first_issue,
        crc_status=crc_status,
        recovery_rate=recovery_rate,
    )




def test_compare_payload_bits_compatibility(expected: bytes, received: bytes) -> dict:
    """Backward-compatible in-memory comparison used by legacy analyzer tests."""
    expected = bytes(expected or b"")
    received = bytes(received or b"")
    overlap = min(len(expected), len(received))
    bit_errors = 0
    byte_mismatches = 0
    preview = []
    for offset in range(overlap):
        xor = expected[offset] ^ received[offset]
        if xor:
            errors = xor.bit_count()
            bit_errors += errors
            byte_mismatches += 1
            if len(preview) < 50:
                preview.append({"offset": offset, "expected": expected[offset],
                                "received": received[offset], "bit_errors": errors})
    delta = len(received) - len(expected)
    missing_extra = abs(delta) * 8
    total_bits = max(len(expected), len(received)) * 8
    if delta and len(preview) < 50:
        preview.append({"offset": overlap,
                        "expected": "EOF" if delta > 0 else "missing",
                        "received": "extra" if delta > 0 else "EOF",
                        "bit_errors": missing_extra})
    errors = bit_errors + missing_extra
    return {
        "expected_bytes": len(expected), "received_bytes": len(received),
        "overlap_bytes": overlap, "length_delta": delta,
        "byte_mismatches": byte_mismatches + abs(delta),
        "overlap_bit_errors": bit_errors, "strict_bit_errors": errors,
        "overlap_bits": overlap * 8, "strict_bits": total_bits,
        "overlap_ber": bit_errors / (overlap * 8) if overlap else None,
        "strict_ber": errors / total_bits if total_bits else None,
        "bit_accuracy": 1.0 - errors / total_bits if total_bits else None,
        "first_mismatch": preview[0]["offset"] if preview else None,
        "preview": preview,
    }

def compare_files(expected_path: str | Path, received_path: str | Path, *, mismatch_limit: int = 50, block_size: int = 65536) -> dict:
    """Compare files in bounded blocks; missing/extra bytes count as eight errors each."""
    expected_path, received_path = Path(expected_path), Path(received_path)
    if mismatch_limit < 0 or block_size < 1:
        raise ValueError("mismatch_limit must be non-negative and block_size positive")
    es, rs = expected_path.stat(), received_path.stat()
    expected_size, received_size = es.st_size, rs.st_size
    overlap = min(expected_size, received_size)
    remaining, offset = overlap, 0
    bit_errors = byte_mismatches = 0
    first_mismatch = None
    preview = []
    with expected_path.open("rb") as ef, received_path.open("rb") as rf:
        while remaining:
            count = min(block_size, remaining)
            eb, rb = ef.read(count), rf.read(count)
            if len(eb) != count or len(rb) != count:
                raise OSError("A file changed during BER comparison")
            for i, (a, b) in enumerate(zip(eb, rb)):
                xor = a ^ b
                if xor:
                    errors = xor.bit_count()
                    bit_errors += errors
                    byte_mismatches += 1
                    if first_mismatch is None:
                        first_mismatch = offset + i
                    if len(preview) < mismatch_limit:
                        preview.append({"offset": offset+i, "expected": a, "received": b, "bit_errors": errors})
            offset += count
            remaining -= count
    ea, ra = expected_path.stat(), received_path.stat()
    if (es.st_size, es.st_mtime_ns, rs.st_size, rs.st_mtime_ns) != (ea.st_size, ea.st_mtime_ns, ra.st_size, ra.st_mtime_ns):
        raise OSError("A file changed during BER comparison")
    delta = received_size - expected_size
    errors = bit_errors + abs(delta) * 8
    total_bits = max(expected_size, received_size) * 8
    if delta:
        if first_mismatch is None:
            first_mismatch = overlap
        if len(preview) < mismatch_limit:
            preview.append({"offset": overlap, "expected": "EOF" if delta > 0 else "missing", "received": "extra" if delta > 0 else "EOF", "bit_errors": abs(delta)*8})
    return {"expected_bytes": expected_size, "received_bytes": received_size, "overlap_bytes": overlap,
            "length_delta": delta, "byte_mismatches": byte_mismatches + abs(delta),
            "overlap_bit_errors": bit_errors, "strict_bit_errors": errors, "strict_bits": total_bits,
            "strict_ber": errors / total_bits if total_bits else None,
            "overlap_ber": bit_errors / (overlap*8) if overlap else None,
            "bit_accuracy": 1.0 - errors/total_bits if total_bits else None,
            "first_mismatch": first_mismatch, "preview": preview}
