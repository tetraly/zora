"""Place enemies in dungeon rooms.

Builds per-level enemy pools from hardcoded source arrays combined with
overworld ROM data, then assigns random enemies to eligible rooms.

Ported line-by-line from NewLevelPlaceEnemies.cs (newLevelPlaceEnemies,
Module.cs:26869).  Cross-referenced against Module.cs:26869-28728.
Safety helpers cross-referenced against Module.cs:31420-32345.
"""

from __future__ import annotations

from zora.level_gen.rom_buffer import (
    LevelGrid,
    ROMOFS_ENEMY_DATA,
    ROMOFS_ITEM_DATA,
    ROMOFS_ROOM_FLAGS,
    ROMOFS_SCREEN_LAYOUT,
)
from zora.rng import Rng

# ---------------------------------------------------------------------------
# Data tables — copied verbatim from C#
# ---------------------------------------------------------------------------

# Level-to-group mapping (obj9, 10 elements). Index 0 unused.
_GROUP_MAP: list[int] = [0, 0, 0, 1, 2, 1, 2, 0, 1, 2]

# Excluded enemy IDs (obj11, 18 elements)
_EXCLUDED: list[int] = [
    61, 49, 50, 57, 56, 51, 52, 60,       # bosses
    258, 259, 260, 261, 263, 264,           # boss high-bit variants
    0, 62, 55, 54,                          # empty + Ganon + Patra
]

# 18 enemy low-byte arrays (obj4).
# Indices 0-8 = Q1 levels 1-9, indices 9-17 = Q2 levels 1-9.
_ENEMY_LOW: list[list[int]] = [
    [10, 6, 42, 61, 0, 21, 85, 6, 231, 155, 106, 219, 42, 27, 0, 106],                     # 0: L1 Q1
    [0, 50, 70, 232, 85, 1, 238, 104, 5, 70, 85, 168, 104, 40, 149, 0, 104],               # 1: L2 Q1
    [219, 173, 0, 239, 91, 19, 173, 60, 75, 238, 11, 11, 239, 203, 83, 147, 0],            # 2: L3 Q1
    [219, 9, 0, 60, 53, 82, 3, 82, 85, 114, 82, 179, 83, 82, 219, 18, 82, 219, 0],        # 3: L4 Q1
    [140, 0, 0, 219, 57, 86, 112, 176, 176, 11, 0, 112, 83, 49, 83, 76, 112, 48, 0, 86],  # 4: L5 Q1
    [123, 179, 0, 4, 179, 164, 252, 52, 179, 123, 123, 247, 114, 252, 82, 252, 123, 9, 219, 83, 100, 0, 100],  # 5: L6 Q1
    [53, 186, 69, 49, 249, 245, 133, 186, 133, 56, 186, 61, 0, 186, 56, 245, 49, 186, 234, 238, 69, 219, 133, 57, 234, 104, 0, 1, 1, 1],  # 6: L7 Q1
    [75, 86, 51, 184, 0, 53, 60, 5, 140, 244, 139, 214, 51, 244, 11, 176, 76, 214, 60, 244, 60, 0, 239],  # 7: L8 Q1
    [239, 179, 247, 123, 241, 241, 59, 58, 179, 87, 35, 8, 252, 123, 179, 213, 82, 179, 213, 8, 247, 55, 213, 219, 239, 146, 123, 246, 62, 164, 252, 163, 241, 83, 151, 7, 252, 123, 58, 179, 123, 7, 219, 83, 252, 241, 0, 241, 59, 0, 252, 7, 123],  # 8: L9 Q1
    [61, 0, 5, 249, 1, 213, 50, 5, 238, 106, 6, 155, 0, 70],                               # 9: L1 Q2
    [134, 0, 54, 134, 170, 69, 168, 134, 49, 192, 231],                                     # 10: L2 Q2
    [173, 60, 75, 0, 219, 219, 3, 112, 0, 11, 219, 176, 75, 19, 11, 238, 112, 19, 0, 112], # 11: L3 Q2
    [0, 99, 51, 4, 82, 45, 221, 252, 60, 247, 83, 253, 114, 246, 173, 221, 253, 0],        # 12: L4 Q2
    [44, 254, 219, 140, 184, 83, 0, 50, 49, 173, 176, 53, 11, 140, 75, 0, 254, 61, 176, 56, 184, 56, 108, 45, 239, 0, 109],  # 13: L5 Q2
    [219, 3, 109, 123, 123, 0, 82, 44, 51, 253, 219, 60, 246, 241, 9, 252, 114, 252, 253, 123, 0],  # 14: L6 Q2
    [1, 49, 173, 49, 255, 56, 133, 69, 134, 108, 238, 49, 245, 0, 54, 255, 69, 49, 56, 170, 255, 1, 133, 232, 0, 186, 232, 245, 219, 133, 255, 61, 173, 0],  # 15: L7 Q2
    [219, 0, 5, 76, 254, 184, 238, 45, 60, 51, 240, 0, 140, 140, 204, 140, 76, 254, 173, 0, 184, 254, 244, 60, 254],  # 16: L8 Q2
    [59, 7, 236, 55, 114, 241, 246, 237, 123, 8, 62, 163, 252, 0, 0, 247, 253, 0, 0, 45, 114, 173, 0, 83, 164, 8, 123, 7, 179, 58, 221, 241, 247, 173, 221, 123, 253, 82, 246, 59, 123, 252, 253, 0],  # 17: L9 Q2
]

