"""Book to Understand NPCs (B48; hints-behavior.md HT-BOOK-01 and HT-BOOK-02): slot 0 shows one
of the lines in which the speaker cannot be understood, and, without the Book of Magic, every person
shows slot 0's text (asm/ht-book-01). The spec's patch was code-read, not run; here it runs."""
from functools import cache

import pytest

from tests.emulator import INV_BOOK, Emulator
from tests.test_progressive_emulator import CAVE_MODE, Game
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, plan
from zora.generate.steps.hint_text import BOOK_SLOT_0_CLASS, POOL, WOOD_SWORD_SLOT_0_CLASS
from zora.model.enums import Destination
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.code_patch_data import PATCHES
from zora.rom.code_patches import BOOK_TO_UNDERSTAND_NPCS
from zora.rom.game_config import GameConfig
from zora.rom.layout import QUOTE_DATA_ADDRESS
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

# The b48 corpus's string: the MVP baseline's with B48 on (HT-BOOK-01's Check)
BOOK_FLAGS = "8iaDYa1PX9GK!pC9GIQIO5JJE!UJ3A"
BASELINE_FLAGS = MVP_BASELINE_LEVEL_ENCODING_OFF
SEEDS = range(3)
PERSON_TEXT_SELECTOR = 0x415
PERSON_TEXT_INDEX = 0x416
DYN_TILE_CHAR = 0x305              # DynTileBuf+3: the character the textbox writes this frame
TEXT_CHAR_MASK, SPECIAL_SPACE, LAST_CHAR_BITS = 0x3F, 0x25, 0xC0
BANK_1_FILE, BANK_1_CPU = 0x4010, 0x8000
TEXT_FRAMES = 900
# HT-BOOK-01's bytes
POINTER_LOAD, ROUTINE = 0x04847, 0x05F40
PATCH_BYTES = {POINTER_LOAD: bytes.fromhex("20309f"), ROUTINE: bytes.fromhex("ad6106d006c044f002a000b9008060")}
PRG0_POINTER_LOAD = bytes.fromhex("b90080")


@cache
def _rom(flags: str, seed: int) -> bytes:
    return generate_rom(flags, seed, remember_repo_base_rom()).rom


def _slot_0_text(rom: bytes, flags: str, seed: int) -> str:
    config = plan(flags, seed).config
    world = parse_rom(rom, GameConfig(dungeon_nothing_code=config.dungeon_nothing_code, hint_mode=config.hint_mode))
    return world.quotes[0].text.replace(CENTERING, "")


CENTERING = "~"                    # the parsed text's centering spaces


@pytest.mark.parametrize("seed", SEEDS)
def test_slot_0_shows_a_line_that_cannot_be_understood(seed: int) -> None:
    """HT-BOOK-02: with B48 slot 0 holds one of the stand-in lines; without, the wood sword cave's."""
    book_lines = {"|".join(entry.lines) for entry in POOL if entry.routing_class == BOOK_SLOT_0_CLASS}
    wood_sword = {"|".join(entry.lines) for entry in POOL if entry.routing_class == WOOD_SWORD_SLOT_0_CLASS}
    assert _slot_0_text(_rom(BOOK_FLAGS, seed), BOOK_FLAGS, seed) in book_lines
    assert _slot_0_text(_rom(BASELINE_FLAGS, seed), BASELINE_FLAGS, seed) in wood_sword


@pytest.mark.parametrize("seed", SEEDS)
def test_the_patch_is_written_only_with_b48(seed: int) -> None:
    """HT-BOOK-01's Check: $20 $30 $9F at 0x04847 with B48, PRG0's $B9 $00 $80 without; and the
    routine's fifteen bytes at 0x05F40."""
    assert dict(PATCHES[BOOK_TO_UNDERSTAND_NPCS]) == PATCH_BYTES
    book, baseline = _rom(BOOK_FLAGS, seed), _rom(BASELINE_FLAGS, seed)
    for offset, data in PATCH_BYTES.items():
        assert book[offset:offset + len(data)] == data
    assert baseline[POINTER_LOAD:POINTER_LOAD + 3] == PRG0_POINTER_LOAD
    assert set(baseline[ROUTINE:ROUTINE + len(PATCH_BYTES[ROUTINE])]) == {0xFF}


def _shown_characters(rom: bytes, selector: int) -> list[int]:
    """The characters the textbox writes for the text at `selector`, special spaces left out."""
    pointer = rom[QUOTE_DATA_ADDRESS + selector] | rom[QUOTE_DATA_ADDRESS + selector + 1] << 8
    offset, characters = pointer - BANK_1_CPU + BANK_1_FILE, []
    while True:
        value = rom[offset]
        if value & TEXT_CHAR_MASK != SPECIAL_SPACE:
            characters.append(value & TEXT_CHAR_MASK)
        if value & LAST_CHAR_BITS == LAST_CHAR_BITS:
            return characters
        offset += 1


def _watch_cave_text(rom: bytes, with_book: bool) -> tuple[int, list[int]]:
    """Enter the white-sword cave and record what its person's textbox writes: (the person's
    selector, the characters)."""
    world = parse_rom(rom, GameConfig(hint_mode=plan(BOOK_FLAGS, 0).config.hint_mode))
    screen = next(screen.screen_num for screen in world.overworld.screens
                  if screen.destination == Destination.WHITE_SWORD_CAVE)
    game = Game(rom)
    game.emu[INV_BOOK] = int(with_book)
    game.go_to_screen(screen)
    game.start_mode(CAVE_MODE)
    return _record_text(game.emu)


def _record_text(emu: Emulator) -> tuple[int, list[int]]:
    characters: list[int] = []
    index = emu[PERSON_TEXT_INDEX]
    for _ in range(TEXT_FRAMES):
        emu.run(1)
        if emu.mode == CAVE_MODE and emu[PERSON_TEXT_INDEX] != index:
            index = emu[PERSON_TEXT_INDEX]
            characters.append(emu[DYN_TILE_CHAR])
    return emu[PERSON_TEXT_SELECTOR], characters


def test_without_the_book_a_person_shows_text_0() -> None:
    """HT-BOOK-01 in play: the white-sword cave's person shows text 0 without the Book, its own
    text with it."""
    rom = _rom(BOOK_FLAGS, 0)
    selector, without = _watch_cave_text(rom, with_book=False)
    _selector, with_book = _watch_cave_text(rom, with_book=True)
    assert selector != 0
    assert without == _shown_characters(rom, 0)
    assert with_book == _shown_characters(rom, selector) != without
