import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest


APPLICATION_SOURCE = Path(__file__).resolve().parents[1]


def run_application(code, tmp_path, *arguments):
    return subprocess.run(
        [sys.executable, "-c", dedent(code), *arguments],
        cwd=APPLICATION_SOURCE,
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "VLC_DATA_DIR": str(tmp_path / "data"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "APPDATA": str(tmp_path / "config"),
        },
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_bundled_fonts_register_expected_qt_families(tmp_path):
    result = run_application(
        """
        from PySide6.QtWidgets import QApplication
        from gui_dev_v3.app import load_bundled_fonts

        app = QApplication([])
        families = load_bundled_fonts()
        expected = {"Inter", "Fira Code", "JetBrains Mono", "Plus Jakarta Sans", "Space Mono"}
        assert expected <= families, families
        """,
        tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("stage", ["tx", "rx", "cleanup"])
def test_application_smoke_exits_nonzero_if_required_stage_fails(tmp_path, stage):
    result = run_application(
        """
        import sys
        from gui_dev_v3 import app

        stage = sys.argv.pop()
        launch_mode = app.VLCMainWindow.launch_mode

        def launch_with_failure(window, mode):
            if mode == stage:
                raise RuntimeError(f"injected {mode} launch failure")
            launch_mode(window, mode)

        def cleanup_with_failure(shell):
            raise RuntimeError("injected TX cleanup failure")

        app.VLCMainWindow.launch_mode = launch_with_failure
        if stage == "cleanup":
            app.TXShell.cleanup = cleanup_with_failure

        raise SystemExit(app.main())
        """,
        tmp_path,
        "--smoke-test",
        stage,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "Smoke test passed" not in output
    assert "injected" in output
