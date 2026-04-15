"""
Round-trip test: parse → serialize must produce bit-identical output.
"""
from pathlib import Path

import pytest

from flags.flags_generated import Flags, Tristate
from zora.game_config import resolve_game_config
from zora.parser import load_bin_files, load_bin_files_q2, parse_game_world
from zora.patches import build_behavior_patch
from zora.rng import SeededRng
from zora.rom_layout import (
    OW_SPRITES_ADDRESS,
    ANY_ROAD_SCREENS_ADDRESS,
    ARMOS_ITEM_ADDRESS,
    ASM_NOTHING_CODE_PATCH_OFFSET,
    ASM_NOTHING_CODE_PATCH_VALUE,
    BOSS_SET_A_SPRITES_ADDRESS,
    BOSS_SET_B_SPRITES_ADDRESS,
    BOSS_SET_C_SPRITES_ADDRESS,
    BOSS_SPRITE_SET_POINTERS_ADDRESS,
    CAVE_ITEM_DATA_ADDRESS,
    CAVE_PRICE_DATA_ADDRESS,
    COAST_ITEM_ADDRESS,
    DOOR_REPAIR_CHARGE_ADDRESS,
    DUNGEON_COMMON_SPRITES_ADDRESS,
    ENEMY_SET_A_SPRITES_ADDRESS,
    ENEMY_SET_B_SPRITES_ADDRESS,
    ENEMY_SET_C_SPRITES_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS_Q2,
    LEVEL_7_9_DATA_ADDRESS_Q2,
    LEVEL_INFO_ADDRESS,
    LEVEL_INFO_SIZE,
    LEVEL_SPRITE_SET_POINTERS_ADDRESS,
    MAGICAL_SWORD_REQUIREMENT_ADDRESS,
    MAZE_DIRECTIONS_ADDRESS,
    QUOTE_DATA_ADDRESS,
    RECORDER_WARP_DESTINATIONS_ADDRESS,
    RECORDER_WARP_Y_COORDINATES_ADDRESS,
    START_SCREEN_ADDRESS,
    TILE_MAPPING_DATA_ADDRESS,
    TILE_MAPPING_POINTERS_ADDRESS,
    WHITE_SWORD_REQUIREMENT_ADDRESS,
)
from zora.serializer import serialize_game_world, serialize_game_world_q2

TEST_DATA = Path(__file__).parent.parent / "rom_data"


def _load_originals():
    names = [
        "level_1_6_data.bin",
        "level_7_9_data.bin",
        "level_info.bin",
        "overworld_data.bin",
        "armos_item.bin",
        "coast_item.bin",
        "white_sword_requirement.bin",
        "magical_sword_requirement.bin",
    ]
    return {n: (TEST_DATA / n).read_bytes() for n in names}


def _load_originals_q2():
    names = [
        "level_1_6_data_q2.bin",
        "level_7_9_data_q2.bin",
        "level_info_q2.bin",
    ]
    return {n: (TEST_DATA / n).read_bytes() for n in names}


def _normalize_level_grid(data: bytes) -> bytes:
    """Normalize table 4 bytes: treat item code 0x03 same as 0x0E (both = NOTHING)."""
    out = bytearray(data)
    table_4_start = 4 * 0x80
    table_4_end = 5 * 0x80
    for i in range(table_4_start, table_4_end):
        if out[i] & 0x1F == 0x03:
            out[i] = (out[i] & 0xE0) | 0x0E
    return bytes(out)


def test_level_grid_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    from zora.rom_layout import LEVEL_1_6_DATA_ADDRESS, LEVEL_7_9_DATA_ADDRESS

    for key, addr, name in [
        ("level_1_6_data.bin", LEVEL_1_6_DATA_ADDRESS, "level_1_6_data"),
        ("level_7_9_data.bin", LEVEL_7_9_DATA_ADDRESS, "level_7_9_data"),
    ]:
        got = _normalize_level_grid(patch.data[addr])
        exp = _normalize_level_grid(originals[key])
        if got != exp:
            for i, (g, e) in enumerate(zip(got, exp, strict=True)):
                if g != e:
                    table = i // 0x80
                    room = i % 0x80
                    pytest.fail(
                        f"{name} mismatch at byte {i:#x} "
                        f"(table {table}, room {room:#x}): "
                        f"got {g:#x}, expected {e:#x}"
                    )
            pytest.fail(f"{name} length mismatch: {len(got)} vs {len(exp)}")


