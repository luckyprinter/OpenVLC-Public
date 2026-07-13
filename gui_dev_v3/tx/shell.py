"""TX Shell — main container with sidebar navigation matching the TX design image."""
from __future__ import annotations

from datetime import datetime

import qtawesome as qta
from gui_dev_v3.tx.navigation import TX_SIDEBAR_TABS
from gui_dev_v3.tx.dashboard import TXDashboardPage
from gui_dev_v3.tx.file_manager_page import FileManagerPage
from gui_dev_v3.tx.placeholders import (
    AboutPage,
    LogsPage,
    TransmitPage,
)
from gui_dev_v3.tx.settings import build_tx_settings
from gui_dev_v3.settings import SettingsManager
from gui_dev_v3.tx_app_state import POLL_INTERVAL_MS, TXAppState, build_default_tx_state
from gui_dev_v3.widgets import scrollable
from gui_dev_v3.theme import COLORS

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QStackedWidget, QVBoxLayout, QWidget


class PulsingDot(QWidget):
    """A small animated pulsing dot for connection status indication."""

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
        # Skip animation in headless/test environments to avoid non-deterministic renders
        import os
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            self._anim_timer.start(40)

    def set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
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


class TXShell(QWidget):
    """Main TX shell with sidebar navigation matching the TX image design."""

    def __init__(self, state: TXAppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state or build_default_tx_state()
        self._settings_mgr = SettingsManager("tx")

        # Restore saved mode
        saved_mode: str = str(self._settings_mgr.get("general/mode", "physical"))
        if saved_mode in ("physical", "simulated") and saved_mode != self.state.mode:
            self.state.set_mode(saved_mode)  # type: ignore[arg-type]

        # Outer vertical layout: header | content | footer
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Content (sidebar + pages) ───────────────────────────────────
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        # ── Sidebar ────
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 16, 8, 12)
        sidebar_layout.setSpacing(4)

        # App title in sidebar
        title = QLabel("VLC Transmitter")
        title.setObjectName("Title")
        title.setStyleSheet(
            "font-size: 16px; padding-left: 6px;"
        )
        title.setWordWrap(True)
        sidebar_layout.addWidget(title)

        subtitle = QLabel("Visible Light\nCommunication")
        subtitle.setObjectName("Muted")
        subtitle.setStyleSheet(
            "font-size: 11px; padding-left: 6px; padding-bottom: 8px; min-height: 28px;"
        )
        sidebar_layout.addWidget(subtitle)

        # Navigation list
        self.nav = QListWidget()
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.setSpacing(2)
        sidebar_layout.addWidget(self.nav, 1)

        # ── Connection Info Card (bottom of sidebar) ────────────────────
        conn_card = QWidget()
        conn_card.setObjectName("Card")
        conn_card_layout = QVBoxLayout(conn_card)
        conn_card_layout.setContentsMargins(8, 8, 8, 8)
        conn_card_layout.setSpacing(4)

        # Status row: pulsing dot + label
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(6)
        self._pulse_dot = PulsingDot()
        self._conn_status = QLabel("Disconnected")
        self._conn_status.setStyleSheet("font-size: 10px; font-weight: 600; background: transparent;")
        status_row.addWidget(self._pulse_dot)
        status_row.addWidget(self._conn_status)
        status_row.addStretch(1)
        conn_card_layout.addLayout(status_row)

        self._conn_device = QLabel("Device: —")
        self._conn_device.setStyleSheet("font-size: 10px; background: transparent;")
        conn_card_layout.addWidget(self._conn_device)

        self._conn_firmware = QLabel("Firmware: —")
        self._conn_firmware.setStyleSheet("font-size: 10px; background: transparent;")
        conn_card_layout.addWidget(self._conn_firmware)

        sidebar_layout.addWidget(conn_card)

        # Version footer
        version = QLabel("v3.0 · PySide6")
        version.setObjectName("Muted")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("font-size: 10px; padding: 8px;")
        sidebar_layout.addWidget(version)

        content.addWidget(self.sidebar)

        # ── Content area ────────────────────────────────────────────────
        self.pages = QStackedWidget()
        content.addWidget(self.pages, 1)

        outer.addLayout(content, 1)

        # ── Footer Status Bar ───────────────────────────────────────────
        self._footer_bar = self._build_footer()
        outer.addWidget(self._footer_bar)

        # Build pages
        self._page_widgets: dict[str, QWidget] = {}
        self._build_pages()

        # Connect navigation
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self.nav.setCurrentRow(0)

        # Shell-level poll timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_poll_timer)
        self._timer.start(POLL_INTERVAL_MS)

    def _build_footer(self) -> QWidget:
        """Build bottom footer status bar."""
        footer = QWidget()
        footer.setObjectName("FooterBar")
        footer.setFixedHeight(28)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(24)

        # Mode indicator (left)
        self._footer_mode = QLabel("Mode: SIMULATED")
        self._footer_mode.setStyleSheet(
            "font-size: 10px; font-weight: 600; background: transparent;"
        )
        layout.addWidget(self._footer_mode)

        layout.addStretch(1)

        # Database status (right)
        self._footer_db = QLabel("Database: Connected")
        self._footer_db.setStyleSheet(
            f"font-size: 10px; color: {COLORS['green']}; background: transparent; font-weight: 600;"
        )
        layout.addWidget(self._footer_db)

        # Log status (right)
        self._footer_log = QLabel("Log: Recording")
        self._footer_log.setStyleSheet(
            f"font-size: 10px; color: {COLORS['green']}; background: transparent; font-weight: 600;"
        )
        layout.addWidget(self._footer_log)

        # Time clock (far right)
        self._footer_time = QLabel()
        self._footer_time.setStyleSheet(
            "font-size: 10px; font-weight: 700; background: transparent;"
        )
        layout.addWidget(self._footer_time)

        # Time update timer
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self._update_footer_time)
        self._time_timer.start(1000)
        self._update_footer_time()

        return footer

    def _update_footer_time(self) -> None:
        """Update the footer clock display."""
        now = datetime.now()
        self._footer_time.setText(now.strftime("%H:%M:%S"))

    def _update_status_indicators(self) -> None:
        """Update connection and mode indicators from current state."""
        connected = self.state.serial_connected
        mode = self.state.mode.upper() if hasattr(self.state, 'mode') else "SIMULATED"

        # Determine dot + header state
        if self.state.mode == "simulated":
            if connected:
                dot_state = "connected"
                status_text = "● Connected (Simulated)"
                status_color = COLORS.get("status_dot_on", COLORS["green"])
                self._conn_device.setText("Device: Simulated RX")
                self._conn_firmware.setText("Firmware: Virtual")
                conn_status_text = "Connected (Sim)"
            else:
                dot_state = "simulated"
                status_text = "● Waiting for RX (Simulated)"
                status_color = COLORS.get("status_dot_sim", COLORS["amber"])
                self._conn_device.setText("Device: —")
                self._conn_firmware.setText("Firmware: —")
                conn_status_text = "Searching (Sim)"
        else:
            if connected:
                dot_state = "connected"
                status_text = "● Connected"
                status_color = COLORS.get("status_dot_on", COLORS["green"])
                self._conn_device.setText("Device: VLC_TX")
                self._conn_firmware.setText("Firmware: v1.0")
                conn_status_text = "Connected"
            else:
                dot_state = "disconnected"
                status_text = "● Disconnected"
                status_color = COLORS.get("status_dot_off", COLORS["red"])
                self._conn_device.setText("Device: —")
                self._conn_firmware.setText("Firmware: —")
                conn_status_text = "Disconnected"


        # Sidebar pulsing dot + label
        self._pulse_dot.set_state(dot_state)
        self._conn_status.setText(conn_status_text)
        self._conn_status.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {status_color}; background: transparent;")

        # Footer mode
        self._footer_mode.setText(f"Mode: {mode}")

    def _on_mode_changed(self, mode: str) -> None:
        """Handle mode toggle from the sidebar."""
        self.state.set_mode(mode)  # type: ignore[arg-type]
        self._settings_mgr.set("general/mode", mode)
        self._update_status_indicators()
        self._refresh_current_page()

    def _refresh_current_page(self) -> None:
        """Call refresh() on the current page if it supports it."""
        current = self.pages.currentWidget()
        if current is not None:
            inner = current.widget() if hasattr(current, "widget") else current
            if hasattr(inner, "refresh"):
                try:
                    inner.refresh(self.state)
                except TypeError as e:
                    if "refresh() takes" in str(e) or "refresh() missing" in str(e):
                        pass
                    else:
                        raise e

    def _on_poll_timer(self) -> None:
        """Poll state and refresh the active page."""
        self.state.refresh()
        self._update_status_indicators()
        self._refresh_current_page()

    def _build_pages(self) -> None:
        self.nav.blockSignals(True)
        self.nav.clear()

        while self.pages.count():
            widget = self.pages.widget(0)
            self.pages.removeWidget(widget)
            widget.deleteLater()

        self._page_widgets.clear()

        page_map: dict[str, QWidget] = {
            "dashboard": TXDashboardPage(self.state),
            "transmit": TransmitPage(self.state),
            "file_manager": FileManagerPage(self.state),
            "settings": build_tx_settings(self.state),
            "logs": LogsPage(self.state),
        }

        for label, page_key, icon_name in TX_SIDEBAR_TABS:
            # Add icon + text to nav
            try:
                icon = qta.icon(icon_name)
            except Exception:
                icon = qta.icon("fa5s.circle")  # Fallback
            item = QListWidgetItem(icon, label)
            self.nav.addItem(item)
            page = page_map.get(page_key)
            if page:
                self._page_widgets[page_key] = page
                self.pages.addWidget(page)

        self.nav.blockSignals(False)

    def cleanup(self) -> None:
        """Stop poll timer and cleanup app state / backends."""
        if hasattr(self, "_timer") and self._timer:
            self._timer.stop()
        if hasattr(self, "_time_timer") and self._time_timer:
            self._time_timer.stop()
        if hasattr(self, "_pulse_dot"):
            self._pulse_dot.cleanup()
        if self.state:
            self.state.cleanup()

    def _on_nav_changed(self, index: int) -> None:
        if 0 <= index < len(TX_SIDEBAR_TABS):
            _, page_key, _ = TX_SIDEBAR_TABS[index]
            page = self._page_widgets.get(page_key)
            if page:
                self.pages.setCurrentWidget(page)
                # Refresh the page when navigated to
                inner = page.widget() if hasattr(page, "widget") else page
                if hasattr(inner, "refresh"):
                    try:
                        inner.refresh(self.state)
                    except TypeError as e:
                        if "refresh() takes" in str(e) or "refresh() missing" in str(e):
                            pass
                        else:
                            raise e
