from __future__ import annotations
import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QHeaderView,
    QGridLayout,
)
from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.widgets import Card, muted_label, value_label, panel_header
from gui_dev_v3.theme import COLORS
from gui_dev_v3.logic.ber_bridge import parse_ber_test_name, generate_ber_test_payload, compare_payload_bits

class BERAnalyzerPage(QWidget):
    """Dedicated tab for comparing received files against reference files and analyzing BER."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_tid = -1
        self._last_chunk_count = -1
        self._last_expected_path = ""
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)

        # ── 1. Reference File Card ──
        self.ref_card = Card("Expected Reference File")
        ref_layout = QHBoxLayout()
        ref_layout.setContentsMargins(4, 4, 4, 4)
        ref_layout.setSpacing(12)

        self.ref_label = QLabel("No reference file loaded (Load under Inspect tab or use BERTEST file)")
        self.ref_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #8c99aa;")
        ref_layout.addWidget(self.ref_label, 1)

        self.ref_card.body.addLayout(ref_layout)
        layout.addWidget(self.ref_card)

        # ── 2. Statistics Card ──
        self.stats_card = Card("Quality & Bit Error Rate Analysis")
        stats_grid = QGridLayout()
        stats_grid.setSpacing(16)

        # Labels
        self.lbl_compared = value_label("—")
        self.lbl_bit_errors = value_label("—")
        self.lbl_ber = value_label("—")
        self.lbl_strict_ber = value_label("—")
        self.lbl_accuracy = value_label("—")
        self.lbl_delta = value_label("—")

        def add_stat_row(grid: QGridLayout, row: int, col: int, title: str, val_lbl: QLabel) -> None:
            title_lbl = QLabel(title.upper())
            title_lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #8c99aa;")
            grid.addWidget(title_lbl, row, col * 2)
            grid.addWidget(val_lbl, row, col * 2 + 1)

        add_stat_row(stats_grid, 0, 0, "Compared Bytes", self.lbl_compared)
        add_stat_row(stats_grid, 0, 1, "Bit Errors", self.lbl_bit_errors)
        add_stat_row(stats_grid, 0, 2, "Bit Error Rate (BER)", self.lbl_ber)
        add_stat_row(stats_grid, 1, 0, "Strict BER", self.lbl_strict_ber)
        add_stat_row(stats_grid, 1, 1, "Bit Accuracy", self.lbl_accuracy)
        add_stat_row(stats_grid, 1, 2, "Size Difference", self.lbl_delta)

        self.stats_card.body.addLayout(stats_grid)
        layout.addWidget(self.stats_card)

        # ── 3. Mismatch Preview Card ──
        self.mismatch_card = Card("Bit Mismatch Preview (First 50 errors)")
        self.mismatch_table = QTableWidget()
        self.mismatch_table.setColumnCount(4)
        self.mismatch_table.setHorizontalHeaderLabels(["Offset", "Expected (Hex)", "Received (Hex)", "Bit Errors"])
        self.mismatch_table.verticalHeader().setVisible(False)
        self.mismatch_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mismatch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.mismatch_table.setMinimumHeight(150)
        self.mismatch_card.body.addWidget(self.mismatch_table)
        layout.addWidget(self.mismatch_card, 1)

    def _get_state(self) -> RXAppState | None:
        parent = self.parent()
        while parent:
            if hasattr(parent, "state"):
                return parent.state
            parent = parent.parent()
        return None

    def refresh(self, state: RXAppState) -> None:
        # Dynamic check
        transfer = state.transfer
        expected_path = state.expected_file_path or ""
        
        # Build received bytes
        received_bytes = bytearray()
        for chunk in transfer.chunks:
            if chunk.received:
                received_bytes.extend(chunk.received)
            else:
                received_bytes.extend(b"\x00" * chunk.expected_size)
        received_bytes = bytes(received_bytes)

        # Get expected bytes
        expected_bytes = b""
        filename = transfer.filename or ""
        ber_params = parse_ber_test_name(filename)
        
        if ber_params:
            size, seed = ber_params
            expected_bytes = generate_ber_test_payload(size, seed)
            self.ref_label.setText(f"BERTEST Auto Mode: Generated seed {seed:08X} ({size} B)")
            self.ref_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #22c55e;")
        elif state.expected_file_data is not None:
            expected_bytes = state.expected_file_data
            self.ref_label.setText(f"Reference Loaded: {os.path.basename(expected_path)} ({len(expected_bytes)} B)")
            self.ref_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #22c55e;")
        else:
            self.ref_label.setText("No reference file loaded (Load under Inspect tab or use BERTEST file)")
            self.ref_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #8c99aa;")

        # Perform bit comparison if expected_bytes exists
        if expected_bytes:
            res = compare_payload_bits(expected_bytes, received_bytes, mismatch_limit=50)
            
            # Update labels
            self.lbl_compared.setText(f"{res['overlap_bytes']} / {res['expected_bytes']} B")
            self.lbl_bit_errors.setText(str(res["strict_bit_errors"]))
            self.lbl_ber.setText(f"{res['overlap_ber'] * 100:.6f} %")
            self.lbl_strict_ber.setText(f"{res['strict_ber'] * 100:.6f} %")
            self.lbl_accuracy.setText(f"{res['bit_accuracy'] * 100:.4f} %")
            
            delta = res["length_delta"]
            if delta > 0:
                self.lbl_delta.setText(f"+{delta} bytes (Extra)")
                self.lbl_delta.setStyleSheet(f"color: {COLORS['red']}; font-weight: 700;")
            elif delta < 0:
                self.lbl_delta.setText(f"{delta} bytes (Missing)")
                self.lbl_delta.setStyleSheet(f"color: {COLORS['red']}; font-weight: 700;")
            else:
                self.lbl_delta.setText("0 bytes (Exact length match)")
                self.lbl_delta.setStyleSheet(f"color: {COLORS['green']}; font-weight: 700;")

            # Populate Mismatch Table
            self.mismatch_table.setRowCount(len(res["preview"]))
            for i, p in enumerate(res["preview"]):
                offset_item = QTableWidgetItem(f"+0x{p['offset']:04X} ({p['offset']})")
                offset_item.setForeground(QColor(COLORS["muted"]))
                
                exp_val = p["expected"]
                exp_str = f"0x{exp_val:02X}" if isinstance(exp_val, int) else str(exp_val)
                rec_val = p["received"]
                rec_str = f"0x{rec_val:02X}" if isinstance(rec_val, int) else str(rec_val)
                
                exp_item = QTableWidgetItem(exp_str)
                rec_item = QTableWidgetItem(rec_str)
                err_item = QTableWidgetItem(f"{p['bit_errors']} bits")
                err_item.setForeground(QColor(COLORS["red"]))

                self.mismatch_table.setItem(i, 0, offset_item)
                self.mismatch_table.setItem(i, 1, exp_item)
                self.mismatch_table.setItem(i, 2, rec_item)
                self.mismatch_table.setItem(i, 3, err_item)
        else:
            # Reset labels to empty
            self.lbl_compared.setText("—")
            self.lbl_bit_errors.setText("—")
            self.lbl_ber.setText("—")
            self.lbl_strict_ber.setText("—")
            self.lbl_accuracy.setText("—")
            self.lbl_delta.setText("—")
            self.lbl_delta.setStyleSheet(f"color: {COLORS['text']};")
            self.mismatch_table.setRowCount(0)