# 18 enemy high-bit arrays (obj7, parallel to _ENEMY_LOW)
_ENEMY_HIGH: list[list[int]] = [
    [128, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],                                   # 0: L1 Q1
    [0, 0, 0, 0, 0, 128, 128, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],                               # 1: L2 Q1
    [0, 128, 0, 128, 0, 0, 128, 0, 0, 128, 0, 0, 128, 0, 0, 0, 0],                           # 2: L3 Q1  (verified against IL)
    [0, 128, 0, 0, 0, 0, 128, 0, 0, 128, 0, 128, 0, 0, 0, 0, 0, 0, 0],                     # 3: L4 Q1
    [0, 0, 0, 0, 0, 0, 0, 128, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],                       # 4: L5 Q1
    [128, 128, 0, 128, 128, 0, 128, 0, 128, 128, 128, 128, 128, 128, 0, 128, 128, 128, 0, 0, 0, 0, 0],  # 5: L6 Q1
    [0, 128, 0, 0, 128, 128, 0, 128, 0, 0, 128, 0, 0, 128, 0, 128, 0, 128, 0, 128, 0, 0, 0, 0, 0, 0, 0, 128, 128, 128],  # 6: L7 Q1
    [0, 0, 0, 128, 0, 0, 0, 128, 0, 128, 0, 0, 0, 128, 0, 128, 0, 0, 0, 128, 0, 0, 128],   # 7: L8 Q1  (verified against IL)
    [128, 128, 128, 128, 128, 128, 0, 0, 128, 0, 0, 128, 128, 128, 128, 0, 0, 128, 0, 128, 128, 0, 0, 0, 128, 0, 128, 128, 0, 0, 128, 0, 128, 0, 0, 128, 128, 128, 0, 128, 128, 128, 0, 0, 128, 128, 0, 128, 0, 0, 128, 128, 128],  # 8: L9 Q1
    [0, 0, 0, 128, 128, 0, 0, 0, 128, 0, 0, 0, 0, 0],                                       # 9: L1 Q2
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],                                                       # 10: L2 Q2
    [128, 0, 0, 0, 0, 0, 128, 0, 0, 0, 0, 128, 0, 0, 0, 128, 0, 0, 0, 0],                   # 11: L3 Q2
    [0, 0, 0, 128, 0, 0, 0, 128, 0, 128, 0, 128, 128, 128, 128, 0, 128, 0],                 # 12: L4 Q2
    [0, 128, 0, 0, 128, 0, 0, 0, 0, 128, 128, 0, 0, 0, 0, 0, 128, 0, 128, 0, 128, 0, 0, 0, 128, 0, 0],  # 13: L5 Q2
    [0, 128, 0, 128, 128, 0, 0, 0, 0, 128, 0, 0, 128, 128, 128, 128, 128, 128, 128, 128, 0],  # 14: L6 Q2
    [128, 0, 0, 0, 128, 0, 0, 0, 0, 0, 128, 0, 128, 0, 0, 128, 0, 0, 0, 0, 128, 128, 0, 0, 0, 128, 0, 128, 0, 0, 128, 0, 0, 0],  # 15: L7 Q2
    [0, 0, 128, 0, 128, 128, 128, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 128, 128, 0, 128, 128, 128, 0, 128],  # 16: L8 Q2
    [0, 128, 0, 0, 128, 128, 128, 0, 128, 128, 0, 0, 128, 0, 0, 128, 128, 0, 0, 0, 128, 0, 0, 0, 0, 128, 128, 128, 128, 0, 0, 128, 128, 128, 0, 128, 128, 0, 128, 0, 128, 128, 128, 0],  # 17: L9 Q2
]

