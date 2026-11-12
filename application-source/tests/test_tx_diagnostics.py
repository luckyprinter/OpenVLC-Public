"""Regression tests for TX diagnostic metric parsing."""
from __future__ import annotations

from gui_dev_v3.tx.backends.physical import TXPhysicalBackend


def test_elapsed_time_parser_accepts_firmware_mm_ss_mmm_format():
    assert TXPhysicalBackend._elapsed_ms("02:03:045") == 123045


def test_elapsed_time_parser_rejects_malformed_values():
    for value in ("", None, "2:60:000", "2:03:1000", "-1:00:000", "not-time"):
        assert TXPhysicalBackend._elapsed_ms(value) is None


def test_optional_transfer_metrics_cannot_break_status_callback():
    parse = TXPhysicalBackend._safe_nonnegative_int
    assert parse(123) == 123
    assert parse("456") == 456
    assert parse(None) == 0
    assert parse("unexpected") == 0
    assert parse(-9) == 0


def test_transfer_size_bucket_boundaries():
    bucket = TXPhysicalBackend._diagnostic_size_bucket
    assert bucket(0) == "empty"
    assert bucket(1023) == "under_1kib"
    assert bucket(1024) == "1_to_16kib"
    assert bucket(16 * 1024) == "16_to_80kib"
    assert bucket(80 * 1024) == "16_to_80kib"
    assert bucket(80 * 1024 + 1) == "over_80kib"
