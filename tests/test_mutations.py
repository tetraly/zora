"""
Mutation tests: parse → modify data model → serialize → verify only expected bytes changed.
"""
import copy
from pathlib import Path

from zora.data_model import Enemy, EnemySpec, Item, Shop
from zora.parser import load_bin_files, parse_game_world
from zora.rom_layout import (
    CAVE_ITEM_DATA_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_INFO_ADDRESS,
    LEVEL_INFO_SIZE,
    RECORDER_WARP_DESTINATIONS_ADDRESS,
    START_SCREEN_ADDRESS,
)
from zora.serializer import serialize_game_world

TEST_DATA = Path(__file__).parent.parent / "rom_data"
LEVEL_TABLE_SIZE = 0x80


def _dungeon_item_byte(item: Item) -> int:
    """Return the dungeon item code the serializer writes for an Item."""
    return 0x03 if item == Item.NOTHING else item.value


def _setup():
    originals = {
        "level_1_6_data.bin": (TEST_DATA / "level_1_6_data.bin").read_bytes(),
        "level_7_9_data.bin": (TEST_DATA / "level_7_9_data.bin").read_bytes(),
        "level_info.bin":     (TEST_DATA / "level_info.bin").read_bytes(),
        "overworld_data.bin": (TEST_DATA / "overworld_data.bin").read_bytes(),
        "armos_item.bin":     (TEST_DATA / "armos_item.bin").read_bytes(),
        "coast_item.bin":     (TEST_DATA / "coast_item.bin").read_bytes(),
    }
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    return gw, originals


def _diff_bytes(a: bytes, b: bytes, label: str) -> list[tuple[int, int, int]]:
    """Return list of (offset, old, new) for differing bytes."""
    assert len(a) == len(b), f"{label}: length mismatch {len(a)} vs {len(b)}"
    return [(i, a[i], b[i]) for i in range(len(a)) if a[i] != b[i]]


def test_change_room_item():
    """Changing a room's item updates only table 4 bits 4-0 for that room slot."""
    gw, originals = _setup()
    gw = copy.deepcopy(gw)

    # Pick level 1, first room that doesn't already have a KEY
    lvl = gw.levels[0]
    target = next(r for r in lvl.rooms if r.item != Item.KEY)
    old_item = target.item
    target.item = Item.KEY

    patch = serialize_game_world(gw, originals)
    grid = patch.data[LEVEL_1_6_DATA_ADDRESS]
    orig_grid = originals["level_1_6_data.bin"]

    diffs = _diff_bytes(orig_grid, grid, "level_1_6_data")

    # Only table 4 byte for this room should change
    expected_offset = 4 * LEVEL_TABLE_SIZE + target.room_num
    assert len(diffs) == 1, f"Expected 1 diff, got {len(diffs)}: {diffs}"
    offset, old_val, new_val = diffs[0]
    assert offset == expected_offset
    assert new_val & 0x1F == _dungeon_item_byte(Item.KEY)
    assert old_val & 0x1F == _dungeon_item_byte(old_item)
    # High 3 bits (dark, boss_cry_2, boss_cry_1) must be preserved
    assert (new_val & 0xE0) == (old_val & 0xE0)


def test_change_room_enemy():
    """Changing a room's enemy updates table 2 (enemy bits) and table 3 (mixed flag)."""
    gw, originals = _setup()
    gw = copy.deepcopy(gw)

    # Pick level 2, first room with a simple (non-mixed) enemy
    lvl = gw.levels[1]
    target = next(r for r in lvl.rooms
                  if not r.enemy_spec.is_group and r.enemy_spec.enemy != Enemy.STALFOS)
    target.enemy_spec = EnemySpec(enemy=Enemy.STALFOS)

    patch = serialize_game_world(gw, originals)
    grid = patch.data[LEVEL_1_6_DATA_ADDRESS]
    orig_grid = originals["level_1_6_data.bin"]

    diffs = _diff_bytes(orig_grid, grid, "level_1_6_data")

    changed_offsets = {d[0] for d in diffs}
    t2_offset = 2 * LEVEL_TABLE_SIZE + target.room_num
    t3_offset = 3 * LEVEL_TABLE_SIZE + target.room_num

    # Table 2 must have changed (enemy bits 5-0)
    assert t2_offset in changed_offsets or grid[t2_offset] & 0x3F == Enemy.STALFOS.value
    # Table 3 mixed bit must be clear (STALFOS is not a mixed group)
    assert grid[t3_offset] & 0x80 == 0
    # No other tables should change
    other = changed_offsets - {t2_offset, t3_offset}
    assert not other, f"Unexpected changes at offsets: {[hex(o) for o in other]}"


