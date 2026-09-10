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

        self.setMinimumHeight(70)
        self.setMinimumWidth(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_percent(self, value: float) -> None:
        """Update the percentage (0-100) and redraw."""
        self._percent = max(0.0, min(100.0, value))
        self.update()

    def _color(self) -> QColor:
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
        span_angle = -270 * (self._percent / 100.0)
        p.drawArc(*arc_rect, 225 * 16, int(span_angle * 16))

        # Center value text (e.g. 92%)
        val_font = _font(11, QFont.Bold)
        p.setFont(val_font)
        p.setPen(QColor(_CLR_WHITE))
        pct_str = f"{self._percent:.0f}%"
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
    """Real-time scrolling signal waveform viewer with three traces.

    Uses pyqtgraph PlotWidget for smooth, GPU-accelerated rendering.
    Displays PVo (green), Vref (blue), and Margin (amber) traces over a
    configurable scrolling time window.
    """

    MAX_SAMPLES = 600  # at 100 ms / sample → 60 s
    refresh_rate_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paused = False
        self._time_window = 10.0  # 10 s default to match image
        self._dt = 0.1  # default 100 ms interval
        self._buffer: list[tuple[float, float, float]] = []
        self._times: list[float] = []
        self._playback_mode = False
        self._updating_range = False
        self._target_margin = 0.365

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

        header = QLabel("SIGNAL WAVEFORMS (LIVE)")
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

        refresh_lbl = QLabel("Refresh Rate")
        refresh_lbl.setStyleSheet(lbl_style)
        side_panel.addWidget(refresh_lbl)

        self._refresh_combo = QComboBox()
        self._refresh_combo.addItems(["100 ms", "200 ms", "500 ms"])
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

        # Target Margin dashed line
        self._target_line = pg.InfiniteLine(
            pos=self._target_margin,
            angle=0,
            pen=QPen(QColor(_CLR_MARGIN), 1, Qt.DashLine),
            label=f"Target {self._target_margin:.3f}V",
            labelOpts={"color": _CLR_MARGIN, "movable": False},
        )
        plot.addItem(self._target_line)

        # Safe Margin Zone (0.35 - 0.45 V)
        zone_brush = QColor(_CLR_GREEN)
        zone_brush.setAlpha(20)
        self._safe_zone = pg.LinearRegionItem(
            values=(0.35, 0.45),
            orientation="horizontal",
            brush=zone_brush,
            pen=QPen(QColor(_CLR_GREEN), 0),
            movable=False,
        )
        plot.addItem(self._safe_zone)

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

        # Dashed baseline for empty state
        self._empty_line = pg.InfiniteLine(
            pos=1.75,
            angle=0,
            pen=QPen(QColor(_CLR_BORDER), 1, Qt.DashLine),
        )
        plot.addItem(self._empty_line)

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
            
        if len(self._buffer) > 10000:
            self._buffer = self._buffer[-10000:]
            self._times = self._times[-10000:]
            
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
        ms = int(text.replace(" ms", ""))
        self._dt = ms / 1000.0
        self.refresh_rate_changed.emit(ms)

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
        self._empty_line.setVisible(not has_data)
        self._target_line.setVisible(has_data)
        self._safe_zone.setVisible(has_data)


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

        # ── 2-column zone legend at the bottom ──────────────────────────
        legend_font = _font(7, QFont.Normal)
        p.setFont(legend_font)

        col1_x = bar_x
        split_w = int(bar_w * 0.58)
        col2_x = bar_x + split_w
        
        col1_text_w = split_w
        col2_text_w = bar_w - split_w

        y_row1 = 56
        y_row2 = 72

        # Row 1 Left: Red box (< 0.28 V Risk (High BER))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ef4444"))
        p.drawRoundedRect(col1_x, y_row1 + 3, 6, 6, 1, 1)
        p.setPen(QColor(_CLR_MUTED))
        p.drawText(col1_x + 12, y_row1, col1_text_w, 12, Qt.AlignLeft | Qt.AlignVCenter, "< 0.28 V    Risk (High BER)")

        # Row 2 Left: Orange box (0.28 - 0.36 V Acceptable)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f59e0b"))
        p.drawRoundedRect(col1_x, y_row2 + 3, 6, 6, 1, 1)
        p.setPen(QColor(_CLR_MUTED))
        p.drawText(col1_x + 12, y_row2, col1_text_w, 12, Qt.AlignLeft | Qt.AlignVCenter, "0.28 - 0.36 V    Acceptable")

        # Row 1 Right: Green box (0.36 - 0.45 V Good)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#22c55e"))
        p.drawRoundedRect(col2_x, y_row1 + 3, 6, 6, 1, 1)
        p.setPen(QColor(_CLR_MUTED))
        p.drawText(col2_x + 12, y_row1, col2_text_w, 12, Qt.AlignLeft | Qt.AlignVCenter, "0.36 - 0.45 V    Good")

        # Row 2 Right: Dark Green box (> 0.45 V Excellent)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#16a34a"))
        p.drawRoundedRect(col2_x, y_row2 + 3, 6, 6, 1, 1)
        p.setPen(QColor(_CLR_MUTED))
        p.drawText(col2_x + 12, y_row2, col2_text_w, 12, Qt.AlignLeft | Qt.AlignVCenter, "> 0.45 V    Excellent")

        p.end()


# ---------------------------------------------------------------------------
# 6. OOKWaveformWidget — Logic-Analyzer-style digital square wave
# ---------------------------------------------------------------------------

# 4B5B encoding table: maps 4-bit nibble (0-15) → 5-bit code
_4B5B_TABLE: dict[int, tuple[int, ...]] = {
    0x0: (1, 1, 1, 1, 0),
    0x1: (0, 1, 0, 0, 1),
    0x2: (1, 0, 1, 0, 0),
    0x3: (1, 0, 1, 0, 1),
    0x4: (0, 1, 0, 1, 0),
    0x5: (0, 1, 0, 1, 1),
    0x6: (0, 1, 1, 1, 0),
    0x7: (0, 1, 1, 1, 1),
    0x8: (1, 0, 0, 1, 0),
    0x9: (1, 0, 0, 1, 1),
    0xA: (1, 0, 1, 1, 0),
    0xB: (1, 0, 1, 1, 1),
    0xC: (1, 1, 0, 1, 0),
    0xD: (1, 1, 0, 1, 1),
    0xE: (1, 1, 1, 0, 0),
    0xF: (1, 1, 1, 0, 1),
}


def _encode_4b5b(data: bytes | None, max_bits: int = 600) -> list[int]:
    """Encode up to max_bits bits from data bytes using 4B5B.

    Returns a flat list of 0/1 bits (NRZ/OOK — 1=LED ON, 0=LED OFF).
    Includes a synthetic preamble of alternating 10101010 before the payload.
    """
    bits: list[int] = []
    # Preamble: 16-bit alternating pattern (sync marker)
    preamble = [1, 0] * 8
    bits.extend(preamble)
    if data:
        for byte_val in data:
            hi_nibble = (byte_val >> 4) & 0xF
            lo_nibble = byte_val & 0xF
            bits.extend(_4B5B_TABLE[hi_nibble])
            bits.extend(_4B5B_TABLE[lo_nibble])
            if len(bits) >= max_bits:
                break
    # Pad with idle HIGH if short
    while len(bits) < 64:
        bits.append(1)
    return bits[:max_bits]


class OOKWaveformWidget(QWidget):
    """Logic-analyzer-style digital square wave for OOK (On-Off Keying) data.

    Displays the decoded bit stream as a crisp HIGH/LOW square wave:
      - HIGH (1) = LED ON  (light flash)
      - LOW  (0) = LED OFF (no light)

    Label: "RX DATA · OOK"
    Color: cyan (#00E5FF) with subtle glow shadow.
    Symbol width: 3 px per bit, scrolling left.
    Buffer: ring buffer of MAX_SYMBOLS bits.

    Data sources:
      - Simulated: bits from 4B5B encoding of current file chunk bytes.
      - Physical:  comparator decision PVo > Vref → 1, else 0.
    """

    MAX_SYMBOLS = 600
    SYM_PX = 3          # pixels per symbol
    _CLR_OOK = "#00E5FF"
    _CLR_OOK_GLOW = "#007A99"
    _CLR_BG_W = "#08111D"
    _CLR_PANEL_W = "#0F1B2D"
    _CLR_BORDER_W = "#1A3152"
    _CLR_MUTED_W = "#708090"
    _CLR_HIGH = "#22c55e"   # "1" label color
    _CLR_LOW = "#ef4444"    # "0" label color

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bits: deque[int] = deque(maxlen=self.MAX_SYMBOLS)
        self._paused = False
        self._has_data = False
        self._playback_mode = False
        
        self._zoom = 3.0  # Pixels per symbol
        self._auto_scroll = True
        self._scroll_offset = 0  # Number of symbols offset from the right (newest)

        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)

        self._build_ui()

    # ── ui ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Top control bar
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 4, 8, 2)
        bar.setSpacing(8)

        header = QLabel("RX DATA · OOK")
        header.setStyleSheet(
            f"color: {self._CLR_OOK}; font-size: 11px; font-weight: 700; "
            f"background: transparent; letter-spacing: 0.5px;"
        )
        bar.addWidget(header)

        bar.addStretch()

        btn_style = (
            f"QPushButton {{ background: {self._CLR_PANEL_W}; color: #d1d5db; "
            f"border: 1px solid {self._CLR_BORDER_W}; border-radius: 4px; "
            f"padding: 3px 8px; font-size: 9px; }}"
            f"QPushButton:hover {{ border-color: {self._CLR_OOK}; color: {self._CLR_OOK}; }}"
        )

        self._auto_scroll_cb = QCheckBox("Auto-scroll")
        self._auto_scroll_cb.setChecked(True)
        self._auto_scroll_cb.setStyleSheet(
            f"QCheckBox {{ color: {self._CLR_MUTED_W}; font-size: 9px; background: transparent; }}"
        )
        self._auto_scroll_cb.toggled.connect(self._on_auto_scroll_toggled)
        bar.addWidget(self._auto_scroll_cb)

        self._zoom_fit_btn = QPushButton("Zoom Fit")
        self._zoom_fit_btn.setStyleSheet(btn_style)
        self._zoom_fit_btn.setFixedHeight(22)
        self._zoom_fit_btn.clicked.connect(self._on_zoom_fit)
        bar.addWidget(self._zoom_fit_btn)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setStyleSheet(btn_style)
        self._pause_btn.setFixedHeight(22)
        self._pause_btn.clicked.connect(self._toggle_pause)
        bar.addWidget(self._pause_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setStyleSheet(btn_style)
        self._clear_btn.setFixedHeight(22)
        self._clear_btn.clicked.connect(self.clear)
        bar.addWidget(self._clear_btn)

        lay.addLayout(bar)

        lay.addStretch(1)

    # ── public api ────────────────────────────────────────────────────────

    def push_bit(self, bit: int) -> None:
        """Push a single bit (0 or 1) and redraw."""
        if self._paused or self._playback_mode:
            return
        self._bits.append(1 if bit else 0)
        self._has_data = True
        if not self._auto_scroll:
            self._scroll_offset += 1
        self.update()

    def push_bits(self, bits: list[int]) -> None:
        """Push a list of bits (bulk update from 4B5B encoder)."""
        if self._paused or self._playback_mode:
            return
        if bits:
            for b in bits:
                self._bits.append(1 if b else 0)
            self._has_data = True
            if not self._auto_scroll:
                self._scroll_offset += len(bits)
            self.update()

    def set_from_pvo_vref(self, pvo: float, vref: float) -> None:
        """Push a single bit derived from comparator decision PVo vs Vref."""
        if self._playback_mode:
            return
        bit = 1 if pvo > vref else 0
        self.push_bit(bit)

    def set_from_4b5b(self, data: bytes | None, seed_offset: int = 0) -> None:
        """Replace buffer with 4B5B-encoded bits from data.

        seed_offset shifts which part of the encoded stream is displayed,
        allowing the waveform to scroll as chunk index advances.
        """
        if self._paused or self._playback_mode:
            return
        bits = _encode_4b5b(data)
        # Rotate by seed_offset to simulate scrolling
        if seed_offset > 0 and bits:
            n = len(bits)
            offset = seed_offset % n
            bits = bits[offset:] + bits[:offset]
            
        old_len = len(self._bits)
        self._bits.clear()
        for b in bits:
            self._bits.append(b)
            
        self._has_data = bool(bits)
        self.update()

    def clear(self) -> None:
        """Clear all buffered bits."""
        self._bits.clear()
        self._has_data = False
        self._scroll_offset = 0
        self.update()

    def set_playback_mode(self, enabled: bool, bits: list[int] | None = None) -> None:
        self._playback_mode = enabled
        self._auto_scroll_cb.setEnabled(not enabled)
        self._zoom_fit_btn.setEnabled(True)
        self._pause_btn.setEnabled(not enabled)
        self._clear_btn.setEnabled(not enabled)

        if enabled:
            self._bits.clear()
            if bits:
                for b in bits:
                    self._bits.append(b)
            self._has_data = bool(bits)
            self._auto_scroll = False
            self._auto_scroll_cb.setChecked(False)
            self._on_zoom_fit()
        else:
            self.clear()
            self._auto_scroll = True
            self._auto_scroll_cb.setChecked(True)

    # ── interactivity ────────────────────────────────────────────────────

    def wheelEvent(self, event) -> None:
        """Handle mouse wheel for X-axis zooming."""
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom *= 1.2
        elif delta < 0:
            self._zoom /= 1.2
            
        self._zoom = max(0.1, min(self._zoom, 50.0))
        
        # If zoom out pushes view past available data, snap to edge
        max_offset = max(0, len(self._bits) - 1)
        self._scroll_offset = min(self._scroll_offset, max_offset)
            
        self.update()
        event.accept()

    def mousePressEvent(self, event) -> None:
        """Start dragging."""
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._last_mouse_x = event.pos().x()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        """Handle dragging to pan."""
        if getattr(self, "_is_dragging", False):
            dx = event.pos().x() - self._last_mouse_x
            
            # Convert pixel delta to symbol delta based on zoom
            if abs(dx) >= self._zoom:
                symbols_shifted = int(dx / self._zoom)
                
                # Dragging right (dx > 0) means looking at older data (increasing offset)
                # Dragging left (dx < 0) means looking at newer data (decreasing offset)
                self._scroll_offset += symbols_shifted
                
                # Constrain offset
                max_offset = max(0, len(self._bits) - 1)
                self._scroll_offset = max(0, min(self._scroll_offset, max_offset))
                
                # If the user drags away from 0, disable auto-scroll and pause
                if self._scroll_offset > 0:
                    self._auto_scroll_cb.setChecked(False)
                    self._auto_scroll = False
                    if not self._paused:
                        self._paused = True
                        self._pause_btn.setText("Resume")
                elif self._scroll_offset == 0:
                    self._auto_scroll_cb.setChecked(True)
                    self._auto_scroll = True
                
                self._last_mouse_x += symbols_shifted * self._zoom
                self.update()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        """End dragging."""
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()

    def keyPressEvent(self, event) -> None:
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key_Space:
            self._toggle_pause()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _on_zoom_fit(self) -> None:
        """Adjust zoom to fit all data."""
        if not self._bits:
            return
        draw_w = self.width() - 32
        self._zoom = max(0.1, draw_w / len(self._bits))
        self._scroll_offset = 0
        self._auto_scroll_cb.setChecked(True)
        self.update()

    def _on_auto_scroll_toggled(self, checked: bool) -> None:
        self._auto_scroll = checked
        if checked:
            self._scroll_offset = 0
            if self._paused:
                self._paused = False
                self._pause_btn.setText("Pause")
        self.update()

    # ── internal ─────────────────────────────────────────────────────────

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self._pause_btn.setText("Resume" if self._paused else "Pause")
        if not self._paused:
            self._scroll_offset = 0
            self._auto_scroll = True
            self._auto_scroll_cb.setChecked(True)

    # ── paint ─────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        """Render the OOK square wave onto the canvas area."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)  # sharp edges for digital
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()

        # Full widget background
        p.fillRect(0, 0, w, h, QColor(self._CLR_BG_W))

        # Canvas area below the control bar (estimate 30px for bar)
        bar_h = 30
        canvas_y = bar_h
        canvas_h = h - bar_h

        if canvas_h < 10:
            p.end()
            return

        # Panel background with border
        p.setPen(QPen(QColor(self._CLR_BORDER_W), 1))
        p.setBrush(QColor(self._CLR_PANEL_W))
        p.drawRoundedRect(4, canvas_y, w - 8, canvas_h - 4, 6, 6)

        if not self._has_data or not self._bits:
            # Empty state
            p.setPen(QColor(self._CLR_MUTED_W))
            p.setFont(_font(9, QFont.Normal))
            p.drawText(4, canvas_y, w - 8, canvas_h - 4, Qt.AlignCenter,
                       "No signal data — waiting for OOK transmission")
            p.end()
            return

        # Layout within canvas
        pad_x = 12
        pad_y = 10
        draw_w = w - 2 * pad_x - 8   # total waveform draw width
        draw_h = canvas_h - 2 * pad_y - 8

        if draw_w < 20 or draw_h < 20:
            p.end()
            return

        # ── Y positions for HIGH and LOW ──────────────────────────────────
        high_y = canvas_y + pad_y + 4
        low_y = canvas_y + pad_y + draw_h - 4
        mid_y = (high_y + low_y) // 2

        # ── Draw Y-axis labels ────────────────────────────────────────────
        lbl_font = _font(8, QFont.Medium)
        p.setFont(lbl_font)

        p.setPen(QColor(self._CLR_HIGH))
        p.drawText(pad_x - 4, high_y - 6, 8, 12, Qt.AlignCenter, "1")
        p.setPen(QColor(self._CLR_LOW))
        p.drawText(pad_x - 4, low_y - 6, 8, 12, Qt.AlignCenter, "0")

        # ── Draw grid lines ───────────────────────────────────────────────
        p.setPen(QPen(QColor(self._CLR_BORDER_W), 1, Qt.DashLine))
        p.drawLine(pad_x + 8, high_y, w - pad_x - 4, high_y)
        p.drawLine(pad_x + 8, low_y, w - pad_x - 4, low_y)
        # Mid dashed centre line
        p.setPen(QPen(QColor(self._CLR_BORDER_W), 1, Qt.DotLine))
        p.drawLine(pad_x + 8, mid_y, w - pad_x - 4, mid_y)

        # ── Determine how many symbols fit in draw_w ──────────────────────
        sym_px = self._zoom
        n_visible = max(1, int(draw_w / sym_px))

        bits_list = list(self._bits)
        n_total = len(bits_list)
        
        # Calculate start index based on scroll_offset
        # offset 0 means we see the newest bits at the right
        end_idx = n_total - self._scroll_offset
        start_idx = max(0, end_idx - n_visible)
        
        if end_idx <= 0 or start_idx >= n_total:
            bits_view = []
        else:
            bits_view = bits_list[start_idx:end_idx]

        if not bits_view:
            p.end()
            return

        n = len(bits_view)

        # Start drawing from the right edge, filling leftward
        start_x = pad_x + 8 + draw_w - n * sym_px

        # ── Draw faint vertical separators ────────────────────────────────
        if sym_px >= 3:
            sep_pen = QPen(QColor(255, 255, 255, 12), 1)  # Very faint white
            p.setPen(sep_pen)
            x_sep = start_x
            for _ in range(n + 1):
                p.drawLine(int(x_sep), high_y, int(x_sep), low_y)
                x_sep += sym_px

        # ── Draw glow shadow (thicker, darker cyan, offset 1px) ───────────
        glow_pen = QPen(QColor(self._CLR_OOK_GLOW), min(sym_px, 3) + 2)
        glow_pen.setCapStyle(Qt.FlatCap)
        glow_pen.setJoinStyle(Qt.MiterJoin)

        p.setPen(glow_pen)
        p.setBrush(Qt.NoBrush)

        # Build path for glow
        glow_path = QPainterPath()
        prev_y = high_y if bits_view[0] else low_y
        glow_path.moveTo(start_x, prev_y)
        x = start_x
        for i, bit in enumerate(bits_view):
            cur_y = high_y if bit else low_y
            if cur_y != prev_y:
                # Vertical edge (transition)
                glow_path.lineTo(x, cur_y)
            glow_path.lineTo(x + sym_px, cur_y)
            x += sym_px
            prev_y = cur_y

        p.drawPath(glow_path)

        # ── Draw main OOK trace (sharp, 2px cyan) ─────────────────────────
        main_pen = QPen(QColor(self._CLR_OOK), min(sym_px, 2))
        main_pen.setCapStyle(Qt.FlatCap)
        main_pen.setJoinStyle(Qt.MiterJoin)

        p.setPen(main_pen)

        main_path = QPainterPath()
        prev_y = high_y if bits_view[0] else low_y
        main_path.moveTo(start_x, prev_y)
        x = start_x
        for i, bit in enumerate(bits_view):
            cur_y = high_y if bit else low_y
            if cur_y != prev_y:
                main_path.lineTo(x, cur_y)
            main_path.lineTo(x + sym_px, cur_y)
            x += sym_px
            prev_y = cur_y

        p.drawPath(main_path)

        # ── Paused overlay ─────────────────────────────────────────────────
        if self._paused:
            p.setPen(QColor(self._CLR_OOK))
            p.setFont(_font(9, QFont.Bold))
            p.drawText(w - 70, canvas_y + 8, 60, 14, Qt.AlignRight,
                       "⏸ PAUSED")

        p.end()
