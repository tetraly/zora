"""Public API for the new-level generation pipeline.

Takes a seed and vanilla ROM data as inputs, runs the full dungeon
generation pipeline (levels 1-6 and 7-9), and returns the generated
data as discrete byte regions that can be plugged into a RawBinFiles
or applied to a ROM.

The pipeline uses a shared ROM buffer internally but this API hides
that detail — callers provide only the read-only regions the pipeline
needs, and receive only the regions it produces.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial

from zora.level_gen.test_xorshift import Xorshift32
from zora.level_gen.rom_buffer import (
    GRID_COLS,
    GRID_ROWS,
    GRID_SIZE,
    LevelGrid,
    ROMOFS_SCREEN_LAYOUT,
    ROMOFS_SCREEN_LAYOUT_Q2,
    ROMOFS_OW_ENEMY_TABLE_1,
    ROMOFS_LEVEL_INFO_BASE,
    LEVEL_INFO_STRIDE,
    clear_grid_data,
    make_level_grid,
)
from zora.level_gen.create_new_levels import fix_level_numbers, new_level_rewrite_maps
from zora.level_gen.regenerate_level_map import regenerate_level_map
from zora.level_gen.doors import new_level_doors
from zora.level_gen.add_entrances import new_level_add_entrances
from zora.level_gen.place_initial_stairs import new_level_place_initial_stairs
from zora.level_gen.rooms import new_level_rooms
from zora.level_gen.place_bosses import new_level_place_bosses
from zora.level_gen.place_enemies import new_level_place_enemies
from zora.level_gen.place_items import new_level_place_items, validate_level_items
from zora.level_gen.add_item_drop import new_level_add_item_drop

_OW_ENEMY_TABLES_SIZE = 256
_LEVEL_INFO_SIZE = 10 * LEVEL_INFO_STRIDE  # 2520 bytes, levels 0-9

# Sprite pointer table: 10 enemy + 10 boss = 20 entries x 2 bytes = 40 bytes.
# File offset 0xC010 (CPU 0xC000). PlaceBosses writes the high byte of
# boss entries (the second 20 bytes) at rom[0xC025 + lv*2] for lv=1..8.
_SPRITE_TABLE_ADDR = 0xC010
_SPRITE_TABLE_SIZE = 40

_ROM_SIZE = 0x20010


@dataclass(frozen=True)
class NewLevelInput:
    """Read-only vanilla ROM data the pipeline needs.

    overworld_enemy_tables: 256 bytes from ROM 0x18510-0x18610.
        Two 128-byte tables used by PlaceEnemies to seed dungeon
        enemy pools from the overworld.

    level_info: 2520 bytes from ROM 0x19310-0x19CE8.
        Level info blocks for levels 0-9 (10 x 252 bytes).
        The pipeline reads item_position_table sentinels and
        writes entrance_room, map data, and stairway lists.

    sprite_table: 40 bytes from ROM 0xC010-0xC038.
        Pointer table for graphics data: 10 enemy sprite set pointers
        followed by 10 boss sprite set pointers (2 bytes each,
        little-endian CPU addresses). PlaceBosses modifies the high
        bytes of the boss entries for levels 1-8.
    """
    overworld_enemy_tables: bytes
    level_info: bytes
    sprite_table: bytes

    def __post_init__(self) -> None:
        if len(self.overworld_enemy_tables) != _OW_ENEMY_TABLES_SIZE:
            raise ValueError(
                f"overworld_enemy_tables must be {_OW_ENEMY_TABLES_SIZE} bytes, "
                f"got {len(self.overworld_enemy_tables)}")
        if len(self.level_info) != _LEVEL_INFO_SIZE:
            raise ValueError(
                f"level_info must be {_LEVEL_INFO_SIZE} bytes, "
                f"got {len(self.level_info)}")
        if len(self.sprite_table) != _SPRITE_TABLE_SIZE:
            raise ValueError(
                f"sprite_table must be {_SPRITE_TABLE_SIZE} bytes, "
                f"got {len(self.sprite_table)}")


@dataclass(frozen=True)
class NewLevelOutput:
    """Generated dungeon data from the pipeline.

    level_1_6_grid: 0x300 bytes — the 6 ROM tables for levels 1-6.
        Corresponds to ROM 0x18710-0x18A10 and RawBinFiles.level_1_6_data.

    level_7_9_grid: 0x300 bytes — the 6 ROM tables for levels 7-9.
        Corresponds to ROM 0x18A10-0x18D10 and RawBinFiles.level_7_9_data.

    level_info: 2520 bytes — modified level info blocks (levels 0-9).
        Corresponds to ROM 0x19310-0x19CE8 and RawBinFiles.level_info.

    sprite_table: 40 bytes — modified sprite pointer table.
        Same layout as the input; boss entries for levels 1-8
        have been updated by PlaceBosses.

    grid_16: 8x16 int grid mapping room positions to level numbers (1-6).
    grid_79: 8x16 int grid mapping room positions to level numbers (7-9).

    dungeon_order: list of 9 ints — the shuffled dungeon assignment
        [1..9] showing which physical level slot holds which dungeon.
    """
    level_1_6_grid: bytes
    level_7_9_grid: bytes
    level_info: bytes
    sprite_table: bytes
    grid_16: list[list[int]]
    grid_79: list[list[int]]
    dungeon_order: list[int]


def generate_new_levels(
    seed: int,
    inputs: NewLevelInput,
    *,
    sort_dungeons: bool = True,
    shuffle_entrances: bool = False,
    add_2nd_doors: bool = False,
    add_2nd_rooms: bool = False,
    add_2nd_monsters: bool = False,
    create_16: bool = True,
    create_79: bool = True,
    mixed_quest_type_1: int = 0,
    mixed_quest_type_2: int = 0,
) -> NewLevelOutput:
    """Run the full dungeon generation pipeline.

    Args:
        seed: RNG seed (deterministic — same seed produces same output).
        inputs: Vanilla ROM data the pipeline reads from.
        sort_dungeons: If False (default), shuffle dungeon order randomly.
            If True, keep dungeons 1-9 in their original slots.
        shuffle_entrances: Affects level map generation and entrance
            placement. Default False.
        add_2nd_doors: Include second-quest door type weights.
        add_2nd_rooms: Include second-quest room types in stair
            placement and room assignment.
        add_2nd_monsters: Include second-quest enemy pools.
        create_16: Generate levels 1-6. Default True.
        create_79: Generate levels 7-9. Default True.
        mixed_quest_type_1: Q2 quest mixing override for stair data
            (level 9). 0 = off, 1 = on.
        mixed_quest_type_2: Q2 quest mixing override for stair data
            (level 7). 0 = off, 1 = on.

    Returns:
        NewLevelOutput with all generated data.
    """
    rom = bytearray(_ROM_SIZE)
    rom[ROMOFS_OW_ENEMY_TABLE_1:ROMOFS_OW_ENEMY_TABLE_1 + _OW_ENEMY_TABLES_SIZE] = (
        inputs.overworld_enemy_tables)
    rom[ROMOFS_LEVEL_INFO_BASE:ROMOFS_LEVEL_INFO_BASE + _LEVEL_INFO_SIZE] = (
        inputs.level_info)
    rom[_SPRITE_TABLE_ADDR:_SPRITE_TABLE_ADDR + _SPRITE_TABLE_SIZE] = (
        inputs.sprite_table)

    rng = Xorshift32(seed)
    level_grid = make_level_grid()

    rng.next()
    rng.next()

    dungeon_order = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    if not sort_dungeons:
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

    saved_grids: dict[int, list[list[int]]] = {}

    for start_level, should_create in [(1, create_16), (7, create_79)]:
        if not should_create:
            saved_grids[start_level] = make_level_grid()
            continue

        num_levels = 6 if start_level == 1 else 3
        clear_grid_data(rom, start_level)
        lg = regenerate_level_map(rng, num_levels, shuffle_entrances)
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                level_grid[r][c] = lg[r][c]
        fix_level_numbers(level_grid, dungeon_order, start_level, num_levels, sort_dungeons)
        new_level_doors(rom, rng, level_grid, rng.next(), start_level, add_2nd_doors)
        result = new_level_add_entrances(rom, rng, level_grid, rng.next(), shuffle_entrances)
        goriya_room = result[2]
        add_item_drop_fn = partial(new_level_add_item_drop, level_grid=level_grid)
        new_level_place_initial_stairs(
            rom, rng, level_grid, rng.next(), start_level, add_2nd_rooms,
            goriya_room, mixed_quest_type_1, mixed_quest_type_2, add_item_drop_fn,
        )
        new_level_rooms(rom, rng, level_grid, rng.next(), start_level, add_2nd_rooms, goriya_room)
        rng.next()
        new_level_place_bosses(rom, rng, start_level, level_grid)
        rng.next()
        new_level_place_enemies(rom, rng, start_level, level_grid, add_2nd_monsters)
        rng.next()
        new_level_place_items(rom, rng, start_level, level_grid)
        validate_level_items(rom, level_grid, start_level)
        new_level_rewrite_maps(rom, level_grid, start_level)

        saved_grids[start_level] = [row[:] for row in level_grid]

    return NewLevelOutput(
        level_1_6_grid=bytes(rom[ROMOFS_SCREEN_LAYOUT:ROMOFS_SCREEN_LAYOUT + GRID_SIZE]),
        level_7_9_grid=bytes(rom[ROMOFS_SCREEN_LAYOUT_Q2:ROMOFS_SCREEN_LAYOUT_Q2 + GRID_SIZE]),
        level_info=bytes(rom[ROMOFS_LEVEL_INFO_BASE:ROMOFS_LEVEL_INFO_BASE + _LEVEL_INFO_SIZE]),
        sprite_table=bytes(rom[_SPRITE_TABLE_ADDR:_SPRITE_TABLE_ADDR + _SPRITE_TABLE_SIZE]),
        grid_16=saved_grids[1],
        grid_79=saved_grids[7],
        dungeon_order=dungeon_order,
    )
