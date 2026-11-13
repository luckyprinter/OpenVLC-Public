"""Offscreen geometry checks for the responsive TX/RX application shell."""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QBoxLayout, QScrollArea, QWidget

from gui_dev_v3.app import VLCMainWindow, _BaseWindow, _minimum_window_dimensions
from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.rx.dashboard import RXDashboardPage
from gui_dev_v3.rx.receive_page import ReceivePage
from gui_dev_v3.rx.ber_analyzer_page import BERAnalyzerPage
from gui_dev_v3.rx.experiments_page import ExperimentsPage
from gui_dev_v3.rx import experiment_store as experiment_store_module
from gui_dev_v3.rx.table_builder_page import TableBuilderPage
from gui_dev_v3.rx.export_page import ExportPage
from gui_dev_v3.rx import export_page as export_page_module
from gui_dev_v3.rx.inspect_page import InspectPage
from gui_dev_v3.rx.signal_page import SignalMonitorPage
from gui_dev_v3.settings import SettingsContainer, ThemePickerGrid, SpinSetting
from gui_dev_v3.tx.dashboard import CurrentSessionWidget, FileDetailsWidget, TXDashboardPage
from gui_dev_v3.tx_app_state import TXAppState
from gui_dev_v3.tx.placeholders import TransmitPage
from gui_dev_v3.tx.file_manager_page import FileManagerPage


@pytest.fixture(autouse=True)
def isolate_legacy_export_history(monkeypatch, tmp_path):
    monkeypatch.setattr(
        export_page_module,
        "LEGACY_HISTORY_PATH",
        tmp_path / "no-legacy-history.json",
    )


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.parametrize("mode", ["tx", "rx"])
@pytest.mark.parametrize(
    ("width", "height", "expected_sidebar_width", "labels_visible"),
    [
        (1366, 768, 224, True),
        (1280, 720, 224, True),
        (1024, 700, 72, False),
        (680, 500, 72, False),
    ],
)
def test_console_shell_reflows_without_overlapping_navigation(
    qapp: QApplication,
    mode: str,
    width: int,
    height: int,
    expected_sidebar_width: int,
    labels_visible: bool,
) -> None:
    window = VLCMainWindow()
    window.show()
    window.resize(width, height)
    window.launch_mode(mode)
    qapp.processEvents()

    shell = window._tx_shell if mode == "tx" else window._rx_shell
    assert shell is not None
    qapp.processEvents()

    assert shell.sidebar.width() == expected_sidebar_width
    assert shell.nav.count() > 0
    assert shell.pages.width() > 0
    assert shell.pages.height() > 0
    assert shell._page_heading.text() == "Dashboard"

    # The sidebar and workspace are adjacent siblings, never overlapping.
    assert shell.sidebar.geometry().right() < shell._main_area.geometry().left()
    assert shell._main_area.geometry().right() <= shell.rect().right()

    first_item = shell.nav.item(0)
    assert bool(first_item.text()) is labels_visible
    assert first_item.toolTip()

    active_page = shell.pages.currentWidget()
    assert active_page is not None
    assert active_page.width() > 0
    assert active_page.height() > 0

    window.return_to_launcher()
    window.close()
    qapp.processEvents()


def test_theme_picker_shows_curated_presets_and_keeps_saved_legacy_theme(qapp):
    from gui_dev_v3.settings import ThemePickerGrid

    picker = ThemePickerGrid(current="graphite_lab")
    assert {card._key for card in picker._cards} == {
        "graphite_lab",
        "midnight_navy",
        "arctic_light",
        "dark_lab",
        "clean_data",
    }

    # A user's previously selected non-curated theme remains visible rather
    # than silently appearing unselected after the UI is simplified.
    legacy_picker = ThemePickerGrid(current="dracula")
    legacy_keys = {card._key for card in legacy_picker._cards}
    assert "dracula" in legacy_keys
    assert len(legacy_keys) == 6


