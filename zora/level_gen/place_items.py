"""Place item rooms in dungeon levels.

For each level, finds random rooms belonging to that level whose door-type
byte is not already reserved, then stamps item-room door types into the
ROM door table.

Ported line-by-line from NewLevelPlaceItems.cs (newLevelPlaceItems,
Module.cs:20346).  Cross-referenced against Module.cs:20346-20482.
No discrepancies found — .cs file matches Module.cs exactly.
"""

from __future__ import annotations

from zora.level_gen.rom_buffer import LevelGrid, ROMOFS_DOOR_DATA
from zora.rng import Rng

_FORBIDDEN_DOOR_TYPES = {3, 14, 26, 27, 22, 23, 29, 30}

_MAX_ATTEMPTS = 10000


def new_level_place_items(
    rom: bytearray,
    rng: Rng,
    level: int,
    level_grid: LevelGrid,
) -> bool:
    """Place item rooms for all levels in the current grid group.

    *level* is the starting level (1 for levels 1-6, 7 for levels 7-9).
    Returns True if all items were placed, False on failure.
    """
    # sodiumRand::seed is a no-op; two RNG advances follow it
    rng.next()
    rng.next()

    end_level = 7 if level == 1 else 10

    for lv in range(level, end_level):
        base_offset = 768 if lv >= 7 else 0
        attempts = 0

        # --- Phase 1: item type 22 (primary item) ---
        room = rng.next() % 128
        while True:
            row = room // 16
            col = room % 16

            if level_grid[row][col] == lv:
                door_byte = rom[room + base_offset + ROMOFS_DOOR_DATA] & 0x7F
                if door_byte not in _FORBIDDEN_DOOR_TYPES:
                    rom[room + base_offset + ROMOFS_DOOR_DATA] = \
                        (rom[room + base_offset + ROMOFS_DOOR_DATA] & ~0x1F) | 22
                    break

            room = rng.next() % 128
            if attempts > _MAX_ATTEMPTS:
                return False
            attempts += 1

        # --- Phase 2: item type 23 (secondary item) ---
        while True:
            row = room // 16
            col = room % 16

            if level_grid[row][col] == lv:
                door_byte = rom[room + base_offset + ROMOFS_DOOR_DATA] & 0x7F
                if door_byte not in _FORBIDDEN_DOOR_TYPES:
                    rom[room + base_offset + ROMOFS_DOOR_DATA] = \
                        (rom[room + base_offset + ROMOFS_DOOR_DATA] & ~0x1F) | 23
                    break

            room = rng.next() % 128
            if attempts > _MAX_ATTEMPTS:
                return False
            attempts += 1

        # --- Phase 3: levels 1 and 2 only — item type (level + 28) ---
        if lv == 1 or lv == 2:
            while True:
                row = room // 16
                col = room % 16

                if level_grid[row][col] == lv:
                    door_byte = rom[room + base_offset + ROMOFS_DOOR_DATA] & 0x7F
                    if door_byte not in _FORBIDDEN_DOOR_TYPES:
                        rom[room + base_offset + ROMOFS_DOOR_DATA] = \
                            (rom[room + base_offset + ROMOFS_DOOR_DATA] & ~0x1F) | (lv + 28)
                        break

                room = rng.next() % 128
                if attempts > _MAX_ATTEMPTS:
                    return False
                attempts += 1

    return True
