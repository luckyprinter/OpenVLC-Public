"""RX Settings — 3-section multi-tab settings page with persistence."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton

from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.settings import (
    BrowseButton,
    ComboSetting,
    DirectorySetting,
    SettingsManager,
    SettingRow,
    SettingsContainer,
    SpinSetting,
    ToggleSetting,
    bind_combo,
    bind_directory_setting,
    bind_spin,
    bind_toggle,
    bind_radio_group,
    bind_slider_spin,
    bind_theme_picker,
    RadioGroup,
    SliderSpinSetting,
    FreeformSpinSetting,
    FreeformDoubleSpinSetting,
    RadioNodeSetting,
    bind_radio_node,
    bind_double_spin,
    ThemePickerGrid,
)
from gui_dev_v3.settings_store import RESOLUTION_PRESETS
from gui_dev_v3.theme import COLORS
from gui_dev_v3.widgets import Card, muted_label, ModeSelectCard, primary_button


# ── General & Display ──────────────────────────────────────────────────


class GeneralDisplayPage(QWidget):
    def __init__(self, mgr: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mgr = mgr
        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(12)

        # 1. Theme Card
        theme_card = Card("Theme")
        from gui_dev_v3.settings_store import load_settings
        current_preset = str(mgr.get("general/theme", load_settings().theme) or "midnight_navy")
        self._theme_picker = ThemePickerGrid(current=current_preset)
        bind_theme_picker(self._theme_picker, mgr, "general/theme", current_preset)
        theme_card.body.addWidget(self._theme_picker)
        lo.addWidget(theme_card)

        # 2. Workspace & Data Card
        workspace_card = Card("Workspace & Data")
        ws_toggle = RadioNodeSetting(True)
        bind_radio_node(ws_toggle, mgr, "general/remember_workspace", True)
        workspace_card.body.addWidget(SettingRow("Remember Last Workspace", ws_toggle))

        auto_save = RadioNodeSetting(True)
        bind_radio_node(auto_save, mgr, "general/auto_save_experiment", True)
        workspace_card.body.addWidget(SettingRow("Auto Save Experiment Data", auto_save))

        from pathlib import Path
        default_dir = str(Path.home() / "vlc_rx_captures")
        self.export_dir_setting = DirectorySetting()
        bind_directory_setting(self.export_dir_setting, mgr, "general/default_export_folder", default_dir)
        workspace_card.body.addWidget(SettingRow("Default Export Folder", self.export_dir_setting))
        lo.addWidget(workspace_card)

        # 3. Window & Display Card
        display_card = Card("Display Options")
        self._res_combo = ComboSetting([key for key, _, _ in RESOLUTION_PRESETS], "1280x800")
        display_card.body.addWidget(SettingRow("Resolution", self._res_combo))

        self._fullscreen_toggle = RadioNodeSetting(False)
        display_card.body.addWidget(SettingRow("Fullscreen (F11)", self._fullscreen_toggle))

        self._borderless_toggle = RadioNodeSetting(False)
        display_card.body.addWidget(SettingRow("Borderless Window", self._borderless_toggle))
        lo.addWidget(display_card)

        # 4. Transfer Stats Preview Card
        stats_config_card = Card("Transfer Stats Preview Configuration")
        STAT_FIELDS = [
            ("File Name", "filename", True),
            ("Chunks Received", "chunks", True),
            ("Packets", "packets", True),
            ("CRC Status", "crc", True),
            ("BER (Live)", "ber", True),
            ("Bit Errors", "bit_errors", False),
            ("Retry Count", "retry_count", False),
            ("Packet Loss", "packet_loss", False),
            ("Elapsed Time", "elapsed", True),
            ("Data Rate", "data_rate", False),
        ]
        for label, key, default in STAT_FIELDS:
            toggle = RadioNodeSetting(default)
            bind_radio_node(toggle, mgr, f"stats_display/{key}", default)
            stats_config_card.body.addWidget(SettingRow(label, toggle))
        lo.addWidget(stats_config_card)

        # 5. Launcher Settings Card
        launcher_card = Card("System Actions")
        self.switch_btn = primary_button("  \u2190  Return to Mode Selection Launcher")
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
        """Lazy lookup of the _BaseWindow (may not be in widget tree at init time)."""
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

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._connected:
            return
        window = self._get_window()
        if window is None:
            return
        self._connected = True

        # Set initial values from window settings
        self._res_combo.setCurrentText(window.settings.resolution)
        self._fullscreen_toggle.setChecked(window.settings.fullscreen)
        self._borderless_toggle.setChecked(window.settings.borderless)

        # Connect resolution
        self._res_combo.currentTextChanged.connect(lambda key: window.set_resolution(key))

        # Connect fullscreen with signal blocking to prevent loops
        def _on_fullscreen_toggled(checked: bool) -> None:
            window.toggle_fullscreen()
        self._fullscreen_toggle.toggled.connect(_on_fullscreen_toggled)

        def _on_fullscreen_changed(is_fs: bool) -> None:
            self._fullscreen_toggle.blockSignals(True)
            self._fullscreen_toggle.setChecked(is_fs)
            self._fullscreen_toggle.blockSignals(False)
        window.fullscreen_changed.connect(_on_fullscreen_changed)

        # Connect borderless
        def _on_borderless_toggled(checked: bool) -> None:
            window.settings.borderless = checked
            if not window.isFullScreen():
                window.setWindowFlag(Qt.FramelessWindowHint, checked)
                window.show()
        self._borderless_toggle.toggled.connect(_on_borderless_toggled)


# ── Connection & Channel ────────────────────────────────────────────────


class ConnectionChannelPage(QWidget):
    def __init__(self, mgr: SettingsManager, state: RXAppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mgr = mgr
        self._state = state

        lo = QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(12)


        # 2. Connection Settings card (only for physical)
        self.conn_card = Card("Connection Settings")
        mode_select = RadioGroup(["Auto Detect (Recommended)", "Manual"], selected="Auto Detect (Recommended)")
        bind_radio_group(mode_select, mgr, "connection/mode", "Auto Detect (Recommended)")
        self.conn_card.body.addWidget(mode_select)

        port_layout = QHBoxLayout()
        self.port_combo = ComboSetting([], "")
        from gui_dev_v3.rx.backends.physical import _list_usb_serial_ports
        
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
                for btn in mode_select._buttons:
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
        self.conn_card.body.addLayout(port_layout)

        auto_conn = RadioNodeSetting(True)
        bind_radio_node(auto_conn, mgr, "connection/auto_connect", True)
        self.conn_card.body.addWidget(SettingRow("Auto Connect On Startup", auto_conn))

        scan_spin = SpinSetting(3, 1, 60, "seconds")
        bind_spin(scan_spin, mgr, "connection/scan_interval", 3)
        self.conn_card.body.addWidget(SettingRow("Scan Interval", scan_spin))

        timeout_spin = SpinSetting(5, 1, 120, "seconds")
        bind_spin(timeout_spin, mgr, "connection/timeout", 5)
        self.conn_card.body.addWidget(SettingRow("Connection Timeout", timeout_spin))
        
        # Live status inside Connection Settings
        self._port_label = muted_label("Port: —")
        self._baud_label = muted_label("Baud: —")
        self._fw_label = muted_label("Firmware: —")
        self.conn_card.body.addWidget(self._port_label)
        self.conn_card.body.addWidget(self._baud_label)
        self.conn_card.body.addWidget(self._fw_label)
        
        lo.addWidget(self.conn_card)


        # 4. Link Parameters card (only for physical)
        self.link_card = Card("Link Parameters (Firmware)")
        self.link_card.body.setSpacing(8)

        # Frequency
        self.freq_set = FreeformDoubleSpinSetting(value=15000.0, rec_min=1000.0, rec_max=50000.0, decimals=0, suffix="Hz")
        bind_double_spin(self.freq_set, mgr, "link/symbol_hz", 15000.0)
        self.link_card.body.addWidget(SettingRow("Symbol Frequency", self.freq_set, "Symbol clock speed. Must match TX exactly."))

        # Preamble Bits
        self.preamble_set = FreeformSpinSetting(64, rec_min=16, rec_max=512, suffix="bits")
        bind_spin(self.preamble_set, mgr, "link/preamble_bits", 64)
        self.link_card.body.addWidget(SettingRow("Preamble Bits", self.preamble_set, "Must match TX Preamble Bits for proper synchronization."))

        # Sample Phase
        self.phase_set = FreeformDoubleSpinSetting(value=50.0, rec_min=0.0, rec_max=100.0, decimals=0, suffix="%")
        bind_double_spin(self.phase_set, mgr, "link/sample_phase_pct", 50.0)
        self.link_card.body.addWidget(SettingRow("Sample Phase", self.phase_set, "Percentage into the symbol window to sample the analog value."))

        # Vref Target
        self.vref_set = FreeformSpinSetting(1700, rec_min=0, rec_max=3300, suffix="mV")
        bind_spin(self.vref_set, mgr, "link/vref_target_mv", 1700)
        self.link_card.body.addWidget(SettingRow("Vref Target", self.vref_set, "Fixed reference voltage target (when auto-calibrate is off)."))

        # Vref Margin Target
        self.vref_margin_set = FreeformSpinSetting(365, rec_min=280, rec_max=450, suffix="mV")
        bind_spin(self.vref_margin_set, mgr, "link/vref_margin_mv", 365)
        self.link_card.body.addWidget(SettingRow("Vref Margin Target", self.vref_margin_set, "Target voltage swing for High/Low discrimination."))

        # Vref PWM Full Scale
        self.vref_pwm_set = FreeformSpinSetting(2625, rec_min=500, rec_max=3300, suffix="mV")
        bind_spin(self.vref_pwm_set, mgr, "link/vref_pwm_full_scale_mv", 2625)
        self.link_card.body.addWidget(SettingRow("Vref PWM Full Scale", self.vref_pwm_set, "Calibration constant mapping PWM duty to mV."))

        # Vref Settle
        self.vref_settle_set = FreeformSpinSetting(120, rec_min=1, rec_max=5000, suffix="ms")
        bind_spin(self.vref_settle_set, mgr, "link/vref_settle_ms", 120)
        self.link_card.body.addWidget(SettingRow("Vref Settle", self.vref_settle_set, "Wait time after adjusting Vref before continuing."))

        # Vref Auto-Calibrate (firmware mode)
        self.vref_auto_set = RadioNodeSetting(False)
        bind_radio_node(self.vref_auto_set, mgr, "link/vref_auto", False)
        self.link_card.body.addWidget(SettingRow("Vref Auto-Calibrate", self.vref_auto_set, "Let firmware automatically track and update reference voltage."))

        # Vref PWM Auto-Cal (app-side PWM stepper)
        self.vref_pwm_autocal_set = RadioNodeSetting(True)
        bind_radio_node(self.vref_pwm_autocal_set, mgr, "link/vref_pwm_autocal", True)
        self.link_card.body.addWidget(SettingRow(
            "Vref PWM Auto-Cal",
            self.vref_pwm_autocal_set,
            "App steps PWM ±1 duty count until measured Vref ≈ Target Vref (±50mV), then locks. "
            "Pauses during file transfer. Re-runs when you change Target Vref and apply settings."
        ))

        # Majority Sampling
        self.maj_set = RadioNodeSetting(True)
        bind_radio_node(self.maj_set, mgr, "link/majority_sampling", True)
        self.link_card.body.addWidget(SettingRow("Majority Sampling", self.maj_set, "Take multiple samples and vote to determine High/Low. Improves noise immunity."))

        # Report Chunks
        self.rep_set = RadioNodeSetting(False)
        bind_radio_node(self.rep_set, mgr, "link/report_chunks", False)
        self.link_card.body.addWidget(SettingRow("Report Chunks", self.rep_set, "Enable detailed chunk decoding reports over serial."))

        # Invert Symbols
        self.inv_set = RadioNodeSetting(False)
        bind_radio_node(self.inv_set, mgr, "link/invert_symbols", False)
        self.link_card.body.addWidget(SettingRow("Invert Symbols", self.inv_set, "Invert logical 1s and 0s. Use if the photodiode circuit is active-low."))

        self.apply_btn = primary_button("Apply Hardware Settings")
        self.apply_btn.clicked.connect(self._on_apply_settings)
        self.link_card.body.addWidget(self.apply_btn)

        lo.addWidget(self.link_card)

        lo.addStretch(1)


    def _on_apply_settings(self) -> None:
        if not self._state:
            return

        freq = int(self.freq_set.value())
        preamble = int(self.preamble_set.value())
        phase = int(self.phase_set.value())
        vref_set = int(self.vref_set.value())
        vref_margin = int(self.vref_margin_set.value())
        vref_pwm = int(self.vref_pwm_set.value())
        vref_settle = int(self.vref_settle_set.value())
        vref_auto = self.vref_auto_set.isChecked()
        maj = self.maj_set.isChecked()
        rep = self.rep_set.isChecked()
        inv = self.inv_set.isChecked()

        self._state.send_firmware_command(f"FREQ={freq}\n")
        self._state.send_firmware_command(f"PREAMBLE={preamble}\n")
        self._state.send_firmware_command(f"PHASE={phase}\n")
        self._state.send_firmware_command(f"MAJ={1 if maj else 0}\n")
        self._state.send_firmware_command(f"REPORT={1 if rep else 0}\n")
        self._state.send_firmware_command(f"INVERT={1 if inv else 0}\n")
        self._state.send_firmware_command(f"VREF_MARGIN={vref_margin}\n")
        self._state.send_firmware_command(f"VREF_PWM_FS={vref_pwm}\n")
        self._state.send_firmware_command(f"VREF_SETTLE_MS={vref_settle}\n")
        self._state.send_firmware_command("VREF_MODE=AUTO\n" if vref_auto else "VREF_MODE=MANUAL\n")
        # VREF_SET must be sent LAST because the firmware blocks/delays to let the RC filter settle.
        # Sending it earlier causes the ESP32's 64-byte UART buffer to overflow with the remaining commands.
        self._state.send_firmware_command(f"VREF_SET={vref_set}\n")
        
        if vref_auto:
            self._state.send_firmware_command("VREF_CAL\n")
            
        self._show_toast("Hardware settings applied to receiver")

    def refresh(self, state: RXAppState) -> None:
        if state is None:
            return
        if state.serial_connected:
            phy = getattr(state, "_physical", None)
            if phy:
                self._port_label.setText(f"Port: {phy.port or '—'}")
                self._baud_label.setText(f"Baud: {getattr(phy, '_baud_rate', 460800)}")
                self._fw_label.setText(f"Firmware: {phy.firmware_version or '—'}")
                return
        self._port_label.setText("Port: —")
        self._baud_label.setText("Baud: —")
        self._fw_label.setText("Firmware: —")

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


# ── Diagnostics & Logs ──────────────────────────────────────────────────


class DiagnosticsLogsPage(QWidget):
    def __init__(self, mgr: SettingsManager, state: RXAppState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mgr = mgr
        self._state = state
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

        # 1. Firmware Card (Removed)

        # 2. Signal Monitoring Card
        refresh_card = Card("Signal Monitoring")
        rate_spin = SpinSetting(100, 10, 9999, "ms")
        bind_spin(rate_spin, mgr, "signal/refresh_rate", 100)
        refresh_card.body.addWidget(SettingRow("Signal Refresh Rate", rate_spin))

        buffer_spin = SpinSetting(1000, 100, 99999, "samples")
        bind_spin(buffer_spin, mgr, "signal/history_buffer", 1000)
        refresh_card.body.addWidget(SettingRow("History Buffer", buffer_spin))

        rt_graph = RadioNodeSetting(True)
        bind_radio_node(rt_graph, mgr, "signal/enable_graphs", True)
        refresh_card.body.addWidget(SettingRow("Enable Real-Time Graphs", rt_graph))

        margin_track = RadioNodeSetting(True)
        bind_radio_node(margin_track, mgr, "signal/enable_margin", True)
        refresh_card.body.addWidget(SettingRow("Enable Margin Tracking", margin_track))

        pvo_track = RadioNodeSetting(True)
        bind_radio_node(pvo_track, mgr, "signal/enable_pvo", True)
        refresh_card.body.addWidget(SettingRow("Enable PVo Tracking", pvo_track))

        vref_track = RadioNodeSetting(True)
        bind_radio_node(vref_track, mgr, "signal/enable_vref", True)
        refresh_card.body.addWidget(SettingRow("Enable Vref Tracking", vref_track))
        lo.addWidget(refresh_card)

        # 3. Logging Card
        save_card = Card("Logging Settings")
        save_rx = RadioNodeSetting(True)
        bind_radio_node(save_rx, mgr, "logging/save_receive", True)
        save_card.body.addWidget(SettingRow("Save Receive Logs", save_rx))

        save_err = RadioNodeSetting(True)
        bind_radio_node(save_err, mgr, "logging/save_errors", True)
        save_card.body.addWidget(SettingRow("Save Error Logs", save_err))

        max_size = SpinSetting(10, 1, 999, "MB")
        bind_spin(max_size, mgr, "logging/max_size_mb", 10)
        save_card.body.addWidget(SettingRow("Maximum Log Size", max_size))

        retention = SpinSetting(30, 1, 999, "days")
        bind_spin(retention, mgr, "logging/retention_days", 30)
        save_card.body.addWidget(SettingRow("Log Retention", retention))
        lo.addWidget(save_card)

        # 4. Developer Card
        tools_card = Card("Developer Tools")
        tools_card.body.setSpacing(8)
        # Arrange developer buttons in a 2-column grid for compactness
        dev_row1 = QHBoxLayout()
        dev_row1.setSpacing(8)
        btn_raw = primary_button("Raw Packet Viewer")
        btn_raw.clicked.connect(lambda: self._show_toast("Raw Packet Viewer: Not yet implemented"))
        dev_row1.addWidget(btn_raw)
        
        btn_ber = primary_button("BER Debugger")
        btn_ber.clicked.connect(lambda: self._show_toast("BER Debugger: Not yet implemented"))
        dev_row1.addWidget(btn_ber)
        
        dev_row2 = QHBoxLayout()
        dev_row2.setSpacing(8)
        
        btn_crc = primary_button("CRC Debugger")
        btn_crc.clicked.connect(lambda: self._show_toast("CRC Debugger: Not yet implemented"))
        dev_row2.addWidget(btn_crc)
        
        btn_ser = primary_button("Serial Console")
        btn_ser.clicked.connect(lambda: self._show_toast("Serial Console: Not yet implemented"))
        dev_row2.addWidget(btn_ser)
        
        dev_row3 = QHBoxLayout()
        dev_row3.setSpacing(8)
        
        btn_perf = primary_button("Performance Metrics")
        btn_perf.clicked.connect(lambda: self._show_toast("Performance Metrics: Not yet implemented"))
        dev_row3.addWidget(btn_perf)
        
        dev_row3.addStretch(1)
        tools_card.body.addLayout(dev_row1)
        tools_card.body.addLayout(dev_row2)
        tools_card.body.addLayout(dev_row3)
        lo.addWidget(tools_card)

        lo.addStretch(1)


# ── Assemble ─────────────────────────────────────────────────────────


def build_rx_settings(state: RXAppState | None = None) -> SettingsContainer:
    """Build the full RX settings with 4 sections and persistence."""
    from gui_dev_v3.rx.placeholders import AboutPage
    mgr = SettingsManager("rx")
    sections: list[tuple[str, QWidget]] = [
        ("General & Display", GeneralDisplayPage(mgr)),
        ("Connection & Channel", ConnectionChannelPage(mgr, state)),
        ("Diagnostics & Logs", DiagnosticsLogsPage(mgr, state)),
        ("About", AboutPage()),
    ]
    container = SettingsContainer(sections)
    return container
