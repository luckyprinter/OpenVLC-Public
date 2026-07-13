"""Table Builder page — configure columns and preview generated data tables.

Image 2: Table Builder — available/selected/manual column picker.
Image 3: Generated Table Preview — data table with export actions.
"""

from __future__ import annotations

import csv
import io
import math
import random
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui_dev_v3.rx.experiment_store import AVAILABLE_CATEGORIES, MANUAL_COLUMNS
from gui_dev_v3.theme import COLORS
from gui_dev_v3.widgets import Card, muted_label, panel_header, primary_button

VLC_PAPER_TEMPLATES = {
    "Adaptive Calibration": {
        "table_name": "Adaptive Calibration Results",
        "rows": 4,
        "available": ["PV0 (V)", "Vref (V)", "Receiver Margin (V)", "Calibration Status"],
        "manual": ["trial_col"]
    },
    "Distance Performance": {
        "table_name": "Distance Performance Evaluation",
        "rows": 4,
        "available": ["Receiver Margin (V)", "BER (%)", "CRC (Pass/Fail)"],
        "manual": ["horizontal_offset", "optical_distance"]
    },
    "Ambient Light Performance": {
        "table_name": "Ambient Light Performance Evaluation",
        "rows": 4,
        "available": ["PV0 (V)", "Vref (V)", "Receiver Margin (V)", "BER (%)", "CRC (Pass/Fail)", "Reconstruction Result"],
        "manual": ["lux_level"]
    },
    "LED Wattage": {
        "table_name": "LED Wattage Impact Study",
        "rows": 3,
        "available": ["PV0 (V)", "Vref (V)", "Receiver Margin (V)", "BER (%)", "CRC (Pass/Fail)", "Reconstruction Result"],
        "manual": ["led_wattage"]
    },
    "Flicker Comfort": {
        "table_name": "Flicker Comfort Rating",
        "rows": 3,
        "available": [],
        "manual": ["led_wattage", "viewing_distance", "flicker_observed", "glare_observed", "comfort_rating", "notes_col"]
    },
    "Payload Performance": {
        "table_name": "Payload Transmission Performance",
        "rows": 4,
        "available": ["File Category", "File Type / Ext", "File Size (KiB)", "Number of Chunks", "Total Transfer Time (s)", "BER (%)", "CRC (Pass/Fail)", "Reconstruction Result"],
        "manual": []
    },
    "Ambient Light test matrix": {
        "table_name": "Ambient Light Test Matrix",
        "rows": 3,
        "available": ["PV0 (V)", "Vref (V)", "Receiver Margin (V)", "CRC (Pass/Fail)", "Reconstruction Result"],
        "manual": ["test_id", "ambient_condition", "lux_level", "lux_tool", "distance_m", "alignment"]
    },
    "Batch Transfer limits": {
        "table_name": "File Batch Limits Evaluation",
        "rows": 3,
        "available": ["File Type / Ext", "File Size (KiB)", "Transfer Path", "Expected Behavior", "CRC (Pass/Fail)", "Reconstruction Result"],
        "manual": ["test_id"]
    },
    "Sensor Comparison": {
        "table_name": "Sensor Comparison Results",
        "rows": 2,
        "available": ["Receiver Sensor", "Front End", "File Name", "PV0 (V)", "Vref (V)", "CRC (Pass/Fail)", "Reconstruction Result"],
        "manual": ["test_id", "distance_m", "alignment"]
    }
}