def test_rx_dashboard_simplifies_secondary_panels_on_compact_work_area(qapp):
    dashboard = RXDashboardPage(RXAppState())
    dashboard.resize(680, 500)
    dashboard.show()
    qapp.processEvents()

    assert dashboard._compact_layout
    assert dashboard._reception.isVisible()
    assert dashboard._file_info.isVisible()
    assert not dashboard._file_info.filesize_row.isVisible()
    assert not dashboard._file_info.received_size_row.isVisible()
    assert not dashboard._perf.isVisible()
    assert not dashboard._signal_mon.isVisible()
    assert not dashboard._receiver_state.isVisible()
    assert not dashboard._activity_log.isVisible()

    dashboard.resize(1100, 700)
    qapp.processEvents()
    assert not dashboard._compact_layout
    assert dashboard._perf.isVisible()
    assert dashboard._signal_mon.isVisible()
    assert dashboard._receiver_state.isVisible()
    # On a standard 700 px laptop height, keep the received-file card tall
    # and leave activity details to the dedicated Logs page.
    assert not dashboard._activity_log.isVisible()

    dashboard.resize(1100, 800)
    qapp.processEvents()
    assert dashboard._activity_log.isVisible()
    dashboard.close()


def test_theme_picker_reflows_to_two_columns_on_narrow_width(qapp):
    picker = ThemePickerGrid()
    picker.resize(420, 180)
    picker.show()
    qapp.processEvents()

    assert picker._column_count == 2
    assert all(card.focusPolicy().name == "StrongFocus" for card in picker._cards)
    assert all(card.accessibleName() for card in picker._cards)
    positions = [
        picker._grid.getItemPosition(index)
        for index in range(picker._grid.count())
    ]
    assert max(column for _row, column, _row_span, _column_span in positions) < 2
    picker.close()


def test_settings_container_reduces_gutters_on_compact_width(qapp):
    page = QWidget()
    settings = SettingsContainer([
        ("General & Display", page),
        ("Diagnostics & Logs", QWidget()),
    ])
    settings.resize(700, 500)
    settings.show()
    qapp.processEvents()

    assert settings._nav_list.focusPolicy().name == "StrongFocus"
    assert settings._nav_panel.width() == 180
    assert settings._nav_list.accessibleName() == "Settings sections"
    assert settings._nav_list.wordWrap()
    assert settings._nav_list.item(0).text() == "General"
    assert settings._nav_list.item(0).data(Qt.ItemDataRole.AccessibleTextRole) == "General & Display"
    wrapper_layout = settings._page_wrappers[0].layout()
    margins = wrapper_layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        10, 12, 10, 12
    )

    settings.resize(1000, 700)
    qapp.processEvents()
    assert settings._nav_list.item(0).text() == "General & Display"
    margins = wrapper_layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        24, 20, 24, 24
    )
    settings.close()


def test_tx_transmission_queue_hides_secondary_panels_on_compact_display(qapp):
    page = TransmitPage()
    page.resize(680, 500)
    page.show()
    qapp.processEvents()

    assert page._compact_layout
    assert page._queue_card.isVisible()
    assert page._controls_card.isVisible()
    assert not page._config_card.isVisible()
    assert not page._history_card.isVisible()

    page.resize(1100, 700)
    qapp.processEvents()
    assert not page._compact_layout
    assert page._config_card.isVisible()
    assert page._history_card.isVisible()
    page.close()


def test_rx_inspect_stacks_explorers_on_compact_display(qapp):
    page = InspectPage()
    page.resize(680, 500)
    page.show()
    qapp.processEvents()

    assert page._compact_layout
    assert page._bottom_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert page._ref_status_layout.direction() == QBoxLayout.Direction.TopToBottom

    page.resize(1100, 700)
    qapp.processEvents()
    assert not page._compact_layout
    assert page._bottom_layout.direction() == QBoxLayout.Direction.LeftToRight
    page.close()


