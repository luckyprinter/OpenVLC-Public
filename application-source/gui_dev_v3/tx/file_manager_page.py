import os
import time
import zipfile
import binascii
import math
from typing import Any

from PySide6.QtCore import Qt, Signal, QFileInfo
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QMessageBox, QFileDialog, QLabel
)

from gui_dev_v3.tx_app_state import TXAppState
from gui_dev_v3.widgets import Card, primary_button, secondary_button

def _detail_row(label_text: str, default_val: str) -> tuple[QWidget, QLabel]:
    w = QWidget()
    w.setObjectName("Card")
    lo = QHBoxLayout(w)
    lo.setContentsMargins(0, 2, 0, 2)
    lbl = QLabel(label_text)
    lbl.setObjectName("Muted")
    val = QLabel(default_val)
    val.setObjectName("Value")
    val.setWordWrap(True)
    lo.addWidget(lbl)
    lo.addStretch(1)
    lo.addWidget(val, alignment=Qt.AlignmentFlag.AlignRight)
    return w, val

# Define the symbol rate and protocol overhead matching TX Simulation Model
SYMBOL_RATE = 15000.0  # sym/s
PROTOCOL_OVERHEAD = 1.25  # 4B5B overhead
PACKET_SIZE = 256  # bytes per packet
PACKET_OVERHEAD = 16  # bytes (preamble + sync + CRC + seq)

class DragDropTable(QTableWidget):
    files_dropped = Signal(list)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                files.append(url.toLocalFile())
        if files:
            self.files_dropped.emit(files)


