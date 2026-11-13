"""RX Simulation Backend — virtual VLC channel model.

Generates all data mathematically from configurable parameters:
  - distance, noise floor, lux, LED wattage, packet loss
No serial ports. No firmware. No filesystem dependencies.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any

from gui_dev_v3.models import (
    ChunkRecord,
    ChunkStatus,
    ExperimentMetadata,
    SessionState,
    SignalState,
    TransferQuality,
    TransferRecord,
    TransferStatus,
)
from gui_dev_v3.logic.ber_bridge import transfer_quality_from_chunks
from PySide6.QtNetwork import QUdpSocket, QHostAddress
from PySide6.QtCore import QTimer
from collections import deque

# ── 4B5B Encoding Helper ──
_4B5B_TABLE: dict[int, tuple[int, ...]] = {
    0x0: (1, 1, 1, 1, 0),
    0x1: (0, 1, 0, 0, 1),
    0x2: (1, 0, 1, 0, 0),
    0x3: (1, 0, 1, 0, 1),
    0x4: (0, 1, 0, 1, 0),
    0x5: (0, 1, 0, 1, 1),
    0x6: (0, 1, 1, 1, 0),
    0x7: (0, 1, 1, 1, 1),
    0x8: (1, 0, 0, 1, 0),
    0x9: (1, 0, 0, 1, 1),
    0xA: (1, 0, 1, 1, 0),
    0xB: (1, 0, 1, 1, 1),
    0xC: (1, 1, 0, 1, 0),
    0xD: (1, 1, 0, 1, 1),
    0xE: (1, 1, 1, 0, 0),
    0xF: (1, 1, 1, 0, 1),
}

def _encode_4b5b(data: bytes | None) -> list[int]:
    """Encode data bytes using 4B5B. Returns a flat list of 0/1 bits."""
    bits: list[int] = []
    # Alternating preamble for synchronization
    preamble = [1, 0] * 8
    bits.extend(preamble)
    if data:
        for byte_val in data:
            hi_nibble = (byte_val >> 4) & 0xF
            lo_nibble = byte_val & 0xF
            bits.extend(_4B5B_TABLE[hi_nibble])
            bits.extend(_4B5B_TABLE[lo_nibble])
    return bits



# ── Dataclass ──

@dataclass
class RXSimulationSnapshot:
    """Immutable data packet from the simulation backend."""
    session: SessionState
    transfer: TransferRecord
    activity_log: list[dict[str, str]]
    channel_params: "VirtualChannelParams"


@dataclass
class VirtualChannelParams:
    """Tunable virtual VLC channel parameters."""
    distance_m: float = 1.0          # 0.1 - 10 m
    noise_floor_mv: float = 15.0     # mV
    lux: int = 420                   # ambient light (lux)
    led_wattage_w: float = 10.0       # LED power (W)
    packet_loss_pct: float = 5.0     # 0 - 50%
    total_chunks: int = 100
    chunk_size: int = 16
    # Link parameters
    symbol_hz: int = 15000
    preamble_bits: int = 64
    sample_phase_pct: int = 50
    vref_target_mv: int = 1700
    vref_margin_mv: int = 365
    vref_pwm_full_scale_mv: int = 2625
    vref_settle_ms: int = 120
    vref_auto: bool = False
    majority_sampling: bool = True
    report_chunks: bool = False
    invert_symbols: bool = False
    # Derived (computed each refresh)
    snr_db: float = 0.0
    ber_estimate: float = 0.0


# ── Backend ──

class RXSimulationBackend:
    """Simulation mode backend — virtual VLC channel model.

    No hardware needed. Generates realistic data from user-configurable
    channel parameters and connects over UDP localhost to the TX app.
    """

    def __init__(self, params: VirtualChannelParams | None = None) -> None:
        self._params = params or VirtualChannelParams()
        self._tick = 0
        self._progress: float = 0.0
        self._chunks: list[ChunkRecord] = []
        self._log: list[dict[str, str]] = []
        self._active = False
        self._transfer_id = 0
        self._filename = "No file transfer"
        self._session_start = time.time()

        # UDP and heartbeat states
        self._tx_connected = False
        self._last_tx_time = 0.0
        self._received_chunks_map: dict[int, bytes] = {}
        self._expected_chunks_map: dict[int, bytes] = {}
        self._chunks_status_map: dict[int, ChunkStatus] = {}
        self._total_chunks = 0
        self._chunk_size = 256
        self._transfer_status = TransferStatus.PENDING
        self._expected_file_data: bytes | None = None
        self._expected_file_path: str | None = None
        self._capture_active = False
        self._capture_start_time = 0.0
        self._capture_pvo: list[float] = []
        self._capture_vref: list[float] = []
        self._capture_margin: list[float] = []
        self._capture_time: list[float] = []
        self._capture_bits: list[int] = []
        self._capture_events: list[dict[str, Any]] = []

        # UDP Socket setup
        self._socket = QUdpSocket()
        ok = self._socket.bind(QHostAddress(QHostAddress.SpecialAddress.LocalHost), 9901, QUdpSocket.BindFlag.ReuseAddressHint)
        if ok:
            self._socket.readyRead.connect(self._on_ready_read)
        else:
            err = self._socket.errorString()
            self._log_append({
                "time": time.strftime("%H:%M:%S"),
                "event": "Error",
                "details": f"UDP bind failed on port 9901: {err}"
            })

        # High-fidelity simulation sample generation
        self._bit_queue = deque()
        self._samples_buffer = []
        self._sample_counter = 0
        self._current_pvo = 0.0
        self._idle_pattern_index = 0

        # Simulation timer to generate a new sample every 100 ms
        self._sim_timer = QTimer()
        self._sim_timer.timeout.connect(self._generate_sim_sample)
        self._sim_timer.start(100)


    def cleanup(self) -> None:
        """Close socket and stop simulation backend gracefully."""
        if hasattr(self, "_sim_timer") and self._sim_timer:
            try:
                self._sim_timer.stop()
                self._sim_timer.timeout.disconnect()
            except Exception:
                pass
            self._sim_timer = None

        if hasattr(self, "_socket") and self._socket:
            try:
                self._socket.readyRead.disconnect()
            except Exception:
                pass
            self._socket.close()
            self._socket.deleteLater()
            self._socket = None

    def set_expected_file(self, data: bytes | None, filepath: str | None) -> None:
        """Set or clear the reference expected file data and update chunk statuses."""
        self._expected_file_data = data
        self._expected_file_path = filepath

        # Slice the new expected file
        self._expected_chunks_map.clear()
        if data is not None and self._total_chunks > 0:
            for idx in range(self._total_chunks):
                start_offset = idx * self._chunk_size
                end_offset = start_offset + self._chunk_size
                self._expected_chunks_map[idx] = data[start_offset:end_offset]

        # Re-evaluate statuses of already received chunks
        for idx in range(self._total_chunks):
            status = self._chunks_status_map.get(idx, ChunkStatus.PENDING)
            received_bytes = self._received_chunks_map.get(idx)
            
            if received_bytes is not None:
                expected_chunk = self._expected_chunks_map.get(idx, b"")
                if expected_chunk:
                    if received_bytes == expected_chunk:
                        self._chunks_status_map[idx] = ChunkStatus.MATCH
                    else:
                        self._chunks_status_map[idx] = ChunkStatus.DIFFERENT
                else:
                    self._chunks_status_map[idx] = ChunkStatus.RECEIVED

    def _log_append(self, entry: dict[str, str]) -> None:
        """Append log entry and cap size to prevent memory leak."""
        self._log.append(entry)
        if len(self._log) > 500:
            del self._log[:100]

    def _on_ready_read(self) -> None:
        import json
        while self._socket.hasPendingDatagrams():
            size = self._socket.pendingDatagramSize()
            data, sender_host, sender_port = self._socket.readDatagram(size)
            try:
                msg_str = data.data().decode("utf-8", errors="replace")
                msg = json.loads(msg_str)
                self._handle_udp_msg(msg, sender_host, sender_port)
            except Exception:
                pass

    def _handle_udp_msg(self, msg: dict[str, Any], host: QHostAddress, port: int) -> None:
        import json
        event = msg.get("event")
        now = time.strftime("%H:%M:%S")

        if event == "ping":
            self._tx_connected = True
            self._last_tx_time = time.time()
            # Reply to port 9902
            reply = {"event": "ping_reply"}
            reply_bytes = json.dumps(reply).encode("utf-8")
            self._socket.writeDatagram(reply_bytes, QHostAddress(QHostAddress.SpecialAddress.LocalHost), 9902)

        elif event == "start_tx":
            self._active = True
            self._transfer_id = msg.get("tid", self._transfer_id + 1)
            if self._transfer_id > 999:
                self._transfer_id = 1
            self._filename = msg.get("filename", "simulated_file.bin")
            self._total_chunks = msg.get("total_chunks", 0)
            self._chunk_size = msg.get("chunk_size", 256)
            self._progress = 0.0
            self._received_chunks_map.clear()
            self._expected_chunks_map.clear()
            self._chunks_status_map.clear()
            self._transfer_status = TransferStatus.INCOMPLETE
            self._bit_queue.clear()
            self._current_pvo = 0.0
            self._idle_pattern_index = 0

            # Active capture tracking
            self._capture_active = True
            self._capture_start_time = time.time()
            self._capture_pvo = []
            self._capture_vref = []
            self._capture_margin = []
            self._capture_time = []
            self._capture_bits = []
            self._capture_events = [{"time": 0.0, "event": "START", "details": f"Simulated reception started for TID {self._transfer_id}"}]

            from gui_dev_v3.logic.ber_bridge import parse_ber_test_name, generate_ber_test_payload
            import os
            ber_params = parse_ber_test_name(self._filename)
            
            ref_data = None
            if ber_params:
                size, seed = ber_params
                ref_data = generate_ber_test_payload(size, seed)
                self._log_append({
                    "time": now,
                    "event": "BERTEST Auto",
                    "details": f"Generated LCG reference ({size} B, seed {seed:08X})"
                })
            elif self._expected_file_data is not None:
                ref_data = self._expected_file_data
                self._log_append({
                    "time": now,
                    "event": "Reference Loaded",
                    "details": f"Using reference: {os.path.basename(self._expected_file_path or '')}"
                })

            for idx in range(self._total_chunks):
                start_offset = idx * self._chunk_size
                end_offset = start_offset + self._chunk_size
                expected = b""
                if ref_data is not None:
                    expected = ref_data[start_offset:end_offset]
                self._expected_chunks_map[idx] = expected
                self._chunks_status_map[idx] = ChunkStatus.PENDING

            self._log_append({"time": now, "event": "Transfer Started", "details": f"File: {self._filename} ({self._total_chunks} chunks)"})

        elif event == "chunk":
            idx = msg.get("index", 0)
            hex_data = msg.get("data", "")
            try:
                payload_bytes = bytes.fromhex(hex_data)
            except ValueError as e:
                self._chunks_status_map[idx] = ChunkStatus.MISSING
                self._log_append({
                    "time": now,
                    "event": "Error",
                    "details": f"Chunk {idx} invalid hex data: {e}"
                })
                return

            # Derive waveform bits from the actual transmission bitstream
            chunk_bits = _encode_4b5b(payload_bytes)
            self._bit_queue.extend(chunk_bits)
            
            # Cap queue to avoid lagging behind transfer
            if len(self._bit_queue) > 300:
                latest_bits = list(self._bit_queue)[-100:]
                self._bit_queue.clear()
                self._bit_queue.extend(latest_bits)

            # Apply channel impairments
            loss_rate = self._params.packet_loss_pct / 100.0
            self._compute_channel()
            ber = min(self._params.ber_estimate, 0.5)

            # Packet loss check
            if random.random() < loss_rate:
                self._chunks_status_map[idx] = ChunkStatus.MISSING
                self._log_append({"time": now, "event": "Chunk Lost", "details": f"Chunk {idx} dropped (simulated loss)"})
                if self._capture_active:
                    elapsed = time.time() - self._capture_start_time
                    self._capture_events.append({"time": round(elapsed, 3), "event": "CHUNK_LOST", "details": f"Chunk {idx} lost"})
            else:
                # Apply BER bit errors
                received = bytearray(payload_bytes)
                bit_errors = 0
                for byte_i in range(len(received)):
                    for bit in range(8):
                        if random.random() < ber:
                            received[byte_i] ^= (1 << bit)
                            bit_errors += 1

                self._received_chunks_map[idx] = bytes(received)
                
                expected_chunk = self._expected_chunks_map.get(idx, b"")
                if expected_chunk:
                    if bytes(received) == expected_chunk:
                        self._chunks_status_map[idx] = ChunkStatus.MATCH
                        if self._capture_active:
                            elapsed = time.time() - self._capture_start_time
                            self._capture_events.append({"time": round(elapsed, 3), "event": "CHUNK_OK", "details": f"Chunk {idx} received OK"})
                    else:
                        self._chunks_status_map[idx] = ChunkStatus.DIFFERENT
                        self._log_append({"time": now, "event": "Byte Mismatch", "details": f"Chunk {idx} differs from reference"})
                        if self._capture_active:
                            elapsed = time.time() - self._capture_start_time
                            self._capture_events.append({"time": round(elapsed, 3), "event": "CHUNK_ERR", "details": f"Chunk {idx} byte mismatch"})
                else:
                    self._chunks_status_map[idx] = ChunkStatus.RECEIVED
                    if self._capture_active:
                        elapsed = time.time() - self._capture_start_time
                        self._capture_events.append({"time": round(elapsed, 3), "event": "CHUNK_RCV", "details": f"Chunk {idx} received (no ref)"})

            processed = sum(1 for status in self._chunks_status_map.values() if status != ChunkStatus.PENDING)
            if self._total_chunks > 0:
                self._progress = (processed / self._total_chunks) * 100.0

        elif event == "stop_tx":
            self._active = False
            self._transfer_status = TransferStatus.COMPLETE
            self._save_received_file()
            self._log_append({"time": now, "event": "Transfer Complete", "details": f"Saved {self._filename}"})

            if self._capture_active:
                self._capture_active = False
                elapsed = time.time() - self._capture_start_time
                self._capture_events.append({"time": round(elapsed, 3), "event": "COMPLETE", "details": "Simulated reception complete"})

                total_bits = 0
                bit_errors = 0
                for c_idx in range(self._total_chunks):
                    expected = self._expected_chunks_map.get(c_idx, b"")
                    received = self._received_chunks_map.get(c_idx, b"")
                    if expected and received:
                        total_bits += len(expected) * 8
                        bit_errors += sum(1 for a, b in zip(expected, received) if a != b) * 8
                    elif expected:
                        total_bits += len(expected) * 8
                        bit_errors += len(expected) * 8

                ber_val = bit_errors / total_bits if total_bits > 0 else 0.0
                duration = elapsed if elapsed > 0 else 1.0
                size = self._total_chunks * self._chunk_size
                throughput = (size * 8) / (duration * 1000.0)

                import datetime
                from gui_dev_v3.data import save_session_capture
                from gui_dev_v3.models import SessionCapture

                cap = SessionCapture(
                    tid=self._transfer_id,
                    timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    filename=self._filename,
                    ber=round(ber_val, 6),
                    crc_status="PASS" if ber_val == 0 else "FAIL",
                    throughput_kbps=round(throughput, 3),
                    analog_time=self._capture_time,
                    pvo_samples=self._capture_pvo,
                    vref_samples=self._capture_vref,
                    margin_samples=self._capture_margin,
                    ook_bits=self._capture_bits,
                    protocol_events=self._capture_events,
                )
                save_session_capture(cap)
                print(f"Saved completed simulation capture for TID {self._transfer_id}")

    def _save_received_file(self) -> None:
        from gui_dev_v3.settings import SettingsManager
        from pathlib import Path
        mgr = SettingsManager("rx")
        default_dir = str(mgr.get("general/default_export_folder") or (Path.home() / "vlc_rx_captures"))

        save_path = Path(default_dir)
        try:
            save_path.mkdir(parents=True, exist_ok=True)
            file_path = save_path / self._filename

            assembled_bytes = bytearray()
            for idx in range(self._total_chunks):
                chunk_data = self._received_chunks_map.get(idx, b"\x00" * self._chunk_size)
                assembled_bytes.extend(chunk_data)

            file_path.write_bytes(assembled_bytes)
        except Exception as e:
            now = time.strftime("%H:%M:%S")
            self._log_append({"time": now, "event": "Save Error", "details": str(e)})

    # ── Channel parameters ──

    @property
    def params(self) -> VirtualChannelParams:
        return self._params

    def set_params(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._params, k):
                setattr(self._params, k, v)

    def update_distance(self, meters: float) -> None:
        self._params.distance_m = max(0.1, min(10.0, meters))

    def update_noise(self, mv: float) -> None:
        self._params.noise_floor_mv = max(0.0, min(500.0, mv))

    def update_lux(self, lx: int) -> None:
        self._params.lux = max(0, min(10000, lx))

    def update_led_wattage(self, w: float) -> None:
        self._params.led_wattage_w = max(0.1, min(100.0, w))

    def update_packet_loss(self, pct: float) -> None:
        self._params.packet_loss_pct = max(0.0, min(50.0, pct))

    # ── Virtual channel model ──

    def _compute_channel(self) -> None:
        """Compute derived channel parameters from the virtual model.

        Models realistic VLC channel with sensible voltage levels.
        Base reference: 2.5V PVo at 1m with 10W LED.
        """
        p = self._params

        # Signal voltage: scales with sqrt(LED power), decays with distance^1.5
        ref_power = 10.0
        ref_distance = 1.0
        ref_voltage = 2.5
        power_factor = math.sqrt(max(p.led_wattage_w, 0.1) / ref_power)
        distance_factor = (ref_distance / max(p.distance_m, 0.1)) ** 1.5
        pvo_v = ref_voltage * power_factor * distance_factor

        # Noise reduces effective signal
        noise_mv = p.noise_floor_mv + (p.lux * 0.01)
        noise_volts = noise_mv / 1000.0
        pvo_v = max(0.0, pvo_v - noise_volts * 0.3)

        # Clip to realistic ADC range
        pvo_v = min(3.3, pvo_v)

        self._computed_pvo = pvo_v

        # SNR: ratio of clean signal to total noise power
        clean_signal = ref_voltage * power_factor * distance_factor
        if noise_mv > 0.5:
            snr_linear = max(clean_signal / (noise_mv / 1000.0), 1.0)
            p.snr_db = 20 * math.log10(snr_linear)
        else:
            p.snr_db = 60.0

        # BER estimate (OOK, AWGN)
        snr_linear = 10 ** (p.snr_db / 20)
        p.ber_estimate = 0.5 * math.erfc(math.sqrt(snr_linear) / math.sqrt(2))
        p.ber_estimate = max(1e-12, min(0.5, p.ber_estimate))

    def _build_transfer(self) -> TransferRecord:
        """Build a TransferRecord from generated chunks."""
        p = self._params
        self._compute_channel()

        chunks: list[ChunkRecord] = []
        for idx in range(self._total_chunks):
            expected = self._expected_chunks_map.get(idx, b"")
            received = self._received_chunks_map.get(idx, b"")
            status = self._chunks_status_map.get(idx, ChunkStatus.PENDING)
            chunks.append(ChunkRecord(
                index=idx, status=status, expected=expected, received=received
            ))

        total_chunks = self._total_chunks
        received_count = sum(1 for status in self._chunks_status_map.values() if status in (ChunkStatus.MATCH, ChunkStatus.DIFFERENT))
        missing = total_chunks - received_count
        different = sum(1 for status in self._chunks_status_map.values() if status == ChunkStatus.DIFFERENT)

        if total_chunks == 0:
            return TransferRecord(
                tid=0,
                filename="",
                status=TransferStatus.PENDING,
                time_label=time.strftime("%H:%M"),
                size_bytes=0,
                total_chunks=0,
                received_chunks=0,
                quality=TransferQuality(
                    label="Excellent",
                    strict_ber=0.0,
                    bit_accuracy=100.0,
                    bit_errors=0,
                    total_bits=0,
                    compared_bytes=0,
                    missing_chunks=0,
                    missing_bytes=0,
                    first_issue="None",
                    crc_status="PASS",
                    recovery_rate=0.0,
                ),
                chunks=[],
            )

        # Estimate severity
        if missing == 0 and different == 0:
            label = "Excellent"
            crc_status = "PASS"
        elif missing > total_chunks * 0.3:
            label = "Poor"
            crc_status = "CRC Failed"
        elif different > total_chunks * 0.05:
            label = "Fair"
            crc_status = "FAIL"
        else:
            label = "Good"
            crc_status = "PASS"

        issues = []
        if different > 0:
            issues.append(f"{different} chunks with bit errors")
        if missing > 0:
            issues.append(f"{missing} missing chunks")
        first_issue = issues[0] if issues else "None"

        quality = TransferQuality(
            label=label,
            strict_ber=p.ber_estimate,
            bit_accuracy=100.0 * (1 - p.ber_estimate) if p.ber_estimate < 1 else 0,
            bit_errors=int(p.ber_estimate * received_count * self._chunk_size * 8),
            total_bits=received_count * self._chunk_size * 8,
            compared_bytes=received_count * self._chunk_size,
            missing_chunks=missing,
            missing_bytes=missing * self._chunk_size,
            first_issue=first_issue,
            crc_status=crc_status,
            recovery_rate=self._progress,
        )

        return TransferRecord(
            tid=self._transfer_id,
            filename=self._filename,
            status=self._transfer_status,
            time_label=time.strftime("%H:%M"),
            size_bytes=total_chunks * self._chunk_size,
            total_chunks=total_chunks,
            received_chunks=received_count,
            quality=quality,
            chunks=chunks,
        )

    def _build_signal(self) -> SignalState:
        """Build SignalState from virtual channel parameters."""
        p = self._params
        pvo_v = getattr(self, '_computed_pvo', 1.5) if self._tx_connected else 0.0

        if self._tx_connected:
            noise_mv = p.noise_floor_mv + (p.lux * 0.01)
            noise_jitter = (noise_mv / 500.0) * pvo_v * 0.15
            vref_ratio = 0.82 + (noise_jitter / max(pvo_v, 0.01)) * 0.08
            vref_ratio = max(0.60, min(0.95, vref_ratio))
            vref_v = pvo_v * vref_ratio
            margin_v = max(0.0, pvo_v - vref_v)

            if margin_v > 0.30:
                label = "Excellent"
            elif margin_v > 0.20:
                label = "Good"
            elif margin_v > 0.10:
                label = "Fair"
            elif margin_v > 0.04:
                label = "Poor"
            else:
                label = "No Signal"

            snr_factor = 1 - (1 / max(p.snr_db, 1))
            distance_penalty = 1 / max(p.distance_m, 0.5) ** 0.5
            data_rate = max(0.5, min(50.0, 25.0 * snr_factor * distance_penalty))
        else:
            vref_v = 0.0
            margin_v = 0.0
            label = "No Signal"
            data_rate = 0.0

        elapsed = time.time() - self._session_start
        hours, rem = divmod(int(elapsed), 3600)
        mins, secs = divmod(rem, 60)
        time_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

        return SignalState(
            label=label,
            pvo=round(pvo_v, 3),
            vref=round(vref_v, 3),
            margin=round(margin_v, 3),
            target_margin=0.365,
            adc_vref=3.300,
            lux=p.lux,
            data_rate=round(data_rate, 2),
            ber=round(p.ber_estimate, 6),
            strict_ber=round(p.ber_estimate, 6),
            crc_status="PASS" if margin_v > 0.10 else "FAIL",
            time_elapsed=time_str,
        )

    def _build_log(self) -> list[dict[str, str]]:
        """Build activity log from recent simulation events."""
        if self._log:
            return self._log[-10:]

        now = time.strftime("%H:%M:%S")
        log: list[dict[str, str]] = []
        if self._tx_connected:
            log.append({"time": now, "event": "Connected", "details": "Simulated Transmitter detected"})
        else:
            log.append({"time": now, "event": "Status", "details": "Simulation idle — waiting for transmitter"})

        return log

    def refresh(self) -> RXSimulationSnapshot:
        """Generate a new data snapshot from the virtual channel model."""
        if time.time() - self._last_tx_time > 3.0:
            self._tx_connected = False

        transfer = self._build_transfer()
        signal = self._build_signal()
        log = self._build_log()

        p = self._params
        session = SessionState(
            role="RX",
            connected_device="Simulated Transmitter" if self._tx_connected else "Virtual VLC Channel (simulation)",
            current_file=transfer.filename if transfer.filename else "—",
            progress_percent=int(self._progress),
            signal=signal,
            latest_transfer=transfer,
        )

        return RXSimulationSnapshot(
            session=session,
            transfer=transfer,
            activity_log=log,
            channel_params=p,
        )

    def _generate_sim_sample(self) -> None:
        """Periodic timer task (100 ms) generating simulated physical signals."""
        self._compute_channel()
        
        # Determine how many symbols/bits to generate in this 100 ms window
        # To scroll at ~20 symbols/second, we generate 2 bits per 100 ms
        num_bits = 2 if self._bit_queue or self._tx_connected else 1
        
        for _ in range(num_bits):
            if self._bit_queue:
                b = self._bit_queue.popleft()
            else:
                if self._tx_connected:
                    b = self._idle_pattern_index % 2
                    self._idle_pattern_index += 1
                else:
                    b = 0

            # Define high/low levels
            pvo_high = getattr(self, "_computed_pvo", 1.5)
            pvo_low = 0.05
            
            # Map deterministic bits into the analog target level
            target = pvo_high if b == 1 else pvo_low
            
            # RC rise/fall smooth response (exponential transition)
            alpha = 0.45
            
            self._current_pvo = self._current_pvo + alpha * (target - self._current_pvo)
            
            # Only add a very tiny high-frequency physical jitter based on the simulated noise floor
            # to keep it "mathematically realistic" but not wholly random.
            noise_floor_v = self._params.noise_floor_mv / 1000.0
            noise = (hash(str(self._sample_counter) + "noise") % 100) / 100.0 * 2.0 - 1.0
            self._current_pvo += noise * noise_floor_v * 0.05
            
            self._current_pvo = max(0.0, min(3.3, self._current_pvo))
            
            # Compute dynamic Vref and Margin
            pvo_v = pvo_high if self._tx_connected else 0.0
            if self._tx_connected:
                # Dynamic deterministic Vref that trails slightly
                noise_mv = self._params.noise_floor_mv + (self._params.lux * 0.01)
                noise_jitter = (noise_mv / 500.0) * pvo_v * 0.15
                vref_ratio = 0.82 + (noise_jitter / max(pvo_v, 0.01)) * 0.08
                vref_ratio = max(0.60, min(0.95, vref_ratio))
                vref_v = pvo_v * vref_ratio
            else:
                vref_v = 0.0
                
            comp_out = 1 if self._current_pvo > vref_v else 0
            margin_v = max(0.0, self._current_pvo - vref_v)
            
            # Round values for display consistency
            pvo_val = round(self._current_pvo, 3)
            vref_val = round(vref_v, 3)
            margin_val = round(margin_v, 3)
            
            # Store sample in buffer
            self._samples_buffer.append((pvo_val, vref_val, margin_val, comp_out))
            self._sample_counter += 1

            if self._capture_active:
                elapsed = time.time() - self._capture_start_time
                self._capture_time.append(round(elapsed, 3))
                self._capture_pvo.append(pvo_val)
                self._capture_vref.append(vref_val)
                self._capture_margin.append(margin_val)
                self._capture_bits.append(comp_out)

        if len(self._samples_buffer) > 1000:
            self._samples_buffer = self._samples_buffer[-1000:]

    def get_new_samples(self, last_idx: int) -> list[tuple[float, float, float, int]]:
        """Retrieve samples generated since last_idx."""
        if last_idx > self._sample_counter:
            last_idx = max(0, self._sample_counter - 100)
        
        new_count = self._sample_counter - last_idx
        if new_count <= 0:
            return []
        
        buffer_len = len(self._samples_buffer)
        start_pos = max(0, buffer_len - new_count)
        return self._samples_buffer[start_pos:]
