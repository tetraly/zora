"""Item spots (zora/generate/item_spots.py): no room's item on a block, statue or staircase.

The floor table is the ROM's (zora/rom/parse/room_layouts.py); every item of the original game's
two quests and every T5 position stands on a square that can hold an item; a seed whose level 4
sword stands in a level 9 room with the diamond staircase has it on floor ($D6, not the stairs'
$89); and the validation step rejects an attempt with an item on such a square, whatever placed it."""
from functools import cache

import pytest

from tests.needs import needs_base_rom, needs_encoder
from tests.test_revision import needs_both, prg1
from zora.flags.codec import decode, encode
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.errors import GenerationFailure
from zora.generate.item_spots import (
    FLOORS,
    check_item_spots,
    is_item_spot,
    item_spot_positions,
    misplaced_items,
    square_at,
)
from zora.generate.pipeline import build, plan
from zora.generate.shapes.t5_positions import T5_BASE, T5_UNIVERSAL
from zora.generate.steps.add_l4_sword import L4_SWORD_ITEM
from zora.model.enums import Item, ItemPosition
from zora.model.game_world import GameWorld
from zora.model.levels import Level
from zora.model.rooms import Room
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.room_layouts import UW_COLUMNS, UW_ROWS, underworld_floors

pytestmark = needs_base_rom
SQUARE_CHARS = {0x74: ".", 0x68: ":", 0x24: "_", 0xF4: "~", 0xB0: "B", 0x94: "S", 0xB4: "s", 0x70: "X"}
# The reported flags: 2.0 beta 7 (3d06ec4), Add L4 Sword on, whose seed 214 put the level 4 sword
# on level 9's diamond staircase (room $69, layout $5A, spot $89). Later output changes moved that
# seed (shop prices, fb51249, the sword now in room $47); seed 5 (picked 2026-10-24 over seeds
# 0-299, one of 17) has the sword in a diamond-staircase room, $76. The string has Encode level
# data on, so these tests need the private encoder; a release tree skips them.
REPORTED_FLAGS, REPORTED_ZORA, REPORTED_SEED = "143oNtDD4PAvB!U8nSk4mxFW0br2w5YUspe7sx", "7.nMFPMU", 5
REPORTED_ROOM, SWORD_SPOT = 0x76, 0xD6
DIAMOND_STAIRS_PUSH, MIDDLE = 0x5A, 0x89
RIVER_LAYOUT, RIVER_SPOT = 0x18, 0xC8             # level 5's key over the water, in both T5 and PRG0


def table_of(rom: bytes) -> dict[int, tuple[str, ...]]:
    floors = underworld_floors(rom)
    return {layout: tuple("".join(SQUARE_CHARS[columns[column][row]] for column in range(UW_COLUMNS))
                          for row in range(UW_ROWS))
            for layout, columns in floors.items()}


@cache
def world(flag_string: str, seed: int, zora: str = "") -> GameWorld:
    return build(plan(flag_string, seed, zora), remember_repo_base_rom()).world


def test_the_floor_table_is_the_roms() -> None:
    assert table_of(bytes(remember_repo_base_rom())) == FLOORS


@needs_both
def test_prg1_has_the_same_floors() -> None:
    assert table_of(prg1()) == FLOORS


@pytest.mark.parametrize("dungeon_quest", [0, 1], ids=["1st quest", "2nd quest"])
def test_every_original_item_stands_on_an_item_spot(dungeon_quest: int) -> None:
    """Dungeon Quest: 1st or 2nd Quest (C02 = 0, 1): the original game's own rooms, whose 2nd
    quest puts 21 items on spots T5 does not list (level 6's triforce at $49 in layout $05)."""
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C02": dungeon_quest}))
    levels = world(flags, 1).levels
    assert sum(room.item != Item.NOTHING for level in levels for room in level.rooms) > 90
    assert misplaced_items(levels) == []


def test_every_t5_position_is_an_item_spot() -> None:
    for table in (T5_BASE, T5_UNIVERSAL):
        for layout, spots in table.items():
            assert all(is_item_spot(layout, spot) for spot in spots), (hex(layout), spots)
    assert square_at(RIVER_LAYOUT, RIVER_SPOT) == "~"


def test_the_diamond_rooms_staircase_holds_no_item() -> None:
    assert square_at(DIAMOND_STAIRS_PUSH, MIDDLE) == "X" and not is_item_spot(DIAMOND_STAIRS_PUSH, MIDDLE)
    assert square_at(DIAMOND_STAIRS_PUSH, 0x2C) == "." and is_item_spot(DIAMOND_STAIRS_PUSH, 0x2C)


def sword_in_the_diamond_room(levels: list[Level]) -> tuple[Level, Room]:
    """Level 9 and REPORTED_ROOM, which the pinned seed must still give the level 4 sword in a
    diamond-staircase room, on a level whose item positions include the stairs: otherwise output
    drift moved the seed and these tests would prove nothing."""
    level9 = next(level for level in levels if level.level_num == 9)
    room = level9.block.room(REPORTED_ROOM)
    sword = [f"${number:02X}" for number in level9.room_nums if level9.block.room(number).item == L4_SWORD_ITEM]
    assert room.item == L4_SWORD_ITEM and room.layout_code == DIAMOND_STAIRS_PUSH \
        and MIDDLE in level9.item_position_table, (
            f"seed drift: seed {REPORTED_SEED} no longer puts the level 4 sword in level 9's diamond-staircase "
            f"room ${REPORTED_ROOM:02X} (the sword is in {sword}, room ${REPORTED_ROOM:02X} has layout "
            f"${room.layout_code:02X}); re-pick a seed that does")
    return level9, room


@needs_encoder
def test_the_reported_seeds_sword_stands_on_floor() -> None:
    level9, room = sword_in_the_diamond_room(world(REPORTED_FLAGS, REPORTED_SEED, REPORTED_ZORA).levels)
    assert level9.item_position_table[room.item_position] == SWORD_SPOT


@needs_encoder
def test_the_check_rejects_an_item_on_a_staircase() -> None:
    levels = world(REPORTED_FLAGS, REPORTED_SEED, REPORTED_ZORA).levels
    check_item_spots(levels)
    level9, room = sword_in_the_diamond_room(levels)
    position = room.item_position
    room.item_position = ItemPosition(level9.item_position_table.index(MIDDLE))
    try:
        assert room.item_position not in item_spot_positions(level9, room)
        with pytest.raises(GenerationFailure, match=rf"level 9 room \${REPORTED_ROOM:02X}"):
            check_item_spots(levels)
    finally:
        room.item_position = position
