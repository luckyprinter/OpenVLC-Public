# rx/ — Receiver (RX) Module

## Responsibility
All UI pages and logic specific to the VLC Receiver application. Provides the main shell with sidebar navigation, a live dashboard with 6 auto-refreshing panels, experiment management (create/view/delete with JSON-backed store), a table builder for generating custom data tables, multi-tab settings (9 sections with QSettings persistence), and placeholder pages for unimplemented tabs.

## Design
- **Shell/Page pattern**: `RXShell` owns a `QListWidget` sidebar + `QStackedWidget` content area. Pages are registered by key matching `SIDEBAR_TABS` in `navigation.py`. A `QTimer` polls state every 1s and refreshes the active page.
- **Hardware connection**: `RXShell` displays the physical ESP32 connection and firmware state. The receiver has no simulated operating mode.
- **Dashboard subpanels**: `RXDashboardPage` composes reception status, performance metrics, signal monitoring, file information, decoder status, and activity-log panels. Detailed live waveforms and signal history are provided on the Signal page.
- **Experiment store**: `experiment_store.py` is a JSON-file-backed CRUD store at `~/.vlc_rx/experiments.json` with seed data. `experiments_page.py` exposes form + table UI.
- **Table Builder**: `table_builder_page.py` has a two-view system (builder → preview). Uses `QListWidget` with drag-drop reorder, category-grouped available columns, and manual columns with checkboxes. Any sample rows are table-preview fixtures only; they do not emulate or replace hardware data.
- **Settings**: `settings.py` in this folder assembles a `SettingsContainer` with 9 section pages (General, Connection, Firmware, Signal Monitoring, Experiments, Database, Table Generator, Logging, Developer) using reusable `SettingRow`/`bind_*` helpers.

## Flow
```
RXShell.__init__()
  → Initialize hardware-only receiver state
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
