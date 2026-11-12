"""Offscreen geometry checks for the responsive TX/RX application shell."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from gui_dev_v3.app import VLCMainWindow
from gui_dev_v3.app_state import RXAppState
from gui_dev_v3.rx.dashboard import RXDashboardPage
from gui_dev_v3.settings import SettingsContainer, ThemePickerGrid


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
    settings = SettingsContainer([("General", page)])
    settings.resize(700, 500)
    settings.show()
    qapp.processEvents()

    assert settings._nav_list.focusPolicy().name == "StrongFocus"
    assert settings._nav_list.accessibleName() == "Settings sections"
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
