# tx/ — Transmitter (TX) Module

## Responsibility
All UI pages and logic specific to the VLC Transmitter application. Provides the main shell, a live dashboard monitoring file info, TX settings, transmission control, progress, and log; multi-tab settings (6 sections); placeholder pages; and tab definitions.

## Design
- **Shell/Page pattern**: `TXShell` mirrors the RX shell structure — sidebar navigation (6 tabs), `QStackedWidget` content, mode toggle, 1s poll timer.
- **TX-specific navigation**: `TX_SIDEBAR_TABS` defined in `navigation.py`: Dashboard, Transmit, File Manager, Settings, Logs, About.
- **Dashboard subpanels** (`TXDashboardPage`):
  - `_FileInfoPanel` — displays filename, type, size, chunks
  - `_TSSettingsPanel` — encoding, modulation, symbol rate, LED pin, TX power, pre-emphasis
  - `_TXControlPanel` — START button + status text
  - `_TXProgressPanel` — progress bar + 4 metric columns (chunk, elapsed, estimated, data rate)
  - `_TXLogPanel` — scrollable monospaced log with alternating row backgrounds
  - `_TXStatusBar` — port, connection indicator, time, mode badge
- **Settings**: 6-section `SettingsContainer` (General, Connection, Firmware, Transmission, Logging, Developer) with QSettings persistence via `bind_*` helpers.
- **Placeholders**: `TransmitPage`, `FileManagerPage`, `LogsPage`, `AboutPage` — stub widgets with descriptive text.

## Flow
```
TXShell.__init__()
  → Restore mode from QSettings
  → Build sidebar + register pages in QStackedWidget
  → _on_poll_timer() → state.refresh() → _refresh_current_page()
  TXDashboardPage.refresh()
    → _file_info.refresh(state)
    → _tx_settings.refresh(state)
    → _tx_control.refresh(state)
    → _tx_progress.refresh(state)
    → _tx_log.refresh(state)
    → _status_bar.refresh(state)
```

## Integration
- **Depends on**: Root `tx_app_state.py` (`TXAppState`), `tx_mock_data.py`, `widgets.py`, `theme.py`, `settings.py` (helpers), `#tx/backends/`.
- **Depended by**: Root `app.py` creates `VLCTransmitterWindow` → `TXShell` as central widget via `main_tx()`.
- **External**: PySide6.
