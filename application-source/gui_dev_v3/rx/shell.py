"""RX Shell — main container with sidebar navigation matching the design image."""

from __future__ import annotations

from datetime import datetime

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QStackedWidget, QVBoxLayout, QWidget

from gui_dev_v3.connection_status import PulsingDot
from gui_dev_v3.app_state import POLL_INTERVAL_MS, RXAppState, build_default_state
from gui_dev_v3.navigation import SIDEBAR_TABS
from gui_dev_v3.settings import SettingsManager
from gui_dev_v3.rx.dashboard import RXDashboardPage
from gui_dev_v3.rx.receive_page import ReceivePage
from gui_dev_v3.rx.inspect_page import InspectPage
from gui_dev_v3.rx.placeholders import AboutPage
from gui_dev_v3.rx.signal_page import SignalMonitorPage
from gui_dev_v3.rx.settings import build_rx_settings
from gui_dev_v3.rx.study_data_page import StudyDataPage
from gui_dev_v3.rx.ber_analyzer_page import BERAnalyzerPage
from gui_dev_v3.widgets import scrollable
from gui_dev_v3.theme import COLORS
from gui_dev_v3.ui_foundation import (
    SidebarNavigationList,
    WorkspaceHeader,
    add_navigation_item,
)


class RXShell(QWidget):
    """Main RX shell with sidebar navigation matching the image design."""

    def __init__(self, state: RXAppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state or build_default_state()
        self._settings_mgr = SettingsManager("rx")

        # Restore saved mode
        saved_mode: str = str(self._settings_mgr.get("general/mode", "physical"))
        if saved_mode in ("physical", "simulated") and saved_mode != self.state.mode:
            self.state.set_mode(saved_mode)  # type: ignore[arg-type]

        # Outer vertical layout: content | footer
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Content (sidebar + pages) ───────────────────────────────────
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        # ── Sidebar ────
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(224)
        self.sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 16, 8, 12)
        sidebar_layout.setSpacing(4)

        # App title in sidebar
        title = QLabel("VLC Receiver")
        self._sidebar_title = title
        title.setObjectName("Title")
        title.setStyleSheet(
            "font-size: 17px; padding-left: 6px;"
        )
        title.setWordWrap(True)
        sidebar_layout.addWidget(title)

        subtitle = QLabel("Visible Light\nCommunication")
        self._sidebar_subtitle = subtitle
        subtitle.setObjectName("Muted")
        subtitle.setStyleSheet(
            "font-size: 12px; padding-left: 6px; padding-bottom: 8px; min-height: 30px;"
        )
        sidebar_layout.addWidget(subtitle)

        # Navigation list
        self.nav = SidebarNavigationList("Receiver", self.sidebar)
        self._nav_items: list[tuple[QListWidgetItem, str]] = []
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
        self._conn_status.setStyleSheet("font-size: 11px; font-weight: 600; background: transparent;")
        status_row.addWidget(self._pulse_dot)
        status_row.addWidget(self._conn_status)
        status_row.addStretch(1)
        conn_card_layout.addLayout(status_row)

        self._conn_device = QLabel("Device: —")
        self._conn_device.setStyleSheet("font-size: 11px; background: transparent;")
        conn_card_layout.addWidget(self._conn_device)

        self._conn_firmware = QLabel("Firmware: —")
        self._conn_firmware.setStyleSheet("font-size: 11px; background: transparent;")
        conn_card_layout.addWidget(self._conn_firmware)

        self._conn_card = conn_card
        sidebar_layout.addWidget(conn_card)

        # Version footer
        version = QLabel("v3.0 · PySide6")
        self._sidebar_version = version
        version.setObjectName("Muted")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("font-size: 11px; padding: 6px;")
        sidebar_layout.addWidget(version)

        content.addWidget(self.sidebar)

        # ── Main workspace: page header + active page ───────────────────
        main_area = QWidget()
        self._main_area = main_area
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._workspace_header = WorkspaceHeader("RECEIVER WORKSPACE")
        self._page_heading = self._workspace_header.page_heading
        main_layout.addWidget(self._workspace_header)

        self.pages = QStackedWidget()
        main_layout.addWidget(self.pages, 1)
        content.addWidget(main_area, 1)

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

        # Shell-level poll timer — refreshes state + active page every 1s
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_poll_timer)
        self._timer.start(POLL_INTERVAL_MS)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        """Use an icon-only sidebar on compact windows; keep normal font sizes."""
        super().resizeEvent(event)
        compact = self.width() < 1120
        if compact == getattr(self, "_compact_sidebar", None):
            return
        self._compact_sidebar = compact

        if compact:
            self.sidebar.setFixedWidth(72)
            self._sidebar_title.setText("VLC RX")
            self._sidebar_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._sidebar_title.setStyleSheet("font-size: 13px; font-weight: 700;")
            self._sidebar_subtitle.hide()
            self._sidebar_version.hide()
            self._conn_status.hide()
            self._conn_device.hide()
            self._conn_firmware.hide()
            self._conn_card.layout().setContentsMargins(6, 8, 6, 8)
            self.nav.setStyleSheet("QListWidget::item { padding: 10px 0; }")
            for item, label in self._nav_items:
                item.setText("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(label)
        else:
            self.sidebar.setFixedWidth(224)
            self._sidebar_title.setText("VLC Receiver")
            self._sidebar_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._sidebar_title.setStyleSheet("font-size: 17px; padding-left: 6px;")
            self._sidebar_subtitle.show()
            self._sidebar_version.show()
            self._conn_status.show()
            self._conn_device.show()
            self._conn_firmware.show()
            self._conn_card.layout().setContentsMargins(8, 8, 8, 8)
            self.nav.setStyleSheet("")
            for item, label in self._nav_items:
                item.setText(label)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

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
            "font-size: 11px; font-weight: 600; background: transparent;"
        )
        layout.addWidget(self._footer_mode)

        layout.addStretch(1)

        # Clock (right) — connection status is shown in the sidebar card.
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

        # Determine dot state and status text
        if self.state.mode == "simulated":
            if connected:
                dot_state = "connected"
                status_text = "Connected (Sim)"
                status_color = COLORS.get("status_dot_on", COLORS["green"])
                self._conn_device.setText("Device: Simulated TX")
                self._conn_firmware.setText("Firmware: Virtual")
            else:
                dot_state = "simulated"
                status_text = "Listening (Sim)"
                status_color = COLORS.get("status_dot_sim", COLORS["amber"])
                self._conn_device.setText("Device: —")
                self._conn_firmware.setText("Firmware: —")
        else:
            if connected:
                dot_state = "connected"
                status_text = "Connected"
                status_color = COLORS.get("status_dot_on", COLORS["green"])
                physical = getattr(self.state, "_physical", None)
                port = getattr(physical, "port", None) if physical else None
                firmware_info = getattr(physical, "_firmware_info", None) if physical else None
                firmware_name = (firmware_info or {}).get("firmware", "")
                if firmware_name and firmware_name not in ("rx_unknown", "rx_forced"):
                    firmware_label = firmware_name
                elif firmware_name == "rx_forced":
                    firmware_label = "Force-connected · version unknown"
                else:
                    firmware_label = "Detected · version not reported"
                device_suffix = f" ({port})" if port else ""
                self._conn_device.setText(f"Device: VLC_RX{device_suffix}")
                self._conn_firmware.setText(f"Firmware: {firmware_label}")
            else:
                dot_state = "disconnected"
                status_text = "Disconnected"
                status_color = COLORS.get("status_dot_off", COLORS["red"])
                self._conn_device.setText("Device: —")
                self._conn_firmware.setText("Firmware: —")

        self._pulse_dot.set_state(dot_state)
        self._conn_status.setText(status_text)
        self._conn_status.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {status_color}; background: transparent;")

        # Footer mode
        self._footer_mode.setText(f"Mode: {mode}")

    def _on_mode_changed(self, mode: str) -> None:
        """Handle mode toggle from the sidebar — switch mode and refresh current page."""
        self.state.set_mode(mode)  # type: ignore[arg-type]
        self._settings_mgr.set("general/mode", mode)
        self._update_status_indicators()
        # Refresh the current page after mode switch
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

        # Remove all pages from stack
        while self.pages.count():
            widget = self.pages.widget(0)
            self.pages.removeWidget(widget)
            widget.deleteLater()

        self._page_widgets.clear()

        # Create page instances
        page_map: dict[str, QWidget] = {
            "dashboard": RXDashboardPage(self.state),
            "receive": ReceivePage(),
            "inspect": InspectPage(),
            "signal": SignalMonitorPage(self.state),
            "ber_analyzer": BERAnalyzerPage(),
            "study_data": StudyDataPage(),
            "settings": build_rx_settings(self.state),
        }

        for label, page_key, icon_name in SIDEBAR_TABS:
            # Add icon + text to nav
            try:
                icon = qta.icon(icon_name, color=COLORS["text"])
            except Exception:
                icon = qta.icon("fa5s.circle", color=COLORS["text"])  # Fallback
            item = add_navigation_item(self.nav, icon, label)
            self._nav_items.append((item, label))
            page = page_map.get(page_key)
            if page:
                # Dense analysis pages can exceed a laptop's logical height at
                # 125–150% scaling. Give them one predictable vertical scroll
                # surface; their own responsive layouts handle horizontal flow.
                page_container = scrollable(page) if page_key in {"receive", "inspect", "signal", "ber_analyzer"} else page
                self._page_widgets[page_key] = page_container
                self.pages.addWidget(page_container)

        self.nav.blockSignals(False)

    def cleanup(self) -> None:
        """Stop poll timer and cleanup app state / backends."""
        if hasattr(self, "_timer") and self._timer:
            self._timer.stop()
        if hasattr(self, "_time_timer") and self._time_timer:
            self._time_timer.stop()
        if hasattr(self, "_pulse_dot"):
            self._pulse_dot.cleanup()

        # Stop timers in SignalMonitorPage
        signal_page = self._page_widgets.get("signal")
        if signal_page:
            inner_page = signal_page.widget() if hasattr(signal_page, "widget") else signal_page
            if hasattr(inner_page, "shutdown"):
                inner_page.shutdown()

        if self.state:
            self.state.cleanup()

    def _on_nav_changed(self, index: int) -> None:
        if 0 <= index < len(SIDEBAR_TABS):
            label, page_key, _ = SIDEBAR_TABS[index]
            self._page_heading.setText(label)
            page = self._page_widgets.get(page_key)
            if page:
                self.pages.setCurrentWidget(page)
                # Refresh the page when navigated to
                inner = page.widget() if hasattr(page, "widget") else page
                if hasattr(inner, "refresh"):
                    try:
                        inner.refresh(self.state)
                    except TypeError:
                        pass
