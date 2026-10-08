"""The entry-side walk (acceptance.md VA-REJ-18) and the hint pass's
inside-dungeon probe (hints-behavior.md HT-HINT-01 rule 2) against the
spec's per-room and per-record checkpoints on the corpus finals of seeds 1
and 2, and the level-9 $4B room's sides (late-gate.md VA-REJ-19)."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.measure.checkpoints.dungeon_room_shuffle import LEVEL9_PERSON_SIDE_KEYS, level9_person_sides
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng
from zora.model.enums import Item, Side
from zora.model.levels import Level
from zora.generate.dungeon_walk import STAIRS, walk_level
from zora.generate.generation_pass import generate_shapes
from zora.generate.steps.hint_text import INSIDE_MEANS, inside_dungeon_needs, item_place, sword_enters
from zora.generate.shapes.options import ShapeOptions


# The finished corpus ROMs: the folder ZORA_CORPUS names (scripts/verify.sh sets it); the tests
# that need them skip without it.
CORPUS = Path(os.environ.get("ZORA_CORPUS", "temp/no-corpus"))
SIDE_LETTERS = ((Side.NORTH, "N"), (Side.SOUTH, "S"), (Side.WEST, "W"), (Side.EAST, "E"), (STAIRS, "X"))

# VA-REJ-18's per-room checkpoint: seed, level, room, the sides it is
# entered by holding the sword, and holding the sword and the ladder
ENTERED_BY = """
    1 8  10 -     SE
    1 8  11 -     E
    1 8  12 -     SW
    1 8  13 -     SW
    1 8  26 -     NSE
    1 8  27 -     WE
    1 8  28 -     NSWE
    1 8  29 -     NW
    1 8  41 -     SE
    1 8  42 -     NWE
    1 8  43 -     WE
    1 8  44 -     NSWX
    1 8  55 -     E
    1 8  56 -     WE
    1 8  57 -     NSW
    1 8  58 -     S
    1 8  60 -     NE
    1 8  61 -     W
    1 8  72 -     -
    1 8  73 -     NE
    1 8  74 -     NSWEX
    1 8  75 -     W
    1 8  87 -     -
    1 8  88 -     -
    1 8  90 -     NS
    1 8 106 S     NS
    1 8 121 SE    SE
    1 8 122 NWE   NWE
    1 8 123 W     W
    2 4  13 -     SE
    2 4  14 -     SW
    2 4  29 -     NSE
    2 4  30 -     WE
    2 4  31 -     W
    2 4  43 -     E
    2 4  44 -     WE
    2 4  45 -     NSW
    2 4  47 -     S
    2 4  61 -     NSE
    2 4  62 -     SWE
    2 4  63 -     NW
    2 4  76 -     S
    2 4  77 -     NSE
    2 4  78 -     NSW
    2 4  92 -     NE
    2 4  93 -     NWE
    2 4  94 -     NSWE
    2 4  95 -     W
    2 4 110 S     NS
    2 4 126 NSE   NSE
    2 4 127 W     W
"""

# HT-HINT-01's per-record checkpoint: seed, level, room, item, room kind,
# enterable with the sword alone, and which means open it
RECORDS = """
    1 1 103 $05 room   yes -
    1 2  92 $10 room   yes -
    1 3   7 $0D cellar no  recorder
    1 4  32 $14 cellar no  none
    1 5  29 $07 room   yes -
    1 5  63 $13 cellar yes -
    1 6  20 $1D room   yes -
    1 6  91 $0A cellar yes -
    1 7  15 $11 cellar no  ladder
    1 7  30 $0C room   no  ladder
    1 8  42 $1E room   no  ladder
    1 8  45 $09 cellar no  ladder
    1 8  47 $0B cellar no  ladder
    1 9  68 $02 cellar yes -
    2 1   0 $1D cellar yes -
    2 1  88 $13 room   yes -
    2 2   4 $10 room   yes -
    2 3  38 $05 room   yes -
    2 4  34 $0A cellar no  ladder
    2 5  26 $09 room   yes -
    2 5  36 $1E cellar yes -
    2 6  79 $0D cellar yes -
    2 7   7 $0B cellar yes -
    2 7  65 $07 room   yes -
    2 8  13 $0C cellar no  recorder
    2 8  18 $14 cellar no  ladder
"""


def _finals(seed: int) -> list[Level]:
    path = CORPUS / f"seed-{seed:04d}.nes"
    if not path.exists():
        pytest.skip("corpus missing")
    return parse_rom(load_rom(path)).levels


def _level(levels: list[Level], level_num: int) -> Level:
    return next(level for level in levels if level.level_num == level_num)


def _letters(sides: set[int]) -> str:
    return "".join(letter for side, letter in SIDE_LETTERS if side in sides) or "-"


def test_entered_sides_match_the_spec_checkpoint() -> None:
    for line in ENTERED_BY.strip().splitlines():
        seed, level, room, by_sword, by_ladder = line.split()
        final = _level(_finals(int(seed)), int(level))
        for held, expected in ((frozenset({Item.WOOD_SWORD}), by_sword),
                               (frozenset({Item.WOOD_SWORD, Item.LADDER}), by_ladder)):
            walk = walk_level(final, held, is_last_boss_open=False, uses_families=True)
            assert _letters(walk.reached.get(int(room), set())) == expected, line


def test_inside_dungeon_probe_matches_the_spec_checkpoint() -> None:
    forms = {form for _means, form in INSIDE_MEANS}
    for line in RECORDS.strip().splitlines():
        seed, level, room, item, kind, enterable, opened_by = line.split()
        place = item_place(_finals(int(seed)), int(level), int(item[1:], 16))
        assert place is not None, line
        assert (place.room if kind == "room" else place.cellar) == int(room), line
        assert sword_enters(place) == (enterable == "yes"), line
        if enterable == "no":
            needs = inside_dungeon_needs(place, int(item[1:], 16))
            assert set(needs) <= forms
            assert (",".join(needs) or "none") == opened_by, line


def test_level9_person_room_sides() -> None:
    """VA-REJ-19: north, east and west are shutter or wall, never all walls."""
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    rom = load_rom(verify_base_rom())
    for seed in range(3):
        gw = parse_rom(rom)
        generate_shapes(gw, Rng(seed), ShapeOptions())
        assert level9_person_sides(parse_rom(serialize_to_rom(gw, rom))) in LEVEL9_PERSON_SIDE_KEYS[:-1]
