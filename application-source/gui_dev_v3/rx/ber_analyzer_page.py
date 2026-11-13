from __future__ import annotations
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
        self._comparison_key: tuple | None = None
        self._comparison_result: dict | None = None
        
        self._compact_layout = False
        self._stat_cells: list[tuple[QLabel, QLabel]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)

        # ── 1. Reference File Card ──
        self.ref_card = Card("Expected Reference File")
        ref_layout = QHBoxLayout()
        ref_layout.setContentsMargins(4, 4, 4, 4)
        ref_layout.setSpacing(12)

        self.ref_label = QLabel("No reference file loaded (select the original file under Inspect)")
        self.ref_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #8c99aa;")
        ref_layout.addWidget(self.ref_label, 1)

        self.ref_card.body.addLayout(ref_layout)
        layout.addWidget(self.ref_card)

        # ── 2. Statistics Card ──
        self.stats_card = Card("Quality & Bit Error Rate Analysis")
        stats_grid = QGridLayout()
        self._stats_grid = stats_grid
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
            self._stat_cells.append((title_lbl, val_lbl))

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

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        """Reflow metric pairs into two or three columns as space permits."""
        super().resizeEvent(event)
        compact = self.width() < 900 or self.height() < 620
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        columns = 2 if compact else 3
        self.mismatch_table.setHorizontalHeaderLabels(
            ["Offset", "Expected", "Received", "Errors"]
            if compact
            else ["Offset", "Expected (Hex)", "Received (Hex)", "Bit Errors"]
        )
        for index, (title_label, value_widget) in enumerate(self._stat_cells):
            self._stats_grid.removeWidget(title_label)
            self._stats_grid.removeWidget(value_widget)
            row = index // columns
            column = (index % columns) * 2
            self._stats_grid.addWidget(title_label, row, column)
            self._stats_grid.addWidget(value_widget, row, column + 1)

    def _get_state(self) -> RXAppState | None:
        parent = self.parent()
        while parent:
            if hasattr(parent, "state"):
                return parent.state
            parent = parent.parent()
        return None

    def refresh(self, state: RXAppState) -> None:
        """Show Method 2 only when both real files are available."""
        from pathlib import Path

        expected_path = Path(state.expected_file_path) if state.expected_file_path else None
        transfer = state.transfer
        received_path = Path(transfer.received_path) if transfer.received_path else None

        if expected_path and expected_path.is_file():
            try:
                expected_size = expected_path.stat().st_size
                self.ref_label.setText(
                    f"Reference loaded: {expected_path.name} ({expected_size:,} B)"
                )
                self.ref_label.setStyleSheet(
                    "font-weight: 600; font-size: 12px; color: #22c55e;"
                )
            except OSError:
                self.ref_label.setText("Reference file is unavailable")
                self.ref_label.setStyleSheet(
                    "font-weight: 600; font-size: 12px; color: #ef4444;"
                )
                expected_path = None
        else:
            self.ref_label.setText("Select the original file under Inspect to calculate Method 2 BER")
            self.ref_label.setStyleSheet(
                "font-weight: 600; font-size: 12px; color: #8c99aa;"
            )
            expected_path = None

        if not expected_path or not received_path or not received_path.is_file():
            self._comparison_key = None
            self._comparison_result = None
            self._clear_results()
            return

        try:
            expected_stat = expected_path.stat()
            received_stat = received_path.stat()
            comparison_key = (
                str(expected_path.resolve()), expected_stat.st_size, expected_stat.st_mtime_ns,
                str(received_path.resolve()), received_stat.st_size, received_stat.st_mtime_ns,
            )
            if comparison_key == self._comparison_key and self._comparison_result is not None:
                result = self._comparison_result
            else:
                result = compare_files(expected_path, received_path, mismatch_limit=50)
                self._comparison_key = comparison_key
                self._comparison_result = result
        except (OSError, ValueError) as exc:
            self._comparison_key = None
            self._comparison_result = None
            self._clear_results()
            self.lbl_ber.setText("Unavailable")
            self.ref_label.setText(f"Comparison unavailable: {str(exc)[:100]}")
            self.ref_label.setStyleSheet(
                "font-weight: 600; font-size: 12px; color: #ef4444;"
            )
            return

        # Store Method 2 on the matching completed capture. CRC status remains
        # independent and is never used to infer BER.
        state.set_method2_comparison(transfer.tid, result)

        self.lbl_compared.setText(
            f"{result['overlap_bytes']:,} / {result['expected_bytes']:,} B"
        )
        self.lbl_bit_errors.setText(f"{result['strict_bit_errors']:,}")
        overlap_ber = result["overlap_ber"]
        strict_ber = result["strict_ber"]
        accuracy = result["bit_accuracy"]
        self.lbl_ber.setText(
            f"{overlap_ber * 100:.6f} %" if overlap_ber is not None else "N/A"
        )
        self.lbl_strict_ber.setText(
            f"{strict_ber * 100:.6f} %" if strict_ber is not None else "N/A"
        )
        self.lbl_accuracy.setText(
            f"{accuracy * 100:.4f} %" if accuracy is not None else "N/A"
        )

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

        preview = result["preview"]
        self.mismatch_table.setRowCount(len(preview))
        for row, item in enumerate(preview):
            offset = item["offset"]
            exp_value = item["expected"]
            rec_value = item["received"]
            exp_text = f"0x{exp_value:02X}" if isinstance(exp_value, int) else str(exp_value)
            rec_text = f"0x{rec_value:02X}" if isinstance(rec_value, int) else str(rec_value)
            cells = (
                QTableWidgetItem(f"+0x{offset:04X} ({offset})"),
                QTableWidgetItem(exp_text),
                QTableWidgetItem(rec_text),
                QTableWidgetItem(f"{item['bit_errors']} bits"),
            )
            cells[0].setForeground(QColor(COLORS["muted"]))
            cells[3].setForeground(QColor(COLORS["red"]))
            for column, cell in enumerate(cells):
                self.mismatch_table.setItem(row, column, cell)

    def _clear_results(self) -> None:
        for label in (
            self.lbl_compared, self.lbl_bit_errors, self.lbl_ber,
            self.lbl_strict_ber, self.lbl_accuracy, self.lbl_delta,
        ):
            label.setText("—")
        self.lbl_delta.setStyleSheet(f"color: {COLORS['text']};")
        self.mismatch_table.setRowCount(0)
