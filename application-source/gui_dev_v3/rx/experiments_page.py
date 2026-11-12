"""Experiments page — create and manage VLC test experiments.

Matches Image 1 design: left panel with "New Experiment" form,
right panel with "Saved Experiments" table + action buttons.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QLayout,
    QDateTimeEdit,
    QHBoxLayout,
    QBoxLayout,
    QSizePolicy,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui_dev_v3.rx.experiment_store import (
    ExperimentStoreError,
    create_experiment,
    delete_experiment,
    list_experiments,
)
from gui_dev_v3.theme import COLORS
from gui_dev_v3.widgets import Card, DetailRow, panel_header, primary_button


EXPERIMENT_TYPES = [
    "Distance Test",
    "Ambient Light",
    "LED Wattage",
    "BER Test",
    "Payload Test",
    "Vref Sweep",
    "Custom",
]


class ExperimentsPage(QWidget):
    """Experiments management page — form + saved table (Image 1)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        layout = QVBoxLayout(self)
        self._main_layout = layout
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        # Build in the narrow-safe arrangement first. A horizontal two-panel
        # minimum width can otherwise prevent the widget from ever receiving
        # the resize event needed to enter compact mode.
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        self._compact_layout = True

        # Page title
        title = QLabel("EXPERIMENTS")
        title.setObjectName("SectionTitle")
        title.setStyleSheet("font-size: 18px;")
        layout.addWidget(title)

        # Two-panel body
        body = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self._body_layout = body
        body.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        body.setSpacing(12)
        layout.addLayout(body, 1)

        # ── Left Panel: New Experiment Form ──
        form_card = Card("New Experiment")
        form_card.setMinimumWidth(0)
        form_card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        form_card.body.setSpacing(14)
        body.addWidget(form_card, 2)  # ~40%

        self._exp_name = QLineEdit()
        self._exp_name.setPlaceholderText("e.g. Distance Test - Day 1")
        _add_form_row(form_card.body, "Experiment Name", self._exp_name)

        self._exp_type = QComboBox()
        self._exp_type.addItems(EXPERIMENT_TYPES)
        self._exp_type.setCurrentText("Distance Test")
        _add_form_row(form_card.body, "Experiment Type", self._exp_type)

        self._exp_date = QDateTimeEdit()
        self._exp_date.setCalendarPopup(True)
        self._exp_date.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        from datetime import datetime
        self._exp_date.setDateTime(datetime.now())
        _add_form_row(form_card.body, "Date", self._exp_date)

        notes_label = QLabel("Notes")
        notes_label.setObjectName("Muted")
        form_card.body.addWidget(notes_label)
        self._exp_notes = QPlainTextEdit()
        self._exp_notes.setPlaceholderText("Optional notes about this experiment...")
        self._exp_notes.setMinimumHeight(80)
        self._exp_notes.setMaximumHeight(140)
        self._exp_notes.setStyleSheet(
            f"background: {COLORS['panel_alt']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 6px; padding: 8px; color: {COLORS['text']};"
        )
        form_card.body.addWidget(self._exp_notes)

        form_card.body.addSpacing(8)

        create_btn = primary_button("+  Create Experiment")
        create_btn.setMinimumHeight(38)
        create_btn.clicked.connect(self._on_create)
        form_card.body.addWidget(create_btn)

        form_card.body.addStretch(1)

        # ── Right Panel: Saved Experiments Table ──
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        body.addLayout(right_col, 3)  # ~60%

        table_card = Card("Saved Experiments")
        table_card.setMinimumWidth(0)
        table_card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        table_card.body.setSpacing(8)
        right_col.addWidget(table_card, 1)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["ID", "Name", "Type", "Records"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(True)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 50)
        self._table.setColumnWidth(2, 140)
        self._table.setColumnWidth(3, 80)
        self._table.verticalHeader().setDefaultSectionSize(32)
        self._table.setSortingEnabled(True)
        self._table.setMinimumHeight(220)
        self._table.setMinimumWidth(0)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        self._empty_state = QLabel(
            "No experiments yet. Create your first experiment to organize test records."
        )
        self._empty_state.setWordWrap(True)
        self._empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_state.setMinimumHeight(100)
        self._empty_state.setObjectName("Muted")
        table_card.body.addWidget(self._empty_state)
        table_card.body.addWidget(self._table)

        # Action buttons row
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        table_card.body.addLayout(action_row)

        self._view_btn = QPushButton("  \U0001f441  View")
        self._edit_btn = QPushButton("  \u270f  Edit")
        self._delete_btn = QPushButton("  \U0001f5d1  Delete")
        for btn in (self._view_btn, self._edit_btn, self._delete_btn):
            btn.setMinimumHeight(34)
            btn.setEnabled(False)
            action_row.addWidget(btn)
        self._delete_btn.setObjectName("Danger")
        action_row.addStretch(1)

        self._view_btn.clicked.connect(self._on_view)
        self._edit_btn.clicked.connect(self._on_edit)
        self._delete_btn.clicked.connect(self._on_delete)

        # Search bar
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("  \U0001f50d  Search experiments...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search)
        table_card.body.addWidget(self._search_input)

        self._selected_id: int | None = None
        self._overlay: QWidget | None = None

        # Load data
        self._reload_table()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        """Stack experiment creation and saved records on compact workspaces."""
        super().resizeEvent(event)
        # Reserve the two-column form/table layout for genuinely roomy workspaces.
        # The available page width is smaller than the window after the shell rail,
        # and high-DPI scaling can further reduce the logical work area.
        compact = self.width() < 1100 or self.height() < 740
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        self._body_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if compact else QBoxLayout.Direction.LeftToRight
        )
        self._body_layout.setSpacing(12 if compact else 24)
        self._main_layout.setContentsMargins(
            12 if compact else 32,
            12 if compact else 28,
            12 if compact else 32,
            12 if compact else 28,
        )
        self._main_layout.setSpacing(12 if compact else 24)
        if self._overlay:
            self._overlay.setGeometry(self.rect())

    def _reload_table(self, filter_text: str = "") -> None:
        all_experiments = list_experiments()
        experiments = all_experiments
        if filter_text:
            ft = filter_text.lower()
            experiments = [e for e in all_experiments if ft in e.name.lower() or ft in e.type.lower()]

        if not experiments:
            self._empty_state.setText(
                "No experiments match your search."
                if all_experiments
                else "No experiments yet. Create your first experiment to organize test records."
            )
        self._empty_state.setVisible(not experiments)
        self._table.setVisible(bool(experiments))
        self._table.setRowCount(len(experiments))
        for row, exp in enumerate(experiments):
            self._table.setItem(row, 0, QTableWidgetItem(str(exp.id)))
            self._table.setItem(row, 1, QTableWidgetItem(exp.name))
            self._table.setItem(row, 2, QTableWidgetItem(exp.type))
            self._table.setItem(row, 3, QTableWidgetItem(str(exp.record_count)))

            for col in range(4):
                item = self._table.item(row, col)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        self._table.resizeRowsToContents()
        self._on_selection_changed()

    def _on_create(self) -> None:
        name = self._exp_name.text().strip()
        if not name:
            self._exp_name.setFocus()
            return
        exp_type = self._exp_type.currentText()
        notes = self._exp_notes.toPlainText().strip()
        try:
            create_experiment(name, exp_type, notes)
        except ExperimentStoreError as exc:
            QMessageBox.warning(
                self,
                "Experiment data unavailable",
                f"Existing experiment data was not changed. {exc}",
            )
            return

        self._exp_name.clear()
        from datetime import datetime
        self._exp_date.setDateTime(datetime.now())
        self._exp_notes.clear()
        self._reload_table()

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if rows:
            row = rows[0].row()
            item = self._table.item(row, 0)
            self._selected_id = int(item.text()) if item else None
        else:
            self._selected_id = None
        enabled = self._selected_id is not None
        for btn in (self._view_btn, self._edit_btn, self._delete_btn):
            btn.setEnabled(enabled)

    def _on_view(self) -> None:
        if self._selected_id is None:
            return
        for exp in list_experiments():
            if exp.id == self._selected_id:
                self._show_detail_card(exp)
                return

    def _show_detail_card(self, exp) -> None:
        """Show experiment details in a floating overlay."""
        card = Card(f"Experiment #{exp.id}")
        card.body.addWidget(DetailRow("Name", exp.name))
        card.body.addWidget(DetailRow("Type", exp.type))
        card.body.addWidget(DetailRow("Created", exp.created_at))
        card.body.addWidget(DetailRow("Records", str(exp.record_count)))
        if exp.notes:
            card.body.addWidget(DetailRow("Notes", exp.notes))
        close_btn = QPushButton("Close")
        close_btn.setObjectName("Primary")
        close_btn.clicked.connect(lambda: self._remove_overlay(card))
        card.body.addWidget(close_btn)

        overlay = QWidget(self)
        overlay.setObjectName("Card")
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(24, 24, 24, 24)
        overlay_layout.addWidget(card)
        overlay_layout.addStretch(1)
        overlay.setStyleSheet(
            "background: rgba(0,0,0,0.6); border: none; border-radius: 8px;"
        )
        overlay.setGeometry(self.rect())
        overlay.raise_()
        overlay.show()
        self._overlay = overlay

    def _remove_overlay(self, _card=None) -> None:
        if self._overlay:
            self._overlay.hide()
            self._overlay.deleteLater()
            self._overlay = None

    def _on_edit(self) -> None:
        if self._selected_id is None:
            return
        for exp in list_experiments():
            if exp.id == self._selected_id:
                self._exp_name.setText(exp.name)
                idx = self._exp_type.findText(exp.type)
                if idx >= 0:
                    self._exp_type.setCurrentIndex(idx)
                from datetime import datetime
                try:
                    dt = datetime.strptime(exp.created_at, "%Y-%m-%d %H:%M:%S")
                    self._exp_date.setDateTime(dt)
                except ValueError:
                    pass
                self._exp_notes.setPlainText(exp.notes)
                return

    def _on_delete(self) -> None:
        if self._selected_id is not None:
            delete_experiment(self._selected_id)
            self._selected_id = None
            self._reload_table()

    def _on_search(self, text: str) -> None:
        self._reload_table(text)



def _add_form_row(layout, label: str, widget) -> None:
    lbl = QLabel(label)
    lbl.setObjectName("Muted")
    layout.addWidget(lbl)
    layout.addWidget(widget)
