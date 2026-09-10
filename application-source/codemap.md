# gui_dev_v3 — Root Application Module
> **Active development target.** This is the current VLC GUI codebase. New features and fixes go here.

## Responsibility
Top-level entry point and shared infrastructure for both RX (receiver) and TX (transmitter) VLC desktop applications. Provides the main window (`_BaseWindow`, `VLCReceiverWindow`, `VLCTransmitterWindow`), application state stores (`RXAppState`, `TXAppState`), domain models, reusable UI widgets, a theme system, settings persistence, and mock/fixture data for development. Launched via `main()` (RX) and `main_tx()` (TX) entry points.

## Design
- **Observer pattern**: `RXAppState`/`TXAppState` manage a subscriber list; UI components subscribe and get notified on refresh.
- **Strategy pattern**: State delegates to Physical or Simulation backends based on `mode`.
- **Dataclass-driven**: All model types (`SessionState`, `SignalState`, `TransferRecord`, `TransferQuality`, `ChunkRecord`, etc.) are frozen dataclasses for immutability and type safety.
- **Theme system**: `theme.py` provides a `COLORS` dict, per-mode theme palettes (dark/light), accent colors, density modes, and generates dynamic QSS.
- **Settings persistence**: `settings_store.py` persists `AppSettings` as JSON to `~/.vlc_rx_app/settings.json`; `settings.py` provides QSettings-based UI binding helpers (`bind_toggle`, `bind_spin`, `bind_combo`, etc.).
- **Widget hierarchy**: `widgets.py` provides `Card`, `MetricCard`, `StatusBadge`, `ProgressBar`, `WaveformWidget`, `ActivityLogTable`, `ModeToggle`, `MetricGrid`, `DetailRow`, `SectionCard`.

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
