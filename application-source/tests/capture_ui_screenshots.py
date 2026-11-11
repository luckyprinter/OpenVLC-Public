"""Capture TX/RX pages at representative laptop window sizes for visual review."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gui_dev_v3.app import VLCMainWindow, load_bundled_fonts


OUTPUT_DIR = Path("ui-screenshots")
WINDOW_SIZES = ((1366, 768), (1280, 720), (1024, 700))
PAGES = {
    "tx": {"dashboard": 0, "transmit": 1, "settings": 4},
    "rx": {"dashboard": 0, "receive": 1, "signal": 3, "settings": 6},
}


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

            for page_name, index in pages.items():
                if index >= shell.nav.count():
                    raise RuntimeError(f"Missing {mode.upper()} navigation page: {page_name}")
                shell.nav.setCurrentRow(index)
                app.processEvents()
                shell._refresh_current_page()
                app.processEvents()

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
