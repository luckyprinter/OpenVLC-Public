"""Serial port detection — copied from vlc_migration."""

from __future__ import annotations

import sys
from dataclasses import dataclass

BAUDRATE = 115200


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
            ports.append(SerialPortInfo(device=port.device, label=f"{port.device} — {port.description}", description=port.description))
        return ports
    except ImportError:
        return [SerialPortInfo(device="/dev/ttyUSB0", label="/dev/ttyUSB0 — Mock port", description="Mock serial port for dev")]


def probe_serial_port(device: str) -> tuple[str, list[str]]:
    try:
        import serial  # type: ignore[import-untyped]

        ser = serial.Serial(device, BAUDRATE, timeout=0.5)
        ser.write(b"\n")
        lines = []
        for _ in range(5):
            try:
                line = ser.readline().decode("utf-8", errors="replace").strip()
                if line:
                    lines.append(line)
            except Exception:
                break
        ser.close()
        for line in lines:
            if "RX" in line.upper():
                return ("rx", lines)
            if "TX" in line.upper():
                return ("tx", lines)
        return ("unknown", lines)
    except Exception:
        return ("error", [])


def infer_firmware_role(device: str) -> str:
    role, _ = probe_serial_port(device)
    return role
