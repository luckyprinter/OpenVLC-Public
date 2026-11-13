"""Transfer record loaders for application-owned logs and received files."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from gui_dev_v3.models import ChunkRecord, ChunkStatus, TransferQuality, TransferRecord, TransferStatus, SessionCapture


def _resolve_log_dir() -> Path:
    """Resolve the application-owned RX log directory."""
    env = os.getenv("VLC_DATA_DIR")
    if env:
        return Path(env).expanduser() / "logs" / "rx"
    return Path(__file__).resolve().parents[2] / "logs" / "rx"


LOG_DIR = _resolve_log_dir()

# Read-only compatibility source for transfer records written by older
# releases. New received payloads and current runtime records use VLC_DATA_DIR.
LEGACY_TRANSFER_RECORDS_DIR = Path.home() / "LiFiReceived" / "transfer_records"

# Sanity bounds for parsed values
_MAX_SIZE_BYTES = 100_000_000  # 100 MB
_MAX_CHUNKS = 500_000
_MAX_TID = 999_999


def _log_dir() -> Path:
    """Return the application-owned log directory, creating it when needed."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


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
        if not isinstance(data, dict):
            raise ValueError("transfer record must be an object")
        tid = int(data.get("tid") or 0)
        payload = data.get("payload") or {}
        chunks_data = data.get("chunks") or {}
        signal_data = data.get("signal") or {}
        if not all(isinstance(value, dict) for value in (payload, chunks_data, signal_data)):
            raise ValueError("payload, chunks, and signal must be objects")

        name = payload.get("name") or f"tid-{tid}.bin"
        if not isinstance(name, str):
            raise ValueError("payload name must be text")
        size_bytes = int(payload.get("size_bytes") or 0)
        total_chunks = int(chunks_data.get("total") or 0)
        received_chunks = int(chunks_data.get("received") or 0)
        missing = chunks_data.get("missing_indexes") or []
        received_indexes = chunks_data.get("received_indexes") or []
        if not isinstance(missing, list) or not isinstance(received_indexes, list):
            raise ValueError("chunk indexes must be arrays")
        for indexes in (missing, received_indexes):
            if any(type(index) is not int or index < 0 or index >= total_chunks for index in indexes):
                raise ValueError("chunk index is outside the declared range")

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
        received_set = set(received_indexes)
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
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
        print(f"Failed to parse transfer record: {exc}")
        return None


def _history_identity(data: Any) -> tuple[int, str, str, int] | None:
    """Return a stable cross-source identity without treating a reusable TID as unique."""
    if not isinstance(data, dict):
        return None
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    try:
        tid = int(data.get("tid") or 0)
        size = int(payload.get("size_bytes") or 0)
    except (TypeError, ValueError, OverflowError):
        return None
    created = str(data.get("created_at") or "")
    filename = payload.get("name") or f"tid-{tid}.bin"
    if not isinstance(filename, str):
        return None
    return tid, created, filename, size


