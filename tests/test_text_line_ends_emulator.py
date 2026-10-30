"""A line the font cannot end, in the emulator (zora/rom/text_encoding.py closed_line). The quote
encoder writes a character the font lacks as the pad tile, and the person text drawer skips the pad
tile before it reads the tile's line or end bits (Z_01.asm @WriteChar), so a line ending on one ran
on into the next, past the box's right edge (the bug aa19038 fixed for the level word). Every line
encoder now closes its line with a space.

Seed 6 of the MVP baseline, every person text the pointer table reaches overwritten in place (where
it is long enough) by a two-line text whose first line ends on a character the font lacks: each
person room of levels 1-8 draws inside the box's 24 columns, the columns either side as in the
finished ROM; without closed_line some room's text runs past them."""
import pytest

import zora.rom.serialize.text as quote_text
from tests.needs import needs_base_rom
from tests.test_level_word_hints_emulator import finished, outside_the_box, person_rooms
from zora.rom.player_settings import hint_text_offsets, text_body

pytestmark = [needs_base_rom, pytest.mark.slow]
TEXT = "WHERE IS IT;|SECRET"        # ";" is not in the font: the quote encoder writes the pad tile
ROOMS = 6                           # the first person rooms of levels 1-8, enough to reach a rewritten text


def with_text(rom: bytes, text: bytes) -> bytes:
    """`rom` with every person text at least as long as `text` replaced by it in place (the old
    text's tail after the new end bits is never read)."""
    out = bytearray(rom)
    for offset in hint_text_offsets(rom):
        if len(text_body(rom, offset)) >= len(text):
            out[offset:offset + len(text)] = text
    return bytes(out)


def overflowing_rooms(rom: bytes) -> list[tuple[int, int]]:
    rooms = person_rooms()[:ROOMS]
    return [(level, room) for level, room in rooms
            if outside_the_box(rom, level, room) != outside_the_box(finished(), level, room)]


def test_a_line_ending_on_a_missing_character_stays_in_the_box() -> None:
    text = bytes(quote_text._encode_quote(TEXT, center=True))
    assert overflowing_rooms(with_text(finished(), text)) == []


def test_without_closed_line_it_overflows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(quote_text, "closed_line", lambda tiles: tiles)
    text = bytes(quote_text._encode_quote(TEXT, center=True))
    assert overflowing_rooms(with_text(finished(), text))
