"""Serial controllers — TX (DMA and non-DMA) and RX with full firmware protocol support.

Key fixes vs original:
 - TXSerialController.apply_4b5b_settings(): gates DMA_MODE / PREAMBLE / CARRIER
   commands only to DMA-capable firmware to avoid TX_ERROR on tx_non_dma.ino.
 - TXSerialController.send_file(): DMA ACK tracking uses a per-chunk start_index
   recorded BEFORE each send (fixes race-window miss on large files).
 - TXSerialController.handle_line(): parses TX_STREAM_DONE / TX_DMA_DONE and
   updates progress state via on_status.
 - RXSerialController.handle_line(): parses LQ telemetry and RX_FILE_HEX lines,
   saving received files to disk and pushing signal metrics to the status callback.
 - Removed dead dump_chunk() method (RX_DUMP_CHUNK command does not exist in fw).
"""

from __future__ import annotations

import re
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .session import (
    MAX_STREAM_FILE_BYTES,
    MAX_NAME_BYTES,
    STREAM_SERIAL_BLOCK,
    SerialSession,
    crc16_ccitt,
)


# ── Firmware capability flags ────────────────────────────────────────────────
# tx_dma.ino supports: PREAMBLE=, CARRIER=, DMA_MODE=, DMA_BEGIN, DMA_DATA
# tx_non_dma.ino does NOT support these commands → would cause TX_ERROR
_TX_DMA_BANNER    = "DMA"           # substring present in tx_dma startup banner
_TX_NON_DMA_CMDS  = frozenset({"DMA_MODE", "PREAMBLE", "CARRIER"})


