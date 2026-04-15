"""Tests for quote parsing, including extended hint bank pointer handling."""

from zora.char_encoding import (
    CHAR_TO_BYTE,
    QUOTE_BLANK,
    QUOTE_END_BITS,
    QUOTE_LINE1_BIT,
)
from zora.parser import _decode_quote, _parse_quotes
from zora.rom_layout import NUM_QUOTES


def _encode_char(ch: str, high_bits: int = 0) -> int:
    """Encode a single character with optional high bits."""
    return CHAR_TO_BYTE[ch] | high_bits


def _build_quotes_data(pointer_offsets: list[int], text_blob: bytes) -> bytes:
    """Build a quotes_data buffer: 38-entry pointer table + text blob.

    pointer_offsets maps quote_id → absolute offset within the buffer.
    Missing ids get a pointer to a 0xFF blank byte in the text blob.
    """
    ptr_table = bytearray(NUM_QUOTES * 2)
    for qid in range(NUM_QUOTES):
        offset = pointer_offsets[qid] if qid < len(pointer_offsets) else 0
        ptr_table[qid * 2] = offset & 0xFF
        ptr_table[qid * 2 + 1] = ((offset >> 8) & 0x7F) | 0x80
    return bytes(ptr_table) + text_blob


# ---------------------------------------------------------------------------
# _decode_quote
# ---------------------------------------------------------------------------

class TestDecodeQuote:
    def test_blank_byte_returns_empty(self) -> None:
        data = bytes([QUOTE_BLANK])
        assert _decode_quote(data, 0) == ""

    def test_offset_beyond_buffer_returns_empty(self) -> None:
        data = bytes([QUOTE_BLANK])
        assert _decode_quote(data, 999) == ""

    def test_simple_one_line_quote(self) -> None:
        # "AB" with end bits on 'B'
        data = bytes([
            _encode_char("A"),
            _encode_char("B", QUOTE_END_BITS),
        ])
        assert _decode_quote(data, 0) == "AB"

    def test_two_line_quote(self) -> None:
        # "AB|CD"
        data = bytes([
            _encode_char("A"),
            _encode_char("B", QUOTE_LINE1_BIT),
            _encode_char("C"),
            _encode_char("D", QUOTE_END_BITS),
        ])
        assert _decode_quote(data, 0) == "AB|CD"

    def test_truncated_data_does_not_crash(self) -> None:
        """If the buffer ends before a quote terminator, don't crash."""
        data = bytes([_encode_char("A"), _encode_char("B")])
        # No end bits — will hit end of buffer without a terminator.
        # Should return without raising, even if the result is incomplete.
        result = _decode_quote(data, 0)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _parse_quotes — extended hint bank regression (IndexError)
# ---------------------------------------------------------------------------

class TestParseQuotesExtendedHintBank:
    """Regression test for the rerandomize crash.

    When extended hints are active, the serializer writes CPU addresses
    (e.g. 0x9xxx) into the pointer table instead of buffer-relative offsets.
    The parser must not crash when those pointers exceed the buffer size.
    """

    def test_out_of_range_pointers_return_blank_quotes(self) -> None:
        """Pointers beyond the buffer should produce blank quote text."""
        ptr_table_size = NUM_QUOTES * 2
        # One real quote at the start of the text area
        real_text = bytes([
            _encode_char("H"),
            _encode_char("I", QUOTE_END_BITS),
        ])
        blank = bytes([QUOTE_BLANK])
        text_blob = real_text + blank

        pointer_offsets: list[int] = []
        for qid in range(NUM_QUOTES):
            if qid == 0:
                # Valid: points into the text area
                pointer_offsets.append(ptr_table_size)
            elif qid == 1:
                # Valid: points to the blank byte
                pointer_offsets.append(ptr_table_size + len(real_text))
            else:
                # Simulate extended hint bank CPU address (out of range)
                pointer_offsets.append(0x9000 + qid * 0x20)

        data = _build_quotes_data(pointer_offsets, text_blob)
        quotes = _parse_quotes(data)

        assert len(quotes) == NUM_QUOTES
        assert quotes[0].text == "HI"
        assert quotes[0].quote_id == 0
        assert quotes[1].text == ""
        assert quotes[1].quote_id == 1
        # All out-of-range quotes should be blank, not crash
        for q in quotes[2:]:
            assert q.text == ""

    def test_all_pointers_out_of_range(self) -> None:
        """If every pointer is out of range, all quotes should be blank."""
        pointer_offsets = [0x9000 + i * 0x20 for i in range(NUM_QUOTES)]
        # Minimal text blob — just needs to be non-empty for the buffer
        data = _build_quotes_data(pointer_offsets, bytes([QUOTE_BLANK]))
        quotes = _parse_quotes(data)

        assert len(quotes) == NUM_QUOTES
        for q in quotes:
            assert q.text == ""
