"""Session state builders — builds live state from vlc_beta status files."""

from __future__ import annotations

from gui_dev_v3.data.status import read_status
from gui_dev_v3.data.records import parse_lq_detail
import math


def _safe_number(value: Any, default: float = 0.0) -> float:
    """Convert untrusted status values to finite numbers without raising."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _safe_integer(value: Any, default: int = 0) -> int:
    """Convert untrusted status values to integers without raising."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return int(number)


from gui_dev3.models import (
    ChunkRecord,
    ChunkStatus,
    ExperimentMetadata,
    SessionState,
    SignalState,
    TransferQuality,
    TransferRecord,
    TransferStatus,
)


def build_session_from_status(role: str, transfer: TransferRecord | None = None) -> SessionState:
    """Build a SessionState from the real-time vlc_beta status files."""
    rx_status = read_status("rx") or {}
    sig_status = read_status("signal") or {}

    # Extract signal data
    margin_v = _safe_number(sig_status.get("margin_v") or rx_status.get("margin_v"))
    pvo_v = _safe_number(sig_status.get("pvo_v") or rx_status.get("pvo_v"))
    vref_v = _safe_number(sig_status.get("vref_v") or rx_status.get("vref_v"))
    swing_v = _safe_number(sig_status.get("swing_v"))
    pass_rate = _safe_number(sig_status.get("pass_rate"))
    quality_label = str(sig_status.get("quality_label") or rx_status.get("stage") or "No Signal")

    # Parse margin from detail string if not present as float
    if margin_v == 0.0 and not sig_status:
        detail = str(rx_status.get("detail") or "")
        parsed = parse_lq_detail(detail)
        margin_v = _safe_number(parsed.get("Margin"))
        pvo_v = _safe_number(parsed.get("PVo")) or _safe_number(parsed.get("SIGNAL"))
        vref_v = _safe_number(parsed.get("Vref"))

    # Parse stage/progress from rx_status
    stage = str(rx_status.get("stage") or "Idle")
    detail = str(rx_status.get("detail") or "")
    percent = min(100.0, max(0.0, _safe_number(rx_status.get("percent"))))
    file_name = str(rx_status.get("file_name") or "")
    size_bytes = max(0, _safe_integer(rx_status.get("size") or rx_status.get("size_bytes")))
    rate_bps = max(0.0, _safe_number(rx_status.get("rate_bps")))
    saved_path = str(rx_status.get("path") or "")

    # Build signal state
    signal = SignalState(
        label=quality_label,
        pvo=pvo_v,
        vref=vref_v,
        margin=margin_v,
        target_margin=0.365,
        adc_vref=(
            _safe_number(sig_status.get("adc_vref") or rx_status.get("adc_vref"))
            if sig_status.get("adc_vref") or rx_status.get("adc_vref") else None
        ),
        # No lux meter is part of this receiver setup.
        lux=None,
        data_rate=rate_bps / 1000.0 if rate_bps > 0 else None,
        ber=None,
        strict_ber=None,
        crc_status=str(rx_status.get("crc_status") or sig_status.get("crc_status") or "Unknown"),
        time_elapsed=str(rx_status.get("time_elapsed") or ""),
    )

    # Use provided transfer or build a minimal one from status
    if transfer is None:
        total_chunks = min(500_000, max(0, _safe_integer(rx_status.get("total_chunks"))))
        received = min(total_chunks, max(0, _safe_integer(rx_status.get("received_chunks"))))
        if total_chunks > 0 and received <= 0 and percent > 0:
            received = int(percent / 100 * total_chunks)
        received = min(max(received, 0), total_chunks)
        status = TransferStatus.INCOMPLETE
        if "complete" in stage.lower() or "success" in stage.lower():
            status = TransferStatus.COMPLETE
            received = total_chunks
            percent = 100.0
        elif "fail" in stage.lower() or "error" in stage.lower():
            status = TransferStatus.CRC_FAILED
        elif "stall" in stage.lower():
            status = TransferStatus.STALLED
        elif "idle" in stage.lower():
            status = TransferStatus.PENDING

        transfer = TransferRecord(
            tid=min(999_999, max(0, _safe_integer(rx_status.get("tid")))),
            filename=file_name or "No active transfer",
            status=status,
            time_label="",
            size_bytes=size_bytes,
            total_chunks=total_chunks,
            received_chunks=received,
            quality=TransferQuality(
                label=quality_label,
                strict_ber=None,
                bit_accuracy=None,
                bit_errors=None,
                total_bits=0,
                compared_bytes=0,
                missing_chunks=total_chunks - received,
                missing_bytes=0,
                first_issue="None",
                crc_status=str(rx_status.get("crc_status") or rx_status.get("crc16_ccitt") or "Unknown"),
                recovery_rate=percent,
            ),
        )

    return SessionState(
        role=role.upper(),
        connected_device=rx_status.get("port") or rx_status.get("device") or "No device",
        current_file=file_name or transfer.filename,
        progress_percent=int(percent),
        signal=signal,
        latest_transfer=transfer,
    )


def build_empty_session() -> SessionState:
    """Build an empty session when no status data is available.

    All fields are explicitly set to unavailable/empty values so offline
    state never presents measurements that were not actually collected.
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
            strict_ber=None,
            bit_accuracy=None,
            bit_errors=None,
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
            adc_vref=None,
            lux=None,
            data_rate=None,
            ber=None,
            strict_ber=None,
            crc_status="Unknown",
            time_elapsed="",
        ),
        latest_transfer=empty_transfer,
    )


def default_experiment_metadata() -> ExperimentMetadata:
    return ExperimentMetadata(
        environment="",
        distance="",
        frequency="",
        vref_mode="",
        notes="",
    )
