"""Signal Monitor — detailed signal analysis tab for VLC Receiver.

Layout (professional engineering dashboard):
┌──────────────────────────────────────────────────────────────────┐
│ LIVE SIGNAL STATUS                                              │
│ [PVo] [Vref] [Margin] [State] [Signal Quality] [Noise Level]    │
├─────────────────────────────┬──────────────────┬────────────────┤
│                             │ RECEIVER          │ MARGIN          │
│ SIGNAL WAVEFORMS (LIVE)     │ DIAGNOSTICS       │ ANALYSIS        │
│ (3 traces, 50%)             │ (4 sections)      │ (target/current │
│                              │                   │ /deviation/     │
│                              │                   │ status + bar)   │
├─────────────────────────────┼──────────────────┼────────────────┤
│ HISTORICAL TRENDS           │ TRANSFER          │ SIGNAL QUALITY  │
│ (TrendChart with tabs)      │ STATISTICS (LIVE) │ METRICS         │
│                              │ (6 rows + bar)    │ (6 bars)        │
├─────────────────────────────┴──────────────────┴────────────────┤
│ Mode: Physical  ● Connected  ● ACTIVE                           │
└──────────────────────────────────────────────────────────────────┘

High-frequency sampler (100 ms) feeds the waveform buffer.
1-second refresh updates all cards, tables, and trend data.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QDialog,
    QPushButton,
)

from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.models import SignalState, TransferRecord
from gui_dev_v3.rx.signal_widgets import (
    CircularGauge,
    MarginScaleBar,
    MetricCard,
    OOKWaveformWidget,
    QualityBar,
    SignalWaveform,
)
from gui_dev_v3.settings import SettingsManager
from gui_dev_v3.theme import COLORS
from gui_dev_v3.widgets import Card, ProgressBar, muted_label, panel_header, value_label


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(text: str) -> QTableWidgetItem:
    """Create a non-editable table item."""
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _make_table(rows: list[tuple[str, str]], col_labels: tuple[str, str] = ("Label", "Value")) -> QTableWidget:
    """Build a 2-column QTableWidget from (label, value) pairs."""
    table = QTableWidget(len(rows), 2)
    table.setHorizontalHeaderLabels(list(col_labels))
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(14)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.horizontalHeader().setStretchLastSection(False)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    table.setAlternatingRowColors(False)
    table.setShowGrid(False)
    table.setStyleSheet(
        "QTableWidget { background: transparent; color: #d1d5db; border: none; font-size: 9px; }"
        "QTableWidget::item { border: none; padding: 0px 4px; }"
        "QHeaderView::section { background: transparent; color: #8c99aa; border: none; font-size: 8px; font-weight: 700; padding: 1px 4px; }"
    )
    for row_idx, (label, value) in enumerate(rows):
        table.setItem(row_idx, 0, _make_item(label))
        table.setItem(row_idx, 1, _make_item(value))
    return table


def _update_table_dynamic(table: QTableWidget, rows: list[tuple[str, str]]) -> None:
    table.setRowCount(len(rows))
    for row_idx, (label, value) in enumerate(rows):
        lbl_item = table.item(row_idx, 0)
        if not lbl_item:
            lbl_item = _make_item(label)
            table.setItem(row_idx, 0, lbl_item)
        else:
            lbl_item.setText(label)
            
        val_item = table.item(row_idx, 1)
        if not val_item:
            val_item = _make_item(value)
            table.setItem(row_idx, 1, val_item)
        else:
            val_item.setText(value)
            
        if value in ("PASS", "ACTIVE", "READY", "STABLE"):
            val_item.setForeground(QColor("#22c55e"))
        elif value in ("FAIL", "INACTIVE", "OFFLINE"):
            val_item.setForeground(QColor("#ef4444"))
        else:
            val_item.setForeground(QColor("#d1d5db"))


class TransferStatsDialog(QDialog):
    def __init__(self, rows: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Full Transfer Statistics")
        self.resize(350, 400)
        self.setStyleSheet("background-color: #0f1923; color: #e0e0e0;")
        lo = QVBoxLayout(self)
        lo.setContentsMargins(16, 16, 16, 16)
        lo.setSpacing(12)
        
        table = _make_table(rows)
        table.setRowCount(len(rows))
        _update_table_dynamic(table, rows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lo.addWidget(table)
        
        btn = QPushButton("Close")
        btn.setObjectName("Primary")
        btn.setStyleSheet("background-color: #2196F3; color: white; padding: 6px 12px; border-radius: 4px;")
        btn.clicked.connect(self.accept)
        lo.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)


def _quality_from_signal(sig: SignalState) -> dict[str, int]:
    """Derive percentage quality metrics from signal state."""
    margin = sig.margin
    vref = sig.vref if sig.vref > 0 else 1.0
    target = sig.target_margin if sig.target_margin > 0 else 0.365

    # SNR-like: ratio of vref to margin noise estimate
    noise_est = max(abs(margin - target) * 0.1, 0.001)
    snr = min(100, int((vref / max(noise_est, 0.001)) * 5))

    # Signal stability: how close margin is to target
    deviation = abs(margin - target)
    stability = max(0, min(100, int(100 - (deviation / target) * 100)))

    # Amplitude stability: based on pvo relative to vref
    amp_stability = min(100, int((sig.pvo / max(vref, 0.001)) * 80)) if sig.pvo > 0 else 0

    # Jitter: inverse of stability
    jitter = max(0, min(100, 100 - stability))

    # Interference: derived from noise
    interference = max(0, min(100, int(noise_est * 200)))

    return {
        "snr": snr,
        "stability": stability,
        "amplitude": amp_stability,
        "jitter": jitter,
        "interference": interference,
    }


def _is_empty(sig: SignalState) -> bool:
    """Check if signal is in empty/offline state."""
    return sig.pvo == 0.0 and sig.vref == 0.0


def _separator() -> QFrame:
    """Thin horizontal line separator for diagnostics sections."""
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.HLine)
    frame.setFrameShadow(QFrame.Shadow.Plain)
    frame.setStyleSheet("background-color: #1A3152; max-height: 1px;")
    return frame


def _section_header(text: str) -> QLabel:
    """Uppercase blue section header for diagnostics panels."""
    label = QLabel(text.upper())
    label.setStyleSheet(
        "font-size: 10px; font-weight: 700; color: #60a5fa; "
        "letter-spacing: 1px; background: transparent;"
    )
    return label


def _diag_row(label_text: str, value_label: QLabel) -> QWidget:
    """Build a horizontal row with muted label and value label for diagnostics."""
    w = QWidget()
    w.setObjectName("Card")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lbl = QLabel(label_text)
    lbl.setStyleSheet("color: #708090; font-size: 10px; background: transparent;")
    lay.addWidget(lbl)
    lay.addStretch(1)
    lay.addWidget(value_label)
    return w


def _set_status_label(label: QLabel, text: str, status_type: str) -> None:
    """Helper to update a label text and its stylesheet color."""
    label.setText(text)
    if status_type == "green":
        label.setStyleSheet("color: #22c55e; font-size: 10px; font-weight: 600; background: transparent;")
    elif status_type == "red":
        label.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: 600; background: transparent;")
    elif status_type == "amber":
        label.setStyleSheet("color: #f59e0b; font-size: 10px; font-weight: 600; background: transparent;")
    else:
        label.setStyleSheet("color: #d1d5db; font-size: 10px; font-weight: 600; background: transparent;")


# ---------------------------------------------------------------------------
# SignalMonitorPage
# ---------------------------------------------------------------------------


class SignalMonitorPage(QWidget):
    """Detailed signal analysis tab with live waveform, metrics, and diagnostics."""

    def __init__(self, state: RXAppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._settings_mgr = SettingsManager("rx")
        self._paused = False
        self._time_window = 30  # seconds for waveform
        self._waveform_buffer: list = []
        self._pvo_hist: list[float] = []
        self._vref_hist: list[float] = []
        self._margin_hist: list[float] = []
        self._last_ook_chunk: int = -1  # track chunk index for OOK update

        self._build_ui()

        # High-frequency sampler (100 ms)
        self._sample_timer = QTimer(self)
        self._sample_timer.timeout.connect(self._sample_waveform)
        self._sample_timer.start(100)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._state and self._state._simulation:
            self._last_ook_chunk = self._state._simulation._sample_counter
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

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Build the complete signal monitoring dashboard layout."""
        self.setStyleSheet("background-color: #0f1923; color: #e0e0e0;")

        outer = QVBoxLayout(self)
        outer.setSpacing(8)
        outer.setContentsMargins(12, 12, 12, 12)

        # Row 1 — 6 status cards (4 MetricCards + 2 QualityBars)
        outer.addLayout(self._build_top_metrics())

        # Row 2 — Waveform / Diagnostics / Margin Analysis (7:3:2)
        outer.addWidget(self._build_middle_row(), 1)

        # Row 3 — Transfer Statistics / Quality Metrics (1:1)
        outer.addWidget(self._build_bottom_row(), 1)

    # --- Row 1: Metric Cards + QualityBars ---

    def _build_top_metrics(self) -> QVBoxLayout:
        """Build top row with 4 MetricCards and 2 CircularGauges in a compact 1×6 grid."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title = QLabel("LIVE SIGNAL STATUS")
        title.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #60a5fa; "
            "background: transparent; padding: 0px; margin: 0px;"
        )
        layout.addWidget(title)

        # 1×6 grid: all 6 widgets in a single row for compactness
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        self._metric_pvo = MetricCard("PVo (TIA Out)", color="#22c55e")
        self._metric_vref = MetricCard("Vref (Threshold)", color="#3b82f6")
        self._metric_margin = MetricCard("Margin (PVo\u2212Vref)", color="#f59e0b")
        self._metric_state = MetricCard("State", color="#26c6da")
        self._quality_top = CircularGauge("Signal Quality")
        self._noise_top = CircularGauge("Noise Level", inverted=True)

        for w in [
            self._metric_pvo, self._metric_vref, self._metric_margin,
            self._metric_state, self._quality_top, self._noise_top,
        ]:
            w.setObjectName("Card")

        # Single row: all 6 widgets
        grid.addWidget(self._metric_pvo, 0, 0)
        grid.addWidget(self._metric_vref, 0, 1)
        grid.addWidget(self._metric_margin, 0, 2)
        grid.addWidget(self._metric_state, 0, 3)
        grid.addWidget(self._quality_top, 0, 4)
        grid.addWidget(self._noise_top, 0, 5)

        layout.addLayout(grid)
        return layout

    # --- Row 2: Waveform / Diagnostics / Margin Analysis ---

    def _build_middle_row(self) -> QSplitter:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: Analog and digital traces stacked vertically (stretch 7)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self._ook_widget = OOKWaveformWidget(parent=left_widget)
        self._ook_widget.setMinimumHeight(280)
        left_layout.addWidget(self._ook_widget, 1)

        splitter.addWidget(left_widget)

        # Center: Receiver Diagnostics (stretch 3)
        diag_widget = self._build_diagnostics_panel()
        diag_card = Card("Receiver Diagnostics")
        diag_card.body.addWidget(diag_widget)
        splitter.addWidget(diag_card)

        # Right: Margin Analysis (stretch 2)
        margin_widget = self._build_margin_analysis()
        margin_card = Card("Margin Analysis")
        margin_card.body.addWidget(margin_widget)
        splitter.addWidget(margin_card)

        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([460, 300, 300])
        return splitter

    def _build_diagnostics_panel(self) -> QWidget:
        """Build receiver diagnostics panel as a flat list matching the screenshot."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._diag_labels: dict[str, QLabel] = {}

        rows = [
            ("ADC Value (Raw)", "adc_raw"),
            ("ADC Voltage", "adc_voltage"),
            ("Comparator Output", "comparator"),
            ("Threshold (Vref)", "threshold_vref"),
            ("Photodiode Status", "photodiode"),
            ("Ambient Light (Lux)", "ambient_light"),
            ("Supply Voltage", "supply_voltage"),
            ("ADC State", "adc_state"),
            ("Auto Vref Mode", "vref_mode"),
            ("Vref Target", "vref_target"),
            ("Vref Error", "vref_error"),
        ]

        for label_text, key in rows:
            val = QLabel("\u2014")
            val.setStyleSheet(
                "color: #d1d5db; font-size: 10px; font-weight: 600; "
                "background: transparent;"
            )
            self._diag_labels[key] = val
            layout.addWidget(_diag_row(label_text, val))

        layout.addStretch(1)
        return widget

    def _build_margin_analysis(self) -> QWidget:
        """Build margin analysis panel with flat metrics and scale bar."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Target Margin, Current Margin, Margin Deviation, Status rows
        self._margin_target_label = value_label("\u2014", color=COLORS["muted"])
        self._margin_current_label = value_label("\u2014", color=COLORS["muted"])
        self._margin_deviation_label = value_label("\u2014", color=COLORS["muted"])
        self._margin_status_label = value_label("\u2014", color=COLORS["muted"])

        layout.addWidget(_row_widget("Target Margin", self._margin_target_label))
        layout.addWidget(_row_widget("Current Margin", self._margin_current_label))
        layout.addWidget(_row_widget("Margin Deviation", self._margin_deviation_label))
        layout.addWidget(_row_widget("Status", self._margin_status_label))

        # MarginScaleBar with zone markers
        self._margin_scale = MarginScaleBar()
        layout.addWidget(self._margin_scale)

        layout.addStretch(1)
        return widget

    # --- Row 3: Historical Trends / Transfer Statistics / Quality Metrics ---

    def _build_bottom_row(self) -> QSplitter:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # --- 1. Transfer Statistics (ProgressBar on top + compact 6-row table) ---
        transfer_widget = self._build_transfer_stats()
        transfer_card = Card("Transfer Statistics (Live)")
        transfer_card.body.addWidget(transfer_widget)
        splitter.addWidget(transfer_card)

        # --- 2. Signal Quality Metrics (6 QualityBars) ---
        quality_widget = self._build_quality_metrics()
        quality_card = Card("Signal Quality Metrics")
        quality_card.body.addWidget(quality_widget)
        splitter.addWidget(quality_card)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([450, 450])
        return splitter

    def _build_transfer_stats(self) -> QWidget:
        """Build transfer statistics panel with 10-row table and progress bar at the bottom."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Compact 10-row table
        transfer_rows = [
            ("File Name", "\u2014"),
            ("Chunks Received", "\u2014"),
            ("Packets", "\u2014"),
            ("CRC Status", "\u2014"),
            ("BER (Live)", "\u2014"),
            ("Bit Errors", "\u2014"),
            ("Retry Count", "\u2014"),
            ("Packet Loss", "\u2014"),
            ("Elapsed Time", "\u2014"),
            ("Data Rate", "\u2014"),
        ]
        self._transfer_table = _make_table(transfer_rows, col_labels=("Metric", "Value"))
        layout.addWidget(self._transfer_table)

        self._view_more_btn = QPushButton("View Full Statistics...")
        self._view_more_btn.setObjectName("Secondary")
        self._view_more_btn.setStyleSheet(
            "QPushButton { background-color: #1f2937; color: #e5e7eb; border: 1px solid #374151; "
            "border-radius: 4px; padding: 4px 8px; font-size: 10px; font-weight: 600; }"
            "QPushButton:hover { background-color: #374151; color: #ffffff; }"
        )
        self._view_more_btn.clicked.connect(self._on_view_more_stats)
        layout.addWidget(self._view_more_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

        # Progress bar at bottom
        progress_layout = QHBoxLayout()
        progress_layout.setContentsMargins(4, 0, 4, 0)
        progress_layout.setSpacing(8)

        self._progress_text_label = QLabel("Progress: 0%")
        self._progress_text_label.setStyleSheet(
            "color: #FFFFFF; font-size: 10px; font-weight: bold; background: transparent;"
        )
        progress_layout.addWidget(self._progress_text_label)

        self._transfer_progress = ProgressBar(0, color=COLORS.get("accent", "#3b82f6"))
        progress_layout.addWidget(self._transfer_progress, stretch=1)
        layout.addLayout(progress_layout)

        return widget

    def _on_view_more_stats(self) -> None:
        if hasattr(self, "_last_all_rows") and self._last_all_rows:
            dialog = TransferStatsDialog(self._last_all_rows, self)
            dialog.exec()

    def _build_quality_metrics(self) -> QWidget:
        """Build 6 QualityBars for detailed signal quality metrics matching screenshot."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._quality_bars: dict[str, QualityBar] = {
            "snr": QualityBar("SNR (Est.)"),
            "stability": QualityBar("Signal Stability"),
            "amplitude": QualityBar("Amplitude Stability"),
            "threshold": QualityBar("Threshold Crossings", show_bar=False),
            "jitter": QualityBar("Jitter (Est.)"),
            "interference": QualityBar("Interference Level"),
        }

        for bar in self._quality_bars.values():
            layout.addWidget(bar)

        layout.addStretch(1)
        return widget

    # --- Status Bar Removed ---

    # ------------------------------------------------------------------
    # High-Frequency Sampler
    # ------------------------------------------------------------------

    def _sample_waveform(self) -> None:
        """Append current signal samples to waveform buffer (100 ms interval)."""
        if self._paused:
            return
        sig = self._state.signal
        mode = self._state.mode

        if mode == "simulated" and self._state._simulation:
            if self._last_ook_chunk <= 0:
                self._last_ook_chunk = self._state._simulation._sample_counter
            new_samples = self._state.get_new_simulation_samples(self._last_ook_chunk)
            for pvo, vref, margin, bit in new_samples:
                self._ook_widget.push_bit(bit)
                self._pvo_hist.append(pvo)
                self._vref_hist.append(vref)
                self._margin_hist.append(margin)
            if new_samples:
                self._last_ook_chunk = self._state._simulation._sample_counter
        else:
            pvo = sig.pvo
            vref = sig.vref
            margin = sig.margin
            self._ook_widget.set_from_pvo_vref(pvo, vref)
            self._pvo_hist.append(pvo)
            self._vref_hist.append(vref)
            self._margin_hist.append(margin)

        # Cap history lists to prevent growth
        for hist in (self._pvo_hist, self._vref_hist, self._margin_hist):
            if len(hist) > 60:
                hist[:] = hist[-60:]

    # ------------------------------------------------------------------
    # 1-second Refresh (called by shell timer)
    # ------------------------------------------------------------------

    def refresh(self, state: RXAppState) -> None:
        """Update all widgets from the latest state. Called every 1 second."""
        sig = state.signal
        transfer = state.transfer
        quality = transfer.quality
        empty = _is_empty(sig)

        # --- Top row: 4 MetricCards + 2 CircularGauges ---
        if empty:
            self._metric_pvo.set_value("0.00 V")
            self._metric_vref.set_value("0.00 V")
            self._metric_margin.set_value("0.00 V")
            self._metric_state.set_value("OFFLINE")
            self._metric_state.set_value_color("#708090")
            self._metric_state.set_center_footer("No hardware")
            self._quality_top.set_percent(0)
            self._noise_top.set_percent(0)
        else:
            self._metric_pvo.set_value(
                f"{sig.pvo:.2f} V",
                sparkline_data=self._pvo_hist[-20:] if self._pvo_hist else None,
                min_val=f"{min(self._pvo_hist):.2f} V" if self._pvo_hist else None,
                max_val=f"{max(self._pvo_hist):.2f} V" if self._pvo_hist else None,
            )
            self._metric_vref.set_value(
                f"{sig.vref:.2f} V",
                sparkline_data=self._vref_hist[-20:] if self._vref_hist else None,
                min_val=f"{min(self._vref_hist):.2f} V" if self._vref_hist else None,
                max_val=f"{max(self._vref_hist):.2f} V" if self._vref_hist else None,
            )
            self._metric_margin.set_value(
                f"{sig.margin:.2f} V",
                sparkline_data=self._margin_hist[-20:] if self._margin_hist else None,
                min_val=f"{min(self._margin_hist):.2f} V" if self._margin_hist else None,
                max_val=f"{max(self._margin_hist):.2f} V" if self._margin_hist else None,
            )

            # State card: READY (green) or OFFLINE (gray)
            if state.serial_connected:
                self._metric_state.set_value("READY")
                self._metric_state.set_value_color("#22c55e")
                self._metric_state.set_center_footer("Receiving possible")
            else:
                self._metric_state.set_value("OFFLINE")
                self._metric_state.set_value_color("#708090")
                self._metric_state.set_center_footer("No hardware")

            # Signal Quality circular gauge
            quality_pct = min(100, int((sig.margin / 0.72) * 100)) if sig.margin > 0 else 0
            self._quality_top.set_percent(quality_pct)

            # Noise Level circular gauge
            noise_est = abs(sig.margin - sig.target_margin) * 0.1 if sig.target_margin > 0 else 0
            noise_val = min(100, max(0, int(noise_est * 200)))
            self._noise_top.set_percent(noise_val)

        # --- Diagnostics Panel ---
        if empty:
            for key in self._diag_labels:
                _set_status_label(self._diag_labels[key], "\u2014", "default")
        else:
            adc_raw = int(sig.pvo / 3.3 * 4096)
            comp = "HIGH" if sig.pvo > sig.vref else "LOW"
            photo_status = "ACTIVE" if sig.pvo > 0.01 else "INACTIVE"
            vref_target = f"{sig.pvo - sig.target_margin:.2f} V"
            vref_error = f"{sig.vref - (sig.pvo - sig.target_margin):+.2f} V"

            _set_status_label(self._diag_labels["adc_raw"], str(adc_raw), "default")
            _set_status_label(self._diag_labels["adc_voltage"], f"{sig.pvo:.2f} V", "default")
            _set_status_label(self._diag_labels["comparator"], comp, "default")
            _set_status_label(self._diag_labels["threshold_vref"], f"{sig.vref:.2f} V", "default")
            _set_status_label(self._diag_labels["photodiode"], photo_status, "green" if photo_status == "ACTIVE" else "red")
            _set_status_label(self._diag_labels["ambient_light"], f"{sig.lux} lx", "default")
            _set_status_label(self._diag_labels["supply_voltage"], f"{sig.adc_vref:.2f} V", "default")
            _set_status_label(self._diag_labels["adc_state"], "STABLE", "green")
            _set_status_label(self._diag_labels["vref_mode"], "AUTO", "default")
            _set_status_label(self._diag_labels["vref_target"], vref_target, "default")
            _set_status_label(self._diag_labels["vref_error"], vref_error, "default")

        # --- Margin Analysis ---
        if empty:
            self._margin_target_label.setText("\u2014")
            self._margin_current_label.setText("\u2014")
            self._margin_deviation_label.setText("\u2014")
            self._margin_status_label.setText("\u2014")
            self._margin_scale.set_margin(None)
        else:
            target = sig.target_margin
            current = sig.margin
            deviation = current - target
            dev_str = f"{deviation:+.3f} V"
            dev_color = "#22c55e" if abs(deviation) < 0.02 else "#f59e0b"

            status_pass = abs(deviation) < 0.02
            status_text = "PASS" if status_pass else "FAIL"
            status_color = "#22c55e" if status_pass else "#ef4444"

            self._margin_target_label.setText(f"{target:.3f} V")
            self._margin_target_label.setStyleSheet("color: #d1d5db; font-size: 10px; font-weight: 600; background: transparent;")
            
            self._margin_current_label.setText(f"{current:.3f} V")
            self._margin_current_label.setStyleSheet("color: #22c55e; font-size: 10px; font-weight: 600; background: transparent;")
            
            self._margin_deviation_label.setText(dev_str)
            self._margin_deviation_label.setStyleSheet(
                f"color: {dev_color}; font-weight: 600; background: transparent; font-size: 10px;"
            )
            self._margin_status_label.setText(status_text)
            self._margin_status_label.setStyleSheet(
                f"color: {status_color}; font-weight: 600; background: transparent; font-size: 10px;"
            )
            self._margin_scale.set_margin(current)



        # --- Transfer Statistics (10 rows) ---
        if empty or transfer.tid == 0:
            transfer_rows = [
                ("File Name", "\u2014"),
                ("Chunks Received", "\u2014"),
                ("Packets", "\u2014"),
                ("CRC Status", "\u2014"),
                ("BER (Live)", "\u2014"),
                ("Bit Errors", "\u2014"),
                ("Retry Count", "\u2014"),
                ("Packet Loss", "\u2014"),
                ("Elapsed Time", "\u2014"),
                ("Data Rate", "\u2014"),
            ]
            self._transfer_progress.set_percent(0)
            self._progress_text_label.setText("Progress: 0%")
        else:
            received = transfer.received_chunks
            total = transfer.total_chunks
            pct = int(received / max(total, 1) * 100) if total > 0 else 0

            packet_loss = 0.0
            if total > 0:
                missing = total - received
                packet_loss = (missing / total) * 100.0

            transfer_rows = [
                ("File Name", transfer.filename or "\u2014"),
                ("Chunks Received", f"{received} / {total}"),
                ("Packets", str(received + quality.compared_bytes)),
                ("CRC Status", quality.crc_status or "\u2014"),
                ("BER (Live)", f"{quality.strict_ber:.4f}"),
                ("Bit Errors", str(quality.bit_errors)),
                ("Retry Count", "0"),
                ("Packet Loss", f"{packet_loss:.2f} %"),
                ("Elapsed Time", transfer.time_label or "\u2014"),
                ("Data Rate", f"{sig.data_rate:.2f} kbps"),
            ]
            self._transfer_progress.set_percent(pct)
            self._progress_text_label.setText(f"Progress: {pct}%")

        self._last_all_rows = transfer_rows
        
        stat_mapping = [
            ("filename", True),
            ("chunks", True),
            ("packets", True),
            ("crc", True),
            ("ber", True),
            ("bit_errors", False),
            ("retry_count", False),
            ("packet_loss", False),
            ("elapsed", True),
            ("data_rate", False),
        ]
        
        preview_rows = []
        for idx, (key, default_val) in enumerate(stat_mapping):
            is_visible = self._settings_mgr.get(f"display_stats/{key}", default_val)
            if is_visible:
                preview_rows.append(transfer_rows[idx])
                
        _update_table_dynamic(self._transfer_table, preview_rows)

        # --- Quality Metrics ---
        if empty:
            for bar in self._quality_bars.values():
                bar.set_value_text("\u2014")
                bar.set_percent(0)
        else:
            q = _quality_from_signal(sig)
            target = sig.target_margin if sig.target_margin > 0 else 0.365
            deviation = abs(sig.margin - target)
            stability = max(0, min(100, int(100 - (deviation / target) * 100)))
            
            # SNR calculation in dB: 20 * log10(Vref / deviation)
            vref_val = max(sig.vref, 0.01)
            deviation_val = max(deviation, 0.001)
            snr_db = max(0.0, min(40.0, 20.0 * math.log10(vref_val / deviation_val)))
            snr_pct = min(100, int((snr_db / 40.0) * 100))

            amp_stability = min(100, int((sig.pvo / max(sig.vref, 0.001)) * 80)) if sig.pvo > 0 else 0
            threshold_crossings = received + quality.compared_bytes

            jitter_ns = max(0.1, min(50.0, (100.0 - stability) * 0.5))
            jitter_pct = min(100, int((jitter_ns / 50.0) * 100))

            interference_pct = min(100, int(deviation * 20))

            self._quality_bars["snr"].set_value_text(f"{snr_db:.1f} dB")
            self._quality_bars["snr"].set_percent(snr_pct)

            self._quality_bars["stability"].set_value_text(f"{stability} %")
            self._quality_bars["stability"].set_percent(stability)

            self._quality_bars["amplitude"].set_value_text(f"{amp_stability} %")
            self._quality_bars["amplitude"].set_percent(amp_stability)

            self._quality_bars["threshold"].set_value_text(str(threshold_crossings))
            self._quality_bars["threshold"].set_percent(0)

            self._quality_bars["jitter"].set_value_text(f"{jitter_ns:.1f} ns")
            self._quality_bars["jitter"].set_percent(jitter_pct)
            self._quality_bars["jitter"].set_inverted(True)

            self._quality_bars["interference"].set_value_text("Low" if interference_pct < 30 else "Medium" if interference_pct < 60 else "High")
            self._quality_bars["interference"].set_percent(interference_pct)
            self._quality_bars["interference"].set_inverted(True)


# ---------------------------------------------------------------------------
# Internal helper: 2-column label:value row as a QWidget
# ---------------------------------------------------------------------------


def _row_widget(label: str, value_widget: QWidget) -> QWidget:
    """Build a horizontal row with a muted label and a value widget."""
    from PySide6.QtWidgets import QHBoxLayout, QLabel

    w = QWidget()
    w.setObjectName("Card")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lbl = QLabel(label)
    lbl.setObjectName("Muted")
    lay.addWidget(lbl)
    lay.addStretch(1)
    lay.addWidget(value_widget)
    return w
