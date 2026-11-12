"""Baseline contract tests for the OpenVLC ESP32 application.

These tests protect stable software/firmware contracts and pure BER/CRC
calculations. They do not emulate the optical channel.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gui_dev_v3.logic.ber_bridge import compare_payload_bits
from gui_dev_v3.serial.detection import BAUDRATE_RX, BAUDRATE_TX, baud_for_role
from gui_dev_v3.serial.session import MAX_NAME_BYTES, MAX_STREAM_FILE_BYTES, crc16_ccitt

ROOT = Path(__file__).resolve().parents[2]


def _define(source: str, name: str) -> int:
    match = re.search(rf"^#define\s+{re.escape(name)}\s+(\d+)", source, re.MULTILINE)
    assert match, f"Missing firmware definition: {name}"
    return int(match.group(1))


def test_crc16_ccitt_standard_check_value() -> None:
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_role_baud_rates_match_firmware() -> None:
    tx = (ROOT / "firmware/tx/tx.ino").read_text(encoding="utf-8")
    rx = (ROOT / "firmware/rx/rx.ino").read_text(encoding="utf-8")

    assert BAUDRATE_TX == 115200
    assert BAUDRATE_RX == 460800
    assert re.search(r"Serial\.begin\(115200\)", tx)
    assert re.search(r"Serial\.begin\(460800\)", rx)
    assert baud_for_role("tx") == BAUDRATE_TX
    assert baud_for_role("rx") == BAUDRATE_RX


def test_rx_and_tx_pin_assignments_match_application_hardware_contract() -> None:
    tx = (ROOT / "firmware/tx/tx.ino").read_text(encoding="utf-8")
    rx = (ROOT / "firmware/rx/rx.ino").read_text(encoding="utf-8")

    assert _define(tx, "TX_PIN") == 5
    assert _define(rx, "RX_PIN") == 5
    assert _define(rx, "SIGNAL_ADC_PIN") == 34
    assert _define(rx, "VREF_ADC_PIN") == 35
    assert _define(rx, "VREF_PWM_PIN") == 25


def test_application_stream_buffer_matches_both_firmware_buffers() -> None:
    tx = (ROOT / "firmware/tx/tx.ino").read_text(encoding="utf-8")
    rx = (ROOT / "firmware/rx/rx.ino").read_text(encoding="utf-8")

    assert MAX_STREAM_FILE_BYTES == 80 * 1024
    assert "#define MAX_STREAM_FILE_BYTES (80UL * 1024UL)" in tx
    assert "#define MAX_RX_FILE_BYTES (80UL * 1024UL)" in rx


def test_method2_identical_file_has_zero_ber() -> None:
    result = compare_payload_bits(b"\x00\xA5\xFF", b"\x00\xA5\xFF")

    assert result["strict_bit_errors"] == 0
    assert result["overlap_ber"] == 0.0
    assert result["strict_ber"] == 0.0
    assert result["length_delta"] == 0


def test_method2_counts_individual_bit_errors() -> None:
    result = compare_payload_bits(b"\x00", b"\x03")

    assert result["overlap_bit_errors"] == 2
    assert result["strict_bit_errors"] == 2
    assert result["overlap_ber"] == 0.25
    assert result["strict_ber"] == 0.25
    assert result["preview"][0]["offset"] == 0


def test_method2_counts_missing_bytes_as_strict_errors() -> None:
    result = compare_payload_bits(b"\x00\xFF", b"\x00")

    assert result["overlap_bit_errors"] == 0
    assert result["strict_bit_errors"] == 8
    assert result["overlap_ber"] == 0.0
    assert result["strict_ber"] == 0.5
    assert result["length_delta"] == -1


def test_method2_handles_two_empty_files() -> None:
    result = compare_payload_bits(b"", b"")

    assert result["strict_bit_errors"] == 0
    assert result["strict_ber"] == 0.0


def test_non_dma_large_file_batching_uses_configured_chunk_and_rounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gui_dev_v3 import settings
    from gui_dev_v3.serial.controllers import TXSerialController

    class FakeSettingsManager:
        def __init__(self, role: str) -> None:
            assert role == "tx"

        def get(self, key: str, default: object = None) -> object:
            if key == "link/dma_mode":
                return False
            return default

    monkeypatch.setattr(settings, "SettingsManager", FakeSettingsManager)
    monkeypatch.setattr("gui_dev_v3.serial.controllers.time.sleep", lambda _seconds: None)

    file_path = tmp_path / "large.bin"
    file_path.write_bytes(b"\xA5" * (MAX_STREAM_FILE_BYTES + 1))

    controller = TXSerialController()
    controller.is_connected = True
    controller.serial_obj = object()
    controller._dma_capable = False

    sent_parts: list[tuple[int, int]] = []

    def fake_send_stream(
        _path: Path,
        part: bytes,
        _name: bytes,
        chunk_size: int,
        _tid: int,
        _crc: int,
        rounds: int,
    ) -> bool:
        sent_parts.append((len(part), chunk_size))
        assert rounds == 3
        return True

    monkeypatch.setattr(controller, "_send_stream", fake_send_stream)
    monkeypatch.setattr(controller, "status", lambda *_args, **_kwargs: None)

    assert controller.send_file(file_path, chunk_bytes=300, rounds=3) is True
    assert [part_size for part_size, _chunk in sent_parts] == [
        MAX_STREAM_FILE_BYTES,
        1,
    ]
    assert all(chunk == 300 for _part_size, chunk in sent_parts)



def test_tx_rejects_filename_that_exceeds_firmware_metadata_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gui_dev_v3 import settings
    from gui_dev_v3.serial.controllers import TXSerialController

    class FakeSettingsManager:
        def __init__(self, role: str) -> None:
            assert role == "tx"

        def get(self, key: str, default: object = None) -> object:
            if key == "link/dma_mode":
                return False
            return default

    monkeypatch.setattr(settings, "SettingsManager", FakeSettingsManager)
    path = tmp_path / ("x" * (MAX_NAME_BYTES + 1))
    path.write_bytes(b"small file")

    controller = TXSerialController()
    controller.is_connected = True
    controller.serial_obj = object()
    controller._dma_capable = False
    sent = []
    monkeypatch.setattr(controller, "_send_stream", lambda *args, **kwargs: sent.append(args) or True)
    monkeypatch.setattr(controller, "status", lambda *_args, **_kwargs: None)

    assert controller.send_file(path) is False
    assert sent == []
