"""Transfer record loaders — reads live data from vlc_beta logs and receive folder."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from gui_dev_v3.models import ChunkRecord, ChunkStatus, TransferQuality, TransferRecord, TransferStatus, SessionCapture

# Paths — resolve with VLC_DATA_DIR env var fallback
def _resolve_data_dir(parents: int, *parts: str) -> Path:
    """Resolve a data directory, checking env var first."""
    env = os.getenv("VLC_DATA_DIR")
    if env:
        return Path(env).expanduser() / Path(*parts)
    return Path(__file__).resolve().parents[parents] / Path(*parts)

BETA_LOG_DIR = _resolve_data_dir(3, "vlc_beta", "logs", "rx")
PROJECT_LOG_DIR = _resolve_data_dir(2, "logs", "rx")
RECEIVE_FOLDER = Path.home() / "LiFiReceived"
TRANSFER_RECORDS_DIR = RECEIVE_FOLDER / "transfer_records"

# Sanity bounds for parsed values
_MAX_SIZE_BYTES = 100_000_000  # 100 MB
_MAX_CHUNKS = 500_000
_MAX_TID = 999_999


def _log_dir() -> Path:
    if BETA_LOG_DIR.exists():
        return BETA_LOG_DIR
    PROJECT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return PROJECT_LOG_DIR


def parse_lq_detail(detail: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for part in detail.split(","):
        part = part.strip()
        if "=" in part:
            key, val = part.split("=", 1)
            try:
                result[key.strip()] = float(val.strip())
            except ValueError:
                pass
    return result


def _parse_transfer_record(data: dict[str, Any]) -> TransferRecord | None:
    """Parse a vlc-rx-transfer-record-v1 JSON dict into a TransferRecord."""
    try:
        tid = int(data.get("tid") or 0)
        payload = data.get("payload") or {}
        chunks_data = data.get("chunks") or {}
        signal_data = data.get("signal") or {}
        attempt = data.get("current_attempt") or {}

        name = payload.get("name") or f"tid-{tid}.bin"
        size_bytes = int(payload.get("size_bytes") or 0)
        total_chunks = int(chunks_data.get("total") or 0)
        received_chunks = int(chunks_data.get("received") or 0)
        missing = chunks_data.get("missing_indexes") or []

        # Validate bounds to prevent corrupted/overflow values
        if tid < 0 or tid > _MAX_TID:
            raise ValueError(f"Invalid tid: {tid}")
        if size_bytes < 0 or size_bytes > _MAX_SIZE_BYTES:
            raise ValueError(f"Invalid size_bytes: {size_bytes}")
        if total_chunks < 0 or total_chunks > _MAX_CHUNKS:
            raise ValueError(f"Invalid total_chunks: {total_chunks}")
        if received_chunks < 0 or received_chunks > total_chunks:
            received_chunks = min(max(received_chunks, 0), total_chunks)

        status_str = str(data.get("status") or "pending").lower()
        if status_str == "complete":
            status = TransferStatus.COMPLETE
        elif status_str == "incomplete":
            status = TransferStatus.INCOMPLETE
        elif "fail" in status_str or "error" in status_str:
            status = TransferStatus.CRC_FAILED
        elif "stall" in status_str:
            status = TransferStatus.STALLED
        else:
            status = TransferStatus.PENDING

        created = str(data.get("created_at") or "")
        time_label = created[-8:] if len(created) >= 8 else created

        quality = TransferQuality(
            label=str(signal_data.get("quality_status") or "Unknown"),
            # CRC/chunk metadata does not constitute a Method 2 BER comparison.
            strict_ber=None,
            bit_accuracy=None,
            bit_errors=None,
            total_bits=0,
            compared_bytes=0,
            missing_chunks=len(missing),
            missing_bytes=0,
            first_issue=f"Chunk {missing[0]} missing" if missing else "None",
            crc_status=str(payload.get("crc16_ccitt") or "Unknown"),
            recovery_rate=(received_chunks / max(total_chunks, 1)) * 100,
        )

        # Build chunk records from received/missing indexes
        chunk_list: list[ChunkRecord] = []
        received_set = set(chunks_data.get("received_indexes") or [])
        missing_set = set(missing)
        for idx in range(total_chunks):
            if idx in missing_set:
                chunk_list.append(ChunkRecord(index=idx, status=ChunkStatus.MISSING))
            elif idx in received_set:
                chunk_list.append(ChunkRecord(index=idx, status=ChunkStatus.MATCH, expected=b"", received=b""))
            else:
                chunk_list.append(ChunkRecord(index=idx, status=ChunkStatus.PENDING))

        return TransferRecord(
            tid=tid,
            filename=name,
            status=status,
            time_label=time_label,
            size_bytes=size_bytes,
            total_chunks=total_chunks,
            received_chunks=received_chunks,
            quality=quality,
            chunks=chunk_list,
        )
    except (ValueError, TypeError, KeyError) as exc:
        print(f"Failed to parse transfer record: {exc}")
        return None


def load_real_transfer_history() -> list[TransferRecord]:
    """Load transfer records from all available sources."""
    records: list[TransferRecord] = []
    seen_tids: set[int] = set()

    # 1. Load from latest_rx_record.json
    latest_path = _log_dir() / "latest_rx_record.json"
    if latest_path.exists():
        try:
            data = json.loads(latest_path.read_text(encoding="utf-8"))
            record = _parse_transfer_record(data)
            if record and record.tid not in seen_tids:
                records.append(record)
                seen_tids.add(record.tid)
        except (OSError, json.JSONDecodeError):
            pass

    # 2. Load from transfer_records/ directory
    if TRANSFER_RECORDS_DIR.exists():
        try:
            paths = sorted(
                [p for p in TRANSFER_RECORDS_DIR.iterdir() if p.suffix == ".json"],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for path in paths[:50]:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    record = _parse_transfer_record(data)
                    if record and record.tid not in seen_tids:
                        records.append(record)
                        seen_tids.add(record.tid)
                except (OSError, json.JSONDecodeError):
                    pass
        except OSError:
            pass

    # 3. Load from beta log directory directly
    if BETA_LOG_DIR.exists():
        try:
            for path in sorted(BETA_LOG_DIR.glob("rx_transfer_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                if path.name == "latest_rx_record.json":
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    record = _parse_transfer_record(data)
                    if record and record.tid not in seen_tids:
                        records.append(record)
                        seen_tids.add(record.tid)
                except (OSError, json.JSONDecodeError):
                    pass
        except OSError:
            pass

    return records


def load_tx_index_records() -> list[dict[str, Any]]:
    return []


def load_tx_transfer_records(index: int) -> list[TransferRecord]:
    return []


def empty_transfer() -> TransferRecord:
    return TransferRecord(
        tid=0,
        filename="",
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


def _resolve_capture_dir() -> Path:
    """Resolve session captures to the application-owned state directory."""
    import os
    env = os.getenv("VLC_DATA_DIR")
    if env:
        return Path(env).expanduser() / "state" / "captures"
    return Path(__file__).resolve().parents[2] / "state" / "captures"


CAPTURE_DIR = _resolve_capture_dir()
LEGACY_CAPTURE_DIR = Path.home() / ".vlc_rx" / "captures"


def save_session_capture(capture: SessionCapture) -> None:
    from dataclasses import asdict
    import json

    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = CAPTURE_DIR / f"session_{capture.tid}.json"
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(asdict(capture), indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        print(f"Failed to save session capture {capture.tid}: {exc}")
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def load_session_capture(tid: int) -> SessionCapture | None:
    path = CAPTURE_DIR / f"session_{tid}.json"
    legacy_path = LEGACY_CAPTURE_DIR / f"session_{tid}.json"
    source_path = path if path.exists() else legacy_path
    if not source_path.exists():
        return None
    try:
        raw_text = source_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        capture = SessionCapture(
            tid=int(data["tid"]),
            timestamp=str(data["timestamp"]),
            filename=str(data["filename"]),
            ber=(float(data["ber"]) if data.get("ber") is not None else None),
            crc_status=str(data["crc_status"]),
            throughput_kbps=float(data["throughput_kbps"]),
            analog_time=list(data["analog_time"]),
            pvo_samples=list(data["pvo_samples"]),
            vref_samples=list(data["vref_samples"]),
            margin_samples=list(data["margin_samples"]),
            ook_bits=list(data["ook_bits"]),
            protocol_events=list(data["protocol_events"]),
            ber_method=str(data.get("ber_method", "unavailable")),
        )
        if source_path == legacy_path:
            # Keep the old file intact; copy it into the current app-data
            # location only after parsing it successfully. A copy failure
            # must not prevent the existing capture from being viewed.
            try:
                CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                temporary.write_text(raw_text, encoding="utf-8")
                temporary.replace(path)
            except OSError as migration_error:
                print(f"Could not migrate legacy capture {tid}: {migration_error}")
        return capture
    except Exception as exc:
        print(f"Failed to load session capture {tid}: {exc}")
        return None