# Overworld enemy table ROM addresses (read-only)
_ROMOFS_OW_TABLE_1 = 99600   # 0x18510
_ROMOFS_OW_TABLE_2 = 99728   # 0x18590


# ---------------------------------------------------------------------------
# Safety-check helpers
# ---------------------------------------------------------------------------

def _is_trap(enemy: int, flag: int) -> bool:
    """itsATrap (Module.cs:31420)."""
    if flag == 0:
        return False
    if enemy == 9 or enemy == 10:
        return True
    masked = enemy & 0x3F
    return masked == 46 or masked == 45 or masked == 55 or masked == 54


def _safe_for_lanmola(screen_type: int) -> bool:
    """safeForLanmola (Module.cs:31499). Returns True if room is safe."""
    st = screen_type & 0x3F
    return (st != 28 and st != 18 and st != 23 and st != 22 and st != 17
            and st != 27 and st != 12 and st != 15 and st != 1 and st != 32
            and st != 51 and st != 39 and st != 41 and st != 4 and st != 9
            and st != 11)


def _safe_for_rupees(screen_type: int) -> bool:
    """safeForRupees (Module.cs:31908). Returns True if room is safe."""
    st = screen_type & 0x3F
    return (st != 18 and st != 23 and st != 24 and st != 20 and st != 19
            and st != 25 and st != 22 and st != 12 and st != 30 and st != 26
            and st != 15 and st != 14 and st != 9 and st != 11 and st != 16
            and st != 32 and st != 12 and st != 14)


