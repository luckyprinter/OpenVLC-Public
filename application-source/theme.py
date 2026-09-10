"""Theme system for the VLC App — 5 named presets with full color palettes.

Presets
-------
midnight_navy  Deep navy dark (default) — refined with glow accents
charcoal       Charcoal gray dark (VS Code / Linear style)
espresso       Warm coffee/mocha dark
synthwave      Neon retro dark
arctic_light   Clean airy light (Notion/Linear style)

Legacy aliases: "dark" → midnight_navy, "light" → arctic_light
"""

from __future__ import annotations

from typing import Literal

ThemeMode = Literal[
    "midnight_navy", "charcoal", "espresso", "synthwave", "arctic_light",
    "dark", "light",  # legacy aliases kept for compatibility
]
AccentName = Literal["blue", "cyan", "green", "violet", "amber", "rose"]
DensityMode = Literal["comfortable", "compact"]

# ── Accent overrides (per-preset defaults are in the palette itself) ────────
ACCENTS: dict[str, str] = {
    "blue":   "#3b82f6",
    "cyan":   "#06b6d4",
    "green":  "#22c55e",
    "violet": "#8b5cf6",
    "amber":  "#f59e0b",
    "rose":   "#f43f5e",
}

# ── Named preset palettes ───────────────────────────────────────────────────
THEMES: dict[str, dict[str, str]] = {
    # ── Midnight Navy — default premium dark ─────────────────────────────
    "midnight_navy": {
        "bg":             "#070E1A",
        "panel":          "#0D1828",
        "panel_alt":      "#111F33",
        "border":         "#1C3354",
        "border_glow":    "#2563eb44",  # accent glow tint for cards
        "text":           "#E8EDF5",
        "muted":          "#5E7A94",
        "secondary":      "#94AAC0",
        "accent":         "#3b82f6",
        "accent_glow":    "#3b82f640",
        "green":          "#22c55e",
        "amber":          "#f59e0b",
        "yellow":         "#eab308",
        "red":            "#ef4444",
        "purple":         "#8b5cf6",
        "pvo":            "#5CE65C",
        "vref":           "#4EA1FF",
        "margin":         "#FFC247",
        "fail":           "#FF5C5C",
        "ook":            "#00E5FF",
        "chart_line":     "#5CE65C",
        "chart_grid":     "#1C3354",
        "sidebar_active": "#162849",
        "header":         "#60a5fa",
        "value":          "#E8EDF5",
        "footer_bg":      "#0A1322",
        "status_dot_on":  "#22c55e",
        "status_dot_off": "#ef4444",
        "status_dot_sim": "#f59e0b",
    },
    # ── Arctic Light — clean airy light ─────────────────────────────────
    "arctic_light": {
        "bg":             "#F0F4FA",
        "panel":          "#FFFFFF",
        "panel_alt":      "#E8EEF6",
        "border":         "#C5D2E5",
        "border_glow":    "#2563eb20",
        "text":           "#141C28",
        "muted":          "#607590",
        "secondary":      "#8094AD",
        "accent":         "#2563eb",
        "accent_glow":    "#2563eb25",
        "green":          "#16a34a",
        "amber":          "#d97706",
        "yellow":         "#ca8a04",
        "red":            "#dc2626",
        "purple":         "#7c3aed",
        "pvo":            "#16a34a",
        "vref":           "#2563eb",
        "margin":         "#d97706",
        "fail":           "#dc2626",
        "ook":            "#0891b2",
        "chart_line":     "#16a34a",
        "chart_grid":     "#C5D2E5",
        "sidebar_active": "#DDE5F5",
        "header":         "#1d4ed8",
        "value":          "#141C28",
        "footer_bg":      "#E4ECF7",
        "status_dot_on":  "#16a34a",
        "status_dot_off": "#dc2626",
        "status_dot_sim": "#d97706",
    },
    # ── 1. Optical Dark Lab ───────────────────────────────────
    "dark_lab": {
        "bg":             "#1E1E24",
        "panel":          "#2B2B36",
        "panel_alt":      "#2B2B36",
        "border":         "#4A4E69",
        "border_glow":    "#FCA31140",
        "text":           "#FFFFFF",
        "muted":          "#A0A0B0",
        "secondary":      "#A0A0B0",
        "accent":         "#FCA311",
        "accent_glow":    "#FCA31140",
        "green":          "#00F5D4",
        "amber":          "#FCA311",
        "yellow":         "#FCA311",
        "red":            "#EF233C",
        "purple":         "#FCA311",
        "pvo":            "#00F5D4",
        "vref":           "#FCA311",
        "margin":         "#FCA311",
        "fail":           "#EF233C",
        "ook":            "#FCA311",
        "chart_line":     "#00F5D4",
        "chart_grid":     "#4A4E69",
        "sidebar_active": "#4A4E69",
        "header":         "#FCA311",
        "value":          "#FFFFFF",
        "footer_bg":      "#1E1E24",
        "status_dot_on":  "#00F5D4",
        "status_dot_off": "#EF233C",
        "status_dot_sim": "#FCA311",
        "fontUi":         '"Inter", sans-serif',
        "fontMono":       '"JetBrains Mono", monospace',
    },

    # ── 2. Clean Data Stream ───────────────────────────────────
    "clean_data": {
        "bg":             "#F8F9FA",
        "panel":          "#FFFFFF",
        "panel_alt":      "#FFFFFF",
        "border":         "#DEE2E6",
        "border_glow":    "#4361EE40",
        "text":           "#212529",
        "muted":          "#6C757D",
        "secondary":      "#6C757D",
        "accent":         "#4361EE",
        "accent_glow":    "#4361EE40",
        "green":          "#2A9D8F",
        "amber":          "#4361EE",
        "yellow":         "#4361EE",
        "red":            "#E63946",
        "purple":         "#4361EE",
        "pvo":            "#2A9D8F",
        "vref":           "#4361EE",
        "margin":         "#4361EE",
        "fail":           "#E63946",
        "ook":            "#4361EE",
        "chart_line":     "#2A9D8F",
        "chart_grid":     "#DEE2E6",
        "sidebar_active": "#DEE2E6",
        "header":         "#4361EE",
        "value":          "#212529",
        "footer_bg":      "#F8F9FA",
        "status_dot_on":  "#2A9D8F",
        "status_dot_off": "#E63946",
        "status_dot_sim": "#4361EE",
        "fontUi":         '"Inter", sans-serif',
        "fontMono":       '"Fira Code", monospace',
    },

    # ── 3. Catppuccin Pastel ───────────────────────────────────
    "catppuccin": {
        "bg":             "#1E1E2E",
        "panel":          "#313244",
        "panel_alt":      "#313244",
        "border":         "#45475A",
        "border_glow":    "#CBA6F740",
        "text":           "#CDD6F4",
        "muted":          "#A6ADC8",
        "secondary":      "#A6ADC8",
        "accent":         "#CBA6F7",
        "accent_glow":    "#CBA6F740",
        "green":          "#A6E3A1",
        "amber":          "#CBA6F7",
        "yellow":         "#CBA6F7",
        "red":            "#F38BA8",
        "purple":         "#CBA6F7",
        "pvo":            "#A6E3A1",
        "vref":           "#CBA6F7",
        "margin":         "#CBA6F7",
        "fail":           "#F38BA8",
        "ook":            "#CBA6F7",
        "chart_line":     "#A6E3A1",
        "chart_grid":     "#45475A",
        "sidebar_active": "#45475A",
        "header":         "#CBA6F7",
        "value":          "#CDD6F4",
        "footer_bg":      "#1E1E2E",
        "status_dot_on":  "#A6E3A1",
        "status_dot_off": "#F38BA8",
        "status_dot_sim": "#CBA6F7",
        "fontUi":         '"Plus Jakarta Sans", sans-serif',
        "fontMono":       '"JetBrains Mono", monospace',
    },

    # ── 4. Dracula Professional ───────────────────────────────────
    "dracula": {
        "bg":             "#282A36",
        "panel":          "#44475A",
        "panel_alt":      "#44475A",
        "border":         "#6272A4",
        "border_glow":    "#BD93F940",
        "text":           "#F8F8F2",
        "muted":          "#BFBFBF",
        "secondary":      "#BFBFBF",
        "accent":         "#BD93F9",
        "accent_glow":    "#BD93F940",
        "green":          "#50FA7B",
        "amber":          "#BD93F9",
        "yellow":         "#BD93F9",
        "red":            "#FF5555",
        "purple":         "#BD93F9",
        "pvo":            "#50FA7B",
        "vref":           "#BD93F9",
        "margin":         "#BD93F9",
        "fail":           "#FF5555",
        "ook":            "#BD93F9",
        "chart_line":     "#50FA7B",
        "chart_grid":     "#6272A4",
        "sidebar_active": "#6272A4",
        "header":         "#BD93F9",
        "value":          "#F8F8F2",
        "footer_bg":      "#282A36",
        "status_dot_on":  "#50FA7B",
        "status_dot_off": "#FF5555",
        "status_dot_sim": "#BD93F9",
        "fontUi":         '"Inter", sans-serif',
        "fontMono":       '"Fira Code", monospace',
    },

    # ── 5. Gruvbox Earth ───────────────────────────────────
    "gruvbox": {
        "bg":             "#282828",
        "panel":          "#3C3836",
        "panel_alt":      "#3C3836",
        "border":         "#504945",
        "border_glow":    "#D7992140",
        "text":           "#EBDBB2",
        "muted":          "#A89984",
        "secondary":      "#A89984",
        "accent":         "#D79921",
        "accent_glow":    "#D7992140",
        "green":          "#B8BB26",
        "amber":          "#D79921",
        "yellow":         "#D79921",
        "red":            "#CC241D",
        "purple":         "#D79921",
        "pvo":            "#B8BB26",
        "vref":           "#D79921",
        "margin":         "#D79921",
        "fail":           "#CC241D",
        "ook":            "#D79921",
        "chart_line":     "#B8BB26",
        "chart_grid":     "#504945",
        "sidebar_active": "#504945",
        "header":         "#D79921",
        "value":          "#EBDBB2",
        "footer_bg":      "#282828",
        "status_dot_on":  "#B8BB26",
        "status_dot_off": "#CC241D",
        "status_dot_sim": "#D79921",
        "fontUi":         '"Inter", sans-serif',
        "fontMono":       '"Space Mono", monospace',
    },

    # ── 6. Solarized Sepia ───────────────────────────────────
    "solarized": {
        "bg":             "#FDF6E3",
        "panel":          "#EEE8D5",
        "panel_alt":      "#EEE8D5",
        "border":         "#93A1A1",
        "border_glow":    "#268BD240",
        "text":           "#657B83",
        "muted":          "#586E75",
        "secondary":      "#586E75",
        "accent":         "#268BD2",
        "accent_glow":    "#268BD240",
        "green":          "#859900",
        "amber":          "#268BD2",
        "yellow":         "#268BD2",
        "red":            "#DC322F",
        "purple":         "#268BD2",
        "pvo":            "#859900",
        "vref":           "#268BD2",
        "margin":         "#268BD2",
        "fail":           "#DC322F",
        "ook":            "#268BD2",
        "chart_line":     "#859900",
        "chart_grid":     "#93A1A1",
        "sidebar_active": "#93A1A1",
        "header":         "#268BD2",
        "value":          "#657B83",
        "footer_bg":      "#FDF6E3",
        "status_dot_on":  "#859900",
        "status_dot_off": "#DC322F",
        "status_dot_sim": "#268BD2",
        "fontUi":         '"Inter", sans-serif',
        "fontMono":       '"JetBrains Mono", monospace',
    },

    # ── 7. Minimalist Edge ───────────────────────────────────
    "minimalist": {
        "bg":             "#FAFAFA",
        "panel":          "#FFFFFF",
        "panel_alt":      "#FFFFFF",
        "border":         "#E5E7EB",
        "border_glow":    "#11182740",
        "text":           "#0F172A",
        "muted":          "#64748B",
        "secondary":      "#64748B",
        "accent":         "#111827",
        "accent_glow":    "#11182740",
        "green":          "#10B981",
        "amber":          "#111827",
        "yellow":         "#111827",
        "red":            "#EF4444",
        "purple":         "#111827",
        "pvo":            "#10B981",
        "vref":           "#111827",
        "margin":         "#111827",
        "fail":           "#EF4444",
        "ook":            "#111827",
        "chart_line":     "#10B981",
        "chart_grid":     "#E5E7EB",
        "sidebar_active": "#E5E7EB",
        "header":         "#111827",
        "value":          "#0F172A",
        "footer_bg":      "#FAFAFA",
        "status_dot_on":  "#10B981",
        "status_dot_off": "#EF4444",
        "status_dot_sim": "#111827",
        "fontUi":         '"Plus Jakarta Sans", sans-serif',
        "fontMono":       '"JetBrains Mono", monospace',
    },

    # ── 8. Terminal Cyber ───────────────────────────────────
    "cyber": {
        "bg":             "#09090B",
        "panel":          "#18181B",
        "panel_alt":      "#18181B",
        "border":         "#27272A",
        "border_glow":    "#22D3EE40",
        "text":           "#F4F4F5",
        "muted":          "#A1A1AA",
        "secondary":      "#A1A1AA",
        "accent":         "#22D3EE",
        "accent_glow":    "#22D3EE40",
        "green":          "#4ADE80",
        "amber":          "#22D3EE",
        "yellow":         "#22D3EE",
        "red":            "#F87171",
        "purple":         "#22D3EE",
        "pvo":            "#4ADE80",
        "vref":           "#22D3EE",
        "margin":         "#22D3EE",
        "fail":           "#F87171",
        "ook":            "#22D3EE",
        "chart_line":     "#4ADE80",
        "chart_grid":     "#27272A",
        "sidebar_active": "#27272A",
        "header":         "#22D3EE",
        "value":          "#F4F4F5",
        "footer_bg":      "#09090B",
        "status_dot_on":  "#4ADE80",
        "status_dot_off": "#F87171",
        "status_dot_sim": "#22D3EE",
        "fontUi":         '"Space Mono", monospace',
        "fontMono":       '"Space Mono", monospace',
    },

}

