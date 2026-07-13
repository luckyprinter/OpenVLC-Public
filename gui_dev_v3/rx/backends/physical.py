"""RX Physical Backend — live serial communication with ESP32 VLC_RX.

Communicates with actual VLC_RX firmware at 460800 baud (RX) or 115200 baud (TX).
- Sends IDENTIFY to detect and read firmware version
- Opens persistent serial connection after detection
- Polls LQ? every refresh() for live signal quality (PVo, Vref, margin, swing)
- Falls back to vlc_beta bridge files when serial unavailable but process is fresh
- No mock data, no simulated values
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gui_dev_v3.data.records import load_real_transfer_history
from gui_dev_v3.data.session import build_empty_session, build_session_from_status
from gui_dev_v3.data.status import read_status
from gui_dev_v3.models import SessionState, SignalState, TransferRecord, TransferStatus

# Resolve beta state dir with VLC_DATA_DIR env var fallback
def _resolve_beta_state_dir() -> Path:
    import os
    env = os.getenv("VLC_DATA_DIR")
    if env:
        return Path(env).expanduser() / "state"
    return Path(__file__).resolve().parents[4] / "vlc_beta" / "state"

BETA_STATE_DIR = _resolve_beta_state_dir()
STATUS_FRESHNESS_SEC = 30.0

# RX firmware runs at 460800, TX at 115200 — try both for IDENTIFY
BAUD_RATES = (460800, 115200)
RX_BAUD = 460800
LQ_POLL_CMD = b"LQ?\n"


@dataclass
class RXPhysicalSnapshot:
    """Immutable data packet from the physical backend."""
    session: SessionState
    transfer: TransferRecord
    activity_log: list[dict[str, str]]
    serial_connected: bool
    device_port: str
    firmware_version: str = ""
    board_type: str = ""
    ports_scanned: int = 0
    firmware_found: bool = False


class RXPhysicalBackend:
    """Physical mode backend — live serial with ESP32 VLC_RX firmware.

    - Scans USB serial ports
    - Sends IDENTIFY at 460800 / 115200 baud to detect VLC_RX
    - Opens persistent serial connection for live LQ polling
    - Reads firmware version from IDENTIFY response
    - Reads pins 34 (PVo ADC) and 35 (Vref ADC) and 5 (data in)
    """

    def __init__(self) -> None:
        self._port: str | None = None
        self._connected: bool = False
        self._firmware_info: dict[str, str] | None = None
        self._ser: Any = None  # pyserial Serial object
        self._baud_rate: int = RX_BAUD

    # ── Port detection ──

    def scan_ports(self) -> list[str]:
        return _list_usb_serial_ports()

    def detect_firmware(self, port: str) -> dict[str, str] | None:
        """Try IDENTIFY at all known baud rates."""
        for baud in BAUD_RATES:
            info = _send_identify(port, "VLC_RX", baud)
            if info:
                self._firmware_info = info
                return info
        return None

    # ── Connection lifecycle ──

    def auto_connect(self) -> bool:
        """Auto-detect: scan → IDENTIFY → open persistent serial."""
        ports = self.scan_ports()
        for port in ports:
            info = self.detect_firmware(port)
            if info and info.get("device") == "VLC_RX":
                self._port = port
                self._connected = True
                self._open_serial()
                self.apply_link_settings()
                return True
        return False

    def connect(self, port: str) -> bool:
        """Connect to a specific port after firmware detection."""
        info = self.detect_firmware(port)
        if info:
            self._port = port
            self._connected = True
            self._open_serial()
            self.apply_link_settings()
            return True
        return False

    def disconnect(self) -> None:
        self._close_serial()
        self._port = None
        self._connected = False
        self._firmware_info = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def port(self) -> str | None:
        return self._port

    @property
    def firmware_version(self) -> str:
        return self._firmware_info.get("firmware", "") if self._firmware_info else ""

    @property
    def board_type(self) -> str:
        return self._firmware_info.get("board", "") if self._firmware_info else ""

    def _open_serial(self) -> None:
        """Open persistent serial connection at RX baud rate."""
        self._close_serial()
        if not self._port:
            return
        try:
            import serial
            self._ser = serial.Serial(
                self._port,
                RX_BAUD,
                timeout=0.5,
                write_timeout=0.5,
            )
            # Flush any stale data
            time.sleep(0.1)
            self._ser.reset_input_buffer()
        except Exception:
            self._ser = None

    def _close_serial(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def send_command(self, cmd: str) -> bool:
        """Write cmd string over serial."""
        if not self._connected or not self._ser:
            return False
        try:
            self._ser.write(cmd.encode("utf-8"))
            self._ser.flush()
            return True
        except Exception:
            return False

    def apply_link_settings(self) -> None:
        """Apply saved settings to physical RX firmware."""
        if not self._connected or not self._ser:
            return
        from gui_dev_v3.settings import SettingsManager
        mgr = SettingsManager("rx")
        
        symbol_hz = int(mgr.get("link/symbol_hz", 15000))
        sample_phase_pct = int(mgr.get("link/sample_phase_pct", 50))
        vref_target_mv = int(mgr.get("link/vref_target_mv", 1700))
        vref_margin_mv = int(mgr.get("link/vref_margin_mv", 365))
        vref_pwm_full_scale_mv = int(mgr.get("link/vref_pwm_full_scale_mv", 2625))
        vref_settle_ms = int(mgr.get("link/vref_settle_ms", 120))
        vref_auto = 1 if mgr.get("link/vref_auto", False) else 0
        majority_sampling = 1 if mgr.get("link/majority_sampling", True) else 0
        report_chunks = 1 if mgr.get("link/report_chunks", False) else 0
        invert_symbols = 1 if mgr.get("link/invert_symbols", False) else 0
        
        self.send_command(f"FREQ={symbol_hz}\n")
        self.send_command(f"PHASE={sample_phase_pct}\n")
        if vref_auto:
            self.send_command("VREF_MODE=AUTO\n")
        else:
            self.send_command("VREF_MODE=MANUAL\n")
            self.send_command(f"VREF_SET={vref_target_mv}\n")
        self.send_command(f"VREF_MARGIN={vref_margin_mv}\n")
        self.send_command(f"VREF_PWM_FS={vref_pwm_full_scale_mv}\n")
        self.send_command(f"VREF_SETTLE_MS={vref_settle_ms}\n")
        self.send_command(f"MAJ={majority_sampling}\n")
        self.send_command(f"REPORT={report_chunks}\n")
        self.send_command(f"INVERT={invert_symbols}\n")

    def cleanup(self) -> None:
        """Close serial connection and release port."""
        self._close_serial()

    # ── Live data acquisition ──

    def _poll_lq(self) -> dict[str, float] | None:
        """Send LQ? and parse the response for signal quality metrics.

        RX firmware responds with something like:
          LQ, SIGNAL=2.846, VREF=2.481, MARGIN=0.365, SWING=0.120, STATUS=...

        Returns dict with keys: SIGNAL, VREF, MARGIN, SWING, PASS_RATE (floats).
        """
        if self._ser is None:
            return None
        try:
            # Flush input, send command
            self._ser.reset_input_buffer()
            self._ser.write(LQ_POLL_CMD)
            self._ser.flush()

            # Read response lines with timeout
            raw = b""
            deadline = time.time() + 1.0
            while time.time() < deadline:
                if self._ser.in_waiting:
                    chunk = self._ser.read(self._ser.in_waiting)
                    raw += chunk
                    if b"\n" in raw or b"\r" in raw:
                        break
                else:
                    time.sleep(0.05)

            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                return None

            return _parse_lq_response(line)
        except Exception:
            return None

    def refresh(self) -> RXPhysicalSnapshot:
        """Read current state from live serial or vlc_beta bridge.

        Priority:
          1. Live serial: send LQ?, parse signal data
          2. vlc_beta bridge: fresh status files (serial not available)
          3. Empty offline state
        """
        if not self._connected:
            return self._empty_snapshot()

        # Try live serial first
        if self._ser is not None:
            import serial
            try:
                _ensure_serial(self._ser)
            except serial.SerialException:
                # Hot plug / disconnect detected
                self.disconnect()
                return self._empty_snapshot()
            except Exception:
                self._close_serial()

        if self._ser is not None:
            lq_data = self._poll_lq()
            if lq_data:
                return self._build_from_lq(lq_data)

        # Fallback: vlc_beta bridge files
        rx_status = read_status("rx")
        sig_status = read_status("signal")

        if _is_fresh(rx_status) or _is_fresh(sig_status):
            session, transfers = self._build_from_status(rx_status, sig_status)
            latest = transfers[0] if transfers else session.latest_transfer
            log = self._build_log(rx_status, sig_status)
            return RXPhysicalSnapshot(
                session=session,
                transfer=latest,
                activity_log=log,
                serial_connected=bool(rx_status) or bool(sig_status),
                device_port=self._port or "",
                firmware_version=self._firmware_info.get("firmware", "") if self._firmware_info else "",
                board_type=self._firmware_info.get("board", "") if self._firmware_info else "",
                ports_scanned=len(self.scan_ports()),
                firmware_found=self._connected,
            )

        # Check if serial connection looks alive
        if self._ser and not self._ser.closed:
            return self._build_stale()

        return self._empty_snapshot()

    def _build_from_lq(self, lq: dict[str, float]) -> RXPhysicalSnapshot:
        """Build a snapshot from live LQ poll data (pins 34, 35, 5)."""
        now = time.strftime("%H:%M:%S")
        pvo = lq.get("SIGNAL", 0.0)
        vref = lq.get("VREF", 0.0)
        margin = lq.get("MARGIN", 0.0)
        swing = lq.get("SWING", 0.0)
        pass_rate = lq.get("PASS_RATE", 100.0)
        status_str = lq.get("STATUS", "SUCCESS_RANGE")

        # Quality label from margin
        if margin > 0.3:
            label = "Excellent"
        elif margin > 0.2:
            label = "Good"
        elif margin > 0.1:
            label = "Fair"
        elif margin > 0.05:
            label = "Poor"
        else:
            label = "No Signal"

        signal = SignalState(
            label=label,
            pvo=round(pvo, 3),
            vref=round(vref, 3),
            margin=round(margin, 3),
            target_margin=0.365,
            adc_vref=3.300,
            lux=int(pvo * 150) if pvo > 0 else 0,  # rough lux estimate from PVo
            data_rate=0.0,  # updated by transfer activity
            ber=0.0,
            strict_ber=0.0,
            crc_status="PASS" if pass_rate > 80 else "FAIL",
            time_elapsed="--",
        )

        session = SessionState(
            role="RX",
            connected_device=f"{self._port or ''} @ {RX_BAUD} baud",
            current_file="No active transfer",
            progress_percent=0,
            signal=signal,
            latest_transfer=_empty_transfer(),
        )

        log = [
            {"time": now, "event": "Connected", "details": f"Port {self._port} @ {RX_BAUD} baud"},
            {"time": now, "event": "LQ Poll", "details": f"PVo={pvo:.3f}V Vref={vref:.3f}V Margin={margin:.3f}V"},
        ]
        if self._firmware_info:
            fw = self._firmware_info.get("firmware", "")
            board = self._firmware_info.get("board", "")
            log.append({"time": now, "event": "Firmware", "details": f"v{fw} on {board}"})

        return RXPhysicalSnapshot(
            session=session,
            transfer=session.latest_transfer,
            activity_log=log,
            serial_connected=True,
            device_port=self._port or "",
            firmware_version=self._firmware_info.get("firmware", "") if self._firmware_info else "",
            board_type=self._firmware_info.get("board", "") if self._firmware_info else "",
            ports_scanned=len(self.scan_ports()),
            firmware_found=True,
        )

    def _build_from_status(self, rx_status: dict | None,
                           sig_status: dict | None) -> tuple[SessionState, list[TransferRecord]]:
        """Build state from vlc_beta bridge files."""
        transfers = load_real_transfer_history()
        latest = transfers[0] if transfers else None
        session = build_session_from_status("rx", latest)
        signal = session.signal

        if sig_status:
            pvo = float(sig_status.get("pvo_v") or signal.pvo or 0.0)
            vref = float(sig_status.get("vref_v") or signal.vref or 0.0)
            margin = float(sig_status.get("margin_v") or signal.margin or 0.0)
            signal = SignalState(
                label=str(sig_status.get("quality_label") or signal.label),
                pvo=round(pvo, 3),
                vref=round(vref, 3),
                margin=round(margin, 3),
                target_margin=float(sig_status.get("margin_best_v") or 0.365),
                adc_vref=3.300,
                lux=int(pvo * 150) if pvo > 0 else 0,
                data_rate=float(sig_status.get("rate_bps", 0)) / 1000.0,
                ber=0.0,
                strict_ber=0.0,
                crc_status="PASS" if sig_status.get("state") in ("success", "active") else "Unknown",
                time_elapsed="--",
            )
            session = SessionState(
                role=session.role,
                connected_device=session.connected_device,
                current_file=session.current_file,
                progress_percent=session.progress_percent,
                signal=signal,
                latest_transfer=session.latest_transfer,
            )

        return session, transfers

    def _build_stale(self) -> RXPhysicalSnapshot:
        """Serial open but no fresh data yet."""
        now = time.strftime("%H:%M:%S")
        session = build_empty_session()
        return RXPhysicalSnapshot(
            session=session,
            transfer=session.latest_transfer,
            activity_log=[
                {"time": now, "event": "Connected", "details": f"Serial open on {self._port}"},
                {"time": now, "event": "Waiting", "details": "Polling LQ... (no response yet)"},
            ],
            serial_connected=True,
            device_port=self._port or "",
            firmware_version=self._firmware_info.get("firmware", "") if self._firmware_info else "",
            board_type=self._firmware_info.get("board", "") if self._firmware_info else "",
            ports_scanned=0,
            firmware_found=True,
        )

    def _empty_snapshot(self) -> RXPhysicalSnapshot:
        now = time.strftime("%H:%M:%S")
        session = build_empty_session()
        tip = "Switch to Simulation mode for virtual data" if not self._connected \
               else "Connect RX ESP32 and detect firmware"
        return RXPhysicalSnapshot(
            session=session,
            transfer=session.latest_transfer,
            activity_log=[
                {"time": now, "event": "Offline", "details": "No hardware connected"},
                {"time": now, "event": "Tip", "details": tip},
            ],
            serial_connected=False,
            device_port="",
            ports_scanned=len(self.scan_ports()),
            firmware_found=False,
        )

    def _build_log(self, rx_status: dict | None,
                   sig_status: dict | None) -> list[dict[str, str]]:
        log = []
        now = time.strftime("%H:%M:%S")
        if rx_status:
            stage = str(rx_status.get("stage", ""))
            detail = str(rx_status.get("detail", ""))
            percent = rx_status.get("percent")
            if stage:
                log.append({"time": now, "event": str(stage), "details": str(detail)[:80]})
            if percent is not None and float(percent) > 0:
                log.append({"time": now, "event": "Progress", "details": f"{float(percent):.0f}% complete"})
        if sig_status:
            margin = sig_status.get("margin_v")
            pvo = sig_status.get("pvo_v")
            if margin is not None:
                log.append({"time": now, "event": "Signal", "details": f"Margin: {float(margin):.3f}V"})
            if pvo is not None:
                log.append({"time": now, "event": "Signal", "details": f"PVo: {float(pvo):.3f}V"})
        if not log:
            log.append({"time": now, "event": "Status", "details": "No active transfer data"})
        return log


# ── Helpers ──

def _is_fresh(status: dict | None, max_age: float = STATUS_FRESHNESS_SEC) -> bool:
    if not status:
        return False
    updated = status.get("updated_at")
    if updated is not None:
        return (time.time() - float(updated)) < max_age
    return False


def _list_usb_serial_ports() -> list[str]:
    try:
        import serial.tools.list_ports
        ports = []
        for port in serial.tools.list_ports.comports():
            meta = f"{port.device or ''} {port.description or ''} {port.hwid or ''}".lower()
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


def _send_identify(port: str, expected_device: str, baud: int = 115200) -> dict[str, str] | None:
    """Send IDENTIFY at a specific baud rate, expect JSON response."""
    try:
        import serial
        with serial.Serial(port, baud, timeout=0.5) as ser:
            time.sleep(0.1)
            ser.reset_input_buffer()
            ser.write(b"IDENTIFY\n")
            ser.flush()
            raw = ser.readline().strip()
            if raw:
                resp = json.loads(raw.decode("utf-8", errors="replace"))
                if isinstance(resp, dict) and resp.get("device") == expected_device:
                    return {
                        "device": str(resp.get("device", "")),
                        "firmware": str(resp.get("firmware", "")),
                        "board": str(resp.get("board", "")),
                    }
    except (ImportError, OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError):
        pass
    return None


def _parse_lq_response(line: str) -> dict[str, float] | None:
    """Parse LQ telemetry line from RX firmware.

    Handles formats:
      LQ, SIGNAL=2.846, VREF=2.481, MARGIN=0.365, SWING=0.120, STATUS=...
      LQ snapshot: SIGNAL=2.846, VREF=2.481, MARGIN=0.365, ...
      CAL_LQ: SIGNAL=...
    """
    # Strip prefix
    for prefix in ("LQ,", "LQ snapshot:", "CAL_LQ:", "LQ "):
        idx = line.find(prefix)
        if idx >= 0:
            line = line[idx + len(prefix):]
            break

    pairs = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=([^,\s]+)", line)
    if not pairs:
        return None

    # Normalise keys
    key_map = {
        "SIGNAL": "SIGNAL", "PVO": "SIGNAL", "PV0": "SIGNAL", "SIG": "SIGNAL", "SIG_MAX": "SIGNAL",
        "VREF": "VREF", "MEASURED_V": "VREF",
        "MARGIN": "MARGIN", "ACHIEVED_MARGIN": "MARGIN",
        "SWING": "SWING",
        "PASS_RATE": "PASS_RATE", "PASS": "PASS_RATE", "PASSRATE": "PASS_RATE",
        "STATUS": "STATUS",
    }
    result: dict[str, float] = {}
    for key, raw_val in pairs:
        upper_key = key.strip().upper()
        norm: str = upper_key  # explicit str type
        if upper_key in key_map:
            norm = key_map[upper_key]
        try:
            # Extract first float from value
            match = re.search(r"[-+]?\d+(?:\.\d+)?", raw_val)
            if match:
                result[norm] = float(match.group(0))
        except (ValueError, TypeError):
            pass
    return result if result else None


def _ensure_serial(ser: Any) -> None:
    """Check serial is still open. Raises if not."""
    if ser is None or ser.closed:
        raise ConnectionError("Serial closed")


def _empty_transfer() -> TransferRecord:
    """Build an empty TransferRecord for offline state."""
    from gui_dev_v3.models import TransferQuality, TransferStatus
    return TransferRecord(
        tid=0, filename="No data",
        status=TransferStatus.PENDING,
        time_label="", size_bytes=0,
        total_chunks=0, received_chunks=0,
        quality=TransferQuality(
            label="No Data", strict_ber=0.0, bit_accuracy=100.0,
            bit_errors=0, total_bits=0, compared_bytes=0,
            missing_chunks=0, missing_bytes=0,
            first_issue="None", crc_status="", recovery_rate=0.0,
        ),
    )
