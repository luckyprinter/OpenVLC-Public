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


def test_large_stream_batch_reads_parts_without_loading_whole_file(tmp_path, monkeypatch):
    import gui_dev_v3.serial.controllers as controllers_module
    import gui_dev_v3.settings as settings_module
    from gui_dev_v3.serial.controllers import _crc16_file
    from gui_dev_v3.serial.session import MAX_STREAM_FILE_BYTES, crc16_ccitt

    payload = bytes(range(256)) * ((MAX_STREAM_FILE_BYTES // 256) + 37)
    source = tmp_path / "large-payload.bin"
    source.write_bytes(payload)

    class Settings:
        def __init__(self, _scope):
            pass

        def get(self, _key, default=None):
            return default

    monkeypatch.setattr(settings_module, "SettingsManager", Settings)
    monkeypatch.setattr(controllers_module.time, "sleep", lambda _seconds: None)

    controller = TXSerialController()
    controller.is_connected = True
    controller.serial_obj = object()
    controller._dma_capable = False
    controller.status = lambda *_args, **_kwargs: None

    sent_parts = []

    def capture_part(_path, part, _name, _chunk, _tid, part_crc, _rounds, **_kwargs):
        assert part_crc == crc16_ccitt(part)
        sent_parts.append(bytes(part))
        return True

    monkeypatch.setattr(controller, "_send_stream", capture_part)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda _self: (_ for _ in ()).throw(AssertionError("large batch must not use read_bytes")),
    )

    assert _crc16_file(source) == crc16_ccitt(payload)
    assert controller.send_file(source) is True
    assert b"".join(sent_parts) == payload
    assert len(sent_parts) >= 2
    assert max(map(len, sent_parts)) <= MAX_STREAM_FILE_BYTES
