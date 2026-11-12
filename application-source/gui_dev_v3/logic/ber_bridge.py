"""Streaming Method 2 comparison of the selected original and reconstructed RX file."""
from __future__ import annotations
from pathlib import Path

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
    if delta and len(preview) < mismatch_limit:
        preview.append({"offset": overlap, "expected": "EOF" if delta > 0 else "missing", "received": "extra" if delta > 0 else "EOF", "bit_errors": abs(delta)*8})
    return {"expected_bytes": expected_size, "received_bytes": received_size, "overlap_bytes": overlap,
            "length_delta": delta, "byte_mismatches": byte_mismatches + abs(delta),
            "overlap_bit_errors": bit_errors, "strict_bit_errors": errors, "strict_bits": total_bits,
            "strict_ber": errors / total_bits if total_bits else None,
            "overlap_ber": bit_errors / (overlap*8) if overlap else None,
            "bit_accuracy": 1.0 - errors/total_bits if total_bits else None,
            "first_mismatch": preview[0]["offset"] if preview else None, "preview": preview}