# Legacy alias map
THEMES["dark"] = THEMES["midnight_navy"]
THEMES["light"] = THEMES["arctic_light"]

# ── Runtime state ───────────────────────────────────────────────────────────
current_theme: str = "midnight_navy"
current_accent: str = "blue"
current_density: DensityMode = "comfortable"

COLORS: dict[str, str] = THEMES[current_theme].copy()

# ── Preset metadata for Settings UI ─────────────────────────────────────────
THEME_PRESETS: list[dict] = [
    {
        "key": "midnight_navy",
        "label": "Midnight Navy",
        "desc": "Deep navy dark with blue glow",
        "preview_bg": "#0D1828",
        "preview_accent": "#3b82f6",
        "preview_text": "#E8EDF5",
    },
    {
        "key": "arctic_light",
        "label": "Arctic Light",
        "desc": "Clean airy light mode",
        "preview_bg": "#FFFFFF",
        "preview_accent": "#2563eb",
        "preview_text": "#141C28",
    },
    {
        "key": "dark_lab",
        "label": "Optical Dark Lab",
        "desc": "Recommended for Dark-Room Testing",
        "preview_bg": "#1E1E24",
        "preview_accent": "#FCA311",
        "preview_text": "#FFFFFF",
    },
    {
        "key": "clean_data",
        "label": "Clean Data Stream",
        "desc": "Academic Light Mode (Best for Panel)",
        "preview_bg": "#F8F9FA",
        "preview_accent": "#4361EE",
        "preview_text": "#212529",
    },
    {
        "key": "catppuccin",
        "label": "Catppuccin Pastel",
        "desc": "Soft High-Contrast Dark",
        "preview_bg": "#1E1E2E",
        "preview_accent": "#CBA6F7",
        "preview_text": "#CDD6F4",
    },
    {
        "key": "dracula",
        "label": "Dracula Professional",
        "desc": "Vibrant Neon Dark",
        "preview_bg": "#282A36",
        "preview_accent": "#BD93F9",
        "preview_text": "#F8F8F2",
    },
    {
        "key": "gruvbox",
        "label": "Gruvbox Earth",
        "desc": "Warm Eye-Care Dark",
        "preview_bg": "#282828",
        "preview_accent": "#D79921",
        "preview_text": "#EBDBB2",
    },
    {
        "key": "solarized",
        "label": "Solarized Sepia",
        "desc": "Low-Contrast Light",
        "preview_bg": "#FDF6E3",
        "preview_accent": "#268BD2",
        "preview_text": "#657B83",
    },
    {
        "key": "minimalist",
        "label": "Minimalist Edge",
        "desc": "Monochrome Focused",
        "preview_bg": "#FAFAFA",
        "preview_accent": "#111827",
        "preview_text": "#0F172A",
    },
    {
        "key": "cyber",
        "label": "Terminal Cyber",
        "desc": "Hacker Matrix Mode",
        "preview_bg": "#09090B",
        "preview_accent": "#22D3EE",
        "preview_text": "#F4F4F5",
    },
]


