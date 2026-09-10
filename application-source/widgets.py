"""Reusable PySide6 widgets for the VLC Receiver app."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui_dev_v3.theme import COLORS


def muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


def value_label(text: str, color: str | None = None) -> QLabel:
    label = QLabel(text)
    if color:
        label.setStyleSheet(f"color: {color}; font-weight: 700; background: transparent;")
    else:
        label.setObjectName("Value")
    return label


def status_green_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("StatusGreen")
    return label


def panel_header(text: str) -> QLabel:
    """Uppercase blue panel header matching the image design."""
    label = QLabel(text.upper())
    label.setObjectName("SectionTitle")
    return label


class Card(QFrame):
    """Reusable card/panel widget with dark navy background and border."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 16)
        self.body.setSpacing(10)
        if title:
            self.body.addWidget(panel_header(title))


class SectionCard(Card):
    """Card with title and optional subtitle."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        if subtitle:
            self.body.addWidget(muted_label(subtitle))


def scrollable(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(widget)
    return area


class MetricCard(Card):
    """Display a labeled value with optional helper text."""

    def __init__(self, title: str, value: str, helper: str = "", parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 26px; font-weight: 700; background: transparent; letter-spacing: -0.5px;")
        value_label.setObjectName("Value")
        self.body.addWidget(value_label)
        if helper:
            self.body.addWidget(muted_label(helper))


class StatusBadge(QLabel):
    """Colored badge for status values like RECEIVING, PASS, etc."""

    def __init__(self, text: str, color: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bg = color or COLORS["green"]
        self.setStyleSheet(
            f"background: {bg}; color: #ffffff; border-radius: 10px; "
            f"padding: 3px 10px; font-weight: 700; font-size: 10px; letter-spacing: 0.5px;"
        )


class DetailRow(QWidget):
    """A label: value pair displayed horizontally."""

    def __init__(self, label: str, value: str, value_color: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        lbl = QLabel(label)
        lbl.setObjectName("Muted")
        val = QLabel(value)
        val.setWordWrap(True)
        if value_color:
            val.setStyleSheet(f"color: {value_color}; font-weight: 600; background: transparent;")
        else:
            val.setObjectName("Value")
            val.setStyleSheet("font-weight: 600; background: transparent;")
        layout.addWidget(lbl)
        layout.addWidget(val, 1, Qt.AlignmentFlag.AlignRight)


class ProgressBar(QWidget):
    """Custom progress bar matching the image — colored fill on dark track."""

    def __init__(self, percent: int = 0, height: int = 12, color: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._percent = max(0, min(100, percent))
        self._color = color
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_percent(self, percent: int) -> None:
        new_pct = max(0, min(100, percent))
        if new_pct != self._percent:
            self._percent = new_pct
            self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        radius = h // 2
        # Track
        painter.setBrush(QColor(COLORS["panel_alt"]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, radius, radius)
        # Fill
        fill_w = int(w * self._percent / 100)
        if fill_w > 0:
            fill_color = QColor(self._color) if self._color else QColor(COLORS["green"])
            painter.setBrush(fill_color)
            painter.drawRoundedRect(0, 0, fill_w, h, radius, radius)
            # Subtle glow edge (bright highlight on top of fill)
            glow = QColor(fill_color)
            glow.setAlpha(80)
            glow_pen = QPen(glow, 1)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(0, 0, fill_w, h, radius, radius)
        painter.end()


class MetricGrid(QWidget):
    """Grid of MetricCards."""

    def __init__(self, metrics: list[tuple[str, str, str]], columns: int = 3, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for index, (title, value, helper) in enumerate(metrics):
            layout.addWidget(MetricCard(title, value, helper), index // columns, index % columns)


class ActivityLogTable(QWidget):
    """Scrollable activity log table matching the image design."""

    def __init__(self, entries: list[dict[str, str]] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "Event", "Details"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 140)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        layout.addWidget(self.table)
        self._last_count = -1

        if entries:
            self.update_entries(entries)

    def update_entries(self, entries: list[dict[str, str]]) -> None:
        num_entries = len(entries)
        self.table.setRowCount(num_entries)
        for row, entry in enumerate(entries):
            for col, key in enumerate(["time", "event", "details"]):
                txt = entry.get(key, "")
                item = self.table.item(row, col)
                if not item:
                    item = QTableWidgetItem(txt)
                    item.setForeground(QColor(COLORS["text"]))
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row, col, item)
                else:
                    if item.text() != txt:
                        item.setText(txt)
        if num_entries != self._last_count:
            self._last_count = num_entries
            self.table.setMinimumHeight(min(200, num_entries * 28 + 30))



class WaveformWidget(QWidget):
    """Signal waveform visualization. Shows live data when active, flat line when not."""

    def __init__(self, active: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setObjectName("ChartFrame")
        self._active = active
        self._samples: list[float] = []

    def set_active(self, active: bool) -> None:
        if active != self._active:
            self._active = active
            self.update()

    def set_samples(self, samples: list[float]) -> None:
        self._samples = samples
        self._active = True
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        
        left_margin = 45
        right_margin = 15
        top_margin = 15
        bottom_margin = 25
        
        plot_w = w - left_margin - right_margin
        plot_h = h - top_margin - bottom_margin

        # Background
        painter.fillRect(0, 0, w, h, QColor(COLORS["panel"]))

        if not self._active or not self._samples:
            # Inactive state: flat baseline with "No signal" overlay
            painter.setPen(QPen(QColor(COLORS["muted"]), 1, Qt.PenStyle.DashLine))
            mid_y = top_margin + plot_h // 2
            painter.drawLine(left_margin, mid_y, left_margin + plot_w, mid_y)
            painter.setPen(QColor(COLORS["muted"]))
            painter.setFont(QFont("Inter", 11))
            painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "No signal")
            painter.end()
            return

        # Grid lines
        painter.setPen(QPen(QColor(COLORS["chart_grid"]), 1))
        for y_frac in [0.25, 0.5, 0.75]:
            y = top_margin + plot_h * (1 - y_frac)
            painter.drawLine(left_margin, int(y), left_margin + plot_w, int(y))

        # Y-axis labels
        painter.setPen(QColor(COLORS["muted"]))
        painter.setFont(QFont("Inter", 9))
        for value, y_frac in [(3.3, 1.0), (1.65, 0.5), (0.0, 0.0)]:
            y = top_margin + plot_h * (1 - y_frac)
            painter.drawText(2, int(y) - 6, left_margin - 6, 12, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{value:.2f}")

        # X-axis labels
        for value, x_frac in [(0.0, 0.0), (1.5, 0.5), (3.0, 1.0)]:
            x = left_margin + plot_w * x_frac
            painter.drawText(int(x) - 20, h - bottom_margin + 2, 40, 12, Qt.AlignmentFlag.AlignCenter, f"{value:.1f}")

        # Waveform line
        path = QPainterPath()
        min_val = 0.0
        max_val = 3.3
        point_count = len(self._samples)
        step_x = plot_w / max(point_count - 1, 1)
        for i, sample in enumerate(self._samples):
            x = left_margin + i * step_x
            y_norm = (sample - min_val) / max(max_val - min_val, 1)
            y = top_margin + plot_h * (1 - y_norm)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        painter.setPen(QPen(QColor(COLORS["chart_line"]), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.end()


def primary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("Primary")
    return button


def secondary_button(text: str, parent: QWidget | None = None) -> QPushButton:
    """Secondary/ghost button, styled via QSS #Secondary objectName."""
    button = QPushButton(text, parent)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setObjectName("Secondary")
    return button


