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
from gui_dev_v3.logic.ber_bridge import compare_files

class BERAnalyzerPage(QWidget):
    """Dedicated tab for comparing received files against reference files and analyzing BER."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_tid = -1
        self._last_chunk_count = -1
        self._last_expected_path = ""
        self._last_received_path = ""
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)

        # ── 1. Reference File Card ──
        self.ref_card = Card("Expected Reference File")
        ref_layout = QHBoxLayout()
        ref_layout.setContentsMargins(4, 4, 4, 4)
        ref_layout.setSpacing(12)

        self.ref_label = QLabel("Load the original reference file under Inspect to calculate Method 2 BER.")
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
        """Compare the saved original reference file with the reconstructed RX file."""
        transfer = state.transfer
        expected_path = state.expected_file_path or ""
        received_path = transfer.received_path or ""

        if (
            transfer.tid == self._last_tid
            and len(transfer.chunks) == self._last_chunk_count
            and expected_path == self._last_expected_path
            and received_path == self._last_received_path
        ):
            return

        self._last_tid = transfer.tid
        self._last_chunk_count = len(transfer.chunks)
        self._last_expected_path = expected_path
        self._last_received_path = received_path

        if not expected_path:
            self._show_unavailable("Load the original file under Inspect to calculate Method 2 BER.")
            return
        if not received_path:
            self._show_unavailable("No reconstructed receive file is available for this transfer yet.")
            return

        expected_file = os.path.abspath(expected_path)
        received_file = os.path.abspath(received_path)
        if not os.path.isfile(expected_file):
            self._show_unavailable("The selected original reference file is no longer available.")
            return
        if not os.path.isfile(received_file):
            self._show_unavailable("The reconstructed receive file could not be found.")
            return

        self.ref_label.setText(
            f"Method 2: {os.path.basename(expected_file)}  ↔  {os.path.basename(received_file)}"
        )
        self.ref_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #22c55e;")

        try:
            result = compare_files(expected_file, received_file, mismatch_limit=50)
        except (OSError, ValueError) as exc:
            self._show_unavailable(f"Method 2 comparison failed: {exc}")
            return

        self.lbl_compared.setText(
            f"{result['overlap_bytes']:,} / {result['expected_bytes']:,} B"
        )
        self.lbl_bit_errors.setText(f"{result['strict_bit_errors']:,}")
        self.lbl_ber.setText(f"{result['overlap_ber'] * 100:.6f} %")
        self.lbl_strict_ber.setText(f"{result['strict_ber'] * 100:.6f} %")
        self.lbl_accuracy.setText(f"{result['bit_accuracy'] * 100:.4f} %")

        delta = result["length_delta"]
        if delta > 0:
            self.lbl_delta.setText(f"+{delta:,} bytes (Extra)")
            self.lbl_delta.setStyleSheet(f"color: {COLORS['red']}; font-weight: 700;")
        elif delta < 0:
            self.lbl_delta.setText(f"{delta:,} bytes (Missing)")
            self.lbl_delta.setStyleSheet(f"color: {COLORS['red']}; font-weight: 700;")
        else:
            self.lbl_delta.setText("0 bytes (Exact length match)")
            self.lbl_delta.setStyleSheet(f"color: {COLORS['green']}; font-weight: 700;")

        self.mismatch_table.setRowCount(len(result["preview"]))
        for row, mismatch in enumerate(result["preview"]):
            offset_item = QTableWidgetItem(
                f"+0x{mismatch['offset']:04X} ({mismatch['offset']:,})"
            )
            offset_item.setForeground(QColor(COLORS["muted"]))
            expected = mismatch["expected"]
            received = mismatch["received"]
            expected_text = f"0x{expected:02X}" if isinstance(expected, int) else str(expected)
            received_text = f"0x{received:02X}" if isinstance(received, int) else str(received)
            expected_item = QTableWidgetItem(expected_text)
            received_item = QTableWidgetItem(received_text)
            errors_item = QTableWidgetItem(f"{mismatch['bit_errors']:,} bits")
            errors_item.setForeground(QColor(COLORS["red"]))
            self.mismatch_table.setItem(row, 0, offset_item)
            self.mismatch_table.setItem(row, 1, expected_item)
            self.mismatch_table.setItem(row, 2, received_item)
            self.mismatch_table.setItem(row, 3, errors_item)

    def _show_unavailable(self, message: str) -> None:
        self.ref_label.setText(message)
        self.ref_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #8c99aa;")
        for label in (
            self.lbl_compared, self.lbl_bit_errors, self.lbl_ber,
            self.lbl_strict_ber, self.lbl_accuracy, self.lbl_delta,
        ):
            label.setText("—")
        self.lbl_delta.setStyleSheet(f"color: {COLORS['text']};")
        self.mismatch_table.setRowCount(0)
