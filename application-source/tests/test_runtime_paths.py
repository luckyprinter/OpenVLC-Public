from pathlib import Path

from gui_dev_v3.runtime_paths import resolve_user_data_dir


def test_windows_runtime_data_uses_local_app_data():
    result = resolve_user_data_dir(
        platform="win32",
        environ={"LOCALAPPDATA": r"C:\Users\Tester\AppData\Local"},
        home=Path(r"C:\Users\Tester"),
    )
    assert result == Path(r"C:\Users\Tester\AppData\Local") / "OpenVLC"


def test_macos_runtime_data_uses_application_support():
    result = resolve_user_data_dir(
        platform="darwin",
        environ={},
        home=Path("/Users/tester"),
    )
    assert result == Path("/Users/tester/Library/Application Support/OpenVLC")


def test_linux_runtime_data_honors_xdg_data_home():
    result = resolve_user_data_dir(
        platform="linux",
        environ={"XDG_DATA_HOME": "/mnt/user-data"},
        home=Path("/home/tester"),
    )
    assert result == Path("/mnt/user-data/OpenVLC")


def test_linux_runtime_data_uses_xdg_default():
    result = resolve_user_data_dir(
        platform="linux",
        environ={},
        home=Path("/home/tester"),
    )
    assert result == Path("/home/tester/.local/share/OpenVLC")

def test_runtime_data_dir_preserves_explicit_user_override(monkeypatch, tmp_path):
    from gui_dev_v3.runtime_paths import configure_runtime_data_dir

    explicit = tmp_path / "custom-openvlc-data"
    monkeypatch.setenv("VLC_DATA_DIR", str(explicit))
    assert configure_runtime_data_dir() == explicit
    assert __import__("os").environ["VLC_DATA_DIR"] == str(explicit)


def test_runtime_status_and_rx_logs_use_application_data(monkeypatch, tmp_path):
    monkeypatch.setenv("VLC_DATA_DIR", str(tmp_path))

    from gui_dev_v3.data import records, status

    assert status._resolve_state_dir() == tmp_path / "state"
    assert records._resolve_log_dir() == tmp_path / "logs" / "rx"
    assert "vlc_beta" not in str(status._resolve_state_dir())
    assert "vlc_beta" not in str(records._resolve_log_dir())


def test_serial_status_writer_uses_application_status_store(monkeypatch):
    from gui_dev_v3.data import status as status_module
    from gui_dev_v3.serial import session as session_module

    captured = {}

    def capture(role, stage, detail="", percent=None, state="idle", **extra):
        captured.update(
            role=role,
            stage=stage,
            detail=detail,
            percent=percent,
            state=state,
            extra=extra,
        )

    monkeypatch.setattr(status_module, "write_status", capture)
    session_module.write_status(
        "rx",
        {
            "role": "rx",
            "stage": "Connected",
            "detail": "Serial link ready",
            "state": "active",
            "updated_at": 123.0,
            "percent": 25,
            "port": "/dev/ttyUSB0",
        },
    )

    assert captured == {
        "role": "rx",
        "stage": "Connected",
        "detail": "Serial link ready",
        "percent": 25,
        "state": "active",
        "extra": {"port": "/dev/ttyUSB0"},
    }


def test_logger_uses_writable_application_data_directory(monkeypatch, tmp_path):
    from pathlib import Path
    from gui_dev_v3.logger import get_base_dir

    monkeypatch.setenv("VLC_DATA_DIR", str(tmp_path))

    assert Path(get_base_dir()) == tmp_path



def test_user_config_directories_follow_platform_conventions(tmp_path):
    from gui_dev_v3.runtime_paths import resolve_user_config_dir

    home = tmp_path / "home"
    assert resolve_user_config_dir(
        platform="win32", environ={"APPDATA": str(tmp_path / "roaming")}, home=home
    ) == tmp_path / "roaming" / "OpenVLC"
    assert resolve_user_config_dir(
        platform="darwin", environ={}, home=home
    ) == home / "Library" / "Application Support" / "OpenVLC" / "Config"
    assert resolve_user_config_dir(
        platform="linux", environ={"XDG_CONFIG_HOME": str(tmp_path / "config")}, home=home
    ) == tmp_path / "config" / "OpenVLC"
    assert resolve_user_config_dir(
        platform="linux", environ={}, home=home
    ) == home / ".config" / "OpenVLC"


def test_app_initializes_user_data_before_importing_runtime_stores():
    import os
    import subprocess
    import sys

    source_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("VLC_DATA_DIR", None)
    code = """
from gui_dev_v3.app import main
from gui_dev_v3.data import records, status
from gui_dev_v3.runtime_paths import configure_runtime_data_dir

root = configure_runtime_data_dir()
assert records.LOG_DIR == root / "logs" / "rx"
assert records.CAPTURE_DIR == root / "state" / "captures"
assert status._STATE_DIR == root / "state"
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=source_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_runtime_status_writes_use_unique_atomic_temporaries(tmp_path, monkeypatch):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from gui_dev_v3.data import status

    monkeypatch.setattr(status, "_STATE_DIR", tmp_path)

    def write(index):
        status.write_status(
            "rx",
            f"Stage {index}",
            detail=f"writer {index}",
            percent=index,
            state="active",
            writer=index,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(32)))

    result = json.loads((tmp_path / "rx_status.json").read_text(encoding="utf-8"))
    assert result["writer"] in range(32)
    assert result["stage"] == f"Stage {result['writer']}"
    assert result["percent"] == result["writer"]
    assert not list(tmp_path.glob(".*.tmp"))



def test_status_reader_treats_invalid_utf8_as_corrupt(monkeypatch, tmp_path):
    from gui_dev_v3.data import status

    monkeypatch.setattr(status, "_STATE_DIR", tmp_path)
    (tmp_path / "rx_status.json").write_bytes(b"\xff\xfe")
    assert status.read_status("rx") is None


def test_status_writer_returns_false_for_unserializable_payload(monkeypatch, tmp_path):
    from gui_dev_v3.data import status

    monkeypatch.setattr(status, "_STATE_DIR", tmp_path)
    assert status.write_status("rx", "Receiving", unsupported=object()) is False
    assert not (tmp_path / "rx_status.json").exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_status_writer_returns_false_for_invalid_percent(monkeypatch, tmp_path):
    from gui_dev_v3.data import status

    monkeypatch.setattr(status, "_STATE_DIR", tmp_path)
    assert status.write_status("rx", "Receiving", percent="invalid") is False
    assert not (tmp_path / "rx_status.json").exists()
