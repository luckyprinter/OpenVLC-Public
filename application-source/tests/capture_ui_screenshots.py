"""Capture TX/RX pages at representative laptop window sizes for visual review."""
from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from gui_dev_v3.app import VLCMainWindow, load_bundled_fonts


SCALE_LABEL = os.environ.get("OPENVLC_SCREENSHOT_SCALE", "1.0").replace(".", "p")
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
            # The primary file controls must retain their full height and a
            # small bottom inset at compact laptop resolutions.
            layout = body
            layout.activate()
            if not page._state.serial_connected and file_panel.start_btn.isEnabled():
                raise RuntimeError(f"TX Start must be disabled while hardware is disconnected at {width}x{height}")
            for control_name in ("select_btn", "start_btn"):
                control = getattr(file_panel, control_name, None)
                if control is None or not control.isVisible():
                    raise RuntimeError(f"TX dashboard is missing visible {control_name} at {width}x{height}")
                bottom = control.mapTo(file_panel, QPoint(0, control.height())).y()
                if control.height() < 30 or bottom > file_panel.height() - 4:
                    raise RuntimeError(
                        f"TX dashboard {control_name} is clipped or compressed at {width}x{height}: "
                        f"height={control.height()}, bottom={bottom}, card_height={file_panel.height()}"
                    )
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

    if mode == "tx" and page_name == "dashboard":
        page = shell._page_widgets.get("dashboard")
        profile = getattr(page, "_link_profile", None)
        status = getattr(profile, "_status", None) if profile is not None else None
        if status is None or status.height() < 12:
            raise RuntimeError(f"TX link-profile status is clipped at {width}x{height}")
        if status.fontMetrics().horizontalAdvance(status.text()) > status.width() + 2:
            raise RuntimeError(f"TX link-profile status text overflows at {width}x{height}")
        for row_name in ("row_protocol", "row_rate", "row_gpio", "row_drive", "row_driver", "row_gap"):
            row = getattr(profile, row_name, None)
            if row is None:
                raise RuntimeError(f"TX link-profile row {row_name} is missing at {width}x{height}")
            for label in (row.lbl, row.val):
                if label.fontMetrics().horizontalAdvance(label.text()) > label.width() + 2:
                    raise RuntimeError(f"TX link-profile text overflows at {width}x{height}: {label.text()}")

        pipeline = getattr(page, "_pipeline", None)
        if pipeline is None or pipeline.height() < 112:
            raise RuntimeError(f"TX pipeline panel is too short at {width}x{height}")
        for stage_name in ("stage_file", "stage_chunk", "stage_enc", "stage_mod", "stage_esp", "stage_optical"):
            stage = getattr(pipeline, stage_name, None)
            desc = getattr(stage, "desc_lbl", None) if stage is not None else None
            if stage is None or stage.height() < 38 or desc is None or desc.height() < 12:
                raise RuntimeError(f"TX pipeline stage {stage_name} is clipped at {width}x{height}")

    if mode == "rx" and page_name == "dashboard":
        page = shell._page_widgets.get("dashboard")
        file_panel = getattr(page, "_file_info", None)
        if file_panel is None or file_panel.height() < 180:
            raise RuntimeError(f"RX received-file panel is too short at {width}x{height}")
        for row_name in ("filename_row", "filesize_row", "received_size_row", "pct_row", "progress_bar"):
            row = getattr(file_panel, row_name, None)
            if row is None or not row.isVisible():
                raise RuntimeError(f"RX received-file row {row_name} is missing at {width}x{height}")
            bottom = row.mapTo(file_panel, QPoint(0, row.height())).y()
            if bottom > file_panel.height() - 4:
                raise RuntimeError(
                    f"RX received-file row {row_name} is clipped at {width}x{height}: "
                    f"bottom={bottom}, card_height={file_panel.height()}"
                )

    if mode == "tx" and page_name == "transmit":
        page = shell._page_widgets.get("transmit")
        if page is not None and not page.state.serial_connected and page.start_btn.isEnabled():
            raise RuntimeError(f"TX batch start must be disabled while hardware is disconnected at {width}x{height}")

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
                    raise RuntimeError(
                        f"TX {page_name} {table_name} column {column} exceeds its viewport "
                        f"at {width}x{height}; table headers must fit or expose horizontal scrolling"
                    )


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
            window.resize(width, height)
            app.processEvents()

            expected_sidebar = 72 if width < 1120 else 224
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

        window.return_to_launcher()
        window.close()
        app.processEvents()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
