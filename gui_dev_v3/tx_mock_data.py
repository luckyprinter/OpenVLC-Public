"""Mock data matching the VLC Transmitter dashboard from the UI image."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TXSettings:
    """Transmission settings matching the TX dashboard design."""
    encoding: str = "4B5B"
    modulation: str = "NRZ / OOK"
    symbol_rate: str = "15,000 sym/s"
    led_pin: str = "GPIO 25"
    tx_power: str = "100 %"
    pre_emphasis: str = "Enabled"


@dataclass
class TXFileInfo:
    """File info matching the TX dashboard design."""
    filename: str = "thesis.pdf"
    filetype: str = "PDF Document"
    size_bytes: int = 24_810  # 24.81 KiB
    total_chunks: int = 97
    chunk_size: int = 256


@dataclass
class TXProgress:
    """Transmission progress matching the TX dashboard."""
    percent: int = 0
    current_chunk: int = 0
    total_chunks: int = 97
    elapsed_time: str = "00:00:00"
    estimated_time: str = "00:00:00"
    data_rate: str = "0 bps"


@dataclass
class TXState:
    """Full TX state matching the dashboard image."""
    file: TXFileInfo = field(default_factory=TXFileInfo)
    settings: TXSettings = field(default_factory=TXSettings)
    progress: TXProgress = field(default_factory=TXProgress)
    status: str = "Ready to transmit"
    serial_connected: bool = True
    port: str = "COM6"
    activity_log: list[dict[str, str]] = field(default_factory=list)


def build_mock_tx_log() -> list[dict[str, str]]:
    return [
        {"time": "12:45:10", "event": "System ready"},
        {"time": "12:45:15", "event": "File loaded", "details": "thesis.pdf (24.81 KiB)"},
        {"time": "12:45:18", "event": "Total chunks", "details": "97"},
        {"time": "12:45:20", "event": "Ready to transmit..."},
    ]


def build_mock_tx_state() -> TXState:
    return TXState(
        file=TXFileInfo(),
        settings=TXSettings(),
        progress=TXProgress(),
        status="Ready to transmit",
        serial_connected=True,
        port="COM6",
        activity_log=build_mock_tx_log(),
    )
