"""Serial port detection — role-aware baud rates for TX (115200) and RX (460800)."""

from __future__ import annotations

import sys
from dataclasses import dataclass

# TX firmware: 115200 baud (tx_dma.ino / tx_non_dma.ino → Serial.begin(115200))
# RX firmware: 460800 baud (rx.ino → Serial.begin(460800))
BAUDRATE_TX = 115200
BAUDRATE_RX = 460800

# Legacy alias used by session.py connect() — defaults to TX; RXPhysicalBackend
# overrides with RX_BAUD directly so this only affects TXSerialController.
BAUDRATE = BAUDRATE_TX

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
            ser = serial.Serial(device, baud, timeout=0.4)
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
            ser.close()
        except Exception:
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
