from gui_dev_v3.serial.line_buffer import SerialLineBuffer


def test_large_hex_line_is_emitted_only_after_newline():
    payload = ("RX_FILE_HEX:17:1:81920:320:ABCD:66696C652E62696E:" + ("AB" * 81920)).encode() + b"\n"
    buffer = SerialLineBuffer(max_line_bytes=len(payload))
    lines = []
    for offset in range(0, len(payload), 997):
        lines.extend(buffer.feed(payload[offset:offset + 997]))
    assert lines == [payload[:-1].decode()]
    assert buffer.pending_bytes == 0


def test_multiple_and_partial_lines_are_preserved():
    buffer = SerialLineBuffer()
    assert buffer.feed(b"RX Ready\nRX_FILE_HEX:1:") == ["RX Ready"]
    assert buffer.feed(b"2:0:0:FFFF::\n") == ["RX_FILE_HEX:1:2:0:0:FFFF::"]


def test_overlong_line_is_discarded_and_next_line_recovers():
    buffer = SerialLineBuffer(max_line_bytes=8)
    assert buffer.feed(b"123456789") == []
    assert buffer.overflow_count == 1
    assert buffer.feed(b"discarded\nOK\n") == ["OK"]
