"""Create rooms for new dungeon levels by selecting room screen types
from weighted probability tables, then writing ROM bytes per room.

Ported line-by-line from NewLevelRooms.cs (newLevelRooms, Module.cs:26649).
Cross-referenced against Module.cs — .cs file treated as sole source of truth
per instructions.

Option B literal translation: all byte offsets, magic numbers, and ROM
addresses preserved exactly as in the C#.
"""

from __future__ import annotations

from zora.level_gen.rom_buffer import (
    LevelGrid,
    ROMOFS_ENEMY_DATA,
)
from zora.rng import Rng


# -----------------------------------------------------------------------
# ItemWeights: 9 per-level weight arrays (32 elements each) for
# _new_level_get_item.  Indexed by (level - 1).
# Extracted from decompiled lines 25712-26134.
# Active positions after zeroing indices 14,22,23,26,27,29,30: 0, 3, 15, 25.
# -----------------------------------------------------------------------

_ITEM_WEIGHTS: list[list[int]] = [
    [0,0,0, 1, 0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0, 0, 6, 0,0, 0,0,0,0],  # L1 total=7
    [2,0,0, 4, 0,0,0,0, 0,0,0,0, 0,0,0,1, 0,0,0,0, 0,0,0,0, 0, 4, 0,0, 0,0,0,0],  # L2 total=11
    [3,0,0, 2, 0,0,0,0, 0,0,0,0, 0,0,0,1, 0,0,0,0, 0,0,0,0, 0, 5, 0,0, 0,0,0,0],  # L3 total=11
    [0,0,0, 8, 0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0, 0, 4, 0,0, 0,0,0,0],  # L4 total=12
    [2,0,0, 3, 0,0,0,0, 0,0,0,0, 0,0,0,1, 0,0,0,0, 0,0,0,0, 0, 7, 0,0, 0,0,0,0],  # L5 total=13
    [1,0,0, 8, 0,0,0,0, 0,0,0,0, 0,0,0,1, 0,0,0,0, 0,0,0,0, 0, 5, 0,0, 0,0,0,0],  # L6 total=15
    [7,0,0,11, 0,0,0,0, 0,0,0,0, 0,0,0,3, 0,0,0,0, 0,0,0,0, 0, 4, 0,0, 0,0,0,0],  # L7 total=25
    [3,0,0, 8, 0,0,0,0, 0,0,0,0, 0,0,0,3, 0,0,0,0, 0,0,0,0, 0, 6, 0,0, 0,0,0,0],  # L8 total=20
    [5,0,0,29, 0,0,0,0, 0,0,0,0, 0,0,0,7, 0,0,0,0, 0,0,0,0, 0, 4, 0,0, 0,0,0,0],  # L9 total=45
]


def _new_level_get_item(rng: Rng, level: int) -> int:
    """Select a door/room type index for a dungeon room.

    Port of zeldaMapGenerator::newLevelGetItem (decompiled line 25706).

    RNG consumption: caller already consumed 1 (seed param, no-op).
    Internally consumes 2 discards + 1 pick = 3.
    """
    level -= 1

    # 2 RNG discards (sodiumRand::seed is no-op)
    rng.next()
    rng.next()

    level = max(0, min(level, len(_ITEM_WEIGHTS) - 1))
    weights = _ITEM_WEIGHTS[level]

    total = 0
    for i in range(len(weights)):
        total += weights[i]
    if total <= 0:
        return 0

    pick = rng.next() % total
    for i in range(len(weights)):
        pick -= weights[i]
        if pick < 0:
            return i
    return 0


