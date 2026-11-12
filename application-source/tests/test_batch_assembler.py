import pytest

from gui_dev_v3.logic.batch_assembler import BatchAssembler


def test_parts_are_reassembled_in_index_order():
    assembler = BatchAssembler()
    assert assembler.add_part(group_id="1", part_index=2, part_count=2, full_crc=0x1234,
                              filename="file.bin", part_data=b"world", part_crc_ok=True,
                              part_chunks=2, tid=22, now=1.0) is None
    result = assembler.add_part(group_id="1", part_index=1, part_count=2, full_crc=0x1234,
                                filename="file.bin", part_data=b"hello ", part_crc_ok=True,
                                part_chunks=3, tid=21, started_monotonic=0.5, now=2.0)
    assert result["data"] == b"hello world"
    assert result["total_chunks"] == 5
    assert result["last_tid"] == 22
    assert assembler.pending_count == 0


def test_identical_duplicate_part_is_idempotent():
    assembler = BatchAssembler()
    assembler.add_part(group_id="2", part_index=1, part_count=2, full_crc=0x2222,
                       filename="x.bin", part_data=b"old", part_crc_ok=True,
                       part_chunks=2, tid=1, now=1.0)
    # A retransmitted copy must not change bytes, chunk counts, or transfer identity.
    assert assembler.add_part(group_id="2", part_index=1, part_count=2, full_crc=0x2222,
                              filename="x.bin", part_data=b"old", part_crc_ok=True,
                              part_chunks=2, tid=99, now=2.0) is None
    result = assembler.add_part(group_id="2", part_index=2, part_count=2, full_crc=0x2222,
                                filename="x.bin", part_data=b"!", part_crc_ok=True,
                                part_chunks=1, tid=2, now=3.0)
    assert result["data"] == b"old!"
    assert result["total_chunks"] == 3
    assert result["last_tid"] == 2


def test_conflicting_duplicate_part_discards_ambiguous_batch():
    assembler = BatchAssembler()
    assembler.add_part(group_id="3", part_index=1, part_count=2, full_crc=0x3333,
                       filename="x.bin", part_data=b"first", part_crc_ok=True,
                       part_chunks=2, tid=1, now=1.0)
    with pytest.raises(ValueError, match="conflicting duplicate"):
        assembler.add_part(group_id="3", part_index=1, part_count=2, full_crc=0x3333,
                           filename="x.bin", part_data=b"other", part_crc_ok=True,
                           part_chunks=2, tid=2, now=2.0)
    assert assembler.pending_count == 0


def test_invalid_index_crc_and_metadata_are_rejected():
    assembler = BatchAssembler()
    with pytest.raises(ValueError):
        assembler.add_part(group_id="x", part_index=0, part_count=2, full_crc=1,
                           filename="x.bin", part_data=b"x", part_crc_ok=True,
                           part_chunks=1, tid=1, now=1.0)
    with pytest.raises(ValueError):
        assembler.add_part(group_id="x", part_index=1, part_count=2, full_crc=1,
                           filename="x.bin", part_data=b"x", part_crc_ok=False,
                           part_chunks=1, tid=1, now=1.0)
    assembler.add_part(group_id="x", part_index=1, part_count=2, full_crc=1,
                       filename="x.bin", part_data=b"x", part_crc_ok=True,
                       part_chunks=1, tid=1, now=1.0)
    with pytest.raises(ValueError):
        assembler.add_part(group_id="x", part_index=2, part_count=2, full_crc=2,
                           filename="x.bin", part_data=b"y", part_crc_ok=True,
                           part_chunks=1, tid=2, now=2.0)
    assert assembler.pending_count == 0


def test_incomplete_groups_expire():
    assembler = BatchAssembler(ttl_seconds=10)
    assembler.add_part(group_id="stale", part_index=1, part_count=2, full_crc=1,
                       filename="x.bin", part_data=b"x", part_crc_ok=True,
                       part_chunks=1, tid=1, now=1.0)
    assert assembler.prune_expired(now=12.0) == ["stale"]
    assert assembler.pending_count == 0
