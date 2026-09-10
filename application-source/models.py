from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TransferStatus(str, Enum):
    COMPLETE = "Complete"
    INCOMPLETE = "Incomplete"
    CRC_FAILED = "CRC Failed"
    STALLED = "Stalled"
    PENDING = "Pending"


class ChunkStatus(str, Enum):
    MATCH = "Match"
    DIFFERENT = "Different"
    MISSING = "Missing"
    PENDING = "Pending"
    RECEIVED = "Seen, bytes pending"


@dataclass(frozen=True)
class ChunkRecord:
    index: int
    status: ChunkStatus
    expected: bytes = b""
    received: bytes = b""

    @property
    def expected_size(self) -> int:
        return len(self.expected)

    @property
    def received_size(self) -> int:
        return len(self.received)

    @property
    def missing_bytes(self) -> int:
        if self.status == ChunkStatus.MISSING:
            return len(self.expected)
        return max(0, len(self.expected) - len(self.received))

    @property
    def different_bytes(self) -> int:
        return sum(1 for a, b in zip(self.expected, self.received) if a != b)


@dataclass(frozen=True)
class TransferQuality:
    label: str
    strict_ber: float
    bit_accuracy: float
    bit_errors: int
    total_bits: int
    compared_bytes: int
    missing_chunks: int
    missing_bytes: int
    first_issue: str
    crc_status: str
    recovery_rate: float


@dataclass(frozen=True)
class TransferRecord:
    tid: int
    filename: str
    status: TransferStatus
    time_label: str
    size_bytes: int
    total_chunks: int
    received_chunks: int
    quality: TransferQuality
    chunks: list[ChunkRecord] = field(default_factory=list)


@dataclass(frozen=True)
class SignalState:
    label: str
    pvo: float
    vref: float
    margin: float
    target_margin: float
    adc_vref: float = 3.300
    lux: int = 420
    data_rate: float = 3.42
    ber: float = 0.0
    strict_ber: float = 0.0
    crc_status: str = "PASS"
    time_elapsed: str = "00:00:38"


@dataclass(frozen=True)
class SessionState:
    role: str
    connected_device: str
    current_file: str
    progress_percent: int
    signal: SignalState
    latest_transfer: TransferRecord


@dataclass(frozen=True)
class ExperimentMetadata:
    environment: str
    distance: str
    frequency: str
    vref_mode: str
    notes: str


@dataclass(frozen=True)
class SessionCapture:
    tid: int
    timestamp: str
    filename: str
    ber: float
    crc_status: str
    throughput_kbps: float
    analog_time: list[float]
    pvo_samples: list[float]
    vref_samples: list[float]
    margin_samples: list[float]
    ook_bits: list[int]
    protocol_events: list[dict[str, Any]]