def test_rx_signal_page_reflows_metrics_and_diagnostics_on_compact_display(qapp):
    from dataclasses import replace

    offline_state = RXAppState()
    page = SignalMonitorPage(offline_state)
    page.refresh(offline_state)
    assert not hasattr(page, "_ook_widget")
    assert page._signal_waveform._buffer == []

    # The plot receives one point per actual state refresh, not ten repeated
    # copies of the same low-rate telemetry value from a 100 ms timer.
    offline_state.serial_connected = True
    offline_state.signal = replace(
        offline_state.signal, pvo=1.20, vref=0.80, margin=0.40
    )
    page.refresh(offline_state)
    assert len(page._signal_waveform._buffer) == 1
    page.refresh(offline_state)
    assert len(page._signal_waveform._buffer) == 1
    page._last_sample_monotonic -= 2.0
    page.refresh(offline_state)
    assert len(page._signal_waveform._buffer) == 2
    offline_state.serial_connected = False
    page.refresh(offline_state)
    assert page._signal_waveform._buffer == []
    assert not page._quality_top._available
    assert not page._noise_top._available
    assert all(bar._value_str == "—" for bar in page._quality_bars.values())
    page.resize(680, 500)
    page.show()
    qapp.processEvents()

    assert page._compact_layout
    assert page._middle_splitter.orientation() == Qt.Orientation.Vertical
    assert page._bottom_splitter.orientation() == Qt.Orientation.Vertical
    positions = [
        page._metric_grid.getItemPosition(index)
        for index in range(page._metric_grid.count())
    ]
    assert max(column for _row, column, _row_span, _column_span in positions) < 2

    page.resize(1100, 700)
    qapp.processEvents()
    assert not page._compact_layout
    assert page._middle_splitter.orientation() == Qt.Orientation.Horizontal
    assert page._bottom_splitter.orientation() == Qt.Orientation.Horizontal
    page.shutdown()
    page.close()


def test_tx_file_manager_stacks_details_on_compact_display(qapp):
    page = FileManagerPage()
    page.resize(680, 500)
    page.show()
    qapp.processEvents()

    assert page._compact_layout
    assert page._main_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert page.file_table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded

    page.resize(1100, 700)
    qapp.processEvents()
    assert not page._compact_layout
    assert page._main_layout.direction() == QBoxLayout.Direction.LeftToRight
    page.resize(1024, 700)
    qapp.processEvents()
    header = page.file_table.horizontalHeader()
    assert header.sectionSize(0) >= 120
    assert all(
        page.file_table.horizontalHeaderItem(column).textAlignment() == Qt.AlignmentFlag.AlignCenter
        for column in range(page.file_table.columnCount())
    )
    page.close()


def test_rx_receive_actions_stack_on_compact_display(qapp):
    page = ReceivePage()
    state = RXAppState()
    page.refresh(state)
    assert not page.lock_btn.isEnabled()
    page._on_lock_vref()
    assert not page._vref_locked

    state.serial_connected = True
    page.refresh(state)
    assert page.lock_btn.isEnabled()
    page._on_lock_vref()
    assert page._vref_locked

    page.resize(680, 500)
    page.show()
    qapp.processEvents()

    assert page._compact_layout
    assert page._control_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert page._status_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert page.terminal.minimumHeight() >= 180

    page.resize(1100, 700)
    qapp.processEvents()
    assert not page._compact_layout
    assert page._control_layout.direction() == QBoxLayout.Direction.LeftToRight
    page.close()


def test_rx_ber_metrics_reflow_on_compact_display(qapp):
    page = BERAnalyzerPage()
    page.resize(680, 500)
    page.show()
    qapp.processEvents()

    assert page._compact_layout
    compact_positions = [
        page._stats_grid.getItemPosition(index)
        for index in range(page._stats_grid.count())
    ]
    assert max(column for _row, column, _row_span, _column_span in compact_positions) < 4

    page.resize(1100, 700)
    qapp.processEvents()
    assert not page._compact_layout
    wide_positions = [
        page._stats_grid.getItemPosition(index)
        for index in range(page._stats_grid.count())
    ]
    assert max(column for _row, column, _row_span, _column_span in wide_positions) < 6
    page.close()


def test_rx_receive_clear_is_display_only_and_does_not_immediately_repopulate(qapp):
    page = ReceivePage()
    page._last_text = "received payload"
    page.terminal.setPlainText("received payload")

    page._on_clear_terminal()
    assert page.terminal.toPlainText() == ""
    assert page._last_text == "received payload"
    assert not page.reset_btn.isEnabled()
    assert page.reset_btn.isHidden()
    assert "does not currently expose" in page.reset_btn.toolTip()

    chunk = SimpleNamespace(index=0, received=b"received payload")
    transfer = SimpleNamespace(
        filename="sample.txt",
        tid=1,
        received_chunks=1,
        total_chunks=1,
        chunks=[chunk],
        status=None,
    )
    state = SimpleNamespace(transfer=transfer, is_receiving=True, progress_percent=50, serial_connected=False)
    page.refresh(state)
    assert page.terminal.toPlainText() == ""

    chunk.received = b"received payload plus new data"
    page.refresh(state)
    assert page.terminal.toPlainText() == "received payload plus new data"
    page.close()


