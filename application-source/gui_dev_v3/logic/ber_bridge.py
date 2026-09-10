"""BER and transfer quality logic — copied from vlc_migration and enhanced with beta helpers."""

from __future__ import annotations
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
        "overlap_ber": (overlap_bit_errors / overlap_bits) if overlap_bits else 0.0,
        "strict_ber": (strict_bit_errors / strict_bits) if strict_bits else 0.0,
        "bit_accuracy": (1.0 - (strict_bit_errors / strict_bits)) if strict_bits else 1.0,
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

