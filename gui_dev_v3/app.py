"""VLC Receiver / Transmitter Application — Main entry points.

- main() launches the VLC Receiver (RX) UI.
- main_tx() launches the VLC Transmitter (TX) UI.
Both share theme, widgets, and data layers for future merging.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QAction, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui_dev_v3.app_state import build_default_state
from gui_dev_v3.rx.shell import RXShell
from gui_dev_v3.settings_store import AppSettings, RESOLUTION_PRESETS, load_settings, save_settings
from gui_dev_v3.theme import APP_QSS, apply_theme, build_qss, THEME_PRESETS, COLORS
from gui_dev_v3.tx.shell import TXShell
from gui_dev_v3.tx_app_state import build_default_tx_state
from gui_dev_v3.widgets import ModeSelectCard  # noqa: F401 — kept for legacy compat


# ── Core Infrastructure ───────────────────────────────────────────────────


def load_bundled_fonts() -> None:
    """Load all TTF files in the assets/fonts directory into QFontDatabase."""
    font_dir = Path(__file__).parent / "assets" / "fonts"
    if font_dir.exists():
        for font_file in font_dir.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font_file))


# ── Design Loader ──────────────────────────────────────────────────────

def load_design_tokens() -> dict:
    """Load design tokens from design.json if it exists."""
    design_path = Path(__file__).parent.parent.parent / "design.json"
    if design_path.exists():
        try:
            with open(design_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def apply_design_tokens(tokens: dict) -> None:
    """Apply design tokens to the theme system."""
    if not tokens:
        return
    # Import here to avoid circular import
    from gui_dev_v3.theme import apply_design_tokens as _apply
    _apply(tokens)


class _BaseWindow(QMainWindow):
    """Shared base window for both RX and TX apps."""

    fullscreen_changed = Signal(bool)

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.setMinimumSize(QSize(1024, 700))
        self.settings = load_settings()
        self._apply_display_mode()
        self._apply_theme()
        # Apply stored resolution after the window is shown
        self._pending_resolution = self.settings.resolution

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        # Apply stored resolution once the window is visible
        if self._pending_resolution:
            self.set_resolution(self._pending_resolution)
            self._pending_resolution = ""

    def _apply_display_mode(self) -> None:
        """Apply borderless flag from settings before show()."""
        if self.settings.borderless:
            self.setWindowFlag(Qt.FramelessWindowHint, True)
        # Fullscreen is NOT re-applied on launch (design decision)

    def _apply_theme(self) -> None:
        apply_theme(theme=self.settings.theme, accent=self.settings.accent, density=self.settings.density)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_qss())
        else:
            self.setStyleSheet(build_qss())

    def set_resolution(self, preset_key: str) -> None:
        """Look up preset and resize window, enforcing minimum size."""
        for key, w, h in RESOLUTION_PRESETS:
            if key == preset_key:
                self.settings.resolution = preset_key
                # Enforce minimum size of 1024x700
                w = max(w, 1024)
                h = max(h, 700)
                self.resize(w, h)
                return
        # Fallback to default if preset not found
        self.settings.resolution = "1280x800"
        self.resize(1280, 800)

    def toggle_fullscreen(self) -> None:
        """Toggle between fullscreen and normal window mode."""
        if self.isFullScreen():
            self.showNormal()
            self.settings.fullscreen = False
        else:
            self.showFullscreen()
            self.settings.fullscreen = True
        self.fullscreen_changed.emit(self.isFullScreen())

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        from gui_dev_v3.settings_store import load_settings, save_settings
        latest = load_settings()
        latest.resolution = self.settings.resolution
        latest.fullscreen = self.settings.fullscreen
        latest.borderless = self.settings.borderless
        save_settings(latest)
        super().closeEvent(event)

# ── Launcher Page ──────────────────────────────────────────────────────


class _ConsoleCard(QFrame):
    """Premium launcher card: icon + title + description + launch hint."""
    clicked = Signal()

    def __init__(self, title: str, description: str, icon_name: str, accent_label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ConsoleCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(QSize(310, 180))
        self.setMaximumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        # Icon + Title row
        top = QHBoxLayout()
        top.setSpacing(12)
        import qtawesome as qta
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon(icon_name, color=COLORS.get("accent", "#3b82f6")).pixmap(28, 28))
        icon_lbl.setFixedSize(QSize(32, 32))
        icon_lbl.setStyleSheet("background: transparent;")
        top.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("CardTitle")
        top.addWidget(title_lbl)
        top.addStretch(1)
        layout.addLayout(top)

        # Description
        desc_lbl = QLabel(description)
        desc_lbl.setObjectName("CardDesc")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        layout.addStretch(1)

        # Launch hint
        launch_lbl = QLabel(accent_label + "  →")
        launch_lbl.setObjectName("CardAccent")
        launch_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(launch_lbl)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class VLCLauncherPage(QWidget):
    """Premium launcher screen — branded hero with TX / RX console cards."""

    def __init__(self, main_window: "VLCMainWindow", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._main_window = main_window

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Center content ──────────────────────────────────────────
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(64, 0, 64, 0)
        center_layout.setSpacing(0)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Brand badge (VLC acronym pill)
        badge_row = QHBoxLayout()
        badge_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge = QLabel("VLC")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setObjectName("DemoBadge")
        badge.setFixedSize(QSize(56, 28))
        badge.setStyleSheet(
            f"background: {COLORS.get('accent_glow','#3b82f620')}; "
            f"color: {COLORS.get('accent','#3b82f6')}; "
            "border: 1px solid currentColor; border-radius: 14px; "
            "font-size: 12px; font-weight: 800; letter-spacing: 2px;"
        )
        badge_row.addWidget(badge)
        center_layout.addLayout(badge_row)
        center_layout.addSpacing(20)

        # App title
        title = QLabel("VISIBLE LIGHT COMM SUITE")
        title.setObjectName("LauncherTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(title)
        center_layout.addSpacing(10)

        # Subtitle
        subtitle = QLabel("Select an operational console mode to initialize the link")
        subtitle.setObjectName("LauncherSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(subtitle)
        center_layout.addSpacing(48)

        # Console cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)
        cards_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tx_card = _ConsoleCard(
            "Transmitter Console",
            "Configure payloads, set symbol rates, and stream\nvisible light data from your TX hardware.",
            "fa5s.broadcast-tower",
            "Launch TX",
        )
        tx_card.clicked.connect(lambda: self._main_window.launch_mode("tx"))

        rx_card = _ConsoleCard(
            "Receiver Console",
            "Capture optical signals, inspect bit streams,\nrun BER analysis, and build test matrices.",
            "fa5s.arrow-circle-down",
            "Launch RX",
        )
        rx_card.clicked.connect(lambda: self._main_window.launch_mode("rx"))

        cards_row.addWidget(tx_card)
        cards_row.addWidget(rx_card)
        center_layout.addLayout(cards_row)

        root.addStretch(2)
        root.addWidget(center)
        root.addStretch(3)

        # ── Bottom version bar ──────────────────────────────────────
        footer = QWidget()
        footer.setObjectName("FooterBar")
        footer.setFixedHeight(28)
        footer_lo = QHBoxLayout(footer)
        footer_lo.setContentsMargins(24, 0, 24, 0)

        ver = QLabel("OpenVLC System Suite  ·  v3.0  ·  PySide6")
        ver.setObjectName("LauncherBadge")
        footer_lo.addWidget(ver)
        footer_lo.addStretch(1)

        hw = QLabel("ESP32 Platform  ·  OOK / NRZ Modulation")
        hw.setObjectName("LauncherBadge")
        footer_lo.addWidget(hw)
        root.addWidget(footer)


# ── Unified Main Window ───────────────────────────────────────────────


class VLCMainWindow(_BaseWindow):
    """Unified main window containing the launcher and RX/TX console modes."""

    def __init__(self) -> None:
        super().__init__("VLC System Suite")
        
        self._stack = QStackedWidget(self)
        self.setCentralWidget(self._stack)

        # Launcher Page
        self._launcher = VLCLauncherPage(self)
        self._stack.addWidget(self._launcher)

        self._rx_shell = None
        self._tx_shell = None
        self._rx_state = None
        self._tx_state = None

        self._stack.setCurrentWidget(self._launcher)

    def launch_mode(self, mode: str) -> None:
        if mode == "tx":
            if self._tx_shell is None:
                self._tx_state = build_default_tx_state()
                self._tx_shell = TXShell(self._tx_state)
                self._stack.addWidget(self._tx_shell)
            self._stack.setCurrentWidget(self._tx_shell)
            self.setWindowTitle("VLC Transmitter")
        elif mode == "rx":
            if self._rx_shell is None:
                self._rx_state = build_default_state()
                self._rx_shell = RXShell(self._rx_state)
                self._stack.addWidget(self._rx_shell)
            self._stack.setCurrentWidget(self._rx_shell)
            self.setWindowTitle("VLC Receiver")

    def return_to_launcher(self) -> None:
        if self._rx_shell is not None:
            try:
                self._rx_shell.cleanup()
            except Exception:
                pass
            self._stack.removeWidget(self._rx_shell)
            self._rx_shell.deleteLater()
            self._rx_shell = None
            self._rx_state = None
        if self._tx_shell is not None:
            try:
                self._tx_shell.cleanup()
            except Exception:
                pass
            self._stack.removeWidget(self._tx_shell)
            self._tx_shell.deleteLater()
            self._tx_shell = None
            self._tx_state = None
        self._stack.setCurrentWidget(self._launcher)
        self.setWindowTitle("VLC System Suite")


# Legacy support
class VLCReceiverWindow(_BaseWindow):
    """Main window for the VLC Receiver (RX) application."""

    def __init__(self) -> None:
        super().__init__("VLC Receiver")
        self.state = build_default_state()
        self.shell = RXShell(self.state)
        self.setCentralWidget(self.shell)


class VLCTransmitterWindow(_BaseWindow):
    """Main window for the VLC Transmitter (TX) application."""

    def __init__(self) -> None:
        super().__init__("VLC Transmitter")
        self.state = build_default_tx_state()
        self.shell = TXShell(self.state)
        self.setCentralWidget(self.shell)


def main() -> int:
    """Launch the unified VLC System Suite."""
    design_tokens = load_design_tokens()
    apply_design_tokens(design_tokens)
    
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    load_bundled_fonts()
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)
    
    window = VLCMainWindow()
    
    # Process CLI flags
    if "--tx" in sys.argv:
        window.launch_mode("tx")
    elif "--rx" in sys.argv:
        window.launch_mode("rx")
        
    window.show()
    return app.exec()


def main_tx() -> int:
    """Launch the VLC Transmitter directly (legacy/wrapper)."""
    if "--tx" not in sys.argv and "--rx" not in sys.argv:
        sys.argv.append("--tx")
    return main()


if __name__ == "__main__":
    raise SystemExit(main())
