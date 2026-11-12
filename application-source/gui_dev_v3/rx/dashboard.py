"""RX Dashboard — live panels matching the VLC Receiver UI design image.

Layout:
┌──────────────────────────────────────────────────────────────┐
│ Top row: Reception Status | Performance Metrics | Signal     │
│ Middle row: Signal Waveform (60%) | Received File Info (40%) │
│ Bottom row: Recent Activity (full width)                     │
└──────────────────────────────────────────────────────────────┘

All panels refresh from live receiver hardware state every 1 second.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QGridLayout,
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
from gui_dev_v3.ui_foundation import PageIntro


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
        
        
        badge_layout.addStretch(1)
        self.badge = StatusBadge("IDLE", COLORS["muted"])
        badge_layout.addWidget(self.badge)
        self.body.addLayout(badge_layout)

        self.chunks_row = MetricRow("Chunks")
        self.body.addWidget(self.chunks_row)

        self.time_elapsed_row = MetricRow("Elapsed")
        self.body.addWidget(self.time_elapsed_row)
        
        self._state = state

    def refresh(self, state: RXAppState) -> None:
        self._state = state
        sig = state.signal
        transfer = state.transfer

        # A disconnected receiver must never be presented as READY.
        is_active = state.is_receiving and state.serial_connected
        if is_active:
            badge_text, badge_color = "RECEIVING", COLORS["green"]
        elif state.serial_connected:
            badge_text, badge_color = "READY", COLORS["green"]
        else:
            badge_text, badge_color = "DISCONNECTED", COLORS["red"]

        self.badge.setText(badge_text)
        self.badge.setStyleSheet(f"background: {badge_color}; color: #0b1016; border-radius: 10px; padding: 4px 9px; font-weight: 700; font-size: 11px;")
        self.chunks_row.setValue(
            f"{transfer.received_chunks} / {transfer.total_chunks}"
            if transfer.total_chunks > 0 else "—"
        )
        self.time_elapsed_row.setValue(sig.time_elapsed if sig.time_elapsed else "—")


class _PerformanceMetricsPanel(Card):
    """Performance Metrics — center top panel."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__("Performance", parent)
        self.ber_row = MetricRow("Method 2 BER")
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
        comparison = state.get_method2_comparison()
        if comparison is None:
            self.ber_row.setValue("Awaiting reference")
            self.strict_ber_row.setValue("Not measured")
        else:
            self.ber_row.setValue(
                f"{comparison['overlap_ber'] * 100:.4f} %"
                if comparison["overlap_ber"] is not None else "Not measurable"
            )
            self.strict_ber_row.setValue(
                f"{comparison['strict_ber'] * 100:.4f} %"
                if comparison["strict_ber"] is not None else "Not measurable"
            )
        transfer = state.transfer
        crc_status = (transfer.quality.crc_status if transfer.quality else "Unknown").strip().upper()
        crc_color = (
            COLORS["green"] if crc_status == "PASS"
            else COLORS["red"] if crc_status in {"FAIL", "FAILED", "CRC FAILED"}
            else COLORS["muted"]
        )
        self.crc_row.setStatus(crc_status or "—", crc_color)
        self.margin_row.setValue(f"{sig.margin:.3f} V")
        self.data_rate_row.setValue(
            f"{sig.data_rate:.2f} kbps"
            if sig.data_rate is not None and sig.data_rate > 0 else "—"
        )


