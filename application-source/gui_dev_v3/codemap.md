# gui_dev_v3 — Root Application Module
> **Active development target.** This is the current VLC GUI codebase. New features and fixes go here.

## Responsibility
Top-level entry point and shared infrastructure for both RX (receiver) and TX (transmitter) VLC desktop applications. Provides the unified launcher, TX/RX application shells, application state stores (`RXAppState`, `TXAppState`), domain models, reusable UI widgets, theme system, and settings persistence. Both consoles use physical ESP32 backends over USB serial.

## Design
- **Observer pattern**: `RXAppState`/`TXAppState` manage a subscriber list; UI components subscribe and get notified on refresh.
- **Hardware boundary**: RX and TX state objects read from their respective physical ESP32 serial backends. There is no virtual hardware or simulation mode.
- **Dataclass-driven**: All model types (`SessionState`, `SignalState`, `TransferRecord`, `TransferQuality`, `ChunkRecord`, etc.) are frozen dataclasses for immutability and type safety.
- **Theme system**: `theme.py` provides a `COLORS` dict, per-mode theme palettes (dark/light), accent colors, density modes, and generates dynamic QSS.
- **Settings persistence**: `settings_store.py` persists `AppSettings` as JSON to `~/.vlc_rx_app/settings.json`; `settings.py` provides QSettings-based UI binding helpers (`bind_toggle`, `bind_spin`, `bind_combo`, etc.).
- **Widget hierarchy**: `widgets.py` provides reusable cards, metric displays, status badges, progress bars, waveform displays, activity logs, and layout helpers.

## Flow
```
app.py:main()/main_tx()
  → QApplication + Fusion style
  → _BaseWindow (load settings, apply theme)
    → RXAppState / TXAppState (build default state, init backends)
    → RXShell / TXShell (sidebar + stacked pages, poll timer)
      → Pages (dashboard, settings, etc.) read state and render
  → QTimer polls state.refresh() every 1s → notify subscribers
```

## Integration
- **Depends on**: `rx/`, `tx/`, `data/`, `serial/`, `logic/` subpackages.
- **Depended by**: `rx/shell.py` and `tx/shell.py` import `RXAppState`/`TXAppState`; `rx/` and `tx/` page modules import shared widgets and theme.
- **External**: PySide6, pyserial (optional, for physical backends).
