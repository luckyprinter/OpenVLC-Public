"""TX STREAM protocol race regressions."""
from pathlib import Path

from gui_dev_v3.serial.controllers import TXSerialController


def test_stream_completion_emitted_during_start_write_is_not_missed(monkeypatch):
    """A fast firmware completion must be visible to the wait that follows START."""
    import gui_dev_v3.settings as settings_module

    class Settings:
        def __init__(self, _scope):
            pass

        def get(self, key, default=None):
            return 15_000 if key == "link/symbol_hz" else default

    monkeypatch.setattr(settings_module, "SettingsManager", Settings)

    controller = TXSerialController()
    controller.is_connected = True
    controller.serial_obj = object()

    def immediate_firmware(line: str) -> bool:
        if line.startswith("STREAM_BEGIN:"):
            controller._append_line("TX_STREAM_BEGIN_OK")
        elif line.startswith("STREAM_DATA:"):
            controller._append_line("TX_STREAM_DATA_OK")
        elif line == "STREAM_START":
            # Simulate a very short transfer whose completion is read before
            # send_line() returns to the caller.
            controller._append_line("TX_STREAM_DONE:7:1")
        return True

    monkeypatch.setattr(controller, "send_line", immediate_firmware)
    monkeypatch.setattr(controller, "status", lambda *_args, **_kwargs: None)

    assert controller._send_stream(
        Path("tiny.bin"),
        b"x",
        b"tiny.bin",
        chunk_size=16,
        tid=7,
        file_crc=0,
        round_count=1,
    ) is True
