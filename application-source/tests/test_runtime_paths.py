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
