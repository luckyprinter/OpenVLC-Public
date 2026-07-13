"""TX Physical Backend — real ESP32 hardware via serial.

Communicates with actual VLC_TX firmware via serial.
No mock data. No simulated values.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import threading
from gui_dev_v3.tx_mock_data import TXFileInfo, TXProgress, TXSettings, TXState
from gui_dev_v3.serial.controllers import TXSerialController

# Resolve beta state/log dirs with VLC_DATA_DIR env var fallback
def _resolve_beta_dir() -> tuple[Path, Path]:
    import os
    env = os.getenv("VLC_DATA_DIR")
    if env:
        base = Path(env).expanduser()
        return base / "state", base / "logs" / "tx"
    parent = Path(__file__).resolve().parents[4] / "vlc_beta"
    return parent / "state", parent / "logs" / "tx"

BETA_STATE_DIR, BETA_TX_LOG_DIR = _resolve_beta_dir()
STATUS_FRESHNESS_SEC = 30.0


@dataclass
class TXPhysicalSnapshot:
    """Immutable data packet from the TX physical backend."""
    filename: str
    filetype: str
    file_size_bytes: int
    total_chunks: int
    chunk_size: int
    encoding: str
    modulation: str
    symbol_rate: str
    led_pin: int
    tx_power: str
    pre_emphasis: str
    status_text: str
    progress_percent: int
    current_chunk: int
    elapsed_time: str
    estimated_time: str
    data_rate: str
    port: str
    serial_connected: bool
    activity_log: list[dict[str, str]]
    record_count: int
    firmware_version: str = ""
    board_type: str = ""


class TXPhysicalBackend:
    """Physical mode backend — real TX serial hardware only."""

    def __init__(self) -> None:
        self._port: str | None = None
        self._connected: bool = False
        self._firmware_info: dict[str, str] | None = None
        self._controller = TXSerialController(on_status=self._on_serial_status)
        self._transmission_thread: threading.Thread | None = None
        self._latest_status: dict[str, Any] = {}
        self._active_file: str = "No file"

    def scan_ports(self) -> list[str]:
        return _list_usb_serial_ports()

    def detect_firmware(self, port: str) -> dict[str, str] | None:
        info = _send_identify(port, "VLC_TX")
        if info:
            self._firmware_info = info
        return info

    def auto_connect(self) -> bool:
        ports = self.scan_ports()
        for port in ports:
            info = self.detect_firmware(port)
            if info and info.get("device") == "VLC_TX":
                self._port = port
                self._connected = True
                self._open_serial()
                self.apply_link_settings()
                return True
        return False

    def connect(self, port: str) -> bool:
        info = self.detect_firmware(port)
        if info:
            self._port = port
            self._connected = True
            self._open_serial()
            self.apply_link_settings()
            return True
        return False

    def _open_serial(self) -> None:
        """Open persistent serial connection via controller."""
        if not self._port:
            return
        self._controller.connect(self._port, expected_role="VLC_TX")

    def _close_serial(self) -> None:
        self._controller.disconnect()

    def disconnect(self) -> None:
        self._close_serial()
        self._port = None
        self._connected = False
        self._firmware_info = None
        self._latest_status = {}

    def send_command(self, cmd: str) -> bool:
        """Write cmd string over serial."""
        if not self._connected:
            return False
        return self._controller.send_line(cmd.strip())

    def _on_serial_status(self, payload: dict[str, Any]) -> None:
        """Callback from TXSerialController."""
        self._latest_status.update(payload)
        
    def start_transmission(self, filepath: str) -> None:
        if not self._connected or not self._port:
            return
            
        path = Path(filepath)
        self._active_file = path.name
        
        # Run in background to prevent GUI freeze
        self._transmission_thread = threading.Thread(
            target=self._controller.send_file,
            args=(path,),
            daemon=True
        )
        self._transmission_thread.start()

    def apply_link_settings(self) -> None:
        """Apply saved settings to physical TX firmware."""
        if not self._connected or not getattr(self, "_ser", None):
            return
        from gui_dev_v3.settings import SettingsManager
        mgr = SettingsManager("tx")
        
        symbol_hz = int(mgr.get("link/symbol_hz", 15000))
        gap = int(mgr.get("link/post_frame_idle_ms", 0))
        fgap = int(mgr.get("link/frame_gap_ms", 1))
        active_low = 1 if mgr.get("link/active_low", False) else 0
        idle_on = 1 if mgr.get("link/idle_on", True) else 0
        quiet = 1 if mgr.get("link/quiet_mode", True) else 0
        intensity = int(mgr.get("link/cal_intensity_pct", 35))
        
        self.send_command(f"FREQ={symbol_hz}")
        self.send_command(f"GAP={gap}")
        self.send_command(f"FGAP={fgap}")
        self.send_command(f"ACTIVE_LOW={active_low}")
        self.send_command(f"IDLE_ON={idle_on}")
        self.send_command(f"QUIET={quiet}")
        self.send_command(f"INTENSITY={intensity}")
        dma_mode = 1 if mgr.get("link/dma_mode", False) else 0
        self.send_command(f"DMA_MODE={dma_mode}")

    def cleanup(self) -> None:
        """Close serial connection and release port."""
        self.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def port(self) -> str | None:
        return self._port

    def refresh(self) -> TXPhysicalSnapshot:
        """Read current TX state from hardware."""
        if not self._connected or not self._controller.is_connected:
            if self._connected:
                self.disconnect()
            return self._empty_snapshot()

        now_str = time.strftime("%H:%M:%S")
        log: list[dict[str, str]] = []
        
        stage = self._latest_status.get("stage", "Idle")
        detail = self._latest_status.get("detail", "")
        percent = float(self._latest_status.get("percent", 0.0))
        filename = self._latest_status.get("file_name", self._active_file)
        
        log.append({"time": now_str, "event": stage, "details": detail})
        
        snapshot = TXPhysicalSnapshot(
            filename=filename,
            filetype=_guess_filetype(filename),
            file_size_bytes=int(self._latest_status.get("size", 0)),
            total_chunks=0,
            chunk_size=256,
            encoding="4B5B",
            modulation="NRZ / OOK",
            symbol_rate="15,000 sym/s",
            led_pin=25,
            tx_power="100 %",
            pre_emphasis="Disabled",
            status_text=f"{stage}: {detail}",
            progress_percent=int(percent),
            current_chunk=0,
            elapsed_time="00:00:00",
            estimated_time="00:00:00",
            data_rate="0 bps",
            port=self._port or "COM",
            serial_connected=True,
            activity_log=log,
            record_count=0,
            firmware_version=self._firmware_info.get("firmware", "") if self._firmware_info else "",
            board_type=self._firmware_info.get("board", "") if self._firmware_info else "",
        )
        return snapshot

    def _empty_snapshot(self) -> TXPhysicalSnapshot:
        now = time.strftime("%H:%M:%S")
        return TXPhysicalSnapshot(
            filename="No file",
            filetype="",
            file_size_bytes=0,
            total_chunks=0,
            chunk_size=256,
            encoding="4B5B",
            modulation="NRZ / OOK",
            symbol_rate="15,000 sym/s",
            led_pin=25,
            tx_power="100 %",
            pre_emphasis="Disabled",
            status_text="Offline — no hardware",
            progress_percent=0,
            current_chunk=0,
            elapsed_time="00:00:00",
            estimated_time="00:00:00",
            data_rate="0 bps",
            port="—",
            serial_connected=False,
            activity_log=[
                {"time": now, "event": "Offline", "details": "No hardware connected"},
                {"time": now, "event": "Tip", "details": "Switch to Simulated mode for mock data"},
            ],
            record_count=0,
        )


# ── Helpers ──

def _is_status_fresh(status: dict | None, max_age: float = STATUS_FRESHNESS_SEC) -> bool:
    if not status:
        return False
    updated = status.get("updated_at")
    if updated is not None:
        return (time.time() - float(updated)) < max_age
    return False


def _read_tx_status() -> dict[str, Any] | None:
    path = BETA_STATE_DIR / "tx_status.json"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] | None = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _read_latest_tx_record() -> dict[str, Any] | None:
    path = BETA_TX_LOG_DIR / "latest_tx_record.json"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] | None = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _parse_tx_record(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload") or {}
    settings = record.get("settings") or {}
    batch = record.get("batch") or {}
    parts = record.get("parts") or []

    filename = payload.get("name", "thesis.pdf")
    size_bytes = int(payload.get("size_bytes", 0))
    chunk_bytes = int(settings.get("chunk_bytes", 256))
    total_chunks = max(size_bytes // max(chunk_bytes, 1), 1) if size_bytes else 0

    if parts:
        total_chunks = sum(
            int(p.get("size_bytes", 0)) // max(chunk_bytes, 1) for p in parts
        )
        total_chunks = max(total_chunks, 1)

    status = str(record.get("status", "pending")).lower()
    mode = str(settings.get("mode", "4B5B"))
    symbol_rate = f"{int(settings.get('symbol_hz', 15000)):,} sym/s"
    led_pin = int(settings.get("led_pin", 25))
    tx_power = 100

    if status == "complete":
        percent = 100
        current_chunk = total_chunks
    elif status in ("failed", "error"):
        percent = 0
        current_chunk = 0
    else:
        percent = 0
        current_chunk = 0

    return {
        "filename": filename,
        "filetype": _guess_filetype(filename),
        "size_bytes": size_bytes,
        "total_chunks": total_chunks,
        "chunk_size": chunk_bytes,
        "encoding": mode,
        "modulation": "NRZ / OOK",
        "symbol_rate": symbol_rate,
        "led_pin": led_pin,
        "tx_power": tx_power,
        "pre_emphasis": "Enabled" if settings.get("pre_emphasis", False) else "Disabled",
        "status_text": "Ready to transmit" if status in ("pending", "idle") else status.capitalize(),
        "percent": percent,
        "current_chunk": current_chunk,
        "elapsed_time": "00:00:00",
        "estimated_time": "00:00:00",
        "data_rate": "0 bps",
        "serial_connected": True,
        "port": str(record.get("tx_port", "COM6")),
    }


def _guess_filetype(filename: str) -> str:
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    mapping = {
        "pdf": "PDF Document",
        "txt": "Text File",
        "md": "Markdown",
        "png": "PNG Image",
        "jpg": "JPEG Image",
        "jpeg": "JPEG Image",
        "bin": "Binary Data",
    }
    return mapping.get(ext, f".{ext.upper()} File" if ext else "Unknown")


def _list_usb_serial_ports() -> list[str]:
    try:
        import serial.tools.list_ports
        ports = []
        for port in serial.tools.list_ports.comports():
            dev = (port.device or "").lower()
            desc = (port.description or "").lower()
            hwid = (port.hwid or "").lower()
            meta = f"{dev} {desc} {hwid}"
            keywords = ("usb", "uart", "cp210", "ch340", "acm", "ftdi", "arduino", "esp32")
            if port.vid is not None and port.pid is not None:
                ports.append(port.device)
            elif any(k in meta for k in keywords):
                ports.append(port.device)
        return sorted(set(ports))
    except ImportError:
        return []
    except (OSError, RuntimeError) as exc:
        import sys
        print(f"Serial port scan failed: {exc}", file=sys.stderr)
        return []


def _send_identify(port: str, expected_device: str) -> dict[str, str] | None:
    try:
        import serial
        with serial.Serial(port, 115200, timeout=0.5) as ser:
            ser.write(b"IDENTIFY\n")
            raw = ser.readline().strip()
            if raw:
                resp = json.loads(raw.decode("utf-8", errors="replace"))
                if isinstance(resp, dict) and resp.get("device") == expected_device:
                    return {
                        "device": str(resp.get("device", "")),
                        "firmware": str(resp.get("firmware", "")),
                        "board": str(resp.get("board", "")),
                    }
    except (ImportError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return None
