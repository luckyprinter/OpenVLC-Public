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
        f"RX_FILE_HEX:13:DATA:3:1:{crc16_ccitt(payload):04X}:"
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


def test_physical_backend_reassembles_batch_and_exposes_received_path(
    tmp_path, monkeypatch
):
    import time
    from gui_dev_v3.rx.backends.physical import crc16_ccitt

    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._save_dir = tmp_path
    backend._active_started_monotonic = time.monotonic()

    first = b"OpenVLC "
    second = b"batch test"
    complete = first + second
    full_crc = crc16_ccitt(complete)

    def make_line(index: int, tid: int, part: bytes) -> str:
        wrapped_name = (
            f"VLCB1~batch-test~{index}~2~{full_crc:04X}~received.bin"
        )
        name_hex = wrapped_name.encode("utf-8").hex()
        return (
            f"RX_FILE_HEX:{tid}:DATA:{len(part)}:1:"
            f"{crc16_ccitt(part):04X}:{name_hex}:{part.hex()}"
        )

    backend._handle_file_hex(make_line(1, 31, first))
    assert backend._batch_assembler.pending_count == 1
    assert not list(tmp_path.iterdir())

    backend._handle_file_hex(make_line(2, 32, second))

    output = tmp_path / "received.bin"
    assert output.read_bytes() == complete
    record = backend._last_completed_transfer
    assert record is not None
    assert record.tid == 32
    assert record.filename == "received.bin"
    assert record.status == TransferStatus.COMPLETE
    assert record.quality.crc_status == "PASS"
    assert record.quality.strict_ber is None
    assert record.received_path == str(output)
    assert backend._batch_assembler.pending_count == 0


def test_bad_batch_part_crc_discards_pending_group_and_active_state(
    tmp_path, monkeypatch
):
    from gui_dev_v3.rx.backends.physical import crc16_ccitt

    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._save_dir = tmp_path
    first = b"first"
    second = b"second"
    full_crc = crc16_ccitt(first + second)

    def make_line(index: int, part: bytes, expected_crc: int) -> str:
        wrapped = f"VLCB1~bad-crc~{index}~2~{full_crc:04X}~failed.bin"
        return (
            f"RX_FILE_HEX:45:DATA:{len(part)}:1:{expected_crc:04X}:"
            f"{wrapped.encode().hex()}:{part.hex()}"
        )

    backend._handle_file_hex(make_line(1, first, crc16_ccitt(first)))
    assert backend._batch_assembler.pending_count == 1

    backend._handle_file_hex(make_line(2, second, 0x0000))

    assert backend._batch_assembler.pending_count == 0
    assert backend._active_tid is None
    assert backend._active_filename == ""
    assert backend._active_started_monotonic is None
    assert not list(tmp_path.iterdir())
    assert backend._last_completed_transfer is None


def test_refresh_expires_incomplete_batches_without_new_fragments(monkeypatch):
    import time
    import gui_dev_v3.rx.backends.physical as physical_module
    import gui_dev_v3.settings as settings_module
    from gui_dev_v3.logic.batch_assembler import BatchAssembler

    class OfflineSettings:
        def __init__(self, _role):
            pass

        def get(self, key, default=None):
            return False if key == "connection/auto_connect" else default

    monkeypatch.setattr(settings_module, "SettingsManager", OfflineSettings)
    monkeypatch.setattr(physical_module, "read_status", lambda _role: None)
    monkeypatch.setattr(physical_module, "_is_fresh", lambda _status: False)
    backend = RXPhysicalBackend()
    backend.scan_ports = lambda: []
    backend._batch_assembler = BatchAssembler(ttl_seconds=1)
    backend._batch_assembler.add_part(
        group_id="expired",
        part_index=1,
        part_count=2,
        full_crc=0x1234,
        filename="large.bin",
        part_data=b"part",
        part_crc_ok=True,
        part_chunks=1,
        tid=50,
        now=time.monotonic() - 2,
    )

    snapshot = backend.refresh()

    assert backend._batch_assembler.pending_count == 0
    assert any(item["event"] == "Batch Expired" for item in snapshot.activity_log)