class _SignalMonitorPanel(Card):
    """Signal Monitor — right top panel."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__("Signal", parent)
        self.pvo_row = MetricRow("PVo")
        self.vref_row = MetricRow("Vref")
        self.adc_vref_row = MetricRow("ADC Vref")
        self.vref_mode_row = MetricRow("Vref Mode")
        self.lux_row = MetricRow("Light estimate")
        self.lux_row.setToolTip("Uncalibrated relative estimate derived from PVo; this is not a lux-meter measurement.")
        self.lux_row.val.setToolTip("Uncalibrated relative estimate derived from PVo; this is not a lux-meter measurement.")

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
        self.adc_vref_row.setValue(
            f"{sig.adc_vref:.3f} V" if sig.adc_vref is not None else "—"
        )
        from gui_dev_v3.settings import SettingsManager
        mgr = SettingsManager("rx")
        vref_auto = mgr.get("link/vref_auto", False)
        self.vref_mode_row.setValue("Auto" if vref_auto else "Manual")
        self.lux_row.setValue(f"{sig.lux} (uncal.)")


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
        if not state.serial_connected or sig.pvo <= 0.01:
            self._ook.clear()
            return last_sample_index

        # The physical backend exposes the latest measured PVo/Vref snapshot.
        self._ook.set_from_pvo_vref(sig.pvo, sig.vref)
        return last_sample_index


class _BitDecodePanel(Card):
    """Bit Decode Panel showing symbol decode and synchronization status."""
    
    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__("Bit Decode", parent)
        self.sync_state_row = StatusRow("Sync State")
        self.symbol_error_row = MetricRow("Method 2 BER")
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
            comparison = state.get_method2_comparison()
            strict_ber = comparison.get("strict_ber") if comparison else None
            self.symbol_error_row.setValue(
                f"{strict_ber * 100:.4f} %"
                if strict_ber is not None else "Awaiting reference"
            )
            self.manchester_row.setStatus("4B5B OOK", COLORS["value"])
        else:
            self.sync_state_row.setStatus("SEARCHING", COLORS["muted"])
            self.symbol_error_row.setValue("—")
            self.manchester_row.setStatus("—", COLORS["muted"])


class _FileInfoPanel(Card):
    """Received File Info — compact two-column summary."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__("Received File Info", parent)
        self.body.setContentsMargins(12, 8, 12, 8)
        self.body.setSpacing(6)

        self.filename_row = MetricRow("File Name")
        self.filesize_row = MetricRow("File Size")
        self.received_size_row = MetricRow("Received Size")
        self.pct_row = MetricRow("Completion")
        self.progress_bar = ProgressBar(0)

        metrics = QGridLayout()
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(18)
        metrics.setVerticalSpacing(4)
        metrics.addWidget(self.filename_row, 0, 0, 1, 2)
        metrics.addWidget(self.filesize_row, 1, 0)
        metrics.addWidget(self.received_size_row, 1, 1)
        metrics.addWidget(self.pct_row, 2, 0)
        metrics.addWidget(self.progress_bar, 2, 1, Qt.AlignmentFlag.AlignVCenter)
        self.body.addLayout(metrics)

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
    """Reception overview; detailed live waveforms remain on the Signal page."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)

        outer.addWidget(PageIntro(
            "RECEIVER  /  MONITORING",
            "Reception overview",
            "Track link quality, signal levels, file progress, and decoder state.",
            self,
        ))

        # At-a-glance link and signal indicators remain grouped together.
        self._reception = _ReceptionStatusPanel(state)
        self._perf = _PerformanceMetricsPanel(state)
        self._signal_mon = _SignalMonitorPanel(state)
        top_grid = QHBoxLayout()
        top_grid.setSpacing(14)
        top_grid.addWidget(self._reception, 1)
        top_grid.addWidget(self._perf, 1)
        top_grid.addWidget(self._signal_mon, 1)
        outer.addLayout(top_grid)

        # The file is the main object being received; decoder state is
        # secondary context. Detailed live waveform analysis stays on Signal.
        detail_widget = QWidget()
        detail_grid = QHBoxLayout(detail_widget)
        detail_grid.setContentsMargins(0, 0, 0, 0)
        detail_grid.setSpacing(14)
        self._file_info = _FileInfoPanel(state)
        self._bit_decode = _BitDecodePanel(state)
        detail_grid.addWidget(self._file_info, 3)
        detail_grid.addWidget(self._bit_decode, 2)

        self._activity_log = _ActivityLogPanel(state)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(detail_widget)
        splitter.addWidget(self._activity_log)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)
        self._splitter = splitter
        self._detail_widget = detail_widget
        self._compact_layout = False

        self.refresh()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        """Keep the overview useful on short/high-DPI laptop work areas."""
        super().resizeEvent(event)
        compact = self.width() < 900 or self.height() < 620
        if compact == self._compact_layout:
            return
        self._compact_layout = compact

        self._perf.setVisible(not compact)
        self._signal_mon.setVisible(not compact)
        self._bit_decode.setVisible(not compact)
        self._activity_log.setVisible(not compact)
        self._file_info.filesize_row.setVisible(not compact)
        self._file_info.received_size_row.setVisible(not compact)
        if compact:
            self._file_info.body.setContentsMargins(12, 8, 12, 10)
            self._file_info.body.setSpacing(6)
        else:
            self._file_info.body.setContentsMargins(16, 14, 16, 16)
            self._file_info.body.setSpacing(10)
        self._file_info.setVisible(True)
        self._reception.setVisible(True)

    def refresh(self, state: RXAppState | None = None) -> None:
        """Refresh the overview panels from the current receiver state."""
        if state is not None:
            self._state = state
        self._reception.refresh(self._state)
        self._perf.refresh(self._state)
        self._signal_mon.refresh(self._state)
        self._bit_decode.refresh(self._state)
        self._file_info.refresh(self._state)
        self._activity_log.refresh(self._state)
