"""Mock data matching the VLC Receiver dashboard from the UI image."""

from __future__ import annotations

from gui_dev_v3.models import (
    ChunkRecord,
    ChunkStatus,
    ExperimentMetadata,
    SessionState,
    SignalState,
    TransferQuality,
    TransferRecord,
    TransferStatus,
)
from gui_dev_v3.logic.ber_bridge import transfer_quality_from_chunks


def build_mock_chunks(total: int = 97) -> list[ChunkRecord]:
    """Build 97 chunks, 75 received (77% complete), matching the image."""
    chunks: list[ChunkRecord] = []
    missing = set(range(75, 97))  # last 22 chunks not yet received
    different = {9, 41}
    pending = set()
    for index in range(total):
        expected = bytes(((0x10 + index + i) % 256 for i in range(16)))
        if index in missing:
            chunks.append(ChunkRecord(index=index, status=ChunkStatus.MISSING, expected=expected))
        elif index in different:
            received = bytearray(expected)
            received[5] ^= 0x3F
            received[8] ^= 0x11
            chunks.append(
                ChunkRecord(index=index, status=ChunkStatus.DIFFERENT, expected=expected, received=bytes(received))
            )
        elif index in pending:
            chunks.append(ChunkRecord(index=index, status=ChunkStatus.RECEIVED, expected=expected))
        else:
            chunks.append(ChunkRecord(index=index, status=ChunkStatus.MATCH, expected=expected, received=expected))
    return chunks


def build_mock_quality(chunks: list[ChunkRecord]) -> TransferQuality:
    """Build quality data with BER=0, CRC PASS, matching the image."""
    return TransferQuality(
        label="Excellent",
        strict_ber=0.0,
        bit_accuracy=100.0,
        bit_errors=0,
        total_bits=131_072,
        compared_bytes=16_384,
        missing_chunks=22,
        missing_bytes=0,
        first_issue="None",
        crc_status="PASS",
        recovery_rate=77.0,
    )


def build_mock_transfer() -> TransferRecord:
    """Build a transfer matching the image: thesis.pdf, 77%, 75/97 chunks."""
    chunks = build_mock_chunks(97)
    quality = build_mock_quality(chunks)
    return TransferRecord(
        tid=42,
        filename="thesis.pdf",
        status=TransferStatus.INCOMPLETE,
        time_label="12:45 PM",
        size_bytes=24_810,  # 24.81 KiB
        total_chunks=97,
        received_chunks=75,
        quality=quality,
        chunks=chunks,
    )


def build_mock_signal() -> SignalState:
    """Build signal data matching the image: PVo=2.846, Vref=2.481, Margin=0.365."""
    return SignalState(
        label="Good",
        pvo=2.846,
        vref=2.481,
        margin=0.365,
        target_margin=0.365,
        adc_vref=3.300,
        lux=420,
        data_rate=3.42,
        ber=0.0,
        strict_ber=0.0,
        crc_status="PASS",
        time_elapsed="00:00:38",
    )


def build_mock_session() -> SessionState:
    """Build a full session matching the image dashboard state."""
    transfer = build_mock_transfer()
    return SessionState(
        role="RX",
        connected_device="ESP32 RX on /dev/ttyUSB0",
        current_file=transfer.filename,
        progress_percent=77,
        signal=build_mock_signal(),
        latest_transfer=transfer,
    )


def build_transfer_history() -> list[TransferRecord]:
    return [build_mock_transfer()]


def build_experiment_metadata() -> ExperimentMetadata:
    return ExperimentMetadata(
        environment="Lab desk, indoor ambient light",
        distance="45 cm",
        frequency="15 kHz",
        vref_mode="Auto lock before receive",
        notes="RX session from image design reference.",
    )


def build_activity_log() -> list[dict[str, str]]:
    """Build the Recent Activity log entries matching the image."""
    return [
        {"time": "12:45:18", "event": "Reception Started", "details": "Receiving file: thesis.pdf"},
        {"time": "12:45:19", "event": "Chunk Received", "details": "Chunk 1 / 97"},
        {"time": "12:45:19", "event": "Chunk Received", "details": "Chunk 2 / 97"},
        {"time": "12:45:20", "event": "CRC Check", "details": "Chunk 2: PASS"},
        {"time": "12:45:20", "event": "Chunk Received", "details": "Chunk 3 / 97"},
        {"time": "12:45:21", "event": "Chunk Received", "details": "Chunk 4 / 97"},
        {"time": "12:45:21", "event": "CRC Check", "details": "Chunk 4: PASS"},
        {"time": "12:45:22", "event": "Chunk Received", "details": "Chunk 5 / 97"},
        {"time": "12:45:23", "event": "Chunk Received", "details": "Chunk 6 / 97"},
        {"time": "12:45:23", "event": "CRC Check", "details": "Chunk 6: PASS"},
        {"time": "12:45:24", "event": "Chunk Received", "details": "Chunk 7 / 97"},
        {"time": "12:45:25", "event": "Signal Update", "details": "Margin: 0.365 V, Lux: 420 lx"},
        {"time": "12:45:26", "event": "BER Update", "details": "BER: 0.0000, Strict BER: 0.0000"},
        {"time": "12:45:28", "event": "Chunk Received", "details": "Chunk 8 / 97"},
        {"time": "12:45:28", "event": "CRC Check", "details": "Chunk 8: PASS"},
        {"time": "12:45:30", "event": "Data Rate Update", "details": "3.42 kbps"},
        {"time": "12:45:32", "event": "Chunk Received", "details": "Chunk 9 / 97"},
        {"time": "12:45:33", "event": "CRC Check", "details": "Chunk 9: DIFFERENT — retransmit requested"},
        {"time": "12:45:35", "event": "Chunk Received", "details": "Chunk 9 / 97 (retransmit)"},
        {"time": "12:45:35", "event": "CRC Check", "details": "Chunk 9: PASS"},
    ]
