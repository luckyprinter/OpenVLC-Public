"""Shared settings UI: multi-tab container with left nav + stacked pages + persistence."""

from __future__ import annotations

import math
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui_dev_v3.widgets import InfoIcon

from gui_dev_v3.theme import COLORS, set_theme, ThemeMode, THEME_PRESETS, apply_theme, build_qss


# ── Persistence ──────────────────────────────────────────────────────


class SettingsManager:
    """Persistent settings via QSettings. Reads/writes to ~/.config/VLC Receiver/.

    Key convention: ``section/key`` (e.g. ``general/theme``).
    """

    APP_NAME = "VLC Receiver"

    def __init__(self, scope: str = "rx") -> None:
        self._settings = QSettings(self.APP_NAME, scope)

    def get(self, key: str, default: object = None) -> object:
        raw = self._settings.value(key, default)
        # QSettings returns 'true'/'false' strings for booleans
        if isinstance(raw, str) and raw.lower() in ("true", "false"):
            return raw.lower() == "true"
        return raw

    def set(self, key: str, value: object) -> None:
        self._settings.setValue(key, value)
        self._settings.sync()

    def value(self, key: str, default: object = None) -> object:
        """Alias for get()."""
        return self.get(key, default)

    def clear(self) -> None:
        """Clear all settings from persistence."""
        self._settings.clear()
        self._settings.sync()


def bind_toggle(toggle: ToggleSetting, mgr: SettingsManager, key: str, default: bool = True) -> None:
    """Load initial value from settings and save on toggle."""
    toggle.setChecked(mgr.get(key, default))  # type: ignore[arg-type]
    toggle.toggled.connect(lambda checked: mgr.set(key, checked))


def bind_radio_node(setting: RadioNodeSetting, mgr: SettingsManager, key: str, default: bool = False) -> None:
    """Bind a RadioNodeSetting to a SettingsManager key."""
    val = mgr.get(key, default)
    setting.setChecked(bool(val))
    setting.toggled.connect(lambda v: mgr.set(key, v))


def bind_spin(setting: SpinSetting | FreeformSpinSetting, mgr: SettingsManager, key: str, default: int = 0) -> None:
    """Load initial value from settings and save on change."""
    try:
        val = int(mgr.get(key, default))
    except (ValueError, TypeError):
        val = default
    setting.setValue(val)
    setting.valueChanged.connect(lambda val: mgr.set(key, val))


def bind_double_spin(spin: DoubleSpinSetting, mgr: SettingsManager, key: str, default: float = 0.0) -> None:
    """Load initial value from settings and save on change."""
    try:
        val = float(mgr.get(key, default))
    except (ValueError, TypeError):
        val = default
    spin.setValue(val)
    spin.valueChanged.connect(lambda val: mgr.set(key, val))


def bind_combo(combo: ComboSetting, mgr: SettingsManager, key: str, default: str = "") -> None:
    """Load initial value from settings and save on selection."""
    default_val = str(mgr.get(key, default) or default)
    idx = combo.findText(default_val)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    combo.currentTextChanged.connect(lambda text: mgr.set(key, text))


def bind_radio_group(group: RadioGroup, mgr: SettingsManager, key: str, default: str = "") -> None:
    """Save which radio is checked on change."""
    # Set initial
    for btn in group._buttons:
        if btn.text() == mgr.get(key, default):
            btn.setChecked(True)
            break
    for btn in group._buttons:
        btn.toggled.connect(lambda checked, b=btn: mgr.set(key, b.text()) if checked else None)


# ── Form controls ────────────────────────────────────────────────────


class SettingRow(QWidget):
    """A labeled row with a control on the right. Matches _detail_row style."""

    def __init__(self, label: str, control: QWidget, tooltip: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 4, 0, 4)
        lo.setSpacing(8)

        lbl = QLabel(label)
        lbl.setObjectName("Muted")
        lbl.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        lo.addWidget(lbl)
        
        if tooltip:
            icon = InfoIcon(tooltip)
            lo.addWidget(icon)
            
        lo.addStretch(1)
        lo.addWidget(control)


