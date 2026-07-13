"""Serial controllers — copied from vlc_migration with RX-specific enhancements."""

from __future__ import annotations

import random
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


class TXSerialController(SerialSession):
    def __init__(self, on_log: LogCallback | None = None, on_status: StatusCallback | None = None) -> None:
        super().__init__(role="tx", on_log=on_log, on_status=on_status)

    def apply_4b5b_settings(
        self,
        freq: int = 15000,
        gap: int = 0,
        fgap: int = 1,
        active_low: bool = False,
        idle_on: bool = True,
        quiet: bool = True,
    ) -> None:
        from gui_dev_v3.settings import SettingsManager
        dma_mode = SettingsManager("tx").get("link/dma_mode", False)
        for command in (
            "MODE=4B5B",
            f"QUIET={1 if quiet else 0}",
            f"FREQ={freq}",
            f"GAP={gap}",
            f"FGAP={fgap}",
            f"ACTIVE_LOW={1 if active_low else 0}",
            f"IDLE_ON={1 if idle_on else 0}",
            f"DMA_MODE={1 if dma_mode else 0}",
            "CONFIG?",
        ):
            self.send_line(command)
        self.status("Settings applied", f"4B5B · {freq} Hz · FGAP {fgap} ms", state="ready")

    def bulb_on(self) -> None:
        self.send_line("BULB=ON")

    def bulb_off(self) -> None:
        self.send_line("BULB=OFF")

    def bulb_idle(self) -> None:
        self.send_line("BULB=IDLE")

    def send_file(self, path: Path, chunk_bytes: int = 256, rounds: int = 1) -> bool:
        if not self.is_connected or self.serial_obj is None:
            self.status("Not connected", "Connect TX before sending", state="error")
            return False
        if not path.exists() or not path.is_file():
            self.status("File missing", str(path), state="error")
            return False
        
        data = path.read_bytes()
        from gui_dev_v3.settings import SettingsManager
        dma_mode = SettingsManager("tx").get("link/dma_mode", False)
        
        if not dma_mode and len(data) > MAX_STREAM_FILE_BYTES:
            self.status("File too large", f"{len(data):,} B exceeds direct {MAX_STREAM_FILE_BYTES:,} B limit", state="error")
            return False
            
        name_bytes = path.name.encode("utf-8", errors="replace")[:MAX_NAME_BYTES]
        chunk_size = max(1, int(chunk_bytes))
        round_count = max(1, int(rounds))
        tid = random.randint(1, 65535)
        file_crc = crc16_ccitt(data)
        
        if dma_mode:
            # === DMA Sliding Window Stream ===
            begin = f"DMA_BEGIN:{tid}:1:{len(data)}:{chunk_size}:{file_crc:04X}:1:{name_bytes.hex().upper()}"
            self.status("Preparing DMA", path.name, percent=0, state="active", file_name=path.name, size=len(data), tid=tid)
            self.send_line("STREAM_CLEAR")
            start_index = len(self.last_lines)
            if not self.send_line(begin):
                return False
            if not self.wait_for_line_containing("TX_DMA_BEGIN_OK", 5.0, start_index):
                self.status("Send failed", "TX did not acknowledge DMA_BEGIN", state="error")
                return False
                
            total_chunks = (len(data) + chunk_size - 1) // chunk_size
            window_size = 2
            in_flight = 0
            chunk_idx = 0
            acked_idx = -1
            
            try:
                while chunk_idx < total_chunks or acked_idx < total_chunks - 1:
                    while in_flight < window_size and chunk_idx < total_chunks:
                        offset = chunk_idx * chunk_size
                        block = data[offset : offset + chunk_size]
                        if not self.send_line(f"DMA_DATA:{chunk_idx}:{block.hex().upper()}"):
                            return False
                        chunk_idx += 1
                        in_flight += 1
                    
                    next_ack = acked_idx + 1
                    if next_ack < total_chunks:
                        start_index = len(self.last_lines) - 200 # check recent lines
                        start_index = max(0, start_index)
                        if not self.wait_for_line_containing(f"TX_DMA_ACK:{next_ack}", 15.0, start_index):
                            self.status("Send failed", f"TX timeout waiting for DMA_ACK:{next_ack}", state="error")
                            return False
                        acked_idx = next_ack
                        in_flight -= 1
                        percent = min(95.0, (acked_idx / total_chunks) * 100.0)
                        self.status("Streaming DMA", path.name, percent=percent, state="active")
                
                start_index = len(self.last_lines)
                if not self.wait_for_line_containing("TX_DMA_DONE", 10.0, start_index):
                    self.status("Send failed", "TX did not finish DMA", state="error")
                    return False
            except Exception as exc:
                self.status("Send failed", str(exc), state="error")
                return False
        else:
            # === Legacy Stop-and-Wait Stream ===
            begin = f"STREAM_BEGIN:{tid}:1:{len(data)}:{chunk_size}:{file_crc:04X}:1:{name_bytes.hex().upper()}"
            self.status("Preparing", path.name, percent=0, state="active", file_name=path.name, size=len(data), tid=tid)
            self.send_line("STREAM_CLEAR")
            start_index = len(self.last_lines)
            if not self.send_line(begin):
                return False
            if not self.wait_for_line_containing("TX_STREAM_BEGIN_OK", 5.0, start_index):
                self.status("Send failed", "TX did not acknowledge STREAM_BEGIN", state="error")
                return False
            total = max(1, len(data))
            try:
                for offset in range(0, len(data), STREAM_SERIAL_BLOCK):
                    block = data[offset : offset + STREAM_SERIAL_BLOCK]
                    start_index = len(self.last_lines)
                    if not self.send_line(f"STREAM_DATA:{offset}:{block.hex().upper()}"):
                        return False
                    if not self.wait_for_line_containing("TX_STREAM_DATA_OK", 5.0, start_index):
                        self.status("Send failed", f"TX did not acknowledge data block at offset {offset}", state="error")
                        return False
                    percent = min(95.0, ((offset + len(block)) / total) * 100.0)
                    self.status("Preloading", path.name, percent=percent, state="active")
                for round_index in range(round_count):
                    start_index = len(self.last_lines)
                    if not self.send_line("STREAM_START"):
                        return False
                    self.status("Sending", f"{path.name} · optical round {round_index + 1}/{round_count}", percent=100, state="active", file_name=path.name, size=len(data), tid=tid)
                    timeout = max(12.0, min(180.0, (len(data) / 512.0) + 10.0))
                    if not self.wait_for_line_containing("TX_STREAM_DONE", timeout, start_index):
                        self.status("Send failed", f"TX did not finish optical round {round_index + 1}", state="error")
                        return False
            except Exception as exc:
                self.status("Send failed", str(exc), state="error")
                return False
                
        self.status("Send complete", path.name, percent=100, state="ready", file_name=path.name, size=len(data), tid=tid)
        return True


class RXSerialController(SerialSession):
    def __init__(self, on_log: LogCallback | None = None, on_status: StatusCallback | None = None) -> None:
        super().__init__(role="rx", on_log=on_log, on_status=on_status)

    def request_config(self) -> None:
        self.send_line("LQ?")
        self.send_line("VREF_GET")

    def lock_vref(self) -> None:
        self.send_line("VREF_CAL")

    def set_vref_mv(self, value: int) -> None:
        self.send_line(f"VREF_SET={int(value)}")

    def start_receive(self) -> None:
        self.status("Receiving", "Receiver is live; firmware listens continuously after serial connect.", state="active")

    def stop_receive(self) -> None:
        self.status("Connected", "Receiver remains connected. Disconnect serial to stop listening.", state="ready")

    def request_latest_hex(self) -> None:
        self.status("Waiting for file dump", "RX_FILE_HEX is emitted automatically by firmware after a complete validated receive.", state="ready")

    def dump_chunk(self, index: int) -> None:
        self.send_line(f"RX_DUMP_CHUNK={max(0, int(index))}")


from .session import LogCallback, StatusCallback  # noqa: E402, F401
