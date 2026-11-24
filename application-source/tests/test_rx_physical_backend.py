import pytest
from binascii import crc_hqx

from gui_dev_v3 import logger
from gui_dev_v3.models import TransferStatus
from gui_dev_v3.rx.backends import physical
from gui_dev_v3.rx.backends.physical import RXPhysicalBackend


def _firmware_dump(tid, payload, *, count=1, name="capture.bin"):
    return (
        f"RX_FILE_HEX:{tid}:1:{len(payload)}:{count}:{crc_hqx(payload, 0xFFFF):04X}:"
        f"{name.encode().hex()}:{payload.hex()}"
    )


def test_physical_reader_reassembles_maximum_dump_and_recovers_after_overlong_line(tmp_path):
    backend = RXPhysicalBackend()
    backend._save_dir = tmp_path
    payload = bytes(range(256)) * 320
    dump = (_firmware_dump(7, payload, count=320) + "\r\n").encode()
    reads = iter([
        *(b"?" * 4096 for _ in range(43)), b"RX Ready\n",  # overlong record's tail
        dump[:500], b"", *(dump[i:i + 4096] for i in range(500, len(dump), 4096)),
        b"RX Ready\n",
    ])

    class FragmentedSerial:
        is_open = True
        in_waiting = 4096

        def read(self, size):
            assert 1 <= size <= 4096
            data = next(reads, None)
            if data is None:
                backend._reader_stop.set()
                return b""
            assert len(data) <= size
            return data

        def readline(self):
            return self.read(4096)

    backend._ser = FragmentedSerial()
    backend._serial_reader_loop()

    assert (tmp_path / "capture.bin").read_bytes() == payload
    assert backend._ready_event.is_set()
    assert sum(entry["event"] == "RX Serial Framing" for entry in backend._log_queue) == 1


def test_physical_timeout_finalizes_matching_transfer_without_ber(tmp_path, monkeypatch):
    backend = RXPhysicalBackend()
    backend._save_dir = tmp_path
    monkeypatch.setattr(backend, "scan_ports", lambda: [])
    backend._dispatch_line("RX_TRANSFER_NOTICE:7:512:4:1234:636170747572652e62696e")
    backend._dispatch_line("RX_RAM_STORE:7:0:1:4")
    backend._dispatch_line("RX_RAM_TIMEOUT:6:received=3:total=4")
    assert backend._active_tid == 7

    backend._dispatch_line("RX_RAM_TIMEOUT:7:received=2:total=4")

    stalled = backend._build_from_lq({})
    assert stalled.transfer.status == TransferStatus.STALLED
    assert stalled.transfer.received_chunks == 2
    assert stalled.transfer.total_chunks == 4
    assert stalled.transfer.quality.missing_chunks == 2
    assert stalled.session.progress_percent == 50
    assert stalled.transfer.received_path is None
    assert stalled.transfer.quality.strict_ber is None
    assert backend._active_tid is None

    backend._dispatch_line(_firmware_dump(8, b"following transfer"))
    assert backend._build_from_lq({}).transfer.status == TransferStatus.COMPLETE


def test_sync_failure_is_reported_separately_from_a_real_lock():
    backend = RXPhysicalBackend()
    backend._dispatch_line("noiseRX_4B5B_SYNC_FAIL")
    backend._dispatch_line("RX_4B5B_SYNC:inverted")
    assert [entry["event"] for entry in backend._log_queue] == ["SYNC FAIL", "SYNC"]


def test_notice_less_dump_uses_its_own_chunk_count_after_other_transfer(tmp_path):
    backend = RXPhysicalBackend()
    backend._save_dir = tmp_path
    first = bytes(range(64))
    backend._dispatch_line(
        f"RX_TRANSFER_NOTICE:7:64:4:{crc_hqx(first, 0xFFFF):04X}:66697273742e62696e"
    )
    backend._dispatch_line(_firmware_dump(7, first, count=4, name="first.bin"))
    backend._dispatch_line(_firmware_dump(8, b"next", name="second.bin"))

    record = backend._last_completed_transfer
    assert record.tid == 8
    assert record.total_chunks == record.received_chunks == 1
    assert (tmp_path / "second.bin").read_bytes() == b"next"