def test_level_info_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    from zora.rom_layout import LEVEL_INFO_ADDRESS

    got = patch.data[LEVEL_INFO_ADDRESS]
    exp = originals["level_info.bin"]

    if got != exp:
        for i, (g, e) in enumerate(zip(got, exp, strict=True)):
            if g != e:
                level_num = i // LEVEL_INFO_SIZE
                offset = i % LEVEL_INFO_SIZE
                pytest.fail(
                    f"level_info mismatch at byte {i:#x} "
                    f"(level_index {level_num}, offset {offset:#x}): "
                    f"got {g:#x}, expected {e:#x}"
                )
        pytest.fail(f"level_info length mismatch: {len(got)} vs {len(exp)}")


def test_fade_palette_roundtrip():
    """fade_palette_raw (level_info block +0x7C, 96 bytes) must survive parse → serialize."""
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    level_info_original = originals["level_info.bin"]
    level_info_serialized = patch.data[LEVEL_INFO_ADDRESS]

    for lvl in gw.levels:
        block_offset = lvl.level_num * LEVEL_INFO_SIZE
        orig_fade = level_info_original[block_offset + 0x7C : block_offset + 0xDC]
        got_fade  = level_info_serialized[block_offset + 0x7C : block_offset + 0xDC]
        if orig_fade != got_fade:
            for i, (g, e) in enumerate(zip(got_fade, orig_fade, strict=True)):
                if g != e:
                    pytest.fail(
                        f"fade_palette_raw mismatch for level {lvl.level_num} "
                        f"at byte +{i:#x}: got {g:#x}, expected {e:#x}"
                    )
        assert lvl.fade_palette_raw == orig_fade, (
            f"Level {lvl.level_num}: fade_palette_raw not parsed correctly"
        )


def test_overworld_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    from zora.rom_layout import OVERWORLD_DATA_ADDRESS

    got = patch.data[OVERWORLD_DATA_ADDRESS]
    exp = originals["overworld_data.bin"]

    if got != exp:
        for i, (g, e) in enumerate(zip(got, exp, strict=True)):
            if g != e:
                table = i // 0x80
                screen = i % 0x80
                pytest.fail(
                    f"overworld_data mismatch at byte {i:#x} "
                    f"(table {table}, screen {screen:#x}): "
                    f"got {g:#x}, expected {e:#x}"
                )
        pytest.fail(f"overworld_data length mismatch: {len(got)} vs {len(exp)}")


def test_quotes_roundtrip():
    quotes_bin = TEST_DATA / "quotes_data.bin"
    if not quotes_bin.exists():
        pytest.skip("quotes_data.bin not present")

    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)

    assert len(gw.quotes) == 38

    patch = serialize_game_world(gw, originals)
    got = patch.data[QUOTE_DATA_ADDRESS]
    exp = quotes_bin.read_bytes()

    if got != exp:
        for i, (g, e) in enumerate(zip(got, exp, strict=True)):
            if g != e:
                pytest.fail(
                    f"quotes_data mismatch at byte {i:#x}: "
                    f"got {g:#x}, expected {e:#x}"
                )
        pytest.fail(f"quotes_data length mismatch: {len(got)} vs {len(exp)}")


def test_cave_data_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    for key, addr, name in [
        ("cave_item_data.bin", CAVE_ITEM_DATA_ADDRESS, "cave_item_data"),
        ("cave_price_data.bin", CAVE_PRICE_DATA_ADDRESS, "cave_price_data"),
    ]:
        exp_path = TEST_DATA / key
        if not exp_path.exists():
            pytest.skip(f"{key} not present")
        exp = exp_path.read_bytes()
        got = patch.data[addr]
        if got != exp:
            for i, (g, e) in enumerate(zip(got, exp, strict=True)):
                if g != e:
                    cave = i // 3
                    slot = i % 3
                    pytest.fail(
                        f"{name} mismatch at byte {i:#x} "
                        f"(cave {cave}, slot {slot}): "
                        f"got {g:#x}, expected {e:#x}"
                    )
            pytest.fail(f"{name} length mismatch: {len(got)} vs {len(exp)}")

    door_path = TEST_DATA / "door_repair_charge.bin"
    if door_path.exists():
        exp_door = door_path.read_bytes()[0]
        got_door = patch.data[DOOR_REPAIR_CHARGE_ADDRESS][0]
        assert got_door == exp_door, f"door_repair mismatch: got {got_door}, expected {exp_door}"


