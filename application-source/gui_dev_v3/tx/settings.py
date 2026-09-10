"""TX Settings — 4-section multi-tab settings page with persistence."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton

from gui_dev_v3.settings import (
    BrowseButton,
    ComboSetting,
    RadioGroup,
    SettingsManager,
    SettingRow,
    SettingsContainer,
    SpinSetting,
    bind_combo,
    bind_spin,
    bind_radio_group,
    bind_slider_spin,
    bind_theme_picker,
    bind_radio_node,
    SliderSpinSetting,
    FreeformSpinSetting,
    RadioNodeSetting,
    ThemePickerGrid,
)
from gui_dev_v3.settings_store import RESOLUTION_PRESETS
from gui_dev_v3.tx_app_state import TXAppState
from gui_dev_v3.widgets import Card, muted_label, ModeSelectCard, primary_button

# ── General & Display ──────────────────────────────────────────────────

class GeneralDisplayPage(QWidget):
    def __init__(self, mgr: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(12)

        theme_card = Card("Theme")
        from gui_dev_v3.settings_store import load_settings
        current_preset = str(mgr.get("general/theme", load_settings().theme) or "midnight_navy")
        self._theme_picker = ThemePickerGrid(current=current_preset)
        bind_theme_picker(self._theme_picker, mgr, "general/theme", current_preset)
        theme_card.body.addWidget(self._theme_picker)
        lo.addWidget(theme_card)

        startup_card = Card("Startup")
        remember = RadioNodeSetting(True)
        bind_radio_node(remember, mgr, "general/remember_mode", True)
        startup_card.body.addWidget(SettingRow("Remember Last Mode", remember))
        startup_card.body.addWidget(SettingRow("Default Save Directory", BrowseButton()))
        auto_load = RadioNodeSetting(True)
        bind_radio_node(auto_load, mgr, "general/auto_load_session", True)
        startup_card.body.addWidget(SettingRow("Auto Load Previous Session", auto_load))
        lo.addWidget(startup_card)

        res_card = Card("Window & Display")
        self._res_combo = ComboSetting([key for key, _, _ in RESOLUTION_PRESETS], "1280x800")
        res_card.body.addWidget(SettingRow("Resolution", self._res_combo))
        
        self._fullscreen_toggle = RadioNodeSetting(False)
        res_card.body.addWidget(SettingRow("Fullscreen (F11)", self._fullscreen_toggle))

        self._borderless_toggle = RadioNodeSetting(False)
        res_card.body.addWidget(SettingRow("Borderless Window", self._borderless_toggle))
        lo.addWidget(res_card)

        launcher_card = Card("System Actions")
        self.switch_btn = QPushButton("  \u2190  Return to Mode Selection Launcher")
        self.switch_btn.setObjectName("Primary")
        self.switch_btn.clicked.connect(self._on_switch_mode_clicked)
        
        self.reset_btn = QPushButton("Reset to Default Settings")
        self.reset_btn.setObjectName("Danger")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        
        launcher_card.body.addWidget(self.switch_btn)
        launcher_card.body.addWidget(self.reset_btn)
        lo.addWidget(launcher_card)

        lo.addStretch(1)

        self._mgr = mgr
        self._window = None
        self._connected = False

    def _get_window(self):
        if self._window is None:
            w = self.parentWidget()
            while w is not None:
                if callable(getattr(w, "set_resolution", None)) and callable(getattr(w, "toggle_fullscreen", None)):
                    self._window = w
                    break
                w = w.parentWidget()
        return self._window

    def _on_reset_clicked(self) -> None:
        self._mgr.clear()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Settings Reset", "All settings have been reset to defaults. Please restart the application for all changes to take effect.")

    def _on_switch_mode_clicked(self) -> None:
        window = self._get_window()
        if window and hasattr(window, "return_to_launcher"):
            window.return_to_launcher()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._connected:
            return
        window = self._get_window()
        if window is None:
            return
        self._connected = True

        self._res_combo.setCurrentText(window.settings.resolution)
        self._fullscreen_toggle.setChecked(window.settings.fullscreen)
        self._borderless_toggle.setChecked(window.settings.borderless)

        self._res_combo.currentTextChanged.connect(lambda key: window.set_resolution(key))

        def _on_fullscreen_toggled(checked: bool) -> None:
            window.toggle_fullscreen()
        self._fullscreen_toggle.toggled.connect(_on_fullscreen_toggled)

        def _on_fullscreen_changed(is_fs: bool) -> None:
            self._fullscreen_toggle.blockSignals(True)
            self._fullscreen_toggle.setChecked(is_fs)
            self._fullscreen_toggle.blockSignals(False)
        window.fullscreen_changed.connect(_on_fullscreen_changed)

        def _on_borderless_toggled(checked: bool) -> None:
            window.settings.borderless = checked
            if not window.isFullScreen():
                window.setWindowFlag(Qt.FramelessWindowHint, checked)
                window.show()
        self._borderless_toggle.toggled.connect(_on_borderless_toggled)


# ── Hardware Connection ──────────────────────────────────────────────

class HardwareConnectionPage(QWidget):
    def __init__(self, mgr: SettingsManager, state: TXAppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mgr = mgr
        self._state = state

        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(12)



        self.opts_card = Card("Connection Options")
        mode_group = RadioGroup(["Auto Detect (Recommended)", "Manual"], selected="Auto Detect (Recommended)")
        bind_radio_group(mode_group, mgr, "connection/mode", "Auto Detect (Recommended)")
        self.opts_card.body.addWidget(mode_group)

        port_layout = QHBoxLayout()
        self.port_combo = ComboSetting([], "")
        from gui_dev_v3.tx.backends.physical import _list_usb_serial_ports
        
        def _refresh_ports():
            self.port_combo.blockSignals(True)
            self.port_combo.clear()
            ports = _list_usb_serial_ports()
            saved = mgr.get("connection/port", "")
            
            if saved and saved not in ports:
                ports.insert(0, saved)
                
            if ports:
                self.port_combo.addItems(ports)
                if saved:
                    self.port_combo.setCurrentText(saved)
            else:
                self.port_combo.addItem("No ports found")
            self.port_combo.blockSignals(False)
                
        _refresh_ports()
        bind_combo(self.port_combo, mgr, "connection/port", "")
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(_refresh_ports)
        
        force_btn = QPushButton("Force Connect")
        force_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        force_btn.setToolTip("Bypass verification and force open this COM port.")
        force_btn.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b;
                color: #1e1e1e;
                font-weight: 600;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover { background-color: #fbbf24; }
        """)
        def _on_force_connect():
            port = self.port_combo.currentText()
            if port and port != "No ports found" and self._state:
                self._state.set_mode("physical")
                for btn in mode_group._buttons:
                    if btn.text() == "Manual":
                        btn.setChecked(True)
                        break
                self._mgr.set("connection/port", port)
                self._state.force_connect_serial(port)
                self._show_toast(f"Forced connection to {port}")
        force_btn.clicked.connect(_on_force_connect)
        
        port_layout.addWidget(QLabel("Target Port:"))
        port_layout.addWidget(self.port_combo, 1)
        port_layout.addWidget(refresh_btn)
        port_layout.addWidget(force_btn)
        self.opts_card.body.addLayout(port_layout)

        auto_conn = RadioNodeSetting(True)
        bind_radio_node(auto_conn, mgr, "connection/auto_connect", True)
        self.opts_card.body.addWidget(SettingRow("Auto Connect On Startup", auto_conn))

        scan_spin = SpinSetting(3, 1, 60, "seconds")
        bind_spin(scan_spin, mgr, "connection/scan_interval", 3)
        self.opts_card.body.addWidget(SettingRow("Port Scan Interval", scan_spin))

        timeout_spin = SpinSetting(5, 1, 120, "seconds")
        bind_spin(timeout_spin, mgr, "connection/timeout", 5)
        self.opts_card.body.addWidget(SettingRow("Connection Timeout", timeout_spin))
        lo.addWidget(self.opts_card)

        self.status_card = Card("Live Status")
        self._port_label = muted_label("Port: —")
        self._conn_label = muted_label("Status: —")
        self.status_card.body.addWidget(self._port_label)
        self.status_card.body.addWidget(self._conn_label)
        lo.addWidget(self.status_card)
        lo.addStretch(1)



    def refresh(self, state: TXAppState) -> None:
        if state is None:
            return
        if state.serial_connected:
            self._port_label.setText(f"Port: {state.port or '—'}")
            self._conn_label.setText("Status: Connected")
            return
        self._port_label.setText(f"Port: {state.port or '—'}")
        self._conn_label.setText("Status: Disconnected")

    def _show_toast(self, msg: str) -> None:
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import QTimer, Qt
        from gui_dev_v3.theme import COLORS
        toast = QLabel(msg, self.window())
        toast.setObjectName("Toast")
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.setStyleSheet(
            f"background: {COLORS['panel']}; color: {COLORS['text']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 8px; "
            f"padding: 10px 20px; font-weight: 700;"
        )
        toast.adjustSize()
        toast.move(self.window().width() - toast.width() - 20, self.window().height() - toast.height() - 20)
        toast.show()
        QTimer.singleShot(2000, toast.deleteLater)