def test_firmware_crc_failure_discards_active_batch_group(monkeypatch):
    import time
    from gui_dev_v3.logic.batch_assembler import BatchAssembler
    from gui_dev_v3.models import TransferStatus

    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._batch_assembler = BatchAssembler()
    backend._batch_assembler.add_part(
        group_id="firmware-crc",
        part_index=1,
        part_count=2,
        full_crc=0x1234,
        filename="failed.bin",
        part_data=b"first",
        part_crc_ok=True,
        part_chunks=1,
        tid=81,
    )
    encoded_name = "VLCB1~firmware-crc~1~2~1234~failed.bin".encode().hex()
    backend._handle_transfer_notice(
        f"RX_TRANSFER_NOTICE:81:10:2:1234:{encoded_name}"
    )
    backend._active_received_chunks = 1

    backend._handle_file_crc_fail(
        "RX_FILE_CRC_FAIL:81:got=0000:expected=1234"
    )

    assert backend._batch_assembler.pending_count == 0
    assert backend._active_batch_group_id is None
    assert backend._active_tid is None
    assert backend._active_filename == ""
    assert backend._active_total_size == 0
    assert backend._active_total_chunks == 0
    assert backend._active_received_chunks == 0
    assert backend._active_started_monotonic is None
    assert backend._last_completed_transfer.status == TransferStatus.CRC_FAILED
    assert backend._last_completed_transfer.quality.strict_ber is None


def test_file_payload_length_mismatch_is_rejected_and_active_state_cleared(
    tmp_path, monkeypatch
):
    from gui_dev_v3.rx.backends.physical import crc16_ccitt

    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._save_dir = tmp_path
    backend._active_tid = 90
    backend._active_filename = "truncated.bin"
    backend._active_total_size = 10
    payload = b"abc"
    name_hex = "truncated.bin".encode().hex()
    line = (
        f"RX_FILE_HEX:90:DATA:10:1:{crc16_ccitt(payload):04X}:"
        f"{name_hex}:{payload.hex()}"
    )

    backend._handle_file_hex(line)

    assert backend._last_completed_transfer is None
    assert backend._active_tid is None
    assert backend._active_filename == ""
    assert backend._active_total_size == 0
    assert not list(tmp_path.iterdir())


def test_batch_group_is_discarded_when_payload_length_fails_before_metadata_parse(
    tmp_path, monkeypatch
):
    from gui_dev_v3.logic.batch_assembler import BatchAssembler
    from gui_dev_v3.rx.backends.physical import crc16_ccitt

    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._save_dir = tmp_path
    backend._batch_assembler = BatchAssembler()
    backend._batch_assembler.add_part(
        group_id="length-mismatch",
        part_index=1,
        part_count=2,
        full_crc=0x1234,
        filename="bad.bin",
        part_data=b"first",
        part_crc_ok=True,
        part_chunks=1,
        tid=82,
    )
    wrapped = "VLCB1~length-mismatch~2~2~1234~bad.bin"
    name_hex = wrapped.encode().hex()
    backend._handle_transfer_notice(
        f"RX_TRANSFER_NOTICE:82:10:1:1234:{name_hex}"
    )
    payload = b"part"
    line = (
        f"RX_FILE_HEX:82:DATA:10:1:{crc16_ccitt(payload):04X}:"
        f"{name_hex}:{payload.hex()}"
    )

    backend._handle_file_hex(line)

    assert backend._batch_assembler.pending_count == 0
    assert backend._active_batch_group_id is None
    assert backend._active_tid is None
    assert not list(tmp_path.iterdir())


