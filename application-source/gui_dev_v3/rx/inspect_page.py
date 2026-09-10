"""Inspect Page — detailed chunk structure and bit-level hex analysis matching Keysight styles."""

from __future__ import annotations

import math
from PySide6.QtCore import Qt, Signal, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

import os
from gui_dev_v3.logic.ber_bridge import parse_ber_test_name

from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.models import ChunkRecord, ChunkStatus
from gui_dev_v3.theme import COLORS
from gui_dev_v3.widgets import Card, muted_label, value_label, panel_header

# Color palette for chunk statuses mapping
_COLORS = {
    ChunkStatus.MATCH:     QColor("#22c55e"),   # green
    ChunkStatus.DIFFERENT: QColor("#ef4444"),   # red
    ChunkStatus.MISSING:   QColor("#1e3a5f"),   # dark navy
    ChunkStatus.PENDING:   QColor("#3b82f6"),   # blue
    ChunkStatus.RECEIVED:  QColor("#06b6d4"),   # cyan
}
_BG        = QColor("#08111D")
_BORDER    = QColor("#1A3152")
_SELECTED  = QColor("#60a5fa")


class ChunkHealthMap(QWidget):
    """Grid of colored rounded rectangles showing chunk integrity."""

    chunk_selected = Signal(int)  # index of chunk on double-click
    selection_changed = Signal(int)  # index of chunk on click

    CELL_SIZE = 14
    CELL_GAP = 2
    MIN_COLS = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._chunks: list[ChunkRecord] = []
        self._selected = -1
        self._hovered = -1

        self.setMouseTracking(True)
        self.setMinimumHeight(60)

    def set_chunks(self, chunks: list[ChunkRecord]) -> None:
        self._chunks = chunks
        self._selected = -1
        self._update_height()
        self.update()

    def select_chunk(self, index: int) -> None:
        if 0 <= index < len(self._chunks):
            self._selected = index
        else:
            self._selected = -1
        self.update()

    def _cols(self) -> int:
        cell_step = self.CELL_SIZE + self.CELL_GAP
        w = self.width()
        cols = max(self.MIN_COLS, (w - 24) // cell_step)
        return cols

    def _update_height(self) -> None:
        n = len(self._chunks)
        if n == 0:
            self.setFixedHeight(60)
            return
        cols = self._cols()
        rows = (n + cols - 1) // cols
        cell_step = self.CELL_SIZE + self.CELL_GAP
        total_h = 12 + rows * cell_step + 12
        self.setMinimumHeight(total_h)

    def resizeEvent(self, event) -> None:
        self._update_height()
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(COLORS["panel"]))

        if not self._chunks:
            p.setPen(QColor(COLORS["muted"]))
            p.setFont(QFont("Inter", 11))
            p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "No transfer data available")
            p.end()
            return

        cols = self._cols()
        cell_step = self.CELL_SIZE + self.CELL_GAP
        origin_x = 12
        origin_y = 12

        for i, chunk in enumerate(self._chunks):
            col = i % cols
            row = i // cols
            cx = origin_x + col * cell_step
            cy = origin_y + row * cell_step

            base_color = _COLORS.get(chunk.status, QColor("#1A3152"))

            # Dim non-selected cells when selection is active
            if self._selected >= 0 and i != self._selected:
                dim_color = QColor(base_color)
                dim_color.setAlpha(80)
                brush = QBrush(dim_color)
            else:
                brush = QBrush(base_color)

            rect = QRectF(cx + 0.5, cy + 0.5, self.CELL_SIZE - 1, self.CELL_SIZE - 1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(brush)

            # Draw a subtle glow under DIFFERENT chunks (red errors)
            if chunk.status == ChunkStatus.DIFFERENT and (self._selected < 0 or i == self._selected):
                glow = QColor("#ef4444")
                glow.setAlpha(40)
                p.setBrush(glow)
                p.drawRoundedRect(cx - 1.5, cy - 1.5, self.CELL_SIZE + 3, self.CELL_SIZE + 3, 3, 3)
                p.setBrush(brush)

            p.drawRoundedRect(rect, 2.0, 2.0)

            # Hover border
            if i == self._hovered:
                p.setPen(QPen(QColor("#FFFFFF"), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect, 2.0, 2.0)

            # Selection border
            if i == self._selected:
                p.setPen(QPen(_SELECTED, 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(cx - 0.5, cy - 0.5, self.CELL_SIZE, self.CELL_SIZE, 2.0, 2.0)

        p.end()

    def _cell_at(self, pos) -> int:
        if not self._chunks:
            return -1
        cols = self._cols()
        cell_step = self.CELL_SIZE + self.CELL_GAP
        col = (pos.x() - 12) // cell_step
        row = (pos.y() - 12) // cell_step
        if 0 <= col < cols:
            idx = row * cols + col
            if 0 <= idx < len(self._chunks):
                return idx
        return -1

    def mouseMoveEvent(self, event) -> None:
        idx = self._cell_at(event.position().toPoint())
        if idx != self._hovered:
            self._hovered = idx
            self.update()
        if 0 <= idx < len(self._chunks):
            c = self._chunks[idx]
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"Chunk #{c.index} ({c.status.value})\n"
                f"Expected: {c.expected_size} Bytes\n"
                f"Received: {c.received_size} Bytes",
                self
            )
        else:
            QToolTip.hideText()

    def mousePressEvent(self, event) -> None:
        idx = self._cell_at(event.position().toPoint())
        if 0 <= idx < len(self._chunks):
            self._selected = idx
            self.update()
            self.selection_changed.emit(idx)
        else:
            self._selected = -1
            self.update()
            self.selection_changed.emit(-1)

    def mouseDoubleClickEvent(self, event) -> None:
        idx = self._cell_at(event.position().toPoint())
        if 0 <= idx < len(self._chunks):
            self.chunk_selected.emit(idx)


class ByteComparisonDialog(QDialog):
    """Side-by-side comparison of expected vs received bytes for double-clicked chunks."""

    def __init__(self, chunk: ChunkRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Chunk #{chunk.index} — Byte-level Comparison")
        self.resize(700, 450)
        self.setStyleSheet(
            f"QDialog {{ background: {COLORS['bg']}; color: {COLORS['text']}; }}"
            f"QTableWidget {{ background: {COLORS['panel']}; border: 1px solid {COLORS['border']}; gridline-color: {COLORS['border']}; }}"
            f"QHeaderView::section {{ background: {COLORS['panel_alt']}; color: {COLORS['muted']}; border: none; font-weight: 700; }}"
        )

        lo = QVBoxLayout(self)
        lo.setContentsMargins(16, 16, 16, 16)
        lo.setSpacing(12)

        # Header info
        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>Chunk Index:</b> {chunk.index}"))
        header.addStretch(1)
        status_lbl = QLabel(f"Status: {chunk.status.value}")
        if chunk.status == ChunkStatus.MATCH:
            status_lbl.setStyleSheet(f"color: {COLORS['green']}; font-weight: 700;")
        elif chunk.status == ChunkStatus.DIFFERENT:
            status_lbl.setStyleSheet(f"color: {COLORS['red']}; font-weight: 700;")
        else:
            status_lbl.setStyleSheet(f"color: {COLORS['muted']}; font-weight: 700;")
        header.addWidget(status_lbl)
        lo.addLayout(header)

        # Table showing byte rows
        # Columns: Offset, Expected (Hex), Expected (ASCII), Received (Hex), Received (ASCII), Match
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Offset", "Expected (Hex)", "Expected (ASCII)",
            "Received (Hex)", "Received (ASCII)", "Integrity"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Populate rows
        max_len = max(len(chunk.expected), len(chunk.received))
        self.table.setRowCount(max_len)

        for i in range(max_len):
            offset_item = QTableWidgetItem(f"+0x{i:04X} ({i})")
            offset_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            offset_item.setForeground(QColor(COLORS["muted"]))
            self.table.setItem(i, 0, offset_item)

            # Expected
            exp_hex, exp_char = "—", "—"
            if i < len(chunk.expected):
                val = chunk.expected[i]
                exp_hex = f"0x{val:02X}"
                exp_char = chr(val) if 32 <= val <= 126 else "."
            
            exp_hex_item = QTableWidgetItem(exp_hex)
            exp_hex_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            exp_hex_item.setFont(QFont("Cascadia Code, Courier New", 10))
            self.table.setItem(i, 1, exp_hex_item)

            exp_char_item = QTableWidgetItem(exp_char)
            exp_char_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 2, exp_char_item)

            # Received
            rec_hex, rec_char = "—", "—"
            if i < len(chunk.received):
                val = chunk.received[i]
                rec_hex = f"0x{val:02X}"
                rec_char = chr(val) if 32 <= val <= 126 else "."
            
            rec_hex_item = QTableWidgetItem(rec_hex)
            rec_hex_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            rec_hex_item.setFont(QFont("Cascadia Code, Courier New", 10))
            self.table.setItem(i, 3, rec_hex_item)

            rec_char_item = QTableWidgetItem(rec_char)
            rec_char_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 4, rec_char_item)

            # Match status
            match_item = QTableWidgetItem()
            match_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Formatting mismatch rows in red
            is_match = False
            if i < len(chunk.expected) and i < len(chunk.received):
                if chunk.expected[i] == chunk.received[i]:
                    is_match = True

            if is_match:
                match_item.setText("MATCH")
                match_item.setForeground(QColor(COLORS["green"]))
            else:
                match_item.setText("MISMATCH")
                match_item.setForeground(QColor(COLORS["red"]))
                # Paint the row cells background slightly red to indicate error
                for col in range(6):
                    cell = self.table.item(i, col)
                    if cell:
                        cell.setBackground(QColor(239, 68, 68, 20))  # subtle red tint

            self.table.setItem(i, 5, match_item)

        lo.addWidget(self.table)

        # OK Close button
        btn = QPushButton("Close")
        btn.setObjectName("Primary")
        btn.setFixedWidth(100)
        btn.clicked.connect(self.accept)
        lo.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)


class InspectPage(QWidget):
    """Detailed file payload inspection tab."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_tid = -1
        self._last_chunk_count = -1
        self._last_expected_path = ""
        self._current_chunks: list[ChunkRecord] = []

        # Page layout
        lo = QVBoxLayout(self)
        lo.setContentsMargins(20, 16, 20, 20)
        lo.setSpacing(12)

        # ── 1. Transfer Snapshot Card ──
        self.snap_card = Card("Transfer Snapshot")
        self.snap_lbl = QLabel("TID: —  |  Filename: —  |  Size: —  |  Total: 0 chunks")
        self.snap_lbl.setStyleSheet("font-weight: 600; font-size: 13px; color: #FFFFFF;")
        self.snap_card.body.addWidget(self.snap_lbl)
        lo.addWidget(self.snap_card)

        # ── 2. Reference File Status Card ──
        self.ref_status_card = Card("Reference File Status")
        ref_status_lo = QHBoxLayout()
        ref_status_lo.setContentsMargins(4, 4, 4, 4)
        ref_status_lo.setSpacing(12)
        
        self.ref_status_lbl = QLabel("No reference file loaded (BERTEST files will auto-compare)")
        self.ref_status_lbl.setStyleSheet("font-weight: 600; font-size: 11px; color: #8c99aa;")
        ref_status_lo.addWidget(self.ref_status_lbl, 1)
        
        self.inspect_load_btn = QPushButton("Load Reference")
        self.inspect_load_btn.setObjectName("Primary")
        self.inspect_load_btn.clicked.connect(self._on_inspect_load_ref)
        ref_status_lo.addWidget(self.inspect_load_btn)
        
        self.inspect_clear_btn = QPushButton("Clear")
        self.inspect_clear_btn.clicked.connect(self._on_inspect_clear_ref)
        ref_status_lo.addWidget(self.inspect_clear_btn)
        
        self.ref_status_card.body.addLayout(ref_status_lo)
        lo.addWidget(self.ref_status_card)

        # ── 3. Chunk Health Map Card ──
        self.map_card = Card("Chunk Health Map")
        self._health_map = ChunkHealthMap()
        self.map_card.body.addWidget(self._health_map)
        
        # Legend row
        legend_row = QHBoxLayout()
        legend_row.setSpacing(16)
        CHUNK_LEGEND = [
            ("Match",     "#22c55e"),
            ("Different", "#ef4444"),
            ("Missing",   "#1e3a5f"),
            ("Pending",   "#3b82f6"),
            ("Received",  "#06b6d4"),
        ]
        for name, color in CHUNK_LEGEND:
            dot = QLabel(f"■ {name}")
            dot.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 700; background: transparent;")
            legend_row.addWidget(dot)
        legend_row.addStretch(1)
        self.map_card.body.addLayout(legend_row)
        
        lo.addWidget(self.map_card)

        # ── 4. Bottom Row (Byte Explorer & Chunk Details) ──
        bottom_lo = QHBoxLayout()
        bottom_lo.setSpacing(12)

        # Left Column: Chunk Explorer
        self.chunk_card = Card("Chunk Details Explorer")
        self.chunk_table = QTableWidget()
        self.chunk_table.setColumnCount(4)
        self.chunk_table.setHorizontalHeaderLabels(["Index", "Status", "Rx/Tx Bytes", "Errors"])
        self.chunk_table.verticalHeader().setVisible(False)
        self.chunk_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.chunk_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.chunk_table.setMinimumHeight(180)
        self.chunk_card.body.addWidget(self.chunk_table)
        bottom_lo.addWidget(self.chunk_card, 1)

        # Right Column: Byte Explorer
        self.byte_card = Card("Byte Explorer")
        self.byte_table = QTableWidget()
        self.byte_table.setColumnCount(4)
        self.byte_table.setHorizontalHeaderLabels(["Offset", "Hex", "ASCII", "Bit View"])
        self.byte_table.verticalHeader().setVisible(False)
        self.byte_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.byte_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.byte_table.setMinimumHeight(180)
        self.byte_card.body.addWidget(self.byte_table)
        bottom_lo.addWidget(self.byte_card, 1)

        lo.addLayout(bottom_lo)

        # Wire map selection changes
        self._health_map.selection_changed.connect(self._on_map_selection)
        self._health_map.chunk_selected.connect(self._on_map_double_click)

        # Wire table selections
        self.chunk_table.itemSelectionChanged.connect(self._on_table_selection)
        self.chunk_table.cellDoubleClicked.connect(self._on_table_double_click)

    def _on_inspect_load_ref(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(self, "Load Expected Reference File", "", "All Files (*)")
        if filepath:
            state = self._get_state()
            if state:
                state.load_expected_file(filepath)

    def _on_inspect_clear_ref(self) -> None:
        state = self._get_state()
        if state:
            state.clear_expected_file()

    def _get_state(self) -> RXAppState | None:
        parent = self.parent()
        while parent:
            if hasattr(parent, "state"):
                return parent.state
            parent = parent.parent()
        return None

    def refresh(self, state: RXAppState) -> None:
        """Refresh page metrics, health map, and explorers from state."""
        transfer = state.transfer

        # Dirty check: skip heavy operations if the transfer has not updated
        expected_path = state.expected_file_path or ""
        if transfer.tid == self._last_tid and len(transfer.chunks) == self._last_chunk_count and expected_path == self._last_expected_path:
            return

        self._last_tid = transfer.tid
        self._last_chunk_count = len(transfer.chunks)
        self._last_expected_path = expected_path
        self._current_chunks = transfer.chunks

        # Update Reference File status label in InspectPage
        filename_raw = transfer.filename or ""
        ber_params = parse_ber_test_name(filename_raw)
        if ber_params:
            size, seed = ber_params
            self.ref_status_lbl.setText(f"BERTEST Auto Mode: Generated seed {seed:08X} ({size} B)")
            self.ref_status_lbl.setStyleSheet("font-weight: 600; font-size: 11px; color: #22c55e;")
        elif state.expected_file_data is not None:
            self.ref_status_lbl.setText(f"Reference Loaded: {os.path.basename(expected_path)} ({len(state.expected_file_data)} B)")
            self.ref_status_lbl.setStyleSheet("font-weight: 600; font-size: 11px; color: #22c55e;")
        else:
            self.ref_status_lbl.setText("No reference file loaded (BERTEST files auto-compare; others show cyan RECEIVED)")
            self.ref_status_lbl.setStyleSheet("font-weight: 600; font-size: 11px; color: #8c99aa;")

        # Update snapshot label
        filename = transfer.filename or "No active transfer"
        status = transfer.status.value if transfer.status else "Idle"
        size = f"{transfer.size_bytes} Bytes" if transfer.size_bytes > 0 else "0 Bytes"
        self.snap_lbl.setText(
            f"TID: {transfer.tid:04d}  |  File: {filename} ({status})  |  "
            f"Size: {size}  |  Total: {transfer.total_chunks} chunks"
        )

        # Populate health map
        self._health_map.set_chunks(self._current_chunks)

        # Populate chunk details table
        # Populate chunk details table
        self.chunk_table.blockSignals(True)
        if self.chunk_table.rowCount() != len(self._current_chunks):
            self.chunk_table.setRowCount(len(self._current_chunks))

        for idx, c in enumerate(self._current_chunks):
            # Index
            idx_item = self.chunk_table.item(idx, 0)
            if idx_item is None:
                idx_item = QTableWidgetItem(f"Chunk #{c.index}")
                idx_item.setForeground(QColor(COLORS["text"]))
                self.chunk_table.setItem(idx, 0, idx_item)
            else:
                idx_item.setText(f"Chunk #{c.index}")

            # Status
            status_item = self.chunk_table.item(idx, 1)
            c_status_val = c.status.value if hasattr(c.status, 'value') else str(c.status)
            color_map = {
                ChunkStatus.MATCH:     COLORS["green"],
                ChunkStatus.DIFFERENT: COLORS["red"],
                ChunkStatus.MISSING:   COLORS["muted"],
                ChunkStatus.PENDING:   COLORS["accent"],
                ChunkStatus.RECEIVED:  COLORS["green"],
            }
            c_color = color_map.get(c.status, COLORS["text"])
            if status_item is None:
                status_item = QTableWidgetItem(c_status_val)
                status_item.setForeground(QColor(c_color))
                status_item.setFont(QFont("Inter", 10, QFont.Bold))
                self.chunk_table.setItem(idx, 1, status_item)
            else:
                status_item.setText(c_status_val)
                status_item.setForeground(QColor(c_color))

            # Rx/Tx Bytes
            bytes_item = self.chunk_table.item(idx, 2)
            bytes_txt = f"{c.received_size} / {c.expected_size} B"
            if bytes_item is None:
                bytes_item = QTableWidgetItem(bytes_txt)
                self.chunk_table.setItem(idx, 2, bytes_item)
            else:
                bytes_item.setText(bytes_txt)

            # Errors
            err_item = self.chunk_table.item(idx, 3)
            err_txt = f"{c.different_bytes} errors" if c.different_bytes > 0 else "None"
            if err_item is None:
                err_item = QTableWidgetItem(err_txt)
                if c.different_bytes > 0:
                    err_item.setForeground(QColor(COLORS["red"]))
                self.chunk_table.setItem(idx, 3, err_item)
            else:
                err_item.setText(err_txt)
                if c.different_bytes > 0:
                    err_item.setForeground(QColor(COLORS["red"]))
                else:
                    err_item.setForeground(QColor(COLORS["text"]))

        self.chunk_table.blockSignals(False)

        # Clear byte explorer when new transfer arrives
        self.byte_table.setRowCount(0)

    def _on_map_selection(self, index: int) -> None:
        """Triggered when user clicks a square in the health map grid."""
        if index < 0 or index >= len(self._current_chunks):
            self.byte_table.setRowCount(0)
            self.chunk_table.clearSelection()
            return

        # Sync chunk table selection
        self.chunk_table.blockSignals(True)
        self.chunk_table.selectRow(index)
        self.chunk_table.blockSignals(False)

        self._populate_byte_explorer(index)

    def _on_table_selection(self) -> None:
        """Triggered when user clicks a row in the chunk details table."""
        rows = self.chunk_table.selectedRanges()
        if not rows:
            self._health_map.select_chunk(-1)
            self.byte_table.setRowCount(0)
            return
        
        index = rows[0].topRow()
        self._health_map.select_chunk(index)
        self._populate_byte_explorer(index)

    def _populate_byte_explorer(self, index: int) -> None:
        """Populate the byte explorer table for the selected chunk."""
        if index < 0 or index >= len(self._current_chunks):
            self.byte_table.setRowCount(0)
            return

        chunk = self._current_chunks[index]
        data = chunk.received if chunk.received else chunk.expected
        
        self.byte_table.blockSignals(True)
        if self.byte_table.rowCount() != len(data):
            self.byte_table.setRowCount(len(data))

        for i, val in enumerate(data):
            # Offset
            offset_item = self.byte_table.item(i, 0)
            offset_txt = f"+0x{i:02X}"
            if offset_item is None:
                offset_item = QTableWidgetItem(offset_txt)
                offset_item.setForeground(QColor(COLORS["muted"]))
                self.byte_table.setItem(i, 0, offset_item)
            else:
                offset_item.setText(offset_txt)

            # Hex
            hex_item = self.byte_table.item(i, 1)
            hex_txt = f"0x{val:02X}"
            if hex_item is None:
                hex_item = QTableWidgetItem(hex_txt)
                hex_item.setFont(QFont("Cascadia Code, Courier New", 10))
                self.byte_table.setItem(i, 1, hex_item)
            else:
                hex_item.setText(hex_txt)

            # ASCII
            char = chr(val) if 32 <= val <= 126 else "."
            ascii_item = self.byte_table.item(i, 2)
            if ascii_item is None:
                ascii_item = QTableWidgetItem(char)
                self.byte_table.setItem(i, 2, ascii_item)
            else:
                ascii_item.setText(char)

            # Bit View
            bits = f"{val:08b}"
            bits_formatted = f"{bits[:4]} {bits[4:]}"
            bit_item = self.byte_table.item(i, 3)
            if bit_item is None:
                bit_item = QTableWidgetItem(bits_formatted)
                bit_item.setFont(QFont("Cascadia Code, Courier New", 10))
                bit_item.setForeground(QColor("#5CE65C"))
                self.byte_table.setItem(i, 3, bit_item)
            else:
                bit_item.setText(bits_formatted)

        self.byte_table.blockSignals(False)

    def _on_map_double_click(self, index: int) -> None:
        if 0 <= index < len(self._current_chunks):
            chunk = self._current_chunks[index]
            dialog = ByteComparisonDialog(chunk, self)
            dialog.exec()

    def _on_table_double_click(self, row: int, column: int) -> None:
        if 0 <= row < len(self._current_chunks):
            chunk = self._current_chunks[row]
            dialog = ByteComparisonDialog(chunk, self)
            dialog.exec()
