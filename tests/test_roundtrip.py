"""Round-trip tests: parse a ROM → serialize must reproduce it byte-identically.

These tests are ROM-based (no extracted .bin files). The vanilla ROM path is
taken from the ZORA_VANILLA_ROM env var, falling back to the repo-root PRG0
"Legend of Zelda, The (USA).nes". All tests skip when no ROM is found; every
resolution path verifies the PRG0 hashes (zora/rom/base_rom.py) and refuses
anything else.
"""
import os
from pathlib import Path

import pytest

from zora.model.game_world import GameWorld
from zora.model.enums import Item, RoomType
from zora.rom.parse.bin_files import load_bin_files_from_rom
from zora.rom.parse.rom_file import load_rom, original_bins_from_rom, parse_rom
from zora.rom.parse.game_world import parse_game_world
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom.layout import LEVEL_INFO_ADDRESS, LEVEL_INFO_SIZE
from zora.rom.serialize.text import _serialize_quotes
from zora.rom.serialize.game_world import serialize_game_world

from zora.rom.base_rom import BASE_ROM_PATH as _DEFAULT_ROM, verify_base_rom


def _vanilla_rom_path() -> Path | None:
    env = os.environ.get("ZORA_VANILLA_ROM")
    if env:
        pp = Path(env)
        return verify_base_rom(pp) if pp.exists() else None
    return verify_base_rom(_DEFAULT_ROM) if _DEFAULT_ROM.exists() else None


@pytest.fixture(scope="module")
def vanilla_rom() -> bytes:
    path = _vanilla_rom_path()
    if path is None:
        pytest.skip("vanilla ROM not found (set ZORA_VANILLA_ROM)")
    return load_rom(path)


@pytest.fixture(scope="module")
def vanilla_world(vanilla_rom: bytes) -> GameWorld:
    return parse_rom(vanilla_rom)


def test_full_rom_roundtrip_byte_identical(vanilla_rom: bytes, vanilla_world: GameWorld) -> None:
    """Parse → serialize → apply must reproduce the entire ROM byte for byte."""
    got = serialize_to_rom(vanilla_world, vanilla_rom)
    if got != vanilla_rom:
        diffs = [(i, vanilla_rom[i], got[i]) for i in range(len(vanilla_rom)) if got[i] != vanilla_rom[i]]
        regions = []
        for addr, exp, act in diffs[:40]:
            regions.append(f"0x{addr:05X}: expected {exp:#04x}, got {act:#04x}")
        pytest.fail(
            f"round-trip differs in {len(diffs)} bytes (first 40):\n" + "\n".join(regions)
        )


def test_parse_from_rom_slices_matches_bin_path(vanilla_rom: bytes, vanilla_world: GameWorld) -> None:
    """load_bin_files_from_rom path and parse_rom agree (same entry function)."""
    gw2 = parse_game_world(load_bin_files_from_rom(vanilla_rom))
    assert len(gw2.levels) == 9
    assert len(vanilla_world.levels) == 9
    for a, b in zip(vanilla_world.levels, gw2.levels):
        assert [r.room_num for r in a.rooms] == [r.room_num for r in b.rooms]


def test_vanilla_basic_invariants(vanilla_world: GameWorld) -> None:
    assert len(vanilla_world.quotes) == 38
    assert vanilla_world.quotes_raw  # captured for passthrough
    for lvl in vanilla_world.levels:
        assert lvl.rooms, f"level {lvl.level_num} parsed with no rooms"
        assert any(r.room_num == lvl.entrance_room for r in lvl.rooms)


def test_quotes_reencode_matches_original(vanilla_rom: bytes, vanilla_world: GameWorld) -> None:
    """decode → re-encode of the vanilla hint block must be lossless (character
    table sanity; independent of the quotes_raw passthrough)."""
    from zora.rom.layout import QUOTE_DATA_ADDRESS, VANILLA_HINT_TEXT_MAX_BYTES
    original = vanilla_rom[QUOTE_DATA_ADDRESS: QUOTE_DATA_ADDRESS + 1442]
    reencoded = _serialize_quotes(vanilla_world.quotes,
                                  max_text_bytes=VANILLA_HINT_TEXT_MAX_BYTES,
                                  center=False)
    if reencoded != original:
        diffs = [(i, original[i], reencoded[i]) for i in range(min(len(original), len(reencoded)))
                 if original[i] != reencoded[i]]
        pytest.fail(f"quotes re-encode differs in {len(diffs)} bytes: {diffs[:10]}")


def test_fade_palette_roundtrip(vanilla_rom: bytes, vanilla_world: GameWorld) -> None:
    originals = original_bins_from_rom(vanilla_rom)
    patch = serialize_game_world(vanilla_world, originals)
    level_info_serialized = patch.data[LEVEL_INFO_ADDRESS]
    for lvl in vanilla_world.levels:
        block_offset = lvl.level_num * LEVEL_INFO_SIZE
        orig_fade = originals["level_info.bin"][block_offset + 0x7C: block_offset + 0xDC]
        got_fade = level_info_serialized[block_offset + 0x7C: block_offset + 0xDC]
        assert got_fade == orig_fade, f"fade palette changed for level {lvl.level_num}"
        assert lvl.fade_palette_raw == orig_fade


