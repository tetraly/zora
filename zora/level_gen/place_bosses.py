"""Place bosses in dungeon rooms.

Selects boss enemy types per level, then places them in randomly chosen
rooms that match the level's area.  Also writes boss sprite page IDs
to ROM.

Ported line-by-line from NewLevelPlaceBosses.cs (newLevelPlaceBosses,
Module.cs:28930).  Cross-referenced against Module.cs:28930-29224.
No discrepancies found — .cs file matches Module.cs exactly.
"""

from __future__ import annotations

from zora.level_gen.helpers import safe_for_dodongo, safe_for_gleeok, safe_for_gohma
from zora.level_gen.rom_buffer import (
    LevelGrid,
    ROMOFS_DOOR_DATA,
    ROMOFS_ENEMY_DATA,
    ROMOFS_ITEM_DATA,
)
from zora.rng import Rng

# Boss sprite page ID ROM base: rom[0xC025 + lv*2] for lv=1..8
_ROMOFS_BOSS_SPRITE_PAGE = 49189  # 0xC025

_BOSS_GROUPS: list[list[int]] = [
    [61, 49, 50, 57, 56],          # Group 0 (easy)
    [51, 52, 60, 131, 132, 133],   # Group 1 (medium)
    [135, 136],                     # Group 2 (hard)
]

_BOSS_ASSIGNMENT = [0, 0, 0, 1, 1, 0, 1, 0, 1, 2]

_SPRITE_PAGE_IDS = [159, 163, 167]

_BOSS_COUNT_PER_LEVEL = [0, 1, 1, 1, 2, 2, 2, 5, 6, 5]

_MAX_ATTEMPTS = 10000
_MAX_ROOM_DRAWS = 100000


def new_level_place_bosses(
    rom: bytearray,
    rng: Rng,
    level: int,
    level_grid: LevelGrid,
) -> bool:
    """Place bosses for all levels in the current grid group.

    *level* is the starting level (1 for levels 1-6, 7 for levels 7-9).
    Returns True if all bosses were placed, False on failure.
    """
    # 3 RNG advances (sodiumRand::seed is a no-op)
    rng.next()
    rng.next()
    rng.next()

    # Assign boss group index per level, write sprite page IDs
    level_boss_group = [0] * 10
    for lv in range(1, 9):
        level_boss_group[lv] = _BOSS_ASSIGNMENT[lv]
        rom[_ROMOFS_BOSS_SPRITE_PAGE + lv * 2] = _SPRITE_PAGE_IDS[_BOSS_ASSIGNMENT[lv]]
    level_boss_group[9] = 2

    end_level = 7 if level == 1 else 10
    attempts = 0

    lv = level
    while lv < end_level:
        boss_count = _BOSS_COUNT_PER_LEVEL[lv]
        base_offset = 768 if lv > 6 else 0

        boss_idx = 0
        while boss_idx < boss_count:
            attempts += 1
            if attempts > _MAX_ATTEMPTS:
                return False

            # Inner loop: draw rooms until finding one in the right level
            # with empty ItemData.  Original has no limit; we add a safety cap.
            room = 0
            room_draws = 0
            while True:
                room_draws += 1
                if room_draws > _MAX_ROOM_DRAWS:
                    return False
                room = rng.next() % 128
                rr = room // 16
                rc = room % 16
                if level_grid[rr][rc] == lv:
                    item_byte = rom[room + base_offset + ROMOFS_ITEM_DATA]
                    if item_byte == 0:
                        break

            # Check screen type isn't special
            screen_byte = rom[room + base_offset + ROMOFS_ENEMY_DATA]
            screen_type_id = screen_byte & 0x7F
            if screen_type_id == 33 or screen_type_id == 41 \
                    or screen_type_id == 32 or screen_type_id == 96:
                continue

            # Pick random boss from level's group
            group = _BOSS_GROUPS[level_boss_group[lv]]
            boss_id = group[rng.next() % len(group)]

            boss_type_base = boss_id & 0x3F
            boss_high_bit = boss_id & 0x80

            # Gleeok check (types 130-133)
            if (boss_id - 130) & 0xFFFFFFFF <= 3:
                loc_byte = rom[room + base_offset + ROMOFS_ENEMY_DATA]
                if not safe_for_gleeok(loc_byte, boss_id):
                    continue

            # Gohma check (types 51, 52 without high bit)
            if boss_high_bit == 0 and (boss_type_base == 51 or boss_type_base == 52):
                loc_byte = rom[room + base_offset + ROMOFS_ENEMY_DATA]
                if not safe_for_gohma(loc_byte):
                    continue

            # Dodongo check (types 49, 50 without high bit)
            if boss_high_bit == 0 and (boss_type_base == 49 or boss_type_base == 50):
                loc_byte = rom[room + base_offset + ROMOFS_ENEMY_DATA]
                if not safe_for_dodongo(loc_byte):
                    continue

            # Skip if first boss and room has shutter doors (door type 3)
            if boss_idx == 0:
                door_byte = rom[room + base_offset + ROMOFS_DOOR_DATA]
                if (door_byte & 0x1F) == 3:
                    boss_idx = 0
                    continue

            # Write boss data to ROM
            rom[room + base_offset + ROMOFS_ITEM_DATA] = boss_id & 0x3F
            rom[room + base_offset + ROMOFS_ENEMY_DATA] = \
                (rom[room + base_offset + ROMOFS_ENEMY_DATA] & 0x7F) | (boss_id & 0x80)

            # First boss: set door type to 26 (boss door)
            if boss_idx == 0 and lv != 9:
                rom[room + base_offset + ROMOFS_DOOR_DATA] = \
                    (rom[room + base_offset + ROMOFS_DOOR_DATA] & ~0x1F) | 26

            boss_idx += 1
        lv += 1

    return True
