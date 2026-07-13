"""Receive Page — modern text reception and control console matching Keysight design rules."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.theme import COLORS
from gui_dev_v3.widgets import Card, ProgressBar, muted_label, value_label, panel_header


class ReceivePage(QWidget):
    """Modern text/file reception console."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_text = ""
        self._vref_locked = False
        self._app_state = None  # to send commands

        # Page layout
        lo = QVBoxLayout(self)
        lo.setContentsMargins(20, 16, 20, 20)
        lo.setSpacing(12)

        # ── 1. Reception Status Card ──
        self.status_card = Card("Reception Status")
        
        # Row 1: Status badge and info
        status_row = QHBoxLayout()
        self.status_badge = QLabel("○ IDLE")
        self.status_badge.setStyleSheet(
            f"color: {COLORS['muted']}; font-weight: 700; font-size: 12px; "
            "background: transparent; letter-spacing: 1.5px;"
        )
        status_row.addWidget(self.status_badge)
        status_row.addStretch(1)
        
        self.filename_lbl = value_label("No file transfer")
        status_row.addWidget(self.filename_lbl)
        
        self.chunks_lbl = muted_label("0 / 0 chunks")
        status_row.addWidget(self.chunks_lbl)
        self.status_card.body.addLayout(status_row)

        # Row 2: Progress bar
        self.progress_bar = ProgressBar(percent=0, height=12)
        self.status_card.body.addWidget(self.progress_bar)
        
        lo.addWidget(self.status_card)

        # ── 2. Received Text Card ──
        text_card = Card("Received Text Monitored")
        text_card.body.setSpacing(6)
        
        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setStyleSheet(
            f"QPlainTextEdit {{"
            f"    background: {COLORS['panel_alt']};"
            f"    color: {COLORS['green']};"
            f"    border: 1px solid {COLORS['border']};"
            f"    border-radius: 6px;"
            f"    padding: 10px;"
            f"    font-family: 'Cascadia Code', 'Courier New', monospace;"
            f"    font-size: 11px;"
            f"}}"
        )
        self.terminal.setPlaceholderText(
            "No data received yet.\n"
            "Waiting for transmission...\n\n"
            "Ensure sender is in range and transmitting."
        )
        text_card.body.addWidget(self.terminal, 1)
        
        lo.addWidget(text_card, 1)

        # ── 3. Control Actions Card ──
        control_card = Card("Control Actions")
        btn_lo = QHBoxLayout()
        btn_lo.setSpacing(10)

        # Lock/Auto Vref (Primary action, togglable)
        self.lock_btn = QPushButton("Auto Vref (Auto-Calibrate)")
        self.lock_btn.setObjectName("Primary")
        self.lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lock_btn.clicked.connect(self._on_lock_vref)
        self.lock_btn.setToolTip("Toggle between hardware auto-calibration of the reference voltage or a fixed manual reference voltage.")
        btn_lo.addWidget(self.lock_btn)

        # Clear Terminal (Default action)
        self.clear_btn = QPushButton("Clear Terminal")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._on_clear_terminal)
        btn_lo.addWidget(self.clear_btn)

        # Reset Transfer (Destructive action, styled outline red)
        self.reset_btn = QPushButton("Reset Transfer")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setStyleSheet(
            f"QPushButton {{"
            f"    background: transparent;"
            f"    border: 1px solid {COLORS['red']};"
            f"    color: {COLORS['red']};"
            f"    border-radius: 6px;"
            f"    padding: 8px 14px;"
            f"    font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{"
            f"    background: rgba(239, 68, 68, 0.12);"
            f"}}"
        )
        self.reset_btn.clicked.connect(self._on_reset_transfer)
        btn_lo.addWidget(self.reset_btn)
        
        control_card.body.addLayout(btn_lo)
        lo.addWidget(control_card)

    def refresh(self, state: RXAppState) -> None:
        """Refresh receive status and payload terminal from current state."""
        self._app_state = state
        transfer = state.transfer
        is_rec = state.is_receiving

        # Update status badge
        if is_rec:
            self.status_badge.setText("● RECEIVING")
            self.status_badge.setStyleSheet(
                f"color: {COLORS['green']}; font-weight: 700; font-size: 12px; "
                "background: transparent; letter-spacing: 1.5px;"
            )
        elif transfer.status == "Complete":
            self.status_badge.setText("● COMPLETE")
            self.status_badge.setStyleSheet(
                f"color: {COLORS['green']}; font-weight: 700; font-size: 12px; "
                "background: transparent; letter-spacing: 1.5px;"
            )
        elif transfer.status == "CRC Failed":
            self.status_badge.setText("● CRC FAILED")
            self.status_badge.setStyleSheet(
                f"color: {COLORS['red']}; font-weight: 700; font-size: 12px; "
                "background: transparent; letter-spacing: 1.5px;"
            )
        else:
            self.status_badge.setText("○ IDLE")
            self.status_badge.setStyleSheet(
                f"color: {COLORS['muted']}; font-weight: 700; font-size: 12px; "
                "background: transparent; letter-spacing: 1.5px;"
            )

        # Update file progress info
        filename = transfer.filename or "No file transfer"
        if filename != "No file transfer" and transfer.tid > 0:
            self.filename_lbl.setText(f"File: {filename}")
        else:
            self.filename_lbl.setText("No file transfer")

        self.chunks_lbl.setText(f"{transfer.received_chunks} / {transfer.total_chunks} chunks")
        self.progress_bar._percent = state.progress_percent
        self.progress_bar.update()

        # Update terminal text
        # If simulated, decode ascii representation of chunk payloads
        # We look at accumulated received bytes or construct a preview from received chunks
        decoded_text = ""
        # Sort chunks by index
        valid_chunks = [c for c in transfer.chunks if c.received]
        if valid_chunks:
            # Sort by index
            valid_chunks.sort(key=lambda x: x.index)
            payload_bytes = b"".join(c.received for c in valid_chunks)
            try:
                decoded_text = payload_bytes.decode("utf-8", errors="replace")
            except Exception:
                decoded_text = f"[Binary data: {len(payload_bytes)} bytes]"
        
        if decoded_text != self._last_text:
            self._last_text = decoded_text
            self.terminal.setPlainText(decoded_text)

    def _on_lock_vref(self) -> None:
        """Toggle between Lock Vref and Auto Vref."""
        self._vref_locked = not self._vref_locked
        if self._vref_locked:
            self.lock_btn.setText("Lock Vref (Fixed)")
            self.lock_btn.setStyleSheet(f"background: {COLORS['amber']}; color: black; font-weight: bold;")
            if self._app_state and self._app_state.mode == "physical":
                self._app_state.send_firmware_command("VREF=LOCK\n")
        else:
            self.lock_btn.setText("Auto Vref (Auto-Calibrate)")
            self.lock_btn.setStyleSheet("")
            if self._app_state and self._app_state.mode == "physical":
                self._app_state.send_firmware_command("VREF=AUTO\n")

    def _on_clear_terminal(self) -> None:
        """Clear received text buffer."""
        self._last_text = ""
        self.terminal.clear()

    def _on_reset_transfer(self) -> None:
        """Reset transfer state."""
        self._last_text = ""
        self.terminal.clear()
        # In a real setup, we might call a state.reset_transfer() if available