def test_maze_directions_vanilla(vanilla_rom: bytes, vanilla_world: GameWorld) -> None:
    # Vanilla: Dead Woods = North, West, South, West; Lost Hills = Up, Up, Up, Up
    from zora.model.enums import OverworldDirection as OD
    assert vanilla_world.overworld.dead_woods_directions == [OD.UP_NORTH, OD.LEFT_WEST, OD.DOWN_SOUTH, OD.LEFT_WEST]
    assert vanilla_world.overworld.lost_hills_directions == [OD.UP_NORTH] * 4


def test_compass_points_to_stairway_room_when_triforce_in_staircase(vanilla_rom: bytes, vanilla_world: GameWorld) -> None:
    """When a triforce is in an item staircase, the compass byte points to the
    room with the stairway down (return_dest), not the staircase room itself."""
    originals = original_bins_from_rom(vanilla_rom)
    for level in vanilla_world.levels:
        staircase = next((sr for sr in level.staircase_rooms
                          if sr.room_type == RoomType.ITEM_STAIRCASE), None)
        triforce_room = next((r for r in level.rooms if r.item == Item.TRIFORCE), None)
        if staircase is None or triforce_room is None:
            continue
        triforce_room.item = Item.NOTHING
        staircase.item = Item.TRIFORCE
        compass_lock = level.triforce_room_ptr
        level.triforce_room_ptr = None  # triforce moved: re-derive
        patch = serialize_game_world(vanilla_world, originals)
        level.triforce_room_ptr = compass_lock
        level_info_bytes = patch.data[LEVEL_INFO_ADDRESS]
        offset = level.level_num * LEVEL_INFO_SIZE
        triforce_room_ptr = level_info_bytes[offset + 0x30]
        assert staircase.return_dest is not None
        assert triforce_room_ptr == staircase.return_dest
        triforce_room.item = Item.TRIFORCE  # restore for later fixtures
        staircase.item = Item.NOTHING
        return
    pytest.skip("no level with both a triforce room and an item staircase")


def test_generated_world_preserves_non_dungeon_regions() -> None:
    """Generated levels must not clobber the overworld block or level_info."""
    path = _vanilla_rom_path()
    if path is None:
        pytest.skip("vanilla ROM not found")
    rom = load_rom(path)
    gw = parse_rom(rom)
    from zora.generate.rng import Rng
    from zora.generate.generation_pass import generate_shapes
    from zora.generate.shapes.options import ShapeOptions
    generate_shapes(gw, Rng(31), ShapeOptions(), post_shapes=False)
    out = serialize_to_rom(gw, rom)
    from zora.rom.layout import CAVE_ITEM_DATA_ADDRESS, LEVEL_INFO_ADDRESS, OVERWORLD_DATA_ADDRESS
    # everything outside the two grids, level info and the rooms' own regions
    # must be untouched by generation: check overworld + cave blocks.
    assert out[OVERWORLD_DATA_ADDRESS: OVERWORLD_DATA_ADDRESS + 0x300] ==         rom[OVERWORLD_DATA_ADDRESS: OVERWORLD_DATA_ADDRESS + 0x300]
    assert out[CAVE_ITEM_DATA_ADDRESS: CAVE_ITEM_DATA_ADDRESS + 120] ==         rom[CAVE_ITEM_DATA_ADDRESS: CAVE_ITEM_DATA_ADDRESS + 120]


