"""RX Dashboard — live panels matching the VLC Receiver UI design image.

Layout:
┌──────────────────────────────────────────────────────────────┐
│ Top row: Reception Status | Performance Metrics | Signal     │
│ Middle row: Signal Waveform (60%) | Received File Info (40%) │
│ Bottom row: Recent Activity (full width)                     │
└──────────────────────────────────────────────────────────────┘

All panels refresh from live vlc_beta data every 1 second.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
    QSplitter,
)

from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.theme import COLORS
from gui_dev_v3.widgets import (
    ActivityLogTable,
    Card,
    ProgressBar,
    StatusBadge,
    WaveformWidget,
    muted_label,
    panel_header,
    value_label,
)
from gui_dev_v3.rx.signal_widgets import OOKWaveformWidget, SignalWaveform


import math


class MetricRow(QWidget):
    """A horizontal row containing a muted label and a value label."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        self.lbl = QLabel(label)
        self.lbl.setObjectName("Muted")
        self.val = QLabel("—")
        self.val.setObjectName("Value")
        self.val.setStyleSheet("font-weight: 600; background: transparent;")
        layout.addWidget(self.lbl)
        layout.addStretch(1)
        layout.addWidget(self.val)

    def setValue(self, value: str) -> None:
        if self.val.text() != value:
            self.val.setText(value)


class StatusRow(QWidget):
    """A horizontal row containing a muted label and a colored status label."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        self.lbl = QLabel(label)
        self.lbl.setObjectName("Muted")
        self.val = QLabel("—")
        self.val.setStyleSheet("font-weight: 700; background: transparent;")
        layout.addWidget(self.lbl)
        layout.addStretch(1)
        layout.addWidget(self.val)

    def setStatus(self, value: str, color: str) -> None:
        if self.val.text() != value:
            self.val.setText(value)
        self.val.setStyleSheet(f"color: {color}; font-weight: 700; background: transparent;")


class _ReceptionStatusPanel(Card):
    """Reception Status — left top panel."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__("Reception", parent)
        badge_layout = QHBoxLayout()
        badge_layout.setContentsMargins(0, 0, 0, 0)
        
        from PySide6.QtWidgets import QPushButton
        self.cancel_btn = QPushButton("Abort")
        self.cancel_btn.setObjectName("CancelBtn")
        self.cancel_btn.setStyleSheet(f"background: {COLORS['red']}; color: white; border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 10px;")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._on_cancel)
        badge_layout.addWidget(self.cancel_btn)
        
        badge_layout.addStretch(1)
        self.badge = StatusBadge("IDLE", COLORS["muted"])
        badge_layout.addWidget(self.badge)
        self.body.addLayout(badge_layout)

        self.chunks_row = MetricRow("Chunks")
        self.body.addWidget(self.chunks_row)

        self.time_elapsed_row = MetricRow("Elapsed")
        self.body.addWidget(self.time_elapsed_row)
        
        self._state = state

    def _on_cancel(self) -> None:
        if self._state.mode == "simulated" and self._state._simulation:
            self._state._simulation.cleanup()
            self._state.notify()

    def refresh(self, state: RXAppState) -> None:
        self._state = state
        sig = state.signal
        transfer = state.transfer

        stage = str(state.session.latest_transfer.status.value) if state.session.latest_transfer else "Idle"
        is_active = state.is_receiving or "incomplete" in stage.lower()
        badge_text = "RECEIVING" if is_active else "IDLE"
        badge_color = COLORS["green"] if is_active else COLORS["muted"]

        self.badge.setText(badge_text)
        self.badge.setStyleSheet(f"background: {badge_color}; color: #0b1016; border-radius: 10px; padding: 4px 9px; font-weight: 700; font-size: 11px;")
        self.chunks_row.setValue(f"{transfer.received_chunks} / {transfer.total_chunks}")
        self.time_elapsed_row.setValue(sig.time_elapsed if sig.time_elapsed else "—")
        self.cancel_btn.setVisible(is_active)


