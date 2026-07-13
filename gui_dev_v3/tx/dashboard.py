"""TX Dashboard — Professional laboratory control console.

Layout:
┌─────────────────────────────────────────────────────────────┐
│ DEVICE STATUS (Full Width)                                  │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────┬─────────────────────────────┐
│ TRANSMISSION PIPELINE       │ CURRENT SESSION             │
├─────────────────────────────┼─────────────────────────────┤
│ FILE DETAILS                │ ENCODED BIT STREAM          │
└─────────────────────────────┴─────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ TRANSMISSION LOGS (Full Width)                              │
└─────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import os
import time
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QFrame,
    QSizePolicy,
)

from gui_dev_v3.theme import COLORS
from gui_dev_v3.tx_app_state import TXAppState
from gui_dev_v3.widgets import Card, muted_label, primary_button


# ── Headers & Layout Helpers ──────────────────────────────────────────

class _SectionHeader(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text.upper())
        self.setObjectName("SectionTitle")


class _DetailRow(QWidget):
    def __init__(self, label: str, value: str, val_color: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self.lbl = QLabel(label)
        self.lbl.setObjectName("Muted")

        self.val = QLabel(value)
        self.val.setObjectName("Value")
        if val_color:
            self.val.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {val_color}; background: transparent;")

        layout.addWidget(self.lbl)
        layout.addStretch(1)
        layout.addWidget(self.val)

    def setValue(self, text: str, color: str | None = None) -> None:
        self.val.setText(text)
        if color:
            self.val.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {color}; background: transparent;")
        else:
            self.val.setStyleSheet("")
            self.val.setObjectName("Value")
            self.val.style().unpolish(self.val)
            self.val.style().polish(self.val)


# ── Section 1: DEVICE STATUS ─────────────────────────────────────────

class _StatusColumn(QWidget):
    def __init__(self, title: str, value: str, val_color: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("Muted")
        self.title_lbl.setStyleSheet("font-size: 9px; font-weight: 700; text-transform: uppercase;")

        self.val_lbl = QLabel(value)
        self.val_lbl.setObjectName("Value")
        if val_color:
            self.val_lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {val_color}; background: transparent;")

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.val_lbl)
        
    def setValue(self, text: str, color: str | None = None) -> None:
        self.val_lbl.setText(text)
        if color:
            self.val_lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {color}; background: transparent;")
        else:
            self.val_lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {COLORS['value']}; background: transparent;")


class DeviceStatusWidget(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        
        title = QLabel("DEVICE STATUS")
        title.setStyleSheet(f"color: {COLORS['header']}; font-size: 10px; font-weight: 700; letter-spacing: 0.5px; background: transparent;")
        layout.addWidget(title)
        
        cols = QHBoxLayout()
        cols.setSpacing(16)
        
        self.box_connection = _StatusColumn("ESP32 CONNECTION", "Disconnected", COLORS["red"])
        self.box_firmware = _StatusColumn("FIRMWARE VERSION", "—")
        self.box_protocol = _StatusColumn("PROTOCOL VERSION", "—")
        self.box_usb = _StatusColumn("USB STATUS", "Inactive")
        
        cols.addWidget(self.box_connection)
        cols.addWidget(self.box_firmware)
        cols.addWidget(self.box_protocol)
        cols.addWidget(self.box_usb)
        layout.addLayout(cols)
        
    def refresh(self, state: TXAppState) -> None:
        connected = state.serial_connected
        mode = state.mode
        
        if mode == "simulated":
            if connected:
                self.box_connection.setValue("Connected (Simulated)", COLORS["green"])
                self.box_firmware.setValue("Virtual Channel", COLORS["value"])
                self.box_protocol.setValue("VLC Beta v3.0", COLORS["value"])
                self.box_usb.setValue("UDP localhost:9902 (Active)", COLORS["green"])
            else:
                self.box_connection.setValue("Waiting for RX Link (Sim)", COLORS["amber"])
                self.box_firmware.setValue("Virtual Channel", COLORS["value"])
                self.box_protocol.setValue("VLC Beta v3.0", COLORS["value"])
                self.box_usb.setValue("UDP localhost:9902 (Listening)", COLORS["muted"])
        else:
            if connected:
                self.box_connection.setValue("Hardware Connected", COLORS["green"])
                self.box_firmware.setValue("ESP32 v1.0", COLORS["value"])
                self.box_protocol.setValue("VLC Beta v3.0", COLORS["value"])
                self.box_usb.setValue(f"{state.port or 'ttyUSB0'} (115200 baud)", COLORS["green"])
            else:
                self.box_connection.setValue("Disconnected", COLORS["red"])
                self.box_firmware.setValue("—", COLORS["muted"])
                self.box_protocol.setValue("VLC Beta v3.0", COLORS["value"])
                self.box_usb.setValue("Inactive", COLORS["muted"])


# ── Section 2: TRANSMISSION PIPELINE ─────────────────────────────────

class _PipelineStage(QFrame):
    def __init__(self, name: str, desc: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PipelineStage")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        
        self.setStyleSheet(
            f"QFrame#PipelineStage {{ background-color: {COLORS['panel_alt']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 6px; }}"
        )
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        self.name_lbl = QLabel(name)
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lbl.setStyleSheet(f"color: {COLORS['muted']}; font-size: 9px; font-weight: 700; background: transparent;")
        
        self.desc_lbl = QLabel(desc)
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_lbl.setStyleSheet(f"color: {COLORS['secondary']}; font-size: 11px; font-weight: 600; background: transparent;")
        self.desc_lbl.setWordWrap(True)
        
        layout.addWidget(self.name_lbl)
        layout.addWidget(self.desc_lbl)
        
    def setActive(self, active: bool, text: str) -> None:
        self.desc_lbl.setText(text)
        if active:
            self.setStyleSheet(
                f"QFrame#PipelineStage {{ background-color: #132238; "
                f"border: 2px solid {COLORS['green']}; border-radius: 6px; }}"
            )
            self.desc_lbl.setStyleSheet(f"color: {COLORS['green']}; font-size: 11px; font-weight: 700; background: transparent;")
        else:
            self.setStyleSheet(
                f"QFrame#PipelineStage {{ background-color: {COLORS['panel_alt']}; "
                f"border: 1px solid {COLORS['border']}; border-radius: 6px; }}"
            )
            self.desc_lbl.setStyleSheet(f"color: {COLORS['secondary']}; font-size: 11px; font-weight: 600; background: transparent;")


class TransmissionPipelineWidget(Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("TRANSMISSION PIPELINE", parent)
        
        self.flow = QHBoxLayout()
        self.flow.setSpacing(6)
        self.flow.setContentsMargins(0, 8, 0, 8)
        
        self.stage_file = _PipelineStage("FILE", "Idle")
        self.stage_chunk = _PipelineStage("CHUNKING", "Idle")
        self.stage_enc = _PipelineStage("4B5B ENCODE", "Idle")
        self.stage_mod = _PipelineStage("OOK MOD", "Idle")
        self.stage_esp = _PipelineStage("ESP32 TX", "Idle")
        self.stage_optical = _PipelineStage("OPTICAL", "Idle")
        
        self.flow.addWidget(self.stage_file)
        self.flow.addWidget(self._arrow())
        self.flow.addWidget(self.stage_chunk)
        self.flow.addWidget(self._arrow())
        self.flow.addWidget(self.stage_enc)
        self.flow.addWidget(self._arrow())
        self.flow.addWidget(self.stage_mod)
        self.flow.addWidget(self._arrow())
        self.flow.addWidget(self.stage_esp)
        self.flow.addWidget(self._arrow())
        self.flow.addWidget(self.stage_optical)
        
        self.body.addLayout(self.flow)
        
    def _arrow(self) -> QLabel:
        lbl = QLabel("→")
        lbl.setStyleSheet(f"color: {COLORS['border']}; font-size: 14px; font-weight: 900; background: transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl
        
    def refresh(self, state: TXAppState) -> None:
        status_lower = (state.status_text or "").lower()
        is_transmitting = "transmitting" in status_lower
        
        if is_transmitting:
            self.stage_file.setActive(True, state.filename or "File")
            self.stage_chunk.setActive(True, f"Chunk {state.current_chunk}/{state.total_chunks}")
            self.stage_enc.setActive(True, state.encoding or "4B5B")
            self.stage_mod.setActive(True, state.modulation or "NRZ/OOK")
            self.stage_esp.setActive(True, f"GPIO {state.led_pin}")
            self.stage_optical.setActive(True, f"LED {state.tx_power}")
        else:
            self.stage_file.setActive(False, "Idle")
            self.stage_chunk.setActive(False, "Idle")
            self.stage_enc.setActive(False, "Idle")
            self.stage_mod.setActive(False, "Idle")
            self.stage_esp.setActive(state.serial_connected, f"GPIO {state.led_pin}" if state.serial_connected else "Offline")
            self.stage_optical.setActive(False, "Idle")


# ── Section 3: CURRENT SESSION ───────────────────────────────────────

class CurrentSessionWidget(Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("CURRENT SESSION", parent)
        self.body.setSpacing(6)
        
        self.row_sent = _DetailRow("Files Sent", "0")
        self.row_success = _DetailRow("Success Rate", "100 %", val_color=COLORS["green"])
        self.row_rate = _DetailRow("Average Throughput", "0 bps")
        self.row_last = _DetailRow("Last Transfer", "None")
        
        self.body.addWidget(self.row_sent)
        self.body.addWidget(self.row_success)
        self.body.addWidget(self.row_rate)
        self.body.addWidget(self.row_last)
        
    def refresh(self, state: TXAppState) -> None:
        sent = 0
        success = 0
        for item in state.session_history:
            if item["outcome"] in ("SUCCESS", "FAILED"):
                sent += 1
            if item["outcome"] == "SUCCESS":
                success += 1
                
        rate_pct = 100
        if sent > 0:
            rate_pct = int((success / sent) * 100)
            
        self.row_sent.setValue(str(sent))
        self.row_success.setValue(f"{rate_pct} %", COLORS["green"] if rate_pct >= 90 else COLORS["amber"])
        self.row_rate.setValue(state.data_rate or "0 bps")
        
        last_file = "None"
        for item in state.session_history:
            if item["outcome"] in ("SUCCESS", "FAILED"):
                last_file = f"{item['file']} ({item['outcome']})"
                break
        self.row_last.setValue(last_file)


# ── Section 4: FILE DETAILS & CONTROLS ───────────────────────────────

class FileDetailsWidget(Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("FILE DETAILS", parent)
        self.body.setSpacing(6)
        
        self.row_name = _DetailRow("Filename", "—")
        self.row_size = _DetailRow("Size", "—")
        self.row_chunks = _DetailRow("Chunk Count", "—")
        self.row_time = _DetailRow("Est. Duration", "—")
        self.row_crc = _DetailRow("CRC Status", "Pending", val_color=COLORS["amber"])
        
        self.body.addWidget(self.row_name)
        self.body.addWidget(self.row_size)
        self.body.addWidget(self.row_chunks)
        self.body.addWidget(self.row_time)
        self.body.addWidget(self.row_crc)
        
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.setContentsMargins(0, 4, 0, 0)
        
        self.select_btn = QPushButton("Select File...")
        self.select_btn.setMinimumHeight(30)
        self.select_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['panel_alt']}; color: {COLORS['text']}; border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 6px 12px; font-weight: 600; font-size: 11px; }}"
            f"QPushButton:hover {{ border-color: {COLORS['accent']}; background-color: {COLORS['sidebar_active']}; }}"
            f"QPushButton:pressed {{ background-color: {COLORS['bg']}; }}"
        )
        
        self.start_btn = primary_button("Start")
        self.start_btn.setMinimumHeight(30)
        self.start_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['accent']}; color: white; border: none; border-radius: 6px; padding: 6px 16px; font-weight: 700; font-size: 11px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['header']}; }}"
        )
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(30)
        self.cancel_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['red']}; color: white; border: none; border-radius: 6px; padding: 6px 16px; font-weight: 700; font-size: 11px; }}"
            f"QPushButton:hover {{ background-color: #ff5c5c; }}"
        )
        
        btn_row.addWidget(self.select_btn)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.cancel_btn)
        self.body.addLayout(btn_row)
        
    def refresh(self, state: TXAppState) -> None:
        self.row_name.setValue(state.filename or "No file")
        
        size_str = "—"
        if state.file_size_bytes > 0:
            size_str = f"{state.file_size_bytes / 1024:.2f} KiB"
        self.row_size.setValue(size_str)
        
        self.row_chunks.setValue(str(state.total_chunks) if state.total_chunks > 0 else "—")
        self.row_time.setValue(state.estimated_time if state.estimated_time != "00:00:00" else "—")
        
        status_lower = (state.status_text or "").lower()
        is_transmitting = "transmitting" in status_lower
        
        if is_transmitting:
            self.row_crc.setValue("Verifying (CRC-16)", COLORS["amber"])
        elif "complete" in status_lower:
            self.row_crc.setValue("SUCCESS (CRC OK)", COLORS["green"])
        elif "failed" in status_lower:
            self.row_crc.setValue("FAILED (CRC Error)", COLORS["red"])
        else:
            self.row_crc.setValue("Idle", COLORS["muted"])
            
        self.start_btn.setEnabled(not is_transmitting and state.serial_connected)
        self.cancel_btn.setVisible(is_transmitting)
        self.start_btn.setVisible(not is_transmitting)


# ── Section 5: ENCODED BIT STREAM ────────────────────────────────────

class DigitalBitstreamWidget(Card):
    """Logic Analyzer digital wave representing the outgoing 4B5B bit stream."""
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("ENCODED BIT STREAM (LOGIC ANALYZER)", parent)
        self._bits: list[int] = []
        self._offset = 0
        self._has_data = False
        
        # Dedicated graphics paint viewport
        self.canvas = QWidget()
        self.canvas.setMinimumHeight(110)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.paintEvent = self._paint_canvas
        self.body.addWidget(self.canvas)
        
    def refresh(self, state: TXAppState) -> None:
        status_lower = (state.status_text or "").lower()
        is_transmitting = "transmitting" in status_lower
        
        if not is_transmitting:
            self._bits = []
            self._has_data = False
            self.canvas.update()
            return
            
        self._has_data = True
        chunk_idx = state.current_chunk
        self._offset = (self._offset + 0.5) % 40
        
        # Generate simulation bits
        bits = []
        for i in range(12):
            bits.append(i % 2) # Preamble representation
        for i in range(70):
            # Generate deterministic bit array based on chunk index
            bits.append(((chunk_idx * 17 + i * 3) >> (i % 5)) & 1)
            
        self._bits = bits
        self.canvas.update()
        
    def _paint_canvas(self, event: Any) -> None:
        painter = QPainter(self.canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.canvas.width()
        h = self.canvas.height()
        
        # Colors
        bg_color = QColor(COLORS["panel_alt"])
        wave_color = QColor("#00E5FF") # logic analyzer cyan
        grid_color = QColor(COLORS["border"])
        text_color = QColor(COLORS["text"])
        muted_color = QColor(COLORS["muted"])
        
        painter.fillRect(0, 0, w, h, bg_color)
        
        left_margin = 15
        right_margin = 15
        top_margin = 20
        bottom_margin = 25
        
        plot_w = w - left_margin - right_margin
        plot_h = h - top_margin - bottom_margin
        
        # Logic level coordinates
        y_high = top_margin + int(plot_h * 0.15)
        y_low = top_margin + int(plot_h * 0.75)
        
        # Draw grids
        painter.setPen(QPen(grid_color, 1, Qt.PenStyle.DashLine))
        painter.drawLine(left_margin, y_high, left_margin + plot_w, y_high)
        painter.drawLine(left_margin, y_low, left_margin + plot_w, y_low)
        
        # Labels
        painter.setPen(muted_color)
        painter.setFont(QFont("Monospace", 8))
        painter.drawText(2, y_high + 4, "1", )
        painter.drawText(2, y_low + 4, "0")
        
        if not self._has_data or not self._bits:
            painter.setPen(QPen(muted_color, 2))
            painter.drawLine(left_margin, y_low, left_margin + plot_w, y_low)
            painter.setFont(QFont("Inter", 10, QFont.Weight.Bold))
            painter.setPen(text_color)
            painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "Logic Analyzer: IDLE")
            painter.end()
            return
            
        num_bits = len(self._bits)
        bit_w = plot_w / num_bits
        
        path = QPainterPath()
        shift_px = (self._offset % 40) * (bit_w / 40.0)
        
        last_x = left_margin
        last_y = y_high if self._bits[0] == 1 else y_low
        path.moveTo(last_x, last_y)
        
        for i in range(num_bits):
            x_start = left_margin + i * bit_w - shift_px
            x_end = x_start + bit_w
            bit_val = self._bits[i]
            target_y = y_high if bit_val == 1 else y_low
            
            if x_end < left_margin:
                continue
            if x_start > left_margin + plot_w:
                break
                
            x_draw_start = max(x_start, left_margin)
            x_draw_end = min(x_end, left_margin + plot_w)
            
            if target_y != last_y:
                path.lineTo(x_draw_start, target_y)
            path.lineTo(x_draw_end, target_y)
            
            last_y = target_y
            
        painter.setPen(QPen(wave_color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        
        # Draw framing boundary
        painter.setPen(QPen(QColor(COLORS["amber"]), 1, Qt.PenStyle.DashLine))
        boundary_x1 = left_margin + 12 * bit_w - shift_px
        if left_margin <= boundary_x1 <= left_margin + plot_w:
            painter.drawLine(int(boundary_x1), top_margin - 8, int(boundary_x1), top_margin + plot_h)
            painter.setPen(QColor(COLORS["amber"]))
            painter.setFont(QFont("Inter", 8, QFont.Weight.Bold))
            painter.drawText(int(boundary_x1) + 4, top_margin - 6, "PREAMBLE")
            
        # Draw scrolling text values
        painter.setPen(text_color)
        painter.setFont(QFont("Monospace", 9, QFont.Weight.Bold))
        
        for i, b in enumerate(self._bits):
            x = left_margin + i * bit_w + (bit_w / 2) - 3 - shift_px
            if left_margin <= x <= left_margin + plot_w - 6:
                painter.drawText(int(x), h - 2, str(b))
                
        painter.end()


# ── Section 6: TRANSMISSION LOGS ─────────────────────────────────────

class _LogEntryWidget(QWidget):
    """Single log entry: timestamp + message, monospace style."""

    def __init__(self, entry: dict[str, str], index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 3, 12, 3)
        layout.setSpacing(12)

        ts = entry.get("time", "")
        event = entry.get("event", "")
        details = entry.get("details", "")

        ts_label = QLabel(f"[{ts}]")
        ts_label.setStyleSheet(
            f"color: {COLORS['header']}; font-family: 'Courier New', monospace; font-size: 11px; background: transparent;"
        )
        layout.addWidget(ts_label)

        msg_text = event
        if details:
            msg_text += f" — {details}"
            
        event_lower = event.lower()
        if "error" in event_lower or "fail" in event_lower:
            text_color = COLORS['red']
        elif "warn" in event_lower:
            text_color = COLORS['amber']
        elif "success" in event_lower or "ok" in event_lower or "finish" in event_lower or "start" in event_lower:
            text_color = COLORS['green']
        elif "offline" in event_lower:
            text_color = COLORS['muted']
        else:
            text_color = COLORS['text']

        msg_label = QLabel(msg_text)
        msg_label.setStyleSheet(
            f"color: {text_color}; font-family: 'Courier New', monospace; font-size: 11px; background: transparent;"
        )
        layout.addWidget(msg_label, 1)

        if index % 2 == 1:
            self.setStyleSheet(f"background: {COLORS['panel_alt']};")
        else:
            self.setStyleSheet(f"background: {COLORS['panel']};")


class _TXLogPanel(Card):
    """TRANSMISSION LOG panel — scrollable list of log entries."""

    def __init__(self, state: TXAppState, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        
        header = _SectionHeader("TRANSMISSION LOGS")
        self.body.addWidget(header)

        self._log_container = QWidget()
        self._log_layout = QVBoxLayout(self._log_container)
        self._log_layout.setContentsMargins(0, 0, 0, 0)
        self._log_layout.setSpacing(0)
        self._log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet(
            f"background: {COLORS['panel']}; border: 1px solid {COLORS['border']}; border-radius: 6px;"
        )
        self._scroll_area.setWidget(self._log_container)

        self._scroll_area.setMinimumHeight(100)
        self._scroll_area.setMaximumHeight(200)
        self.body.addWidget(self._scroll_area, 1)

        self._last_log_len = 0
        self._no_entries_label = muted_label("No log entries yet.")
        self._log_layout.addWidget(self._no_entries_label)

    def refresh(self, state: TXAppState) -> None:
        log_entries = state.activity_log
        num_entries = len(log_entries)

        if num_entries == self._last_log_len:
            return

        if num_entries < self._last_log_len or self._last_log_len == 0:
            while self._log_layout.count():
                item = self._log_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            self._last_log_len = 0

        if num_entries == 0:
            self._no_entries_label = muted_label("No log entries yet.")
            self._log_layout.addWidget(self._no_entries_label)
            self._last_log_len = 0
            return

        for i in range(self._last_log_len, num_entries):
            entry = log_entries[i]
            widget = _LogEntryWidget(entry, i)
            self._log_layout.addWidget(widget)

        self._last_log_len = num_entries

        scrollbar = self._scroll_area.verticalScrollBar()
        if scrollbar:
            QTimer.singleShot(50, lambda: scrollbar.setValue(scrollbar.maximum()))


# ── Unified Dashboard Page ───────────────────────────────────────────

class TXDashboardPage(QWidget):
    """Full TX console dashboard matching laboratory software design."""

    def __init__(self, state: TXAppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(12)

        # 1. Device Status Panel (Full Width)
        self._device_status = DeviceStatusWidget()
        outer.addWidget(self._device_status)

        # 2. Pipeline and Session Row
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        
        self._pipeline = TransmissionPipelineWidget()
        self._session = CurrentSessionWidget()
        
        row2.addWidget(self._pipeline, 1)
        row2.addWidget(self._session, 1)
        outer.addLayout(row2)

        # 3. File Details and Encoded Bit Stream Row
        row3 = QHBoxLayout()
        row3.setSpacing(12)
        
        self._file_details = FileDetailsWidget()
        self._file_details.select_btn.clicked.connect(self._on_select_file_clicked)
        self._file_details.start_btn.clicked.connect(self._on_start_clicked)
        self._file_details.cancel_btn.clicked.connect(self._on_cancel_clicked)
        
        self._bit_stream = DigitalBitstreamWidget()
        
        row3.addWidget(self._file_details, 1)
        row3.addWidget(self._bit_stream, 1)
        outer.addLayout(row3)

        # 4. Logs Panel (Full Width)
        self._logs = _TXLogPanel(state)
        outer.addWidget(self._logs, 1)

        self.refresh()

    def _on_select_file_clicked(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        filepath, _ = QFileDialog.getOpenFileName(self, "Select File to Transmit", "", "All Files (*)")
        if filepath:
            from pathlib import Path
            p = Path(filepath)
            if p.exists():
                self._state.filename = p.name
                self._state.filetype = p.suffix.upper()[1:] + " File"
                self._state.file_size_bytes = p.stat().st_size
                self._state.total_chunks = max(1, (self._state.file_size_bytes + self._state.chunk_size - 1) // self._state.chunk_size)
                self._state.current_chunk = 0
                self._state.progress_percent = 0
                self._state.status_text = f"Selected {p.name}"
                self._pending_filepath = filepath
                self._state.refresh()

    def _on_start_clicked(self) -> None:
        filepath = getattr(self, "_pending_filepath", None)
        if filepath:
            self._state.start_transmission(filepath)
        else:
            self._on_select_file_clicked()
            filepath = getattr(self, "_pending_filepath", None)
            if filepath:
                self._state.start_transmission(filepath)

    def _on_cancel_clicked(self) -> None:
        if self._state.mode == "simulated" and self._state._simulation:
            self._state._simulation.stop()
            self._state.refresh()

    def refresh(self, state: TXAppState | None = None) -> None:
        if state is not None:
            self._state = state
            
        self._device_status.refresh(self._state)
        self._pipeline.refresh(self._state)
        self._session.refresh(self._state)
        self._file_details.refresh(self._state)
        self._bit_stream.refresh(self._state)
        self._logs.refresh(self._state)