def test_nothing_code_config_vanilla_is_default() -> None:
    """Item.NOTHING is a model meaning; the ROM byte is a GameConfig setting.
    Default (VANILLA, $03) keeps everything byte-identical (covered by
    test_full_rom_roundtrip_byte_identical); ZORA_REMAP ($0E) rewrites the
    nothing rooms, and the final ROM steps add the engine sentinel patch byte."""
    from zora.rom.game_config import DungeonNothingCode, GameConfig
    from zora.rom.layout import ASM_NOTHING_CODE_PATCH_OFFSET, ASM_NOTHING_CODE_PATCH_VALUE
    path = _vanilla_rom_path()
    if path is None:
        pytest.skip("vanilla ROM not found")
    rom = load_rom(path)
    gw = parse_rom(rom)
    cfg = GameConfig(dungeon_nothing_code=DungeonNothingCode.ZORA_REMAP)
    patch = serialize_game_world(gw, original_bins_from_rom(rom), config=cfg)
    grid = patch.data[0x18710]          # level 1-6 grid, table 4
    vanilla_t4 = rom[0x18710 + 4 * 0x80: 0x18710 + 5 * 0x80]
    n03 = sum(1 for b in vanilla_t4 if b & 0x1F == 0x03)
    n0e = sum(1 for b in grid[4 * 0x80:5 * 0x80] if b & 0x1F == 0x0E)
    assert n03 > 10
    # cells not owned by the model (stale stair-pool leftovers) keep their
    # raw vanilla byte; only modelled rooms get the configured code
    assert n03 - n0e <= 2
    # the engine sentinel patch is a final ROM step (zora/rom/final_steps.py)
    assert ASM_NOTHING_CODE_PATCH_OFFSET not in patch.data
    finished = serialize_to_rom(gw, rom, config=cfg)
    assert finished[ASM_NOTHING_CODE_PATCH_OFFSET] == ASM_NOTHING_CODE_PATCH_VALUE == 0x0E
    # re-parse with the same config: every nothing room stays nothing
    # (including the 10 vanilla $23/$63 rooms whose bits 6-5 are a boss-roar
    # index, not a drop flag — QUESTIONS #39), and the ONLY triforce of power
    # is Ganon's room L9 $42 (item $0E + enemy $3E).
    out = bytearray(rom)
    patch.apply(out)
    gw2 = parse_rom(bytes(out), config=cfg)
    for lvl, lvl2 in zip(gw.levels, gw2.levels):
        nothing1 = {r.room_num for r in lvl.rooms if r.item == Item.NOTHING}
        nothing2 = {r.room_num for r in lvl2.rooms if r.item == Item.NOTHING}
        assert nothing1 == nothing2
    tfop = [(l.level_num, r.room_num) for l in gw2.levels for r in l.rooms
            if r.item == Item.TRIFORCE_OF_POWER]
    assert tfop == [(9, 0x42)]
    # the whole-block check passes under both encodings (each ROM read with
    # its own config)
    from zora.measure.checks import check_triforce_of_power
    assert check_triforce_of_power(gw2).passed
    assert check_triforce_of_power(parse_rom(rom)).passed
    # with the DEFAULT config that same ROM reads every $0E byte as the
    # triforce of power — the encoding is a setting, not a model fact
    gw3 = parse_rom(bytes(out))
    assert sum(r.item == Item.TRIFORCE_OF_POWER
               for l in gw3.levels for r in l.rooms) > 1
    assert not check_triforce_of_power(gw3).passed


def test_triforce_of_power_rule_units() -> None:
    """$0E is the TFoP only in a Ganon ($3E) room under ZORA_REMAP; a
    no-item room with trigger 7 is flagged; boss_sound round-trips."""
    from zora.measure.checks import check_triforce_of_power
    from zora.model.enums import BossSound, Enemy, RoomAction
    from zora.rom.parse.levels import _parse_room
    ganon = _parse_room(0x42, 0, 0, 0x3E, 0x28, 0x8E, 0x03, nothing_code=0x0E)
    other = _parse_room(0x43, 0, 0, 0x01, 0x00, 0x2E, 0x00, nothing_code=0x0E)
    assert ganon.item == Item.TRIFORCE_OF_POWER and ganon.enemy == Enemy.THE_BEAST
    assert other.item == Item.NOTHING
    assert other.boss_sound == BossSound.ROAR_AQUAMENTUS_GLEEOK_GANON
    assert _parse_room(0x10, 0, 0, 0, 0, 0x6F, 0).boss_sound == \
        BossSound.ROAR_DIGDOGGER_MANHANDLA_PATRA
    rom = load_rom(_vanilla_rom_path() or pytest.skip("vanilla ROM not found"))
    gw = parse_rom(rom)
    assert check_triforce_of_power(gw).passed
    # any room of the block, owned or not: a no-item room with trigger 7
    # is flagged
    room = next(r for r in gw.blocks[0].rooms if r.item == Item.NOTHING)
    room.room_action = RoomAction.ALL_DEAD_ITEM
    assert room.item_appears_on_clear and room.item_hidden_at_load
    rn = room.room_num
    res = check_triforce_of_power(gw)
    assert not res.passed and f"trigger7 ['1-6:{rn:02X}'" in res.message


def test_finished_rom_round_trips_with_its_start_y_in_the_patch(vanilla_rom: bytes) -> None:
    """A finished ROM carries FP-ENTR-01's patch, so parse_rom reads the
    overworld start Y from the patch's byte; serializing the parsed world
    again writes it back there, not to LevelInfo_StartY, even without the
    code patches in the config. Baseline seed 17 starts at Y $5D, not PRG0's
    $8D (scripts/qa_sweep.py first found such a seed; seed 5 until the
    2026-10-07 output change)."""
    from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
    from zora.generate.pipeline import generate_rom
    from zora.rom.code_patches import overworld_start_y
    from zora.rom.layout import START_POSITION_Y_ADDRESS
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 17, vanilla_rom).rom
    assert overworld_start_y(rom) == 0x5D
    assert rom[START_POSITION_Y_ADDRESS] == vanilla_rom[START_POSITION_Y_ADDRESS] == 0x8D
    assert serialize_to_rom(parse_rom(rom), rom) == rom