def test_self_consistent_dump_cannot_override_conflicting_notice(tmp_path):
    backend = RXPhysicalBackend()
    backend._save_dir = tmp_path
    backend._dispatch_line("RX_TRANSFER_NOTICE:7:16:1:1234:66697273742e62696e")
    backend._dispatch_line(_firmware_dump(7, b"wrong identity", name="first.bin"))

    rejected = backend._last_completed_transfer
    assert rejected.status == physical.TransferStatus.STALLED
    assert rejected.received_path is None
    assert backend._active_tid is None
    assert not list(tmp_path.iterdir())


def test_physical_refresh_drains_fast_terminal_records_without_lq(tmp_path, monkeypatch):
    backend = RXPhysicalBackend()
    backend._save_dir = tmp_path
    backend._connected = True
    monkeypatch.setattr(physical, "read_status", lambda _role: None)
    monkeypatch.setattr(backend, "scan_ports", lambda: [])
    backend._ser = type("OpenSerial", (), {"closed": False})()
    monkeypatch.setattr(backend, "_poll_lq", lambda: None)
    first = b"first result"
    second = b"second result"

    for payload in (first, second):
        backend._dispatch_line(
            f"RX_TRANSFER_NOTICE:7:{len(payload)}:1:{crc_hqx(payload, 0xFFFF):04X}:"
            "636170747572652e62696e"
        )
        backend._dispatch_line(_firmware_dump(7, payload))

    snapshot = backend.refresh()
    assert snapshot.transfer == snapshot.completed_transfers[-1]
    assert [item.received_bytes for item in snapshot.completed_transfers] == [12, 13]
    assert all(item.capture_id and item.duration_seconds is not None for item in snapshot.completed_transfers)
    assert len({item.capture_id for item in snapshot.completed_transfers}) == 2
    assert backend.refresh().completed_transfers == ()


def test_physical_refresh_emits_only_new_observed_analog_for_active_capture(monkeypatch):
    backend = RXPhysicalBackend()
    backend._connected = True
    monkeypatch.setattr(physical, "read_status", lambda _role: None)
    monkeypatch.setattr(backend, "scan_ports", lambda: [])
    backend._ser = type("OpenSerial", (), {"closed": False})()
    monkeypatch.setattr(backend, "_poll_lq", lambda: {"SIGNAL": 2.4, "VREF": 2.0, "MARGIN": 0.4})
    backend._dispatch_line("RX_TRANSFER_NOTICE:7:512:4:1234:636170747572652e62696e")
    assert backend.refresh().analog_sample is None

    backend._dispatch_line("LQ,SIGNAL=2.4,VREF=2.0,MARGIN=0.4")

    snapshot = backend.refresh()
    capture_id, elapsed, pvo, vref, margin = snapshot.analog_sample
    assert capture_id == snapshot.transfer.capture_id
    assert elapsed >= 0 and (pvo, vref, margin) == (2.4, 2.0, 0.4)
    assert backend.refresh().analog_sample is None


