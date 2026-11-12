"""Offscreen geometry checks for the responsive TX/RX application shell."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from gui_dev_v3.app import VLCMainWindow


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


def test_tx_dashboard_uses_real_profile_instead_of_synthetic_bitstream(qapp):
    from types import SimpleNamespace

    from gui_dev_v3.tx.dashboard import CurrentSessionWidget, TXConfigurationWidget

    state = SimpleNamespace(
        serial_connected=False,
        encoding="4B5B",
        modulation="NRZ / OOK",
        symbol_rate="15,000 sym/s",
        led_pin=5,
        tx_power="100 %",
        pre_emphasis="Disabled",
        session_history=[],
    )

    profile = TXConfigurationWidget()
    profile.refresh(state)
    assert profile.row_gpio.val.text() == "GPIO 5"
    assert "disconnected" in profile._status.text().lower()
    assert not hasattr(profile, "canvas")

    session = CurrentSessionWidget()
    session.refresh(state)
    assert session.row_success.val.text() == "—"


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