class ModeSelectCard(QFrame):
    """Clickable mode card with custom icon, title, description, and active glow border."""
    clicked = Signal()

    def __init__(self, title: str, description: str, icon_name: str, active: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ModeCard")
        self._active = active
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(100)
        self.setLineWidth(1)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        
        self.update_style()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        
        # Top row: Icon + Title
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        
        import qtawesome as qta
        self.icon_label = QLabel()
        self.icon_label.setPixmap(qta.icon(icon_name, color=COLORS["accent"]).pixmap(24, 24))
        self.icon_label.setStyleSheet("background: transparent;")
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #f3f4f6; background: transparent;")
        
        top_layout.addWidget(self.icon_label)
        top_layout.addWidget(self.title_label)
        top_layout.addStretch(1)
        layout.addLayout(top_layout)
        
        # Description
        self.desc_label = QLabel(description)
        self.desc_label.setObjectName("Muted")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 11px; background: transparent;")
        layout.addWidget(self.desc_label)
        
    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update_style()
            
    def update_style(self) -> None:
        if self._active:
            self.setStyleSheet(
                f"QFrame#ModeCard {{ background-color: {COLORS['sidebar_active']}; border: 2px solid {COLORS['accent']}; border-radius: 10px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame#ModeCard {{ background-color: {COLORS['panel']}; border: 1px solid {COLORS['border']}; border-radius: 10px; }}"
            )
            
    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)

class InfoIcon(QLabel):
    """A small circular '?' icon that shows a tooltip on hover."""
    def __init__(self, tooltip_text: str, parent: QWidget | None = None) -> None:
        super().__init__("?", parent)
        self.setToolTip(tooltip_text)
        self.setFixedSize(16, 16)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background: {COLORS["panel_alt"]};
                color: {COLORS["text"]};
                border-radius: 8px;
                font-size: 10px;
                font-weight: bold;
            }}
            QLabel:hover {{
                background: {COLORS["accent"]};
                color: white;
            }}
        """)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
