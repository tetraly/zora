"""Add dungeon entrance screens to the level map.

Determines which screen each dungeon entrance should be placed on,
then writes entrance data to ROM.

Ported line-by-line from NewLevelAddEntrances.cs (newLevelAddEntrances,
Module.cs:20486). Cross-referenced against Module.cs:20486-20695.

Discrepancies found in the .cs file (fixed here to match Module.cs):
- Level 9 filtering: .cs allows level-9 candidates at row!=7 if grid[6][col]==9.
  Module.cs unconditionally skips level 9 at row!=7, then separately checks
  grid[6][col]==9 only when row==7.
- Level 9 special data: .cs only writes GoriyaRoom. Module.cs writes both
  P_0[1551]=screenIndex AND P_0[1552]=screenIndex-16.
"""

from __future__ import annotations

from zora.level_gen.rom_buffer import (
    GRID_COLS,
    GRID_ROWS,
    LevelGrid,
    ROMOFS_ENTRANCE_DATA,
    ROMOFS_SCREEN_LAYOUT,
    ROMOFS_SCREEN_LAYOUT_Q2,
)
from zora.rng import Rng

_DIR_ROW = (1, 0, -1, 0)
_DIR_COL = (0, 1, 0, -1)


def new_level_add_entrances(
    rom: bytearray,
    rng: Rng,
    level_grid: LevelGrid,
    seed: int,
    shuffle_entrances: bool,
) -> tuple[bool, int, int]:
    """Add entrance rooms for levels 1-9.

    Returns (success, p0_1551, p0_1552) where the two ints are the
    level-9 special values (screenIndex and screenIndex-16).
    When level 9 is not placed or the call fails, they default to 0.
    """
    # sodiumRand::seed is a NO-OP in the original. Do NOT reseed.
    rng.next()
    rng.next()

    candidates: list[list[int]] = [[] for _ in range(10)]

    room_count = [0] * 10

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            lv = level_grid[row][col]
            if 0 < lv < 10:
                room_count[lv] += 1

    start_row = 0 if shuffle_entrances else 7

    for row in range(start_row, 8):
        for col in range(GRID_COLS):
            cell_level = level_grid[row][col]

            if cell_level == 0:
                continue

            # Cell below must differ (unless at row 7)
            if row + 1 <= 7 and col <= 15:
                if level_grid[row + 1][col] == cell_level:
                    continue

            # Check 4 neighbors for matching level connectivity
            for d in range(4):
                nr = row + _DIR_ROW[d]
                nc = col + _DIR_COL[d]
                if 0 <= nr <= 7 and 0 <= nc <= 15:
                    if level_grid[row][col] == level_grid[nr][nc]:
                        break
            else:
                # No matching neighbor found
                continue

            # Level 9 special filtering (from Module.cs:20601-20613)
            if cell_level == 9:
                if row != 7:
                    continue
                if level_grid[6][col] != 9:
                    continue

            screen_index = row * 16 + col
            candidates[cell_level].append(screen_index)

    p0_1551 = 0
    p0_1552 = 0

    for level in range(1, 10):
        if len(candidates[level]) == 0 and room_count[level] > 0:
            return (False, 0, 0)

        if len(candidates[level]) > 0:
            count = len(candidates[level])
            idx = rng.next() % count
            screen_index = candidates[level][idx]

            # Write entrance screen index to level info block
            rom[level * 252 + ROMOFS_ENTRANCE_DATA] = screen_index & 0xFF

            # Configure entrance room in ROM
            layout_base = ROMOFS_SCREEN_LAYOUT_Q2 if level > 6 else ROMOFS_SCREEN_LAYOUT

            # Clear south wall bits 2-4: &= ~0x1C = &= 0xE3 = &= -29
            rom[screen_index + layout_base] &= 0xFF & (~0x1C)

            # Set entrance flag (Table 3, +384 = +0x180)
            rom[screen_index + layout_base + 384] = 33

            # Set room type bits (Table 4, +512 = +0x200): clear low 5, set 3
            rom[screen_index + layout_base + 512] &= 0xFF & (~0x1F)
            rom[screen_index + layout_base + 512] |= 3

            # Set visit flag (Table 5, +640 = +0x280)
            rom[screen_index + layout_base + 640] = 1

            # Level 9 special data (Module.cs:20663-20665)
            if level == 9:
                p0_1551 = screen_index
                p0_1552 = screen_index - 16

    return (True, p0_1551, p0_1552)
