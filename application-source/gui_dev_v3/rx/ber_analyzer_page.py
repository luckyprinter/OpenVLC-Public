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
    QSizePolicy,
)
from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.widgets import Card, muted_label, value_label, panel_header
from gui_dev_v3.theme import COLORS

class BERAnalyzerPage(QWidget):
    """Dedicated tab for comparing received files against reference files and analyzing BER."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        self._main_layout = layout
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)
        self._compact_layout = False

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

        # Keep metric title/value pairs together so the grid can reflow
        # from three groups per row to two without recreating live labels.
        self._stats_grid = stats_grid
        self._stat_pairs: list[tuple[QLabel, QLabel]] = []
        self.lbl_compared = value_label("—")
        self.lbl_bit_errors = value_label("—")
        self.lbl_ber = value_label("—")
        self.lbl_strict_ber = value_label("—")
        self.lbl_accuracy = value_label("—")
        self.lbl_delta = value_label("—")
        for title, value in [
            ("Compared Bytes", self.lbl_compared),
            ("Bit Errors", self.lbl_bit_errors),
            ("Bit Error Rate (BER)", self.lbl_ber),
            ("Strict BER", self.lbl_strict_ber),
            ("Bit Accuracy", self.lbl_accuracy),
            ("Size Difference", self.lbl_delta),
        ]:
            title_label = QLabel(title.upper())
            title_label.setWordWrap(True)
            title_label.setMinimumWidth(0)
            title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            value.setMinimumWidth(0)
            value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            title_label.setStyleSheet("font-size: 9px; font-weight: 700; color: #8c99aa;")
            self._stat_pairs.append((title_label, value))
        self._reflow_stats(compact=False)

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
        self.mismatch_table.setMinimumWidth(0)
        self.mismatch_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.mismatch_card.body.addWidget(self.mismatch_table)
        layout.addWidget(self.mismatch_card, 1)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        """Reflow BER metrics and tighten page gutters on compact screens."""
        super().resizeEvent(event)
        compact = self.width() < 900 or self.height() < 620
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        self._main_layout.setContentsMargins(
            12 if compact else 20,
            12 if compact else 16,
            12 if compact else 20,
            12 if compact else 20,
        )
        self._reflow_stats(compact=compact)

    def _reflow_stats(self, compact: bool) -> None:
        columns = 2 if compact else 3
        for title_label, value_label_widget in self._stat_pairs:
            self._stats_grid.removeWidget(title_label)
            self._stats_grid.removeWidget(value_label_widget)
        for index, (title_label, value_label_widget) in enumerate(self._stat_pairs):
            row, group_column = divmod(index, columns)
            self._stats_grid.addWidget(title_label, row, group_column * 2)
            self._stats_grid.addWidget(value_label_widget, row, group_column * 2 + 1)

    def _get_state(self) -> RXAppState | None:
        parent = self.parent()
        while parent:
            if hasattr(parent, "state"):
                return parent.state
            parent = parent.parent()
        return None

    def refresh(self, state: RXAppState) -> None:
        """Show Method 2 BER from the selected original and reconstructed RX file.

        A valid CRC is a transport-integrity result, not a substitute for
        comparing the received file against the user's original reference.
        """
        transfer = state.transfer
        expected_path = state.expected_file_path or ""
        received_path = transfer.received_path or ""

        if not expected_path:
            self.ref_label.setText(
                "No original reference loaded. Use Inspect > Load Reference."
            )
            self.ref_label.setStyleSheet(
                "font-weight: 600; font-size: 12px; color: #8c99aa;"
            )
            self._reset_results()
            return

        self.ref_label.setText(f"Reference: {os.path.basename(expected_path)}")
        self.ref_label.setStyleSheet(
            "font-weight: 600; font-size: 12px; color: #22c55e;"
        )

        if not received_path:
            self._reset_results()
            self.lbl_compared.setText("Waiting for received file")
            self.lbl_ber.setText("Not measured")
            self.lbl_strict_ber.setText("Not measured")
            return

        result = state.get_method2_comparison()
        if result is None:
            self._reset_results()
            self.lbl_compared.setText("Comparison unavailable")
            self.lbl_ber.setText("Not measured")
            self.lbl_strict_ber.setText("Not measured")
            self.ref_label.setText(
                f"Reference: {os.path.basename(expected_path)} · "
                f"Received: {os.path.basename(received_path)} · comparison unavailable"
            )
            self.ref_label.setStyleSheet(
                f"font-weight: 600; font-size: 12px; color: {COLORS['red']};"
            )
            return

        self.lbl_compared.setText(
            f"{result['overlap_bytes']:,} / {result['expected_bytes']:,} B"
        )
        self.lbl_bit_errors.setText(f"{result['strict_bit_errors']:,}")
        self.lbl_ber.setText(
            f"{result['overlap_ber'] * 100:.6f} %" if result["overlap_ber"] is not None else "Not measurable"
        )
        self.lbl_strict_ber.setText(
            f"{result['strict_ber'] * 100:.6f} %" if result["strict_ber"] is not None else "Not measurable"
        )
        self.lbl_accuracy.setText(
            f"{result['bit_accuracy'] * 100:.4f} %" if result["bit_accuracy"] is not None else "Not measurable"
        )

        delta = result["length_delta"]
        if delta > 0:
            self.lbl_delta.setText(f"+{delta:,} bytes (Extra)")
            self.lbl_delta.setStyleSheet(
                f"color: {COLORS['red']}; font-weight: 700;"
            )
        elif delta < 0:
            self.lbl_delta.setText(f"{delta:,} bytes (Missing)")
            self.lbl_delta.setStyleSheet(
                f"color: {COLORS['red']}; font-weight: 700;"
            )
        else:
            self.lbl_delta.setText("0 bytes (Exact length match)")
            self.lbl_delta.setStyleSheet(
                f"color: {COLORS['green']}; font-weight: 700;"
            )

        preview = result["preview"]
        self.mismatch_table.setRowCount(len(preview))
        for row, mismatch in enumerate(preview):
            offset_item = QTableWidgetItem(
                f"+0x{mismatch['offset']:04X} ({mismatch['offset']:,})"
            )
            offset_item.setForeground(QColor(COLORS["muted"]))

            expected_value = mismatch["expected"]
            received_value = mismatch["received"]
            expected_text = (
                f"0x{expected_value:02X}"
                if isinstance(expected_value, int) else str(expected_value)
            )
            received_text = (
                f"0x{received_value:02X}"
                if isinstance(received_value, int) else str(received_value)
            )
            expected_item = QTableWidgetItem(expected_text)
            received_item = QTableWidgetItem(received_text)
            errors_item = QTableWidgetItem(f"{mismatch['bit_errors']:,} bits")
            errors_item.setForeground(QColor(COLORS["red"]))

            self.mismatch_table.setItem(row, 0, offset_item)
            self.mismatch_table.setItem(row, 1, expected_item)
            self.mismatch_table.setItem(row, 2, received_item)
            self.mismatch_table.setItem(row, 3, errors_item)

    def _reset_results(self) -> None:
        """Clear prior transfer metrics so stale BER is never shown."""
        for label in (
            self.lbl_compared,
            self.lbl_bit_errors,
            self.lbl_ber,
            self.lbl_strict_ber,
            self.lbl_accuracy,
            self.lbl_delta,
        ):
            label.setText("—")
        self.lbl_delta.setStyleSheet(f"color: {COLORS['text']};")
        self.mismatch_table.setRowCount(0)