def new_level_rooms(
    rom: bytearray,
    rng: Rng,
    level_grid: LevelGrid,
    seed: int,
    level_start: int,
    add_2nd_quest: bool,
    goriya_room: int = 0,
) -> bool:
    """Create rooms for dungeon levels by weighted random selection.

    *level_start* is 1 (levels 1-6) or 7 (levels 7-9).
    *goriya_room* is needed for L9 special room placement (from add_entrances).
    Returns True on success, False if placement failed.
    """
    # sodiumRand::seed is a no-op; advance RNG twice
    rng.next()
    rng.next()

    # --- 10 Q1 probability tables (128 elements each) ---
    q1_tables: list[list[int]] = [
        [
            1,0,2,1,1,0,0,0, 0,0,0,0,0,1,0,0,
            0,0,0,0,0,1,0,1, 0,0,0,0,0,1,2,1,
            0,1,0,0,0,0,1,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,1,0,0,0,0,0,
            0,0,1,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            1,0,2,1,1,0,0,0, 0,0,0,0,0,1,0,0,
            0,0,0,0,0,1,0,1, 0,0,0,0,0,1,2,1,
            0,1,0,0,0,0,1,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,1,0,0,0,0,0,
            0,0,1,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            4,0,1,2,0,0,0,0, 0,0,0,0,0,2,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,1,1,1,
            0,1,0,0,1,2,1,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            4,0,0,1,0,0,0,0, 1,0,0,0,0,0,0,1,
            0,1,0,0,0,0,0,0, 0,0,0,1,0,2,1,1,
            0,1,0,0,0,1,1,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,1,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            1,1,1,1,0,1,0,0, 0,0,0,0,1,0,0,0,
            0,1,1,0,0,2,1,1, 1,0,0,0,0,0,0,0,
            0,1,0,0,0,0,2,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,2,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            1,0,1,0,0,0,0,1, 0,0,0,0,0,0,0,0,
            0,0,1,1,1,2,0,2, 2,0,0,0,0,1,1,0,
            0,1,0,0,1,0,3,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,2,0,0,0,0,0,
            0,0,1,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            1,1,0,2,0,1,0,0, 0,0,1,0,0,1,0,0,
            0,0,0,3,1,0,0,1, 1,0,0,1,0,1,0,1,
            0,1,0,0,1,0,2,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,2,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,1,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            3,0,1,0,1,0,0,0, 0,1,1,0,0,1,0,0,
            0,0,0,1,0,0,1,0, 1,1,0,0,0,1,1,1,
            0,1,0,3,4,2,4,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 1,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,2,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            3,0,0,0,0,1,0,0, 0,0,0,0,0,0,0,0,
            0,2,0,0,0,0,1,0, 1,0,0,1,1,0,0,0,
            0,1,0,3,3,2,3,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,2,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            5,0,0,1,0,0,0,0, 0,0,2,0,1,0,1,0,
            0,1,1,1,4,0,1,1, 1,2,0,3,1,1,1,3,
            0,1,0,2,0,4,7,1, 1,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 1,0,2,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,7,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
    ]

    # --- 10 Q2 probability tables (128 elements each) ---
    q2_tables: list[list[int]] = [
        [
            0,0,1,0,1,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,1,0,0, 1,0,0,1,0,1,1,1,
            0,1,0,1,1,1,0,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,1,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            0,0,1,0,1,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,1,0,0, 1,0,0,1,0,1,1,1,
            0,1,0,1,1,1,0,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,1,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            1,0,1,0,0,1,0,1, 0,0,1,0,0,1,1,0,
            1,1,0,0,0,0,0,0, 0,0,0,2,1,0,1,0,
            0,1,0,4,0,0,0,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,1,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            0,0,0,1,0,0,0,0, 0,0,0,0,0,1,0,0,
            0,1,0,0,0,0,0,0, 0,0,0,1,0,0,0,0,
            0,1,0,1,1,1,1,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 1,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            1,0,0,1,1,0,0,0, 0,0,1,0,0,0,0,0,
            0,1,0,1,0,2,0,1, 0,0,0,1,0,1,0,2,
            0,1,0,3,3,0,4,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,1,1,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,1,
            1,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            1,0,0,0,0,1,0,0, 0,0,0,0,0,1,0,0,
            0,0,0,0,0,1,0,1, 1,0,0,3,1,1,0,0,
            0,1,0,1,0,1,1,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,1,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            0,0,0,0,0,1,0,0, 0,0,0,1,1,0,1,0,
            0,0,0,1,1,1,1,0, 1,1,0,0,1,0,0,0,
            0,1,0,1,3,0,1,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,1,0,0,0,0,1,1, 0,0,1,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            0,0,0,0,0,1,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,1,0,1,0,0, 1,0,0,1,0,0,0,0,
            0,1,0,4,3,0,2,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,1,0,0,0,0,1,0, 0,0,1,0,0,0,0,0,
            0,2,0,0,0,0,0,0, 0,0,1,0,0,0,0,3,
            1,0,1,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            0,0,0,0,1,0,0,0, 0,0,0,0,1,0,0,1,
            0,0,0,0,0,1,2,0, 1,0,0,0,0,0,1,0,
            0,1,0,3,4,0,2,0, 0,1,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,1,1, 3,0,2,0,0,1,0,0,
            0,2,0,0,0,0,0,0, 0,0,2,0,0,0,0,1,
            1,0,2,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
        [
            1,1,0,1,0,0,0,0, 1,0,0,0,1,1,0,1,
            0,0,1,0,1,2,2,0, 0,1,0,0,0,2,0,0,
            0,1,0,10,2,0,3,1, 1,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,3,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,1,
            5,0,2,0,0,0,0,0, 0,0,0,0,0,0,0,0,
            0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,
        ],
    ]

    # Merge Q2 tables onto Q1 if enabled
    table: list[list[int]] = []
    for i in range(10):
        row = list(q1_tables[i])
        if add_2nd_quest:
            for j in range(128):
                row[j] += q2_tables[i][j]
        table.append(row)

    # Zero out reserved indices and adjust index 38
    for lv in range(10):
        table[lv][90] = 0
        table[lv][28] = 0
        table[lv][27] = 0
        table[lv][92] = 0
        table[lv][40] = 0
        table[lv][39] = 0
        table[lv][41] = 0
        table[lv][33] = 0
        table[lv][38] -= 1
        if lv > 3:
            table[lv][38] -= 1

    # Compute per-level weight sums
    weight_sums: list[int] = [0] * 10
    for i in range(10):
        s = 0
        for j in range(128):
            s += table[i][j]
        weight_sums[i] = s

    # Determine base offset and end level
    if level_start == 1:
        base_offset = 0
    else:
        base_offset = 768

    rom_base = base_offset + ROMOFS_ENEMY_DATA

    # === PRE-LOOP: Place boss rooms, item rooms, L5/L7/L9 specials ===
    end_level = 6 if level_start == 1 else 9
    l9_item_counter = 12
    item_room_counts = [0, 1, 1, 1, 1, 2, 2, 1, 2, 3]

    for level in range(level_start, end_level + 1):
        level_data_addr = level * 252 + 103225

        # --- Part A: Place boss room ---
        boss_room = rng.next() % 128
        retries = 0
        while True:
            row = boss_room // 16
            col = boss_room % 16
            if row < len(level_grid) and col < len(level_grid[row]):
                if level_grid[row][col] == level:
                    existing = rom[boss_room + rom_base] & 0xFF
                    if (existing & 0x7F) == 0:
                        break
            boss_room = rng.next() % 128
            retries += 1
            if retries > 1000:
                return False

        # Write boss room data
        rom[boss_room + rom_base] = rom[boss_room + rom_base] & 0x80
        if level != 9:
            rom[boss_room + rom_base] = rom[boss_room + rom_base] | 41
            rom[boss_room + rom_base + 128] = 27
        else:
            # L9 special: write entrance room at GoriyaRoom position
            gr = goriya_room
            rom[gr + rom_base] = 166  # unchecked((byte)(-90)) = 0xA6
            rom[gr + rom_base - 128] = 11
            rom[gr + rom_base + 128] = 3
            rom[gr + rom_base + 256] = 0
            rom[gr + rom_base - 256] = rom[gr + rom_base - 256] & 0xFC

            # Find empty L9 room for boss approach
            retries = 0
            while True:
                row = boss_room // 16
                col = boss_room % 16
                if row < len(level_grid) and col < len(level_grid[row]):
                    if level_grid[row][col] == 9:
                        if (rom[boss_room + rom_base] & 0x7F) == 0:
                            break
                boss_room = rng.next() % 128
                retries += 1
                if retries > 1000:
                    return False

            # Write boss approach room
            rom[boss_room + rom_base] = 39
            rom[boss_room + rom_base - 128] = 55
            rom[boss_room + rom_base - 256] = rom[boss_room + rom_base - 256] & 0xFC
            rom[boss_room + rom_base - 256] = rom[boss_room + rom_base - 256] | 2
            rom[boss_room + rom_base + 128] = rom[boss_room + rom_base + 128] & 0xE0
            rom[boss_room + rom_base + 128] = rom[boss_room + rom_base + 128] | 3
            rom[boss_room + rom_base + 256] = 1

            # Find another empty L9 room for the boss room itself
            boss_room = rng.next() % 128
            retries = 0
            while True:
                row = boss_room // 16
                col = boss_room % 16
                if row < len(level_grid) and col < len(level_grid[row]):
                    if level_grid[row][col] == 9:
                        if (rom[boss_room + rom_base] & 0x7F) == 0:
                            break
                boss_room = rng.next() % 128
                retries += 1
                if retries > 1000:
                    return False

            # Write L9 boss room
            rom[boss_room + rom_base] = rom[boss_room + rom_base] & 0x80
            rom[boss_room + rom_base] = rom[boss_room + rom_base] | 40
            rom[boss_room + rom_base - 128] = 62
            rom[boss_room + rom_base + 128] = 0x8E

        # --- Part B: Scan for door entry position (value 137 in level data) ---
        scan_pos = 0
        scan_addr = level_data_addr
        while rom[scan_addr] != 137:
            scan_pos += 1
            scan_addr += 1
        rom[boss_room + rom_base + 256] = (scan_pos * 16 + 1) & 0xFF

        # --- Part C: Place item rooms ---
        item_count = item_room_counts[level]
        placed = 0
        while placed < item_count:
            item_room = rng.next() % 112
            item_retries = 0
            failed = False
            while True:
                row = item_room // 16
                col = item_room % 16
                if row < len(level_grid) and col < len(level_grid[row]):
                    if level_grid[row][col] == level:
                        if (rom[item_room + rom_base] & 0x7F) == 0:
                            break
                item_room = rng.next() % 112
                item_retries += 1
                if item_retries >= 1000:
                    failed = True
                    break
            if failed:
                break

            rom[item_room + rom_base] = 166  # 0xA6
            if level == 9:
                rom[item_room + rom_base - 128] = l9_item_counter & 0xFF
                l9_item_counter += 1
            else:
                rom[item_room + rom_base - 128] = 13
            rom[item_room + rom_base - 256] = rom[item_room + rom_base - 256] & 0xFC
            rom[item_room + rom_base + 128] = rom[item_room + rom_base + 128] & 0xE0
            rom[item_room + rom_base + 128] = rom[item_room + rom_base + 128] | 3
            rom[item_room + rom_base + 256] = 1

            placed += 1

        # --- Part D: L5/L7 special rooms ---
        if level == 5 or level == 7:
            spec_room = rng.next() % 112
            spec_retries = 0
            while True:
                row = spec_room // 16
                col = spec_room % 16
                if row < len(level_grid) and col < len(level_grid[row]):
                    if level_grid[row][col] == level:
                        if (rom[spec_room + rom_base] & 0x7F) == 0:
                            break
                spec_room = rng.next() % 112
                spec_retries += 1
                if spec_retries > 4001:
                    return False

            rom[spec_room + rom_base] = 166  # 0xA6
            rom[spec_room + rom_base - 128] = 15
            rom[spec_room + rom_base - 256] = rom[spec_room + rom_base - 256] & 0xFC
            rom[spec_room + rom_base + 128] = rom[spec_room + rom_base + 128] | 3
            rom[spec_room + rom_base + 256] = 1

            if level == 7:
                spec_room = rng.next() % 112
                max_l7_retries = 100000
                l7_retries = 0
                while True:
                    row = spec_room // 16
                    col = spec_room % 16
                    if row < len(level_grid) and col < len(level_grid[row]):
                        if level_grid[row][col] == 7:
                            if (rom[spec_room + rom_base] & 0x7F) == 0:
                                break
                    spec_room = rng.next() % 112
                    l7_retries += 1
                    if l7_retries > max_l7_retries:
                        return False

                rom[spec_room + rom_base] = 38
                rom[spec_room + rom_base - 128] = 54
                rom[spec_room + rom_base - 256] = rom[spec_room + rom_base - 256] & 0xFC
                rom[spec_room + rom_base + 128] = rom[spec_room + rom_base + 128] | 3
                rom[spec_room + rom_base + 256] = 1

    # === END PRE-LOOP ===

    # Per-level door variant count tracker
    door_variant_count = [0] * 10

    # Door variant lookup table (34 entries)
    door_variants: list[list[int]] = [
        [0, 135, 137, 153, 172],
        [2, 135, 137, 200],
        [3, 137, 153, 201],
        [4, 137, 201],
        [5, 44, 220],
        [6, 137],
        [8, 137],
        [10, 137],
        [12, 136],
        [13, 172, 214],
        [14, 137],
        [15, 137],
        [17, 137],
        [18, 138, 214, 220],
        [19, 137, 138],
        [20, 137, 138],
        [21, 135, 136, 138],
        [22, 136, 137],
        [23, 137, 138],
        [24, 137, 138, 200],
        [25, 137],
        [27, 137],
        [28, 214],
        [29, 137, 138, 201],
        [30, 38, 214],
        [31, 201],
        [35, 137],
        [36, 135, 137],
        [37, 137],
        [38, 137],
        [40, 137],
        [41, 137],
        [90, 214],
        [99, 137],
    ]

    # Main room placement loop
    room = 0
    while room < 128:
        room_row = room // 16
        room_col = room % 16

        level_id = 0
        if room_row < len(level_grid) and room_col < len(level_grid[room_row]):
            level_id = level_grid[room_row][room_col]

        if level_id == 0:
            room += 1
            continue

        # Check if room's EnemyData byte is 0 (unoccupied)
        existing_byte = rom[room + rom_base]
        if existing_byte >= 128:
            existing_byte = existing_byte  # unsigned, handle sbyte cast
        if (existing_byte & 0x7F) != 0:
            room += 1
            continue

        # Look up level from LevelGrid
        grid_level = 0
        if room_row < len(level_grid) and room_col < len(level_grid[room_row]):
            grid_level = level_grid[room_row][room_col]
        if grid_level < 0 or grid_level >= len(table):
            grid_level = level_id

        total_weight = weight_sums[grid_level]
        if total_weight <= 0:
            rng.next()
            room += 1
            continue

        # Weighted random selection
        roll = rng.next() % total_weight
        screen_type = 0

        roll -= table[grid_level][0]
        while roll >= 0 and screen_type < 127:
            screen_type += 1
            roll -= table[grid_level][screen_type]

        # newLevelGetItem: caller consumes 1 RNG for seed param (no-op)
        rng.next()  # seed param consumed at call site
        item_data = _new_level_get_item(rng, grid_level)

        # Re-roll if itemData is 3 (shutter) and variant count < 4
        if door_variant_count[grid_level] < 4:
            while item_data == 3:
                reroll_level = 0
                if room_row < len(level_grid) and room_col < len(level_grid[room_row]):
                    reroll_level = level_grid[room_row][room_col]
                rng.next()  # seed param consumed at call site
                item_data = _new_level_get_item(rng, reroll_level)
                if door_variant_count[grid_level] >= 4:
                    break

        # --- Write 4 ROM bytes ---
        # Byte 0: EnemyData - screen type, preserve high bit
        rom[room + rom_base] = (rom[room + rom_base] & 0x80) | (screen_type & 0x7F)

        # Byte 1: DoorData (+128)
        rom[room + rom_base + 128] = item_data & 0xFF

        # Byte 2: RoomFlags (+256) - clear low 3 bits, set bit 0
        rom[room + rom_base + 256] = (rom[room + rom_base + 256] & ~0x07) | 1

        # Flag logic
        if (screen_type & 0x40) != 0 and screen_type != 96:
            rom[room + rom_base + 256] = (rom[room + rom_base + 256] & ~0x07) | 4
        elif rng.next() % 3 != 0:
            if rom[room + rom_base + 128] != 3:
                rom[room + rom_base + 256] = rom[room + rom_base + 256] | 7

        # Door variant selection
        variant_idx = -1
        for dv in range(len(door_variants)):
            if door_variants[dv][0] == screen_type:
                variant_idx = dv
                break

        if variant_idx >= 0 and len(door_variants[variant_idx]) > 1:
            # Variant matched — scan ROM for candidates
            level_for_variant = 0
            if room_row < len(level_grid) and room_col < len(level_grid[room_row]):
                level_for_variant = level_grid[room_row][room_col]

            level_data_addr = level_for_variant * 252 + 103225
            candidates: list[int] = []

            for vi in range(1, len(door_variants[variant_idx])):
                for pos in range(4):
                    addr = level_data_addr + pos
                    if 0 <= addr < len(rom):
                        rom_byte = rom[addr]
                        if rom_byte >= 128:
                            rom_byte_signed = rom_byte - 256
                        else:
                            rom_byte_signed = rom_byte
                        # C# does (sbyte)state.Rom[addr] then if < 0, += 256
                        # Net effect: unsigned comparison
                        rom_val = rom_byte
                        if rom_val == door_variants[variant_idx][vi]:
                            candidates.append(pos)

            if len(candidates) > 0:
                picked_variant = candidates[rng.next() % len(candidates)]
                rom[room + rom_base + 256] = (rom[room + rom_base + 256] & 0x0F) | ((picked_variant << 4) & 0xFF)
                door_variant_count[grid_level] += 1
            elif door_variant_count[grid_level] > 5:
                rom[room + rom_base + 128] = 3
                flag_byte = rom[room + rom_base + 256]
                if (flag_byte & 0x0F) == 7:
                    # EXE uses `b & -7` = 0xF9, NOT `& ~7` = 0xF8
                    rom[room + rom_base + 256] = flag_byte & 0xF9
            else:
                rom[room + rom_base] = 0
                # retry room (room-- equivalent: don't increment)
                continue
        else:
            # Screen type did NOT match any variant entry
            if door_variant_count[level_id] > 5:
                rom[room + rom_base + 128] = 3
                flag_byte = rom[room + rom_base + 256]
                if (flag_byte & 7) != 4:
                    rom[room + rom_base + 256] = (flag_byte & ~7) | 1
            else:
                rom[room + rom_base] = 0
                # retry room
                continue

        # Post-variant: decrement probability table for screen types 14, 15, 18
        if screen_type == 14 or screen_type == 15 or screen_type == 18:
            if 0 <= grid_level < len(table) and screen_type < len(table[grid_level]):
                table[grid_level][screen_type] -= 1
                weight_sums[grid_level] -= 1

        room += 1

    return True
