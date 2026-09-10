"""TX Simulation Backend — virtual VLC channel model.

Generates all TX data from configurable parameters.
No serial ports. No firmware. No filesystem dependencies.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any

from gui_dev_v3.tx_mock_data import TXFileInfo, TXProgress, TXSettings, TXState
from PySide6.QtCore import QTimer, Qt
from PySide6.QtNetwork import QUdpSocket, QHostAddress


@dataclass
class TXSimulationSnapshot:
    """Immutable data packet from the TX simulation backend."""
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
    tid: int
    channel_params: "VirtualChannelParams"


@dataclass
class VirtualChannelParams:
    """Tunable virtual VLC channel parameters."""
    distance_m: float = 1.0
    noise_floor_mv: float = 15.0
    lux: int = 420
    led_wattage_w: float = 10.0
    packet_loss_pct: float = 5.0
    # TX-specific
    symbol_hz: int = 15000
    preamble_bits: int = 64
    encoding: str = "4B5B"
    chunk_size: int = 256
    file_size_kb: int = 24
    post_frame_idle_ms: int = 0
    frame_gap_ms: int = 1
    active_low: bool = False
    idle_on: bool = True
    cal_intensity_pct: int = 35
    quiet_mode: bool = True
    # Derived
    snr_db: float = 0.0


class TXSimulationBackend:
    """Simulation mode backend — virtual TX channel model.

    No hardware needed. Connects to RX app over localhost UDP port 9901/9902.
    """

    def __init__(self, params: VirtualChannelParams | None = None) -> None:
        self._params = params or VirtualChannelParams()
        self._tick = 0
        self._progress: float = 0.0
        self._session_start = time.time()
        self._status_text = "Ready to transmit"

        # Heartbeat and connection state
        self._rx_connected = False
        self._last_rx_time = time.time()
        self._log: list[dict[str, str]] = []

        # Transmission file state
        self._file_data = b""
        self._filename = "No file"
        self._total_chunks = 0
        self._current_chunk = 0
        self._chunk_size = 256
        self._transfer_id = 0

        # UDP Sockets setup
        self._socket = QUdpSocket()
        ok = self._socket.bind(QHostAddress(QHostAddress.SpecialAddress.LocalHost), 9902, QUdpSocket.BindFlag.ReuseAddressHint)
        if ok:
            self._socket.readyRead.connect(self._on_ready_read)
        else:
            err = self._socket.errorString()
            self._log_append({
                "time": time.strftime("%H:%M:%S"),
                "event": "Error",
                "details": f"UDP bind failed on port 9902: {err}"
            })

        # Heartbeat timer (pings every 1 second)
        self._ping_timer = QTimer()
        self._ping_timer.timeout.connect(self._send_heartbeat)
        self._ping_timer.start(1000)

        # File chunk send timer
        self._send_timer = QTimer()
        self._send_timer.timeout.connect(self._send_next_chunk)

    def stop(self) -> None:
        """Stop all timers and close sockets gracefully to prevent leak."""
        if hasattr(self, "_ping_timer") and self._ping_timer:
            self._ping_timer.stop()
        if hasattr(self, "_send_timer") and self._send_timer:
            self._send_timer.stop()
        if hasattr(self, "_socket") and self._socket:
            try:
                self._socket.readyRead.disconnect()
            except Exception:
                pass
            self._socket.close()
            self._socket.deleteLater()
            self._socket = None

    def cleanup(self) -> None:
        """Alias for stop() to support unified state cleanup."""
        self.stop()

    def _log_append(self, entry: dict[str, str]) -> None:
        """Append log entry and cap size to prevent memory leak."""
        self._log.append(entry)
        if len(self._log) > 500:
            del self._log[:100]

    def _send_heartbeat(self) -> None:
        import json
        ping_msg = {"event": "ping"}
        ping_bytes = json.dumps(ping_msg).encode("utf-8")
        self._socket.writeDatagram(ping_bytes, QHostAddress(QHostAddress.SpecialAddress.LocalHost), 9901)

    def _on_ready_read(self) -> None:
        import json
        while self._socket.hasPendingDatagrams():
            size = self._socket.pendingDatagramSize()
            data, sender_host, sender_port = self._socket.readDatagram(size)
            try:
                msg_str = data.data().decode("utf-8", errors="replace")
                msg = json.loads(msg_str)
                if msg.get("event") == "ping_reply":
                    self._rx_connected = True
                    self._last_rx_time = time.time()
            except Exception:
                pass

    def start_transmission(self, filepath: str) -> None:
        from pathlib import Path
        import json
        p = self._params
        self._compute_channel()

        path = Path(filepath)
        if not path.exists():
            now = time.strftime("%H:%M:%S")
            self._log_append({"time": now, "event": "Error", "details": f"File {path.name} not found"})
            return

        self._file_data = path.read_bytes()
        self._filename = path.name
        self._chunk_size = p.chunk_size
        self._total_chunks = max(1, math.ceil(len(self._file_data) / self._chunk_size))
        self._current_chunk = 0
        self._progress = 0.0
        self._session_start = time.time()
        self._status_text = "Transmitting..."
        self._log.clear()

        now = time.strftime("%H:%M:%S")
        self._log_append({"time": now, "event": "Start TX", "details": f"Sending {self._filename} ({self._total_chunks} chunks)"})

        self._transfer_id = int(time.time() * 10) % 100000
        # Send start message to RX
        start_msg = {
            "event": "start_tx",
            "filename": self._filename,
            "total_chunks": self._total_chunks,
            "chunk_size": self._chunk_size,
            "tid": self._transfer_id
        }
        start_bytes = json.dumps(start_msg).encode("utf-8")
        self._socket.writeDatagram(start_bytes, QHostAddress(QHostAddress.SpecialAddress.LocalHost), 9901)

        # Start send timer based on symbol rate
        # Time to send 1 chunk in ms
        delay_ms = int(max(10, ((self._chunk_size * 8) / max(p.symbol_hz, 100)) * 1000.0))
        self._send_timer.start(delay_ms)

    def _send_next_chunk(self) -> None:
        import json
        now = time.strftime("%H:%M:%S")

        # Guard against zero chunks or reset state
        if self._total_chunks == 0:
            self._send_timer.stop()
            return

        # Check connection loss
        if time.time() - self._last_rx_time > 3.0:
            self._rx_connected = False
            self._send_timer.stop()
            self._progress = 0.0
            self._status_text = "Failed"
            self._log_append({"time": now, "event": "Abort", "details": "Connection to RX lost"})
            return

        start_offset = self._current_chunk * self._chunk_size
        end_offset = start_offset + self._chunk_size
        chunk_bytes = self._file_data[start_offset:end_offset]

        # Send chunk message to RX
        chunk_msg = {
            "event": "chunk",
            "index": self._current_chunk,
            "data": chunk_bytes.hex()
        }
        chunk_bytes_data = json.dumps(chunk_msg).encode("utf-8")
        self._socket.writeDatagram(chunk_bytes_data, QHostAddress(QHostAddress.SpecialAddress.LocalHost), 9901)

        self._current_chunk += 1
        self._progress = (self._current_chunk / self._total_chunks) * 100.0

        if self._current_chunk >= self._total_chunks:
            self._send_timer.stop()
            self._status_text = "Complete"
            self._progress = 100.0
            # Send stop message to RX
            stop_msg = {"event": "stop_tx"}
            stop_bytes = json.dumps(stop_msg).encode("utf-8")
            self._socket.writeDatagram(stop_bytes, QHostAddress(QHostAddress.SpecialAddress.LocalHost), 9901)
            self._log_append({"time": now, "event": "Complete", "details": "Transmission successful"})

    @property
    def params(self) -> VirtualChannelParams:
        return self._params

    def set_params(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._params, k):
                setattr(self._params, k, v)

    def _compute_channel(self) -> None:
        p = self._params
        signal = (p.led_wattage_w * 1000) / max(p.distance_m ** 2, 0.01)
        ambient_noise = p.noise_floor_mv + (p.lux * 0.01)
        if ambient_noise > 0:
            p.snr_db = 20 * math.log10(max(signal / ambient_noise, 1.0))
        else:
            p.snr_db = 60.0

    def _build_log(self) -> list[dict[str, str]]:
        if self._log:
            return self._log[-10:]

        now = time.strftime("%H:%M:%S")
        p = self._params
        log: list[dict[str, str]] = []
        log.append({"time": now, "event": "System ready"})
        if self._rx_connected:
            log.append({"time": now, "event": "Connected", "details": "Simulated Receiver detected"})
        else:
            log.append({"time": now, "event": "Ready", "details": "Waiting for simulated RX..."})
        return log

    def refresh(self) -> TXSimulationSnapshot:
        """Generate a new data snapshot from the virtual channel model."""
        p = self._params
        self._compute_channel()

        # Connection timeout check
        if time.time() - self._last_rx_time > 3.0:
            self._rx_connected = False

        total_chunks = self._total_chunks if self._total_chunks > 0 else max((p.file_size_kb * 1024) // max(p.chunk_size, 1), 1)
        current = self._current_chunk

        elapsed = time.time() - self._session_start
        hours, rem = divmod(int(elapsed), 3600)
        mins, secs = divmod(rem, 60)
        elapsed_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

        # Data rate and time from physical model
        symbols_per_chunk = (p.chunk_size * 8 * 1.25) + p.preamble_bits
        time_per_chunk_s = symbols_per_chunk / max(p.symbol_hz, 1) + (p.frame_gap_ms / 1000.0)
        
        # Adjust for packet loss overhead
        effective_time_per_chunk = time_per_chunk_s / max(0.01, (1 - p.packet_loss_pct / 100))
        
        data_rate_bps = int((p.chunk_size * 8) / effective_time_per_chunk)
        data_rate_str = f"{data_rate_bps:,} bps"

        est_remaining = "00:00:00"
        if data_rate_bps > 0 and self._progress < 100:
            remain_secs = int((total_chunks - current) * effective_time_per_chunk)
            h, r = divmod(remain_secs, 3600)
            m, s = divmod(r, 60)
            est_remaining = f"{h:02d}:{m:02d}:{s:02d}"

        filename = self._filename if self._filename != "No file" else f"sim_{p.file_size_kb}kb.bin"
        file_size = len(self._file_data) if len(self._file_data) > 0 else p.file_size_kb * 1024

        log = self._build_log()

        return TXSimulationSnapshot(
            filename=filename,
            filetype="Binary Data" if self._filename != "No file" else "",
            file_size_bytes=file_size,
            total_chunks=total_chunks,
            chunk_size=p.chunk_size,
            encoding=p.encoding,
            modulation="NRZ / OOK",
            symbol_rate=f"{p.symbol_hz:,} sym/s",
            led_pin=25,
            tx_power="100 %",
            pre_emphasis="Enabled",
            status_text=self._status_text,
            progress_percent=int(self._progress),
            current_chunk=current,
            elapsed_time=elapsed_str,
            estimated_time=est_remaining,
            data_rate=data_rate_str,
            port="—",
            serial_connected=self._rx_connected,
            activity_log=log,
            record_count=1,
            tid=self._transfer_id,
            channel_params=p,
        )
