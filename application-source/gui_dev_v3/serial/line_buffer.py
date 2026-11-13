"""Bounded assembly of newline-delimited messages from serial reads."""

from __future__ import annotations


class SerialLineBuffer:
    """Accumulate partial reads and emit only complete, bounded text lines."""

    def __init__(self, max_line_bytes: int = 256 * 1024) -> None:
        if max_line_bytes < 1:
            raise ValueError("max_line_bytes must be positive")
        self.max_line_bytes = int(max_line_bytes)
        self._buffer = bytearray()
        self._discarding = False
        self.overflow_count = 0

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()
        self._discarding = False

    def feed(self, data: bytes) -> list[str]:
        if not data:
            return []

        incoming = data
        if self._discarding:
            newline = incoming.find(b"\n")
            if newline < 0:
                return []
            incoming = incoming[newline + 1:]
            self._discarding = False

        self._buffer.extend(incoming)
        lines: list[str] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            raw = bytes(self._buffer[:newline])
            del self._buffer[:newline + 1]
            if len(raw) > self.max_line_bytes:
                self.overflow_count += 1
                continue
            line = raw.rstrip(b"\r").decode("utf-8", errors="replace").strip()
            if line:
                lines.append(line)

        if len(self._buffer) > self.max_line_bytes:
            self._buffer.clear()
            self._discarding = True
            self.overflow_count += 1
        return lines