class TableBuilderPage(QWidget):
    """Table Builder with two stacked views: builder (Image 2) and preview (Image 3)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stack = QVBoxLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(0)

        self._builder_view = self._build_builder_view()
        self._preview_view = self._build_preview_view()

        self._stack.addWidget(self._builder_view)
        self._stack.addWidget(self._preview_view)
        self._preview_view.hide()

        self._selected_keys: list[str] = []
        self._table_name = "Distance Test Results"
        self._row_count = 10

    # ──────────────────────────────────────────────
    # Builder View (Image 2)
    # ──────────────────────────────────────────────

    def _build_builder_view(self) -> QWidget:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        title = QLabel("TABLE BUILDER")
        title.setObjectName("SectionTitle")
        title.setStyleSheet("font-size: 18px;")
        layout.addWidget(title)

        # Top row: Table Name + Rows + Template
        top_row = QHBoxLayout()
        top_row.setSpacing(20)
        layout.addLayout(top_row)

        name_label = QLabel("Table Name")
        name_label.setObjectName("Muted")
        top_row.addWidget(name_label)
        self._name_input = QLineEdit("Distance Test Results")
        self._name_input.setMinimumWidth(240)
        top_row.addWidget(self._name_input)

        rows_label = QLabel("Rows")
        rows_label.setObjectName("Muted")
        top_row.addWidget(rows_label)
        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(1, 100)
        self._rows_spin.setValue(10)
        self._rows_spin.setFixedWidth(80)
        top_row.addWidget(self._rows_spin)

        template_label = QLabel("Test Template")
        template_label.setObjectName("Muted")
        top_row.addWidget(template_label)
        self._template_combo = QComboBox()
        self._template_combo.setMinimumWidth(200)
        self._template_combo.addItem("Custom (No Template)")
        for tname in VLC_PAPER_TEMPLATES.keys():
            self._template_combo.addItem(tname)
        self._template_combo.currentTextChanged.connect(self._on_template_selected)
        top_row.addWidget(self._template_combo)

        top_row.addStretch(1)

        # Three-column body
        three_col = QHBoxLayout()
        three_col.setSpacing(16)
        layout.addLayout(three_col, 1)

        # ── Left: Available Columns (category tree) ──
        left_card = Card("Available Columns")
        three_col.addWidget(left_card, 1)

        # Search for available columns
        self._avail_search = QLineEdit()
        self._avail_search.setPlaceholderText("  \U0001f50d  Search columns...")
        self._avail_search.textChanged.connect(self._filter_available)
        left_card.body.addWidget(self._avail_search)

        self._avail_list = QListWidget()
        self._avail_list.setAlternatingRowColors(False)
        self._avail_list.setSpacing(1)
        self._avail_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_card.body.addWidget(self._avail_list, 1)

        # ── Arrow buttons ──
        arrow_col = QVBoxLayout()
        arrow_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow_col.setSpacing(8)
        three_col.addLayout(arrow_col)

        self._add_btn = QPushButton("\u2192")
        self._add_btn.setFixedSize(36, 36)
        self._add_btn.clicked.connect(self._add_selected)
        arrow_col.addWidget(self._add_btn)

        self._remove_btn = QPushButton("\u2190")
        self._remove_btn.setFixedSize(36, 36)
        self._remove_btn.clicked.connect(self._remove_selected)
        arrow_col.addWidget(self._remove_btn)

        # ── Center: Selected Columns ──
        center_card = Card("Selected Columns (Drag to Reorder)")
        three_col.addWidget(center_card, 1)

        self._selected_list = QListWidget()
        self._selected_list.setAlternatingRowColors(False)
        self._selected_list.setSpacing(2)
        self._selected_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._selected_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        center_card.body.addWidget(self._selected_list, 1)

        selected_hint = QLabel("Drag items to reorder")
        selected_hint.setObjectName("Muted")
        selected_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selected_hint.setStyleSheet("font-size: 10px; background: transparent;")
        center_card.body.addWidget(selected_hint)

        # ── Right: Manual Input Columns (draggable reorder) ──
        right_card = Card("Manual Input Columns (Drag to Reorder)")
        three_col.addWidget(right_card, 1)

        self._manual_list = QListWidget()
        self._manual_list.setAlternatingRowColors(False)
        self._manual_list.setSpacing(2)
        self._manual_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._manual_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._manual_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._manual_list.itemChanged.connect(self._on_manual_toggle)

        for key, label, checked in MANUAL_COLUMNS:
            item = QListWidgetItem(f"  {label}")
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self._manual_list.addItem(item)

        right_card.body.addWidget(self._manual_list, 1)
        manual_hint = QLabel("Drag to reorder • Check to include")
        manual_hint.setObjectName("Muted")
        manual_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        manual_hint.setStyleSheet("font-size: 10px; background: transparent;")
        right_card.body.addWidget(manual_hint)

        # ── Bottom buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        layout.addLayout(btn_row)

        preview_btn = QPushButton("  \U0001f50d  Preview Table")
        preview_btn.setMinimumHeight(38)
        preview_btn.setStyleSheet(
            f"background: {COLORS.get('purple', '#7c3aed')}; color: white; "
            f"border: none; border-radius: 6px; font-weight: 700; padding: 8px 20px;"
        )
        preview_btn.clicked.connect(self._on_preview)
        btn_row.addWidget(preview_btn)

        generate_btn = QPushButton("  \u2699  Generate Table")
        generate_btn.setMinimumHeight(38)
        generate_btn.setObjectName("Primary")
        generate_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(generate_btn)

        btn_row.addStretch(1)

        self._build_available_list()

        # Connect model signals for drag-and-drop / structural modifications to columns
        self._selected_list.model().layoutChanged.connect(self._on_selected_list_changed)
        self._selected_list.model().rowsInserted.connect(self._on_selected_list_changed)
        self._selected_list.model().rowsRemoved.connect(self._on_selected_list_changed)
        self._selected_list.model().rowsMoved.connect(self._on_selected_list_changed)

        self._manual_list.model().layoutChanged.connect(self._on_manual_list_changed)
        self._manual_list.model().rowsInserted.connect(self._on_manual_list_changed)
        self._manual_list.model().rowsRemoved.connect(self._on_manual_list_changed)
        self._manual_list.model().rowsMoved.connect(self._on_manual_list_changed)

        return outer

    def _build_available_list(self) -> None:
        self._avail_list.clear()
        for category, columns in AVAILABLE_CATEGORIES:
            # Category header item (non-selectable)
            cat_item = QListWidgetItem(f"  \u25bc  {category}")
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            cat_item.setForeground(Qt.GlobalColor.cyan)
            font = cat_item.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() - 1)
            cat_item.setFont(font)
            self._avail_list.addItem(cat_item)

            for key, label in columns:
                item = QListWidgetItem(f"    {label}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setData(Qt.ItemDataRole.UserRole + 1, category)
                self._avail_list.addItem(item)

    def _filter_available(self, text: str) -> None:
        for i in range(self._avail_list.count()):
            item = self._avail_list.item(i)
            if not item:
                continue
            # Always show category headers
            if not (item.flags() & Qt.ItemFlag.ItemIsSelectable):
                item.setHidden(False)
            elif not text:
                item.setHidden(False)
            else:
                item.setHidden(text.lower() not in item.text().lower())

    def _add_selected(self) -> None:
        current = self._avail_list.currentItem()
        if not current or not (current.flags() & Qt.ItemFlag.ItemIsSelectable):
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        label = current.text().strip()
        if key and label not in self._selected_keys:
            self._selected_keys.append(label)
            self._rebuild_selected()

    def _remove_selected(self) -> None:
        current = self._selected_list.currentItem()
        if not current:
            return
        label = current.text().strip()
        self._selected_keys = [k for k in self._selected_keys if k != label]
        self._rebuild_selected()

    def _rebuild_selected(self) -> None:
        self._selected_list.clear()
        for label in self._selected_keys:
            item = QListWidgetItem(f"  {label}")
            item.setData(Qt.ItemDataRole.UserRole, label)
            self._selected_list.addItem(item)

    def _on_manual_toggle(self, item: QListWidgetItem | None = None) -> None:
        """Called when any manual column checkbox changes or items are reordered."""
        self._on_manual_list_changed()

    def _on_selected_list_changed(self, *args: Any) -> None:
        if getattr(self, "_populating_template", False):
            return

        # Sync self._selected_keys with actual items in self._selected_list
        keys = []
        for i in range(self._selected_list.count()):
            item = self._selected_list.item(i)
            if item:
                keys.append(item.text().strip())
        self._selected_keys = keys

        self._template_combo.blockSignals(True)
        self._template_combo.setCurrentText("Custom (No Template)")
        self._template_combo.blockSignals(False)

    def _on_manual_list_changed(self, *args: Any) -> None:
        if getattr(self, "_populating_template", False):
            return
        self._template_combo.blockSignals(True)
        self._template_combo.setCurrentText("Custom (No Template)")
        self._template_combo.blockSignals(False)

    def _on_template_selected(self, template_name: str) -> None:
        if template_name not in VLC_PAPER_TEMPLATES:
            return

        template = VLC_PAPER_TEMPLATES[template_name]

        # Use _populating_template flag to prevent resetting combo to Custom
        self._populating_template = True

        self._name_input.blockSignals(True)
        self._rows_spin.blockSignals(True)
        self._manual_list.blockSignals(True)

        self._name_input.setText(template["table_name"])
        self._rows_spin.setValue(template["rows"])

        # Rebuild selected columns (Available)
        self._selected_keys = list(template["available"])
        self._rebuild_selected()

        # Re-order and toggle manual columns
        from gui_dev_v3.rx.experiment_store import MANUAL_COLUMNS as MC
        mc_dict = {key: label for key, label, _ in MC}

        self._manual_list.clear()

        # First add template's manual keys (checked)
        for key in template["manual"]:
            if key in mc_dict:
                item = QListWidgetItem(f"  {mc_dict[key]}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self._manual_list.addItem(item)

        # Then add remaining manual keys (unchecked)
        for key, label, _ in MC:
            if key not in template["manual"]:
                item = QListWidgetItem(f"  {label}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self._manual_list.addItem(item)

        self._name_input.blockSignals(False)
        self._rows_spin.blockSignals(False)
        self._manual_list.blockSignals(False)

        self._populating_template = False

    # ──────────────────────────────────────────────
    # Preview View (Image 3)
    # ──────────────────────────────────────────────

    def _build_preview_view(self) -> QWidget:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title_row = QHBoxLayout()
        layout.addLayout(title_row)

        self._preview_title = QLabel("GENERATED TABLE PREVIEW")
        self._preview_title.setObjectName("SectionTitle")
        self._preview_title.setStyleSheet("font-size: 18px;")
        title_row.addWidget(self._preview_title)

        title_row.addStretch(1)

        back_btn = QPushButton("  \u2190  Back to Builder")
        back_btn.clicked.connect(self._show_builder)
        back_btn.setMinimumHeight(32)
        title_row.addWidget(back_btn)

        # Scrollable table area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(scroll, 1)

        self._preview_table = QTableWidget(0, 0)
        self._preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._preview_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._preview_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._preview_table.verticalHeader().setVisible(False)
        self._preview_table.setAlternatingRowColors(False)
        self._preview_table.setShowGrid(True)
        scroll.setWidget(self._preview_table)

        # Export buttons row
        export_row = QHBoxLayout()
        export_row.setSpacing(12)
        layout.addLayout(export_row)

        csv_btn = QPushButton("  \U0001f4c4  Export CSV")
        csv_btn.setMinimumHeight(36)
        csv_btn.clicked.connect(self._export_csv)
        export_row.addWidget(csv_btn)

        xls_btn = QPushButton("  \U0001f4ca  Export Excel")
        xls_btn.setMinimumHeight(36)
        xls_btn.clicked.connect(self._export_excel)
        export_row.addWidget(xls_btn)

        copy_btn = QPushButton("  \U0001f4cb  Copy Table")
        copy_btn.setMinimumHeight(36)
        copy_btn.clicked.connect(self._copy_table)
        export_row.addWidget(copy_btn)

        save_btn = QPushButton("  \U0001f4be  Save Template")
        save_btn.setMinimumHeight(36)
        save_btn.clicked.connect(self._save_template)
        export_row.addWidget(save_btn)

        export_row.addStretch(1)

        return outer

    # ──────────────────────────────────────────────
    # View switching
    # ──────────────────────────────────────────────

    def _show_builder(self) -> None:
        self._preview_view.hide()
        self._builder_view.show()

    def _show_preview(self) -> None:
        self._builder_view.hide()
        self._preview_view.show()

    def _on_preview(self) -> None:
        """Preview with mock data — relies on selected columns."""
        if not self._selected_keys:
            return
        self._generate_table_data(preview=True)

    def _on_generate(self) -> None:
        if not self._selected_keys:
            return
        self._generate_table_data(preview=False)

    def _get_column_keys(self) -> list[str]:
        """Return the full ordered list of column keys for the table."""
        keys: list[str] = []

        # Map display names to data keys
        display_to_key: dict[str, str] = {}
        for cat, cols in AVAILABLE_CATEGORIES:
            for key, label in cols:
                display_to_key[label] = key

        for disp in self._selected_keys:
            key = display_to_key.get(disp, disp)
            keys.append(key)

        # Add checked manual columns in user-defined order
        for i in range(self._manual_list.count()):
            item = self._manual_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                key = item.data(Qt.ItemDataRole.UserRole)
                if key:
                    keys.append(key)

        return keys

    def _get_column_labels(self) -> list[str]:
        """Return display labels for the table header."""
        labels: list[str] = []

        for disp in self._selected_keys:
            labels.append(disp)

        # Manual columns in user-defined order
        for i in range(self._manual_list.count()):
            item = self._manual_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                # Strip leading spaces from display text
                labels.append(item.text().strip())

        return labels

    def _generate_table_data(self, preview: bool = True) -> None:
        """Generate mock data matching the experiment pattern from Image 3."""
        keys = self._get_column_keys()
        labels = self._get_column_labels()
        n_rows = self._rows_spin.value()

        # Build realistic mock data
        rows: list[list[str]] = []
        for i in range(n_rows):
            dist = 1.0 + i * 0.5  # 1.0, 1.5, 2.0, ...
            row: list[str] = []
            for key in keys:
                val = self._compute_mock_value(key, dist, i, n_rows)
                row.append(val)
            rows.append(row)

        self._preview_title.setText(
            f"GENERATED TABLE PREVIEW — {self._name_input.text()}"
        )

        # Build table
        column_count = len(labels)
        self._preview_table.setColumnCount(column_count)
        self._preview_table.setHorizontalHeaderLabels(labels)
        self._preview_table.setRowCount(n_rows)

        for r, row_data in enumerate(rows):
            for c, val in enumerate(row_data):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                      if c > 0 else Qt.AlignmentFlag.AlignLeft)
                self._preview_table.setItem(r, c, item)

        # Auto-fit all columns — content-aware with proportional stretch
        header = self._preview_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        # Give last column a minimum stretch so table fills the view
        if column_count > 1:
            for c in range(column_count):
                if self._preview_table.columnWidth(c) < 60:
                    self._preview_table.setColumnWidth(c, 60)
        self._preview_table.setMinimumWidth(600)

        self._show_preview()

    def _compute_mock_value(self, key: str, dist: float, row: int, total: int) -> str:
        """Generate realistic VLC test data for a given column key."""
        template = self._template_combo.currentText()

        # Handle specific template mock data if a standard template is selected
        if template == "Adaptive Calibration":
            pvos = [0.81, 1.24, 1.78, 2.35]
            vrefs = [0.45, 0.88, 1.42, 1.99]
            idx = row % len(pvos)
            if key == "trial_col":
                return str(row + 1)
            if key == "pvo":
                return f"{pvos[idx]:.2f}"
            if key == "vref":
                return f"{vrefs[idx]:.2f}"
            if key == "margin":
                return f"{pvos[idx] - vrefs[idx]:.2f}"
            if key == "calibration_status":
                return "Success"

        elif template == "Distance Performance":
            offsets = [0.0, 0.5, 1.0, 1.5]
            opt_dists = [2.10, 2.16, 2.33, 2.58]
            margins = [0.36, 0.37, 0.35, 0.34]
            idx = row % len(offsets)
            if key == "trial_col":
                return str(row + 1)
            if key == "horizontal_offset":
                return f"{offsets[idx]:.1f}"
            if key == "optical_distance":
                return f"{opt_dists[idx]:.2f}"
            if key == "margin":
                return f"{margins[idx]:.2f}"
            if key == "ber":
                return "0.00"
            if key == "crc_status":
                return "PASS"

        elif template == "Ambient Light Performance":
            luxes = [120, 250, 420, 650]
            pvos = [1.82, 2.07, 2.33, 2.61]
            vrefs = [1.46, 1.71, 1.97, 2.25]
            idx = row % len(luxes)
            if key == "trial_col":
                return str(row + 1)
            if key == "lux_level":
                return str(luxes[idx])
            if key == "pvo":
                return f"{pvos[idx]:.2f}"
            if key == "vref":
                return f"{vrefs[idx]:.2f}"
            if key == "margin":
                return f"{pvos[idx] - vrefs[idx]:.2f}"
            if key == "ber":
                return "0.00"
            if key == "crc_status":
                return "PASS"
            if key == "reconstruction_result":
                return "Complete"

        elif template == "LED Wattage":
            wattages = ["6W", "9W", "12W"]
            pvos = [1.98, 2.24, 2.55]
            vrefs = [1.62, 1.88, 2.19]
            idx = row % len(wattages)
            if key == "trial_col":
                return str(row + 1)
            if key == "led_wattage":
                return wattages[idx]
            if key == "pvo":
                return f"{pvos[idx]:.2f}"
            if key == "vref":
                return f"{vrefs[idx]:.2f}"
            if key == "margin":
                return f"{pvos[idx] - vrefs[idx]:.2f}"
            if key == "ber":
                return "0.00"
            if key == "crc_status":
                return "PASS"
            if key == "reconstruction_result":
                return "Complete"

        elif template == "Flicker Comfort":
            wattages = ["6W", "9W", "12W"]
            notes = [
                "Dim but stable; visible flicker during transmission",
                "Moderate brightness; visible flicker during transmission",
                "Brightest setting; visible flicker during transmission"
            ]
            idx = row % len(wattages)
            if key == "led_wattage":
                return wattages[idx]
            if key == "viewing_distance":
                return "1.5"
            if key == "flicker_observed":
                return "Yes"
            if key == "glare_observed":
                return "No"
            if key == "comfort_rating":
                return "Tolerable"
            if key == "notes_col":
                return notes[idx]

        elif template == "Payload Performance":
            categories = ["Text Document", "Image", "Audio", "Engineering Design File"]
            types = ["TXT", "JPG", "WAV", "FZPZ"]
            sizes = [5.00, 45.59, 15.94, 7.48]
            chunks = [20, 183, 64, 30]
            times = [9, 86, 31, 14]
            idx = row % len(categories)
            if key == "file_category":
                return categories[idx]
            if key == "file_type":
                return types[idx]
            if key == "file_size":
                return f"{sizes[idx]:.2f}"
            if key == "chunks_count":
                return str(chunks[idx])
            if key == "transfer_time":
                return str(times[idx])
            if key == "ber":
                return "0.00"
            if key == "crc_status":
                return "PASS"
            if key == "reconstruction_result":
                return "Complete"

        elif template == "Ambient Light test matrix":
            conditions = ["Dim room", "Normal room light", "TV/unstable nearby light"]
            luxes = [120, 250, 420]
            pvos = [1.82, 2.07, 2.33]
            vrefs = [1.46, 1.71, 1.97]
            idx = row % len(conditions)
            if key == "test_id":
                return f"A{row + 1}"
            if key == "ambient_condition":
                return conditions[idx]
            if key == "lux_level":
                return str(luxes[idx])
            if key == "lux_tool":
                return "UT383BT Lux Meter"
            if key == "distance_m":
                return "2.10"
            if key == "alignment":
                return "Perfect Alignment"
            if key == "pvo":
                return f"{pvos[idx]:.2f}"
            if key == "vref":
                return f"{vrefs[idx]:.2f}"
            if key == "margin":
                return f"{pvos[idx] - vrefs[idx]:.2f}"
            if key == "crc_status":
                return "PASS"
            if key == "reconstruction_result":
                return "Complete"

        elif template == "Batch Transfer limits":
            exts = ["txt", "png", "zip"]
            sizes = ["75 KiB", "120 KiB", "150 KiB"]
            paths = ["direct stream", "direct firmware stream", "GUI batched transfer"]
            behaviors = [
                "accepted by ESP32 RAM buffer",
                "rejected or file too large",
                "split into 80 KiB VLCB1 parts"
            ]
            crcs = ["PASS", "FAIL", "PASS"]
            statuses = ["Complete", "Failed", "Complete"]
            idx = row % len(exts)
            if key == "test_id":
                return f"M{row + 1}"
            if key == "file_type":
                return exts[idx]
            if key == "file_size":
                return sizes[idx]
            if key == "transfer_path":
                return paths[idx]
            if key == "expected_behavior":
                return behaviors[idx]
            if key == "crc_status":
                return crcs[idx]
            if key == "reconstruction_result":
                return statuses[idx]

        elif template == "Sensor Comparison":
            sensors = ["BPW34 photodiode", "Phototransistor"]
            front_ends = ["OPA2604 TIA + LM393", "Transistor Pre-amp"]
            pvos = [2.35, 3.10]
            vrefs = [1.99, 2.50]
            idx = row % len(sensors)
            if key == "test_id":
                return f"S{row + 1}"
            if key == "receiver_sensor":
                return sensors[idx]
            if key == "front_end":
                return front_ends[idx]
            if key == "file_name":
                return "thesis.pdf (24.81 KB)"
            if key == "distance_m":
                return "2.10"
            if key == "alignment":
                return "Perfect Alignment"
            if key == "pvo":
                return f"{pvos[idx]:.2f}"
            if key == "vref":
                return f"{vrefs[idx]:.2f}"
            if key == "crc_status":
                return "PASS"
            if key == "reconstruction_result":
                return "Complete"

        # Fallback to general/default formula-based mock values
        if key == "distance_m":
            return f"{dist:.2f}"
        if key == "optical_distance":
            od = math.sqrt(dist * dist + 2.1 * 2.1)
            return f"{od:.2f}"
        if key == "height_m":
            return "2.10"
        if key == "led_wattage":
            return "12"
        if key == "lux_level":
            return f"{random.randint(200, 900)}"
        if key == "horizontal_offset":
            return f"{max(0.0, dist - 1.0):.2f}"
        if key == "notes_col":
            return "" if row % 3 else "Good LOS"

        # Auto columns from available list
        if key == "file_name":
            names = ["thesis.pdf", "report.txt", "image.png", "audio.wav"]
            return names[row % len(names)]
        if key == "file_size":
            sizes = [24.81, 5.0, 45.59, 15.94, 92.01, 18.6, 7.48, 120.5, 33.2, 68.4]
            return f"{sizes[row % len(sizes)]:.2f}"
        if key == "transfer_time":
            t = 9 + dist * 8
            return f"{t:.1f}"
        if key == "data_rate":
            rate = 7132 / (1 + dist * 0.15)
            return f"{rate:.0f}"
        if key == "ber":
            ber = 0.00001 * math.pow(10, dist * 0.4)
            return f"{ber:.4f}"
        if key == "strict_ber":
            ber = 0.00002 * math.pow(10, dist * 0.35)
            return f"{ber:.4f}"
        if key == "bit_errors":
            return str(int(dist * random.randint(1, 10)))
        if key == "crc_status":
            return "PASS" if dist < 4.0 else "FAIL"
        if key == "chunk_completion":
            completion = 100.0 - max(0, (dist - 1.0) * 4.5)
            return f"{completion:.2f}"
        if key == "pvo":
            pvo = 2.89 - (dist - 1.0) * 0.175
            return f"{pvo:.3f}"
        if key == "vref":
            vref = 2.53 - (dist - 1.0) * 0.16
            return f"{vref:.3f}"
        if key == "margin":
            margin = 0.36 - (dist - 1.0) * 0.028
            return f"{margin:.3f}"

        return "—"

    # ──────────────────────────────────────────────
    # Export actions
    # ──────────────────────────────────────────────

    def _export_csv(self) -> None:
        """Copy CSV to clipboard (simplified export)."""
        text = self._table_to_csv()
        cb = QApplication.clipboard()
        if cb:
            cb.setText(text)
        self._show_toast("CSV copied to clipboard")

    def _export_excel(self) -> None:
        """Copy TSV (Excel-compatible) to clipboard."""
        rows = self._preview_table.rowCount()
        cols = self._preview_table.columnCount()
        lines: list[str] = []
        # Header
        headers = [self._preview_table.horizontalHeaderItem(c).text()
                   for c in range(cols)]
        lines.append("\t".join(headers))
        for r in range(rows):
            vals = [self._preview_table.item(r, c).text() if self._preview_table.item(r, c) else ""
                    for c in range(cols)]
            lines.append("\t".join(vals))
        text = "\n".join(lines)
        cb = QApplication.clipboard()
        if cb:
            cb.setText(text)
        self._show_toast("Excel data copied to clipboard")

    def _copy_table(self) -> None:
        """Copy markdown-formatted table to clipboard."""
        rows = self._preview_table.rowCount()
        cols = self._preview_table.columnCount()
        lines: list[str] = []

        headers = [self._preview_table.horizontalHeaderItem(c).text()
                   for c in range(cols)]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join("---" for _ in headers) + "|")

        for r in range(rows):
            vals = [self._preview_table.item(r, c).text() if self._preview_table.item(r, c) else ""
                    for c in range(cols)]
            lines.append("| " + " | ".join(vals) + " |")

        cb = QApplication.clipboard()
        if cb:
            cb.setText("\n".join(lines))
        self._show_toast("Table copied as Markdown")

    def _save_template(self) -> None:
        self._show_toast("Template saved")

    def _table_to_csv(self) -> str:
        rows = self._preview_table.rowCount()
        cols = self._preview_table.columnCount()
        output = io.StringIO()
        writer = csv.writer(output)
        headers = [self._preview_table.horizontalHeaderItem(c).text()
                   for c in range(cols)]
        writer.writerow(headers)
        for r in range(rows):
            vals = [self._preview_table.item(r, c).text() if self._preview_table.item(r, c) else ""
                    for c in range(cols)]
            writer.writerow(vals)
        return output.getvalue()

    def _show_toast(self, msg: str) -> None:
        """Show a temporary toast notification."""
        from PySide6.QtWidgets import QLabel
        toast = QLabel(msg, self)
        toast.setObjectName("Toast")
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.setStyleSheet(
            f"background: {COLORS['panel']}; color: {COLORS['text']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 8px; "
            f"padding: 10px 20px; font-weight: 700;"
        )
        toast.adjustSize()
        toast.move((self.width() - toast.width()) // 2, 20)
        toast.show()
        QTimer.singleShot(2000, toast.deleteLater)
