from gui_dev_v3 import logger
from gui_dev_v3.models import TransferStatus
from gui_dev_v3.rx.backends.physical import RXPhysicalBackend


def test_firmware_crc_failure_does_not_invent_ber(monkeypatch):
    monkeypatch.setattr(logger, "file_log", lambda *_args, **_kwargs: None)
    backend = RXPhysicalBackend()
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
