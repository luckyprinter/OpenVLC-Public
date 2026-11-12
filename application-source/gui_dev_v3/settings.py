"""Shared settings UI: multi-tab container with left nav + stacked pages + persistence."""

from __future__ import annotations

import math
from PySide6.QtCore import Qt, QSettings, Signal, QSize
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
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
        self.scope = scope
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


def reset_all_settings(mgr: SettingsManager, window: QWidget | None = None) -> bool:
    """Reset both console preference scopes and the shared display settings.

    Persist and verify the shared defaults before clearing either QSettings
    scope. If a corrupt settings file cannot be backed up or the new file
    cannot be written, leave the existing console preferences and in-memory
    window settings untouched so the UI can report the failure accurately.
    """
    from gui_dev_v3.settings_store import AppSettings, save_settings

    defaults = AppSettings()
    if not save_settings(defaults, allow_corrupt_recovery=True):
        return False

    # Reuse the current manager and clear the other console's scope too.
    mgr.clear()
    other_scope = "tx" if getattr(mgr, "scope", "rx") == "rx" else "rx"
    SettingsManager(other_scope).clear()

    # closeEvent persists the window's in-memory display values. Replace them
    # too, otherwise closing after reset would silently restore the old values.
    if window is not None and hasattr(window, "settings"):
        window.settings = defaults
    return True


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
        self.setEditable(True)
        self.addItems(items)
        if current:
            self.setCurrentText(current)


class SpinSetting(QSpinBox):
    """Integer spin box with label-friendly width."""

    def __init__(self, value: int = 0, minimum: int = 0, maximum: int = 9999, suffix: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setValue(value)
        if suffix:
            self.setSuffix(f" {suffix}")
        self.setFixedWidth(max(128, self.sizeHint().width()))
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
        self.setFixedWidth(max(128, self.sizeHint().width()))
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
        self.setFixedWidth(max(128, self.sizeHint().width()))
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
        self.setFixedWidth(max(128, self.sizeHint().width()))
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


class SliderSpinSetting(QDoubleSpinBox):
    """A spinbox setting to replace the forbidden QSlider."""

    def __init__(
        self,
        value: float = 0.0,
        minimum: float = 0.0,
        maximum: float = 1.0,
        step: float = 0.1,
        decimals: int = 1,
        suffix: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setSingleStep(step)
        self.setDecimals(decimals)
        self.setValue(value)
        if suffix:
            self.setSuffix(f" {suffix}")
        self.setFixedWidth(max(128, self.sizeHint().width()))
        self.setAlignment(Qt.AlignmentFlag.AlignRight)

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
    clamped_val = slider_spin.value()
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

        self._path = str(path)
        self.edit = QLineEdit(self._path)
        self.edit.setReadOnly(True)
        self.edit.setCursorPosition(0)
        self.edit.setToolTip(self._path)
        self.setToolTip(self._path)
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
        # Keep the real path separate from the visible line-edit viewport.
        # A read-only QLineEdit otherwise opens at the end of a long path,
        # hiding its beginning on compact/high-DPI displays.
        path = QFileDialog.getExistingDirectory(self, "Select Directory", self.text())
        if path:
            self.setText(path)
            self.valueChanged.emit(path)

    def text(self) -> str:
        return self._path

    def setText(self, text: str) -> None:
        self._path = str(text)
        self.edit.setText(self._path)
        self.edit.setCursorPosition(0)
        self.edit.setToolTip(self._path)
        self.setToolTip(self._path)


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
        self._page_wrappers: list[QWidget] = []

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(1)

        # ── Left navigation ──
        nav_panel = QWidget()
        nav_panel.setObjectName("Card")
        nav_panel.setFixedWidth(200)
        self._nav_panel = nav_panel
        nav_lo = QVBoxLayout(nav_panel)
        nav_lo.setContentsMargins(8, 16, 8, 8)
        nav_lo.setSpacing(2)

        nav_header = QLabel("SETTINGS")
        nav_header.setObjectName("SectionTitle")
        nav_lo.addWidget(nav_header)
        nav_lo.addSpacing(8)

        self._nav_list = QListWidget()
        self._nav_list.setObjectName("SettingsNavigation")
        self._nav_list.setAccessibleName("Settings sections")
        self._nav_list.setAccessibleDescription("Choose a settings category.")
        self._nav_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._nav_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._nav_list.setWordWrap(True)
        self._nav_list.setTextElideMode(Qt.TextElideMode.ElideNone)
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
            item.setToolTip(label)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, label)
            item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, f"Open {label} settings.")
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item.setSizeHint(QSize(0, 42))
            self._nav_list.addItem(item)
            # Wrap page in a padded container so all sub-pages have consistent
            # breathing room at the top and sides — fixes the "bald top" issue.
            wrapper = QWidget()
            wrapper_lo = QVBoxLayout(wrapper)
            wrapper_lo.setContentsMargins(24, 20, 24, 24)
            wrapper_lo.setSpacing(0)
            wrapper_lo.addWidget(page)
            self._page_wrappers.append(wrapper)
            wrapper_lo.addStretch(1)
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

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        """Reduce settings-page gutters on compact laptop work areas."""
        super().resizeEvent(event)
        compact = self.width() < 900
        # On compact work areas the settings navigation must not consume the
        # width needed by the active form. Keep category labels readable while
        # giving the stacked page enough room for controls such as directory
        # pickers and theme choices.
        self._nav_panel.setFixedWidth(180 if compact else 200)
        # Long category labels need a second line at high scaling; a fixed
        # 42px row clips them even though word wrapping is enabled.
        for index in range(self._nav_list.count()):
            item = self._nav_list.item(index)
            if item is not None:
                item.setSizeHint(QSize(0, 56 if compact else 42))
        margins = (10, 12, 10, 12) if compact else (24, 20, 24, 24)
        for wrapper in self._page_wrappers:
            layout = wrapper.layout()
            if layout is not None:
                layout.setContentsMargins(*margins)

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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(preset["label"])
        self.setAccessibleDescription(f"Select the {preset['label']} theme.")
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
            f"QWidget#ThemeSwatch:focus {{ border: 2px solid {self._preset['preview_accent']}; }}"
        )

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self._key)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit(self._key)
            event.accept()
            return
        super().keyPressEvent(event)


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

        from PySide6.QtWidgets import QGridLayout
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 6, 0, 6)
        self._grid.setSpacing(6)
        self._column_count = 3

        # Keep the default picker focused on five curated presets. Older
        # presets remain supported in theme.py so existing saved preferences
        # continue to load; if one is currently selected, keep it visible so
        # the user can see the active choice and switch away from it.
        curated_keys = {
            "graphite_lab",
            "midnight_navy",
            "arctic_light",
            "dark_lab",
            "clean_data",
        }
        primary_presets = [
            preset for preset in THEME_PRESETS
            if preset["key"] in curated_keys or preset["key"] == current
        ]
        for i, preset in enumerate(primary_presets):
            card = _SwatchCard(preset, active=(preset["key"] == current))
            card.clicked.connect(self._on_card_clicked)
            self._cards.append(card)
            self._grid.addWidget(card, i // self._column_count, i % self._column_count)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        """Reflow theme choices instead of clipping them on narrow windows."""
        super().resizeEvent(event)
        columns = 1 if self.width() < 320 else 2 if self.width() < 560 else 3
        if columns == self._column_count:
            return
        self._column_count = columns
        for index, card in enumerate(self._cards):
            self._grid.removeWidget(card)
            self._grid.addWidget(card, index // columns, index % columns)

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