def test_change_entrance_room():
    """Changing level.entrance_room updates level_info block[0x2F] only."""
    gw, originals = _setup()
    gw = copy.deepcopy(gw)

    lvl = gw.levels[2]  # level 3
    old_entrance = lvl.entrance_room
    # Pick a room that's in the level but not currently the entrance
    new_entrance = next(r.room_num for r in lvl.rooms if r.room_num != old_entrance)
    lvl.entrance_room = new_entrance

    patch = serialize_game_world(gw, originals)
    info = patch.data[LEVEL_INFO_ADDRESS]
    orig_info = originals["level_info.bin"]

    diffs = _diff_bytes(orig_info, info, "level_info")

    slot_base = 3 * LEVEL_INFO_SIZE  # level 3 is slot index 3
    expected_offset = slot_base + 0x2F
    assert len(diffs) == 1, f"Expected 1 diff, got {len(diffs)}: {[(hex(o), hex(a), hex(b)) for o,a,b in diffs]}"
    offset, old_val, new_val = diffs[0]
    assert offset == expected_offset
    assert new_val == new_entrance
    assert old_val == old_entrance


def test_change_recorder_warp_destination():
    """Changing one recorder warp destination updates exactly one byte."""
    gw, originals = _setup()
    gw = copy.deepcopy(gw)

    old_dest = gw.overworld.recorder_warp_destinations[0]
    new_dest = (old_dest + 1) & 0x7F
    gw.overworld.recorder_warp_destinations[0] = new_dest

    patch = serialize_game_world(gw, originals)
    got = patch.data[RECORDER_WARP_DESTINATIONS_ADDRESS]
    orig = (TEST_DATA / "recorder_warp_destinations.bin").read_bytes()

    diffs = _diff_bytes(orig, got, "recorder_warp_destinations")
    assert len(diffs) == 1
    offset, old_val, new_val = diffs[0]
    assert offset == 0
    assert old_val == old_dest
    assert new_val == new_dest


def test_change_start_screen():
    """Changing start_screen updates exactly one byte."""
    gw, originals = _setup()
    gw = copy.deepcopy(gw)

    old_screen = gw.overworld.start_screen
    new_screen = (old_screen + 1) & 0x7F
    gw.overworld.start_screen = new_screen

    patch = serialize_game_world(gw, originals)
    got = patch.data[START_SCREEN_ADDRESS]
    orig = (TEST_DATA / "start_screen.bin").read_bytes()

    diffs = _diff_bytes(orig, got, "start_screen")
    assert len(diffs) == 1
    assert diffs[0] == (0, old_screen, new_screen)


def test_change_cave_item():
    """Changing a cave item updates exactly one byte in cave_item_data, preserving flag bits."""
    gw, originals = _setup()
    gw = copy.deepcopy(gw)

    # Find a shop cave and change its first item slot
    shop = next(c for c in gw.overworld.caves if isinstance(c, Shop))
    old_item = shop.items[0].item
    new_item = Item.KEY if old_item != Item.KEY else Item.BOMBS
    shop.items[0].item = new_item

    # Find which cave index this shop maps to
    cave_item_orig = (TEST_DATA / "cave_item_data.bin").read_bytes()

    patch = serialize_game_world(gw, originals)
    got = patch.data[CAVE_ITEM_DATA_ADDRESS]

    diffs = _diff_bytes(cave_item_orig, got, "cave_item_data")
    assert len(diffs) == 1, f"Expected 1 diff, got {len(diffs)}: {diffs}"
    offset, old_val, new_val = diffs[0]
    assert new_val & 0x1F == new_item.value
    assert old_val & 0x1F == old_item.value
    # Flag bits preserved
    assert (new_val & 0xE0) == (old_val & 0xE0)
