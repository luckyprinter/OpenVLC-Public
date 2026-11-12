"""Bounded, validated assembly of multi-part optical file transfers."""
from __future__ import annotations
import time
import threading
from dataclasses import dataclass, field
from typing import Any
from gui_dev_v3.serial.transfer_plan import MAX_BATCH_PARTS

@dataclass
class _PendingBatch:
    group_id: str
    part_count: int
    full_crc: int
    filename: str
    started_monotonic: float
    last_seen: float
    parts: dict[int, bytes] = field(default_factory=dict)
    chunks: dict[int, int] = field(default_factory=dict)
    tids: dict[int, int] = field(default_factory=dict)
    total_bytes: int = 0

class BatchAssembler:
    """Assemble parts in index order and reject ambiguous retransmissions."""
    def __init__(self, *, ttl_seconds: float = 300.0, max_pending_batches: int = 2,
                 max_parts: int = MAX_BATCH_PARTS, max_batch_bytes: int = 80 * 1024 * 1024,
                 max_part_chunks: int = 512) -> None:
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self.max_pending_batches = max(1, int(max_pending_batches))
        self.max_parts = max(2, int(max_parts))
        self.max_batch_bytes = max(1, int(max_batch_bytes))
        self.max_part_chunks = max(1, int(max_part_chunks))
        self._pending: dict[str, _PendingBatch] = {}
        self._lock = threading.RLock()

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def clear(self) -> None:
        with self._lock:
            self._pending.clear()

    def discard(self, group_id: str) -> None:
        """Discard one incomplete group after a protocol-level failure."""
        with self._lock:
            self._pending.pop(str(group_id), None)

    def prune_expired(self, now: float | None = None) -> list[str]:
        with self._lock:
            current = time.monotonic() if now is None else float(now)
            expired = [key for key, batch in self._pending.items()
                       if current - batch.last_seen > self.ttl_seconds]
            for key in expired:
                self._pending.pop(key, None)
            return expired

    def add_part(
        self, *, group_id: str, part_index: int, part_count: int, full_crc: int,
        filename: str, part_data: bytes, part_crc_ok: bool, part_chunks: int,
        tid: int, started_monotonic: float | None = None,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        """Thread-safe wrapper around the assembler's state mutation."""
        with self._lock:
            return self._add_part_unlocked(
                group_id=group_id,
                part_index=part_index,
                part_count=part_count,
                full_crc=full_crc,
                filename=filename,
                part_data=part_data,
                part_crc_ok=part_crc_ok,
                part_chunks=part_chunks,
                tid=tid,
                started_monotonic=started_monotonic,
                now=now,
            )

    def _add_part_unlocked(
        self,
        *,
        group_id: str,
        part_index: int,
        part_count: int,
        full_crc: int,
        filename: str,
        part_data: bytes,
        part_crc_ok: bool,
        part_chunks: int,
        tid: int,
        started_monotonic: float | None = None,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        current = time.monotonic() if now is None else float(now)
        self.prune_expired(current)
        group_id, filename = str(group_id).strip(), str(filename).strip()
        part_index, part_count, full_crc = int(part_index), int(part_count), int(full_crc)
        part_chunks, tid, part_data = int(part_chunks), int(tid), bytes(part_data)

        def reject(message: str) -> None:
            # A malformed fragment makes the group ambiguous; do not retain
            # previously accepted parts and accidentally complete it later.
            self._pending.pop(group_id, None)
            raise ValueError(message)

        if not group_id or not filename:
            reject("batch group and filename are required")
        if part_count < 2 or part_count > self.max_parts:
            reject(f"invalid batch part count: {part_count}")
        if not 1 <= part_index <= part_count:
            reject("batch part index is outside its declared range")
        if not 0 <= full_crc <= 0xFFFF:
            reject("full-file CRC must be 16-bit")
        if not 1 <= part_chunks <= self.max_part_chunks:
            reject("invalid part chunk count")
        if not part_crc_ok:
            reject("batch part CRC failed")
        if not part_data:
            reject("empty batch parts are invalid")
        batch = self._pending.get(group_id)
        if batch and (batch.part_count != part_count or batch.full_crc != full_crc or batch.filename != filename):
            self._pending.pop(group_id, None)
            raise ValueError("batch metadata changed; incomplete group discarded")
        if batch is None:
            if len(self._pending) >= self.max_pending_batches:
                oldest = min(self._pending.values(), key=lambda item: item.last_seen)
                self._pending.pop(oldest.group_id, None)
            started = current if started_monotonic is None else float(started_monotonic)
            batch = _PendingBatch(group_id, part_count, full_crc, filename, started, current)
            self._pending[group_id] = batch
        previous = batch.parts.get(part_index)
        if previous is not None:
            if previous != part_data or batch.chunks[part_index] != part_chunks:
                self._pending.pop(group_id, None)
                raise ValueError("conflicting duplicate batch part; group discarded")
            batch.last_seen = current
            return None
        if batch.total_bytes + len(part_data) > self.max_batch_bytes:
            self._pending.pop(group_id, None)
            raise ValueError("batch exceeds configured byte limit")
        batch.parts[part_index] = part_data
        batch.chunks[part_index] = part_chunks
        batch.tids[part_index] = tid
        batch.total_bytes += len(part_data)
        batch.last_seen = current
        if len(batch.parts) != part_count:
            return None
        result = {"group_id": group_id, "filename": filename, "full_crc": full_crc,
                  "data": b"".join(batch.parts[i] for i in range(1, part_count + 1)),
                  "total_chunks": sum(batch.chunks.values()), "last_tid": batch.tids[part_count],
                  "started_monotonic": batch.started_monotonic}
        self._pending.pop(group_id, None)
        return result