def test_recorder_warp_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    for key, addr, name in [
        ("recorder_warp_destinations.bin",  RECORDER_WARP_DESTINATIONS_ADDRESS,  "recorder_warp_destinations"),
        ("recorder_warp_y_coordinates.bin", RECORDER_WARP_Y_COORDINATES_ADDRESS, "recorder_warp_y_coordinates"),
    ]:
        exp = (TEST_DATA / key).read_bytes()
        got = patch.data[addr]
        if got != exp:
            for i, (g, e) in enumerate(zip(got, exp, strict=True)):
                if g != e:
                    pytest.fail(f"{name} mismatch at index {i}: got {g:#04x}, expected {e:#04x}")
            pytest.fail(f"{name} length mismatch: {len(got)} vs {len(exp)}")


def test_any_road_and_start_screen_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    exp_any_road = (TEST_DATA / "any_road_screens.bin").read_bytes()
    got_any_road = patch.data[ANY_ROAD_SCREENS_ADDRESS]
    assert got_any_road == exp_any_road, \
        f"any_road_screens mismatch: got {list(got_any_road)}, expected {list(exp_any_road)}"

    exp_start = (TEST_DATA / "start_screen.bin").read_bytes()
    got_start = patch.data[START_SCREEN_ADDRESS]
    assert got_start == exp_start, \
        f"start_screen mismatch: got {got_start[0]:#04x}, expected {exp_start[0]:#04x}"


def test_sprite_set_pointers_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    for key, addr, name in [
        ("level_sprite_set_pointers.bin", LEVEL_SPRITE_SET_POINTERS_ADDRESS, "level_sprite_set_pointers"),
        ("boss_sprite_set_pointers.bin",  BOSS_SPRITE_SET_POINTERS_ADDRESS,  "boss_sprite_set_pointers"),
    ]:
        exp = (TEST_DATA / key).read_bytes()
        got = patch.data[addr]
        if got != exp:
            for i in range(0, min(len(got), len(exp)), 2):
                g = got[i] | (got[i+1] << 8)
                e = exp[i] | (exp[i+1] << 8)
                if g != e:
                    pytest.fail(f"{name} mismatch at index {i//2}: got {g:#06x}, expected {e:#06x}")
            pytest.fail(f"{name} length mismatch: {len(got)} vs {len(exp)}")


def test_sprite_data_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    for key, addr in [
        ("ow_sprites.bin",             OW_SPRITES_ADDRESS),
        ("enemy_set_b_sprites.bin",    ENEMY_SET_B_SPRITES_ADDRESS),
        ("enemy_set_c_sprites.bin",    ENEMY_SET_C_SPRITES_ADDRESS),
        ("dungeon_common_sprites.bin", DUNGEON_COMMON_SPRITES_ADDRESS),
        ("enemy_set_a_sprites.bin",    ENEMY_SET_A_SPRITES_ADDRESS),
        ("boss_set_a_sprites.bin",     BOSS_SET_A_SPRITES_ADDRESS),
        ("boss_set_b_sprites.bin",     BOSS_SET_B_SPRITES_ADDRESS),
        ("boss_set_c_sprites.bin",     BOSS_SET_C_SPRITES_ADDRESS),
    ]:
        exp = (TEST_DATA / key).read_bytes()
        got = patch.data[addr]
        assert got == exp, f"{key} roundtrip mismatch"


def test_enemy_tile_maps_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    for key, addr in [
        ("tile_mapping_pointers.bin", TILE_MAPPING_POINTERS_ADDRESS),
        ("tile_mapping_data.bin",     TILE_MAPPING_DATA_ADDRESS),
    ]:
        exp = (TEST_DATA / key).read_bytes()
        got = patch.data[addr]
        assert got == exp, f"{key} roundtrip mismatch"


# ---------------------------------------------------------------------------
# Second quest round-trip tests
# ---------------------------------------------------------------------------