class _PerformanceMetricsPanel(Card):
    """Performance Metrics — center top panel."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__("Performance", parent)
        self.ber_row = MetricRow("BER")
        self.strict_ber_row = MetricRow("Strict BER")
        self.crc_row = StatusRow("CRC")
        self.margin_row = MetricRow("Margin")
        self.data_rate_row = MetricRow("Rate")

        self.body.addWidget(self.ber_row)
        self.body.addWidget(self.strict_ber_row)
        self.body.addWidget(self.crc_row)
        self.body.addWidget(self.margin_row)
        self.body.addWidget(self.data_rate_row)

    def refresh(self, state: RXAppState) -> None:
        sig = state.signal
        self.ber_row.setValue(f"{sig.ber:.4f}")
        self.strict_ber_row.setValue(f"{sig.strict_ber:.4f}")
        self.crc_row.setStatus(sig.crc_status, COLORS["green"] if sig.crc_status == "PASS" else COLORS["red"])
        self.margin_row.setValue(f"{sig.margin:.3f} V")
        self.data_rate_row.setValue(f"{sig.data_rate:.2f} kbps" if sig.data_rate > 0 else "— kbps")


class _SignalMonitorPanel(Card):
    """Signal Monitor — right top panel."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__("Signal", parent)
        self.pvo_row = MetricRow("PVo")
        self.vref_row = MetricRow("Vref")
        self.adc_vref_row = MetricRow("ADC Vref")
        self.vref_mode_row = MetricRow("Vref Mode")
        self.lux_row = MetricRow("Lux")

        self.body.addWidget(self.pvo_row)
        self.body.addWidget(self.vref_row)
        self.body.addWidget(self.adc_vref_row)
        self.body.addWidget(self.vref_mode_row)
        self.body.addWidget(self.lux_row)
        self._state = state

    def refresh(self, state: RXAppState) -> None:
        self._state = state
        sig = state.signal
        self.pvo_row.setValue(f"{sig.pvo:.3f} V")
        self.vref_row.setValue(f"{sig.vref:.3f} V")
        self.adc_vref_row.setValue(f"{sig.adc_vref:.3f} V")
        from gui_dev_v3.settings import SettingsManager
        mgr = SettingsManager("rx")
        vref_auto = mgr.get("link/vref_auto", False)
        self.vref_mode_row.setValue("Auto" if vref_auto else "Manual")
        self.lux_row.setValue(f"{sig.lux} lx")


class _SignalWaveformPanel(Card):
    """Signal Waveform — Digital Logic Analyzer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Signal Waveforms (Live)", parent)
        self.body.setSpacing(6)
        self.body.setContentsMargins(8, 4, 8, 4)

        self._ook = OOKWaveformWidget(parent=self)
        self._ook.setMinimumHeight(180)
        self.body.addWidget(self._ook, 1)

    def refresh(self, state: RXAppState) -> None:
        # Handled at 100 ms via refresh_telemetry
        pass

    def refresh_telemetry(self, state: RXAppState, last_sample_index: int) -> int:
        """Fetch new high-frequency samples and feed OOK widget."""
        sig = state.signal
        mode = state.mode
        has_signal = (state.serial_connected or mode == "simulated") and (
            sig.pvo > 0.01 or mode == "simulated"
        )

        if not has_signal:
            self._ook.clear()
            return last_sample_index

        if mode == "simulated":
            new_samples = state.get_new_simulation_samples(last_sample_index)
            for pvo, vref, margin, bit in new_samples:
                self._ook.push_bit(bit)
            if new_samples and state._simulation:
                last_sample_index = state._simulation._sample_counter
        else:
            # Physical mode fallback (sample snapshot from state)
            pvo = sig.pvo
            vref = sig.vref
            self._ook.set_from_pvo_vref(pvo, vref)

        return last_sample_index


class _BitDecodePanel(Card):
    """Bit Decode Panel showing symbol decode and synchronization status."""
    
    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__("Bit Decode", parent)
        self.sync_state_row = StatusRow("Sync State")
        self.symbol_error_row = MetricRow("Symbol Errors")
        self.manchester_row = StatusRow("Encoding")
        
        self.body.addWidget(self.sync_state_row)
        self.body.addWidget(self.symbol_error_row)
        self.body.addWidget(self.manchester_row)
        self.body.addStretch(1)
        
    def refresh(self, state: RXAppState) -> None:
        transfer = state.transfer
        stage = str(state.session.latest_transfer.status.value) if state.session.latest_transfer else "idle"
        is_active = state.is_receiving or "incomplete" in stage.lower()
        
        if is_active:
            self.sync_state_row.setStatus("LOCKED", COLORS["green"])
            self.symbol_error_row.setValue(f"{int(state.signal.ber * 1000)}")
            self.manchester_row.setStatus("4B5B OOK", COLORS["value"])
        else:
            self.sync_state_row.setStatus("SEARCHING", COLORS["muted"])
            self.symbol_error_row.setValue("—")
            self.manchester_row.setStatus("—", COLORS["muted"])


class _FileInfoPanel(Card):
    """Received File Info — right middle panel."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__("Received File Info", parent)
        self.filename_row = MetricRow("File Name")
        self.filesize_row = MetricRow("File Size")
        self.received_size_row = MetricRow("Received Size")
        self.pct_row = MetricRow("Completion")
        self.progress_bar = ProgressBar(0)

        self.body.addWidget(self.filename_row)
        self.body.addWidget(self.filesize_row)
        self.body.addWidget(self.received_size_row)
        self.body.addWidget(self.pct_row)
        self.body.addWidget(self.progress_bar)

    def refresh(self, state: RXAppState) -> None:
        transfer = state.transfer
        received_size = transfer.size_bytes * transfer.received_chunks // max(transfer.total_chunks, 1)

        self.filename_row.setValue(transfer.filename or "—")
        self.filesize_row.setValue(f"{transfer.size_bytes / 1024:.2f} KiB" if transfer.size_bytes else "—")
        self.received_size_row.setValue(f"{received_size / 1024:.2f} KiB" if received_size else "—")

        pct = state.progress_percent
        self.pct_row.setValue(f"{pct}%")
        self.progress_bar.set_percent(pct)


