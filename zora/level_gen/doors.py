"""Assign wall/door types between adjacent rooms in each dungeon level.

Iterates the 8x16 level grid and, for each pair of horizontally or
vertically adjacent rooms belonging to the same level, randomly assigns
a door type (open/locked/bomb/shutter) based on per-level weight tables.

ROM writes go to Table 0 (north/south walls) and Table 1 (east/west walls).

Ported line-by-line from NewLevelDoors.cs (newLevelDoors, Module.cs:19509).
Cross-referenced: config arrays verified against Module.cs:19516-19838,
layout base logic verified against Module.cs:19979-19980.
"""

from __future__ import annotations

from zora.level_gen.rom_buffer import (
    GRID_COLS,
    GRID_ROWS,
    LevelGrid,
    ROMOFS_SCREEN_LAYOUT,
    ROMOFS_SCREEN_LAYOUT_Q2,
)
from zora.rng import Rng


def new_level_doors(
    rom: bytearray,
    rng: Rng,
    level_grid: LevelGrid,
    seed: int,
    start_level: int,
    allow_2nd_quest: bool,
) -> None:
    rng.next()
    rng.next()

    door_configs: list[list[int]] = [
        [0, 0, 0, 0, 0, 0, 0, 0],          # Index 0: empty sentinel
        [18,  0, 0, 0,  4, 12, 0,  3],      # Level 1
        [25,  0, 0, 0, 10,  6, 0,  6],      # Level 2
        [23,  0, 0, 0,  4,  8, 0,  8],      # Level 3
        [23,  2, 0, 0,  8, 10, 0,  6],      # Level 4
        [21, 12, 0, 0, 10, 12, 0,  6],      # Level 5
        [25,  8, 0, 0,  6, 10, 0, 12],      # Level 6
        [30, 26, 0, 0, 20, 10, 0, 11],      # Level 7
        [21, 12, 0, 0, 12,  8, 0, 12],      # Level 8
        [41, 68, 0, 0, 38, 32, 0, 14],      # Level 9
    ]

    door_configs_2: list[list[int]] = [
        [0, 0, 0, 0, 0, 0, 0, 0],           # Index 0: empty sentinel
        [15,  4, 0, 0,  6,  4, 0,  4],      # Level 1
        [21, 11, 3, 0,  6,  8, 0,  6],      # Level 2
        [11,  2, 0, 0,  0,  6, 0,  2],      # Level 3
        [31, 29, 12, 0,  8,  6, 0, 11],     # Level 4
        [19, 12, 2, 0,  0,  4, 0,  6],      # Level 5
        [26,  4, 4, 0, 10,  6, 0,  5],      # Level 6
        [28, 12, 0, 0,  0,  4, 0, 17],      # Level 7
        [28, 16, 6, 0,  8, 10, 0, 13],      # Level 8
        [55, 23, 16, 0, 18, 10, 0, 21],     # Level 9
    ]

    base_offset = 0

    if allow_2nd_quest:
        for lvl in range(len(door_configs)):
            if lvl < len(door_configs_2):
                for j in range(len(door_configs[lvl])):
                    if j < len(door_configs_2[lvl]):
                        door_configs[lvl][j] += door_configs_2[lvl][j]

    configs = door_configs

    door_totals = [0] * 10
    for ci in range(len(configs)):
        for j in range(len(configs[ci])):
            door_totals[ci] += configs[ci][j]

    layout_base = ROMOFS_SCREEN_LAYOUT_Q2 if start_level == 7 else ROMOFS_SCREEN_LAYOUT
    door_conn_base = layout_base + 128

    # Step 1: Initialize all occupied rooms with base door value 2
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            if level_grid[row][col] != 0:
                room_idx = row * 16 + col
                rom[room_idx + base_offset + layout_base] = 2
                rom[room_idx + base_offset + door_conn_base] |= 2

    # Step 2: Process vertical and horizontal adjacency
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            room_idx = row * 16 + col
            cell_level = level_grid[row][col]

            # --- Vertical adjacency (down) ---
            cur_byte = rom[room_idx + base_offset + layout_base]
            if cur_byte < 0:
                cur_byte += 256

            if row + 1 < 8 and level_grid[row + 1][col] == cell_level and cell_level != 0:
                door_type = cur_byte & ~0x1C
                total = door_totals[cell_level if cell_level < len(configs) else 0]
                if total > 0:
                    pick = rng.next() % total
                    door_idx = 0
                    level_cfg_idx = cell_level if cell_level < len(configs) else 0
                    pick -= configs[level_cfg_idx][0]
                    while pick >= 0 and door_idx < len(configs[level_cfg_idx]) - 1:
                        door_idx += 1
                        pick -= configs[level_cfg_idx][door_idx]

                    if (cell_level == 9 and row + 1 < 8
                            and level_grid[row + 1][col] == 9
                            and col == 6 and (row == 5 or row == 6)):
                        door_idx = 7

                    door_type_2 = door_idx
                    door_idx_copy = door_idx
                    if door_idx == 0:
                        if rng.next() % 5 == 0:
                            door_type_2 = 7
                        elif rng.next() % 5 == 0:
                            door_idx_copy = 7

                    rom[room_idx + base_offset + layout_base] = ((door_type_2 << 2) | door_type) & 0xFF
                    below_addr = room_idx + 16 + base_offset + layout_base
                    below_byte = rom[below_addr]
                    if below_byte < 0:
                        below_byte += 256
                    rom[below_addr] = below_byte & 0x1F
                    below_byte = rom[below_addr]
                    if below_byte < 0:
                        below_byte += 256
                    rom[below_addr] = ((door_idx_copy << 5) | below_byte) & 0xFF

            elif cell_level != 0:
                rom[room_idx + base_offset + layout_base] = ((cur_byte & ~0x18) | 4) & 0xFF
                if row + 1 >= 8:
                    wall_addr = base_offset + layout_base + col
                else:
                    wall_addr = room_idx + 16 + base_offset + layout_base
                below_byte = rom[wall_addr]
                if below_byte < 0:
                    below_byte += 256
                rom[wall_addr] = ((below_byte & 0x1F) | 0x20) & 0xFF

            # --- Horizontal adjacency (right) ---
            h_addr = room_idx + base_offset + door_conn_base
            h_byte = rom[h_addr]
            if h_byte < 0:
                h_byte += 256

            if col + 1 < 16 and level_grid[row][col + 1] == cell_level and cell_level != 0:
                door_type = h_byte & ~0x1C
                level_cfg_idx = cell_level if cell_level < len(configs) else 0
                total = door_totals[level_cfg_idx]
                if total > 0:
                    pick = rng.next() % total
                    door_idx = 0
                    pick -= configs[level_cfg_idx][0]
                    while pick >= 0 and door_idx < len(configs[level_cfg_idx]) - 1:
                        door_idx += 1
                        pick -= configs[level_cfg_idx][door_idx]

                    skip_rng = False
                    if (cell_level == 9 and col + 1 < 16
                            and level_grid[row][col + 1] == 9
                            and row == 6 and (col == 5 or col == 6)):
                        door_idx = 7
                        skip_rng = True

                    if (cell_level == 9 and col + 1 < 16
                            and level_grid[row][col + 1] == 9
                            and row == 7 and (col == 5 or col == 6)):
                        door_idx = 1

                    door_type_2 = door_idx
                    if not skip_rng:
                        if door_idx == 0 and rng.next() % 5 == 0:
                            door_type_2 = 7
                        elif door_idx == 0 and rng.next() % 5 == 0:
                            door_idx = 7

                    rom[h_addr] = ((door_type_2 << 2) | door_type) & 0xFF
                    right_addr = room_idx + 1 + base_offset + door_conn_base
                    right_byte = rom[right_addr]
                    if right_byte < 0:
                        right_byte += 256
                    rom[right_addr] = right_byte & 0x1F
                    right_byte = rom[right_addr]
                    if right_byte < 0:
                        right_byte += 256
                    rom[right_addr] = ((door_idx << 5) | right_byte) & 0xFF

            elif cell_level != 0:
                wall_byte = (h_byte & ~0x18) | 4
                rom[h_addr] = wall_byte & 0xFF
                if col + 1 >= 16:
                    wall_addr_2 = row * 16 + base_offset + door_conn_base
                else:
                    wall_addr_2 = room_idx + 1 + base_offset + door_conn_base
                right_byte = rom[wall_addr_2]
                if right_byte < 0:
                    right_byte += 256
                rom[wall_addr_2] = ((right_byte & 0x1F) | 0x20) & 0xFF

    # =========================================================================
    # WORKAROUND — NOT IN ORIGINAL C# PORT
    #
    # The original C# (Module.cs:19509) only writes solid walls when iterating
    # from a cell to its right/below neighbor.  When the left/above neighbor is
    # empty (level 0), no code ever sets the occupied room's north/west wall to
    # SOLID_WALL, leaving it at OPEN_DOOR.  The parser's flood fill then leaks
    # through the empty room into adjacent levels.
    #
    # This pass runs after the ported logic and forces solid walls on every
    # occupied-room edge that faces an empty, different-level, or grid-boundary
    # cell.  It only overwrites walls that should already be solid, so it does
    # not change any same-level door assignments from Step 2.
    # =========================================================================
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cell_level = level_grid[row][col]
            if cell_level == 0:
                continue
            room_idx = row * 16 + col

            # North wall
            if row == 0 or level_grid[row - 1][col] != cell_level:
                addr = room_idx + base_offset + layout_base
                byte_val = rom[addr] & 0xFF
                rom[addr] = ((byte_val & 0x1F) | 0x20) & 0xFF

            # South wall
            if row == GRID_ROWS - 1 or level_grid[row + 1][col] != cell_level:
                addr = room_idx + base_offset + layout_base
                byte_val = rom[addr] & 0xFF
                rom[addr] = ((byte_val & ~0x1C) | 4) & 0xFF

            # West wall
            if col == 0 or level_grid[row][col - 1] != cell_level:
                addr = room_idx + base_offset + door_conn_base
                byte_val = rom[addr] & 0xFF
                rom[addr] = ((byte_val & 0x1F) | 0x20) & 0xFF

            # East wall
            if col == GRID_COLS - 1 or level_grid[row][col + 1] != cell_level:
                addr = room_idx + base_offset + door_conn_base
                byte_val = rom[addr] & 0xFF
                rom[addr] = ((byte_val & ~0x1C) | 4) & 0xFF
    # =========================================================================
    # END WORKAROUND
    # =========================================================================
