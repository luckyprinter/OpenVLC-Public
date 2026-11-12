"""Neutral transmitter data models shared by the GUI and physical backend."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TXSettings:
    """Configuration values reported by or sent to the TX firmware."""
    encoding: str = "4B5B"
    modulation: str = "NRZ / OOK"
    symbol_rate: str = "15,000 sym/s"
    led_pin: str = "GPIO 5"
    tx_power: str = "100 %"
    pre_emphasis: str = "Enabled"


@dataclass
class TXFileInfo:
    """Metadata for the file currently selected for transmission."""
    filename: str = "No file"
    filetype: str = ""
    size_bytes: int = 0
    total_chunks: int = 0
    chunk_size: int = 256


@dataclass
class TXProgress:
    """Progress counters reported by the transmitter firmware."""
    percent: int = 0
    current_chunk: int = 0
    total_chunks: int = 0
    elapsed_time: str = "00:00:00"
    estimated_time: str = "00:00:00"
    data_rate: str = "0 bps"


@dataclass
class TXState:
    """Combined transmitter state used by the application."""
    file: TXFileInfo = field(default_factory=TXFileInfo)
    settings: TXSettings = field(default_factory=TXSettings)
    progress: TXProgress = field(default_factory=TXProgress)
    status: str = "Offline — no hardware"
    serial_connected: bool = False
    port: str = "—"
    activity_log: list[dict[str, str]] = field(default_factory=list)