def test_q2_level_grid_roundtrip():
    originals_q2 = _load_originals_q2()
    bins = load_bin_files_q2(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world_q2(gw, originals_q2)

    for key, addr, name in [
        ("level_1_6_data_q2.bin", LEVEL_1_6_DATA_ADDRESS_Q2, "level_1_6_data_q2"),
        ("level_7_9_data_q2.bin", LEVEL_7_9_DATA_ADDRESS_Q2, "level_7_9_data_q2"),
    ]:
        got = _normalize_level_grid(patch.data[addr])
        exp = _normalize_level_grid(originals_q2[key])
        if got != exp:
            for i, (g, e) in enumerate(zip(got, exp, strict=True)):
                if g != e:
                    table = i // 0x80
                    room  = i % 0x80
                    pytest.fail(
                        f"{name} mismatch at byte {i:#x} "
                        f"(table {table}, room {room:#x}): "
                        f"got {g:#x}, expected {e:#x}"
                    )
            pytest.fail(f"{name} length mismatch: {len(got)} vs {len(exp)}")


def test_q2_level_info_roundtrip():
    originals_q2 = _load_originals_q2()
    bins = load_bin_files_q2(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world_q2(gw, originals_q2)

    got = patch.data[LEVEL_INFO_ADDRESS]
    exp = originals_q2["level_info_q2.bin"]

    if got != exp:
        for i, (g, e) in enumerate(zip(got, exp, strict=True)):
            if g != e:
                level_num = i // LEVEL_INFO_SIZE
                offset    = i % LEVEL_INFO_SIZE
                pytest.fail(
                    f"level_info_q2 mismatch at byte {i:#x} "
                    f"(level_index {level_num}, offset {offset:#x}): "
                    f"got {g:#x}, expected {e:#x}"
                )
        pytest.fail(f"level_info_q2 length mismatch: {len(got)} vs {len(exp)}")


def test_armos_and_coast_item_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    exp_armos = (TEST_DATA / "armos_item.bin").read_bytes()
    got_armos = patch.data[ARMOS_ITEM_ADDRESS]
    assert got_armos == exp_armos, \
        f"armos_item mismatch: got {got_armos[0]:#04x}, expected {exp_armos[0]:#04x}"

    exp_coast = (TEST_DATA / "coast_item.bin").read_bytes()
    got_coast = patch.data[COAST_ITEM_ADDRESS]
    assert got_coast == exp_coast, \
        f"coast_item mismatch: got {got_coast[0]:#04x}, expected {exp_coast[0]:#04x}"


def test_asm_nothing_code_patch_written_when_enabled():
    """When nothing_code behavior patch is active, the ASM patch byte must appear in the patch."""
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    config = resolve_game_config(
        Flags(shuffle_magical_sword=Tristate.ON, progressive_items=Tristate.OFF),
        SeededRng(0),
    )
    data_patch = serialize_game_world(
        gw, originals, change_dungeon_nothing_code=True
    )
    patch = data_patch.merge(build_behavior_patch(config))

    assert ASM_NOTHING_CODE_PATCH_OFFSET in patch.data, (
        f"ASM nothing-code patch missing from patch.data "
        f"(offset {ASM_NOTHING_CODE_PATCH_OFFSET:#x} not present)"
    )
    got = patch.data[ASM_NOTHING_CODE_PATCH_OFFSET]
    assert got == bytes([ASM_NOTHING_CODE_PATCH_VALUE]), (
        f"ASM nothing-code patch has wrong value: got {got!r}, "
        f"expected {bytes([ASM_NOTHING_CODE_PATCH_VALUE])!r}"
    )


def test_asm_nothing_code_patch_absent_when_disabled():
    """When no behavior patches are active, the ASM nothing-code patch must NOT appear."""
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    config = resolve_game_config(Flags(), SeededRng(0))
    data_patch = serialize_game_world(gw, originals)
    patch = data_patch.merge(build_behavior_patch(config))

    assert ASM_NOTHING_CODE_PATCH_OFFSET not in patch.data, (
        f"ASM nothing-code patch unexpectedly present in patch.data "
        f"(offset {ASM_NOTHING_CODE_PATCH_OFFSET:#x})"
    )


def test_progressive_items_behavior_patch_written():
    """When progressive_items behavior patch is active, all three ASM patches must appear."""
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    config = resolve_game_config(Flags(progressive_items=Tristate.ON), SeededRng(0))
    data_patch = serialize_game_world(gw, originals)
    patch = data_patch.merge(build_behavior_patch(config))

    # HandleClass2: CLC / ADC $0657,Y / NOP
    assert patch.data.get(0x6D06) == bytes([0x18, 0x79, 0x57, 0x06, 0xEA]), (
        f"HandleClass2 patch wrong or missing at 0x6D06: {patch.data.get(0x6D06)!r}"
    )
    # Ring/tunic color fix call site: JSR $FFE4
    assert patch.data.get(0x6BFB) == bytes([0x20, 0xE4, 0xFF]), (
        f"Ring call site patch wrong or missing at 0x6BFB: {patch.data.get(0x6BFB)!r}"
    )
    # Ring/tunic color fix routine
    assert patch.data.get(0x1FFF4) == bytes([0x8E, 0x02, 0x06,
                                             0x8E, 0x72, 0x06,
                                             0xEE, 0x4F, 0x03,
                                             0x60]), (
        f"Ring fix routine wrong or missing at 0x1FFF4: {patch.data.get(0x1FFF4)!r}"
    )


def test_progressive_items_behavior_patch_absent_by_default():
    """Without progressive_items, none of the ASM patches should appear."""
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    config = resolve_game_config(Flags(), SeededRng(0))
    data_patch = serialize_game_world(gw, originals)
    patch = data_patch.merge(build_behavior_patch(config))

    assert 0x6D06  not in patch.data, "HandleClass2 patch unexpectedly present"
    assert 0x6BFB  not in patch.data, "Ring call site patch unexpectedly present"
    assert 0x1FFF4 not in patch.data, "Ring fix routine unexpectedly present"


def test_maze_directions_roundtrip():
    """Maze direction bytes at MAZE_DIRECTIONS_ADDRESS must survive parse → serialize unchanged."""
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    got = patch.data[MAZE_DIRECTIONS_ADDRESS]
    # Vanilla: Dead Woods = North, West, South, West  (0x08 0x02 0x04 0x02)
    #          Lost Hills = Up, Up, Up, Up            (0x08 0x08 0x08 0x08)
    expected = bytes([0x08, 0x02, 0x04, 0x02,  0x08, 0x08, 0x08, 0x08])
    assert got == expected, (
        f"maze_directions mismatch: got {list(got)!r}, expected {list(expected)!r}"
    )


def test_heart_requirements_roundtrip():
    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    patch = serialize_game_world(gw, originals)

    exp_ws = (TEST_DATA / "white_sword_requirement.bin").read_bytes()
    got_ws = patch.data[WHITE_SWORD_REQUIREMENT_ADDRESS]
    assert got_ws == exp_ws, \
        f"white_sword_requirement mismatch: got {got_ws[0]:#04x}, expected {exp_ws[0]:#04x}"

    exp_ms = (TEST_DATA / "magical_sword_requirement.bin").read_bytes()
    got_ms = patch.data[MAGICAL_SWORD_REQUIREMENT_ADDRESS]
    assert got_ms == exp_ms, \
        f"magical_sword_requirement mismatch: got {got_ms[0]:#04x}, expected {exp_ms[0]:#04x}"


def test_compass_points_to_stairway_room_when_triforce_in_staircase():
    """When a triforce is placed in an item staircase, the compass room byte
    should point to the room with the stairway down (return_dest), not the
    staircase room itself."""
    from zora.data_model import Item, RoomType

    originals = _load_originals()
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)

    # Find a level with an item staircase and move its triforce there.
    for level in gw.levels:
        staircase = next(
            (sr for sr in level.staircase_rooms
             if sr.room_type == RoomType.ITEM_STAIRCASE),
            None,
        )
        triforce_room = next(
            (r for r in level.rooms if r.item == Item.TRIFORCE),
            None,
        )
        if staircase is not None and triforce_room is not None:
            break
    else:
        pytest.skip("No level with both a triforce room and an item staircase")

    # Move triforce into the staircase; clear it from the regular room.
    triforce_room.item = Item.NOTHING
    staircase.item = Item.TRIFORCE

    patch = serialize_game_world(gw, originals)
    level_info_bytes = patch.data[LEVEL_INFO_ADDRESS]
    offset = level.level_num * LEVEL_INFO_SIZE
    compass_room = level_info_bytes[offset + 0x30]

    assert staircase.return_dest is not None
    assert compass_room == staircase.return_dest, (
        f"L{level.level_num}: compass points to {compass_room:#04x}, "
        f"expected return_dest {staircase.return_dest:#04x}"
    )
