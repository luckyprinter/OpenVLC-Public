"""Placeholder pages and fully-populated pages for non-Dashboard TX tabs."""
from __future__ import annotations

import os
import time
import csv
from typing import Any


from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QFileDialog
)

from gui_dev_v3.tx_app_state import TXAppState
from gui_dev_v3.widgets import Card, muted_label, primary_button, secondary_button
from gui_dev_v3.theme import COLORS


class TransmitPage(QWidget):
    def __init__(self, state: TXAppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._batch_active = False
        self._current_queue_index = -1

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Left Column - Queue
        left_col = QVBoxLayout()
        queue_card = Card("Transmission Queue")
        
        self.queue_table = QTableWidget(0, 3)
        self.queue_table.setHorizontalHeaderLabels(["Filename", "Size", "Status"])
        self.queue_table.verticalHeader().setDefaultSectionSize(32)
        qhdr = self.queue_table.horizontalHeader()
        qhdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)          # Filename
        qhdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)            # Size
        qhdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)            # Status
        self.queue_table.setColumnWidth(1, 70)
        self.queue_table.setColumnWidth(2, 90)
        self.queue_table.setFixedHeight(220)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.queue_table.setAlternatingRowColors(True)
        self.queue_table.setShowGrid(False)
        self.queue_table.setSortingEnabled(True)
        
        queue_card.body.addWidget(self.queue_table)
        left_col.addWidget(queue_card)
        
        # Session History Card
        history_card = Card("Session History")
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["Time", "File", "Throughput", "Outcome"])
        self.history_table.verticalHeader().setDefaultSectionSize(32)
        hhdr = self.history_table.horizontalHeader()
        hhdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)       # Time
        hhdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)     # File
        hhdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)       # Throughput
        hhdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)       # Outcome
        self.history_table.setColumnWidth(0, 80)
        self.history_table.setColumnWidth(2, 110)
        self.history_table.setColumnWidth(3, 80)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setShowGrid(False)
        self.history_table.setFixedHeight(180)
        self.history_table.setSortingEnabled(True)
        
        history_card.body.addWidget(self.history_table)
        left_col.addWidget(history_card)
        
        layout.addLayout(left_col, 6)

        # Right Column - Controls
        right_col = QVBoxLayout()
        ctrl_card = Card("Queue Controls")
        self.start_btn = primary_button("Start Batch Transmission")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self._on_start_batch)
        ctrl_card.body.addWidget(self.start_btn)

        self.clear_btn = secondary_button("Clear Completed Queue")
        self.clear_btn.clicked.connect(self._on_clear_queue)
        ctrl_card.body.addWidget(self.clear_btn)
        right_col.addWidget(ctrl_card)
        
        config_card = Card("Batch Configuration")
        config_card.body.addWidget(_detail_row("Batch Mode", "Sequential"))
        config_card.body.addWidget(_detail_row("Retry Policy", "Max 3 retries"))
        config_card.body.addWidget(_detail_row("Delay Between Files", "2.0 seconds"))
        right_col.addWidget(config_card)
        
        right_col.addStretch(1)
        layout.addLayout(right_col, 4)

        if self.state:
            self.refresh(self.state)

    def _on_start_batch(self) -> None:
        if not self.state:
            return

        if self._batch_active:
            # Stop the batch
            self._batch_active = False
            self._current_queue_index = -1
            self.start_btn.setText("Start Batch Transmission")
            self.start_btn.setObjectName("Primary")
            self.start_btn.style().unpolish(self.start_btn)
            self.start_btn.style().polish(self.start_btn)
            
            # Cancel active simulation if running
            if self.state.mode == "simulated" and self.state._simulation:
                self.state._simulation.stop()
                self.state.refresh()
            return

        # Start the batch
        # Find if there are queued items
        queued_items = [i for i, item in enumerate(self.state.transmission_queue) if item["status"] == "Queued"]
        if not queued_items:
            QMessageBox.information(
                self, "Queue Empty", 
                "No queued files found. Please load files from the File Manager tab first."
            )
            return

        self._batch_active = True
        self._current_queue_index = -1
        self.start_btn.setText("Stop Batch Transmission")
        self.start_btn.setObjectName("Danger")
        # Force QSS re-polish after objectName change
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

    def _on_clear_queue(self) -> None:
        if not self.state:
            return
        # Keep only "Queued" or currently active items
        self.state.transmission_queue = [
            item for item in self.state.transmission_queue 
            if item["status"] in ("Queued", "Transmitting") or "Transmitting" in item["status"]
        ]
        self.refresh(self.state)

    def refresh(self, state: TXAppState) -> None:
        self.state = state
        
        # 1. Update Queue Table
        self.queue_table.blockSignals(True)
        self.queue_table.setRowCount(len(state.transmission_queue))
        for row, item in enumerate(state.transmission_queue):
            # Filename
            file_item = QTableWidgetItem(item["filename"])
            self.queue_table.setItem(row, 0, file_item)
            
            # Size
            size_item = QTableWidgetItem(item["size"])
            self.queue_table.setItem(row, 1, size_item)
            
            # Status (with colors)
            status_str = item["status"]
            status_item = QTableWidgetItem(status_str)
            if "Transmitting" in status_str:
                status_item.setForeground(QColor(COLORS["accent"]))
            elif status_str == "Completed":
                status_item.setForeground(QColor(COLORS["green"]))
            elif status_str == "Queued":
                status_item.setForeground(QColor(COLORS["amber"]))
            elif status_str == "Failed":
                status_item.setForeground(QColor(COLORS["red"]))
            self.queue_table.setItem(row, 2, status_item)
        self.queue_table.blockSignals(False)

        # 2. Update Session History Table
        self.history_table.blockSignals(True)
        self.history_table.setRowCount(len(state.session_history))
        for row, item in enumerate(state.session_history):
            self.history_table.setItem(row, 0, QTableWidgetItem(item["time"]))
            self.history_table.setItem(row, 1, QTableWidgetItem(item["file"]))
            self.history_table.setItem(row, 2, QTableWidgetItem(item["throughput"]))
            
            outcome_str = item["outcome"]
            outcome_item = QTableWidgetItem(outcome_str)
            if outcome_str == "SUCCESS":
                outcome_item.setForeground(QColor(COLORS["green"]))
            else:
                outcome_item.setForeground(QColor(COLORS["red"]))
            self.history_table.setItem(row, 3, outcome_item)
        self.history_table.blockSignals(False)

        # 3. Batch State Machine Processing
        if self._batch_active:
            if self._current_queue_index == -1:
                # Find the next file to transmit
                next_idx = -1
                for idx, item in enumerate(state.transmission_queue):
                    if item["status"] == "Queued":
                        next_idx = idx
                        break
                
                if next_idx == -1:
                    # All done!
                    self._batch_active = False
                    self.start_btn.setText("Start Batch Transmission")
                    self.start_btn.setObjectName("Primary")
                    self.start_btn.style().unpolish(self.start_btn)
                    self.start_btn.style().polish(self.start_btn)
                    QMessageBox.information(self, "Batch Complete", "All batch transmission tasks completed successfully!")
                else:
                    # Start transmitting this file
                    self._current_queue_index = next_idx
                    current_item = state.transmission_queue[next_idx]
                    current_item["status"] = "Transmitting (0%)"
                    
                    filepath = current_item.get("filepath", "")
                    if filepath and os.path.exists(filepath):
                        # Trigger state transmission
                        state.start_transmission(filepath)
                    else:
                        current_item["status"] = "Failed (File Missing)"
                        self._current_queue_index = -1
            else:
                # Currently transmitting a file
                current_item = state.transmission_queue[self._current_queue_index]
                status_lower = (state.status_text or "").lower()
                
                if "complete" in status_lower:
                    current_item["status"] = "Completed"
                    self._current_queue_index = -1  # Fetch next on next poll
                elif "failed" in status_lower or "abort" in status_lower or "offline" in status_lower:
                    current_item["status"] = "Failed"
                    self._current_queue_index = -1  # Fetch next on next poll
                else:
                    # Update active progress
                    current_item["status"] = f"Transmitting ({state.progress_percent}%)"