def test_truncated_file_line_clears_matching_active_transfer():
    from gui_dev_v3.logic.batch_assembler import BatchAssembler

    backend = RXPhysicalBackend()
    backend._batch_assembler = BatchAssembler()
    backend._batch_assembler.add_part(
        group_id="truncated-group",
        part_index=1,
        part_count=2,
        full_crc=0x1234,
        filename="truncated.bin",
        part_data=b"first",
        part_crc_ok=True,
        part_chunks=1,
        tid=101,
    )
    backend._active_tid = 101
    backend._active_filename = "truncated.bin"
    backend._active_total_size = 10
    backend._active_total_chunks = 2
    backend._active_received_chunks = 1
    backend._active_started_monotonic = 1.0
    backend._active_batch_group_id = "truncated-group"

    backend._handle_file_hex("RX_FILE_HEX:101:DATA:10")

    assert backend._active_tid is None
    assert backend._active_filename == ""
    assert backend._active_total_size == 0
    assert backend._active_total_chunks == 0
    assert backend._active_received_chunks == 0
    assert backend._active_started_monotonic is None
    assert backend._active_batch_group_id is None
    assert backend._batch_assembler.pending_count == 0



def test_serial_cleanup_discards_incomplete_batch_and_active_progress():
    from gui_dev_v3.logic.batch_assembler import BatchAssembler

    backend = RXPhysicalBackend()
    backend._batch_assembler = BatchAssembler()
    backend._batch_assembler.add_part(
        group_id="session-one",
        part_index=1,
        part_count=2,
        full_crc=0x1234,
        filename="must-not-cross-session.bin",
        part_data=b"old-session",
        part_crc_ok=True,
        part_chunks=1,
        tid=201,
    )
    backend._active_tid = 201
    backend._active_filename = "part.bin"
    backend._active_total_size = 11
    backend._active_total_chunks = 2
    backend._active_received_chunks = 1
    backend._active_batch_group_id = "session-one"

    backend.cleanup()

    assert backend._batch_assembler.pending_count == 0
    assert backend._active_tid is None
    assert backend._active_filename == ""
    assert backend._active_total_size == 0
    assert backend._active_total_chunks == 0
    assert backend._active_received_chunks == 0
    assert backend._active_started_monotonic is None
    assert backend._active_batch_group_id is None


def test_stale_file_payload_cannot_complete_a_different_active_transfer(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._save_dir = tmp_path
    backend._active_tid = 202
    backend._active_filename = "current.bin"
    backend._active_total_size = 7
    backend._active_total_chunks = 1
    backend._active_received_chunks = 1

    from gui_dev_v3.rx.backends.physical import crc16_ccitt
    payload = b"stale"
    name_hex = "old.bin".encode().hex()
    line = (
        f"RX_FILE_HEX:201:DATA:{len(payload)}:1:"
        f"{crc16_ccitt(payload):04X}:{name_hex}:{payload.hex()}"
    )

    backend._handle_file_hex(line)

    assert backend._last_completed_transfer is None
    assert backend._active_tid == 202
    assert backend._active_filename == "current.bin"
    assert not list(tmp_path.iterdir())


def test_batch_payload_group_must_match_transfer_notice(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._save_dir = tmp_path
    backend._active_tid = 303
    backend._active_batch_group_id = "announced-group"
    backend._active_filename = "announced.bin"
    backend._batch_assembler.add_part(
        group_id="announced-group",
        part_index=1,
        part_count=2,
        full_crc=0x1234,
        filename="capture.bin",
        part_data=b"already accepted",
        part_crc_ok=True,
        part_chunks=1,
        tid=302,
    )

    from gui_dev_v3.rx.backends.physical import crc16_ccitt
    payload = b"part"
    wrapped = "VLCB1~different-group~1~2~1234~capture.bin"
    line = (
        f"RX_FILE_HEX:303:DATA:{len(payload)}:1:"
        f"{crc16_ccitt(payload):04X}:{wrapped.encode().hex()}:{payload.hex()}"
    )

    backend._handle_file_hex(line)

    assert backend._batch_assembler.pending_count == 0
    assert backend._active_tid is None
    assert backend._active_batch_group_id is None
    assert not list(tmp_path.iterdir())
