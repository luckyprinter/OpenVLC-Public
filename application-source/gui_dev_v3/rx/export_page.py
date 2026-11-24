"""Export Page — Transfer history logs, file actions, and database backup management matching Keysight styles."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QPlainTextEdit,
    QSizePolicy,
)

from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.models import SessionCapture, TransferRecord, TransferStatus
from gui_dev_v3.theme import COLORS
from gui_dev_v3.widgets import Card, DetailRow, panel_header, scrollable, value_label
from gui_dev_v3.data.records import load_session_capture
from gui_dev_v3.rx import experiment_store
from gui_dev_v3.rx.receiver_storage import (
    HISTORY_FILENAME,
    RESTORE_JOURNAL,
    STATE_LOCK_NAME,
    ReceiverStorageError,
    lock_state,
    read_rows,
    restore_json,
    write_json,
)


def _resolve_history_dir() -> Path:
    """Resolve export history to the application-owned state directory."""
    env = os.getenv("VLC_DATA_DIR")
    if env:
        return Path(env).expanduser() / "state"
    return Path(__file__).resolve().parents[2] / "state"


HISTORY_DIR = _resolve_history_dir()
HISTORY_PATH = HISTORY_DIR / HISTORY_FILENAME
LEGACY_HISTORY_PATH = Path.home() / ".vlc_rx" / HISTORY_FILENAME


def _validate_history(data: object) -> list[dict]:
    """Accept legacy rows with omitted display fields and validate fields used by Export."""
    if not isinstance(data, list):
        raise ReceiverStorageError("Transfer history must be a list")
    for row in data:
        if not isinstance(row, dict) or type(row.get("tid")) is not int:
            raise ReceiverStorageError("Transfer history contains an invalid TID")
        for key in ("filename", "status", "time_label"):
            if key in row and not isinstance(row[key], str):
                raise ReceiverStorageError(f"Transfer history contains an invalid {key}")
        for key in ("size_bytes", "total_chunks", "received_chunks", "received_bytes"):
            value = row.get(key)
            if value is not None and (type(value) is not int or not 0 <= value <= sys.maxsize):
                raise ReceiverStorageError(f"Transfer history contains an invalid {key}")
        for key in ("received_path", "capture_id", "ber_method"):
            value = row.get(key)
            if value is not None and not isinstance(value, str):
                raise ReceiverStorageError(f"Transfer history contains an invalid {key}")
        for key in ("ber", "duration_seconds"):
            value = row.get(key)
            if key == "ber" and value == "N/A":
                continue
            if value is not None and (
                type(value) not in (int, float) or not 0 <= value <= sys.maxsize
                or not math.isfinite(value)
            ):
                raise ReceiverStorageError(f"Transfer history contains an invalid {key}")
    return data


def _read_history() -> list[dict]:
    return read_rows(HISTORY_PATH, LEGACY_HISTORY_PATH, _validate_history)


def _recovery_message(copies: tuple[Path, ...]) -> str:
    if not copies:
        return ""
    return "\n\nPrevious data was saved to:\n" + "\n".join(str(copy) for copy in copies)


class SessionInspectorCard(Card):
    """Inspector for saved telemetry trends, OOK capture data, and protocol logs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Session Inspector", parent)
        
        # Stacked layout to toggle between Empty state and detail view
        self.stacked = QStackedWidget()
        self.body.addWidget(self.stacked)

        # ── 1. Empty State Widget ──
        self.empty_widget = QWidget()
        empty_lo = QVBoxLayout(self.empty_widget)
        empty_lo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lo.setSpacing(12)

        import qtawesome as qta
        self.empty_icon = QLabel()
        self.empty_icon.setPixmap(qta.icon("fa5s.chart-line", color="#3A4D6B").pixmap(64, 64))
        self.empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lo.addWidget(self.empty_icon)

        self.empty_title = QLabel("Select a Transfer Log")
        self.empty_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF;")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lo.addWidget(self.empty_title)

        self.empty_desc = QLabel(
            "Select an entry from the history list to review saved PVo/Vref/margin "
            "telemetry and protocol events. Raw OOK samples are shown only when "
            "the firmware has actually captured them."
        )
        self.empty_desc.setStyleSheet("font-size: 12px; color: #8C99AA;")
        self.empty_desc.setWordWrap(True)
        self.empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_desc.setMaximumWidth(300)
        empty_lo.addWidget(self.empty_desc)

        self.stacked.addWidget(self.empty_widget)

        # ── 2. Detailed Session View ──
        self.detail_widget = QWidget()
        detail_lo = QVBoxLayout(self.detail_widget)
        detail_lo.setContentsMargins(0, 0, 0, 0)
        detail_lo.setSpacing(8)

        # Tab Widget
        self.tabs = QTabWidget()
        detail_lo.addWidget(self.tabs)
        self.stacked.addWidget(self.detail_widget)

        # ── Tab 1: Summary ──
        self.summary_tab = QWidget()
        self.summary_lo = QVBoxLayout(self.summary_tab)
        self.summary_lo.setContentsMargins(16, 16, 16, 16)
        self.summary_lo.setSpacing(12)
        
        self.info_group = Card("Transfer Summary")
        self.info_group.body.setSpacing(8)
        self.summary_lo.addWidget(self.info_group)
        
        self.summary_lo.addStretch(1)
        self.tabs.addTab(self.summary_tab, "Summary")

        # ── Tab 2: Waveforms ──
        self.waveform_tab = QWidget()
        self.waveform_lo = QVBoxLayout(self.waveform_tab)
        self.waveform_lo.setContentsMargins(8, 8, 8, 8)
        self.waveform_lo.setSpacing(8)

        from gui_dev_v3.rx.signal_widgets import SignalWaveform
        self.signal_waveform = SignalWaveform()
        self.signal_waveform.setMinimumHeight(280)

        self.waveform_lo.addWidget(self.signal_waveform, 1)

        self.tabs.addTab(self.waveform_tab, "Telemetry Trend")

        # ── Tab 3: OOK Capture Data ──
        self.ook_data_tab = QWidget()
        self.ook_data_lo = QVBoxLayout(self.ook_data_tab)
        self.ook_data_lo.setContentsMargins(12, 12, 12, 12)
        
        self.ook_data_text = QPlainTextEdit()
        self.ook_data_text.setReadOnly(True)
        self.ook_data_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.ook_data_text.setStyleSheet("""
            QPlainTextEdit {
                background-color: #06090F;
                border: 1px solid #1A3152;
                border-radius: 6px;
                font-family: monospace;
                font-size: 11px;
                color: #00E5FF;
                padding: 10px;
            }
        """)
        self.ook_data_lo.addWidget(self.ook_data_text)
        self.tabs.addTab(self.ook_data_tab, "OOK Capture Data")

        # ── Tab 4: Protocol Logs ──
        self.protocol_tab = QWidget()
        self.protocol_lo = QVBoxLayout(self.protocol_tab)
        self.protocol_lo.setContentsMargins(12, 12, 12, 12)

        self.protocol_table = QTableWidget(0, 3)
        self.protocol_table.setHorizontalHeaderLabels(["Time", "Event", "Details"])
        self.protocol_table.verticalHeader().setVisible(False)
        self.protocol_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.protocol_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.protocol_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.protocol_table.horizontalHeader().setStretchLastSection(True)
        self.protocol_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.protocol_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.protocol_table.setStyleSheet("""
            QTableWidget {
                background-color: #0B1625;
                gridline-color: #1A3152;
                border: 1px solid #1A3152;
                color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #0F1B2D;
                color: #8C99AA;
                padding: 6px;
                border: 1px solid #1A3152;
                font-weight: bold;
            }
        """)
        self.protocol_lo.addWidget(self.protocol_table)
        self.tabs.addTab(self.protocol_tab, "Protocol Logs")

        # Start in empty state
        self.show_empty()

    def show_empty(self) -> None:
        self.empty_title.setText("Select a Transfer Log")
        self.empty_desc.setText(
            "Select an entry from the history list to review saved PVo/Vref/margin "
            "telemetry and protocol events. Raw OOK samples are shown only when "
            "the firmware has actually captured them."
        )
        self.stacked.setCurrentIndex(0)

    def show_unavailable(self, filename: str) -> None:
        """Explain when an older transfer has no saved physical capture."""
        self.empty_title.setText("Capture Not Available")
        self.empty_desc.setText(
            f"No physical capture was saved for {filename}. The transfer record "
            "remains available, but telemetry trends, raw OOK samples, and protocol "
            "events are not invented or presented as hardware measurements."
        )
        self.stacked.setCurrentIndex(0)

    def show_capture(self, capture: SessionCapture, entry: dict) -> None:
        self.stacked.setCurrentIndex(1)

        # Clear existing info group items
        for i in reversed(range(self.info_group.body.count())):
            item = self.info_group.body.itemAt(i)
            if item.widget() and item.widget().objectName() != "SectionTitle":
                item.widget().deleteLater()

        # Update Summary tab
        status = getattr(capture, "status", None) or entry.get("status", "Complete")
        color_map = {
            "Complete": COLORS["green"],
            "CRC Failed": COLORS["red"],
            "Incomplete": COLORS["amber"],
            "Stalled": COLORS["muted"],
        }
        status_color = color_map.get(status, "#FFFFFF")

        self.info_group.body.addWidget(DetailRow("TID", f"{capture.tid:04d}"))
        self.info_group.body.addWidget(DetailRow("Filename", capture.filename))
        self.info_group.body.addWidget(DetailRow("Status", status, value_color=status_color))
        self.info_group.body.addWidget(DetailRow("Timestamp", capture.timestamp))
        
        size = entry.get("size_bytes")
        size_txt = (
            "Unavailable" if size is None else
            f"{size:,} Bytes" if size < 1024 else
            f"{size / 1024:.2f} KiB ({size:,} Bytes)"
        )
        self.info_group.body.addWidget(DetailRow("File Size", size_txt))
        if getattr(capture, "capture_id", None):
            received = getattr(capture, "received_bytes", None)
            duration = getattr(capture, "duration_seconds", None)
            self.info_group.body.addWidget(DetailRow(
                "Delivered File Bytes", "Unavailable" if received is None else f"{received:,} Bytes",
            ))
            self.info_group.body.addWidget(DetailRow(
                "Host Receive Duration", "Unavailable" if duration is None else f"{duration:.3f} s",
            ))
        rate = capture.throughput_kbps
        self.info_group.body.addWidget(DetailRow(
            "Throughput", "Unavailable" if rate is None else f"{rate:.2f} kbps",
        ))
        self.info_group.body.addWidget(DetailRow(
            "Method 2 Bit Error Rate",
            f"{capture.ber:.4%}" if capture.ber is not None else "Not measured — no reference comparison",
        ))
        self.info_group.body.addWidget(DetailRow("CRC Status", capture.crc_status, value_color=status_color))

        # Replay only the voltage telemetry actually saved in the capture.
        self.signal_waveform.set_playback_mode(True, capture)

        # Older releases stored low-rate PVo>Vref decisions in ook_bits. Those
        # values are retained for data compatibility but are not symbol-rate
        # OOK samples, so label them explicitly instead of calling them bits.
        if capture.ook_bits:
            legacy_text = (
                "Legacy threshold-state samples from low-rate PVo/Vref telemetry. "
                "These are NOT decoded symbol-rate OOK bits.\n\n"
            )
            bit_values = "".join(str(bit) for bit in capture.ook_bits)
            grouped = " ".join(
                bit_values[index:index + 8]
                for index in range(0, len(bit_values), 8)
            )
            self.ook_data_text.setPlainText(legacy_text + grouped)
        else:
            self.ook_data_text.setPlainText(
                "Raw comparator/bit samples are not available in this capture. "
                "The current firmware does not stream symbol-rate OOK samples."
            )

        # Update Protocol Logs table
        self.protocol_table.setRowCount(len(capture.protocol_events))
        for row, evt in enumerate(capture.protocol_events):
            t_val = evt.get("time", 0.0)
            t_item = QTableWidgetItem(f"{t_val:.3f} s" if isinstance(t_val, (int, float)) else str(t_val))
            t_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t_item.setForeground(QColor("#FFFFFF"))
            self.protocol_table.setItem(row, 0, t_item)

            evt_item = QTableWidgetItem(evt.get("event", "—"))
            evt_item.setForeground(QColor(COLORS["accent"]))
            evt_item.setFont(QFont("Inter", 10, QFont.Bold))
            self.protocol_table.setItem(row, 1, evt_item)

            det_item = QTableWidgetItem(evt.get("details", ""))
            det_item.setForeground(QColor("#FFFFFF"))
            self.protocol_table.setItem(row, 2, det_item)