class LogsPage(QWidget):
    def __init__(self, state: TXAppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Filter bar
        filter_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter logs by filename or outcome...")
        self.search_edit.setObjectName("SearchInput")
        self.search_edit.textChanged.connect(self._on_filter_changed)

        self.export_btn = QPushButton("Export to CSV")
        self.export_btn.setObjectName("ExportBtn")
        self.export_btn.clicked.connect(self._on_export_clicked)
        
        filter_layout.addWidget(self.search_edit, 1)
        filter_layout.addWidget(self.export_btn)
        layout.addLayout(filter_layout)

        # Logs Card
        logs_card = Card("Transmission Session History")
        
        self.logs_table = QTableWidget(0, 6)
        self.logs_table.setHorizontalHeaderLabels(["Timestamp", "Filename", "Outcome", "Chunks Sent", "Data Rate", "Duration"])
        self.logs_table.verticalHeader().setDefaultSectionSize(32)
        lhdr = self.logs_table.horizontalHeader()
        lhdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)         # Timestamp
        lhdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)       # Filename
        lhdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)         # Outcome
        lhdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)         # Chunks Sent
        lhdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)         # Data Rate
        lhdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)         # Duration
        self.logs_table.setColumnWidth(0, 140)
        self.logs_table.setColumnWidth(2, 80)
        self.logs_table.setColumnWidth(3, 90)
        self.logs_table.setColumnWidth(4, 100)
        self.logs_table.setColumnWidth(5, 80)
        self.logs_table.verticalHeader().setVisible(False)
        self.logs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.logs_table.setAlternatingRowColors(True)
        self.logs_table.setShowGrid(False)
        self.logs_table.setSortingEnabled(True)
        # No fixed height — table expands to fill the card
        logs_card.body.addWidget(self.logs_table, 1)

        # ── Stats Summary Bar ──────────────────────────────────────
        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,0.08);")
        logs_card.body.addWidget(sep)

        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 6, 0, 2)
        stats_row.setSpacing(24)

        self._stat_total = QLabel("Total: 0")
        self._stat_total.setObjectName("Muted")
        self._stat_success = QLabel("Success: 0")
        self._stat_success.setStyleSheet(f"font-size: 12px; color: {COLORS['green']};")
        self._stat_failed = QLabel("Failed: 0")
        self._stat_failed.setStyleSheet(f"font-size: 12px; color: {COLORS['red']};")
        self._stat_avg_rate = QLabel("Avg Rate: —")
        self._stat_avg_rate.setObjectName("Muted")

        for lbl in (self._stat_total, self._stat_success, self._stat_failed, self._stat_avg_rate):
            lbl.setStyleSheet(lbl.styleSheet() + " font-size: 12px;")
            stats_row.addWidget(lbl)
        stats_row.addStretch(1)
        logs_card.body.addLayout(stats_row)

        layout.addWidget(logs_card, 1)

        if self.state:
            self.refresh(self.state)

    def refresh(self, state: TXAppState) -> None:
        self.state = state
        self.logs_table.blockSignals(True)
        self.logs_table.setSortingEnabled(False)  # disable during repopulation
        self.logs_table.setRowCount(len(state.session_history))
        total = len(state.session_history)
        success_count = 0
        failed_count = 0
        rates: list[float] = []

        for row, entry in enumerate(state.session_history):
            time_str = entry.get("time", "")
            self.logs_table.setItem(row, 0, QTableWidgetItem(time_str))
            self.logs_table.setItem(row, 1, QTableWidgetItem(entry.get("file", "—")))

            outcome_str = entry.get("outcome", "—")
            outcome_item = QTableWidgetItem(outcome_str)
            if outcome_str == "SUCCESS":
                outcome_item.setForeground(QColor(COLORS["green"]))
                success_count += 1
            else:
                outcome_item.setForeground(QColor(COLORS["red"]))
                failed_count += 1
            self.logs_table.setItem(row, 2, outcome_item)

            self.logs_table.setItem(row, 3, QTableWidgetItem(entry.get("chunks", "—")))
            rate_str = entry.get("throughput", "—")
            self.logs_table.setItem(row, 4, QTableWidgetItem(rate_str))
            self.logs_table.setItem(row, 5, QTableWidgetItem(entry.get("duration", "—")))

            # Collect numeric rate for average (format: "12.3 kbps")
            try:
                rate_val = float(rate_str.split()[0])
                rates.append(rate_val)
            except (ValueError, IndexError):
                pass

        self.logs_table.setSortingEnabled(True)
        self.logs_table.blockSignals(False)

        # Update stats bar
        self._stat_total.setText(f"Total: {total}")
        self._stat_success.setText(f"Success: {success_count}")
        self._stat_failed.setText(f"Failed: {failed_count}")
        if rates:
            avg = sum(rates) / len(rates)
            unit = "kbps" if state.session_history and "kbps" in (state.session_history[0].get("throughput", "")) else ""
            self._stat_avg_rate.setText(f"Avg Rate: {avg:.1f} {unit}".strip())
        else:
            self._stat_avg_rate.setText("Avg Rate: —")

    def _on_filter_changed(self, text: str) -> None:
        text = text.lower()
        for row in range(self.logs_table.rowCount()):
            match = False
            for col in range(self.logs_table.columnCount()):
                item = self.logs_table.item(row, col)
                if item and text in item.text().lower():
                    match = True
                    break
            self.logs_table.setRowHidden(row, not match)

    def _on_export_clicked(self) -> None:
        filepath, _ = QFileDialog.getSaveFileName(self, "Export Logs to CSV", "", "CSV Files (*.csv)")
        if filepath:
            try:
                with open(filepath, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    # Headers
                    headers = [
                        self.logs_table.horizontalHeaderItem(col).text() 
                        for col in range(self.logs_table.columnCount())
                    ]
                    writer.writerow(headers)
                    # Rows
                    for row in range(self.logs_table.rowCount()):
                        row_data = [
                            self.logs_table.item(row, col).text() if self.logs_table.item(row, col) else "" 
                            for col in range(self.logs_table.columnCount())
                        ]
                        writer.writerow(row_data)
                QMessageBox.information(self, "Export Succeeded", f"Log data saved to:\n{filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Failed to save CSV file:\n{e}")


class AboutPage(QWidget):
    def __init__(self, state: TXAppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        card = Card("VLC GUI")
        
        # Version and Build
        version_label = QLabel("Version: 1.0.0 | Build: June 2026")
        version_label.setObjectName("Muted")
        card.body.addWidget(version_label)
        
        # Created by
        creator_label = QLabel("Created by: Reymart Martinez")
        creator_label.setStyleSheet("font-weight: bold; margin-top: 10px; margin-bottom: 10px;")
        card.body.addWidget(creator_label)
        
        # About description
        about_title = QLabel("About:")
        about_title.setStyleSheet("font-weight: bold; margin-top: 10px;")
        card.body.addWidget(about_title)
        
        about_text = QLabel(
            "An experimental Visible Light Communication (VLC) graphical user interface "
            "developed in partial fulfillment of the requirements for the degree of "
            "Bachelor of Science in Electronics Engineering. Designed to monitor, encode, "
            "and reconstruct 4B5B + NRZ/OOK optical payloads via ESP32 microcontrollers."
        )
        about_text.setWordWrap(True)
        about_text.setStyleSheet("line-height: 1.4;")
        card.body.addWidget(about_text)
        
        # License & Legal
        legal_title = QLabel("License & Legal:")
        legal_title.setStyleSheet("font-weight: bold; margin-top: 15px;")
        card.body.addWidget(legal_title)
        
        legal_text = QLabel(
            "Copyright © 2026. All rights reserved.\n"
            "This software is provided \"as-is\", without warranty of any kind, express or implied. "
            "For academic and experimental use only."
        )
        legal_text.setWordWrap(True)
        legal_text.setObjectName("Muted")
        card.body.addWidget(legal_text)

        layout.addWidget(card)
        layout.addStretch(1)


# ── Helpers ──

def _detail_row(label: str, value: str) -> QWidget:
    w = QWidget()
    w.setObjectName("Card")
    lo = QHBoxLayout(w)
    lo.setContentsMargins(0, 2, 0, 2)
    lbl = QLabel(label)
    lbl.setObjectName("Muted")
    val = QLabel(value)
    val.setObjectName("Value")
    val.setWordWrap(True)
    lo.addWidget(lbl)
    lo.addStretch(1)
    lo.addWidget(val, alignment=Qt.AlignmentFlag.AlignRight)
    return w


def _set_row_value(row_widget: QWidget, new_value: str) -> None:
    lo = row_widget.layout()
    if lo and lo.count() >= 2:
        val_label = lo.itemAt(lo.count() - 1).widget()
        if isinstance(val_label, QLabel):
            val_label.setText(new_value)