# ── TX Settings ──────────────────────────────────────────────────────

class TXSettingsPage(QWidget):
    def __init__(self, mgr: SettingsManager, state: TXAppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mgr = mgr
        self._state = state
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(12)

        params_card = Card("Default Parameters")
        
        chunk_items = ["64", "128", "256", "512", "1024"]
        chunk_val = str(mgr.get("transmission/chunk_size", 512))
        if chunk_val not in chunk_items:
            chunk_val = "512"
        self.chunk_combo = ComboSetting(chunk_items, chunk_val)
        bind_combo(self.chunk_combo, mgr, "transmission/chunk_size", chunk_val)
        self.chunk_combo.currentTextChanged.connect(lambda v: mgr.set("transmission/chunk_size", int(v)))
        params_card.body.addWidget(SettingRow("Default Chunk Size", self.chunk_combo, "Size of each data chunk in bytes. 512 is recommended. Must match ESP32 DMA buffer limits."))

        delay_spin = FreeformSpinSetting(0, rec_min=0, rec_max=9999, suffix="ms")
        bind_spin(delay_spin, mgr, "transmission/delay", 0)
        params_card.body.addWidget(SettingRow("Transmission Delay", delay_spin, "Artificial delay added before starting the transmission on the PC side."))
        lo.addWidget(params_card)

        self.link_card = Card("Link & Modulation Parameters")
        self.link_card.body.setSpacing(8)
        
        self.freq_set = FreeformSpinSetting(value=15000, rec_min=1000, rec_max=50000, suffix="Hz")
        bind_spin(self.freq_set, mgr, "link/symbol_hz", 15000)
        self.link_card.body.addWidget(SettingRow("Symbol Frequency", self.freq_set, "Controls the symbol clock speed. Higher values increase data rate but reduce range."))

        self.preamble_set = FreeformSpinSetting(64, rec_min=16, rec_max=512, suffix="bits")
        bind_spin(self.preamble_set, mgr, "link/preamble_bits", 64)
        self.link_card.body.addWidget(SettingRow("Preamble Bits", self.preamble_set, "Number of alternating bits sent before the sync word. Helps the receiver lock onto the signal."))
        
        self.gap_set = FreeformSpinSetting(0, rec_min=0, rec_max=10000, suffix="ms")
        bind_spin(self.gap_set, mgr, "link/post_frame_idle_ms", 0)
        self.link_card.body.addWidget(SettingRow("Post-Frame Idle", self.gap_set, "Optional millisecond delay after a frame completes before the next can begin."))
        
        self.fgap_set = FreeformSpinSetting(1, rec_min=0, rec_max=1000, suffix="ms")
        bind_spin(self.fgap_set, mgr, "link/frame_gap_ms", 1)
        self.link_card.body.addWidget(SettingRow("Frame Gap", self.fgap_set, "Millisecond gap injected between the preamble and payload of a frame."))
        
        self.active_low_set = RadioNodeSetting(True)
        bind_radio_node(self.active_low_set, mgr, "link/active_low", True)
        self.link_card.body.addWidget(SettingRow("Active Low Driver", self.active_low_set, "Inverts the GPIO logic. Use ON if the LED turns on when GPIO is LOW."))
        
        self.idle_on_set = RadioNodeSetting(True)
        bind_radio_node(self.idle_on_set, mgr, "link/idle_on", True)
        self.link_card.body.addWidget(SettingRow("Keep LED On at Idle", self.idle_on_set, "Keeps the transmitter LED illuminated when not sending data, providing continuous ambient light."))
        
        self.intensity_set = FreeformSpinSetting(35, rec_min=0, rec_max=100, suffix="%")
        bind_spin(self.intensity_set, mgr, "link/cal_intensity_pct", 100)
        self.link_card.body.addWidget(SettingRow("Cal Intensity", self.intensity_set, "The PWM duty cycle percentage used for the 'Idle On' continuous light."))
        
        self.quiet_set = RadioNodeSetting(True)
        bind_radio_node(self.quiet_set, mgr, "link/quiet_mode", True)
        self.link_card.body.addWidget(SettingRow("Quiet Mode", self.quiet_set, "Suppresses verbose serial debug output from the ESP32 to save serial bandwidth."))
        
        self.dma_set = RadioNodeSetting(False)
        bind_radio_node(self.dma_set, mgr, "link/dma_mode", False)
        self.link_card.body.addWidget(SettingRow("DMA Double-Buffering Mode", self.dma_set, "Experimental: streams chunks in real-time using a dual-core pipeline."))
        
        self.apply_btn = primary_button("Apply Hardware Settings")
        self.apply_btn.clicked.connect(self._on_apply_settings)
        self.link_card.body.addWidget(self.apply_btn)
        
        lo.addWidget(self.link_card)

        retry_card = Card("Retry")
        enable_retry = RadioNodeSetting(True)
        bind_radio_node(enable_retry, mgr, "transmission/enable_retry", True)
        retry_card.body.addWidget(SettingRow("Enable Retry", enable_retry))

        max_retry = SpinSetting(3, 0, 99)
        bind_spin(max_retry, mgr, "transmission/max_retries", 3)
        retry_card.body.addWidget(SettingRow("Maximum Retries", max_retry))
        lo.addWidget(retry_card)

        live_card = Card("Current Session")
        live_card.body.setSpacing(6)
        live_card.body.addWidget(muted_label("Live link parameters for the active session:"))
        self._symbol_rate_label = muted_label("Symbol Rate: —")
        self._tx_power_label = muted_label("TX Power: —")
        live_card.body.addWidget(self._symbol_rate_label)
        live_card.body.addWidget(self._tx_power_label)
        lo.addWidget(live_card)
        lo.addStretch(1)

        current_mode = state.mode if state else str(mgr.get("general/mode", "physical"))
        self._update_visibility(current_mode)

    def _on_apply_settings(self) -> None:
        if not self._state:
            return
        
        freq = self.freq_set.value()
        preamble = self.preamble_set.value()
        gap = self.gap_set.value()
        fgap = self.fgap_set.value()
        active_low = self.active_low_set.isChecked()
        idle_on = self.idle_on_set.isChecked()
        intensity = self.intensity_set.value()
        quiet = self.quiet_set.isChecked()
        dma_mode = self.dma_set.isChecked()

        if self._state.mode == "physical":
            # Use the gated helper so DMA_MODE/PREAMBLE/CARRIER are only sent
            # to DMA-capable firmware. Sending them to tx_non_dma.ino causes
            # 'TX_ERROR: unknown command' which disrupts the non-DMA blinking.
            self._state.apply_link_settings_from_ui(
                freq=freq,
                preamble=preamble,
                gap=gap,
                fgap=fgap,
                active_low=active_low,
                idle_on=idle_on,
                intensity=intensity,
                quiet=quiet,
                dma_mode=dma_mode,
            )
        else:
            self._state.update_simulation_params(
                symbol_hz=freq,
                preamble_bits=preamble,
                post_frame_idle_ms=gap,
                frame_gap_ms=fgap,
                active_low=active_low,
                idle_on=idle_on,
                cal_intensity_pct=intensity,
                quiet_mode=quiet
            )

    def _update_visibility(self, mode: str) -> None:
        pass

    def _update_link_param(self, command_key: str, value: Any) -> None:
        if not self._state:
            return
        if self._state.mode == "physical":
            if command_key != "PREAMBLE_BITS":
                self._state.send_firmware_command(f"{command_key}={value}\n")
        else:
            mapping = {
                "FREQ": "symbol_hz",
                "PREAMBLE_BITS": "preamble_bits",
                "GAP": "post_frame_idle_ms",
                "FGAP": "frame_gap_ms",
                "ACTIVE_LOW": "active_low",
                "IDLE_ON": "idle_on",
                "INTENSITY": "cal_intensity_pct",
                "QUIET": "quiet_mode",
            }
            param_name = mapping.get(command_key)
            if param_name:
                if command_key in ("ACTIVE_LOW", "IDLE_ON", "QUIET"):
                    val_bool = (value != 0)
                    self._state.update_simulation_params(**{param_name: val_bool})
                else:
                    self._state.update_simulation_params(**{param_name: value})

    def refresh(self, state: TXAppState) -> None:
        if state is None:
            return
        self._symbol_rate_label.setText(f"Symbol Rate: {state.symbol_rate or '—'}")
        self._tx_power_label.setText(f"TX Power: {state.tx_power or '—'}")


# ── Diagnostics & Logs ───────────────────────────────────────────────

class DiagnosticsLogsPage(QWidget):
    def __init__(self, mgr: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(12)

    def _show_toast(self, msg: str) -> None:
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import QTimer, Qt
        from gui_dev_v3.theme import COLORS
        toast = QLabel(msg, self.window())
        toast.setObjectName("Toast")
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.setStyleSheet(
            f"background: {COLORS['panel']}; color: {COLORS['amber']}; "
            f"border: 1px solid {COLORS['amber']}; border-radius: 8px; "
            f"padding: 10px 20px; font-weight: 700;"
        )
        toast.adjustSize()
        toast.move(self.window().width() - toast.width() - 20, self.window().height() - toast.height() - 20)
        toast.show()
        QTimer.singleShot(2000, toast.deleteLater)

        save_card = Card("Logging Settings")
        save_tx = RadioNodeSetting(True)
        bind_radio_node(save_tx, mgr, "logging/save_transmission", True)
        save_card.body.addWidget(SettingRow("Save Transmission Logs", save_tx))

        level_combo = ComboSetting(["Debug", "Info", "Warning", "Error"], "Info")
        bind_combo(level_combo, mgr, "logging/level", "Info")
        save_card.body.addWidget(SettingRow("Log Level", level_combo))

        retention = SpinSetting(30, 1, 999, "days")
        bind_spin(retention, mgr, "logging/retention_days", 30)
        save_card.body.addWidget(SettingRow("Log Retention", retention))
        lo.addWidget(save_card)

        tools_card = Card("Developer Tools")
        tools_card.body.setSpacing(8)
        # Arrange developer buttons in a 2-column grid for compactness
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        btn_debug = primary_button("Show Debug Messages")
        btn_debug.clicked.connect(lambda: self._show_toast("Show Debug Messages: Not yet implemented"))
        row1.addWidget(btn_debug)
        
        btn_serial = primary_button("Raw Serial Monitor")
        btn_serial.clicked.connect(lambda: self._show_toast("Raw Serial Monitor: Not yet implemented"))
        row1.addWidget(btn_serial)
        
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        btn_pkt = primary_button("Packet Inspector")
        btn_pkt.clicked.connect(lambda: self._show_toast("Packet Inspector: Not yet implemented"))
        row2.addWidget(btn_pkt)
        
        btn_dump = primary_button("Export Debug Dump")
        btn_dump.clicked.connect(lambda: self._show_toast("Export Debug Dump: Not yet implemented"))
        row2.addWidget(btn_dump)
        
        tools_card.body.addLayout(row1)
        tools_card.body.addLayout(row2)
        lo.addWidget(tools_card)

        note_card = Card("Note")
        note_card.body.addWidget(muted_label(
            "These tools expose raw serial I/O and low-level protocol data. "
            "Intended for development and debugging only."
        ))
        lo.addWidget(note_card)
        lo.addStretch(1)


# ── Assemble ─────────────────────────────────────────────────────────

def build_tx_settings(state: TXAppState | None = None) -> SettingsContainer:
    """Build the full TX settings with 4 sections and persistence."""
    from gui_dev_v3.tx.placeholders import AboutPage
    mgr = SettingsManager("tx")
    sections: list[tuple[str, QWidget]] = [
        ("General & Display", GeneralDisplayPage(mgr)),
        ("Hardware Connection", HardwareConnectionPage(mgr, state=state)),
        ("TX Settings", TXSettingsPage(mgr, state=state)),
        ("Diagnostics & Logs", DiagnosticsLogsPage(mgr)),
        ("About", AboutPage(state=state)),
    ]
    # No developer_index since Developer isn't a standalone tab.
    container = SettingsContainer(sections)
    return container
