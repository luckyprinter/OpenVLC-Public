"""Capture TX/RX pages at representative laptop window sizes for visual review."""
from __future__ import annotations

import os
import re
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from gui_dev_v3.app import VLCMainWindow, load_bundled_fonts


SCALE_VALUE = float(os.environ.get("OPENVLC_SCREENSHOT_SCALE", "1.0"))
if SCALE_VALUE <= 0:
    raise ValueError("OPENVLC_SCREENSHOT_SCALE must be greater than zero")
SCALE_LABEL = str(SCALE_VALUE).replace(".", "p")
OUTPUT_DIR = Path("ui-screenshots") / f"scale-{SCALE_LABEL}"
WINDOW_SIZES = ((1366, 768), (1280, 720), (1024, 700))
PAGES = {
    "tx": {"dashboard": 0, "transmit": 1, "file_manager": 2, "logs": 3, "settings": 4},
    "rx": {"dashboard": 0, "receive": 1, "inspect": 2, "signal": 3, "ber_analyzer": 4, "study_data": 5, "settings": 6},
}


def validate_page_geometry(mode: str, page_name: str, shell, width: int, height: int) -> None:
    """Catch clipped TX controls and table headers before screenshot capture."""
    if mode == "tx" and page_name == "dashboard":
        page = shell._page_widgets.get("dashboard")
        file_panel = getattr(page, "_file_details", None)
        body = getattr(file_panel, "body", None)
        if body is not None:
            # Card.body is already a QVBoxLayout; activate it before measuring.
            layout = body
            layout.activate()
            for index in range(layout.count()):
                item = layout.itemAt(index)
                widget = item.widget()
                if widget is not None and widget.isVisible():
                    # Card.body is a QLayout, not a QWidget. Compare the child
                    # bounds and layout content area in the owning card's
                    # coordinate system so the check works across Qt platforms.
                    card = body.parentWidget()
                    child_top = widget.mapTo(card, QPoint(0, 0)).y()
                    child_bottom = child_top + widget.height()
                    content_top = body.geometry().top()
                    content_bottom = body.geometry().bottom()
                    if child_top < content_top - 1 or child_bottom > content_bottom + 1:
                        raise RuntimeError(
                            f"TX file-details control is clipped at {width}x{height}: "
                            f"{widget.objectName() or widget.__class__.__name__} "
                            f"(bottom={child_bottom}, content_bottom={content_bottom})"
                        )

    if mode == "tx":
        page = shell._page_widgets.get(page_name)
        table_names = {
            "transmit": ("queue_table", "history_table"),
            "file_manager": ("file_table",),
            "logs": ("logs_table",),
        }.get(page_name, ())
        for table_name in table_names:
            table = getattr(page, table_name, None)
            if table is None:
                continue
            header = table.horizontalHeader()
            for column in range(table.columnCount()):
                right = header.sectionViewportPosition(column) + header.sectionSize(column)
                if right > table.viewport().width() + 2:
                    can_scroll = (
                        table.horizontalScrollBarPolicy()
                        != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                        and table.horizontalScrollBar().maximum() > 0
                    )
                    if not can_scroll:
                        raise RuntimeError(
                            f"TX {page_name} {table_name} column {column} exceeds its viewport "
                            f"at {width}x{height} without a usable horizontal scrollbar"
                        )


def _capture_nested_views(window, app, mode: str, page_name: str, shell, width: int, height: int) -> None:
    """Capture important inner tabs/settings sections that a page screenshot misses."""
    if mode == "rx" and page_name == "study_data":
        page = shell._page_widgets.get("study_data")
        tabs = getattr(page, "tabs", None)
        if tabs is None:
            raise RuntimeError("RX Study & Data page is missing its inner tabs")
        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            app.processEvents()
            tab_widget = tabs.widget(index)
            content = tab_widget.widget() if hasattr(tab_widget, "widget") else tab_widget
            if content is not None and hasattr(content, "_compact_layout"):
                expected_compact = content.width() < 900 or content.height() < 620
                if content._compact_layout != expected_compact:
                    raise RuntimeError(
                        f"RX Study & Data {tabs.tabText(index)} did not reflow at "
                        f"{width}x{height}: content={content.width()}x{content.height()}"
                    )
            slug = re.sub(r"[^a-z0-9]+", "_", tabs.tabText(index).lower()).strip("_")
            target = OUTPUT_DIR / f"rx_study_data_{slug}_{width}x{height}.png"
            if not window.grab().save(str(target), "PNG"):
                raise RuntimeError(f"Could not save screenshot: {target}")
            print(f"Captured {target}", flush=True)

    if page_name == "settings":
        page = shell._page_widgets.get("settings")
        if hasattr(page, "widget"):
            page = page.widget()
        nav = getattr(page, "_nav_list", None)
        if nav is None:
            return
        for index in range(nav.count()):
            item = nav.item(index)
            if item is None or item.isHidden():
                continue
            nav.setCurrentRow(index)
            app.processEvents()
            slug = re.sub(r"[^a-z0-9]+", "_", item.text().lower()).strip("_")
            target = OUTPUT_DIR / f"{mode}_settings_{slug}_{width}x{height}.png"
            if not window.grab().save(str(target), "PNG"):
                raise RuntimeError(f"Could not save screenshot: {target}")
            print(f"Captured {target}", flush=True)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    load_bundled_fonts()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for mode, pages in PAGES.items():
        window = VLCMainWindow()
        window.show()
        window.launch_mode(mode)
        app.processEvents()

        shell = window._tx_shell if mode == "tx" else window._rx_shell
        if shell is None:
            raise RuntimeError(f"Could not create {mode.upper()} console")

        for width, height in WINDOW_SIZES:
            # The listed sizes describe physical display pixels. Qt lays out
            # widgets in device-independent pixels, so divide by the active
            # scale factor to model the usable workspace on a real display.
            logical_width = max(1, round(width / SCALE_VALUE))
            logical_height = max(1, round(height / SCALE_VALUE))
            window.resize(logical_width, logical_height)
            app.processEvents()

            expected_sidebar = 72 if logical_width < 1120 else 224
            if shell.sidebar.width() != expected_sidebar:
                raise RuntimeError(
                    f"{mode.upper()} sidebar width {shell.sidebar.width()} "
                    f"does not match expected {expected_sidebar} at {width}x{height}"
                )
            if shell.sidebar.geometry().right() >= shell._main_area.geometry().left():
                raise RuntimeError(f"{mode.upper()} sidebar overlaps the workspace at {width}x{height}")
            if shell.pages.width() <= 0 or shell.pages.height() <= 0:
                raise RuntimeError(f"{mode.upper()} page area has no usable size at {width}x{height}")

            for page_name, index in pages.items():
                if index >= shell.nav.count():
                    raise RuntimeError(f"Missing {mode.upper()} navigation page: {page_name}")
                shell.nav.setCurrentRow(index)
                app.processEvents()
                shell._refresh_current_page()
                app.processEvents()
                validate_page_geometry(mode, page_name, shell, width, height)

                filename = f"{mode}_{page_name}_{width}x{height}.png"
                target = OUTPUT_DIR / filename
                if not window.grab().save(str(target), "PNG"):
                    raise RuntimeError(f"Could not save screenshot: {target}")
                print(f"Captured {target}", flush=True)
                _capture_nested_views(window, app, mode, page_name, shell, width, height)

        window.return_to_launcher()
        window.close()
        app.processEvents()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
