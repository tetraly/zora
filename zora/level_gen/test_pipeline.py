"""Python test harness for byte-comparison testing of the new_level pipeline.

Creates a ROM buffer pre-populated with read-only regions from a reference
ROM, seeds with Xorshift32(12345), then runs the full create_new_levels
orchestration (levels 1-6, then 7-9), dumping the grid region and
level_grid after each sub-step.

Snapshots are written to new_level/snapshots_py/.

The harness replicates the exact RNG consumption pattern of _try_create()
in create_new_levels.py so that C# and Python stay in sync.
"""

from __future__ import annotations

import os
import sys
from functools import partial

from zora.level_gen.test_xorshift import Xorshift32
from zora.level_gen.rom_buffer import (
    GRID_COLS,
    GRID_ROWS,
    GRID_SIZE,
    LevelGrid,
    ROMOFS_SCREEN_LAYOUT,
    ROMOFS_SCREEN_LAYOUT_Q2,
    clear_grid_data,
    make_level_grid,
)
from zora.level_gen.create_new_levels import (
    fix_level_numbers,
    new_level_rewrite_maps,
)
from zora.level_gen.regenerate_level_map import regenerate_level_map
from zora.level_gen.doors import new_level_doors
from zora.level_gen.add_entrances import new_level_add_entrances
from zora.level_gen.place_initial_stairs import new_level_place_initial_stairs
from zora.level_gen.rooms import new_level_rooms
from zora.level_gen.place_bosses import new_level_place_bosses
from zora.level_gen.place_enemies import new_level_place_enemies
from zora.level_gen.place_items import new_level_place_items, validate_level_items
from zora.level_gen.add_item_drop import new_level_add_item_drop


SEED = 12345
ROM_SIZE = 0x20010  # full iNES ROM size (header + PRG + CHR)
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "snapshots_py")

# ROM regions that the pipeline reads from (pre-existing data, not generated).
# These are copied from the reference ROM into the test buffer at startup.
_ROM_READ_REGIONS = [
    (0x18510, 0x18610),   # overworld enemy tables (256 bytes)
    (0x19310, 0x19CE8),   # level info blocks, levels 0-9 (2520 bytes)
]

ROM_PATH = os.path.join(os.path.dirname(__file__), "prg0.nes")


def _make_test_rom() -> bytearray:
    """Create a test ROM buffer with read-only regions from the reference ROM."""
    ref_rom = open(ROM_PATH, "rb").read()
    rom = bytearray(len(ref_rom))
    for start, end in _ROM_READ_REGIONS:
        rom[start:end] = ref_rom[start:end]
    return rom


# ROM regions written by the pipeline (dumped in snapshots).
_BOSS_SPRITE_START = 0xC025
_BOSS_SPRITE_END = 0xC036       # 17 bytes (8 page IDs at odd offsets, interleaved)
_LEVEL_INFO_START = 0x19310
_LEVEL_INFO_END = 0x19CE8       # 2520 bytes (levels 0-9)


def dump_rom_snapshot(rom: bytearray, label: str) -> None:
    """Dump all pipeline-written ROM regions to a single file."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    path = os.path.join(SNAPSHOT_DIR, f"snapshot_after_{label}.hex")
    with open(path, "wb") as f:
        f.write(rom[ROMOFS_SCREEN_LAYOUT: ROMOFS_SCREEN_LAYOUT + GRID_SIZE])
        f.write(rom[ROMOFS_SCREEN_LAYOUT_Q2: ROMOFS_SCREEN_LAYOUT_Q2 + GRID_SIZE])
        f.write(rom[_BOSS_SPRITE_START: _BOSS_SPRITE_END])
        f.write(rom[_LEVEL_INFO_START: _LEVEL_INFO_END])


def dump_level_grid(level_grid: LevelGrid, label: str) -> None:
    """Dump the 8x16 level grid as 128 raw bytes."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    path = os.path.join(SNAPSHOT_DIR, f"grid_after_{label}.hex")
    data = bytearray()
    for row in level_grid:
        for cell in row:
            data.append(cell & 0xFF)
    with open(path, "wb") as f:
        f.write(data)


