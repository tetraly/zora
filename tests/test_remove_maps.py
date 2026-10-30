"""Remove Maps, All Maps and All Compasses (B92 to B94; features-behavior.md FP-MAP-01, FP-MAP-02), on the
spec's Check strings. A pair is CP-5 and CP-5 with the setting on, the same seed (the same world,
FL-SEED-01): with Remove Maps the four level blocks differ in the 18 map bytes (6, 3, 6 and 3), each now
"no item" with its high bits kept, and in ZORA's trigger 7 to 1 on those map rooms (docs/deviations.md);
with All Maps and All Compasses the new file's starting table holds every level's map or compass.
The emulator side is tests/test_remove_maps_emulator.py."""
from collections import Counter
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.generate.pipeline import generate_rom
from zora.generate.steps.remove_maps import remove_maps
from zora.model.enums import Item, RoomAction, RoomType
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.code_patches import PRG0_START_ITEMS
from zora.rom.parse.rom_file import parse_rom
from zora.rom.start_items import COMPASS_9_INDEX, COMPASS_INDEX, MAP_9_INDEX, MAP_INDEX, start_table

pytestmark = needs_base_rom

CP5 = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A"
B92_ON = "BtH0Hdj8LFhsBw!L!jIWWh3fmMqsjAMeny0rUJ3A"
B92_POSSIBLE = "NlY0ZGRGgVG1Yoo3ZQHVFEz9EghHBWFuas8ZUJ3A"
B93_ON = "Zdp0qu9P0kpBvgbm87GTyntdh!Xges99NmGHUJ3A"
B94_ON = "1huR2WgSC2EAB5uR0XJAMJ7MXUtd6RxVf8C!ZUJ3A"
ALL_THREE = "2SPW3eCJjODOqYNeqo66HCL0TM90jJL4fIqUQUJ3A"
SEED = 100001
# The four level blocks (headered file offsets) and their item and trigger tables (E and F)
BLOCKS = (0x18710, 0x18A10, 0x18D10, 0x19010)
TABLE = 0x80
ITEM_TABLE, TRIGGER_TABLE = 4 * TABLE, 5 * TABLE
ITEM_MASK, HIGH_BITS, TRIGGER_MASK = 0x1F, 0xE0, 0x07
NOTHING_CODES = {0x03, 0x0E}            # PRG0's "no item" and ZORA's remap (game_config.DungeonNothingCode)
SEED_CODE = range(0x0AFB0, 0x0AFB4)     # FP-HASH-01's file-select code, which follows the flag string
MAPS_PER_BLOCK = (6, 3, 6, 3)


@cache
def rom(flags: str, seed: int = SEED) -> bytes:
    return generate_rom(flags, seed, remember_repo_base_rom()).rom


def maps_per_block(image: bytes) -> tuple[int, ...]:
    world = parse_rom(image)
    return tuple(sum(room.item is Item.MAP for room in block.rooms)
                 + sum(c.room_type is RoomType.ITEM_STAIRCASE and c.item is Item.MAP for c in block.staircases)
                 for block in (*world.blocks, *world.blocks_2q))


def test_remove_maps_takes_the_map_out_and_keeps_the_rest() -> None:
    world = parse_rom(remember_repo_base_rom())
    blocks = (*world.blocks, *world.blocks_2q)
    before = {(index, room.room_num): (room.item, room.room_action, room.is_dark, room.boss_sound)
              for index, block in enumerate(blocks) for room in block.rooms}
    remove_maps(blocks)
    for index, block in enumerate(blocks):
        for room in block.rooms:
            item, action, dark, sound = before[(index, room.room_num)]
            assert (room.is_dark, room.boss_sound) == (dark, sound)
            if item is Item.MAP:
                assert room.item is Item.NOTHING
                assert room.room_action is (RoomAction.ALL_DEAD if action is RoomAction.ALL_DEAD_ITEM else action)
            else:
                assert (room.item, room.room_action) == (item, action)


def test_the_pair_differs_in_the_18_map_bytes() -> None:
    """FP-MAP-01's Check, one seed: the map bytes, ZORA's trigger 7 to 1 on map rooms, the seed code."""
    off, on = rom(CP5), rom(B92_ON)
    assert maps_per_block(off) == MAPS_PER_BLOCK and maps_per_block(on) == (0, 0, 0, 0)
    kinds: Counter[str] = Counter()
    in_blocks = set()
    for start in BLOCKS:
        for room in range(TABLE):
            item, trigger = start + ITEM_TABLE + room, start + TRIGGER_TABLE + room
            in_blocks |= {item, trigger}
            if off[item] != on[item]:
                assert off[item] & ITEM_MASK == Item.MAP and on[item] & ITEM_MASK in NOTHING_CODES
                assert off[item] & HIGH_BITS == on[item] & HIGH_BITS
                kinds["map"] += 1
            if off[trigger] != on[trigger]:
                assert off[item] & ITEM_MASK == Item.MAP
                assert off[trigger] & TRIGGER_MASK == RoomAction.ALL_DEAD_ITEM
                assert on[trigger] & TRIGGER_MASK == RoomAction.ALL_DEAD
                assert off[trigger] & ~TRIGGER_MASK == on[trigger] & ~TRIGGER_MASK
                kinds["trigger"] += 1
    assert kinds["map"] == sum(MAPS_PER_BLOCK) and kinds["trigger"] > 0
    elsewhere = {i for i, (a, b) in enumerate(zip(off, on, strict=True)) if a != b} - in_blocks
    assert elsewhere <= set(SEED_CODE), sorted(f"${i:05X}" for i in elsewhere)


@pytest.mark.parametrize(("flags", "maps", "compasses"), ((B93_ON, True, False), (B94_ON, False, True),
                                                          (ALL_THREE, True, True)))
def test_the_new_file_table_holds_every_map_or_compass(flags: str, maps: bool, compasses: bool) -> None:
    world = parse_rom(rom(flags))
    assert (world.start_all_maps, world.start_all_compasses) == (maps, compasses)
    table = world.starting_items_new_file
    assert table is not None
    assert (table[MAP_INDEX], table[MAP_9_INDEX]) == ((0xFF, 0x01) if maps else (0, 0))
    assert (table[COMPASS_INDEX], table[COMPASS_9_INDEX]) == ((0xFF, 0x01) if compasses else (0, 0))
    assert maps_per_block(rom(flags)) == ((0, 0, 0, 0) if flags == ALL_THREE else MAPS_PER_BLOCK)


def test_the_start_table_changes_only_its_four_slots() -> None:
    both = start_table([], 3, 3, all_maps=True, all_compasses=True)
    assert {i for i, (a, b) in enumerate(zip(PRG0_START_ITEMS, both, strict=True)) if a != b} == {
        MAP_INDEX, MAP_9_INDEX, COMPASS_INDEX, COMPASS_9_INDEX}
    assert start_table([], 3, 3) == PRG0_START_ITEMS


def test_remove_maps_at_random_is_a_coin_per_seed() -> None:
    outcomes = {maps_per_block(rom(B92_POSSIBLE, seed)) for seed in range(1, 9)}
    assert outcomes == {MAPS_PER_BLOCK, (0, 0, 0, 0)}