class TXSerialController(SerialSession):
    """Serial controller for TX firmware (tx_dma.ino or tx_non_dma.ino).

    Automatically detects DMA capability from the firmware's startup banner.
    """

    def __init__(
        self,
        on_log: LogCallback | None = None,
        on_status: StatusCallback | None = None,
    ) -> None:
        super().__init__(role="tx", on_log=on_log, on_status=on_status)
        # Detected at connection time; None = not yet known
        self._dma_capable: bool | None = None

    # ── Firmware capability detection ────────────────────────────────────────

    def handle_line(self, line: str) -> None:
        """Parse firmware lines for capability detection and progress updates."""
        self.log(line)

        # Detect DMA capability from the startup banner
        # tx_dma.ino:     "=== LiFi 4B5B TX Stream Ready ===" + has DMA_ handlers
        # tx_non_dma.ino: same banner but "Commands: ... STREAM_*" (no DMA_*)
        if self._dma_capable is None:
            if "DMA" in line.upper():
                self._dma_capable = True
            elif "STREAM_*" in line and "DMA" not in line.upper():
                self._dma_capable = False
            elif line.startswith("TX 4B5B CONFIG:"):
                # CONFIG? response is present on both; absence of DMA lines
                # after ~1 s defaults to non-DMA
                self._dma_capable = False

        # Only forward calibration events, leave transmission state to the synchronous loops
        if line.startswith("TX_CAL_INTENSITY:"):
            self.status("Calibration", line, state="ready")

    @property
    def dma_capable(self) -> bool:
        """True if connected firmware supports DMA streaming (tx_dma.ino)."""
        if self._dma_capable is not None:
            return self._dma_capable
        # Fall back to user setting while capability is still unknown
        from gui_dev_v3.settings import SettingsManager
        return bool(SettingsManager("tx").get("link/dma_mode", False))

    # ── Settings application ─────────────────────────────────────────────────

    def apply_4b5b_settings(
        self,
        freq: int = 15000,
        gap: int = 0,
        fgap: int = 1,
        active_low: bool = True,
        idle_on: bool = True,
        quiet: bool = True,
    ) -> None:
        """Send link-layer configuration to firmware.

        DMA_MODE, PREAMBLE, and CARRIER are only sent when the firmware is
        confirmed DMA-capable (tx_dma.ino); they would cause TX_ERROR on
        tx_non_dma.ino.
        """
        from gui_dev_v3.settings import SettingsManager
        mgr = SettingsManager("tx")
        dma_mode = mgr.get("link/dma_mode", False)

        commands = [
            "MODE=4B5B",
            f"QUIET={1 if quiet else 0}",
            f"FREQ={freq}",
            f"GAP={gap}",
            f"FGAP={fgap}",
            f"ACTIVE_LOW={1 if active_low else 0}",
            f"IDLE_ON={1 if idle_on else 0}",
        ]

        # Gate DMA-only commands to DMA-capable firmware only
        if self.dma_capable:
            commands.append(f"DMA_MODE={1 if dma_mode else 0}")
            preamble_bits = int(mgr.get("link/preamble_bits", 64))
            carrier_hz    = int(mgr.get("link/carrier_hz", 30000))
            commands.append(f"PREAMBLE={preamble_bits}")
            commands.append(f"CARRIER={carrier_hz}")

        commands.append("CONFIG?")
        for cmd in commands:
            self.send_line(cmd)

        mode_label = "DMA" if (self.dma_capable and dma_mode) else "Stream"
        self.status(
            "Settings applied",
            f"4B5B · {freq} Hz · {mode_label} · FGAP {fgap} ms",
            state="ready",
        )

    # ── LED control ─────────────────────────────────────────────────────────

    def bulb_on(self)   -> None: self.send_line("BULB=ON")
    def bulb_off(self)  -> None: self.send_line("BULB=OFF")
    def bulb_idle(self) -> None: self.send_line("BULB=IDLE")

    # ── File transmission ────────────────────────────────────────────────────

    def send_file(self, path: Path, chunk_bytes: int = 256, rounds: int = 1) -> bool:
        """Transmit a file via STREAM (non-DMA) or DMA sliding-window protocol.

        DMA mode is selected when:
          1. The user setting `link/dma_mode` is True, AND
          2. The firmware is DMA-capable (tx_dma.ino).

        Non-DMA (tx_non_dma.ino) always uses the stop-and-wait STREAM protocol.
        """
        if not self.is_connected or self.serial_obj is None:
            self.status("Not connected", "Connect TX before sending", state="error")
            return False
        if not path.exists() or not path.is_file():
            self.status("File missing", str(path), state="error")
            return False

        data = path.read_bytes()
        from gui_dev_v3.settings import SettingsManager
        mgr = SettingsManager("tx")
        user_wants_dma = bool(mgr.get("link/dma_mode", False))
        use_dma = user_wants_dma and self.dma_capable

        if not use_dma and len(data) > MAX_STREAM_FILE_BYTES:
            import math
            group_id = random.randint(1, 65535)
            full_crc = crc16_ccitt(data)
            part_count = math.ceil(len(data) / MAX_STREAM_FILE_BYTES)
            
            self.status(
                "Batching large file",
                f"{len(data):,} B split into {part_count} parts",
                state="active",
            )
            
            for part_index, offset in enumerate(range(0, len(data), MAX_STREAM_FILE_BYTES), start=1):
                part = data[offset:offset + MAX_STREAM_FILE_BYTES]
                part_tid = random.randint(1, 65535)
                part_crc = crc16_ccitt(part)
                # Format: VLCB1~group_id~part_index~part_count~full_crc~original_name
                prefix = f"VLCB1~{group_id:04X}~{part_index:03d}~{part_count:03d}~{full_crc:04X}~"
                part_name = prefix + path.name
                part_name_bytes = part_name.encode("utf-8", errors="replace")[:MAX_NAME_BYTES]
                
                self.status(
                    "Sending batch part",
                    f"Part {part_index}/{part_count}...",
                    state="active",
                )
                success = self._send_stream(path, part, part_name_bytes, chunk_size, part_tid, part_crc, round_count)
                if not success:
                    return False
                
                # Delay for RX to process batch part
                if part_index < part_count:
                    import time as _time
                    delay_s = max(6.0, min(14.0, 3.0 + (len(part) / 20_000.0)))
                    self.status("Batch delay", f"Waiting {delay_s:.1f}s for RX buffer...", state="active")
                    _time.sleep(delay_s)
                    
            self.status("Batch complete", f"All {part_count} parts sent", state="ready")
            return True

        name_bytes = path.name.encode("utf-8", errors="replace")[:MAX_NAME_BYTES]
        chunk_size  = max(16, min(int(chunk_bytes), 1024))
        round_count = max(1, int(rounds))
        tid         = random.randint(1, 65535)
        file_crc    = crc16_ccitt(data)

        if use_dma:
            return self._send_dma(path, data, name_bytes, chunk_size, tid, file_crc)
        else:
            return self._send_stream(path, data, name_bytes, chunk_size, tid, file_crc, round_count)

    # ── DMA protocol (tx_dma.ino) ────────────────────────────────────────────

    def _send_dma(
        self,
        path: Path,
        data: bytes,
        name_bytes: bytes,
        chunk_size: int,
        tid: int,
        file_crc: int,
    ) -> bool:
        """DMA sliding-window transmission (tx_dma.ino only)."""
        begin = (
            f"DMA_BEGIN:{tid}:1:{len(data)}:{chunk_size}"
            f":{file_crc:04X}:1:{name_bytes.hex().upper()}"
        )
        total_chunks = max(1, (len(data) + chunk_size - 1) // chunk_size)
        total_start_time = time.monotonic()
        self.status(
            "Preparing DMA", path.name,
            percent=0, state="active",
            file_name=path.name, size=len(data), tid=tid,
            chunk=0, total_chunks=total_chunks,
        )
        self.send_line("STREAM_CLEAR")

        # Record start_index BEFORE send so we don't miss fast ACKs
        start_index = self.line_counter
        if not self.send_line(begin):
            return False
        if not self.wait_for_line_containing("TX_DMA_BEGIN_OK", 5.0, start_index):
            self.status("Send failed", "TX did not acknowledge DMA_BEGIN", state="error")
            return False

        window_size  = 2
        in_flight    = 0
        chunk_idx    = 0
        acked_idx    = -1
        chunk_start_indices: dict[int, int] = {}

        try:
            while chunk_idx < total_chunks or acked_idx < total_chunks - 1:
                # Fill the sliding window
                while in_flight < window_size and chunk_idx < total_chunks:
                    offset = chunk_idx * chunk_size
                    block  = data[offset: offset + chunk_size]
                    # Record start_index per-chunk BEFORE send
                    chunk_start_indices[chunk_idx] = self.line_counter
                    if not self.send_line(f"DMA_DATA:{chunk_idx}:{block.hex().upper()}"):
                        return False
                    chunk_idx += 1
                    in_flight += 1

                # Wait for the next expected ACK
                next_ack = acked_idx + 1
                if next_ack < total_chunks:
                    # Look up the exact log index recorded right before sending this chunk
                    si = chunk_start_indices.get(next_ack, 0)
                    if not self.wait_for_line_containing(
                        f"TX_DMA_ACK:{next_ack}", 15.0, si
                    ):
                        self.status(
                            "Send failed",
                            f"TX timeout waiting for DMA_ACK:{next_ack}",
                            state="error",
                        )
                        return False
                    acked_idx  = next_ack
                    in_flight -= 1
                    percent    = min(95.0, (acked_idx / total_chunks) * 100.0)
                    
                    elapsed_total = time.monotonic() - total_start_time
                    cur_rate = f"{((len(data) * (percent / 100.0) * 8) / max(0.1, elapsed_total)):.0f} bps"
                    em, es = divmod(int(elapsed_total), 60)
                    ms = int((elapsed_total - int(elapsed_total)) * 1000)
                    elapsed_str = f"{em:02d}:{es:02d}:{ms:03d}"
                    
                    self.status("Streaming DMA", path.name, percent=percent, state="active",
                                chunk=acked_idx, total_chunks=total_chunks,
                                elapsed_time=elapsed_str, data_rate=cur_rate)

            si = self.line_counter
            if not self.wait_for_line_containing("TX_DMA_DONE", 10.0, si):
                self.status("Send failed", "TX did not finish DMA", state="error")
                return False

        except Exception as exc:
            self.status("Send failed", str(exc), state="error")
            return False

        elapsed_total = time.monotonic() - total_start_time
        data_rate = f"{((len(data) * 8) / max(0.1, elapsed_total)):.0f} bps"
        em, es = divmod(int(elapsed_total), 60)
        ms = int((elapsed_total - int(elapsed_total)) * 1000)
        elapsed_str = f"{em:02d}:{es:02d}:{ms:03d}"

        self.status(
            "Send complete", path.name,
            percent=100, state="ready",
            file_name=path.name, size=len(data), tid=tid,
            chunk=total_chunks, total_chunks=total_chunks,
            elapsed_time=elapsed_str, data_rate=data_rate,
        )
        self._latest_status["data_rate"] = data_rate
        return True

    # ── STREAM protocol (tx_non_dma.ino and tx_dma.ino) ─────────────────────

    def _send_stream(
        self,
        path: Path,
        data: bytes,
        name_bytes: bytes,
        chunk_size: int,
        tid: int,
        file_crc: int,
        round_count: int,
    ) -> bool:
        """Stop-and-wait STREAM transmission (works on both tx_dma and tx_non_dma)."""
        total_start_time = time.monotonic()
        begin = (
            f"STREAM_BEGIN:{tid}:1:{len(data)}:{chunk_size}"
            f":{file_crc:04X}:1:{name_bytes.hex().upper()}"
        )
        tot_c = max(1, (len(data) + chunk_size - 1) // chunk_size)
        self.status(
            "Preparing", path.name,
            percent=0, state="active",
            file_name=path.name, size=len(data), tid=tid,
            chunk=0, total_chunks=tot_c,
        )
        self.send_line("STREAM_CLEAR")

        si = self.line_counter
        if not self.send_line(begin):
            return False
        if not self.wait_for_line_containing("TX_STREAM_BEGIN_OK", 5.0, si):
            self.status("Send failed", "TX did not acknowledge STREAM_BEGIN", state="error")
            return False

        total = max(1, len(data))
        try:
            for offset in range(0, len(data), STREAM_SERIAL_BLOCK):
                block = data[offset: offset + STREAM_SERIAL_BLOCK]
                si    = self.line_counter
                if not self.send_line(f"STREAM_DATA:{offset}:{block.hex().upper()}"):
                    return False
                if not self.wait_for_line_containing("TX_STREAM_DATA_OK", 5.0, si):
                    self.status(
                        "Send failed",
                        f"TX did not acknowledge data block at offset {offset}",
                        state="error",
                    )
                    return False
                percent = min(95.0, ((offset + len(block)) / total) * 100.0)
                current_c = offset // chunk_size
                tot_c = max(1, (len(data) + chunk_size - 1) // chunk_size)
                self.status("Preloading", path.name, percent=percent, state="active", chunk=current_c, total_chunks=tot_c)

            for round_index in range(round_count):
                if not self.send_line("STREAM_START"):
                    return False
                # Capture counter AFTER sending STREAM_START so we only see new lines
                si = self.line_counter
                self.status(
                    "Sending",
                    f"{path.name} · optical round {round_index + 1}/{round_count}",
                    percent=0, state="active",
                    file_name=path.name, size=len(data), tid=tid,
                    chunk=tot_c, total_chunks=tot_c,
                )
                
                # Estimate optical transmission time: 4B5B = 10 bits per data byte
                from gui_dev_v3.settings import SettingsManager
                mgr = SettingsManager("tx")
                symbol_hz = int(mgr.get("link/symbol_hz", 15000))
                est_seconds = (len(data) * 10) / max(1, symbol_hz)
                
                start_t = time.monotonic()
                timeout = max(12.0, min(180.0, est_seconds * 3 + 10.0))
                done = False
                
                while time.monotonic() - start_t < timeout:
                    if self.wait_for_line_containing("TX_STREAM_DONE", timeout=0.1, start_counter=si):
                        done = True
                        break
                        
                    elapsed = time.monotonic() - start_t
                    pct = min(99.0, (elapsed / max(0.1, est_seconds)) * 100.0)
                    elapsed_total = time.monotonic() - total_start_time
                    # data_rate: bytes actually transmitted * 8 bits / elapsed
                    cur_rate = f"{int((len(data) * 8) / max(0.1, elapsed_total))} bps"
                    
                    em, es = divmod(int(elapsed_total), 60)
                    ms = int((elapsed_total - int(elapsed_total)) * 1000)
                    elapsed_str = f"{em:02d}:{es:02d}:{ms:03d}"
                    
                    m_est, s_est = divmod(int(est_seconds), 60)
                    h_est, m_est = divmod(m_est, 60)
                    est_str = f"{h_est:02d}:{m_est:02d}:{s_est:02d}"
                    
                    self.status(
                        "Sending",
                        f"{path.name} · optical round {round_index + 1}/{round_count}",
                        percent=pct, state="active",
                        file_name=path.name, size=len(data), tid=tid,
                        elapsed_time=elapsed_str,
                        estimated_time=est_str,
                        data_rate=cur_rate,
                        chunk=tot_c, total_chunks=tot_c,
                    )
                    
                if not done:
                    self.status(
                        "Send failed",
                        f"TX did not finish optical round {round_index + 1}",
                        state="error",
                    )
                    return False

        except Exception as exc:
            self.status("Send failed", str(exc), state="error")
            return False

        elapsed_total = time.monotonic() - total_start_time
        data_rate = f"{((len(data) * 8) / elapsed_total):.0f} bps" if elapsed_total > 0 else "0 bps"
        
        m, s = divmod(int(elapsed_total), 60)
        ms = int((elapsed_total - int(elapsed_total)) * 1000)
        elapsed_str = f"{m:02d}:{s:02d}:{ms:03d}"

        self.status(
            "Send complete", path.name,
            percent=100, state="ready",
            file_name=path.name, size=len(data), tid=tid,
            elapsed_time=elapsed_str,
            data_rate=data_rate,
            chunk=tot_c, total_chunks=tot_c,
        )
        return True


# ── RX Controller ─────────────────────────────────────────────────────────────

class RXSerialController(SerialSession):
    """Serial controller for RX firmware (rx.ino) at 460800 baud.

    handle_line() now parses:
      - LQ,...  → signal quality metrics pushed via on_status
      - RX_FILE_HEX:...  → file data decoded and saved to disk
      - RX_RAM_STORE: / RX_TRANSFER_NOTICE:  → progress updates
      - VREF_*  → VREF state forwarded to status
    """

    def __init__(
        self,
        on_log: LogCallback | None = None,
        on_status: StatusCallback | None = None,
        save_dir: str | Path | None = None,
    ) -> None:
        super().__init__(role="rx", on_log=on_log, on_status=on_status)
        # Directory where received files are saved (defaults to ~/vlc_rx_captures)
        self._save_dir: Path = (
            Path(save_dir) if save_dir else Path.home() / "vlc_rx_captures"
        )

    # ── Firmware line parser ─────────────────────────────────────────────────

    def handle_line(self, line: str) -> None:
        """Dispatch firmware lines to the appropriate parser."""
        self.log(line)

        if line.startswith("LQ,"):
            self._parse_lq(line)
        elif line.startswith("RX_FILE_HEX:"):
            self._parse_rx_file_hex(line)
        elif line.startswith("RX_RAM_STORE:"):
            self._parse_ram_store(line)
        elif line.startswith("RX_TRANSFER_NOTICE:"):
            self._parse_transfer_notice(line)
        elif line.startswith("RX_FILE_CRC_FAIL:"):
            self.status("CRC Failure", line, state="error")
        elif line.startswith("RX_RAM_TIMEOUT:"):
            self.status("Transfer timeout", line, state="error")
        elif line.startswith("VREF_CAL_OK:") or line.startswith("VREF_SET_OK:"):
            self.status("Vref updated", line, state="ready")
        elif line.startswith("VREF_STATE:"):
            self._parse_vref_state(line)

    # ── LQ telemetry parser ──────────────────────────────────────────────────

    _LQ_KEYS = {
        "SIGNAL": "pvo", "SIGNAL_ACTUAL": "pvo_actual",
        "VREF": "vref", "VREF_ACTUAL": "vref_actual",
        "MARGIN": "margin", "MARGIN_ACTUAL": "margin_actual",
        "SWING": "swing", "SWING_ACTUAL": "swing_actual",
        "PASS_RATE": "pass_rate",
        "STATUS": "status",
        "VREF_MODE": "vref_mode",
        "VREF_TARGET_MV": "vref_target_mv",
        "VREF_PWM": "vref_pwm",
    }

    def _parse_lq(self, line: str) -> None:
        """Parse  LQ,MODE=4B5B,SIGNAL=...,VREF=...,MARGIN=...,STATUS=...  lines."""
        pairs = re.findall(r"([A-Z0-9_]+)=([^,\r\n]+)", line)
        data: dict[str, Any] = {"_type": "lq"}
        for key, val in pairs:
            dest = self._LQ_KEYS.get(key)
            if dest is None:
                continue
            try:
                data[dest] = float(re.search(r"[-+]?\d+(?:\.\d+)?", val).group(0))  # type: ignore[union-attr]
            except (AttributeError, ValueError):
                data[dest] = val.strip()

        if data:
            # Map to the status dict format the GUI understands
            pvo    = float(data.get("pvo", 0.0))
            vref   = float(data.get("vref", 0.0))
            margin = float(data.get("margin", 0.0))
            swing  = float(data.get("swing", 0.0))
            pr     = float(data.get("pass_rate", 100.0))
            status_str = str(data.get("status", ""))

            self.status(
                "Receiving" if pr > 0 else "Idle",
                f"PVo={pvo:.3f}V  Vref={vref:.3f}V  Margin={margin:.3f}V",
                state="active",
                # Signal metrics — consumed by RXPhysicalBackend / app_state
                pvo_v=round(pvo, 4),
                vref_v=round(vref, 4),
                margin_v=round(margin, 4),
                swing_v=round(swing, 4),
                pass_rate=round(pr, 1),
                quality_label=self._margin_label(margin),
                lq_status=status_str,
            )

    @staticmethod
    def _margin_label(margin: float) -> str:
        if margin > 0.45:  return "Excellent"
        if margin > 0.36:  return "Good"
        if margin > 0.28:  return "Fair"
        return "Low"

    # ── RX_FILE_HEX parser / file saver ─────────────────────────────────────

    def _parse_rx_file_hex(self, line: str) -> None:
        """Decode and save a complete received file.

        Firmware format (single line):
          RX_FILE_HEX:<tid>:<frame_type>:<total_size>:<total_chunks>
                      :<file_crc_hex>:<name_hex>:<data_hex>
        """
        try:
            # Split into exactly 8 fields (data_hex may contain no colons)
            parts = line.split(":", 7)
            if len(parts) < 8:
                self.log(f"[RX] Malformed RX_FILE_HEX (too few fields): {line[:80]}")
                return

            _, tid_s, ftype_s, size_s, chunks_s, crc_hex, name_hex, data_hex = parts
            tid          = int(tid_s)
            total_size   = int(size_s)
            total_chunks = int(chunks_s)
            expected_crc = int(crc_hex, 16)

            name_str = bytes.fromhex(name_hex).decode("utf-8", errors="replace")
            file_data = bytes.fromhex(data_hex)

            if len(file_data) != total_size:
                self.log(
                    f"[RX] Size mismatch: got {len(file_data)} B, expected {total_size} B"
                )

            # Verify CRC
            from .session import crc16_ccitt
            actual_crc = crc16_ccitt(file_data)
            if actual_crc != expected_crc:
                self.status(
                    "CRC mismatch",
                    f"TID {tid}: got {actual_crc:04X} expected {expected_crc:04X}",
                    state="error",
                    tid=tid,
                )
                return

            # Save file to disk
            save_path = self._save_to_disk(name_str, file_data, tid)

            self.status(
                "File received",
                f"Saved → {save_path.name}",
                state="ready",
                file_name=name_str,
                size=len(file_data),
                tid=tid,
                total_chunks=total_chunks,
                save_path=str(save_path),
                crc_ok=True,
            )
            self.log(f"[RX] File saved: {save_path}  ({len(file_data):,} bytes)")

        except Exception as exc:
            self.log(f"[RX] RX_FILE_HEX parse error: {exc} | line[:120]={line[:120]}")

    def _save_to_disk(self, name: str, data: bytes, tid: int) -> Path:
        """Write received bytes to save_dir, avoiding filename collisions."""
        self._save_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in (".", "_", "-") else "_" for c in name)
        if not safe_name:
            safe_name = f"rx_{tid}.bin"
        out = self._save_dir / safe_name
        # Avoid overwriting: append _2, _3, … if needed
        if out.exists():
            stem = out.stem
            suffix = out.suffix
            counter = 2
            while out.exists():
                out = self._save_dir / f"{stem}_{counter}{suffix}"
                counter += 1
        out.write_bytes(data)
        return out

    # ── Progress / notice parsers ────────────────────────────────────────────

    def _parse_ram_store(self, line: str) -> None:
        """RX_RAM_STORE:<tid>:<chunk_idx>:<received>:<total>"""
        try:
            parts = line.split(":")
            if len(parts) >= 5:
                tid      = int(parts[1])
                received = int(parts[3])
                total    = int(parts[4])
                percent  = min(99.0, (received / max(total, 1)) * 100.0)
                self.status(
                    "Receiving",
                    f"TID {tid}: chunk {received}/{total}",
                    percent=percent,
                    state="active",
                    tid=tid,
                    received_chunks=received,
                    total_chunks=total,
                )
        except (ValueError, IndexError):
            pass

    def _parse_transfer_notice(self, line: str) -> None:
        """RX_TRANSFER_NOTICE:<tid>:<total_size>:<total_chunks>:<crc_hex>:<name_hex>"""
        try:
            parts = line.split(":")
            if len(parts) >= 6:
                tid          = int(parts[1])
                total_size   = int(parts[2])
                total_chunks = int(parts[3])
                name_hex     = parts[5] if len(parts) > 5 else ""
                name_str     = bytes.fromhex(name_hex).decode("utf-8", errors="replace") if name_hex else "?"
                self.status(
                    "Transfer started",
                    f"TID {tid}: {name_str} ({total_size:,} B, {total_chunks} chunks)",
                    state="active",
                    tid=tid,
                    total_size=total_size,
                    total_chunks=total_chunks,
                    file_name=name_str,
                )
        except (ValueError, IndexError):
            pass

    def _parse_vref_state(self, line: str) -> None:
        """Forward key VREF fields to status."""
        pairs = re.findall(r"([A-Z0-9_]+)=([^:,\r\n]+)", line)
        data: dict[str, Any] = {}
        for k, v in pairs:
            try:
                data[k.lower()] = float(v)
            except ValueError:
                data[k.lower()] = v.strip()
        if data:
            self.status("Vref state", line, state="ready", **data)

    # ── High-level commands ──────────────────────────────────────────────────

    def request_config(self) -> None:
        """Ask firmware to report current LQ and Vref state."""
        self.send_line("LQ?")
        self.send_line("VREF_GET")

    def lock_vref(self) -> None:
        """Trigger firmware auto-calibration (VREF_CAL)."""
        self.send_line("VREF_CAL")

    def lock_vref_with_swing(self) -> None:
        """Trigger firmware auto-calibration requiring a live signal (VREF_CAL_SWING)."""
        self.send_line("VREF_CAL_SWING")

    def set_vref_mv(self, value: int) -> None:
        self.send_line(f"VREF_SET={int(value)}")

    def set_vref_margin_mv(self, mv: int) -> None:
        self.send_line(f"VREF_MARGIN={int(mv)}")

    def set_vref_settle_ms(self, ms: int) -> None:
        self.send_line(f"VREF_SETTLE_MS={int(ms)}")

    def set_vref_pwm_full_scale_mv(self, mv: int) -> None:
        self.send_line(f"VREF_PWM_FS={int(mv)}")

    def sweep_vref(self, start_mv: int, end_mv: int, step_mv: int = 50) -> None:
        """Trigger a Vref sweep (firmware reports VREF_SWEEP_POINT lines)."""
        self.send_line(f"VREF_SWEEP={start_mv},{end_mv},{step_mv}")

    def start_receive(self) -> None:
        self.status(
            "Receiving",
            "Receiver is live; firmware listens continuously after serial connect.",
            state="active",
        )

    def stop_receive(self) -> None:
        self.status(
            "Connected",
            "Receiver remains connected. Disconnect serial to stop listening.",
            state="ready",
        )

    def clear_buffer(self) -> None:
        """Send CLEAR command to reset firmware RAM buffer and duplicate history."""
        self.send_line("CLEAR")

    def set_save_dir(self, path: str | Path) -> None:
        """Change the directory where received files are written."""
        self._save_dir = Path(path)


# ── Type aliases (re-exported for callers that imported them here) ─────────────
from .session import LogCallback, StatusCallback  # noqa: E402, F401
