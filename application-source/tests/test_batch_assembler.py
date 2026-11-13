import pytest
from gui_dev_v3.logic.batch_assembler import BatchAssembler

def _add(a, idx, data, now=1, tid=None, crc=True):
    return a.add_part(group_id="g", part_index=idx, part_count=2, full_crc=0x1234,
        filename="capture.bin", part_data=data, part_crc_ok=crc, part_chunks=1,
        tid=idx if tid is None else tid, now=now)

def test_reassembles_out_of_order():
    a=BatchAssembler()
    assert _add(a,2,b"b") is None
    result=_add(a,1,b"a",now=2)
    assert result["data"]==b"ab" and result["total_chunks"]==2
    assert a.pending_count==0

def test_identical_duplicate_is_idempotent():
    a=BatchAssembler()
    _add(a,1,b"a")
    assert _add(a,1,b"a",now=2,tid=99) is None
    assert _add(a,2,b"b",now=3)["data"]==b"ab"

def test_conflicting_duplicate_discards_group():
    a=BatchAssembler()
    _add(a,1,b"a")
    with pytest.raises(ValueError,match="conflicting duplicate"):
        _add(a,1,b"x",now=2)
    assert a.pending_count==0

def test_bad_crc_discards_group():
    a=BatchAssembler()
    _add(a,1,b"a")
    with pytest.raises(ValueError,match="CRC"):
        _add(a,2,b"b",crc=False)
    assert a.pending_count==0

def test_expired_incomplete_group_is_pruned():
    a=BatchAssembler(ttl_seconds=5)
    _add(a,1,b"a",now=1)
    assert a.prune_expired(now=7)==["g"]
    assert a.pending_count==0

def test_batch_byte_limit_discards_group():
    a=BatchAssembler(max_batch_bytes=1)
    _add(a,1,b"a")
    with pytest.raises(ValueError,match="byte limit"):
        _add(a,2,b"b",now=2)
    assert a.pending_count==0

def test_invalid_part_index_discards_existing_group():
    a=BatchAssembler()
    _add(a,1,b"a")
    with pytest.raises(ValueError,match="outside its declared range"):
        a.add_part(group_id="g",part_index=3,part_count=2,full_crc=0x1234,
            filename="capture.bin",part_data=b"b",part_crc_ok=True,
            part_chunks=1,tid=2,now=2)
    assert a.pending_count==0

def test_empty_part_discards_existing_group():
    a=BatchAssembler()
    _add(a,1,b"a")
    with pytest.raises(ValueError,match="empty batch parts"):
        _add(a,2,b"",now=2)
    assert a.pending_count==0

def test_metadata_change_discards_existing_group():
    a=BatchAssembler()
    _add(a,1,b"a")
    with pytest.raises(ValueError,match="metadata changed"):
        a.add_part(group_id="g",part_index=2,part_count=2,full_crc=0x5678,
            filename="capture.bin",part_data=b"b",part_crc_ok=True,
            part_chunks=1,tid=2,now=2)
    assert a.pending_count==0


def test_concurrent_parts_are_serialized_and_assembled_once():
    from concurrent.futures import ThreadPoolExecutor

    assembler = BatchAssembler()
    parts = [
        {
            "group_id": "concurrent",
            "part_index": 1,
            "part_count": 2,
            "full_crc": 0x1234,
            "filename": "concurrent.bin",
            "part_data": b"first",
            "part_crc_ok": True,
            "part_chunks": 1,
            "tid": 61,
        },
        {
            "group_id": "concurrent",
            "part_index": 2,
            "part_count": 2,
            "full_crc": 0x1234,
            "filename": "concurrent.bin",
            "part_data": b"second",
            "part_crc_ok": True,
            "part_chunks": 1,
            "tid": 62,
        },
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: assembler.add_part(**item), parts))

    completed = [result for result in results if result is not None]
    assert len(completed) == 1
    assert completed[0]["data"] == b"firstsecond"
    assert assembler.pending_count == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"part_index": "not-an-index"},
        {"part_count": "not-a-count"},
        {"full_crc": "not-a-crc"},
        {"part_chunks": "not-a-chunk-count"},
        {"tid": "not-a-tid"},
        {"part_data": None},
    ],
)
def test_malformed_field_conversion_discards_existing_group(overrides):
    a = BatchAssembler()
    _add(a, 1, b"a")
    values = {
        "group_id": "g",
        "part_index": 2,
        "part_count": 2,
        "full_crc": 0x1234,
        "filename": "capture.bin",
        "part_data": b"b",
        "part_crc_ok": True,
        "part_chunks": 1,
        "tid": 2,
        "now": 2,
    }
    values.update(overrides)

    with pytest.raises(ValueError, match="invalid batch part metadata"):
        a.add_part(**values)

    assert a.pending_count == 0
