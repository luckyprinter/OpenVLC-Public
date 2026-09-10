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
        self._controller = TXSerialController(
            on_status=self._on_serial_status,
            on_log=self._controller_log,
        )
        self._transmission_thread: threading.Thread | None = None
        self._latest_status: dict[str, Any] = {}
        # Preserved completion metrics — never wiped by idle polls
        self._last_completion: dict[str, Any] = {}
        self._active_file: str = "No file"
        self._log_queue: list[dict[str, str]] = []
        self._last_logged: dict[str, str] = {}

    def _controller_log(self, msg: str) -> None:
        self.log("Serial", msg)

    def log(self, event: str, details: str) -> None:
        if self._last_logged.get(event) == details:
            return
        self._last_logged[event] = details
        import time
        now = time.strftime("%H:%M:%S")
        self._log_queue.append({"time": now, "event": event, "details": details})
        
        from gui_dev_v3.logger import file_log
        file_log("TX", event, details)


    def scan_ports(self) -> list[str]:
        return _list_usb_serial_ports()

    def detect_firmware(self, port: str) -> dict[str, str] | None:
        info = _send_identify(port, "VLC_TX")
        if info:
            self._firmware_info = info
        return info

    def auto_connect(self) -> bool:
        ports = self.scan_ports()
        if ports:
            self.log("Scan", f"Found {len(ports)} ports: {', '.join(ports)}")
        for port in ports:
            self.log("Detect", f"Probing {port}...")
            info = self.detect_firmware(port)
            if info and info.get("device") == "VLC_TX":
                self._port = port
                self._connected = True
                fw = info.get("firmware", "tx_unknown")
                fw_label = "Non-DMA" if ("non_dma" in fw or "nondma" in fw) else ("DMA" if "dma" in fw else "TX")
                self.log("Connected", f"Auto-connected to {port} | Firmware: {fw_label} ({fw})")
                self._open_serial()
                self.apply_link_settings()
                return True
        if ports:
            self.log("Failed", "No VLC_TX devices found.")
        return False

    def connect(self, port: str, force: bool = False) -> bool:
        if not force:
            self.log("Connect", f"Detecting firmware on {port}...")
            info = self.detect_firmware(port)
            if not info:
                self.log("Error [C01]", f"Firmware detection failed on {port}")
                return False
        else:
            self.log("Force Connect", f"Bypassing handshake for {port}")
            info = {"device": "VLC_TX", "firmware": "tx_forced", "board": "Unknown"}
            self._firmware_info = info
            
        from PySide6.QtCore import QTimer
        self._timer = QTimer()
        self._timer.timeout.connect(self.refresh)
        self._timer.start(100)
        self._port = port
        self._connected = True
        self._open_serial()
        if not self._controller.is_connected:
            self.log("Error [C02]", f"PySerial failed to open {port}")
        else:
            fw = (self._firmware_info or {}).get("firmware", "tx_unknown")
            fw_label = "Non-DMA" if ("non_dma" in fw or "nondma" in fw) else ("DMA" if "dma" in fw else "TX")
            force_str = " (Force Connect)" if force else ""
            self.log("Connected", f"Opened {port} | Firmware: {fw_label}{force_str}")
            self.apply_link_settings()
        return True

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
        stage = payload.get("stage", "")
        
        # When a transmission completes, freeze the final metrics so idle
        # polls don't overwrite elapsed_time / data_rate with defaults.
        if stage == "Send complete":
            self._completion_pending = True
            self._last_completion = {
                "elapsed_time": payload.get("elapsed_time", "00:00:00"),
                "data_rate":    payload.get("data_rate", "0 bps"),
                "file_name":    payload.get("file_name", self._active_file),
                "size":         payload.get("size", 0),
                "total_chunks": payload.get("total_chunks", 0),
                "chunk":        payload.get("chunk", 0),
            }
        
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
        """Apply saved settings to physical TX firmware.

        Uses the controller's gated apply_4b5b_settings() so that DMA-only
        commands (DMA_MODE=, PREAMBLE=, CARRIER=) are only sent when the
        connected firmware is confirmed DMA-capable. Sending these to
        tx_non_dma.ino causes 'TX_ERROR: unknown command' responses.
        """
        if not self._connected or not self._controller.is_connected:
            return
        from gui_dev_v3.settings import SettingsManager
        mgr = SettingsManager("tx")

        symbol_hz  = int(mgr.get("link/symbol_hz", 15000))
        gap        = int(mgr.get("link/post_frame_idle_ms", 0))
        fgap       = int(mgr.get("link/frame_gap_ms", 1))
        active_low = bool(mgr.get("link/active_low", True))
        idle_on    = bool(mgr.get("link/idle_on", True))
        quiet      = bool(mgr.get("link/quiet_mode", True))
        intensity  = int(mgr.get("link/cal_intensity_pct", 100))

        # apply_4b5b_settings() gates DMA_MODE/PREAMBLE/CARRIER to DMA firmware only
        self._controller.apply_4b5b_settings(
            freq=symbol_hz,
            gap=gap,
            fgap=fgap,
            active_low=active_low,
            idle_on=idle_on,
            quiet=quiet,
        )
        # INTENSITY is common to both firmware variants
        self.send_command(f"INTENSITY={intensity}")

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
            from gui_dev_v3.settings import SettingsManager
            mgr = SettingsManager("tx")
            mode = mgr.get("connection/mode", "Auto Detect (Recommended)")
            auto_conn = mgr.get("connection/auto_connect", True)
            
            if auto_conn:
                now = time.time()
                if not hasattr(self, "_last_scan_time"):
                    self._last_scan_time = 0
                scan_interval = mgr.get("connection/scan_interval", 3)
                
                if (now - self._last_scan_time) > scan_interval:
                    self._last_scan_time = now
                    if mode == "Manual":
                        target_port = mgr.get("connection/port", "")
                        if target_port:
                            self.connect(target_port)
                    else:
                        self.auto_connect()

        if not self._connected or not self._controller.is_connected:
            if self._connected:
                self.disconnect()
            log_out = list(self._log_queue)
            self._log_queue.clear()
            return self._empty_snapshot(log_out)

        now_str = time.strftime("%H:%M:%S")
        log: list[dict[str, str]] = []
        
        stage = self._latest_status.get("stage", "Idle")
        detail = self._latest_status.get("detail", "")
        percent = float(self._latest_status.get("percent", 0.0))
        filename = self._latest_status.get("file_name", self._active_file)
        
        if stage == "Connected" and detail:
            log.append({"time": now_str, "event": stage, "details": detail})
            
        if self._log_queue:
            log.extend(self._log_queue)
            self._log_queue.clear()
        
        snapshot = TXPhysicalSnapshot(
            filename=filename,
            filetype=_guess_filetype(filename),
            file_size_bytes=int(self._latest_status.get("size", 0)),
            total_chunks=int(self._latest_status.get("total_chunks", 0)),
            chunk_size=256,
            encoding="4B5B",
            modulation="NRZ / OOK",
            symbol_rate="15,000 sym/s",
            led_pin=25,
            tx_power="100 %",
            pre_emphasis="Disabled",
            status_text=f"Transmitting: {stage} - {detail}" if stage in ("Preparing", "Preloading", "Sending", "Streaming DMA", "Preparing DMA") else f"{stage}: {detail}",
            progress_percent=int(percent),
            current_chunk=int(self._latest_status.get("chunk", 0)),
            # Use frozen completion metrics if available and current stage is idle/complete
            elapsed_time=(
                self._last_completion.get("elapsed_time", "00:00:00")
                if stage in ("Send complete", "Idle", "Connected", "Calibration")
                else self._latest_status.get("elapsed_time", "00:00:00")
            ),
            estimated_time=self._latest_status.get("estimated_time", "00:00:00"),
            data_rate=(
                self._last_completion.get("data_rate", "0 bps")
                if stage in ("Send complete", "Idle", "Connected", "Calibration")
                else self._latest_status.get("data_rate", "0 bps")
            ),
            port=self._port or "COM",
            serial_connected=True,
            activity_log=log,
            record_count=0,
            firmware_version=self._firmware_info.get("firmware", "") if self._firmware_info else "",
            board_type=self._firmware_info.get("board", "") if self._firmware_info else "",
        )
        
        # Ensure that 'Send complete' is guaranteed to be seen by the GUI at least once
        if getattr(self, "_completion_pending", False) and self._last_completion:
            snapshot.status_text = f"Send complete: {self._last_completion.get('file_name', '')}"
            snapshot.elapsed_time = self._last_completion.get("elapsed_time", "00:00:00")
            snapshot.data_rate = self._last_completion.get("data_rate", "0 bps")
            snapshot.current_chunk = self._last_completion.get("chunk", 0)
            snapshot.total_chunks = self._last_completion.get("total_chunks", 0)
            snapshot.progress_percent = 100
            self._completion_pending = False

        return snapshot

    def _empty_snapshot(self, extra_log: list[dict[str, str]] | None = None) -> TXPhysicalSnapshot:
        now = time.strftime("%H:%M:%S")
        log = extra_log or []
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
            activity_log=log,
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
    """Return serial ports, prioritising true USB/ACM adapters (ESP32) first.

    Port priority order:
      1. ttyUSB* / ttyACM* — real USB-serial adapters (CP2102, CH340, FTDI)
      2. COM* — Windows virtual COM ports
      3. Everything else with USB VID/PID
    Native kernel ttyS* ports are excluded unless they have a USB VID/PID.
    """
    try:
        import serial.tools.list_ports
        usb_ports: list[str] = []
        other_ports: list[str] = []
        for port in serial.tools.list_ports.comports():
            dev = port.device or ""
            meta = f"{dev} {port.description or ''} {port.hwid or ''}".lower()
            is_usb_adapter = any(
                dev.startswith(p) for p in ("/dev/ttyUSB", "/dev/ttyACM")
            ) or (
                # Windows: COM ports with a real USB VID/PID
                dev.upper().startswith("COM") and port.vid is not None
            )
            has_vid_pid = port.vid is not None and port.pid is not None
            keywords = ("usb", "cp210", "ch340", "ftdi", "arduino", "esp32", "uart")

            if is_usb_adapter:
                usb_ports.append(dev)
            elif has_vid_pid and any(k in meta for k in keywords):
                other_ports.append(dev)
            # Deliberately skip plain ttyS* with no VID/PID — kernel ghost ports

        return sorted(set(usb_ports)) + sorted(set(other_ports))
    except ImportError:
        return []
    except (OSError, RuntimeError) as exc:
        import sys
        print(f"Serial port scan failed: {exc}", file=sys.stderr)
        return []


