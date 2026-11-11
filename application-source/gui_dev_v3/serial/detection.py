"""Serial port detection — role-aware baud rates for TX (115200) and RX (460800)."""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

# TX firmware: 115200 baud (tx_dma.ino / tx_non_dma.ino → Serial.begin(115200))
# RX firmware: 460800 baud (rx.ino → Serial.begin(460800))
BAUDRATE_TX = 115200
BAUDRATE_RX = 460800

# Legacy alias used by session.py connect() — defaults to TX; RXPhysicalBackend
# overrides with RX_BAUD directly so this only affects TXSerialController.
BAUDRATE = BAUDRATE_TX

# Both TX and RX consoles may scan from separate processes. Serialize the
# complete identify -> persistent-open sequence so one role cannot repeatedly
# steal the other role's candidate port between the probe and final open.
_SERIAL_SCAN_LOCK_PATH = Path.home() / ".vlc_app" / "serial_scan.lock"


@contextmanager
def serial_scan_lock(timeout: float = 20.0):
    """Acquire a cross-process lock around serial discovery and connection.

    The lock is released automatically if a scan fails or the process exits.
    It protects only discovery/connection setup; active TX and RX serial
    sessions remain independent and can operate simultaneously.
    """
    path = _SERIAL_SCAN_LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.0, timeout)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\\0")
                stream.flush()
            while True:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for the shared serial scan lock")
                    time.sleep(0.05)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            while True:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for the shared serial scan lock")
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


# Probe order: try RX baud first (it will reject TX firmware), then TX baud
_PROBE_BAUDS = (BAUDRATE_RX, BAUDRATE_TX)

# Startup banner substrings that identify each firmware role
_RX_BANNER = "LiFi 4B5B RX"
_TX_BANNER = "LiFi 4B5B TX"


@dataclass(frozen=True)
class SerialPortInfo:
    device: str
    label: str
    description: str = ""


def list_serial_ports() -> list[SerialPortInfo]:
    try:
        import serial.tools.list_ports  # type: ignore[import-untyped]

        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append(
                SerialPortInfo(
                    device=port.device,
                    label=f"{port.device} — {port.description}",
                    description=port.description,
                )
            )
        return ports
    except ImportError:
        return [
            SerialPortInfo(
                device="/dev/ttyUSB0",
                label="/dev/ttyUSB0 — Mock port",
                description="Mock serial port for dev",
            )
        ]


def probe_serial_port(device: str) -> tuple[str, list[str]]:
    """Probe one port under the same cross-process lock used by both backends."""
    try:
        with serial_scan_lock():
            return _probe_serial_port_locked(device)
    except TimeoutError:
        return ("error", [])


def _probe_serial_port_locked(device: str) -> tuple[str, list[str]]:
    """Auto-detect firmware role by probing at RX baud (460800) then TX baud (115200).

    Returns ("rx"|"tx"|"unknown"|"error", lines_received).
    """
    try:
        import serial  # type: ignore[import-untyped]
    except ImportError:
        return ("error", [])

    for baud in _PROBE_BAUDS:
        lines: list[str] = []
        try:
            # Configure modem-control lines before opening: opening a USB-UART
            # port with DTR/RTS asserted can reset some ESP32 boards. Exclusive
            # ownership prevents the TX and RX app scanners from probing the
            # same POSIX serial device simultaneously.
            ser = serial.Serial()
            ser.port = device
            ser.baudrate = baud
            ser.timeout = 0.4
            ser.dtr = False
            ser.rts = False
            ser.exclusive = True
            ser.open()
            with ser:
                for _ in range(6):
                    ser.write(b"\n")
                    try:
                        raw = ser.readline()
                        if raw:
                            line = raw.decode("utf-8", errors="replace").strip()
                            if line:
                                lines.append(line)
                    except Exception:
                        break
        except Exception:
            # A busy/locked port is not a firmware mismatch; another scan pass
            # can retry after the other application releases it.
            continue

        # Check banner lines for role markers
        combined = " ".join(lines).upper()
        if _RX_BANNER.upper() in combined:
            return ("rx", lines)
        if _TX_BANNER.upper() in combined:
            return ("tx", lines)

        # Fallback: look for bare "RX" / "TX" prefix tokens
        for line in lines:
            upper = line.upper()
            if upper.startswith("RX") or "VLC_RX" in upper:
                return ("rx", lines)
            if upper.startswith("TX") or "VLC_TX" in upper:
                return ("tx", lines)

    return ("unknown", [])


def infer_firmware_role(device: str) -> str:
    role, _ = probe_serial_port(device)
    return role


def baud_for_role(role: str) -> int:
    """Return the correct baud rate for a given firmware role string."""
    if role == "rx":
        return BAUDRATE_RX
    return BAUDRATE_TX