def test_rx_experiments_stack_form_and_saved_records_on_compact_display(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(experiment_store_module, "STORE_DIR", tmp_path)
    monkeypatch.setattr(experiment_store_module, "STORE_PATH", tmp_path / "experiments.json")
    page = ExperimentsPage()
    assert not page._empty_state.isHidden()
    assert page._table.isHidden()
    assert page._table.rowCount() == 0
    # The 1024x700 target must stack the form and saved-records table.
    page.resize(1024, 700)
    page.show()
    qapp.processEvents()

    assert page._compact_layout
    assert page._body_layout.direction() == QBoxLayout.Direction.TopToBottom

    # Only a genuinely roomy work area should restore the side-by-side layout.
    page.resize(1200, 760)
    qapp.processEvents()
    assert not page._compact_layout, f"actual page size: {page.width()}x{page.height()}"
    assert page._body_layout.direction() == QBoxLayout.Direction.LeftToRight
    page.close()


def test_rx_table_builder_stacks_column_lists_on_compact_display(qapp):
    page = TableBuilderPage()
    page.resize(680, 500)
    page.show()
    qapp.processEvents()

    assert page._compact_layout
    assert page._builder_top_row.direction() == QBoxLayout.Direction.TopToBottom
    assert page._three_col_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert page._arrow_layout.direction() == QBoxLayout.Direction.LeftToRight

    # Clear the prior narrow-content minimum before simulating a wider,
    # short viewport; the real QScrollArea does this as its viewport widens.
    page.setMinimumHeight(0)
    # Wide but short windows keep the picker in three columns while using
    # compact spacing; the 1024x700 workspace is narrow enough to stack it.
    page.resize(1022, 574)
    qapp.processEvents()
    assert page._compact_layout
    assert not page._narrow_layout
    assert page._three_col_layout.direction() == QBoxLayout.Direction.LeftToRight

    page.resize(936, 554)
    qapp.processEvents()
    assert page._compact_layout
    assert page._narrow_layout
    assert page._three_col_layout.direction() == QBoxLayout.Direction.TopToBottom
    assert page.minimumHeight() >= 900
    assert all(
        card.minimumHeight() >= 220
        for card in (page._available_card, page._selected_card, page._manual_card)
    )

    page.resize(1200, 800)
    qapp.processEvents()
    assert not page._compact_layout
    assert page.minimumHeight() == 0
    assert page._three_col_layout.direction() == QBoxLayout.Direction.LeftToRight
    assert page._arrow_layout.direction() == QBoxLayout.Direction.TopToBottom
    page.close()


def test_rx_export_stacks_history_and_inspector_on_compact_display(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(export_page_module, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(export_page_module, "HISTORY_PATH", tmp_path / "history.json")
    page = ExportPage()
    assert page._history_data == []
    assert not export_page_module.HISTORY_PATH.exists()
    assert not page._history_empty_state.isHidden()
    assert page.table.rowCount() == 0
    page.resize(680, 500)
    page.show()
    qapp.processEvents()

    assert page._compact_layout
    assert page.splitter.orientation() == Qt.Orientation.Vertical

    page.resize(1100, 700)
    qapp.processEvents()
    assert not page._compact_layout
    assert page.splitter.orientation() == Qt.Orientation.Horizontal
    page.close()


def test_rx_export_preserves_unreadable_history_instead_of_overwriting(qapp, monkeypatch, tmp_path):
    history_path = tmp_path / "history.json"
    history_path.write_text("{ invalid json", encoding="utf-8")
    monkeypatch.setattr(export_page_module, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(export_page_module, "HISTORY_PATH", history_path)

    page = ExportPage()
    assert page._history_data == []
    page._history_data.append({"tid": 99, "filename": "must-not-overwrite.bin"})
    page._save_history()
    assert history_path.read_text(encoding="utf-8") == "{ invalid json"
    page.close()


def test_numeric_settings_keep_suffix_visible(qapp):
    setting = SpinSetting(3, 1, 60, "seconds")
    assert setting.width() >= setting.sizeHint().width()
    assert setting.width() >= 128



def test_table_builder_exports_blank_template_without_fabricated_measurements(qapp):
    page = TableBuilderPage()
    page._selected_keys = ["Distance (m)", "BER (%)", "PV0 (V)"]
    page._generate_table_data(preview=True)

    assert "no synthetic test data" in page._preview_notice.text()
    assert page._preview_table.rowCount() > 0
    assert page._preview_table.columnCount() == len(page._get_column_labels())
    column_keys = page._get_column_keys()
    for row in range(page._preview_table.rowCount()):
        for column, key in enumerate(column_keys):
            item = page._preview_table.item(row, column)
            assert item is not None
            expected = str(row + 1) if key == "trial_col" else ""
            assert item.text() == expected

    page.close()


def test_tx_dashboard_hides_secondary_panels_on_compact_display(qapp):
    page = TXDashboardPage(TXAppState())
    assert not page.findChildren(QScrollArea), "Dashboard panels must not introduce nested scrolling"
    page.resize(800, 600)
    page.show()
    qapp.processEvents()

    assert not page._pipeline.isVisible()
    assert not page._logs.isVisible()
    assert not hasattr(page, "_bit_stream")

    page.resize(1100, 700)
    qapp.processEvents()
    assert page._pipeline.isVisible()
    assert page._logs.isVisible()
    page.close()


def test_tx_start_requires_selected_file_and_connected_hardware(qapp):
    widget = FileDetailsWidget()
    state = SimpleNamespace(
        filename="",
        file_size_bytes=0,
        total_chunks=0,
        status_text="Idle",
        elapsed_time="",
        estimated_time="",
        serial_connected=True,
    )
    widget.refresh(state)
    assert not widget.start_btn.isEnabled()
    assert widget.select_btn.height() >= 30
    assert widget.start_btn.height() >= 30

    state.filename = "measured-data.bin"
    widget.refresh(state)
    assert widget.start_btn.isEnabled()
    widget.close()

def test_rx_export_updates_existing_history_after_method2_comparison(qapp: QApplication, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from gui_dev_v3.models import TransferStatus as RXTransferStatus

    monkeypatch.setattr(export_page_module, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(export_page_module, "HISTORY_PATH", tmp_path / "history.json")
    transfer = SimpleNamespace(
        tid=77,
        status=RXTransferStatus.COMPLETE,
        filename="received.bin",
        time_label="12:00:00",
        size_bytes=8,
        total_chunks=1,
        received_chunks=1,
    )
    state = SimpleNamespace(transfer=transfer, get_method2_comparison=lambda: None)
    page = ExportPage()
    page.refresh(state)
    assert page._history_data[0]["ber"] == "N/A"
    assert page._history_data[0]["ber_method"] is None

    state.get_method2_comparison = lambda: {
        "strict_ber": 0.0125,
        "overlap_ber": 0.0,
    }
    page.refresh(state)
    assert page._history_data[0]["ber"] == 0.0125
    assert page._history_data[0]["ber_method"] == "method2_reference_file"
    page.close()

def test_tx_batch_start_requires_connected_hardware_and_queued_files(qapp):
    from types import SimpleNamespace

    state = SimpleNamespace(
        serial_connected=False,
        transmission_queue=[],
        session_history=[],
    )
    page = TransmitPage(state)
    assert not page.start_btn.isEnabled()

    state.serial_connected = True
    state.transmission_queue = [{
        "filename": "queued.bin",
        "size": "1 KiB",
        "status": "Queued",
    }]
    page.refresh(state)
    assert page.start_btn.isEnabled()

    state.serial_connected = False
    page.refresh(state)
    assert not page.start_btn.isEnabled()
    page.close()

def test_rx_export_reads_legacy_history_without_deleting_it(qapp, monkeypatch, tmp_path):
    legacy_path = tmp_path / "legacy-history.json"
    original = [{
        "tid": 12,
        "filename": "previous.bin",
        "status": "Complete",
        "time_label": "10:00:00",
        "size_bytes": 4,
        "total_chunks": 1,
        "received_chunks": 1,
        "ber": "N/A",
        "ber_method": None,
    }]
    import json
    raw = json.dumps(original)
    legacy_path.write_text(raw, encoding="utf-8")
    current_path = tmp_path / "app-data" / "transfer_history.json"
    monkeypatch.setattr(export_page_module, "HISTORY_DIR", current_path.parent)
    monkeypatch.setattr(export_page_module, "HISTORY_PATH", current_path)
    monkeypatch.setattr(export_page_module, "LEGACY_HISTORY_PATH", legacy_path)

    page = ExportPage()
    assert page._history_data == original
    assert not current_path.exists()
    assert legacy_path.read_text(encoding="utf-8") == raw
    page.close()

def test_offline_dashboard_metrics_are_unavailable_not_zero_or_perfect(qapp):
    tx_panel = CurrentSessionWidget()
    tx_panel.refresh(SimpleNamespace(session_history=[]))
    assert tx_panel.row_sent.val.text() == "0"
    assert tx_panel.row_success.val.text() == "—"

    rx_page = RXDashboardPage(RXAppState())
    assert rx_page._signal_mon.pvo_row.val.text() == "—"
    assert rx_page._signal_mon.vref_row.val.text() == "—"
    assert rx_page._perf.margin_row.val.text() == "—"
    assert rx_page._file_info.pct_row.val.text() == "—"
    tx_panel.close()
    rx_page.close()

def test_rx_export_does_not_treat_legacy_ber_label_as_method2_proof(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(export_page_module, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(export_page_module, "HISTORY_PATH", tmp_path / "history.json")
    page = ExportPage()
    page._history_data = [{
        "tid": 5,
        "filename": "old.bin",
        "status": "Complete",
        "time_label": "09:00:00",
        "size_bytes": 8,
        "total_chunks": 1,
        "received_chunks": 1,
        "ber": 0.0,
        "ber_method": "method2",
    }]
    page._populate_table()
    assert page.table.item(0, 6).text() == "N/A"
    page.close()

def test_rx_export_does_not_overwrite_corrupt_legacy_history(qapp, monkeypatch, tmp_path):
    legacy_path = tmp_path / "legacy-history.json"
    original = "{ damaged legacy history"
    legacy_path.write_text(original, encoding="utf-8")
    current_path = tmp_path / "app-data" / "transfer_history.json"
    monkeypatch.setattr(export_page_module, "HISTORY_DIR", current_path.parent)
    monkeypatch.setattr(export_page_module, "HISTORY_PATH", current_path)
    monkeypatch.setattr(export_page_module, "LEGACY_HISTORY_PATH", legacy_path)

    page = ExportPage()
    assert page._history_corrupt
    page._history_data.append({"tid": 88, "filename": "must-not-replace.bin"})
    page._save_history()
    assert not current_path.exists()
    assert legacy_path.read_text(encoding="utf-8") == original
    page.close()



def test_window_minimum_height_respects_scaled_logical_work_area():
    from gui_dev_v3.app import _minimum_window_dimensions

    # A 1024x700 physical display at 150% scaling is roughly 683x466 logical
    # pixels before taskbars/window decorations.
    min_width, min_height = _minimum_window_dimensions(683, 466)

    assert min_width == 640
    assert min_height == 418
    assert min_width <= 683 - 32
    assert min_height <= 466 - 48



def test_tx_file_manager_crc16_reads_large_files_incrementally(qapp, tmp_path, monkeypatch):
    import binascii

    from gui_dev_v3.tx.file_manager_page import FileManagerPage

    payload = bytes(range(256)) * 1024
    source = tmp_path / "large-payload.bin"
    source.write_bytes(payload)

    page = FileManagerPage()
    actual = page._compute_crc16(str(source))
    expected = f"0x{binascii.crc_hqx(payload, 0xFFFF):04X}"

    assert actual == expected

    # The file manager must read in bounded blocks rather than a single
    # unbounded read, even when the file is larger than one block.
    original_open = open
    read_sizes = []

    class TrackingReader:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __enter__(self):
            self._wrapped.__enter__()
            return self

        def __exit__(self, *args):
            return self._wrapped.__exit__(*args)

        def read(self, size=-1):
            read_sizes.append(size)
            return self._wrapped.read(size)

    def tracking_open(path, mode="r", *args, **kwargs):
        wrapped = original_open(path, mode, *args, **kwargs)
        if str(path) == str(source) and mode == "rb":
            return TrackingReader(wrapped)
        return wrapped

    monkeypatch.setattr("builtins.open", tracking_open)
    assert page._compute_crc16(str(source)) == expected
    assert read_sizes and all(0 < size <= 64 * 1024 for size in read_sizes)



def test_rx_dashboard_does_not_present_an_uncalibrated_lux_estimate(qapp):
    from gui_dev_v3.app_state import RXAppState
    from gui_dev_v3.rx.dashboard import RXDashboardPage

    page = RXDashboardPage(RXAppState())
    from PySide6.QtWidgets import QLabel

    labels = [label.text() for label in page.findChildren(QLabel)]

    assert not any("lux" in label.lower() or "light estimate" in label.lower() for label in labels)



def test_directory_setting_shows_path_from_start_and_preserves_full_value(qapp):
    from gui_dev_v3.settings import DirectorySetting

    full_path = "/home/test-user/.local/share/OpenVLC/received"
    setting = DirectorySetting(full_path)
    setting.resize(260, 40)
    setting.show()
    qapp.processEvents()

    assert setting.text() == full_path
    assert setting.edit.text() == full_path
    assert setting.edit.cursorPosition() == 0
    assert setting.edit.toolTip() == full_path
    setting.close()



def test_rx_dashboard_reports_connection_state_not_decoder_lock(qapp):
    state = RXAppState()
    page = RXDashboardPage(state)

    assert page._receiver_state.connection_row.val.text() == "DISCONNECTED"
    assert page._receiver_state.protocol_row.val.text() == "—"

    # RXAppState initializes from the runtime status file. Reset the
    # transfer snapshot here so this dashboard-only assertion is independent
    # of status records left by earlier tests on the same CI worker.
    from gui_dev_v3.data.session import build_empty_session

    state.session = build_empty_session()
    state.transfer = state.session.latest_transfer
    state.serial_connected = True
    page.refresh(state)
    assert page._receiver_state.connection_row.val.text() == "READY"
    assert page._receiver_state.protocol_row.val.text() == "4B5B / OOK"
    assert page._receiver_state.connection_row.val.text() != "LOCKED"
    page.close()



def test_session_inspector_replays_telemetry_and_labels_legacy_threshold_samples(qapp):
    from gui_dev_v3.models import SessionCapture
    from gui_dev_v3.rx.export_page import SessionInspectorCard

    inspector = SessionInspectorCard()
    capture = SessionCapture(
        tid=91,
        timestamp="2026-11-13 12:00:00",
        filename="telemetry.bin",
        ber=None,
        crc_status="PASS",
        throughput_kbps=0.0,
        analog_time=[0.0, 1.0, 2.0],
        pvo_samples=[1.0, 1.1, 1.2],
        vref_samples=[0.7, 0.7, 0.7],
        margin_samples=[0.3, 0.4, 0.5],
        ook_bits=[1, 0, 1, 0],
        protocol_events=[],
        ber_method="unavailable",
    )
    inspector.show_capture(capture, {"status": "Complete", "size_bytes": 3})

    assert len(inspector.signal_waveform._buffer) == 3
    assert "Legacy threshold-state samples" in inspector.ook_data_text.toPlainText()
    assert "NOT decoded symbol-rate OOK bits" in inspector.ook_data_text.toPlainText()
    inspector.close()



def test_export_page_path_and_empty_inspector_are_honest(qapp, monkeypatch, tmp_path):
    from gui_dev_v3.rx import export_page

    history_dir = tmp_path / "history"
    monkeypatch.setattr(export_page, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(export_page, "HISTORY_PATH", history_dir / "transfer_history.json")
    monkeypatch.setattr(
        export_page, "LEGACY_HISTORY_PATH", tmp_path / "legacy" / "transfer_history.json"
    )

    page = export_page.ExportPage()
    full_path = page._folder_edit.text()
    assert page._folder_edit.cursorPosition() == 0
    assert page._folder_edit.toolTip() == full_path

    inspector = page.inspector_card
    inspector.show_empty()
    description = inspector.empty_desc.text()
    assert "PVo/Vref/margin telemetry" in description
    assert "decoded bitstream" not in description.lower()
    page.close()


@pytest.mark.parametrize(
    ("available_width", "available_height", "expected"),
    [
        (1920, 1080, (640, 480)),
        (1366, 768, (640, 480)),
        (800, 600, (640, 480)),
        (680, 500, (640, 452)),
        (500, 400, (468, 352)),
    ],
)
def test_minimum_window_dimensions_allow_responsive_laptop_sizes(
    available_width: int,
    available_height: int,
    expected: tuple[int, int],
) -> None:
    assert _minimum_window_dimensions(available_width, available_height) == expected



def test_main_window_close_cleans_up_both_console_backends(qapp, monkeypatch):
    window = VLCMainWindow()
    cleaned = []
    window._rx_shell = SimpleNamespace(cleanup=lambda: cleaned.append("rx"))
    window._tx_shell = SimpleNamespace(cleanup=lambda: cleaned.append("tx"))
    base_close = []
    monkeypatch.setattr(
        _BaseWindow,
        "closeEvent",
        lambda _self, event: base_close.append(event),
    )
    event = object()

    window.closeEvent(event)

    assert cleaned == ["rx", "tx"]
    assert base_close == [event]


def test_main_window_close_continues_when_one_console_cleanup_fails(qapp, monkeypatch):
    window = VLCMainWindow()
    cleaned = []

    def fail_cleanup():
        raise RuntimeError("simulated RX shutdown failure")

    window._rx_shell = SimpleNamespace(cleanup=fail_cleanup)
    window._tx_shell = SimpleNamespace(cleanup=lambda: cleaned.append("tx"))
    base_close = []
    monkeypatch.setattr(
        _BaseWindow,
        "closeEvent",
        lambda _self, event: base_close.append(event),
    )
    event = object()

    window.closeEvent(event)

    assert cleaned == ["tx"]
    assert base_close == [event]


def test_receive_page_reports_interrupted_for_real_transfer_after_disconnect(qapp):
    from dataclasses import replace
    from gui_dev_v3.data.session import build_empty_session
    from gui_dev_v3.models import TransferStatus

    state = RXAppState()
    empty = build_empty_session()
    partial_transfer = replace(
        empty.latest_transfer,
        tid=42,
        filename="partial.bin",
        status=TransferStatus.INCOMPLETE,
        size_bytes=100,
        total_chunks=4,
        received_chunks=2,
    )
    state.session = replace(
        empty,
        progress_percent=50,
        latest_transfer=partial_transfer,
    )
    state.transfer = state.session.latest_transfer
    state.serial_connected = False

    page = ReceivePage()
    page.refresh(state)

    assert state.is_receiving is True
    assert page.status_badge.text() == "● INTERRUPTED"
    page.close()


def test_receive_page_keeps_empty_offline_state_idle(qapp):
    from gui_dev_v3.data.session import build_empty_session

    state = RXAppState()
    state.session = build_empty_session()
    state.transfer = state.session.latest_transfer
    state.serial_connected = False

    page = ReceivePage()
    page.refresh(state)

    assert state.is_receiving is False
    assert page.status_badge.text() == "○ IDLE"
    page.close()


def test_tx_queue_header_uses_compact_label_at_laptop_size(qapp):
    page = TransmitPage()
    page.resize(680, 500)
    page.show()
    qapp.processEvents()

    assert page.queue_table.horizontalHeaderItem(0).text() == "File"

    page.resize(1024, 700)
    qapp.processEvents()
    assert page.queue_table.horizontalHeaderItem(0).text() == "Filename"
    page.close()


def test_ber_mismatch_headers_fit_compact_layout(qapp):
    page = BERAnalyzerPage()
    page.resize(680, 500)
    page.show()
    qapp.processEvents()

    compact_headers = [
        page.mismatch_table.horizontalHeaderItem(i).text()
        for i in range(page.mismatch_table.columnCount())
    ]
    assert compact_headers == ["Offset", "Expected", "Received", "Errors"]

    page.resize(1024, 700)
    qapp.processEvents()
    full_headers = [
        page.mismatch_table.horizontalHeaderItem(i).text()
        for i in range(page.mismatch_table.columnCount())
    ]
    assert full_headers == ["Offset", "Expected (Hex)", "Received (Hex)", "Bit Errors"]
    page.close()
