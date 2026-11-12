"""Export Page — Transfer history logs, file actions, and database backup management matching Keysight styles."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
)

from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.models import TransferStatus, SessionCapture
from gui_dev_v3.theme import COLORS
from gui_dev_v3.widgets import Card, muted_label, value_label, panel_header, DetailRow, scrollable
from gui_dev_v3.data.records import load_session_capture


HISTORY_DIR = Path.home() / ".vlc_rx"
HISTORY_PATH = HISTORY_DIR / "transfer_history.json"


def _default_history() -> list[dict]:
    """Return an empty history; never seed the application with fabricated transfers."""
    return []


class SessionInspectorCard(Card):
    """Inspector panel displaying detailed session capture info, waveforms, and logs."""

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
            "Select an entry from the history list to review its high-fidelity "
            "analog waveforms, decoded digital bitstream, and protocol timeline."
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

        from gui_dev_v3.rx.signal_widgets import OOKWaveformWidget
        self.ook_waveform = OOKWaveformWidget()
        self.ook_waveform.setMinimumHeight(280)

        self.waveform_lo.addWidget(self.ook_waveform, 1)

        self.tabs.addTab(self.waveform_tab, "Waveforms")

        # ── Tab 3: Bitstream ──
        self.bitstream_tab = QWidget()
        self.bitstream_lo = QVBoxLayout(self.bitstream_tab)
        self.bitstream_lo.setContentsMargins(12, 12, 12, 12)
        
        self.bitstream_text = QPlainTextEdit()
        self.bitstream_text.setReadOnly(True)
        self.bitstream_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.bitstream_text.setStyleSheet("""
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
        self.bitstream_lo.addWidget(self.bitstream_text)
        self.tabs.addTab(self.bitstream_tab, "Bitstream")

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
        self.stacked.setCurrentIndex(0)

    def show_capture(self, capture: SessionCapture, entry: dict) -> None:
        self.stacked.setCurrentIndex(1)

        # Clear existing info group items
        for i in reversed(range(self.info_group.body.count())):
            item = self.info_group.body.itemAt(i)
            if item.widget() and item.widget().objectName() != "SectionTitle":
                item.widget().deleteLater()

        # Update Summary tab
        status = entry.get("status", "Complete")
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
        
        size = entry.get("size_bytes", 0)
        size_txt = f"{size:,} Bytes" if size < 1024 else f"{size/1024:.2f} KiB ({size:,} Bytes)"
        self.info_group.body.addWidget(DetailRow("File Size", size_txt))
        self.info_group.body.addWidget(DetailRow("Throughput", f"{capture.throughput_kbps:.2f} kbps"))
        self.info_group.body.addWidget(DetailRow("Bit Error Rate (BER)", f"{capture.ber:.4%}"))
        self.info_group.body.addWidget(DetailRow("CRC Status", capture.crc_status, value_color=status_color))

        # Update Waveforms
        self.ook_waveform.set_playback_mode(True, capture.ook_bits)

        # Update Bitstream
        # Format the bits cleanly: group by 8 bits with space, wrapping after 64 bits
        bit_str = ""
        for idx, bit in enumerate(capture.ook_bits):
            bit_str += str(bit)
            if (idx + 1) % 8 == 0:
                bit_str += " "
            if (idx + 1) % 64 == 0:
                bit_str += "\n"
        self.bitstream_text.setPlainText(bit_str.strip() or "No bits decoded in this capture session.")

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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history_data: list[dict] = []
        self._load_history()
        # Page layout
        lo = QVBoxLayout(self)
        lo.setContentsMargins(20, 16, 20, 20)
        lo.setSpacing(12)

        # Create horizontal splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
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
        hdr_actions.addWidget(muted_label("Historical transfer snapshots stored on this device."))
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
        self.table.setMinimumHeight(220)
        self.history_card.body.addWidget(self.table)

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

        # Set splitter ratio/sizes (e.g., 55% left, 45% right)
        self.splitter.setSizes([620, 580])

        lo.addWidget(self.splitter)

        # Build initial table rows
        self._populate_table()

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
        if HISTORY_PATH.exists():
            try:
                data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._history_data = data
                    return
            except (OSError, json.JSONDecodeError):
                pass
        
        self._history_data = _default_history()
        self._save_history()

    def _save_history(self) -> None:
        try:
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            HISTORY_PATH.write_text(json.dumps(self._history_data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._history_data))
        for row, entry in enumerate(self._history_data):
            # TID
            tid_item = QTableWidgetItem(f"{entry.get('tid', 0):04d}")
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
            size = entry.get("size_bytes", 0)
            size_txt = f"{size:,} B" if size < 1024 else f"{size/1024:.1f} KiB"
            size_item = QTableWidgetItem(size_txt)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, size_item)

            # Chunks
            rx = entry.get("received_chunks", 0)
            tot = entry.get("total_chunks", 0)
            chunks_item = QTableWidgetItem(f"{rx} / {tot}")
            chunks_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, chunks_item)

            # BER
            ber = entry.get("ber", 0.0)
            ber_txt = f"{ber:.2%}" if ber > 0 else "0.00%"
            ber_item = QTableWidgetItem(ber_txt)
            ber_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if ber > 0:
                ber_item.setForeground(QColor(COLORS["red"]))
            self.table.setItem(row, 6, ber_item)

        self.table.clearSelection()
        self._on_selection_changed()

    def refresh(self, state: RXAppState) -> None:
        """Called periodically on dashboard refresh timer. Syncs new completed transfers."""
        transfer = state.transfer
        if transfer.tid > 0 and transfer.status != "Pending":
            # Check if this TID is already in the history
            exists = any(item.get("tid") == transfer.tid for item in self._history_data)
            if not exists:
                ber = transfer.quality.strict_ber if transfer.quality else 0.0
                entry = {
                    "tid": transfer.tid,
                    "filename": transfer.filename,
                    "status": transfer.status.value,
                    "time_label": transfer.time_label,
                    "size_bytes": transfer.size_bytes,
                    "total_chunks": transfer.total_chunks,
                    "received_chunks": transfer.received_chunks,
                    "ber": ber,
                }
                self._history_data.insert(0, entry)
                self._save_history()
                self._populate_table()

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
        capture = load_session_capture(tid)
        if capture is not None:
            self.inspector_card.show_capture(capture, entry)
        else:
            self.inspector_card.show_empty()

    def _on_browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Export Directory", self._folder_edit.text())
        if path:
            self._folder_edit.setText(path)

    def _on_open_folder(self) -> None:
        folder = self._folder_edit.text()
        Path(folder).mkdir(parents=True, exist_ok=True)
        import subprocess
        import sys
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
            self._history_data.clear()
            self._save_history()
            self._populate_table()

    def _get_selected_entry(self) -> dict | None:
        rows = self.table.selectedRanges()
        if not rows:
            return None
        idx = rows[0].topRow()
        if 0 <= idx < len(self._history_data):
            return self._history_data[idx]
        return None

    def _on_open_file(self) -> None:
        if not self._get_selected_entry():
            return
        QMessageBox.warning(
            self,
            "File Unavailable",
            "This history record contains transfer metadata only. The received payload file is not stored with the history record, so it cannot be opened from here.",
        )

    def _on_save_as(self) -> None:
        if not self._get_selected_entry():
            return
        QMessageBox.warning(
            self,
            "Export Unavailable",
            "The original received payload bytes are not available in this history record. No placeholder file was written.",
        )

    def _on_backup_db(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Backup Database to File", "vlc_database_backup.json", "JSON Files (*.json)")
        if path:
            # We backup the whole .vlc_rx config folder content
            backup_data = {
                "experiments": [],
                "history": self._history_data
            }
            exp_file = HISTORY_DIR / "experiments.json"
            if exp_file.exists():
                try:
                    backup_data["experiments"] = json.loads(exp_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # Write the real history and experiment metadata to the selected backup file.
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                QApplication.processEvents()
                Path(path).write_text(json.dumps(backup_data, indent=2), encoding="utf-8")
                QApplication.restoreOverrideCursor()
                QMessageBox.information(self, "Backup Successful", "Receiver database backed up successfully.")
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, "Backup Failed", f"Failed to write backup database file:\n{e}")

    def _on_restore_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore Database from File", "", "JSON Files (*.json)")
        if path:
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                if "experiments" not in data and "history" not in data:
                    raise ValueError("Invalid backup file structure")
                
                ret = QMessageBox.question(
                    self, "Restore Database", "This will overwrite your current experimental data and logs. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if ret == QMessageBox.StandardButton.Yes:
                    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                    time.sleep(0.3)
                    QApplication.processEvents()
                    
                    if "history" in data:
                        self._history_data = data["history"]
                        self._save_history()
                        self._populate_table()
                    
                    if "experiments" in data:
                        exp_file = HISTORY_DIR / "experiments.json"
                        exp_file.write_text(json.dumps(data["experiments"], indent=2), encoding="utf-8")
                        
                    QApplication.restoreOverrideCursor()
                    QMessageBox.information(self, "Restore Successful", "Receiver database restored successfully.")
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, "Restore Failed", f"Failed to read or parse backup database file:\n{e}")

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
