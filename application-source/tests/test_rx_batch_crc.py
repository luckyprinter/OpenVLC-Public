import time

from gui_dev_v3.logic.batch_assembler import BatchAssembler
from gui_dev_v3.rx.backends.physical import RXPhysicalBackend


def test_batch_crc_failure_uses_batch_flag_not_decorated_filename(monkeypatch):
    backend = RXPhysicalBackend()
    monkeypatch.setattr("gui_dev_v3.logger.file_log", lambda *args, **kwargs: None)

    encoded_name = "VLCB1~group-1~1~2~ABCD~original.bin".encode("utf-8").hex()
    backend._handle_transfer_notice(
        f"RX_TRANSFER_NOTICE:41:100:2:ABCD:{encoded_name}"
    )

    assert backend._active_is_batch is True
    assert backend._active_filename == "original.bin (Part 1/2)"

    backend._handle_file_crc_fail(
        "RX_FILE_CRC_FAIL:41:got=0000:expected=ABCD"
    )

    # A failed batch part is not a completed file-level transfer.
    assert backend._last_completed_transfer is None
    assert backend._active_tid is None
    assert backend._active_is_batch is False
    assert backend._active_started_monotonic is None


def test_rx_poll_prunes_expired_incomplete_batches():
    backend = RXPhysicalBackend()
    backend._batch_assembler = BatchAssembler(ttl_seconds=1)
    old_time = time.monotonic() - 2
    backend._batch_assembler.add_part(
        group_id="expired", part_index=1, part_count=2, full_crc=0x1234,
        filename="large.bin", part_data=b"part", part_crc_ok=True,
        part_chunks=1, tid=50, now=old_time,
    )

    backend._prune_expired_batches()

    assert backend._batch_assembler.pending_count == 0
    assert any(item["event"] == "Batch Expired" for item in backend._log_queue)
