# rx/ — Receiver (RX) Module

## Responsibility
All UI pages and logic specific to the VLC Receiver application. Provides the main shell with sidebar navigation, a live dashboard with 6 auto-refreshing panels, experiment management (create/view/delete with JSON-backed store), a table builder for generating custom data tables, multi-tab settings (9 sections with QSettings persistence), and placeholder pages for unimplemented tabs.

## Design
- **Shell/Page pattern**: `RXShell` owns a `QListWidget` sidebar + `QStackedWidget` content area. Pages are registered by key matching `SIDEBAR_TABS` in `navigation.py`. A `QTimer` polls state every 1s and refreshes the active page.
- **Mode toggle**: `ModeToggle` (from root `widgets.py`) switches between `physical`/`simulated` mode, saved to QSettings.
- **Dashboard subpanels**: `RXDashboardPage` composes `_ReceptionStatusPanel`, `_PerformanceMetricsPanel`, `_SignalMonitorPanel`, `_SignalWaveformPanel`, `_FileInfoPanel`, `_ActivityLogPanel`. Each has a `refresh(state)` method that clears and rebuilds its content from the current `RXAppState`.
- **Experiment store**: `experiment_store.py` is a JSON-file-backed CRUD store at `~/.vlc_rx/experiments.json` with seed data. `experiments_page.py` exposes form + table UI.
- **Table Builder**: `table_builder_page.py` has a two-view system (builder → preview). Uses `QListWidget` with drag-drop reorder, category-grouped available columns, manual columns with checkboxes, and generates realistic mock VLC test data.
- **Settings**: `settings.py` in this folder assembles a `SettingsContainer` with 9 section pages (General, Connection, Firmware, Signal Monitoring, Experiments, Database, Table Generator, Logging, Developer) using reusable `SettingRow`/`bind_*` helpers.

## Flow
```
RXShell.__init__()
  → Restore mode from QSettings
  → Build sidebar + register pages in QStackedWidget
  → _build_pages() creates page instances (dashboard, experiments, etc.)
  → _on_nav_changed() switches QStackedWidget, calls refresh()
  → _on_poll_timer() → state.refresh() → _refresh_current_page()
  Each page.refresh() reads state fields and rebuilds child widgets
```

## Integration
- **Depends on**: Root `app_state.py` (`RXAppState`), `widgets.py`, `theme.py`, `settings.py` (helpers), `navigation.py`, `data/`, `logic/`.
- **Depended by**: Root `app.py` creates `VLCReceiverWindow` → `RXShell` as central widget.
- **External**: PySide6 (`QtWidgets`, `QtCore`).