class _ActivityLogPanel(Card):
    """Recent Activity — full-width bottom panel."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__("Recent Activity", parent)
        self._log_table = ActivityLogTable(parent=self)
        self.body.addWidget(self._log_table, 1)

    def refresh(self, state: RXAppState) -> None:
        self._log_table.update_entries(state.activity_log)



class RXDashboardPage(QWidget):
    """Dashboard with live panels that auto-refresh from vlc_beta data."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        # Main layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 20)
        outer.setSpacing(12)

        # --- Top Row: 3 panels ---
        self._reception = _ReceptionStatusPanel(state)
        self._perf = _PerformanceMetricsPanel(state)
        self._signal_mon = _SignalMonitorPanel(state)

        top_grid = QHBoxLayout()
        top_grid.setSpacing(12)
        top_grid.addWidget(self._reception, 1)
        top_grid.addWidget(self._perf, 1)
        top_grid.addWidget(self._signal_mon, 1)
        outer.addLayout(top_grid)

        # --- Splitter for Middle & Bottom Rows ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # --- Middle Row: Waveform (50%) | Bit Decode (20%) | File Info (30%) ---
        mid_widget = QWidget()
        mid_grid = QHBoxLayout(mid_widget)
        mid_grid.setContentsMargins(0, 0, 0, 0)
        mid_grid.setSpacing(10)
        
        self._signal_waveform = _SignalWaveformPanel()
        self._bit_decode = _BitDecodePanel(state)
        self._file_info = _FileInfoPanel(state)

        mid_grid.addWidget(self._signal_waveform, 5)
        mid_grid.addWidget(self._bit_decode, 2)
        mid_grid.addWidget(self._file_info, 3)

        # --- Bottom Row: Activity Log ---
        self._activity_log = _ActivityLogPanel(state)
        
        splitter.addWidget(mid_widget)
        splitter.addWidget(self._activity_log)
        
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        
        outer.addWidget(splitter, 1)

        # High-frequency sampler (100 ms)
        self._last_sample_index = 0
        self._sample_timer = QTimer(self)
        self._sample_timer.timeout.connect(self._sample_waveform)
        self._sample_timer.start(100)

        # Initial refresh
        self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._state and self._state._simulation:
            self._last_sample_index = self._state._simulation._sample_counter
        if hasattr(self, "_sample_timer") and not self._sample_timer.isActive():
            self._sample_timer.start(100)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if hasattr(self, "_sample_timer") and self._sample_timer.isActive():
            self._sample_timer.stop()

    def shutdown(self) -> None:
        if hasattr(self, "_sample_timer"):
            self._sample_timer.stop()
            try:
                self._sample_timer.timeout.disconnect()
            except Exception:
                pass

    def _sample_waveform(self) -> None:
        if self._state is not None:
            self._last_sample_index = self._signal_waveform.refresh_telemetry(self._state, self._last_sample_index)

    def refresh(self, state: RXAppState | None = None) -> None:
        """Refresh all dashboard panels from current state. Called by shell timer."""
        if state is not None:
            self._state = state
        self._reception.refresh(self._state)
        self._perf.refresh(self._state)
        self._signal_mon.refresh(self._state)
        self._signal_waveform.refresh(self._state)
        self._bit_decode.refresh(self._state)
        self._file_info.refresh(self._state)
        self._activity_log.refresh(self._state)