def apply_theme(
    theme: str | None = None,
    accent: str | None = None,
    density: DensityMode | None = None,
) -> None:
    """Apply a named theme preset with optional accent + density overrides."""
    global current_theme, current_accent, current_density

    if theme is not None and theme in THEMES:
        # Resolve aliases
        resolved = "midnight_navy" if theme == "dark" else ("arctic_light" if theme == "light" else theme)
        current_theme = resolved

    if accent is not None and accent in ACCENTS:
        current_accent = accent

    if density in {"comfortable", "compact"}:
        current_density = density

    COLORS.clear()
    COLORS.update(THEMES[current_theme])
    # Override accent only if the user has explicitly set one via the accent selector
    if current_accent in ACCENTS:
        COLORS["accent"] = ACCENTS[current_accent]


def apply_design_tokens(tokens: dict) -> None:
    """Apply design tokens from design.json to override theme colors."""
    if not tokens:
        return
    color_keys = ["bg", "panel", "panel_alt", "border", "text", "muted", "accent", "green", "amber", "red"]
    for key in color_keys:
        if key in tokens:
            COLORS[key] = tokens[key]
    global APP_QSS
    APP_QSS = build_qss()


def set_theme(theme: str) -> None:
    apply_theme(theme=theme)


def set_accent(accent: str) -> None:
    apply_theme(accent=accent)


