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

        mode_card = Card("Operating Mode")
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(12)
        
        current_mode = state.mode if state else str(mgr.get("general/mode", "physical"))
        
        self.physical_card = ModeSelectCard(
            title="Physical Mode",
            description="Connect to a physical VLC transmitter device via USB Serial port.",
            icon_name="fa5s.microchip",
            active=(current_mode == "physical")
        )
        self.simulated_card = ModeSelectCard(
            title="Simulation Mode",
            description="Simulate VLC transmission using localhost UDP socket.",
            icon_name="fa5s.wave-square",
            active=(current_mode == "simulated")
        )
        
        self.physical_card.clicked.connect(lambda: self._select_mode("physical"))
        self.simulated_card.clicked.connect(lambda: self._select_mode("simulated"))
        
        mode_layout.addWidget(self.physical_card)
        mode_layout.addWidget(self.simulated_card)
        mode_card.body.addLayout(mode_layout)
        lo.addWidget(mode_card)

        self.opts_card = Card("Connection Options")
        mode_group = RadioGroup(["Auto Detect (Recommended)", "Manual"], selected="Auto Detect (Recommended)")
        bind_radio_group(mode_group, mgr, "connection/mode", "Auto Detect (Recommended)")
        self.opts_card.body.addWidget(mode_group)

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

        self.fw_card = Card("Expected Device")
        dev_combo = ComboSetting(["VLC_TX", "VLC_RX", "VLC_DEBUG"], "VLC_TX")
        bind_combo(dev_combo, mgr, "firmware/device_type", "VLC_TX")
        self.fw_card.body.addWidget(SettingRow("Device Type", dev_combo))

        proto_combo = ComboSetting(["VLC_PROTO_V1", "VLC_PROTO_V0"], "VLC_PROTO_V1")
        bind_combo(proto_combo, mgr, "firmware/protocol_version", "VLC_PROTO_V1")
        self.fw_card.body.addWidget(SettingRow("Protocol Version", proto_combo))

        mismatch = RadioNodeSetting(False)
        bind_radio_node(mismatch, mgr, "firmware/allow_mismatch", False)
        self.fw_card.body.addWidget(SettingRow("Allow Version Mismatch", mismatch))
        lo.addWidget(self.fw_card)

        self.status_card = Card("Live Status")
        self._port_label = muted_label("Port: —")
        self._conn_label = muted_label("Status: —")
        self.status_card.body.addWidget(self._port_label)
        self.status_card.body.addWidget(self._conn_label)
        lo.addWidget(self.status_card)
        lo.addStretch(1)

        self._update_visibility(current_mode)

    def _select_mode(self, mode: str) -> None:
        if self._state:
            self._state.set_mode(mode)
            self._mgr.set("general/mode", mode)
            w = self.parentWidget()
            depth = 0
            while w is not None and depth < 20:
                if hasattr(w, "_update_status_indicators") and hasattr(w, "_refresh_current_page"):
                    w._update_status_indicators()
                    w._refresh_current_page()
                    break
                w = w.parentWidget()
                depth += 1
        
        self.physical_card.set_active(mode == "physical")
        self.simulated_card.set_active(mode == "simulated")
        self._update_visibility(mode)

    def _update_visibility(self, mode: str) -> None:
        is_sim = mode == "simulated"
        self.opts_card.setVisible(not is_sim)
        self.fw_card.setVisible(not is_sim)
        self.status_card.setVisible(not is_sim)

    def refresh(self, state: TXAppState) -> None:
        if state is None:
            return
        mode = state.mode
        self._update_visibility(mode)
        self.physical_card.set_active(mode == "physical")
        self.simulated_card.set_active(mode == "simulated")

        if mode == "physical":
            phy = getattr(state, "_physical", None)
            if phy and phy.is_connected:
                self._port_label.setText(f"Port: {phy.port or '—'}")
                self._conn_label.setText("Status: Connected")
                return
            self._port_label.setText(f"Port: {state.port or '—'}")
            self._conn_label.setText("Status: Disconnected")
        else:
            self._port_label.setText("Port: —")
            self._conn_label.setText("Status: Simulated (no hardware)")


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
        
        self.active_low_set = RadioNodeSetting(False)
        bind_radio_node(self.active_low_set, mgr, "link/active_low", False)
        self.link_card.body.addWidget(SettingRow("Active Low Driver", self.active_low_set, "Inverts the GPIO logic. Use ON if the LED turns on when GPIO is LOW."))
        
        self.idle_on_set = RadioNodeSetting(True)
        bind_radio_node(self.idle_on_set, mgr, "link/idle_on", True)
        self.link_card.body.addWidget(SettingRow("Keep LED On at Idle", self.idle_on_set, "Keeps the transmitter LED illuminated when not sending data, providing continuous ambient light."))
        
        self.intensity_set = FreeformSpinSetting(35, rec_min=0, rec_max=100, suffix="%")
        bind_spin(self.intensity_set, mgr, "link/cal_intensity_pct", 35)
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
            self._state.send_firmware_command(f"FREQ={freq}\n")
            self._state.send_firmware_command(f"PREAMBLE={preamble}\n")
            self._state.send_firmware_command(f"GAP={gap}\n")
            self._state.send_firmware_command(f"FGAP={fgap}\n")
            self._state.send_firmware_command(f"ACTIVE_LOW={1 if active_low else 0}\n")
            self._state.send_firmware_command(f"IDLE_ON={1 if idle_on else 0}\n")
            self._state.send_firmware_command(f"INTENSITY={intensity}\n")
            self._state.send_firmware_command(f"QUIET={1 if quiet else 0}\n")
            self._state.send_firmware_command(f"DMA_MODE={1 if dma_mode else 0}\n")
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
        row1.addWidget(primary_button("Show Debug Messages"))
        row1.addWidget(primary_button("Raw Serial Monitor"))
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(primary_button("Packet Inspector"))
        row2.addWidget(primary_button("Export Debug Dump"))
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
