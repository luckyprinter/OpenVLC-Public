from gui_dev_v3 import logger
from gui_dev_v3.models import TransferStatus
from gui_dev_v3.rx.backends.physical import RXPhysicalBackend


def test_firmware_crc_failure_does_not_invent_ber(monkeypatch):
    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._active_tid = 12
    backend._active_filename = "sample.bin"
    backend._active_total_size = 32
    backend._active_total_chunks = 4
    backend._active_received_chunks = 4

    backend._handle_file_crc_fail("RX_FILE_CRC_FAIL:12:got=1234:expected=5678")

    record = backend._last_completed_transfer
    assert record is not None
    assert record.status == TransferStatus.CRC_FAILED
    assert record.quality.crc_status == "FAIL"
    assert record.quality.strict_ber is None
    assert record.quality.bit_accuracy is None
    assert record.quality.bit_errors is None
    assert backend._active_tid is None

def test_rejected_batch_fragment_clears_active_rx_transfer(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._save_dir = tmp_path
    backend._active_tid = 9
    backend._active_filename = "old.bin"
    backend._active_total_size = 20
    backend._active_total_chunks = 2
    backend._active_received_chunks = 1

    from gui_dev_v3.rx.backends.physical import crc16_ccitt
    fragment = b"\\xAA"
    metadata = "VLCB1~group-1~3~2~1234~capture.bin".encode("utf-8").hex()
    line = f"RX_FILE_HEX:9:DATA:1:1:{crc16_ccitt(fragment):04X}:{metadata}:{fragment.hex()}"

    backend._handle_file_hex(line)

    assert backend._batch_assembler.pending_count == 0
    assert backend._active_tid is None
    assert backend._active_filename == ""
    assert backend._active_started_monotonic is None
    assert not list(tmp_path.iterdir())

def test_crc_pass_does_not_create_a_ber_comparison(tmp_path, monkeypatch):
    import time
    from gui_dev_v3.rx.backends.physical import crc16_ccitt

    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._save_dir = tmp_path
    backend._active_tid = 13
    backend._active_filename = "received.bin"
    backend._active_total_size = 3
    backend._active_total_chunks = 1
    backend._active_received_chunks = 1
    backend._active_started_monotonic = time.monotonic()

    payload = b"VLC"
    filename_hex = "received.bin".encode("utf-8").hex()
    line = (
        f"RX_FILE_HEX:13:DATA:1:1:{crc16_ccitt(payload):04X}:"
        f"{filename_hex}:{payload.hex()}"
    )
    backend._handle_file_hex(line)

    record = backend._last_completed_transfer
    assert record is not None
    assert record.quality.crc_status == "PASS"
    assert record.quality.strict_ber is None
    assert record.quality.bit_accuracy is None
    assert record.quality.bit_errors is None
    assert record.quality.total_bits == 0
    assert record.quality.compared_bytes == 0
    assert record.received_path is not None


def test_cached_status_is_not_reported_as_live_serial_connection(monkeypatch):
    import time
    from types import SimpleNamespace
    import gui_dev_v3.rx.backends.physical as physical_module
    import gui_dev_v3.settings as settings_module

    class OfflineSettings:
        def __init__(self, _role):
            pass

        def get(self, key, default=None):
            if key == "connection/auto_connect":
                return False
            return default

    monkeypatch.setattr(settings_module, "SettingsManager", OfflineSettings)
    monkeypatch.setattr(
        physical_module,
        "read_status",
        lambda role: {"role": role, "updated_at": time.time()},
    )
    monkeypatch.setattr(physical_module, "_is_fresh", lambda _status: True)
    transfer = SimpleNamespace(tid=4)
    session = SimpleNamespace(latest_transfer=transfer)
    backend = RXPhysicalBackend()
    backend._build_from_status = lambda *_args: (session, [transfer])
    backend._build_log = lambda *_args: []
    backend.scan_ports = lambda: []

    snapshot = backend.refresh()

    assert snapshot.transfer is transfer
    assert snapshot.serial_connected is False
    assert snapshot.firmware_found is False


def test_incomplete_batch_part_clears_live_progress_but_keeps_bounded_group(tmp_path, monkeypatch):
    import time
    from gui_dev_v3.rx.backends.physical import crc16_ccitt

    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._save_dir = tmp_path
    backend._active_tid = 31
    backend._active_filename = "part-1.bin"
    backend._active_total_size = 1
    backend._active_total_chunks = 1
    backend._active_received_chunks = 1
    backend._active_started_monotonic = time.monotonic()

    fragment = b"\xAA"
    batch_name = "VLCB1~group-2~1~2~1234~complete.bin"
    name_hex = batch_name.encode("utf-8").hex()
    line = (
        f"RX_FILE_HEX:31:DATA:1:1:{crc16_ccitt(fragment):04X}:"
        f"{name_hex}:{fragment.hex()}"
    )

    backend._handle_file_hex(line)

    assert backend._batch_assembler.pending_count == 1
    assert backend._active_tid is None
    assert backend._active_filename == ""
    assert backend._active_total_size == 0
    assert backend._active_total_chunks == 0
    assert backend._active_received_chunks == 0
    assert backend._active_started_monotonic is None
    assert not list(tmp_path.iterdir())
