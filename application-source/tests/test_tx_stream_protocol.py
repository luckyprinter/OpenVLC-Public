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
            controller._append_line("TX_STREAM_BEGIN_OK:7:mode=4B5B:size=1:chunk=16:chunks=1")
        elif line.startswith("STREAM_DATA:"):
            controller._append_line("TX_STREAM_DATA_OK:7:1:1")
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


def test_stream_ignores_wrong_tid_and_waits_past_180_seconds(monkeypatch):
    from gui_dev_v3.serial import controllers

    controller = TXSerialController()
    controller.is_connected = True
    controller.serial_obj = object()
    controller._dma_capable = False
    now = 0.0
    started = False
    completion_delivered = False
    events = []
    monkeypatch.setattr(controllers.time, "monotonic", lambda: now)
    monkeypatch.setattr(controller, "on_status", events.append)

    def fake_sleep(seconds):
        nonlocal now, completion_delivered
        now += seconds
        if started and now >= 205 and not completion_delivered:
            controller._append_line("TX_STREAM_DONE:7:80")
            completion_delivered = True

    def firmware(command):
        nonlocal started
        if command.startswith("STREAM_BEGIN:"):
            controller._append_line("TX_STREAM_BEGIN_OK:7:mode=4B5B:size=20480:chunk=256:chunks=80")
        elif command.startswith("STREAM_DATA:"):
            _, offset, payload = command.split(":")
            loaded = int(offset) + len(payload) // 2
            controller._append_line(f"TX_STREAM_DATA_OK:7:{loaded}:20480")
        elif command == "STREAM_START":
            started = True
            controller._append_line("TX_STREAM_DONE:17:80")
        return True

    monkeypatch.setattr(controllers.time, "sleep", fake_sleep)
    monkeypatch.setattr(controller, "send_line", firmware)
    assert controller.apply_4b5b_settings(freq=1000)
    assert controller._send_stream(Path("slow.bin"), bytes(20480), b"slow.bin", 256, 7, 0, 1)
    assert completion_delivered
    assert events[-1]["stage"] == "Send complete"


def test_stream_reports_firmware_crc_error_without_waiting_for_done(monkeypatch):
    controller = TXSerialController()
    controller.is_connected = True
    controller.serial_obj = object()
    events = []
    monkeypatch.setattr(controller, "on_status", events.append)

    def firmware(command):
        if command.startswith("STREAM_BEGIN:"):
            controller._append_line("TX_STREAM_BEGIN_OK:7:mode=4B5B:size=1:chunk=16:chunks=1")
        elif command.startswith("STREAM_DATA:"):
            controller._append_line("TX_STREAM_DATA_OK:7:1:1")
        elif command == "STREAM_START":
            controller._append_line("TX_STREAM_ERROR:file_crc:got=1111:expected=2222")
        return True

    monkeypatch.setattr(controller, "send_line", firmware)
    assert not controller._send_stream(Path("tiny.bin"), b"x", b"tiny.bin", 16, 7, 0, 1)
    assert events[-1]["stage"] == "CRC Failure"


def test_disconnect_between_stream_parts_stops_the_batch(tmp_path, monkeypatch):
    source = tmp_path / "payload.bin"
    source.write_bytes(b"x" * 32769)
    controller = TXSerialController()
    controller._dma_capable = False
    controller.is_connected = True
    controller.serial_obj = object()
    parts = []

    def send_part(_path, data, *_args, **_kwargs):
        parts.append(len(data))
        controller.is_connected = False
        return True

    monkeypatch.setattr(controller, "_send_stream", send_part)
    assert not controller.send_file(source, chunk_bytes=64)
    assert parts == [32768]
def test_large_stream_batch_reads_parts_without_loading_whole_file(tmp_path, monkeypatch):
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
    monkeypatch.setattr(TXSerialController, "_wait_between_parts", lambda *_args: False)

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
