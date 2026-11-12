"""Bounded, validated assembly of multi-part optical file transfers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from gui_dev_v3.serial.transfer_plan import MAX_BATCH_PARTS


@dataclass
class _PendingBatch:
    group_id: str
    part_count: int
    full_crc: int
    filename: str
    created_at: float
    last_seen: float
    started_monotonic: float
    parts: dict[int, bytes] = field(default_factory=dict)
    part_chunks: dict[int, int] = field(default_factory=dict)
    part_tids: dict[int, int] = field(default_factory=dict)
    total_bytes: int = 0


class BatchAssembler:
    """Collect valid parts and return one reconstructed file when complete."""

    def __init__(self, *, ttl_seconds: float = 300.0, max_pending_batches: int = 2,
                 max_parts: int = MAX_BATCH_PARTS, max_batch_bytes: int = 80 * 1024 * 1024,
                 max_part_chunks: int = 512) -> None:
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self.max_pending_batches = max(1, int(max_pending_batches))
        self.max_parts = max(2, int(max_parts))
        self.max_batch_bytes = max(1, int(max_batch_bytes))
        self.max_part_chunks = max(1, int(max_part_chunks))
        self._pending: dict[str, _PendingBatch] = {}

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def clear(self) -> None:
        self._pending.clear()

    def prune_expired(self, now: float | None = None) -> list[str]:
        current = time.monotonic() if now is None else float(now)
        expired = [gid for gid, batch in self._pending.items()
                   if current - batch.last_seen > self.ttl_seconds]
        for gid in expired:
            self._pending.pop(gid, None)
        return expired

    def add_part(self, *, group_id: str, part_index: int, part_count: int, full_crc: int,
                 filename: str, part_data: bytes, part_crc_ok: bool, part_chunks: int,
                 tid: int, started_monotonic: float | None = None,
                 now: float | None = None) -> dict[str, Any] | None:
        current = time.monotonic() if now is None else float(now)
        self.prune_expired(current)
        group_id, filename = str(group_id).strip(), str(filename).strip()
        part_index, part_count, full_crc = int(part_index), int(part_count), int(full_crc)
        part_chunks, tid, part_data = int(part_chunks), int(tid), bytes(part_data)

        if not group_id or not filename:
            raise ValueError("batch group and filename are required")
        if part_count < 2 or part_count > self.max_parts:
            raise ValueError(f"invalid batch part count: {part_count}")
        if not 1 <= part_index <= part_count:
            raise ValueError(f"part index {part_index} is outside 1..{part_count}")
        if not 0 <= full_crc <= 0xFFFF:
            raise ValueError("full-file CRC must be a 16-bit value")
        if not 1 <= part_chunks <= self.max_part_chunks:
            raise ValueError(f"part chunk count must be within 1..{self.max_part_chunks}")
        if not part_crc_ok:
            raise ValueError(f"part {part_index} failed its CRC")
        if not part_data:
            raise ValueError("empty batch parts are not valid")

        batch = self._pending.get(group_id)
        if batch is not None and (batch.part_count != part_count or batch.full_crc != full_crc
                                  or batch.filename != filename):
            self._pending.pop(group_id, None)
            raise ValueError(f"batch metadata changed for group {group_id}")
        if batch is None:
            if len(self._pending) >= self.max_pending_batches:
                oldest = min(self._pending.values(), key=lambda item: item.last_seen)
                self._pending.pop(oldest.group_id, None)
            started = current if started_monotonic is None else float(started_monotonic)
            batch = _PendingBatch(group_id, part_count, full_crc, filename, current, current, started)
            self._pending[group_id] = batch

        previous = batch.parts.get(part_index)
        next_total = batch.total_bytes - (len(previous) if previous is not None else 0) + len(part_data)
        if next_total > self.max_batch_bytes:
            self._pending.pop(group_id, None)
            raise ValueError(f"batch exceeds {self.max_batch_bytes} byte safety limit")
        batch.parts[part_index] = part_data
        batch.part_chunks[part_index] = part_chunks
        batch.part_tids[part_index] = tid
        batch.total_bytes = next_total
        batch.last_seen = current

        if set(batch.parts) != set(range(1, part_count + 1)):
            return None
        result = {
            "group_id": group_id,
            "filename": batch.filename,
            "full_crc": batch.full_crc,
            "data": b"".join(batch.parts[index] for index in range(1, part_count + 1)),
            "total_chunks": sum(batch.part_chunks.values()),
            "started_monotonic": batch.started_monotonic,
            "last_tid": batch.part_tids[part_count],
            "part_count": part_count,
        }
        self._pending.pop(group_id, None)
        return result
