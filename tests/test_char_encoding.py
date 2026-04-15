"""Tests for zora/char_encoding.py."""

from zora.char_encoding import (
    BYTE_TO_CHAR,
    CHAR_TO_BYTE,
    QUOTE_BLANK,
    QUOTE_CHAR_MASK,
    QUOTE_END_BITS,
    QUOTE_LINE1_BIT,
    QUOTE_LINE2_BIT,
)


def test_byte_to_char_is_inverse_of_char_to_byte():
    """BYTE_TO_CHAR must be the exact inverse of CHAR_TO_BYTE — no entries lost."""
    assert len(BYTE_TO_CHAR) == len(CHAR_TO_BYTE), (
        "CHAR_TO_BYTE has collisions: two characters map to the same byte code, "
        "so BYTE_TO_CHAR has fewer entries than CHAR_TO_BYTE"
    )
    for char, byte in CHAR_TO_BYTE.items():
        assert BYTE_TO_CHAR[byte] == char, (
            f"BYTE_TO_CHAR[{byte:#x}] = {BYTE_TO_CHAR.get(byte)!r}, expected {char!r}"
        )


def test_char_to_byte_roundtrip():
    """Every character in CHAR_TO_BYTE survives a char→byte→char roundtrip."""
    for char, byte in CHAR_TO_BYTE.items():
        assert BYTE_TO_CHAR[byte] == char


def test_no_duplicate_byte_values():
    """No two characters may share the same byte code."""
    seen: dict[int, str] = {}
    for char, byte in CHAR_TO_BYTE.items():
        assert byte not in seen, (
            f"Byte {byte:#x} is mapped to both {seen[byte]!r} and {char!r}"
        )
        seen[byte] = char


def test_quote_blank_not_in_char_mask():
    """QUOTE_BLANK (0xFF) must not be reachable via QUOTE_CHAR_MASK (0x3F = 63 values).

    If a valid character code could equal 0xFF & QUOTE_CHAR_MASK, the decoder
    would misinterpret a blank-quote sentinel as a character.
    """
    assert QUOTE_BLANK & QUOTE_CHAR_MASK not in BYTE_TO_CHAR, (
        f"QUOTE_BLANK & QUOTE_CHAR_MASK ({QUOTE_BLANK & QUOTE_CHAR_MASK:#x}) "
        "collides with a valid character code"
    )


def test_quote_bit_constants_are_mutually_exclusive():
    """The three quote control values must be distinct and fit in 2 high bits."""
    controls = [QUOTE_LINE1_BIT, QUOTE_LINE2_BIT, QUOTE_END_BITS]
    assert len(set(controls)) == 3, "Quote bit constants are not all distinct"
    for val in controls:
        assert val & ~QUOTE_END_BITS == 0, (
            f"Quote bit constant {val:#x} uses bits outside the high-2-bit mask"
        )


def test_quote_end_bits_is_combination_of_line_bits():
    """QUOTE_END_BITS must equal QUOTE_LINE1_BIT | QUOTE_LINE2_BIT."""
    assert QUOTE_END_BITS == QUOTE_LINE1_BIT | QUOTE_LINE2_BIT


def test_quote_char_mask_does_not_overlap_control_bits():
    """QUOTE_CHAR_MASK must not overlap with any of the high-2-bit control values."""
    assert QUOTE_CHAR_MASK & QUOTE_END_BITS == 0, (
        "QUOTE_CHAR_MASK overlaps with quote control bits"
    )