def test_physical_disconnects_finalize_interrupted_capture(monkeypatch):
    backend = RXPhysicalBackend()
    backend._connected = True
    monkeypatch.setattr(physical, "write_status", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(physical, "read_status", lambda _role: None)
    monkeypatch.setattr(backend, "scan_ports", lambda: [])
    monkeypatch.setattr(backend, "_poll_lq", lambda: None)

    class OpenPort:
        closed = False

        def close(self):
            self.closed = True

    for disconnect in ("manual", "unplugged"):
        serial = OpenPort()
        backend._ser = serial
        backend._connected = True
        backend._reader_stop.clear()
        backend._dispatch_line("RX_TRANSFER_NOTICE:7:512:4:1234:636170747572652e62696e")
        backend._dispatch_line("RX_RAM_STORE:7:0:1:4")
        active = backend.refresh().transfer

        if disconnect == "manual":
            backend.disconnect()
        else:
            backend._mark_serial_lost(serial, OSError("USB unplugged"))

        snapshot = backend.refresh()
        terminal, = snapshot.completed_transfers
        assert snapshot.transfer == terminal
        assert terminal.capture_id == active.capture_id
        assert terminal.status == TransferStatus.STALLED
        assert terminal.received_chunks == 1
        assert terminal.quality.missing_chunks == 3
        assert terminal.received_bytes is None


def test_new_notice_preserves_interrupted_capture_as_stalled(monkeypatch):
    backend = RXPhysicalBackend()
    monkeypatch.setattr(backend, "scan_ports", lambda: [])
    backend._dispatch_line("RX_TRANSFER_NOTICE:7:512:4:1234:6f6c642e62696e")
    backend._dispatch_line("RX_RAM_STORE:7:0:1:4")
    active = backend._build_from_lq({}).transfer

    backend._dispatch_line("RX_TRANSFER_NOTICE:8:128:1:1234:6e65772e62696e")

    assert backend._last_completed_transfer.capture_id == active.capture_id
    assert backend._last_completed_transfer.status == TransferStatus.STALLED
    assert backend._last_completed_transfer.received_chunks == 1
    assert backend._build_from_lq({}).transfer.tid == 8


def test_physical_batch_with_bad_full_crc_does_not_publish_file(tmp_path):
    backend = RXPhysicalBackend()
    backend._save_dir = tmp_path
    for index, payload in ((1, b"first"), (2, b"second")):
        backend._dispatch_line(_firmware_dump(
            index, payload, name=f"VLCB1~group~{index}~2~0000~batch.bin",
        ))

    record = backend._last_completed_transfer
    assert record.status == TransferStatus.CRC_FAILED
    assert record.received_path is None
    assert record.quality.strict_ber is None
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("with_notice", [True, False])
def test_physical_dump_crc_mismatch_has_terminal_failure_without_payload(tmp_path, with_notice):
    backend = RXPhysicalBackend()
    backend._save_dir = tmp_path
    if with_notice:
        backend._dispatch_line("RX_TRANSFER_NOTICE:7:5:1:0000:636170747572652e62696e")
    backend._dispatch_line("RX_FILE_HEX:7:1:5:1:0000:636170747572652e62696e:6162636465")

    record = backend._last_completed_transfer
    assert record.status == TransferStatus.CRC_FAILED
    assert record.quality.crc_status == "FAIL"
    assert record.quality.strict_ber is None
    assert record.received_path is None
    assert record.received_bytes is None
    assert not list(tmp_path.iterdir())


def test_physical_receive_page_previews_saved_file_without_retaining_payload(tmp_path):
    from PySide6.QtWidgets import QApplication
    from types import SimpleNamespace
    from gui_dev_v3.rx.receive_page import ReceivePage

    app = QApplication.instance() or QApplication([])
    backend = RXPhysicalBackend()
    backend._save_dir = tmp_path
    payload = b"start" + b"x" * (80 * 1024 - 9) + b"tail"
    backend._dispatch_line(_firmware_dump(7, payload, count=320))
    record = backend._last_completed_transfer
    assert record.chunks == []

    page = ReceivePage()
    page.refresh(SimpleNamespace(
        transfer=record, serial_connected=True, is_receiving=False, progress_percent=100,
    ))

    preview = page.terminal.toPlainText()
    assert preview.startswith("start")
    assert "tail" not in preview
    assert "Preview limited" in preview
    assert len(preview) < len(payload)
    page.close()
    app.processEvents()

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
    assert backend._last_completed_transfer.status == TransferStatus.CRC_FAILED


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


def test_malformed_transfer_notice_does_not_mutate_active_transfer():
    from gui_dev_v3.logic.batch_assembler import BatchAssembler

    backend = RXPhysicalBackend()
    backend._batch_assembler = BatchAssembler()
    backend._batch_assembler.add_part(
        group_id="keep-this-group",
        part_index=1,
        part_count=2,
        full_crc=0x1234,
        filename="capture.bin",
        part_data=b"first",
        part_crc_ok=True,
        part_chunks=1,
        tid=401,
    )
    backend._active_tid = 401
    backend._active_batch_group_id = "keep-this-group"
    backend._active_filename = "capture.bin"
    backend._active_total_size = 10
    backend._active_total_chunks = 2
    backend._active_received_chunks = 1
    started = backend._active_started_monotonic

    # Invalid part index: validation must finish before any active fields change.
    wrapped = "VLCB1~poison-group~3~2~1234~capture.bin".encode().hex()
    backend._handle_transfer_notice(
        f"RX_TRANSFER_NOTICE:402:10:2:1234:{wrapped}"
    )

    assert backend._active_tid == 401
    assert backend._active_batch_group_id == "keep-this-group"
    assert backend._active_filename == "capture.bin"
    assert backend._active_total_size == 10
    assert backend._active_total_chunks == 2
    assert backend._active_received_chunks == 1
    assert backend._active_started_monotonic == started
    assert backend._batch_assembler.pending_count == 1


def test_new_transfer_notice_discards_abandoned_active_batch_group():
    from gui_dev_v3.logic.batch_assembler import BatchAssembler

    backend = RXPhysicalBackend()
    backend._batch_assembler = BatchAssembler()
    backend._batch_assembler.add_part(
        group_id="abandoned",
        part_index=1,
        part_count=2,
        full_crc=0x1234,
        filename="capture.bin",
        part_data=b"first",
        part_crc_ok=True,
        part_chunks=1,
        tid=501,
    )
    backend._active_tid = 501
    backend._active_batch_group_id = "abandoned"

    ordinary_name = "next.bin".encode().hex()
    backend._handle_transfer_notice(
        f"RX_TRANSFER_NOTICE:502:8:1:1234:{ordinary_name}"
    )

    assert backend._active_tid == 502
    assert backend._active_batch_group_id is None
    assert backend._batch_assembler.pending_count == 0


def test_atomic_received_file_write_persists_complete_bytes(tmp_path):
    payload = bytes(range(256)) * 4

    saved = physical._atomic_save_received_file(tmp_path, "capture.bin", payload)

    assert saved == tmp_path / "capture.bin"
    assert saved.read_bytes() == payload
    assert not list(tmp_path.glob(".rx-*.tmp"))


def test_received_publication_preserves_an_existing_destination(tmp_path):
    existing = tmp_path / "capture.bin"
    existing.write_bytes(b"existing")

    saved = physical._atomic_save_received_file(tmp_path, existing.name, b"new payload")

    assert existing.read_bytes() == b"existing"
    assert saved.name == "capture_1.bin"
    assert saved.read_bytes() == b"new payload"


def test_valid_payload_storage_error_preserves_crc_and_reports_terminal_failure(monkeypatch, tmp_path):
    backend = RXPhysicalBackend()
    backend._save_dir = tmp_path
    name = b"file.bin".hex()
    backend._dispatch_line(f"RX_TRANSFER_NOTICE:23:9:1:29B1:{name}")
    capture_id = backend._active_capture_id

    def fail_write(*_args, **_kwargs):
        raise OSError("Storage unavailable")

    monkeypatch.setattr(physical, "_atomic_save_received_file", fail_write)
    backend._dispatch_line(f"RX_FILE_HEX:23:DATA:9:1:29B1:{name}:{b'123456789'.hex()}")

    terminal = backend._last_completed_transfer
    assert terminal.status == physical.TransferStatus.STALLED
    assert terminal.quality.crc_status == "PASS"
    assert terminal.capture_id == capture_id
    assert terminal.received_path is None
    assert backend._active_tid is None


def test_dump_confirmation_reconciles_a_missing_payload(monkeypatch):
    backend = RXPhysicalBackend()
    monkeypatch.setattr(physical, "write_status", lambda *_args, **_kwargs: True)
    name = b"file.bin".hex()
    backend._dispatch_line(f"RX_TRANSFER_NOTICE:23:9:1:29B1:{name}")
    backend._dispatch_line("RX_FILE_DUMPED:22:9")
    assert backend._active_tid == 23

    backend._dispatch_line("RX_FILE_DUMPED:23:9")

    assert backend._active_tid is None
    assert backend._last_completed_transfer.status == physical.TransferStatus.STALLED
    assert backend._last_completed_transfer.received_path is None


def test_close_does_not_clear_reader_owned_transfer_until_reader_stops():
    backend = RXPhysicalBackend()
    name = b"file.bin".hex()
    backend._dispatch_line(f"RX_TRANSFER_NOTICE:23:9:1:29B1:{name}")
    capture_id = backend._active_capture_id

    class Reader:
        alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout):
            pass

    reader = Reader()
    backend._reader_thread = reader
    assert backend._close_serial() is False
    assert backend._active_capture_id == capture_id
    assert backend._last_completed_transfer is None

    reader.alive = False
    assert backend._close_serial() is True
    assert backend._last_completed_transfer.capture_id == capture_id
    assert backend._last_completed_transfer.status == physical.TransferStatus.STALLED


