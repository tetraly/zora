"""Blank hints (C03 = 5; HT-HINT-07) in the emulator: a person with an empty text draws no tile. The
game draws every text's last character, so ZORA's empty text (one space with the end mark) put a
space tile where the text starts ($21A4), a black square on a dungeon's floor (a player's report,
2026-10-28; docs/reports/blank-hints-stray-tile.md). ht-hint-07 ends that tile's transfer.

On the spec's Blank string, seed 1: an elder's room and a bomb upgrader's keep their floor tile at the
text's start, and the person's text still ends (the person's state moves on, as before the fix); the
toll's room ($14 of level 6) and level 9's entrance person ($60), whose texts are real, draw as
before; the same ROM with ht-hint-07's bytes put back to the base's draws the stray tile; all of it
on PRG0 and on PRG1 (bank 1 is the same in both). Other hint styles leave the patch out."""
from functools import cache

import pytest

from tests.emulator import OBJ_STATE
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import Console
from tests.test_revision import prg1
from zora.generate.pipeline import build, finish, plan
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.code_patch_data import PATCHES
from zora.rom.code_patches import BLANK_HINTS

pytestmark = needs_base_rom
BLANK, DECEPTION = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ4R", "8hq4BeR1JXo89BJ2!TFpTP02u8UJ1u"
TEXT_START = 0x21A4            # the nametable address of the text's first character
TEXT_ROWS, TEXT_ROWS_SIZE = 0x21A0, 0x60   # the nametable rows the text's three lines are drawn in
PERSON_SLOT = 1
TEXT_FRAMES = 400              # long enough for the longest text to finish
# (level, room) of seed 1's persons: an elder and a bomb upgrader with empty texts; the toll and level
# 9's entrance person, with real texts
EMPTY_TEXT_ROOMS = ((1, 0x56), (3, 0x0B))
REAL_TEXT_ROOMS = ((6, 0x14), (9, 0x60))


def base_rom(on_prg1: bool) -> bytes:
    return prg1() if on_prg1 else remember_repo_base_rom()


@cache
def rom(flag_string: str, on_prg1: bool = False) -> bytes:
    base = base_rom(on_prg1)
    return finish(build(plan(flag_string, 1), base), base)


@cache
def without_fix(on_prg1: bool) -> bytes:
    """The Blank ROM with ht-hint-07's bytes put back to the base's."""
    base, data = base_rom(on_prg1), bytearray(rom(BLANK, on_prg1))
    for offset, piece in PATCHES[BLANK_HINTS]:
        assert isinstance(piece, bytes)
        data[offset:offset + len(piece)] = base[offset:offset + len(piece)]
    return bytes(data)


def visit(data: bytes, level: int, room: int) -> tuple[int, int, int]:
    """(the tile at the text's start on entry, after the text, the person's state after it)."""
    console = Console(data)
    console.enter_room(level, room)
    before = console.emu.nametable(TEXT_START, 1)[0]
    console.emu.run(TEXT_FRAMES)
    return before, console.emu.nametable(TEXT_START, 1)[0], console.emu[OBJ_STATE + PERSON_SLOT]


def test_only_blank_hints_write_the_patch() -> None:
    base = remember_repo_base_rom()
    for offset, piece in PATCHES[BLANK_HINTS]:
        assert isinstance(piece, bytes)
        assert rom(BLANK)[offset:offset + len(piece)] == piece
        assert rom(DECEPTION)[offset:offset + len(piece)] == base[offset:offset + len(piece)]


@pytest.mark.parametrize("on_prg1", [False, True])
@pytest.mark.parametrize(("level", "room"), EMPTY_TEXT_ROOMS)
def test_an_empty_text_draws_no_tile(level: int, room: int, on_prg1: bool) -> None:
    before, after, state = visit(rom(BLANK, on_prg1), level, room)
    unfixed_before, unfixed_after, unfixed_state = visit(without_fix(on_prg1), level, room)
    assert after == before
    assert (unfixed_before, unfixed_after) == (before, 0x24)      # the stray space tile, before the fix
    assert state == unfixed_state                                 # the text ends as it did


def text_rows(data: bytes, level: int, room: int) -> tuple[bytes, int]:
    """The text's nametable rows once it has run, and the person's state."""
    console = Console(data)
    console.enter_room(level, room)
    console.emu.run(TEXT_FRAMES)
    return console.emu.nametable(TEXT_ROWS, TEXT_ROWS_SIZE), console.emu[OBJ_STATE + PERSON_SLOT]


@pytest.mark.parametrize("on_prg1", [False, True])
@pytest.mark.parametrize(("level", "room"), REAL_TEXT_ROOMS)
def test_a_real_text_draws_as_before(level: int, room: int, on_prg1: bool) -> None:
    rows, state = text_rows(rom(BLANK, on_prg1), level, room)
    assert (rows, state) == text_rows(without_fix(on_prg1), level, room)
    assert len(set(rows)) > 2                                     # letters, not only floor and spaces