def load_real_transfer_history() -> list[TransferRecord]:
    """Load transfer records from all available sources."""
    records: list[TransferRecord] = []
    seen_records: set[tuple[int, str, str, int]] = set()

    # 1. Load from latest_rx_record.json
    latest_path = _log_dir() / "latest_rx_record.json"
    if latest_path.exists():
        try:
            data = json.loads(latest_path.read_text(encoding="utf-8"))
            record = _parse_transfer_record(data)
            identity = _history_identity(data)
            if record and identity is not None and identity not in seen_records:
                records.append(record)
                seen_records.add(identity)
        except (OSError, json.JSONDecodeError):
            pass

    # 2. Import legacy transfer records without moving or modifying user files.
    if LEGACY_TRANSFER_RECORDS_DIR.exists():
        try:
            paths = sorted(
                [p for p in LEGACY_TRANSFER_RECORDS_DIR.iterdir() if p.suffix == ".json"],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for path in paths[:50]:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    record = _parse_transfer_record(data)
                    identity = _history_identity(data)
                    if record and identity is not None and identity not in seen_records:
                        records.append(record)
                        seen_records.add(identity)
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


def _validate_capture_data(data: Any, expected_tid: int) -> None:
    """Validate persisted capture structure before reading or replacing it."""
    required = {
        "tid", "timestamp", "filename", "ber", "crc_status",
        "throughput_kbps", "analog_time", "pvo_samples", "vref_samples",
        "margin_samples", "ook_bits", "protocol_events",
    }
    if not isinstance(data, dict) or not required.issubset(data):
        raise ValueError("capture has an invalid structure")
    if int(data["tid"]) != expected_tid:
        raise ValueError("capture TID does not match its filename/request")
    for key in ("timestamp", "filename", "crc_status"):
        if not isinstance(data[key], str):
            raise ValueError(f"capture {key} must be text")

    for key in ("analog_time", "pvo_samples", "vref_samples", "margin_samples"):
        values = data[key]
        if not isinstance(values, list) or len(values) > 2_000_000:
            raise ValueError(f"capture {key} must be a bounded array")
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError(f"capture {key} contains a non-finite sample")

    bits = data["ook_bits"]
    if (
        not isinstance(bits, list)
        or len(bits) > 2_000_000
        or any(value not in (0, 1) for value in bits)
    ):
        raise ValueError("capture OOK bits must be a bounded binary array")
    events = data["protocol_events"]
    if (
        not isinstance(events, list)
        or len(events) > 200_000
        or any(not isinstance(item, dict) for item in events)
    ):
        raise ValueError("capture protocol events must be a bounded object array")

    ber = data.get("ber")
    if ber is not None and (
        not math.isfinite(float(ber)) or not 0.0 <= float(ber) <= 1.0
    ):
        raise ValueError("capture BER must be finite and between zero and one")
    throughput = float(data["throughput_kbps"])
    if not math.isfinite(throughput) or throughput < 0.0:
        raise ValueError("capture throughput must be finite and non-negative")


def save_session_capture(capture: SessionCapture) -> None:
    """Atomically save a capture without replacing an unreadable existing file."""
    from dataclasses import asdict

    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = CAPTURE_DIR / f"session_{capture.tid}.json"

    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            _validate_capture_data(existing, capture.tid)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            print(
                f"Refusing to overwrite unreadable session capture {capture.tid}; "
                f"original data was preserved: {exc}"
            )
            return

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CAPTURE_DIR,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(asdict(capture), temporary, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    except OSError as exc:
        print(f"Failed to save session capture {capture.tid}: {exc}")
    finally:
        if temporary_path is not None and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def load_session_capture(tid: int) -> SessionCapture | None:
    try:
        requested_tid = int(tid)
        if requested_tid < 0 or requested_tid > _MAX_TID:
            return None
    except (TypeError, ValueError, OverflowError):
        return None

    path = CAPTURE_DIR / f"session_{requested_tid}.json"
    legacy_path = LEGACY_CAPTURE_DIR / f"session_{requested_tid}.json"
    source_path = path if path.exists() else legacy_path
    if not source_path.exists():
        return None
    try:
        raw_text = source_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        _validate_capture_data(data, requested_tid)
        stored_tid = requested_tid
        ber_value = float(data["ber"]) if data.get("ber") is not None else None
        throughput = float(data["throughput_kbps"])

        capture = SessionCapture(
            tid=stored_tid,
            timestamp=str(data["timestamp"]),
            filename=str(data["filename"]),
            ber=ber_value,
            crc_status=str(data["crc_status"]),
            throughput_kbps=throughput,
            analog_time=list(data["analog_time"]),
            pvo_samples=list(data["pvo_samples"]),
            vref_samples=list(data["vref_samples"]),
            margin_samples=list(data["margin_samples"]),
            ook_bits=list(data["ook_bits"]),
            protocol_events=list(data["protocol_events"]),
            ber_method=str(data.get("ber_method", "unavailable")),
        )
        if source_path == legacy_path:
            # Keep the old file intact. Use a unique same-directory temporary
            # so simultaneous readers cannot collide during legacy migration.
            temporary_path: Path | None = None
            try:
                CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=CAPTURE_DIR,
                    prefix=f".session_{requested_tid}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    temporary.write(raw_text)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_path, path)
            except OSError as migration_error:
                print(f"Could not migrate legacy capture {requested_tid}: {migration_error}")
            finally:
                if temporary_path is not None and temporary_path.exists():
                    try:
                        temporary_path.unlink()
                    except OSError:
                        pass
        return capture
    except Exception as exc:
        print(f"Failed to load session capture {requested_tid}: {exc}")
        return None

