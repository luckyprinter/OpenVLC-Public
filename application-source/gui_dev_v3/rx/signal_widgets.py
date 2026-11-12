"""Polished professional engineering dashboard widgets for VLC/LiFi receiver signal monitoring.

Visual style: dark-themed professional lab software (Saleae Logic Analyzer / Keysight BenchVue / SDR++).
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np
import pyqtgraph as pg
import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from gui_dev_v3.theme import COLORS

pg.setConfigOptions(antialias=True)
pg.setConfigOptions(useOpenGL=False)

# ── Palette constants ─────────────────────────────────────────────────
# These override theme defaults for a consistent, instrument-grade look.

_CLR_BG = "#08111D"
_CLR_PANEL = "#0F1B2D"
_CLR_PANEL_ALT = "#132238"
_CLR_BORDER = "#1A3152"
_CLR_WHITE = "#FFFFFF"
_CLR_MUTED = "#708090"

_CLR_PVO = "#5CE65C"
_CLR_VREF = "#4EA1FF"
_CLR_MARGIN = "#FFC247"
_CLR_FAIL = "#FF5C5C"

_CLR_GREEN = "#22c55e"
_CLR_AMBER = "#f59e0b"
_CLR_RED = "#ef4444"

def _trace_color(name: str) -> QColor:
    """Return the QColor for a trace name."""
    if name == "pvo":
        return QColor(_CLR_PVO)
    if name == "vref":
        return QColor(_CLR_VREF)
    return QColor(_CLR_MARGIN)


def _trace_label(name: str) -> str:
    """Return the display label for a trace name."""
    if name == "pvo":
        return "PVo"
    if name == "vref":
        return "Vref"
    return "Margin"


def _font(size: int, weight: int = QFont.Normal) -> QFont:
    """Create a QFont with the project's font stack."""
    f = QFont("Inter", size)
    f.setWeight(weight)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def _elide_text(text: str, font: QFont, max_width: int) -> str:
    """Elide text to fit within max_width pixels."""
    fm = QFontMetrics(font)
    return fm.elidedText(text, Qt.ElideRight, max_width)


# ---------------------------------------------------------------------------
# 1. MetricCard
# ---------------------------------------------------------------------------