def test_atomic_received_file_write_failure_leaves_no_partial_destination(
    tmp_path, monkeypatch
):
    def fail_replace(_source, _destination):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(physical.os, "rename" if physical.os.name == "nt" else "link", fail_replace)

    try:
        physical._atomic_save_received_file(tmp_path, "capture.bin", b"payload")
    except OSError as exc:
        assert "simulated disk failure" in str(exc)
    else:
        raise AssertionError("atomic write should report replacement failure")

    assert not (tmp_path / "capture.bin").exists()
    assert not list(tmp_path.glob(".rx-*.tmp"))



def test_rx_reader_handles_serial_is_open_property_failure(monkeypatch):
    backend = RXPhysicalBackend()
    backend._reader_stop.clear()
    failures = []

    class BrokenSerial:
        @property
        def is_open(self):
            raise OSError("USB device disappeared")

    backend._ser = BrokenSerial()
    backend._mark_serial_lost = lambda ser, exc: failures.append((ser, exc))

    backend._serial_reader_loop()

    assert len(failures) == 1
    assert isinstance(failures[0][1], OSError)
    assert "USB device disappeared" in str(failures[0][1])


def test_rx_unexpected_disconnect_persists_connection_lost_status(monkeypatch):
    backend = RXPhysicalBackend()
    backend._reader_stop.clear()
    backend._record_diag = lambda *_args, **_kwargs: None
    writes = []
    monkeypatch.setattr(
        physical,
        "write_status",
        lambda role, stage, **kwargs: writes.append((role, stage, kwargs)) or True,
    )

    class FakeSerial:
        port = "/dev/ttyUSB-RX"
        closed = False

        def close(self):
            self.closed = True

    serial_handle = FakeSerial()
    backend._ser = serial_handle
    backend._connected = True
    backend._port = serial_handle.port

    backend._mark_serial_lost(serial_handle, OSError("USB unplugged"))

    assert serial_handle.closed
    assert backend._ser is None
    assert backend._connected is False
    assert backend._port is None
    assert writes == [
        (
            "rx",
            "Connection Lost",
            {
                "detail": "OSError",
                "state": "error",
                "port": "/dev/ttyUSB-RX",
            },
        )
    ]