def set_density(density: DensityMode) -> None:
    apply_theme(density=density)


def get_color(name: str) -> str:
    return COLORS.get(name, "#ffffff")


def build_qss() -> str:
    """Build the global QSS stylesheet from the current COLORS palette."""
    t = COLORS
    padding = "8px 14px" if current_density == "comfortable" else "5px 10px"
    item_padding = "10px 14px" if current_density == "comfortable" else "7px 12px"
    font_size = "13px" if current_density == "comfortable" else "12px"
    title_size = "20px" if current_density == "comfortable" else "18px"
    section_size = "11px" if current_density == "comfortable" else "10px"

    # Derive glow border color safely
    border_glow = t.get("border_glow", t["border"])
    accent_glow = t.get("accent_glow", t["accent"] + "33")
    footer_bg = t.get("footer_bg", t["panel"])

    return f"""
/* ── Base ──────────────────────────────────────────────────────── */
QWidget {{
    background: {t['bg']};
    color: {t['text']};
    font-family: {t.get('fontUi', '"Inter", "Segoe UI", Arial, sans-serif')};
    font-size: {font_size};
}}
QMainWindow, QStackedWidget {{ background: {t['bg']}; }}

/* ── Sidebar ────────────────────────────────────────────────────── */
QFrame#Sidebar, QWidget#Sidebar {{
    background: {t['panel']};
    border-right: 1px solid {t['border']};
    border-top: none;
    border-bottom: none;
    border-left: none;
}}

/* ── Navigation list ────────────────────────────────────────────── */
QListWidget {{
    background: transparent;
    border: none;
    outline: none;
    font-size: {font_size};
}}
QListWidget::item {{
    padding: {item_padding};
    border-radius: 7px;
    color: {t['muted']};
    margin: 1px 0px;
}}
QListWidget::item:selected {{
    background: {t['sidebar_active']};
    color: {t['text']};
    font-weight: 600;
    border-left: 3px solid {t['accent']};
    padding-left: 11px;
}}
QListWidget::item:hover:!selected {{
    background: {t['sidebar_active']};
    color: {t['secondary']};
}}

/* ── Cards / panels ─────────────────────────────────────────────── */
QFrame#Card {{
    background: {t['panel']};
    border: 1px solid {t['border']};
    border-top: 1px solid {t.get('border_glow', t['border'])};
    border-radius: 10px;
}}
QFrame#ChartFrame {{
    background: {t['panel']};
    border: 1px solid {t['border']};
    border-radius: 10px;
}}

/* ── Typography labels ──────────────────────────────────────────── */
QLabel {{ background: transparent; }}
QLabel#Title {{
    font-size: {title_size};
    font-weight: 700;
    background: transparent;
    letter-spacing: -0.3px;
}}
QLabel#SectionTitle {{
    font-size: {section_size};
    font-weight: 700;
    color: {t['header']};
    letter-spacing: 1.2px;
    text-transform: uppercase;
    background: transparent;
}}
QLabel#Muted {{ color: {t['muted']}; background: transparent; }}
QLabel#Value {{ color: {t['value']}; background: transparent; font-weight: 600; }}
QLabel#StatusGreen {{ color: {t['green']}; font-weight: 700; background: transparent; }}
QLabel#DemoBadge {{
    background: {t['panel_alt']};
    color: {t['muted']};
    border: 1px solid {t['border']};
    border-radius: 999px;
    padding: 4px 10px;
    font-weight: 700;
    font-size: 11px;
}}
QLabel#Toast {{
    background: {t['panel']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 8px 12px;
    font-weight: 600;
}}

/* ── Inputs ─────────────────────────────────────────────────────── */
QComboBox, QLineEdit {{
    background: {t['panel_alt']};
    border: 1px solid {t['border']};
    border-radius: 7px;
    padding: {padding};
    color: {t['text']};
    selection-background-color: {t['accent']};
}}
QComboBox:hover, QLineEdit:hover {{
    border-color: {t['secondary']};
}}
QComboBox:focus, QLineEdit:focus {{
    border-color: {t['accent']};
    border-width: 1px;
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {t['panel']};
    color: {t['text']};
    selection-background-color: {t['accent']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 4px;
}}

/* ── Buttons ────────────────────────────────────────────────────── */
QPushButton {{
    background: {t['panel_alt']};
    border: 1px solid {t['border']};
    border-radius: 7px;
    padding: {padding};
    color: {t['text']};
    font-weight: 500;
}}
QPushButton:hover {{
    border-color: {t['accent']};
    background: {t['sidebar_active']};
    color: {t['text']};
}}
QPushButton:pressed {{
    background: {t['panel']};
}}
QPushButton#Primary {{
    background: {t['accent']};
    border: 1px solid {t['accent']};
    color: white;
    font-weight: 700;
}}
QPushButton#Primary:hover {{
    background: {t['accent']};
    border-color: {t['accent']};
    color: white;
}}
QPushButton#Danger {{
    background: {t['red']};
    border-color: {t['red']};
    color: white;
    font-weight: 700;
}}
QPushButton#Danger:hover {{
    border-color: {t['red']};
}}
QPushButton:disabled,
QPushButton#Primary:disabled {{
    background: {t['panel_alt']};
    border-color: {t['border']};
    color: {t['muted']};
    font-weight: 400;
}}
QPushButton#Secondary {{
    background: {t['panel_alt']};
    border: 1px solid {t['border']};
    color: {t['text']};
    font-weight: 600;
    border-radius: 7px;
}}
QPushButton#Secondary:hover {{
    border-color: {t['accent']};
    background: {t['sidebar_active']};
}}
QPushButton#ExportBtn {{
    background: {t['green']};
    border: 1px solid {t['green']};
    color: {t['bg']};
    font-weight: 700;
    border-radius: 7px;
}}
QPushButton#ExportBtn:hover {{
    background: {t['green']};
    border-color: {t['green']};
}}

/* ── Extra labels ────────────────────────────────────────────────── */
QLabel#AboutTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {t['accent']};
    background: transparent;
    letter-spacing: 0.5px;
}}
QLabel#AboutDesc {{
    color: {t['secondary']};
    background: transparent;
}}
QLabel#FeedbackSuccess {{
    color: {t['green']};
    background: transparent;
    font-size: 11px;
    font-weight: 700;
}}
QLineEdit#SearchInput {{
    background: {t['panel_alt']};
    border: 1px solid {t['border']};
    border-radius: 7px;
    padding: 6px 10px;
    color: {t['text']};
}}
QLineEdit#SearchInput:focus {{
    border-color: {t['accent']};
}}

/* ── Splitter ───────────────────────────────────────────────────── */
QSplitter::handle {{ image: none; background: transparent; }}

/* ── Footer / Header bars ───────────────────────────────────────── */
QWidget#FooterBar {{
    background: {footer_bg};
    border-top: 1px solid {t['border']};
}}
QWidget#HeaderBar {{
    background: {footer_bg};
    border-bottom: 1px solid {t['border']};
}}

/* ── Launcher ────────────────────────────────────────────────────── */
QFrame#LauncherBg {{
    background: {t['bg']};
    border: none;
}}
QFrame#ConsoleCard {{
    background: {t['panel']};
    border: 1px solid {t['border']};
    border-top: 2px solid {t.get('border_glow', t['border'])};
    border-radius: 14px;
}}
QFrame#ConsoleCard:hover {{
    border: 2px solid {t['accent']};
    border-top: 2px solid {t['accent']};
    background: {t['sidebar_active']};
}}
QLabel#LauncherTitle {{
    color: {t['accent']};
    font-size: 26px;
    font-weight: 800;
    letter-spacing: 2px;
    background: transparent;
}}
QLabel#LauncherSubtitle {{
    color: {t['muted']};
    font-size: 13px;
    background: transparent;
}}
QLabel#LauncherBadge {{
    color: {t['muted']};
    font-size: 11px;
    font-weight: 600;
    background: transparent;
}}
QLabel#CardTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {t['text']};
    background: transparent;
}}
QLabel#CardDesc {{
    font-size: 11px;
    color: {t['muted']};
    background: transparent;
}}
QLabel#CardAccent {{
    font-size: 11px;
    font-weight: 700;
    color: {t['accent']};
    background: transparent;
}}

/* ── Table ──────────────────────────────────────────────────────── */
QTableWidget {{
    background: {t['panel']};
    alternate-background-color: {t['panel_alt']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: {t['sidebar_active']};
    selection-color: {t['text']};
    outline: none;
    font-size: 12px;
}}
QTableWidget::item {{
    padding: 8px 12px;
    border: none;
}}
QHeaderView::section {{
    background: {t['panel_alt']};
    color: {t['muted']};
    border: none;
    border-bottom: 1px solid {t['border']};
    padding: {padding};
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}

/* ── Scrollbar ──────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    border-radius: 3px;
    margin: 2px 0;
}}
QScrollBar::handle:vertical {{
    background: {t['border']};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t['muted']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {t['border']};
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t['muted']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Progress bar ───────────────────────────────────────────────── */
QProgressBar {{
    border: 1px solid {t['border']};
    border-radius: 5px;
    background: {t['panel_alt']};
    height: 8px;
    text-align: center;
    font-size: 10px;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {t['green']};
    border-radius: 5px;
}}

/* ── Splitter ───────────────────────────────────────────────────── */
QSplitter::handle {{ image: none; background: transparent; }}

/* ── TabWidget ──────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {t['border']};
    background: {t['panel_alt']};
    border-radius: 6px;
}}
QTabBar::tab {{
    background: {t['panel']};
    border: 1px solid {t['border']};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 8px 14px;
    color: {t['muted']};
    font-weight: 600;
    font-size: 11px;
}}
QTabBar::tab:selected, QTabBar::tab:hover {{
    background: {t['panel_alt']};
    color: {t['text']};
}}

/* ── Footer / Header bars ───────────────────────────────────────── */
QWidget#FooterBar {{
    background: {footer_bg};
    border-top: 1px solid {t['border']};
}}
QWidget#HeaderBar {{
    background: {footer_bg};
    border-bottom: 1px solid {t['border']};
}}
"""



apply_theme(current_theme, current_accent, current_density)
APP_QSS = build_qss()