class MetricCard(QWidget):
    """Dark panel card with label, value, and sparkline.

    Compact height ~70px. Rendered via QPainter for a crisp instrument-panel look.
    """

    def __init__(self, label: str, value: str = "—",
                 color: str | None = None, value_color: str | None = None) -> None:
        super().__init__()
        self._label_text = label
        self._value_text = str(value)
        self._chart_color = QColor(color) if color else QColor(_CLR_PVO)
        self._value_color = QColor(value_color) if value_color else None
        self._center_footer = ""
        self._sparkline_data: list[float] = []
        self._min_text: str | None = None
        self._max_text: str | None = None

        self.setMinimumHeight(55)
        self.setMinimumWidth(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ── public api ──────────────────────────────────────────────────────

    def set_value(self, value: float | str,
                  sparkline_data: list[float] | None = None,
                  min_val: float | str | None = None,
                  max_val: float | str | None = None) -> None:
        """Update displayed value and optional sparkline / min / max."""
        if value in (None, "—", "") or (isinstance(value, float) and math.isnan(value)):
            self._value_text = "—"
        else:
            self._value_text = str(value)
        if sparkline_data is not None:
            self._sparkline_data = list(sparkline_data)
        if min_val is not None:
            self._min_text = str(min_val)
        if max_val is not None:
            self._max_text = str(max_val)
        self.update()

    def set_value_color(self, color: str | QColor | None) -> None:
        """Set custom color for the value text (useful for state colors)."""
        self._value_color = QColor(color) if color else None
        self.update()

    def set_center_footer(self, text: str) -> None:
        """Set a centered footer text instead of Min/Max."""
        self._center_footer = text
        self.update()

    # ── paint ───────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()

        # ── background + border (8px rounded for premium feel) ──────────
        p.setPen(QPen(QColor(_CLR_BORDER), 1))
        p.setBrush(QColor(_CLR_PANEL))
        p.drawRoundedRect(0.5, 0.5, w - 1, h - 1, 8, 8)

        pad = 12
        inner_w = w - 2 * pad

        # ── label (top, small) ─────────────────────────────────────────
        label_font = _font(9, QFont.Medium)
        p.setFont(label_font)
        p.setPen(self._chart_color)
        p.drawText(pad, 6, inner_w, 14, Qt.AlignLeft | Qt.AlignVCenter,
                   self._label_text.upper())

        # ── value (middle, compact) ────────────────────────────────────
        value_pt = 18
        value_font = _font(value_pt, QFont.Bold)
        p.setFont(value_font)
        if self._value_color:
            p.setPen(self._value_color)
        else:
            p.setPen(QColor(_CLR_WHITE))

        value_str = self._value_text
        fm = QFontMetrics(value_font)
        if fm.horizontalAdvance(value_str) > inner_w:
            value_str = _elide_text(value_str, value_font, inner_w)

        value_y = 20
        value_h = value_pt + 4
        p.drawText(pad, value_y, inner_w, value_h,
                   Qt.AlignLeft | Qt.AlignVCenter, value_str)

        p.end()


class CircularGauge(QWidget):
    """Circular/semi-circular gauge drawing a 270-degree arc with QPainter.

    Displays a title, a circular progress arc, a center percentage value,
    and a quality rating subtext at the bottom.
    """

    def __init__(self, label: str, value: float = 0.0, inverted: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label_text = label
        self._percent = value
        self._inverted = inverted
        self._available = True

        self.setMinimumHeight(70)
        self.setMinimumWidth(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_percent(self, value: float) -> None:
        """Update the percentage (0-100) and redraw."""
        self._percent = max(0.0, min(100.0, value))
        self.update()

    def set_available(self, available: bool) -> None:
        """Show an unavailable state instead of a fabricated zero reading."""
        self._available = available
        self.update()

    def _color(self) -> QColor:
        if not self._available:
            return QColor(_CLR_MUTED)
        pct = self._percent
        if self._inverted:
            # For noise level: low noise is good (green), high noise is bad (red)
            if pct < 30:
                return QColor(_CLR_GREEN)
            if pct < 60:
                return QColor(_CLR_AMBER)
            return QColor(_CLR_RED)
        else:
            # For signal quality: high quality is good (green), low is bad (red)
            if pct > 70:
                return QColor(_CLR_GREEN)
            if pct > 40:
                return QColor(_CLR_AMBER)
            return QColor(_CLR_RED)

    def _subtext(self) -> str:
        if not self._available:
            return "Offline"
        pct = self._percent
        if self._inverted:
            if pct < 30:
                return "Low"
            if pct < 60:
                return "Medium"
            return "High"
        else:
            if pct > 70:
                return "Excellent"
            if pct > 40:
                return "Good"
            return "Fair"

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()

        # Draw card background and border
        p.setPen(QPen(QColor(_CLR_BORDER), 1))
        p.setBrush(QColor(_CLR_PANEL))
        p.drawRoundedRect(0.5, 0.5, w - 1, h - 1, 8, 8)

        # Title
        pad = 12
        inner_w = w - 2 * pad
        label_font = _font(9, QFont.Medium)
        p.setFont(label_font)
        p.setPen(QColor(_CLR_MUTED))
        p.drawText(pad, 6, inner_w, 14, Qt.AlignHCenter | Qt.AlignVCenter,
                   self._label_text.upper())

        # Arc dimensions
        arc_d = min(inner_w, 36)
        arc_x = (w - arc_d) / 2
        arc_y = 22
        arc_rect = (arc_x, arc_y, arc_d, arc_d)

        # Draw background arc track
        pen_w = 4
        track_pen = QPen(QColor(_CLR_PANEL_ALT), pen_w)
        track_pen.setCapStyle(Qt.RoundCap)
        p.setPen(track_pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(*arc_rect, 225 * 16, -270 * 16)

        # Draw foreground progress arc
        val_color = self._color()
        val_pen = QPen(val_color, pen_w)
        val_pen.setCapStyle(Qt.RoundCap)
        p.setPen(val_pen)
        span_angle = -270 * (self._percent / 100.0) if self._available else 0
        p.drawArc(*arc_rect, 225 * 16, int(span_angle * 16))

        # Center value text (e.g. 92%)
        val_font = _font(11, QFont.Bold)
        p.setFont(val_font)
        p.setPen(QColor(_CLR_WHITE))
        pct_str = f"{self._percent:.0f}%" if self._available else "—"
        p.drawText(int(arc_x), int(arc_y), int(arc_d), int(arc_d),
                   Qt.AlignCenter, pct_str)

        # Subtext at the bottom
        sub_font = _font(9, QFont.Medium)
        p.setFont(sub_font)
        p.setPen(val_color)
        sub_txt = self._subtext()
        p.drawText(pad, h - 16, inner_w, 12, Qt.AlignHCenter | Qt.AlignVCenter,
                   sub_txt)

        p.end()


class SignalWaveform(QWidget):
    """Scrolling trend of measured PVo, Vref, and margin telemetry.

    This plots the actual values reported by the receiver's low-rate status
    telemetry. It is not an oscilloscope trace or a decoded OOK bit waveform.
    """

    MAX_SAMPLES = 600  # bounded trend history; default sampling is one second
    refresh_rate_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paused = False
        self._time_window = 10.0  # 10 s default to match image
        self._dt = 1.0  # receiver status telemetry refreshes once per second
        self._buffer: list[tuple[float, float, float]] = []
        self._times: list[float] = []
        self._playback_mode = False
        self._updating_range = False

        self._init_ui()
        self._init_plot()

    # ── ui construction ─────────────────────────────────────────────────

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # Top row: Header + Checkboxes
        top_row = QHBoxLayout()
        top_row.setContentsMargins(8, 4, 8, 4)

        header = QLabel("PVo / Vref TELEMETRY TREND")
        header.setStyleSheet(f"color: {_CLR_GREEN}; font-weight: bold; "
                             f"font-size: 12px; background: transparent;")
        top_row.addWidget(header)
        top_row.addStretch()

        # Checkboxes
        self._pvo_cb = QCheckBox("PVo")
        self._pvo_cb.setChecked(True)
        self._pvo_cb.setStyleSheet(f"QCheckBox {{ color: {_CLR_PVO}; font-weight: bold; font-size: 10px; background: transparent; }}")
        self._pvo_cb.toggled.connect(self._on_trace_toggle)
        top_row.addWidget(self._pvo_cb)

        self._vref_cb = QCheckBox("Vref")
        self._vref_cb.setChecked(True)
        self._vref_cb.setStyleSheet(f"QCheckBox {{ color: {_CLR_VREF}; font-weight: bold; font-size: 10px; background: transparent; }}")
        self._vref_cb.toggled.connect(self._on_trace_toggle)
        top_row.addWidget(self._vref_cb)

        self._margin_cb = QCheckBox("Margin")
        self._margin_cb.setChecked(False)
        self._margin_cb.setStyleSheet(f"QCheckBox {{ color: {_CLR_MARGIN}; font-weight: bold; font-size: 10px; background: transparent; }}")
        self._margin_cb.toggled.connect(self._on_trace_toggle)
        top_row.addWidget(self._margin_cb)

        main_layout.addLayout(top_row)

        # Body row: Plot (left) + Side Controls (right)
        body_row = QHBoxLayout()
        body_row.setSpacing(8)

        # Plot widget
        self._plot_widget = pg.PlotWidget()
        body_row.addWidget(self._plot_widget, stretch=1)

        # Side Controls Stack
        side_panel = QVBoxLayout()
        side_panel.setContentsMargins(0, 0, 8, 0)
        side_panel.setSpacing(6)

        lbl_style = f"color: {_CLR_MUTED}; font-size: 9px; font-weight: 500;"
        combo_style = f"""
            QComboBox {{
                background-color: {_CLR_PANEL_ALT};
                color: {_CLR_WHITE};
                border: 1px solid {_CLR_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
                min-width: 65px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {_CLR_PANEL_ALT};
                color: {_CLR_WHITE};
                border: 1px solid {_CLR_BORDER};
            }}
        """
        btn_style = f"""
            QPushButton {{
                background-color: {_CLR_PANEL_ALT};
                color: {_CLR_WHITE};
                border: 1px solid {_CLR_BORDER};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: 500;
                min-width: 65px;
            }}
            QPushButton:hover {{
                background-color: #1e3a5f;
                border-color: #3b82f6;
            }}
        """

        time_lbl = QLabel("Time Window")
        time_lbl.setStyleSheet(lbl_style)
        side_panel.addWidget(time_lbl)

        self._window_combo = QComboBox()
        self._window_combo.addItems(["10 s", "30 s", "60 s"])
        self._window_combo.setCurrentIndex(0)  # 10 s default to match image
        self._window_combo.setStyleSheet(combo_style)
        self._window_combo.currentTextChanged.connect(self._on_window_changed)
        side_panel.addWidget(self._window_combo)

        side_panel.addSpacing(4)

        refresh_lbl = QLabel("Sample Interval")
        refresh_lbl.setStyleSheet(lbl_style)
        side_panel.addWidget(refresh_lbl)

        self._refresh_combo = QComboBox()
        self._refresh_combo.addItems(["1 s", "2 s", "5 s"])
        self._refresh_combo.setCurrentIndex(0)
        self._refresh_combo.setStyleSheet(combo_style)
        self._refresh_combo.currentTextChanged.connect(self._on_refresh_combo_changed)
        side_panel.addWidget(self._refresh_combo)

        side_panel.addSpacing(10)

        cb_style = f"QCheckBox {{ color: {_CLR_MUTED}; font-size: 10px; font-weight: 500; background: transparent; }}"
        self._follow_cb = QCheckBox("Follow Live")
        self._follow_cb.setChecked(True)
        self._follow_cb.setStyleSheet(cb_style)
        self._follow_cb.toggled.connect(self._on_follow_toggled)
        side_panel.addWidget(self._follow_cb)

        self._jump_btn = QPushButton("Live")
        self._jump_btn.setIcon(qta.icon("fa5s.arrow-right"))
        self._jump_btn.setStyleSheet(btn_style)
        self._jump_btn.clicked.connect(self.jump_to_latest)
        side_panel.addWidget(self._jump_btn)

        side_panel.addSpacing(6)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setIcon(qta.icon("fa5s.pause"))
        self._pause_btn.setStyleSheet(btn_style)
        self._pause_btn.clicked.connect(self._toggle_pause)
        side_panel.addWidget(self._pause_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setIcon(qta.icon("fa5s.trash-alt"))
        self._clear_btn.setStyleSheet(btn_style)
        self._clear_btn.clicked.connect(self.clear_data)
        side_panel.addWidget(self._clear_btn)

        side_panel.addStretch()
        body_row.addLayout(side_panel)

        main_layout.addLayout(body_row)

    def _init_plot(self) -> None:
        plot = self._plot_widget
        plot.setBackground(_CLR_PANEL)
        plot.showGrid(x=True, y=True, alpha=0.3)

        # Axis styling
        left_axis = plot.getAxis("left")
        left_axis.setPen(QColor(_CLR_BORDER))
        left_axis.setTextPen(QColor(_CLR_MUTED))
        left_axis.setLabel("Voltage (V)", color=_CLR_MUTED)

        bottom_axis = plot.getAxis("bottom")
        bottom_axis.setPen(QColor(_CLR_BORDER))
        bottom_axis.setTextPen(QColor(_CLR_MUTED))
        bottom_axis.setLabel("Time (s)", color=_CLR_MUTED)

        # Y range fixed 0-3.5 V
        plot.setYRange(0, 3.5)
        plot.setXRange(0, self._time_window)

        # Trace curves (initially empty)
        self._pvo_curve = plot.plot(
            pen=QPen(QColor(_CLR_PVO), 2.5),
            name="PVo",
            fillLevel=None,
            fillBrush=None,
        )
        self._vref_curve = plot.plot(
            pen=QPen(QColor(_CLR_VREF), 2.5),
            name="Vref",
            fillLevel=None,
            fillBrush=None,
        )
        self._margin_curve = plot.plot(
            pen=QPen(QColor(_CLR_MARGIN), 2.5),
            name="Margin",
            fillLevel=None,
            fillBrush=None,
        )
        self._margin_curve.setVisible(self._margin_cb.isChecked())

        # Empty state text (hidden once data arrives)
        self._empty_text = pg.TextItem(
            "No signal",
            color=QColor(_CLR_MUTED),
            anchor=(0.5, 0.5),
        )
        self._empty_text.setPos(self._time_window / 2, 1.75)
        plot.addItem(self._empty_text)

        # Connect user range changes to auto-disable follow live
        plot.getViewBox().sigRangeChanged.connect(self._on_range_changed)

        self._update_empty_state()

    # ── public api ──────────────────────────────────────────────────────

    def add_sample(self, pvo: float, vref: float, margin: float, elapsed_time: float | None = None) -> None:
        """Append a (pvo, vref, margin) sample to the buffer."""
        if self._paused or self._playback_mode:
            return
        self._buffer.append((pvo, vref, margin))
        if elapsed_time is not None:
            self._times.append(elapsed_time)
        else:
            self._times.append(len(self._buffer) * self._dt)
            
        if len(self._buffer) > self.MAX_SAMPLES:
            del self._buffer[:-self.MAX_SAMPLES]
            del self._times[:-self.MAX_SAMPLES]
            
        self._redraw()

    def set_paused(self, paused: bool) -> None:
        """Pause or resume live updates."""
        self._paused = paused
        icon_name = "fa5s.play" if paused else "fa5s.pause"
        self._pause_btn.setIcon(qta.icon(icon_name))
        self._pause_btn.setText("Resume" if paused else "Pause")

    def clear_data(self) -> None:
        """Clear all buffered samples and reset the plot."""
        self._buffer.clear()
        self._times.clear()
        self._pvo_curve.setData([], [])
        self._vref_curve.setData([], [])
        self._margin_curve.setData([], [])
        self._updating_range = True
        self._plot_widget.setXRange(0, self._time_window, padding=0)
        self._updating_range = False
        self._update_empty_state()

    def set_time_window(self, seconds: float) -> None:
        """Change the visible time window in seconds."""
        self._time_window = float(seconds)
        if self._times:
            t_latest = self._times[-1]
            if self._follow_cb.isChecked():
                self._updating_range = True
                self._plot_widget.setXRange(t_latest - self._time_window, t_latest, padding=0)
                self._updating_range = False
        else:
            self._plot_widget.setXRange(0, self._time_window)
        self._redraw()

    # ── public api (playback mode & follow live) ─────────────────────────

    def set_playback_mode(self, enabled: bool, capture: SessionCapture | None = None) -> None:
        """Configure widget for playback review or live tracking."""
        self._playback_mode = enabled
        self._follow_cb.setChecked(not enabled)
        self._follow_cb.setEnabled(not enabled)
        self._jump_btn.setEnabled(not enabled)
        self._pause_btn.setEnabled(not enabled)
        self._clear_btn.setEnabled(not enabled)
        self._window_combo.setEnabled(not enabled)
        self._refresh_combo.setEnabled(not enabled)

        if enabled and capture:
            self._buffer = list(zip(capture.pvo_samples, capture.vref_samples, capture.margin_samples))
            self._times = list(capture.analog_time)
            self._redraw()
            if self._times:
                self._updating_range = True
                self._plot_widget.setXRange(self._times[0], self._times[-1], padding=0.05)
                self._updating_range = False
        else:
            self.clear_data()

    def jump_to_latest(self) -> None:
        """Snaps the viewport to the latest data and resumes Follow Live."""
        self._follow_cb.setChecked(True)
        if self._times:
            t_latest = self._times[-1]
            self._updating_range = True
            self._plot_widget.setXRange(t_latest - self._time_window, t_latest, padding=0)
            self._updating_range = False

    # ── internal ────────────────────────────────────────────────────────

    def _on_follow_toggled(self, checked: bool) -> None:
        if checked:
            self.jump_to_latest()

    def _on_range_changed(self, viewBox, range_val) -> None:
        if self._updating_range or self._paused or self._playback_mode:
            return
        # If the user drags or zooms, uncheck follow live
        if self._follow_cb.isChecked():
            self._follow_cb.blockSignals(True)
            self._follow_cb.setChecked(False)
            self._follow_cb.blockSignals(False)

    def _toggle_pause(self) -> None:
        self.set_paused(not self._paused)

    def _on_window_changed(self, text: str) -> None:
        seconds = float(text.replace(" s", ""))
        self.set_time_window(seconds)

    def _on_refresh_combo_changed(self, text: str) -> None:
        seconds = float(text.replace(" s", ""))
        self._dt = seconds
        self.refresh_rate_changed.emit(int(seconds * 1000))

    def _on_trace_toggle(self) -> None:
        self._pvo_curve.setVisible(self._pvo_cb.isChecked())
        self._vref_curve.setVisible(self._vref_cb.isChecked())
        self._margin_curve.setVisible(self._margin_cb.isChecked())

    def _redraw(self) -> None:
        if not self._buffer or not self._times:
            self._update_empty_state()
            return

        buf = list(self._buffer)
        times = list(self._times)

        pvo_data = np.array([s[0] for s in buf])
        vref_data = np.array([s[1] for s in buf])
        margin_data = np.array([s[2] for s in buf])

        self._pvo_curve.setData(times, pvo_data)
        self._vref_curve.setData(times, vref_data)
        self._margin_curve.setData(times, margin_data)

        if not self._playback_mode and times:
            t_latest = times[-1]
            if self._follow_cb.isChecked():
                self._updating_range = True
                self._plot_widget.setXRange(t_latest - self._time_window, t_latest, padding=0)
                self._updating_range = False

        self._update_empty_state()

    def _update_empty_state(self) -> None:
        has_data = len(self._buffer) > 0
        self._empty_text.setVisible(not has_data)


# ---------------------------------------------------------------------------
# 3. TrendChart  (pyqtgraph-based)
# ---------------------------------------------------------------------------

class TrendChart(QWidget):
    """Tabbed trend chart showing margin / PVo / Vref over the last 60 s.

    Each trace maintains a 60-point buffer (one sample per second).
    """

    BUFFER_SIZE = 60

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_trace = "margin"
        self._auto_scale = True

        # Per-trace buffers: {name: deque of values}
        self._buffers: dict[str, deque[float]] = {
            "margin": deque(maxlen=self.BUFFER_SIZE),
            "pvo": deque(maxlen=self.BUFFER_SIZE),
            "vref": deque(maxlen=self.BUFFER_SIZE),
        }

        self._init_ui()
        self._init_plot()

    # ── ui construction ─────────────────────────────────────────────────

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Tab row
        tab_row = QHBoxLayout()
        tab_row.setSpacing(4)

        self._tabs: dict[str, QPushButton] = {}
        for name in ("margin", "pvo", "vref"):
            btn = QPushButton(_trace_label(name))
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked, n=name: self.set_active_trace(n))
            self._tabs[name] = btn
            tab_row.addWidget(btn)

        tab_row.addStretch()
        layout.addLayout(tab_row)

        # Plot widget
        self._plot_widget = pg.PlotWidget()
        layout.addWidget(self._plot_widget, stretch=1)

        # Bottom row: Auto Scale checkbox
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(8, 0, 8, 0)
        self._auto_check = QCheckBox("Auto Scale")
        self._auto_check.setChecked(True)
        self._auto_check.setStyleSheet(f"QCheckBox {{ color: {_CLR_MUTED}; font-size: 9px; background: transparent; }}")
        self._auto_check.toggled.connect(self._on_auto_scale_toggled)
        bottom_row.addWidget(self._auto_check)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        # Stats label (hidden, kept for structural compatibility)
        self._stats_label = QLabel()
        self._stats_label.hide()

        # Apply default tab styling
        self._update_tab_styling()

    def _init_plot(self) -> None:
        plot = self._plot_widget
        plot.setBackground(_CLR_PANEL)
        plot.showGrid(x=True, y=True, alpha=0.3)

        left_axis = plot.getAxis("left")
        left_axis.setPen(QColor(_CLR_BORDER))
        left_axis.setTextPen(QColor(_CLR_MUTED))
        left_axis.setLabel("Margin (V)", color=_CLR_MUTED)

        bottom_axis = plot.getAxis("bottom")
        bottom_axis.setPen(QColor(_CLR_BORDER))
        bottom_axis.setTextPen(QColor(_CLR_MUTED))
        bottom_axis.setLabel("Time (s)", color=_CLR_MUTED)

        plot.setYRange(0, 3.5)
        plot.setXRange(-self.BUFFER_SIZE, 0)

        # Single curve (switched by active trace)
        self._curve = plot.plot(pen=QPen(_trace_color("margin"), 2))

        # Empty state
        self._empty_text = pg.TextItem(
            "Collecting data...",
            color=QColor(_CLR_MUTED),
            anchor=(0.5, 0.5),
        )
        self._empty_text.setPos(-self.BUFFER_SIZE / 2, 1.75)
        plot.addItem(self._empty_text)

        self._empty_line = pg.InfiniteLine(
            pos=1.75,
            angle=0,
            pen=QPen(QColor(_CLR_BORDER), 1, Qt.DashLine),
        )
        plot.addItem(self._empty_line)

    # ── public api ──────────────────────────────────────────────────────

    def add_point(self, pvo: float, vref: float, margin: float) -> None:
        """Append samples to all trace buffers and update the plot."""
        self._buffers["pvo"].append(pvo)
        self._buffers["vref"].append(vref)
        self._buffers["margin"].append(margin)
        self._update_plot()

    def set_active_trace(self, name: str) -> None:
        """Switch the displayed trace."""
        if name not in self._buffers:
            return
        self._active_trace = name
        self._update_tab_styling()
        self._update_plot()

    def refresh(self) -> None:
        """Force a plot redraw."""
        self._update_plot()

    # ── internal ────────────────────────────────────────────────────────

    def _update_tab_styling(self) -> None:
        for name, btn in self._tabs.items():
            is_active = name == self._active_trace
            btn.setChecked(is_active)
            if is_active:
                color = _trace_color(name).name()
                btn.setStyleSheet(
                    f"background: {color}; color: #000; font-weight: bold; "
                    f"border: 1px solid {color}; border-radius: 4px; "
                    f"padding: 2px 10px; font-size: 11px;"
                )
            else:
                btn.setStyleSheet(
                    f"background: {_CLR_PANEL_ALT}; color: {_CLR_MUTED}; "
                    f"border: 1px solid {_CLR_BORDER}; border-radius: 4px; "
                    f"padding: 2px 10px; font-size: 11px;"
                )

    def _on_auto_scale_toggled(self, checked: bool) -> None:
        self._auto_scale = checked
        self._update_y_range()

    def _update_y_range(self) -> None:
        plot = self._plot_widget
        if self._auto_scale:
            buf = self._buffers[self._active_trace]
            if buf:
                lo = min(buf)
                hi = max(buf)
                padding = max((hi - lo) * 0.15, 0.1)
                plot.setYRange(max(0, lo - padding), hi + padding)
            else:
                plot.setYRange(0, 0.6 if self._active_trace == "margin" else 3.5)
        else:
            plot.setYRange(0, 0.6 if self._active_trace == "margin" else 3.5)

    def _update_plot(self) -> None:
        buf = self._buffers[self._active_trace]
        has_data = len(buf) > 0

        self._empty_text.setVisible(not has_data)
        self._empty_line.setVisible(not has_data)

        # Update Y-axis label
        left_axis = self._plot_widget.getAxis("left")
        left_axis.setLabel(f"{_trace_label(self._active_trace)} (V)", color=_CLR_MUTED)

        if has_data:
            n = len(buf)
            x = np.arange(-n, 0, 1)
            y = np.array(buf)
            color = _trace_color(self._active_trace)
            self._curve.setPen(QPen(color, 2))
            self._curve.setData(x, y)

            # Update stats
            avg_val = np.mean(y)
            min_val = np.min(y)
            max_val = np.max(y)
            self._stats_label.setText(
                f"Avg: {avg_val:.3f}  Min: {min_val:.3f}  Max: {max_val:.3f}"
            )
        else:
            self._curve.setData([], [])
            self._stats_label.setText("Avg: —  Min: —  Max: —")

        self._update_y_range()


# ---------------------------------------------------------------------------
# 4. QualityBar
# ---------------------------------------------------------------------------

class QualityBar(QWidget):
    """Compact horizontal quality bar with pill-shaped fill.

    Layout:  [Label]  [████████░░░░]  85% Good
    Green >70%, Amber 40-70%, Red <40%.
    Optional inverted mode for metrics where lower is better.
    """

    BAR_HEIGHT = 10
    BAR_MIN_WIDTH = 50
    FIXED_HEIGHT = 20

    def __init__(self, label: str = "", value_text: str = "",
                 show_bar: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._percent = 0.0
        self._value_str = value_text
        self._label_str = label
        self._inverted = False
        self._show_bar = show_bar

        self.setFixedHeight(self.FIXED_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._label_widget = QLabel(self._label_str)
        self._label_widget.setStyleSheet(
            f"color: {_CLR_MUTED}; font-size: 9px; font-weight: 500; "
            f"background: transparent;"
        )
        layout.addWidget(self._label_widget)

        # Bar drawn in paintEvent — spacer widget to occupy space
        self._bar_container = QWidget()
        self._bar_container.setMinimumWidth(self.BAR_MIN_WIDTH)
        self._bar_container.setFixedHeight(self.BAR_HEIGHT)
        self._bar_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        layout.addWidget(self._bar_container, stretch=1)

        if not self._show_bar:
            self._bar_container.hide()
            layout.addStretch(1)

        self._value_widget = QLabel(self._value_str)
        self._value_widget.setStyleSheet(
            f"color: {_CLR_WHITE}; font-size: 9px; font-weight: 600; "
            f"background: transparent;"
        )
        layout.addWidget(self._value_widget)

    # ── public api ──────────────────────────────────────────────────────

    def set_percent(self, value: float) -> None:
        """Update fill percentage (0-100)."""
        self._percent = max(0.0, min(100.0, value))
        self._bar_container.update()

    def set_value_text(self, text: str) -> None:
        """Update the value string shown after the bar."""
        self._value_str = text
        self._value_widget.setText(text)

    def set_label(self, text: str) -> None:
        """Change the label text."""
        self._label_str = text
        self._label_widget.setText(text)

    def set_inverted(self, inverted: bool) -> None:
        """Invert color logic (green when low, red when high)."""
        self._inverted = inverted
        self._bar_container.update()

    # ── paint (on the bar container) ────────────────────────────────────

    def _bar_color(self) -> QColor:
        pct = self._percent
        if self._inverted:
            # Green when low
            if pct < 30:
                return QColor(_CLR_GREEN)
            if pct < 60:
                return QColor(_CLR_AMBER)
            return QColor(_CLR_RED)
        else:
            if pct > 70:
                return QColor(_CLR_GREEN)
            if pct > 40:
                return QColor(_CLR_AMBER)
            return QColor(_CLR_RED)

    def _quality_text(self) -> str:
        pct = self._percent
        if self._inverted:
            if pct < 30:
                return "Excellent"
            if pct < 60:
                return "Acceptable"
            return "Poor"
        else:
            if pct > 70:
                return "Excellent"
            if pct > 40:
                return "Acceptable"
            return "Poor"

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._show_bar:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        geom = self._bar_container.geometry()
        bar_x = geom.x()
        bar_y = geom.y()
        bar_w = geom.width()
        bar_h = geom.height()

        # Background track (pill shape)
        track_rect = (bar_x, bar_y, bar_w - 1, bar_h - 1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_CLR_PANEL_ALT))
        p.drawRoundedRect(*track_rect, bar_h / 2, bar_h / 2)

        # Filled portion (pill shape)
        fill_w = int((bar_w - 1) * (self._percent / 100.0))
        if fill_w > 0:
            fill_color = self._bar_color()
            p.setBrush(fill_color)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h - 1, bar_h / 2, bar_h / 2)

        p.end()


# ---------------------------------------------------------------------------
# 5. MarginScaleBar
# ---------------------------------------------------------------------------

class MarginScaleBar(QWidget):
    """Compact color-zoned scale bar for margin voltage display.

    Zones:  Red (0-0.28V) → Orange (0.28-0.36V) → Yellow (0.36-0.45V) → Green (0.45V+)
    Tick marks at 0, 0.18, 0.36, 0.54, 0.72 with labels.
    A downward triangle marker indicates the current margin value.
    """

    FIXED_HEIGHT = 100
    MARGIN_MAX = 0.72

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._margin_value: float | None = None
        self.setFixedHeight(self.FIXED_HEIGHT)
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ── public api ──────────────────────────────────────────────────────

    def set_margin(self, value: float | None) -> None:
        """Set the current margin voltage (0.0 - 0.72).  None = no data."""
        self._margin_value = value
        self.update()

    # ── paint ───────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()

        # Layout constants
        bar_y = 20
        bar_h = 10
        bar_x = 12
        bar_w = w - 24

        if bar_w < 30:
            p.end()
            return

        zone_defs = [
            (0.0, 0.28, QColor("#ef4444")),
            (0.28, 0.36, QColor("#f59e0b")),
            (0.36, 0.45, QColor("#22c55e")),
            (0.45, self.MARGIN_MAX, QColor("#16a34a")),
        ]

        # ── draw colored bar zones ─────────────────────────────────────
        p.setPen(Qt.NoPen)
        for lo, hi, clr in zone_defs:
            x0 = bar_x + (lo / self.MARGIN_MAX) * bar_w
            x1 = bar_x + (hi / self.MARGIN_MAX) * bar_w
            zone_w = x1 - x0
            if zone_w > 0:
                p.setBrush(clr)
                p.drawRoundedRect(int(x0), bar_y, int(zone_w), bar_h, 2, 2)

        # ── border around bar ──────────────────────────────────────────
        p.setPen(QPen(QColor(_CLR_BORDER), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 2, 2)

        # ── tick marks + labels (ticks shifted below bar) ──────────────
        p.setPen(QPen(QColor(_CLR_MUTED), 1))
        tick_labels = ["0", "0.18", "0.36", "0.54", "0.72"]
        tick_values = [0.0, 0.18, 0.36, 0.54, 0.72]
        tick_font = _font(7)
        p.setFont(tick_font)

        for tick_val, tick_str in zip(tick_values, tick_labels):
            x = bar_x + (tick_val / self.MARGIN_MAX) * bar_w
            # Tick line below bar
            p.drawLine(int(x), bar_y + bar_h, int(x), bar_y + bar_h + 3)
            # Label below tick
            p.drawText(int(x) - 12, bar_y + bar_h + 4, 24, 10,
                       Qt.AlignCenter, tick_str)

        # ── margin indicator triangle ──────────────────────────────────
        if self._margin_value is not None:
            margin_clamped = max(0.0, min(self.MARGIN_MAX, self._margin_value))
            indicator_x = bar_x + (margin_clamped / self.MARGIN_MAX) * bar_w

            # Triangle (downward pointing) above bar
            tri_size = 5
            tri_path = QPainterPath()
            tri_path.moveTo(indicator_x, bar_y - 1)
            tri_path.lineTo(indicator_x - tri_size, bar_y - 1 - tri_size)
            tri_path.lineTo(indicator_x + tri_size, bar_y - 1 - tri_size)
            tri_path.closeSubpath()

            p.setPen(QPen(QColor(_CLR_WHITE), 1))
            p.setBrush(QColor(_CLR_WHITE))
            p.drawPath(tri_path)

            # Value label above triangle
            p.setPen(QColor(_CLR_WHITE))
            p.setFont(_font(8, QFont.Bold))
            p.drawText(int(indicator_x) - 20, bar_y - 18, 40, 10,
                       Qt.AlignCenter, f"{self._margin_value:.3f}V")
        else:
            # Empty state: dashed baseline
            p.setPen(QPen(QColor(_CLR_BORDER), 1, Qt.DashLine))
            mid_y = bar_y + bar_h / 2
            p.drawLine(int(bar_x), int(mid_y),
                       int(bar_x + bar_w), int(mid_y))

        # ── single-column zone legend ──────────────────────────────────
        # A vertical list remains readable in the narrow Signal-page panel.
        legend_font = _font(7, QFont.Normal)
        p.setFont(legend_font)
        legend_rows = [
            (QColor("#ef4444"), "< 0.28 V   Risk (high BER)"),
            (QColor("#f59e0b"), "0.28 - 0.36 V   Acceptable"),
            (QColor("#22c55e"), "0.36 - 0.45 V   Good"),
            (QColor("#16a34a"), "> 0.45 V   Excellent"),
        ]
        for row, (zone_color, label) in enumerate(legend_rows):
            y = 54 + row * 11
            p.setPen(Qt.NoPen)
            p.setBrush(zone_color)
            p.drawRoundedRect(bar_x, y + 3, 6, 6, 1, 1)
            p.setPen(QColor(_CLR_MUTED))
            p.drawText(
                bar_x + 12, y, max(0, bar_w - 12), 12,
                Qt.AlignLeft | Qt.AlignVCenter, label,
            )

        p.end()