def test_ram_store_ignores_stale_tid_and_rejects_invalid_progress():
    backend = RXPhysicalBackend()
    backend._active_tid = 77
    backend._active_total_chunks = 4
    backend._active_received_chunks = 1

    backend._handle_ram_store("RX_RAM_STORE:76:1:2:4")
    assert backend._active_received_chunks == 1
    assert backend._log_queue[-1]["event"] == "Ignored Stale Chunk Progress"

    backend._handle_ram_store("RX_RAM_STORE:77:4:2:4")
    assert backend._active_received_chunks == 1
    assert backend._log_queue[-1]["event"] == "RAM Store Error"

    backend._handle_ram_store("RX_RAM_STORE:77:2:2:4")
    assert backend._active_received_chunks == 2
    assert backend._log_queue[-1]["event"] == "Chunk Received"


@pytest.mark.parametrize("invalid_tid", [0, -1, 0x10000])
def test_rx_file_hex_rejects_tid_outside_firmware_range(
    invalid_tid, tmp_path, monkeypatch
):
    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._save_dir = tmp_path
    payload = b"payload"
    name_hex = "invalid-tid.bin".encode().hex()
    line = (
        f"RX_FILE_HEX:{invalid_tid}:DATA:{len(payload)}:1:"
        f"{physical.crc16_ccitt(payload):04X}:{name_hex}:{payload.hex()}"
    )

    backend._handle_file_hex(line)

    assert backend._last_completed_transfer is None
    assert backend._active_tid is None
    assert not list(tmp_path.iterdir())
    assert backend._log_queue[-1]["event"] == "RX File Error"