class ToggleSetting(QCheckBox):
    """On/off toggle styled as a switch-like checkbox."""

    def __init__(self, checked: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setChecked(checked)
        self.setMinimumWidth(40)


class ComboSetting(QComboBox):
    """Dropdown with consistent styling."""

    def __init__(self, items: list[str], current: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.addItems(items)
        if current and current in items:
            self.setCurrentText(current)


class SpinSetting(QSpinBox):
    """Integer spin box with label-friendly width."""

    def __init__(self, value: int = 0, minimum: int = 0, maximum: int = 9999, suffix: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setValue(value)
        if suffix:
            self.setSuffix(f" {suffix}")
        self.setFixedWidth(100)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)


class FreeformSpinSetting(QSpinBox):
    """A SpinBox that allows freeform input but warns visually if outside recommended bounds."""
    
    def __init__(self, value: int = 0, rec_min: int = 0, rec_max: int = 9999, suffix: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # We allow a much wider absolute range than recommended
        self.setRange(0, 10000000)
        self._rec_min = rec_min
        self._rec_max = rec_max
        if suffix:
            self.setSuffix(f" {suffix}")
        self.setFixedWidth(100)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setValue(value)
        
        self.valueChanged.connect(self._check_bounds)
        self._check_bounds(value)
        
    def _check_bounds(self, val: int) -> None:
        if val < self._rec_min or val > self._rec_max:
            # Highlight orange/red if outside recommended safe limits
            self.setStyleSheet("QSpinBox { border: 1px solid #FF5555; background: #2A1111; }")
            self.setToolTip(f"Warning: ESP32 safe limits are usually {self._rec_min} - {self._rec_max}")
        else:
            self.setStyleSheet("")
            self.setToolTip("")


class FreeformDoubleSpinSetting(QDoubleSpinBox):
    """A DoubleSpinBox that allows freeform input but warns visually if outside recommended bounds."""
    
    def __init__(self, value: float = 0.0, rec_min: float = 0.0, rec_max: float = 9999.0, decimals: int = 1, suffix: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(0.0, 10000000.0)
        self._rec_min = rec_min
        self._rec_max = rec_max
        self.setDecimals(decimals)
        if suffix:
            self.setSuffix(f" {suffix}")
        self.setFixedWidth(100)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setValue(value)
        
        self.valueChanged.connect(self._check_bounds)
        self._check_bounds(value)
        
    def _check_bounds(self, val: float) -> None:
        if val < self._rec_min or val > self._rec_max:
            self.setStyleSheet("QDoubleSpinBox { border: 1px solid #FF5555; background: #2A1111; }")
            self.setToolTip(f"Warning: safe limits are usually {self._rec_min} - {self._rec_max}")
        else:
            self.setStyleSheet("")
            self.setToolTip("")

class RadioNodeSetting(QWidget):
    """A custom toggle mimicking (○) ON  (●) OFF."""
    toggled = Signal(bool)

    def __init__(self, checked: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(12)
        
        self.btn_on = QRadioButton("ON")
        self.btn_off = QRadioButton("OFF")
        
        self.btn_on.setChecked(checked)
        self.btn_off.setChecked(not checked)
        
        # Style them to use circle nodes and bold text
        style = "QRadioButton { font-weight: bold; } QRadioButton::indicator { width: 14px; height: 14px; border-radius: 7px; border: 1px solid #777; } QRadioButton::indicator:checked { background-color: #4CAF50; border: 2px solid #fff; }"
        self.btn_on.setStyleSheet(style)
        self.btn_off.setStyleSheet(style.replace("#4CAF50", "#FF5555"))
        
        lo.addWidget(self.btn_on)
        lo.addWidget(self.btn_off)
        
        self.btn_on.toggled.connect(self._on_toggled)
        
    def _on_toggled(self, checked: bool) -> None:
        self.toggled.emit(checked)
        
    def isChecked(self) -> bool:
        return self.btn_on.isChecked()
        
    def setChecked(self, checked: bool) -> None:
        self.btn_on.setChecked(checked)
        self.btn_off.setChecked(not checked)


class DoubleSpinSetting(QDoubleSpinBox):
    """Float spin box."""

    def __init__(self, value: float = 0.0, minimum: float = 0.0, maximum: float = 9999.0, suffix: str = "", decimals: int = 1, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setValue(value)
        self.setDecimals(decimals)
        if suffix:
            self.setSuffix(f" {suffix}")
        self.setFixedWidth(100)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)


class BrowseButton(QPushButton):
    """Small button for 'Browse' actions."""

    def __init__(self, text: str = "Browse", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFixedWidth(80)


class RadioGroup(QWidget):
    """Vertical/horizontal radio button group."""

    def __init__(self, options: list[str], selected: str | None = None, horizontal: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lo = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(8)
        self._buttons: list[QRadioButton] = []
        for opt in options:
            btn = QRadioButton(opt)
            if opt == selected:
                btn.setChecked(True)
            self._buttons.append(btn)
            lo.addWidget(btn)
        lo.addStretch(1)


class SliderSpinSetting(QWidget):
    """A synchronized slider and double spinbox widget.

    Signals valueChanged(float) on user adjustment.
    """

    valueChanged = Signal(float)

    def __init__(
        self,
        value: float = 0.0,
        minimum: float = 0.0,
        maximum: float = 100.0,
        step: float = 1.0,
        decimals: int = 1,
        suffix: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._decimals = decimals
        self._multiplier = 10 ** decimals

        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(8)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(minimum * self._multiplier), int(maximum * self._multiplier))
        self.slider.setSingleStep(int(step * self._multiplier))
        self.slider.setValue(int(value * self._multiplier))

        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setValue(value)
        if suffix:
            self.spin.setSuffix(f" {suffix}")
        self.spin.setFixedWidth(90)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight)

        lo.addWidget(self.slider, 1)
        lo.addWidget(self.spin)

        # Sync slider -> spin
        self.slider.valueChanged.connect(self._on_slider_changed)
        # Sync spin -> slider
        self.spin.valueChanged.connect(self._on_spin_changed)

    def _on_slider_changed(self, val: int) -> None:
        float_val = val / self._multiplier
        if not math.isclose(self.spin.value(), float_val, abs_tol=1e-5):
            self.spin.blockSignals(True)
            self.spin.setValue(float_val)
            self.spin.blockSignals(False)
            self.valueChanged.emit(float_val)

    def _on_spin_changed(self, val: float) -> None:
        slider_val = int(val * self._multiplier)
        if self.slider.value() != slider_val:
            self.slider.blockSignals(True)
            self.slider.setValue(slider_val)
            self.slider.blockSignals(False)
            self.valueChanged.emit(val)

    def value(self) -> float:
        return self.spin.value()

    def setValue(self, val: float) -> None:
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(val)
        self.slider.setValue(int(val * self._multiplier))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)

def bind_double_spin(setting: FreeformDoubleSpinSetting | DoubleSpinSetting, mgr: SettingsManager, key: str, default: float = 0.0) -> None:
    """Load initial value from settings and save on change."""
    try:
        val = float(mgr.get(key, default))
    except (ValueError, TypeError):
        val = default
    setting.setValue(val)
    setting.valueChanged.connect(lambda v: mgr.set(key, float(v)))


def bind_slider_spin(slider_spin: SliderSpinSetting, mgr: SettingsManager, key: str, default: float = 0.0) -> None:
    """Load initial value from settings and save on change."""
    try:
        val = float(mgr.get(key, default))
    except (ValueError, TypeError):
        val = default
    slider_spin.setValue(val)
    # Persist the possibly clamped value back to SettingsManager
    clamped_val = slider_spin.spin.value()
    mgr.set(key, clamped_val)
    slider_spin.valueChanged.connect(lambda val: mgr.set(key, val))


class DirectorySetting(QWidget):
    """A directory path editor with a browse button."""
    valueChanged = Signal(str)

    def __init__(self, path: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.edit = QLineEdit(path)
        self.edit.setReadOnly(True)
        self.edit.setStyleSheet(
            f"QLineEdit {{ background: {COLORS['panel_alt']}; border: 1px solid {COLORS['border']}; "
            f"border-radius: 6px; padding: 6px 10px; color: {COLORS['text']}; }}"
        )
        layout.addWidget(self.edit, 1)

        self.btn = QPushButton("Browse")
        self.btn.setFixedWidth(80)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(self._on_browse)
        layout.addWidget(self.btn)

    def _on_browse(self) -> None:
        current_dir = self.edit.text()
        path = QFileDialog.getExistingDirectory(self, "Select Directory", current_dir)
        if path:
            self.edit.setText(path)
            self.valueChanged.emit(path)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, text: str) -> None:
        self.edit.setText(text)


def bind_directory_setting(widget: DirectorySetting, mgr: SettingsManager, key: str, default: str = "") -> None:
    """Load initial value and save on change."""
    val = str(mgr.get(key, default) or default)
    widget.setText(val)
    widget.valueChanged.connect(lambda new_val: mgr.set(key, new_val))


# ── Settings Container ───────────────────────────────────────────────


class SettingsContainer(QWidget):
    """Left-nav + stacked-page container for multi-tab settings panels.

    Sections: list of (label, page_widget).
    Developer is hidden behind a toggle at the bottom of the nav.
    """

    def __init__(self, sections: list[tuple[str, QWidget]], developer_index: int | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sections = sections
        self._developer_index = developer_index

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(1)

        # ── Left navigation ──
        nav_panel = QWidget()
        nav_panel.setObjectName("Card")
        nav_panel.setFixedWidth(200)
        nav_lo = QVBoxLayout(nav_panel)
        nav_lo.setContentsMargins(8, 16, 8, 8)
        nav_lo.setSpacing(2)

        nav_header = QLabel("SETTINGS")
        nav_header.setObjectName("SectionTitle")
        nav_lo.addWidget(nav_header)
        nav_lo.addSpacing(8)

        self._nav_list = QListWidget()
        self._nav_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._nav_list.setSpacing(1)
        self._nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_lo.addWidget(self._nav_list, 1)

        # Developer toggle at bottom
        self._dev_toggle = QCheckBox("Show Advanced")
        self._dev_toggle.setObjectName("Muted")
        self._dev_toggle.toggled.connect(self._on_dev_toggle)
        nav_lo.addWidget(self._dev_toggle)
        if self._developer_index is None:
            self._dev_toggle.hide()

        outer.addWidget(nav_panel)

        # ── Right stacked pages ──
        self._stack = QStackedWidget()
        outer.addWidget(self._stack, 1)

        # Build nav items and pages
        for idx, (label, page) in enumerate(sections):
            item = QListWidgetItem(label)
            self._nav_list.addItem(item)
            # Wrap page in a padded container so all sub-pages have consistent
            # breathing room at the top and sides — fixes the "bald top" issue.
            wrapper = QWidget()
            wrapper_lo = QVBoxLayout(wrapper)
            wrapper_lo.setContentsMargins(24, 20, 24, 24)
            wrapper_lo.setSpacing(0)
            wrapper_lo.addWidget(page)
            # Wrap in scroll area
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(wrapper)
            self._stack.addWidget(scroll)

            # Mark developer items
            if developer_index is not None and idx >= developer_index:
                item.setHidden(True)

        self._nav_list.currentRowChanged.connect(self._on_nav_changed)
        if sections:
            self._nav_list.setCurrentRow(0)

    def _on_nav_changed(self, index: int) -> None:
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)

    def _on_dev_toggle(self, checked: bool) -> None:
        if self._developer_index is not None:
            for i in range(self._developer_index, self._nav_list.count()):
                item = self._nav_list.item(i)
                if item:
                    item.setHidden(not checked)
            if not checked and self._nav_list.currentRow() >= self._developer_index:
                self._nav_list.setCurrentRow(0)

    def refresh(self, state) -> None:
        """Call refresh on every sub-page that has it. Compatible with shell refresh()."""
        import logging
        for _label, page in self._sections:
            if hasattr(page, "refresh"):
                try:
                    page.refresh(state)
                except Exception as e:
                    logging.warning(f"Error refreshing settings page {_label}: {e}")

    def refresh_all(self, state) -> None:
        """Alias for refresh()."""
        self.refresh(state)


# ── Theme Picker ─────────────────────────────────────────────────────


class _SwatchCard(QWidget):
    """A compact pill-style theme selector: left accent stripe + theme name.
    
    Replaces the old large swatch card (52px color preview bar + name)
    with a slim clickable chip to reduce vertical space in Settings.
    """

    clicked = Signal(str)  # emits preset key

    def __init__(self, preset: dict, active: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._key = preset["key"]
        self._active = active
        self._preset = preset
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self.setMinimumWidth(120)
        self._build()

    def _build(self) -> None:
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        # Thin left accent stripe (4px wide)
        self._stripe = QLabel()
        self._stripe.setFixedWidth(4)
        self._stripe.setStyleSheet(
            f"background: {self._preset['preview_accent']}; "
            f"border-top-left-radius: 6px; border-bottom-left-radius: 6px;"
        )
        lo.addWidget(self._stripe)

        # Theme name label
        self._name_lbl = QLabel(self._preset["label"])
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._name_lbl.setStyleSheet("font-size: 12px; font-weight: 600; padding: 0 10px;")
        lo.addWidget(self._name_lbl, 1)

        self._update_style()

    def _update_style(self) -> None:
        self.setObjectName("ThemeSwatch")
        if self._active:
            bg = COLORS.get("sidebar_active", "rgba(255,255,255,0.06)")
            border_color = self._preset["preview_accent"]
            border_width = "2px"
        else:
            bg = "transparent"
            border_color = COLORS["border"]
            border_width = "1px"
        self.setStyleSheet(
            f"QWidget#ThemeSwatch {{ border: {border_width} solid {border_color}; "
            f"border-radius: 6px; background: {bg}; }}"
        )

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self._key)
        super().mousePressEvent(event)


class ThemePickerGrid(QWidget):
    """Grid of swatch cards for selecting a named theme preset.

    Clicking a swatch immediately applies the theme to the app
    (requires the parent QApplication to call setStyleSheet again).
    """

    theme_changed = Signal(str)  # emits the selected theme key

    def __init__(self, current: str = "midnight_navy", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current = current
        self._cards: list[_SwatchCard] = []

        from PySide6.QtWidgets import QApplication
        from PySide6.QtWidgets import QGridLayout
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 6, 0, 6)
        grid.setSpacing(6)

        # Only show the 5 primary presets (not the dark/light legacy aliases)
        primary_presets = [p for p in THEME_PRESETS]
        cols = 3
        for i, preset in enumerate(primary_presets):
            card = _SwatchCard(preset, active=(preset["key"] == current))
            card.clicked.connect(self._on_card_clicked)
            self._cards.append(card)
            grid.addWidget(card, i // cols, i % cols)

    def _on_card_clicked(self, key: str) -> None:
        if key == self._current:
            return
        self._current = key
        # Apply theme live FIRST so COLORS is updated
        from PySide6.QtWidgets import QApplication
        from gui_dev_v3.theme import apply_theme, build_qss
        apply_theme(theme=key)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_qss())
        
        # Update active state on ALL cards so they redraw with new COLORS
        for card in self._cards:
            card.set_active(card._key == key)
            
        self.theme_changed.emit(key)

    def set_current(self, key: str) -> None:
        self._current = key
        for card in self._cards:
            card.set_active(card._key == key)


def bind_theme_picker(picker: ThemePickerGrid, mgr: SettingsManager, key: str = "general/theme", default: str = "midnight_navy") -> None:
    """Load initial theme from settings and save on change."""
    from gui_dev_v3.settings_store import load_settings, save_settings
    app_settings = load_settings()
    saved = str(app_settings.theme or default)
    picker.set_current(saved)
    def _on_theme_changed(k: str) -> None:
        mgr.set(key, k)  # Keep QSettings updated just in case
        latest_settings = load_settings()
        latest_settings.theme = k # type: ignore[assignment]
        save_settings(latest_settings)
    picker.theme_changed.connect(_on_theme_changed)