class FileManagerPage(QWidget):
    def __init__(self, state: TXAppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._files = [] # list of dicts: filepath, name, ext, size, crc, est_time
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Left Column - Directory Browser (Table)
        left_col = QVBoxLayout()
        dir_card = Card("Local Payload Directory")
        
        self.file_table = DragDropTable(0, 5)
        self.file_table.setHorizontalHeaderLabels(["Filename", "Type", "Size", "CRC-16", "Est. Time"])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 5):
            self.file_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.file_table.verticalHeader().setDefaultSectionSize(32)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.file_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.file_table.setAlternatingRowColors(True)
        self.file_table.setShowGrid(False)
        self.file_table.setSortingEnabled(True)
        self.file_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.file_table.files_dropped.connect(self._on_files_added)
        
        dir_card.body.addWidget(self.file_table)
        
        # Add File Button row
        btn_row = QHBoxLayout()
        self.btn_browse = primary_button("Browse / Add File")
        self.btn_browse.clicked.connect(self._on_browse_clicked)
        btn_row.addWidget(self.btn_browse)
        btn_row.addStretch()
        
        dir_card.body.addLayout(btn_row)
        left_col.addWidget(dir_card)
        layout.addLayout(left_col, 6)

        # Right Column - File Details & Actions
        right_col = QVBoxLayout()
        
        details_card = Card("Payload Details")
        w_name, self.lbl_name = _detail_row("Name", "—")
        w_size, self.lbl_size = _detail_row("Size", "—")
        w_crc, self.lbl_crc = _detail_row("CRC-16", "—")
        w_est_time, self.lbl_est_time = _detail_row("Est. Duration", "—")
        
        details_card.body.addWidget(w_name)
        details_card.body.addWidget(w_size)
        details_card.body.addWidget(w_crc)
        details_card.body.addWidget(w_est_time)
        right_col.addWidget(details_card)
        
        actions_card = Card("Actions")
        self.btn_add_queue = primary_button("Add to Transmit Queue")
        self.btn_add_queue.clicked.connect(self._on_add_to_queue)
        self.btn_add_queue.setEnabled(False)
        
        self.btn_compress = secondary_button("Compress (ZIP) Payload")
        self.btn_compress.clicked.connect(self._on_compress_clicked)
        self.btn_compress.setEnabled(False)
        
        actions_card.body.addWidget(self.btn_add_queue)
        actions_card.body.addWidget(self.btn_compress)
        
        self.lbl_feedback = QLabel("")
        self.lbl_feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_feedback.setObjectName("FeedbackSuccess")
        actions_card.body.addWidget(self.lbl_feedback)
        
        right_col.addWidget(actions_card)
        right_col.addStretch(1)
        
        layout.addLayout(right_col, 4)

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
            
    def _estimate_time(self, size_bytes: int) -> str:
        if size_bytes == 0:
            return "0s"
        total_chunks = math.ceil(size_bytes / PACKET_SIZE)
        total_bytes = size_bytes + (total_chunks * PACKET_OVERHEAD)
        total_bits = total_bytes * 8 * PROTOCOL_OVERHEAD
        seconds = total_bits / SYMBOL_RATE
        
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = seconds % 60
            return f"{mins} min {secs:.1f} sec"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours} hr {mins} min"

    def _compute_crc16(self, filepath: str) -> str:
        try:
            with open(filepath, "rb") as f:
                data = f.read()
                # CRC-CCITT
                crc = binascii.crc_hqx(data, 0xFFFF)
                return f"0x{crc:04X}"
        except Exception:
            return "ERROR"

    def _on_browse_clicked(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select Payload Files", "", "All Files (*)")
        if files:
            self._on_files_added(files)

    def _on_files_added(self, filepaths: list[str]) -> None:
        for filepath in filepaths:
            info = QFileInfo(filepath)
            if not info.exists() or not info.isFile():
                continue
            
            size_bytes = info.size()
            
            file_data = {
                "filepath": filepath,
                "name": info.fileName(),
                "ext": info.suffix().upper() or "FILE",
                "size_bytes": size_bytes,
                "size_str": self._format_size(size_bytes),
                "crc": self._compute_crc16(filepath),
                "est_time": self._estimate_time(size_bytes)
            }
            self._files.append(file_data)
            
        self._refresh_table()

    def _refresh_table(self) -> None:
        # Disable sorting during repopulation to prevent mid-insert reordering
        self.file_table.setSortingEnabled(False)
        self.file_table.setRowCount(len(self._files))
        for row, fd in enumerate(self._files):
            # Store original _files index in UserRole so selection stays
            # correct after the user sorts the table by any column
            name_item = QTableWidgetItem(fd["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, row)
            self.file_table.setItem(row, 0, name_item)
            self.file_table.setItem(row, 1, QTableWidgetItem(fd["ext"]))
            self.file_table.setItem(row, 2, QTableWidgetItem(fd["size_str"]))
            self.file_table.setItem(row, 3, QTableWidgetItem(fd["crc"]))
            self.file_table.setItem(row, 4, QTableWidgetItem(fd["est_time"]))
        self.file_table.setSortingEnabled(True)
        
    def _on_selection_changed(self) -> None:
        selected_rows = self.file_table.selectionModel().selectedRows()
        if not selected_rows:
            self._update_details_pane(None)
            self.btn_add_queue.setEnabled(False)
            self.btn_compress.setEnabled(False)
            return
        # Use UserRole index so lookup is correct even after sorting
        visual_row = selected_rows[0].row()
        name_item = self.file_table.item(visual_row, 0)
        original_idx = name_item.data(Qt.ItemDataRole.UserRole) if name_item else 0
        fd = self._files[original_idx]
        self._update_details_pane(fd)
        self.btn_add_queue.setEnabled(True)
        # Enable compression if not already a zip
        self.btn_compress.setEnabled(fd["ext"] != "ZIP")
        
    def _update_details_pane(self, fd: dict | None) -> None:
        if fd:
            self.lbl_name.setText(fd["name"])
            self.lbl_size.setText(fd["size_str"])
            self.lbl_crc.setText(fd["crc"])
            self.lbl_est_time.setText(fd["est_time"])
        else:
            self.lbl_name.setText("—")
            self.lbl_size.setText("—")
            self.lbl_crc.setText("—")
            self.lbl_est_time.setText("—")
            
    def _on_compress_clicked(self) -> None:
        selected_rows = self.file_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        visual_row = selected_rows[0].row()
        name_item = self.file_table.item(visual_row, 0)
        original_idx = name_item.data(Qt.ItemDataRole.UserRole) if name_item else 0
        fd = self._files[original_idx]
        
        try:
            zip_path = fd["filepath"] + ".zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(fd["filepath"], fd["name"])
                
            # Add the new zip file to the list
            self._on_files_added([zip_path])
            self.lbl_feedback.setText(f"Compressed to {fd['name']}.zip successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Compression Error", str(e))
            
    def _on_add_to_queue(self) -> None:
        if not self.state:
            return

        selected_rows = self.file_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        visual_row = selected_rows[0].row()
        name_item = self.file_table.item(visual_row, 0)
        original_idx = name_item.data(Qt.ItemDataRole.UserRole) if name_item else 0
        fd = self._files[original_idx]

        self.state.transmission_queue.append({
            "filename": fd["name"],
            "filepath": fd["filepath"],
            "size": fd["size_str"],
            "status": "Queued"
        })

        self.lbl_feedback.setText(f"Added {fd['name']} to Transmit Queue")