@pytest.mark.parametrize(
    ("rx_status", "expected_status"),
    [
        (
            {
                "stage": "Connection Lost",
                "tid": 0,
                "size": 0,
                "total_chunks": 0,
                "received_chunks": 0,
            },
            "Pending",
        ),
        (
            {
                "stage": "Connection Lost",
                "tid": 42,
                "file_name": "partial.bin",
                "size": 1024,
                "total_chunks": 4,
                "received_chunks": 2,
                "percent": 50,
            },
            "Stalled",
        ),
    ],
)
def test_cached_rx_status_does_not_invent_empty_or_live_transfer(
    rx_status, expected_status, monkeypatch
):
    from gui_dev_v3.data import session as session_module

    monkeypatch.setattr(
        session_module,
        "read_status",
        lambda role: rx_status if role == "rx" else None,
    )

    snapshot = session_module.build_session_from_status("rx")

    assert snapshot.latest_transfer.status.value == expected_status
    if expected_status == "Pending":
        assert snapshot.latest_transfer.tid == 0
        assert snapshot.latest_transfer.filename == "No active transfer"
    else:
        assert snapshot.latest_transfer.tid == 42
        assert snapshot.latest_transfer.filename == "partial.bin"


def test_rx_unexpected_disconnect_persists_partial_transfer_context(monkeypatch):
    backend = RXPhysicalBackend()
    backend._reader_stop.clear()
    backend._record_diag = lambda *_args, **_kwargs: None
    writes = []
    monkeypatch.setattr(
        physical,
        "write_status",
        lambda role, stage, **kwargs: writes.append((role, stage, kwargs)) or True,
    )

    class FakeSerial:
        port = "/dev/ttyUSB-RX"

        def close(self):
            pass

    handle = FakeSerial()
    backend._ser = handle
    backend._connected = True
    backend._port = handle.port
    backend._active_tid = 42
    backend._active_filename = "partial.bin"
    backend._active_total_size = 2048
    backend._active_total_chunks = 4
    backend._active_received_chunks = 2

    backend._mark_serial_lost(handle, OSError("USB unplugged"))

    assert writes == [
        (
            "rx",
            "Connection Lost",
            {
                "detail": "OSError",
                "state": "error",
                "port": "/dev/ttyUSB-RX",
                "tid": 42,
                "file_name": "partial.bin",
                "size_bytes": 2048,
                "total_chunks": 4,
                "received_chunks": 2,
                "percent": 50.0,
            },
        )
    ]


def test_rx_manual_disconnect_persists_partial_transfer_context(monkeypatch):
    backend = RXPhysicalBackend()
    backend._record_diag = lambda *_args, **_kwargs: None
    backend._close_serial = lambda: True
    writes = []
    monkeypatch.setattr(
        physical,
        "write_status",
        lambda role, stage, **kwargs: writes.append((role, stage, kwargs)) or True,
    )
    backend._connected = True
    backend._port = "/dev/ttyUSB-RX"
    backend._active_tid = 7
    backend._active_filename = "manual.bin"
    backend._active_total_size = 100
    backend._active_total_chunks = 2
    backend._active_received_chunks = 1

    backend.disconnect()

    assert writes == [
        (
            "rx",
            "Disconnected",
            {
                "detail": "User disconnected",
                "state": "idle",
                "port": "/dev/ttyUSB-RX",
                "tid": 7,
                "file_name": "manual.bin",
                "size_bytes": 100,
                "total_chunks": 2,
                "received_chunks": 1,
                "percent": 50.0,
            },
        )
    ]
