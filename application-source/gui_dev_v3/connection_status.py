"""Shared connection-state indicator used by both TX and RX workspaces."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from gui_dev_v3.theme import COLORS


class PulsingDot(QWidget):
    """Shared animated connection-state indicator."""

    _COLOR_MAP = {
        "connected":    "status_dot_on",
        "disconnected": "status_dot_off",
        "simulated":    "status_dot_sim",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._state = "disconnected"
        self._alpha = 255
        self._direction = -8
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        # Keep stable connection states calm; animate only while waiting.
        import os
        self._animations_enabled = os.environ.get("QT_QPA_PLATFORM") != "offscreen"

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        if self._animations_enabled and state == "simulated":
            if not self._anim_timer.isActive():
                self._anim_timer.start(40)
        else:
            self._anim_timer.stop()
            self._alpha = 255
        self.update()

    def _tick(self) -> None:
        self._alpha += self._direction
        if self._alpha <= 80:
            self._direction = 8
        elif self._alpha >= 255:
            self._direction = -8
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        from PySide6.QtGui import QPainter, QColor
        from PySide6.QtCore import Qt
        import os
        color_key = self._COLOR_MAP.get(self._state, "status_dot_off")
        color = QColor(COLORS.get(color_key, "#ef4444"))
        color.setAlpha(self._alpha)
        painter = QPainter(self)
        # Skip antialiasing in headless mode — drawEllipse AA is non-deterministic
        # between process launches on offscreen platform
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(1, 1, 8, 8)
        painter.end()

    def cleanup(self) -> None:
        self._anim_timer.stop()
