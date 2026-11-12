"""Offscreen geometry checks for the responsive TX/RX application shell."""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QBoxLayout, QWidget

from gui_dev_v3.app import VLCMainWindow
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
from gui_dev_v3.tx.dashboard import FileDetailsWidget, TXDashboardPage
from gui_dev_v3.tx_app_state import TXAppState
from gui_dev_v3.tx.placeholders import TransmitPage
from gui_dev_v3.tx.file_manager_page import FileManagerPage


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
    assert not dashboard._bit_decode.isVisible()
    assert not dashboard._activity_log.isVisible()

    dashboard.resize(1100, 700)
    qapp.processEvents()
    assert not dashboard._compact_layout
    assert dashboard._perf.isVisible()
    assert dashboard._signal_mon.isVisible()
    assert dashboard._bit_decode.isVisible()
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
    assert settings._nav_list.accessibleName() == "Settings sections"
    assert settings._nav_list.wordWrap()
    assert settings._nav_list.item(0).text() == "General & Display"
    wrapper_layout = settings._page_wrappers[0].layout()
    margins = wrapper_layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        10, 12, 10, 12
    )

    settings.resize(1000, 700)
    qapp.processEvents()
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
    page = SignalMonitorPage(RXAppState())
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
    page.close()


def test_rx_receive_actions_stack_on_compact_display(qapp):
    page = ReceivePage()
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
    state = SimpleNamespace(transfer=transfer, is_receiving=True, progress_percent=50)
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

    state.filename = "measured-data.bin"
    widget.refresh(state)
    assert widget.start_btn.isEnabled()
    widget.close()

def test_rx_export_updates_existing_history_after_method2_comparison(qapp, monkeypatch, tmp_path):
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
