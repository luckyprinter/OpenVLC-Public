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


def test_tx_dashboard_uses_saved_profile_instead_of_synthetic_bitstream(qapp):
    from types import SimpleNamespace

    from gui_dev_v3.tx.dashboard import CurrentSessionWidget, FileDetailsWidget, TXConfigurationWidget

    class FakeSettingsManager:
        values = {
            "link/symbol_hz": 12000,
            "link/cal_intensity_pct": 65,
            "link/active_low": False,
            "link/idle_on": False,
            "link/frame_gap_ms": 2,
        }

        def get(self, key, default=None):
            return self.values.get(key, default)

    state = SimpleNamespace(
        serial_connected=False,
        filename="No file",
        file_size_bytes=0,
        total_chunks=0,
        status_text="Offline — no hardware",
        estimated_time="00:00:00",
        elapsed_time="00:00:00",
        session_history=[],
    )

    profile = TXConfigurationWidget(settings_manager=FakeSettingsManager())
    profile.refresh(state)
    assert profile.row_protocol.val.text() == "4B5B / NRZ-OOK"
    assert profile.row_rate.val.text() == "12,000 sym/s"
    assert profile.row_gpio.val.text() == "GPIO 5"
    assert profile.row_drive.val.text() == "65 %"
    assert profile.row_driver.val.text() == "Active-high · Idle off"
    assert profile.row_gap.val.text() == "2 ms"
    assert "disconnected" in profile._status.text().lower()
    assert not hasattr(profile, "canvas")

    session = CurrentSessionWidget()
    session.refresh(state)
    assert session.row_success.val.text() == "—"

    file_details = FileDetailsWidget()
    file_details.refresh(state)
    assert not file_details.start_btn.isEnabled()


def test_rx_dashboard_does_not_present_offline_defaults_as_measurements(qapp):
    from types import SimpleNamespace

    from gui_dev_v3.rx.dashboard import _PerformanceMetricsPanel, _SignalMonitorPanel

    state = SimpleNamespace(
        serial_connected=False,
        signal=SimpleNamespace(
            ber=0.0,
            strict_ber=0.0,
            crc_status="",
            margin=0.0,
            data_rate=0.0,
            pvo=0.0,
            vref=0.0,
            adc_vref=0.0,
            lux=0,
        ),
        transfer=SimpleNamespace(total_chunks=0, received_chunks=0),
    )

    performance = _PerformanceMetricsPanel(state)
    performance.refresh(state)
    assert performance.ber_row.val.text() == "—"
    assert performance.strict_ber_row.val.text() == "—"
    assert performance.margin_row.val.text() == "—"
    assert performance.data_rate_row.val.text() == "—"

    signal = _SignalMonitorPanel(state)
    signal.refresh(state)
    assert signal.pvo_row.val.text() == "—"
    assert signal.vref_row.val.text() == "—"
    assert signal.adc_vref_row.val.text() == "—"
    assert signal.lux_row.val.text() == "—"


def test_rx_signal_page_uses_unavailable_markers_when_disconnected(qapp):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QLabel
    from gui_dev_v3.rx.signal_page import SignalMonitorPage

    signal = SimpleNamespace(
        pvo=0.0,
        vref=0.0,
        margin=0.0,
        target_margin=0.365,
        data_rate=0.0,
        ber=0.0,
        strict_ber=0.0,
        crc_status="",
        lux=0,
        adc_vref=0.0,
    )
    quality = SimpleNamespace(crc_status="", strict_ber=0.0, bit_errors=0, compared_bytes=0)
    transfer = SimpleNamespace(
        quality=quality,
        tid=0,
        total_chunks=0,
        received_chunks=0,
        filename="",
        time_label="",
        size_bytes=0,
    )
    state = SimpleNamespace(serial_connected=False, signal=signal, transfer=transfer)

    page = SignalMonitorPage(state)
    try:
        page.refresh(state)
        # Signal MetricCard is a custom-painted QWidget, not a QLabel
        # container. Assert its public display state rather than searching
        # for an internal child widget that intentionally does not exist.
        for metric in (page._metric_pvo, page._metric_vref, page._metric_margin):
            assert metric._value_text == "—"
    finally:
        page.shutdown()


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
