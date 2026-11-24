"""Bounded, validated assembly of multi-part optical file transfers."""
from __future__ import annotations
import tempfile
import time
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from gui_dev_v3.serial.session import MAX_STREAM_FILE_BYTES
from gui_dev_v3.serial.transfer_plan import MAX_BATCH_PARTS


@dataclass
class _PendingBatch:
    group_id: str
    part_count: int
    full_crc: int
    filename: str
    started_monotonic: float | None
    last_seen: float
    staging: tempfile.TemporaryDirectory
    chunks: dict[int, int] = field(default_factory=dict)
    tids: dict[int, int] = field(default_factory=dict)
    total_bytes: int = 0


@dataclass(frozen=True)
class CompletedBatch:
    filename: str
    full_crc: int
    staging: tempfile.TemporaryDirectory
    part_count: int
    total_bytes: int
    total_chunks: int
    last_tid: int
    started_monotonic: float | None

    def blocks(self) -> Iterator[bytes]:
        for index in range(1, self.part_count + 1):
            with (Path(self.staging.name) / str(index)).open("rb") as part:
                while block := part.read(64 * 1024):
                    yield block


class BatchAssembler:
    """Stage bounded parts on disk and reject ambiguous retransmissions."""
    def __init__(self, *, ttl_seconds: float = 300.0, max_pending_batches: int = 2,
                 max_parts: int = MAX_BATCH_PARTS, max_batch_bytes: int = 80 * 1024 * 1024,
                 max_part_chunks: int = 512, staging_root: Path | None = None) -> None:
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self.max_pending_batches = max(1, int(max_pending_batches))
        self.max_parts = max(2, int(max_parts))
        self.max_batch_bytes = max(1, int(max_batch_bytes))
        self.max_part_chunks = max(1, int(max_part_chunks))
        self._staging_root = staging_root
        self._pending: dict[str, _PendingBatch] = {}
        self._lock = threading.RLock()

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def clear(self) -> None:
        with self._lock:
            for group_id in tuple(self._pending):
                self._discard_unlocked(group_id)

    def discard(self, group_id: str) -> None:
        """Discard one incomplete group after a protocol-level failure."""
        with self._lock:
            self._discard_unlocked(str(group_id))

    def _discard_unlocked(self, group_id: str) -> None:
        batch = self._pending.pop(group_id, None)
        if batch is not None:
            batch.staging.cleanup()

    def prune_expired(self, now: float | None = None) -> list[str]:
        with self._lock:
            current = time.monotonic() if now is None else float(now)
            expired = [key for key, batch in self._pending.items()
                       if current - batch.last_seen > self.ttl_seconds]
            for key in expired:
                self._discard_unlocked(key)
            return expired

    def add_part(
        self, *, group_id: str, part_index: int, part_count: int, full_crc: int,
        filename: str, part_data: bytes, part_crc_ok: bool, part_chunks: int,
        tid: int, started_monotonic: float | None = None,
        now: float | None = None,
    ) -> CompletedBatch | None:
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
    ) -> CompletedBatch | None:
        current = time.monotonic() if now is None else float(now)
        self.prune_expired(current)
        group_id, filename = str(group_id).strip(), str(filename).strip()

        def reject(message: str) -> None:
            # A malformed fragment makes the group ambiguous; do not retain
            # previously accepted parts and accidentally complete it later.
            self._discard_unlocked(group_id)
            raise ValueError(message)

        try:
            part_index, part_count, full_crc = int(part_index), int(part_count), int(full_crc)
            part_chunks, tid, part_data = int(part_chunks), int(tid), bytes(part_data)
        except (TypeError, ValueError, OverflowError) as exc:
            reject(f"invalid batch part metadata: {exc}")

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
        if len(part_data) > MAX_STREAM_FILE_BYTES:
            reject("batch part exceeds the firmware byte limit")
        batch = self._pending.get(group_id)
        if batch and (batch.part_count != part_count or batch.full_crc != full_crc or batch.filename != filename):
            reject("batch metadata changed; incomplete group discarded")
        if batch is None:
            if len(self._pending) >= self.max_pending_batches:
                oldest = min(self._pending.values(), key=lambda item: item.last_seen)
                self._discard_unlocked(oldest.group_id)
            staging = tempfile.TemporaryDirectory(
                prefix="openvlc-batch-", dir=self._staging_root, ignore_cleanup_errors=True,
            )
            batch = _PendingBatch(group_id, part_count, full_crc, filename, None, current, staging)
            self._pending[group_id] = batch
        staged_part = Path(batch.staging.name) / str(part_index)
        try:
            if part_index in batch.chunks:
                if batch.chunks[part_index] != part_chunks or staged_part.read_bytes() != part_data:
                    reject("conflicting duplicate batch part; group discarded")
                batch.last_seen = current
                return None
            if batch.total_bytes + len(part_data) > self.max_batch_bytes:
                reject("batch exceeds configured byte limit")
            staged_part.write_bytes(part_data)
        except OSError:
            self._discard_unlocked(group_id)
            raise

        if part_index == 1:
            batch.started_monotonic = started_monotonic
        batch.chunks[part_index] = part_chunks
        batch.tids[part_index] = tid
        batch.total_bytes += len(part_data)
        batch.last_seen = current
        if len(batch.chunks) != part_count:
            return None
        self._pending.pop(group_id, None)
        return CompletedBatch(
            filename, full_crc, batch.staging, part_count, batch.total_bytes,
            sum(batch.chunks.values()), batch.tids[part_count], batch.started_monotonic,
        )
