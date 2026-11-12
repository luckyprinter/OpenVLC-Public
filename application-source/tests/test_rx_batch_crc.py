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