def _safe_for_traps(screen_type: int) -> bool:
    """safeForTraps (Module.cs:31872). Returns True if room is safe."""
    st = screen_type & 0x3F
    return (st != 18 and st != 8 and st != 28 and st != 9 and st != 7
            and st != 41 and st != 15 and st != 12)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def new_level_place_enemies(
    rom: bytearray,
    rng: Rng,
    level: int,
    level_grid: LevelGrid,
    allow_2nd_quest: bool,
) -> None:
    """Place enemies for all levels in the current grid group.

    *level* is the starting level (1 for levels 1-6, 7 for levels 7-9).
    *allow_2nd_quest* controls Q2 enemy merging and ROM epilogue writes.
    """
    # sodiumRand::seed is a no-op. Discard 2 values.
    rng.next()
    rng.next()

    # --- Phase 1: Build 8 deduped enemy sets from 18 source arrays ---
    sets: list[set[int]] = [set() for _ in range(8)]

    for arr_idx in range(18):
        group_idx = _GROUP_MAP[(arr_idx % 9) + 1]
        lo = _ENEMY_LOW[arr_idx]
        hi = _ENEMY_HIGH[arr_idx]

        for j in range(len(lo)):
            combined = (hi[j] << 1) | lo[j]

            # The original sets the sprite-page bit (hi=128 -> bit 8)
            # on boss/special enemies (6-bit codes 0x32-0x3F).  On the
            # NES this is fine — the engine reads the 6-bit enemy code
            # and the sprite-page flag independently.  Our parser
            # combines them into a single enemy_code (6bit + 0x40).
            # Codes 0x40-0x52 and 0x62-0x7F are valid Enemy enum
            # values (mixed enemy groups), so we keep bit 8 for those.
            # Only strip for the 0x53-0x61 gap which has no enum entry.
            if combined & 0x100:
                code_if_grouped = (combined & 0x3F) + 0x40
                if 0x53 <= code_if_grouped <= 0x61:
                    combined &= 0xFF

            if combined in _EXCLUDED:
                continue
            if 267 <= combined <= 288:
                continue
            if (combined & 0x3F) == 0:
                continue

            quest_off = 4 if arr_idx >= 9 else 0
            sets[quest_off + group_idx].add(combined)

            if allow_2nd_quest and arr_idx >= 9:
                sets[group_idx].add(combined)

    # --- Phase 2: Overworld enemy collection into sets 3 and 7 ---
    for screen in range(128):
        hi_bit = (rom[screen + _ROMOFS_OW_TABLE_2] & 0x80) << 1
        lo_byte = rom[screen + _ROMOFS_OW_TABLE_1] & 0x3F
        combined = hi_bit | lo_byte
        if combined != 0:
            sets[3].add(combined)
            sets[7].add(combined)

    # --- Phase 3: Convert sets to sorted lists ---
    pools: list[list[int]] = [sorted(s) for s in sets]

    # --- Phase 4: Room-by-room enemy placement ---
    base_offset = 768 if level != 1 else 0

    room = 0
    while room < 128:
        grid_row = room // 16
        grid_col = room % 16
        cell_value = level_grid[grid_row][grid_col]

        if cell_value == 0:
            room += 1
            continue

        screen_addr = room + base_offset + ROMOFS_ENEMY_DATA
        screen_type = rom[screen_addr] & 0x3F

        if screen_type == 0x21 or screen_type == 0x29:
            room += 1
            continue

        loc_byte = rom[screen_addr - 128]
        if loc_byte != 0 or screen_type == 0x20:
            room += 1
            continue

        group_idx = _GROUP_MAP[cell_value]
        pool = pools[group_idx]
        if len(pool) == 0:
            room += 1
            continue

        selected = pool[rng.next() % len(pool)]

        # Lanmola check (IDs 58=0x3A, 59=0x3B)
        if (selected == 58 or selected == 59) and not _safe_for_lanmola(screen_type):
            continue  # retry same room

        # Rupee enemy check (ID 53=0x35)
        if selected == 53 and not _safe_for_rupees(screen_type):
            continue

        # Trap check
        if _is_trap(selected & 0x3F, selected & 0x100) and not _safe_for_traps(screen_type):
            continue

        # =================================================================
        # WORKAROUND — NOT IN ORIGINAL C# PORT
        #
        # The original C# does not check whether an unkillable NPC enemy
        # (OLD_MAN through OLD_MAN_6, 6-bit codes 0x0B-0x12) is placed in
        # a room with shutter doors and a kill-to-open room action.  Since
        # NPCs cannot be killed, the shutters never open, creating a
        # dead-end room.  Re-roll for another enemy when this happens.
        # =================================================================
        enemy_6bit = selected & 0x3F
        if 0x0B <= enemy_6bit <= 0x12:
            t5_addr = room + base_offset + ROMOFS_ROOM_FLAGS
            room_action = rom[t5_addr] & 0x07
            if room_action in (1, 2, 6, 7):
                t0_addr = room + base_offset + ROMOFS_SCREEN_LAYOUT
                t1_addr = t0_addr + 128
                t0_byte = rom[t0_addr]
                t1_byte = rom[t1_addr]
                has_shutter = (
                    ((t0_byte >> 5) & 0x07) == 7
                    or ((t0_byte >> 2) & 0x07) == 7
                    or ((t1_byte >> 5) & 0x07) == 7
                    or ((t1_byte >> 2) & 0x07) == 7
                )
                if has_shutter:
                    continue  # retry same room
        # =================================================================
        # END WORKAROUND
        # =================================================================

        # NPC north-wall check: the NES engine lets Link walk off the top
        # of the screen in NPC rooms if the north wall isn't solid.
        # Re-roll rather than placing an NPC here.
        if 0x0B <= enemy_6bit <= 0x12:
            t0_addr_nw = room + base_offset + ROMOFS_SCREEN_LAYOUT
            north_wall = (rom[t0_addr_nw] >> 5) & 0x07
            if north_wall != 1:
                continue  # retry same room

        # Write enemy to ROM
        rom[room + base_offset + ROMOFS_ITEM_DATA] = selected & 0xFF
        rom[screen_addr] = rom[screen_addr] | ((selected >> 1) & 0x80)

        room += 1

    # --- Phase 5: allow_2nd_quest epilogue ---
    if allow_2nd_quest:
        rom[70493] = 0xD0   # 0x1135D
        rom[70557] = 0xD0   # 0x1139D
        rom[70364] = 0xD0   # 0x112DC