def run_group(
    rom: bytearray,
    rng: Xorshift32,
    level_grid: LevelGrid,
    dungeon_order: list[int],
    start_level: int,
) -> bool:
    """Run the pipeline for one level group, dumping after each step.

    start_level: 1 for levels 1-6, 7 for levels 7-9.
    The rng is shared across both groups — caller must not reset it.
    """
    group = "16" if start_level == 1 else "79"
    num_levels = 6 if start_level == 1 else 3

    # 4a/5a: Clear data
    clear_grid_data(rom, start_level)

    # 4b/5b: regenerate_level_map
    level_grid_new = regenerate_level_map(rng, num_levels, False)
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            level_grid[r][c] = level_grid_new[r][c]

    # 4c/5c: fix_level_numbers
    fix_level_numbers(level_grid, dungeon_order, start_level, num_levels, False)

    dump_rom_snapshot(rom, f"{group}_1_regenerate_level_map")
    dump_level_grid(level_grid, f"{group}_1_regenerate_level_map")
    print(f"  [{group}] After regenerate_level_map — dumped")

    # 4d: Flatten grid (consumed but not used by test)
    # screen_type_data: list[int] = [cell for row in level_grid for cell in row]

    # 4e/5e: new_level_doors (call-site consumes 1 RNG for seed param)
    new_level_doors(rom, rng, level_grid, rng.next(), start_level, False)
    dump_rom_snapshot(rom, f"{group}_2_doors")
    dump_level_grid(level_grid, f"{group}_2_doors")
    print(f"  [{group}] After doors — dumped")

    # 4f/5f: new_level_add_entrances
    result = new_level_add_entrances(rom, rng, level_grid, rng.next(), False)
    if not result[0]:
        print(f"  [{group}] add_entrances FAILED")
        return False
    goriya_room = result[2]
    dump_rom_snapshot(rom, f"{group}_3_add_entrances")
    dump_level_grid(level_grid, f"{group}_3_add_entrances")
    print(f"  [{group}] After add_entrances — dumped (goriya_room={goriya_room})")

    # 4g/5g: new_level_place_initial_stairs
    add_item_drop_fn = partial(new_level_add_item_drop, level_grid=level_grid)
    if not new_level_place_initial_stairs(
        rom, rng, level_grid, rng.next(), start_level, False,
        goriya_room, 0, 0, add_item_drop_fn,
    ):
        print(f"  [{group}] place_initial_stairs FAILED")
        return False
    dump_rom_snapshot(rom, f"{group}_4_place_initial_stairs")
    dump_level_grid(level_grid, f"{group}_4_place_initial_stairs")
    print(f"  [{group}] After place_initial_stairs — dumped")

    # 4h/5h: new_level_rooms
    if not new_level_rooms(rom, rng, level_grid, rng.next(), start_level, False, goriya_room):
        print(f"  [{group}] rooms FAILED")
        return False
    dump_rom_snapshot(rom, f"{group}_5_rooms")
    dump_level_grid(level_grid, f"{group}_5_rooms")
    print(f"  [{group}] After rooms — dumped")

    # 4i/5i: new_level_place_bosses
    rng.next()  # call-site consumes 1 RNG for seed param
    if not new_level_place_bosses(rom, rng, start_level, level_grid):
        print(f"  [{group}] place_bosses FAILED")
        return False
    dump_rom_snapshot(rom, f"{group}_6_place_bosses")
    dump_level_grid(level_grid, f"{group}_6_place_bosses")
    print(f"  [{group}] After place_bosses — dumped")

    # 4j/5j: new_level_place_enemies
    rng.next()
    new_level_place_enemies(rom, rng, start_level, level_grid, False)
    dump_rom_snapshot(rom, f"{group}_7_place_enemies")
    dump_level_grid(level_grid, f"{group}_7_place_enemies")
    print(f"  [{group}] After place_enemies — dumped")

    # 4k/5k: new_level_place_items
    rng.next()
    if not new_level_place_items(rom, rng, start_level, level_grid):
        print(f"  [{group}] place_items FAILED")
        return False
    validate_level_items(rom, level_grid, start_level)
    dump_rom_snapshot(rom, f"{group}_8_place_items")
    dump_level_grid(level_grid, f"{group}_8_place_items")
    print(f"  [{group}] After place_items — dumped")

    # 4l/5l: new_level_rewrite_maps
    level9_start_col = new_level_rewrite_maps(rom, level_grid, start_level)
    dump_rom_snapshot(rom, f"{group}_9_rewrite_maps")
    dump_level_grid(level_grid, f"{group}_9_rewrite_maps")
    print(f"  [{group}] After rewrite_maps — dumped (level9_start_col={level9_start_col})")

    return True


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else SEED
    print(f"Running pipeline with seed={seed}")
    print()

    rng = Xorshift32(seed)
    rom = _make_test_rom()
    level_grid = make_level_grid()

    # Step 1: advance RNG twice (sodiumRand::seed is a NO-OP)
    rng.next()
    rng.next()

    # Step 2: create dungeon assignment array
    dungeon_order = [1, 2, 3, 4, 5, 6, 7, 8, 9]

    # Step 3: shuffle (sort_dungeons=False)
    remaining = 6
    i = 0
    while remaining > 0:
        j = rng.next() % remaining
        dungeon_order[i], dungeon_order[i + j] = dungeon_order[i + j], dungeon_order[i]
        i += 1
        remaining -= 1
    for i in range(6, 9):
        j = rng.next() % (9 - i)
        dungeon_order[i], dungeon_order[i + j] = dungeon_order[i + j], dungeon_order[i]

    print(f"Dungeon order: {dungeon_order}")
    print()

    # Step 4: levels 1-6
    print("=== Levels 1-6 ===")
    ok = run_group(rom, rng, level_grid, dungeon_order, 1)
    if not ok:
        print("Levels 1-6 pipeline FAILED — try a different seed.")
        sys.exit(1)
    print()

    # Step 5: levels 7-9
    print("=== Levels 7-9 ===")
    ok = run_group(rom, rng, level_grid, dungeon_order, 7)
    if not ok:
        print("Levels 7-9 pipeline FAILED — try a different seed.")
        sys.exit(1)
    print()

    print(f"All snapshots written to {SNAPSHOT_DIR}/")


if __name__ == "__main__":
    main()
