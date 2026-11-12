import pytest

from gui_dev_v3.serial.transfer_plan import (
    MAX_STREAM_CHUNKS,
    plan_stream_parts,
)
from gui_dev_v3.serial.session import crc16_ccitt


@pytest.mark.parametrize(
    ("chunk_size", "expected_part_size"),
    [
        (16, 16 * MAX_STREAM_CHUNKS),
        (128, 128 * MAX_STREAM_CHUNKS),
        (256, 80 * 1024),
        (512, 80 * 1024),
        (1024, 80 * 1024),
    ],
)
def test_part_size_respects_byte_and_chunk_limits(chunk_size, expected_part_size):
    part_size, part_count = plan_stream_parts(200_000, chunk_size)
    assert part_size == expected_part_size
    assert part_count >= 1
    assert (part_size + chunk_size - 1) // chunk_size <= MAX_STREAM_CHUNKS
    assert part_size <= 80 * 1024


def test_small_file_uses_one_part():
    assert plan_stream_parts(1024, 256) == (80 * 1024, 1)


def test_crc16_can_be_updated_incrementally():
    payload = bytes(range(256)) * 257
    whole = crc16_ccitt(payload)
    first = crc16_ccitt(payload[:12345])
    incremental = crc16_ccitt(payload[12345:], initial_crc=first)
    assert incremental == whole


@pytest.mark.parametrize(
    ("file_size", "chunk_size"),
    [(-1, 256), (100, 0)],
)
def test_invalid_transfer_plan_inputs(file_size, chunk_size):
    if file_size < 0 or chunk_size == 0:
        with pytest.raises(ValueError):
            plan_stream_parts(file_size, chunk_size)


def test_tx_batch_send_obeys_firmware_chunk_limit(tmp_path, monkeypatch):
    import gui_dev_v3.settings as settings_module
    import gui_dev_v3.serial.controllers as controllers_module
    from gui_dev_v3.serial.controllers import TXSerialController

    class NoDmaSettings:
        def __init__(self, _role):
            pass

        def get(self, key, default=None):
            return False if key == "link/dma_mode" else default

    monkeypatch.setattr(settings_module, "SettingsManager", NoDmaSettings)
    monkeypatch.setattr(controllers_module.time, "sleep", lambda _seconds: None)
    source = tmp_path / "large.bin"
    source.write_bytes(b"x" * 100_000)

    controller = TXSerialController()
    controller._dma_capable = False
    controller.serial_obj = object()
    controller.is_connected = True
    sent_parts = []

    def capture_part(_path, data, name_bytes, chunk_size, _tid, _crc, _rounds):
        sent_parts.append((data, name_bytes, chunk_size))
        return True

    controller._send_stream = capture_part
    assert controller.send_file(source, chunk_bytes=16) is True
    assert len(sent_parts) == 13
    assert all(len(part) <= 16 * MAX_STREAM_CHUNKS for part, _, _ in sent_parts)
    assert all((len(part) + 15) // 16 <= MAX_STREAM_CHUNKS for part, _, _ in sent_parts)
    assert all(len(name) <= 80 for _, name, _ in sent_parts)


def test_tx_rejects_long_filenames_instead_of_truncating(tmp_path, monkeypatch):
    import gui_dev_v3.settings as settings_module
    from gui_dev_v3.serial.controllers import TXSerialController

    class NoDmaSettings:
        def __init__(self, _role):
            pass

        def get(self, key, default=None):
            return False if key == "link/dma_mode" else default

    monkeypatch.setattr(settings_module, "SettingsManager", NoDmaSettings)
    source = tmp_path / (("x" * 81) + ".bin")
    source.write_bytes(b"short")

    controller = TXSerialController()
    controller._dma_capable = False
    controller.serial_obj = object()
    controller.is_connected = True
    controller._send_stream = lambda *_args: pytest.fail("truncated filename must not be sent")

    assert controller.send_file(source) is False
