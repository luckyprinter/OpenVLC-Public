"""Session state builders for live hardware and offline receiver state."""

from __future__ import annotations

from gui_dev_v3.models import (
    ExperimentMetadata,
    SessionState,
    SignalState,
    TransferQuality,
    TransferRecord,
    TransferStatus,
)


def build_session_from_status(role: str, transfer: TransferRecord | None = None) -> SessionState:
    """Build a session from an already-parsed transfer record.

    Kept as a compatibility helper for callers that previously consumed
    external status JSON. Live signal and progress values must come from the
    physical serial backend, never from stale bridge files.
    """
    empty = build_empty_session()
    if transfer is None:
        return SessionState(
            role=role.upper(),
            connected_device="No device",
            current_file="No transfer",
            progress_percent=0,
            signal=empty.signal,
            latest_transfer=empty.latest_transfer,
        )

    progress = int(
        (transfer.received_chunks / transfer.total_chunks) * 100
    ) if transfer.total_chunks > 0 else 0
    return SessionState(
        role=role.upper(),
        connected_device="No device",
        current_file=transfer.filename,
        progress_percent=max(0, min(100, progress)),
        signal=empty.signal,
        latest_transfer=transfer,
    )


def build_empty_session() -> SessionState:
    """Build an empty session when no status data is available.

    All fields are explicitly set to zero/empty to prevent leaking
    dataclass defaults (e.g. data_rate=3.42, lux=420) into offline state.
    """
    empty_transfer = TransferRecord(
        tid=0,
        filename="No data",
        status=TransferStatus.PENDING,
        time_label="",
        size_bytes=0,
        total_chunks=0,
        received_chunks=0,
        quality=TransferQuality(
            label="No Data",
            strict_ber=0.0,
            bit_accuracy=100.0,
            bit_errors=0,
            total_bits=0,
            compared_bytes=0,
            missing_chunks=0,
            missing_bytes=0,
            first_issue="None",
            crc_status="",
            recovery_rate=0.0,
        ),
    )
    return SessionState(
        role="RX",
        connected_device="No device",
        current_file="No transfer",
        progress_percent=0,
        signal=SignalState(
            label="No Signal",
            pvo=0.0,
            vref=0.0,
            margin=0.0,
            target_margin=0.365,
            adc_vref=0.0,
            lux=0,
            data_rate=0.0,
            ber=0.0,
            strict_ber=0.0,
            crc_status="",
            time_elapsed="",
        ),
        latest_transfer=empty_transfer,
    )


def default_experiment_metadata() -> ExperimentMetadata:
    return ExperimentMetadata(
        environment="Lab desk, indoor ambient light",
        distance="45 cm",
        frequency="15 kHz",
        vref_mode="Auto lock before receive",
        notes="",
    )