class ExportPage(QWidget):
    """Modern VLC Receiver history and data export page."""

    experiments_restored = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history_data: list[dict] = []
        self._pending_history: dict[tuple[int, str | None], TransferRecord] = {}
        self._history_corrupt = False
        self._history_write_error = None
        self._load_history()
        # Page layout
        lo = QVBoxLayout(self)
        self._main_layout = lo
        lo.setContentsMargins(20, 16, 20, 20)
        lo.setSpacing(12)
        # Keep the scrollable page at the splitter's current minimum, including
        # when it changes orientation after the scroll area was laid out.
        lo.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self._compact_layout = False

        # Create horizontal splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                image: none;
                background: transparent;
            }
        """)

        # Left Column Widget
        left_widget = QWidget()
        left_lo = QVBoxLayout(left_widget)
        left_lo.setContentsMargins(0, 0, 0, 0)
        left_lo.setSpacing(12)

        # ── 1. Export Folder Card ──
        folder_card = Card("Export Directory")
        folder_lo = QHBoxLayout()
        folder_lo.setSpacing(6)

        self._folder_edit = QLineEdit(str(HISTORY_DIR / "exports"))
        self._folder_edit.setReadOnly(True)
        self._folder_edit.setCursorPosition(0)
        self._folder_edit.setToolTip(self._folder_edit.text())
        self._folder_edit.setStyleSheet(
            f"QLineEdit {{ background: {COLORS['panel_alt']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 6px; padding: 6px 10px; color: {COLORS['text']}; }}"
        )
        folder_lo.addWidget(self._folder_edit, 1)

        browse_btn = QPushButton("Browse")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._on_browse_folder)
        folder_lo.addWidget(browse_btn)

        open_dir_btn = QPushButton("Open Folder")
        open_dir_btn.setObjectName("Primary")
        open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_dir_btn.clicked.connect(self._on_open_folder)
        folder_lo.addWidget(open_dir_btn)

        folder_card.body.addLayout(folder_lo)
        left_lo.addWidget(folder_card)

        # ── 2. Transfer History Card ──
        self.history_card = Card("Transfer Logs History")
        
        # Header actions row
        hdr_actions = QHBoxLayout()
        hdr_actions.addStretch(1)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._on_refresh_history)
        hdr_actions.addWidget(refresh_btn)
        
        clear_btn = QPushButton("Clear Logs")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._on_clear_logs)
        hdr_actions.addWidget(clear_btn)
        self.history_card.body.addLayout(hdr_actions)

        # The Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "TID", "Filename", "Status", "Date / Time", "Size", "Chunks", "BER"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        # Column sizing: TID fixed, Filename stretches, rest fit content
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)        # TID
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)      # Filename
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Status
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Date/Time
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Size
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Chunks
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # BER
        self.table.setColumnWidth(0, 55)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setSortingEnabled(True)
        self.table.setMinimumHeight(144)
        self.table.setMinimumWidth(0)
        self._history_empty_state = QLabel(
            "No transfer history yet. Completed or failed sessions will appear here."
        )
        self._history_empty_state.setWordWrap(True)
        self._history_empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._history_empty_state.setObjectName("Muted")
        self.history_card.body.addWidget(self._history_empty_state)
        self.history_card.body.addWidget(self.table, 1)

        # Actions below the table
        act_row = QHBoxLayout()
        self.open_file_btn = QPushButton("Open File")
        self.open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_file_btn.setEnabled(False)
        self.open_file_btn.clicked.connect(self._on_open_file)
        act_row.addWidget(self.open_file_btn)

        self.save_as_btn = QPushButton("Save As...")
        self.save_as_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_as_btn.setEnabled(False)
        self.save_as_btn.clicked.connect(self._on_save_as)
        act_row.addWidget(self.save_as_btn)
        act_row.addStretch(1)

        self.history_card.body.addLayout(act_row)
        left_lo.addWidget(self.history_card, 1)

        # Connect selection changed
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        # ── 3. Database Management Card ──
        db_card = Card("Database Storage Operations")
        db_lo = QHBoxLayout()
        self._database_actions = db_lo
        self._database_actions_stacked = False
        db_lo.setSpacing(10)

        # Outlined ghost-style secondary buttons
        self.backup_btn = self._ghost_btn("Backup DB", "fa5s.database")
        self.backup_btn.clicked.connect(self._on_backup_db)
        db_lo.addWidget(self.backup_btn)

        self.restore_btn = self._ghost_btn("Restore DB", "fa5s.upload")
        self.restore_btn.clicked.connect(self._on_restore_db)
        db_lo.addWidget(self.restore_btn)

        self.csv_btn = self._ghost_btn("Export CSV", "fa5s.file-csv")
        self.csv_btn.clicked.connect(self._on_export_csv)
        db_lo.addWidget(self.csv_btn)

        db_card.body.addLayout(db_lo)
        left_lo.addWidget(db_card)

        self.splitter.addWidget(left_widget)

        # Right Column Widget: Session Inspector
        self.inspector_card = SessionInspectorCard()
        self.splitter.addWidget(self.inspector_card)
        for index in range(self.splitter.count()):
            child = self.splitter.widget(index)
            child.setMinimumWidth(0)
            child.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

        # Set splitter ratio/sizes (e.g., 55% left, 45% right)
        self.splitter.setSizes([620, 580])

        lo.addWidget(self.splitter)

        # Build initial table rows
        self._populate_table()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        """Stack history and session inspection on compact workspaces."""
        super().resizeEvent(event)
        compact = self.width() < 1060
        stack_buttons = self.width() < 440
        if stack_buttons != self._database_actions_stacked:
            self._database_actions_stacked = stack_buttons
            self._database_actions.setDirection(
                QBoxLayout.Direction.TopToBottom if stack_buttons else QBoxLayout.Direction.LeftToRight
            )
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        self.splitter.setOrientation(
            Qt.Orientation.Vertical if compact else Qt.Orientation.Horizontal
        )
        self._main_layout.setContentsMargins(
            12 if compact else 20,
            12 if compact else 16,
            12 if compact else 20,
            12 if compact else 20,
        )
        self.table.setMinimumHeight(112 if compact else 144)
        self.splitter.setSizes([420, 360] if compact else [620, 580])

    def _ghost_btn(self, text: str, icon_name: str) -> QPushButton:
        import qtawesome as qta
        btn = QPushButton(qta.icon(icon_name, color="#708090"), f"  {text}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"    background: transparent;"
            f"    border: 1px solid {COLORS['border']};"
            f"    color: #AAB7C5;"
            f"    border-radius: 6px;"
            f"    padding: 8px 16px;"
            f"    font-size: 11px;"
            f"    font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{"
            f"    border-color: {COLORS['accent']};"
            f"    color: #FFFFFF;"
            f"}}"
        )
        return btn

    def _load_history(self) -> None:
        try:
            with lock_state(HISTORY_PATH.parent):
                self._history_data = _read_history()
        except ReceiverStorageError:
            self._history_corrupt = True
        else:
            self._history_corrupt = False
            self._history_write_error = None

    def _populate_table(self) -> None:
        if self._history_corrupt:
            self._history_empty_state.setText(
                "History could not be read. Existing data was preserved."
            )
        elif self._history_write_error:
            self._history_empty_state.setText(self._history_write_error)
        else:
            self._history_empty_state.setText(
                "No transfer history yet. Completed or failed sessions will appear here."
            )
        self._history_empty_state.setVisible(
            self._history_corrupt or self._history_write_error is not None or not self._history_data
        )
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._history_data))
        for row, entry in enumerate(self._history_data):
            # TID
            tid_item = QTableWidgetItem(f"{entry['tid']:04d}")
            tid_item.setData(Qt.ItemDataRole.UserRole, row)
            tid_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tid_item.setForeground(QColor(COLORS["muted"]))
            self.table.setItem(row, 0, tid_item)

            # Filename
            file_item = QTableWidgetItem(entry.get("filename", "—"))
            file_item.setForeground(QColor("#FFFFFF"))
            self.table.setItem(row, 1, file_item)

            # Status
            status = entry.get("status", "Complete")
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color_map = {
                "Complete": COLORS["green"],
                "CRC Failed": COLORS["red"],
                "Incomplete": COLORS["amber"],
                "Stalled": COLORS["muted"],
            }
            status_item.setForeground(QColor(color_map.get(status, "#FFFFFF")))
            status_item.setFont(QFont("Inter", 10, QFont.Bold))
            self.table.setItem(row, 2, status_item)

            # Time
            time_item = QTableWidgetItem(entry.get("time_label", "—"))
            self.table.setItem(row, 3, time_item)

            # Size
            size = entry.get("size_bytes")
            size_txt = "—" if size is None else f"{size:,} B" if size < 1024 else f"{size / 1024:.1f} KiB"
            size_item = QTableWidgetItem(size_txt)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, size_item)

            # Chunks
            rx = entry.get("received_chunks")
            tot = entry.get("total_chunks")
            chunks_item = QTableWidgetItem("—" if rx is None or tot is None else f"{rx} / {tot}")
            chunks_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, chunks_item)

            # BER
            ber = entry.get("ber")
            ber_is_measured = (
                entry.get("ber_method") == "method2_reference_file"
                and isinstance(ber, (int, float))
            )
            ber_txt = f"{ber:.4%}" if ber_is_measured else "N/A"
            ber_item = QTableWidgetItem(ber_txt)
            ber_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if ber_is_measured and ber > 0:
                ber_item.setForeground(QColor(COLORS["red"]))
            self.table.setItem(row, 6, ber_item)

        self.table.setSortingEnabled(sorting)
        self.table.clearSelection()
        self._on_selection_changed()

    def refresh(self, state: RXAppState) -> None:
        """Persist newly completed physical transfers and later Method 2 comparisons."""
        if state.mode != "physical":
            return
        transfer = state.transfer
        for finished in getattr(state, "completed_physical_transfers", ()):
            self._pending_history[finished.tid, finished.capture_id] = finished
        completed = list(self._pending_history.values())
        if transfer.tid > 0 and transfer.status != TransferStatus.PENDING:
            # Legacy backends exposed only the current transfer. Modern
            # captures enter history only after their terminal event.
            if getattr(transfer, "capture_id", None) is None:
                completed.append(transfer)
            comparison = state.get_method2_comparison()
        else:
            comparison = None
        if not completed and comparison is None:
            return
        # Merge the snapshot twice only when it actually changes this page. The
        # locked merge starts with the latest disk rows from other RX processes.
        current_rows = [dict(row) for row in self._history_data]
        self._merge_transfers(current_rows, completed, transfer, comparison)
        if current_rows == self._history_data:
            self._pending_history.clear()
            return
        try:
            with lock_state(HISTORY_PATH.parent):
                rows = _read_history()
                self._merge_transfers(rows, completed, transfer, comparison)
                write_json(HISTORY_PATH, _validate_history(rows))
        except (OSError, ValueError, ReceiverStorageError):
            if self._history_write_error is None:
                self._history_write_error = "New history could not be saved. Check receiver data storage."
                self._populate_table()
            return
        self._history_data = rows
        self._pending_history.clear()
        self._history_corrupt = False
        self._history_write_error = None
        self._populate_table()

    @staticmethod
    def _find_transfer_row(rows: list[dict], transfer: TransferRecord) -> dict | None:
        capture_id = getattr(transfer, "capture_id", None)
        return next(
            (
                row for row in rows
                if row["tid"] == transfer.tid and row.get("capture_id") == capture_id
            ),
            None,
        )

    @classmethod
    def _merge_transfers(
        cls,
        rows: list[dict],
        completed: list[TransferRecord],
        current: TransferRecord,
        comparison: dict | None,
    ) -> None:
        for transfer in completed:
            entry = cls._find_transfer_row(rows, transfer)
            if entry is None:
                entry = {
                    "tid": transfer.tid,
                    "capture_id": getattr(transfer, "capture_id", None),
                    "ber": "N/A",
                    "ber_method": None,
                }
                rows.insert(0, entry)
            entry.update(
                filename=transfer.filename,
                status=transfer.status.value,
                time_label=transfer.time_label,
                size_bytes=transfer.size_bytes,
                total_chunks=transfer.total_chunks,
                received_chunks=transfer.received_chunks,
            )
            for field in ("received_path", "received_bytes", "duration_seconds"):
                value = getattr(transfer, field, None)
                if value is not None:
                    entry[field] = value

        if comparison is not None and (entry := cls._find_transfer_row(rows, current)) is not None:
            ber = comparison.get("strict_ber")
            entry.update(
                ber=ber if ber is not None else "N/A",
                ber_method="method2_reference_file",
            )

    def _on_selection_changed(self) -> None:
        selected = bool(self.table.selectedItems())
        self.open_file_btn.setEnabled(selected)
        self.save_as_btn.setEnabled(selected)

        if not selected:
            self.inspector_card.show_empty()
            return

        entry = self._get_selected_entry()
        if not entry:
            self.inspector_card.show_empty()
            return

        tid = entry.get("tid", 0)
        capture_id = entry.get("capture_id")
        capture = load_session_capture(tid, capture_id=capture_id)
        if capture is not None:
            self.inspector_card.show_capture(capture, entry)
        else:
            self.inspector_card.show_unavailable(str(entry.get("filename") or "this transfer"))

    def _on_browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Export Directory", self._folder_edit.text())
        if path:
            self._folder_edit.setText(path)
            self._folder_edit.setCursorPosition(0)
            self._folder_edit.setToolTip(path)

    def _on_open_folder(self) -> None:
        folder = self._folder_edit.text()
        Path(folder).mkdir(parents=True, exist_ok=True)
        import subprocess
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    def _on_refresh_history(self) -> None:
        self._load_history()
        self._populate_table()

    def _on_clear_logs(self) -> None:
        ret = QMessageBox.question(
            self, "Clear Logs", "Are you sure you want to delete all transfer logs?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            try:
                with lock_state(HISTORY_PATH.parent):
                    restore_json({HISTORY_PATH: []})
            except ReceiverStorageError as exc:
                QMessageBox.warning(self, "Clear Logs Failed", str(exc))
                return
            self._history_data = []
            self._pending_history.clear()
            self._history_corrupt = False
            self._history_write_error = None
            self._populate_table()

    def _get_selected_entry(self) -> dict | None:
        selected = self.table.selectedRanges()
        if not selected:
            return None
        item = self.table.item(selected[0].topRow(), 0)
        index = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(index, int) and 0 <= index < len(self._history_data):
            return self._history_data[index]
        return None

    def _received_file_path(self, entry: dict) -> Path | None:
        raw_path = entry.get("received_path")
        if not raw_path:
            return None
        try:
            path = Path(str(raw_path)).expanduser()
            return path if path.is_file() else None
        except OSError:
            return None

    def _on_open_file(self) -> None:
        entry = self._get_selected_entry()
        if not entry:
            return

        source = self._received_file_path(entry)
        if source is None:
            QMessageBox.warning(
                self,
                "Received File Unavailable",
                "The original received payload is not available for this history entry.",
            )
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(source.resolve()))):
            QMessageBox.warning(
                self, "Open File Failed",
                f"Could not open the received file:\n{source}",
            )

    def _on_save_as(self) -> None:
        entry = self._get_selected_entry()
        if not entry:
            return

        source = self._received_file_path(entry)
        if source is None:
            QMessageBox.warning(
                self,
                "Received File Unavailable",
                "The original received payload is not available for this history entry.",
            )
            return

        filename = entry.get("filename") or source.name
        destination, _ = QFileDialog.getSaveFileName(
            self, "Save File As", filename, "All Files (*)"
        )
        if not destination:
            return

        try:
            shutil.copy2(source, Path(destination))
            QMessageBox.information(
                self, "Save File", "The received payload was copied successfully."
            )
        except OSError as exc:
            QMessageBox.warning(
                self, "Save File Failed", f"Could not copy the received payload:\n{exc}"
            )

    def _on_backup_db(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Backup Database to File", "vlc_database_backup.json", "JSON Files (*.json)",
        )
        if not path:
            return
        destination = Path(path)
        try:
            store_paths = (
                HISTORY_PATH, LEGACY_HISTORY_PATH,
                experiment_store.STORE_PATH, experiment_store.LEGACY_STORE_PATH,
                HISTORY_PATH.parent / RESTORE_JOURNAL, HISTORY_PATH.parent / STATE_LOCK_NAME,
            )
            if destination.resolve() in {source.resolve() for source in store_paths}:
                raise ReceiverStorageError("Choose a backup file outside the active database files.")
            with lock_state(HISTORY_PATH.parent):
                backup = {"history": _read_history(), "experiments": experiment_store.read_experiments()}
                write_json(destination, backup)
        except (OSError, ValueError, ReceiverStorageError) as exc:
            QMessageBox.warning(self, "Backup Failed", str(exc))
            return
        QMessageBox.information(self, "Backup Successful", "Receiver database backed up successfully.")

    def _on_restore_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Restore Database from File", "", "JSON Files (*.json)",
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_bytes())
            if not isinstance(data, dict) or not {"history", "experiments"} & data.keys():
                raise ReceiverStorageError("Invalid backup file structure")
            replacements = {}
            if "history" in data:
                replacements[HISTORY_PATH] = _validate_history(data["history"])
            if "experiments" in data:
                replacements[experiment_store.STORE_PATH] = experiment_store.validate_experiments(
                    data["experiments"]
                )
            confirmed = QMessageBox.question(
                self, "Restore Database",
                "Replace the existing receiver data included in this backup?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                return
            with lock_state(HISTORY_PATH.parent):
                recovery_copies = restore_json(replacements)
        except (OSError, ValueError, RecursionError, ReceiverStorageError) as exc:
            QMessageBox.warning(self, "Restore Failed", str(exc))
            return
        if HISTORY_PATH in replacements:
            self._history_data = replacements[HISTORY_PATH]
            self._pending_history.clear()
            self._history_corrupt = False
            self._history_write_error = None
            self._populate_table()
        if experiment_store.STORE_PATH in replacements:
            self.experiments_restored.emit()
        QMessageBox.information(
            self, "Restore Successful",
            "Receiver database restored successfully." + _recovery_message(recovery_copies),
        )

    def _on_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Database to CSV", "vlc_history_export.csv", "CSV Files (*.csv)")
        if path:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                time.sleep(0.2)
                QApplication.processEvents()
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["TID", "Filename", "Status", "Date / Time", "Size (Bytes)", "Chunks Received", "Chunks Total", "BER"])
                    for entry in self._history_data:
                        writer.writerow([
                            entry.get("tid"),
                            entry.get("filename"),
                            entry.get("status"),
                            entry.get("time_label"),
                            entry.get("size_bytes"),
                            entry.get("received_chunks"),
                            entry.get("total_chunks"),
                            entry.get("ber")
                        ])
                QApplication.restoreOverrideCursor()
                QMessageBox.information(self, "Export CSV", "Transfer logs exported to CSV successfully.")
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, "Export CSV Failed", f"Could not write CSV export:\n{e}")