def _send_identify(port: str, expected_device: str) -> dict[str, str] | None:
    try:
        import serial
        import time
        import json
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = 115200
        ser.timeout = 0.5
        ser.dtr = False
        ser.rts = False
        ser.open()
        with ser:
            time.sleep(0.2)
            ser.reset_input_buffer()
            # Send the empty string ping to trigger "TX Ready" or "RX Ready"
            ser.write(b"\n")
            ser.flush()
            
            for _ in range(5):
                raw = ser.readline().strip()
                if raw:
                    resp = raw.decode("utf-8", errors="replace").strip()
                    
                    # Check for the new ping response format
                    if ("TX Ready" in resp or "TX Stream Ready" in resp) and expected_device == "VLC_TX":
                        return {
                            "device": "VLC_TX",
                            "firmware": "tx_unknown",
                            "board": "ESP32",
                        }
                    elif ("RX Ready" in resp or "RX Stream Ready" in resp) and expected_device == "VLC_RX":
                        return {
                            "device": "VLC_RX",
                            "firmware": "rx_unknown",
                            "board": "ESP32",
                        }
                        
                    # Fallback to the old IDENTIFY JSON format
                    if resp.startswith("{"):
                        j = json.loads(resp)
                        if isinstance(j, dict) and j.get("device") == expected_device:
                            return {
                                "device": str(j.get("device", "")),
                                "firmware": str(j.get("firmware", "")),
                                "board": str(j.get("board", "")),
                            }
    except Exception:
        pass
    return None
