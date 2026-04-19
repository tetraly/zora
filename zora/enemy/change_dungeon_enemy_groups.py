"""Redistribute enemies across enemy sprite-set groups, then update rooms.

Reassigns which enemies belong to which sprite-set group (A/B/C, and
optionally OW), repacks sprite tile data, updates tile frame mappings,
expands companion variants, and replaces enemies in dungeon (and optionally
overworld) rooms.

Ported from changeDungeonEnemyGroups (change_dungeon_enemy_groups.cs).
"""

from __future__ import annotations

from zora.data_model import (
    SCREEN_ENTRANCE_TYPES,
    Enemy,
    EnemyData,
    EnemySpec,
    EnemySpriteSet,
    EntranceType,
    GameWorld,
    RoomType,
    SpriteData,
)
from zora.enemy.safety_checks import is_safe_for_room
from zora.rng import Rng

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum retries for the outer assignment loop (re-rolling all group assignments).
_MAX_OUTER_RETRIES = 1000

# Maximum retries when the inner assignment loop fails to place a single enemy.
_MAX_ASSIGNMENT_RETRIES = 1000

# Maximum retries when a safety check rejects a random enemy pick for a room.
_MAX_ROOM_RETRIES = 1000


# ---------------------------------------------------------------------------
# Enemy definitions: the 12 "safe" enemies that can be shuffled between groups.
# ---------------------------------------------------------------------------

# Number of 16-byte sprite tile columns each enemy requires.
# Each enemy sprite set (enemy_set_a/b/c) holds 34 columns (0x220 = 544 bytes).
# An enemy can only be assigned to a group with enough remaining column budget.
_ENEMY_TILE_COLUMNS: dict[Enemy, int] = {
    Enemy.ZOL:            4,
    Enemy.RED_GORIYA:    16,
    Enemy.RED_DARKNUT:   20,
    Enemy.VIRE:           8,
    Enemy.POLS_VOICE:     4,
    Enemy.LIKE_LIKE:      6,
    Enemy.RED_WIZZROBE:  12,
    Enemy.WALLMASTER:     4,
    Enemy.ROPE:           8,
    Enemy.STALFOS:        4,
    Enemy.GIBDO:          4,
    Enemy.RED_LANMOLA:    4,
}

# Vanilla enemy groups — which enemies originally belong to each sprite set.
# Used to detect which group a room's current enemy belongs to, so we know
# which new pool to draw from.
_VANILLA_ENEMY_GROUPS: dict[EnemySpriteSet, frozenset[Enemy]] = {
    EnemySpriteSet.A: frozenset({
        Enemy.BLUE_GORIYA, Enemy.RED_GORIYA,
        Enemy.WALLMASTER, Enemy.ROPE, Enemy.STALFOS,
    }),
    EnemySpriteSet.B: frozenset({
        Enemy.RED_DARKNUT, Enemy.BLUE_DARKNUT,
        Enemy.POLS_VOICE, Enemy.GIBDO,
    }),
    EnemySpriteSet.C: frozenset({
        Enemy.VIRE, Enemy.LIKE_LIKE,
        Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE,
        Enemy.RED_LANMOLA, Enemy.BLUE_LANMOLA,
    }),
}

# Companion expansions: after group assignment, if a primary enemy is in a
# group, its companion variant is added to the same group's replacement pool.
_COMPANION_EXPANSIONS: dict[Enemy, Enemy] = {
    Enemy.RED_GORIYA:    Enemy.BLUE_GORIYA,
    Enemy.RED_DARKNUT:   Enemy.BLUE_DARKNUT,
    Enemy.RED_WIZZROBE:  Enemy.BLUE_WIZZROBE,
    Enemy.RED_LANMOLA:   Enemy.BLUE_LANMOLA,
    Enemy.BLUE_LYNEL:    Enemy.RED_LYNEL,
    Enemy.BLUE_MOBLIN:   Enemy.RED_MOBLIN,
    Enemy.BLUE_TEKTITE:  Enemy.RED_TEKTITE,
    Enemy.BLUE_LEEVER:   Enemy.RED_LEEVER,
}

# Enemies that can NOT be placed in the overworld group (group 3).
_FORBIDDEN_FROM_OVERWORLD: frozenset[Enemy] = frozenset({
    Enemy.RED_LANMOLA,
    Enemy.WALLMASTER,
    Enemy.VIRE,
    Enemy.ZOL,
    Enemy.LIKE_LIKE,
})

# All enemies (primaries + companions) whose sprites live in the shuffleable
# enemy sprite banks.  Members of mixed groups that match this set must be
# replaced after the sprite group shuffle to stay compatible with the bank
# the NES loads for their level.
_SHUFFLEABLE_ENEMIES: frozenset[Enemy] = frozenset(
    set(_ENEMY_TILE_COLUMNS.keys()) | set(_COMPANION_EXPANSIONS.values())
)

# Vanilla sprite set ownership for each dungeon mixed group.
# Derived from which levels use each group in the unmodified ROM.
# Groups that span multiple sprite sets in vanilla are assigned to one:
#   Group 14 → B (removed from Level 9 / set C rooms before use).
_MIXED_GROUP_SPRITE_SET: dict[int, EnemySpriteSet] = {
    0x6D: EnemySpriteSet.B,   # Group 12 — L3(B)
    0x6E: EnemySpriteSet.A,   # Group 13 — L2,7(A); removed from L3(B)
    0x6F: EnemySpriteSet.B,   # Group 14 — L3,8(B); removed from L9(C)
    0x70: EnemySpriteSet.B,   # Group 15 — L5,8(B)
    0x71: EnemySpriteSet.C,   # Group 16 — L9(C)
    0x72: EnemySpriteSet.C,   # Group 17 — L4,6(C)
    0x73: EnemySpriteSet.C,   # Group 18 — L4,6,9(C)
    0x74: EnemySpriteSet.B,   # Group 19 — L8(B)
    0x75: EnemySpriteSet.A,   # Group 20 — L7(A)
    0x76: EnemySpriteSet.C,   # Group 21 — L9(C)
    0x77: EnemySpriteSet.C,   # Group 22 — L6,9(C)
    0x78: EnemySpriteSet.B,   # Group 23 — L8(B)
    0x79: EnemySpriteSet.A,   # Group 24 — L7(A)
    0x7A: EnemySpriteSet.A,   # Group 25 — L7(A)
    0x7B: EnemySpriteSet.C,   # Group 26 — L6,9(C)
    0x7C: EnemySpriteSet.C,   # Group 27 — L6,9(C)
}


# Enemies that must not share a group (Lanmola and Wallmaster are
# mutually exclusive).
_MUTUALLY_EXCLUSIVE: frozenset[tuple[Enemy, Enemy]] = frozenset({
    (Enemy.RED_LANMOLA, Enemy.WALLMASTER),
    (Enemy.WALLMASTER, Enemy.RED_LANMOLA),
})

# Wizzrobe-compatible enemies: every dungeon group must contain at least one.
# This prevents a group from having no enemies that can coexist with Wizzrobes.
_WIZZROBE_COMPAT_BASE: list[Enemy] = [
    Enemy.RED_GORIYA,
    Enemy.RED_DARKNUT,
    Enemy.GIBDO,
    Enemy.RED_WIZZROBE,
    # These are only relevant for the overworld group:
    Enemy.BLUE_LYNEL,
    Enemy.BLUE_MOBLIN,
    Enemy.RED_OCTOROK_1,
]


# ---------------------------------------------------------------------------
# Sprite tile layout: vanilla locations for reading tile data.
#
# Each safe enemy occupies a contiguous run of 16-byte columns within its
# vanilla enemy sprite set bytearray.  The offsets are derived from the C#
# statOffsets[i] + 16400 formula, which gives each enemy's absolute ROM
# file address.  We then subtract the ROM file address of the bytearray
# that physically contains that data to get the byte offset within it.
#
# C# spriteBanks mapping to ROM file addresses:
#   spriteBanks[0] = 56779 = 0xDDCB = ENEMY_SET_A_SPRITES_ADDRESS
#   spriteBanks[1] = 55435 = 0xD88B = ENEMY_SET_B_SPRITES_ADDRESS
#   spriteBanks[2] = 55979 = 0xDAAB = ENEMY_SET_C_SPRITES_ADDRESS
#   spriteBanks[3] = 53867 = 0xD24B + 0x20 (within OW_SPRITES region)
#
# The physical location of each enemy's sprite data in ROM:
#   Set A enemies: ROPE, STALFOS, WALLMASTER, RED_GORIYA → enemy_set_a
#   Set A enemy:   ZOL → enemy_set_b (physically in the B bank region)
#   Set B enemies: POLS_VOICE, GIBDO, RED_DARKNUT → enemy_set_b
#   Set C enemies: RED_LANMOLA, LIKE_LIKE, VIRE, RED_WIZZROBE → enemy_set_c
# ---------------------------------------------------------------------------

_VANILLA_SPRITE_SET: dict[Enemy, EnemySpriteSet] = {
    Enemy.ZOL:            EnemySpriteSet.B,   # physically in enemy_set_b despite being a group A enemy
    Enemy.RED_GORIYA:     EnemySpriteSet.A,
    Enemy.ROPE:           EnemySpriteSet.A,
    Enemy.STALFOS:        EnemySpriteSet.A,
    Enemy.WALLMASTER:     EnemySpriteSet.A,
    Enemy.RED_DARKNUT:    EnemySpriteSet.B,
    Enemy.POLS_VOICE:     EnemySpriteSet.B,
    Enemy.GIBDO:          EnemySpriteSet.B,
    Enemy.VIRE:           EnemySpriteSet.C,
    Enemy.LIKE_LIKE:      EnemySpriteSet.C,
    Enemy.RED_WIZZROBE:   EnemySpriteSet.C,
    Enemy.RED_LANMOLA:    EnemySpriteSet.C,
}

# Maps EnemySpriteSet → SpriteData attribute name.
_GROUP_SPRITE_ATTR: dict[EnemySpriteSet, str] = {
    EnemySpriteSet.A:  "enemy_set_a",
    EnemySpriteSet.B:  "enemy_set_b",
    EnemySpriteSet.C:  "enemy_set_c",
    EnemySpriteSet.OW: "ow_sprites",
}

# The group ordering: indices 0-2 map to A/B/C, index 3 to OW.
_GROUP_ORDER: list[EnemySpriteSet] = [
    EnemySpriteSet.A, EnemySpriteSet.B, EnemySpriteSet.C, EnemySpriteSet.OW,
]

# Maximum sprite tile columns per group.
_GROUP_CAPACITY = 34

# NES engine column base for enemy sprite sets.
_COL_START = 158

# The ow_sprites bytearray starts at OW_SPRITES_ADDRESS (0xD24B), but the C#
# sprite bank base for the OW group is spriteBanks[3] = 0xD26B (0xD24B + 0x20).
# Byte offsets into ow_sprites must be shifted by +0x20 to skip the "additional
# sprites" prefix that precedes the enemy sprite region.
_OW_BANK_PREFIX = 0x20

# ROM file addresses of each sprite set bytearray (used as bank bases for
# offset calculation).  These must match the addresses used to parse each
# bytearray in parser.py / rom_layout.py.
_SPRITE_BANK_BASES: dict[EnemySpriteSet, int] = {
    EnemySpriteSet.A: 0xDDCB,  # 56779 — ENEMY_SET_A_SPRITES_ADDRESS
    EnemySpriteSet.B: 0xD88B,  # 55435 — ENEMY_SET_B_SPRITES_ADDRESS
    EnemySpriteSet.C: 0xDAAB,  # 55979 — ENEMY_SET_C_SPRITES_ADDRESS
}

# Per-enemy stat offsets → sprite data ROM address = statOffsets[i] + 16400.
# We derive the byte offset within each vanilla set from these.
# For each enemy, offset_in_set = (statOffsets[i] + 16400) - _SPRITE_BANK_BASES[set].
_STAT_OFFSETS: dict[Enemy, int] = {
    Enemy.ZOL:           39195,
    Enemy.RED_GORIYA:    40667,
    Enemy.RED_DARKNUT:   39259,
    Enemy.VIRE:          39803,
    Enemy.POLS_VOICE:    39067,
    Enemy.LIKE_LIKE:     39643,
    Enemy.RED_WIZZROBE:  39931,
    Enemy.WALLMASTER:    40603,
    Enemy.ROPE:          40411,
    Enemy.STALFOS:       40539,
    Enemy.GIBDO:         39131,
    Enemy.RED_LANMOLA:   39579,
}


def _compute_sprite_offset(enemy: Enemy) -> int:
    """Compute the byte offset of an enemy's tile data within its vanilla set."""
    sprite_set = _VANILLA_SPRITE_SET[enemy]
    stat_offset = _STAT_OFFSETS[enemy]
    rom_addr = stat_offset + 16400
    bank_base = _SPRITE_BANK_BASES[sprite_set]
    return rom_addr - bank_base


def _compute_sprite_size(enemy: Enemy) -> int:
    """Compute the byte count of an enemy's tile data (columns × 16)."""
    return _ENEMY_TILE_COLUMNS[enemy] * 16


# Pre-computed byte offset and size of each enemy's tile data within its
# vanilla sprite set.
_SPRITE_OFFSET: dict[Enemy, int] = {e: _compute_sprite_offset(e) for e in _VANILLA_SPRITE_SET}
_SPRITE_SIZE: dict[Enemy, int] = {e: _compute_sprite_size(e) for e in _VANILLA_SPRITE_SET}

# Pre-computed vanilla engine column range for each enemy.
# Column = _COL_START + (byte_offset_in_bank / 16).
_VANILLA_COLUMNS: dict[Enemy, list[int]] = {
    e: list(range(
        _COL_START + _SPRITE_OFFSET[e] // 16,
        _COL_START + _SPRITE_OFFSET[e] // 16 + _ENEMY_TILE_COLUMNS[e],
    ))
    for e in _VANILLA_SPRITE_SET
}

# Number of tile frame entries per enemy (enemyMinDims in C#).
# This is the count of entries in tile_frames for each safe enemy.
_TILE_FRAME_COUNT: dict[Enemy, int] = {
    Enemy.ZOL:            2,
    Enemy.RED_GORIYA:     4,
    Enemy.RED_DARKNUT:    6,
    Enemy.VIRE:           4,
    Enemy.POLS_VOICE:     2,
    Enemy.LIKE_LIKE:      4,
    Enemy.RED_WIZZROBE:   4,
    Enemy.WALLMASTER:     2,
    Enemy.ROPE:           2,
    Enemy.STALFOS:        1,
    Enemy.GIBDO:          1,
    Enemy.RED_LANMOLA:    0,
}

# Wallmaster has an additional 32-byte sprite block that must be written
# to the shared bank region at the start of each group's sprite set.
# This data lives at spriteBanks[0] = 56779 in the ROM, which corresponds
# to the first 32 bytes of each enemy sprite set.
_WALLMASTER_SHARED_BLOCK_SIZE = 32  # 2 columns × 16 bytes

# Wallmaster's extra reserved column slots in the NES tile address space.
# These are engine-specific slot indices that Wallmaster uses for its
# additional sprite frames.
_WALLMASTER_EXTRA_SLOTS: list[int] = [636, 632, 688, 692, 696, 700]

# Lanmola's sprite data occupies the very start of the bank (offset 0),
# overlapping with the shared block region.  It reserves columns 158-161.
_LANMOLA_RESERVED_SLOTS: list[int] = [161, 160, 159, 158]


# ---------------------------------------------------------------------------
# Tile frame duplication: primary → companion.
#
# After sprite repacking, companion enemies need their tile_frames updated
# to match their primary's new values.  The C# does this via ROM byte copies
# at fixed addresses (lines 582-598).  In our model, we copy tile_frames
# entries.
# ---------------------------------------------------------------------------

# Maps (source_enemy, dest_enemy) for tile frame duplication.
# Derived from the ROM byte copy block in the C# (lines 582-598).
# Each pair means: dest's tile_frames should be copied from source's.
_TILE_FRAME_COPIES: list[tuple[Enemy, Enemy]] = [
    # RED_DARKNUT → BLUE_DARKNUT (12 → 11 in some orderings, but
    # the C# copies specific ROM offsets; these map to the following pairs)
    (Enemy.RED_GORIYA, Enemy.BLUE_GORIYA),    # 28403-28406 → 28399-28402
    (Enemy.RED_DARKNUT, Enemy.BLUE_DARKNUT),  # 28413-28418 ← 28407-28412
    (Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE),  # 28447-28450 ← 28443-28446
    (Enemy.BLUE_LYNEL, Enemy.RED_LYNEL),      # 28322-28325 ← 28318-28321
    (Enemy.BLUE_MOBLIN, Enemy.RED_MOBLIN),     # 28330-28333 ← 28326-28329
    (Enemy.BLUE_TEKTITE, Enemy.RED_TEKTITE),  # 28348-28349 ← 28346-28347
    (Enemy.BLUE_LEEVER, Enemy.RED_LEEVER),    # 28360-28369 ← 28350-28359
]

# ---------------------------------------------------------------------------
# Overworld safety checks
# ---------------------------------------------------------------------------

# Overworld screens where Wizzrobes should not be placed.
_BAD_FOR_WIZZROBE_SCREENS: frozenset[int] = frozenset({
    5, 6, 7, 8, 114, 2, 29, 30, 23, 26, 56, 68, 85, 63,
})


def _needs_bracelet(screen_num: int) -> bool:
    """Check if an overworld screen requires the Power Bracelet to access."""
    entrance = SCREEN_ENTRANCE_TYPES.get(screen_num)
    return entrance in (EntranceType.POWER_BRACELET, EntranceType.POWER_BRACELET_AND_BOMB)


def _screen_has_enemy(screen_enemy: Enemy, target: Enemy,
                      is_group: bool, group_members: list[Enemy] | None) -> bool:
    """Check if a screen's enemy (or mixed group) contains the target enemy."""
    if not is_group:
        return screen_enemy == target
    if group_members is not None:
        return target in group_members
    return False


# ---------------------------------------------------------------------------
# Sprite packing
# ---------------------------------------------------------------------------

def _read_enemy_tiles(sprites: SpriteData, enemy: Enemy) -> bytes:
    """Extract an enemy's sprite tile data from its vanilla sprite set."""
    sprite_set = _VANILLA_SPRITE_SET[enemy]
    source = getattr(sprites, _GROUP_SPRITE_ATTR[sprite_set])
    offset = _SPRITE_OFFSET[enemy]
    size = _SPRITE_SIZE[enemy]
    return bytes(source[offset:offset + size])


def _read_wallmaster_shared_block(sprites: SpriteData) -> bytes:
    """Read the 32-byte shared sprite block used by Wallmaster.

    This block lives at the start of each sprite set bank and contains
    common sprite data that Wallmaster references.  In the C#, this is
    obj10[255] read from spriteBanks[0] = 56779 = 0xDDCB.

    This is exactly ENEMY_SET_A_SPRITES_ADDRESS (0xDDCB), so the first
    32 bytes of enemy_set_a are the correct source.
    """
    return bytes(sprites.enemy_set_a[0:_WALLMASTER_SHARED_BLOCK_SIZE])


def _repack_enemy_sprites(
    sprites: SpriteData,
    group_enemies: dict[EnemySpriteSet, list[Enemy]],
    wallmaster_shared_block: bytes,
    start_enemy: Enemy,
) -> dict[Enemy, list[int]]:
    """Rewrite enemy sprite sets to match the new group assignments.

    For each group (A/B/C, and optionally OW), enemy tile data is packed
    sequentially into the corresponding enemy_set_* bytearray.

    Wallmaster gets special treatment: its 32-byte shared block is written
    at the start of any group it belongs to, and its own sprite data is
    written at byte offset 224 within the bank.

    Lanmola also gets special treatment: its sprite data is written at
    byte offset 0, overlapping with the shared block region.

    The start enemy is skipped here — it is packed separately by
    ``_repack_start_enemy`` at the top of each bank it belongs to.
    Its slots are pre-reserved so other enemies don't overwrite them.

    Returns a dict mapping each enemy to its list of assigned engine column
    numbers (one per tile column).  Columns may not be contiguous if slots
    in between were reserved by Wallmaster, Lanmola, or the start enemy.
    """
    # Read all enemy tile data from vanilla sets before overwriting.
    tile_cache: dict[Enemy, bytes] = {}
    for enemy in _VANILLA_SPRITE_SET:
        tile_cache[enemy] = _read_enemy_tiles(sprites, enemy)

    # Maps each enemy to the ordered list of engine column numbers where
    # its tile columns were placed.  Used by _update_tile_frames to remap
    # tile frame entries to the actual (possibly non-contiguous) positions.
    column_assignments: dict[Enemy, list[int]] = {}

    for sprite_set in [EnemySpriteSet.A, EnemySpriteSet.B, EnemySpriteSet.C, EnemySpriteSet.OW]:
        if sprite_set not in group_enemies:
            continue

        enemies_in_group = group_enemies[sprite_set]
        target = getattr(sprites, _GROUP_SPRITE_ATTR[sprite_set])

        # Track which column slots are used (relative to _COL_START).
        # The bank has 34 columns: slots _COL_START to _COL_START+33.
        slot_used = [False] * 768  # Oversized to match C#'s obj47

        # --- Overworld group slot reservation ---
        # The C# marks ALL 256 slots as reserved for the OW group, then
        # opens specific regions where OW enemy sprites can be packed.
        if sprite_set == EnemySpriteSet.OW:
            ow_region_bases = [206, 202, 240]
            ow_region_sizes = [16, 4, 16]
            for s in range(256):
                slot_used[s] = True
            for base, size in zip(ow_region_bases, ow_region_sizes):
                for s in range(base, base + size):
                    slot_used[s] = False

        # --- Wallmaster special handling ---
        if Enemy.WALLMASTER in enemies_in_group:
            # Write shared block at bank offset 0 (2 columns)
            for k in range(len(wallmaster_shared_block)):
                target[k] = wallmaster_shared_block[k]

            # Write Wallmaster sprite data at bank offset 224 (4 columns)
            wm_data = tile_cache[Enemy.WALLMASTER]
            wm_offset = 224
            for k in range(len(wm_data)):
                target[wm_offset + k] = wm_data[k]

            # Record Wallmaster's column assignment (single fixed position).
            # Column = _COL_START + (byte_offset / 16) = 158 + 14 = 172
            wm_start_col = _COL_START + wm_offset // 16
            wm_cols = len(wm_data) // 16
            column_assignments[Enemy.WALLMASTER] = list(
                range(wm_start_col, wm_start_col + wm_cols)
            )

            # Reserve the shared block slots and Wallmaster's own slots.
            shared_cols = len(wallmaster_shared_block) // 16
            for s in range(shared_cols):
                slot_used[_COL_START + s] = True
            for s in range(wm_start_col, wm_start_col + wm_cols):
                slot_used[s] = True

            # Reserve Wallmaster's extra engine slots.
            for s in _WALLMASTER_EXTRA_SLOTS:
                slot_used[s] = True

        # --- Lanmola special handling ---
        if Enemy.RED_LANMOLA in enemies_in_group:
            # Lanmola sprite data at bank offset 0 (4 columns)
            lm_data = tile_cache[Enemy.RED_LANMOLA]
            for k in range(len(lm_data)):
                target[k] = lm_data[k]

            # Reserve slots 158-161
            for s in _LANMOLA_RESERVED_SLOTS:
                slot_used[s] = True

        # --- Start enemy slot reservation ---
        # The start enemy is packed at the top of the bank by
        # _repack_start_enemy (column = 192 - cols).  Reserve those slots
        # so the main loop doesn't pack anything there.
        if start_enemy in enemies_in_group and start_enemy in tile_cache:
            se_cols = len(tile_cache[start_enemy]) // 16
            se_pos = 192 - se_cols
            for s in range(se_pos, se_pos + se_cols):
                slot_used[s] = True

        # --- Main packing loop for remaining enemies ---
        for enemy in enemies_in_group:
            if enemy == Enemy.WALLMASTER:
                continue  # Already handled
            if enemy == Enemy.RED_LANMOLA:
                continue  # Already handled
            if enemy == start_enemy:
                continue  # Handled by _repack_start_enemy
            if enemy not in tile_cache:
                continue  # Companion variants don't have their own tiles

            data = tile_cache[enemy]
            cols_needed = len(data) // 16
            slot_base = _COL_START
            assigned_cols: list[int] = []

            for col_idx in range(cols_needed):
                # Find next free slot
                while slot_base < 256 and slot_used[slot_base]:
                    slot_base += 1

                if slot_base >= 256:
                    break

                slot_used[slot_base] = True
                assigned_cols.append(slot_base)

                # Write 16 bytes of sprite data
                rom_offset = (slot_base - _COL_START) * 16
                if sprite_set == EnemySpriteSet.OW:
                    rom_offset += _OW_BANK_PREFIX
                src_offset = col_idx * 16
                for t in range(16):
                    if src_offset + t < len(data):
                        target[rom_offset + t] = data[src_offset + t]

                slot_base += 1

            if assigned_cols:
                column_assignments[enemy] = assigned_cols

    return column_assignments


def _repack_start_enemy(
    sprites: SpriteData,
    start_enemy: Enemy,
    group_enemies: dict[EnemySpriteSet, list[Enemy]],
    tile_cache: dict[Enemy, bytes],
) -> list[int]:
    """Pack the start enemy's sprite data into every group that contains it.

    The start enemy is shared between groups 1 and 2 (B and C), and its
    tile data must be present in each.  It's placed at the top of the bank
    (column = 192 - columns_needed) so it doesn't conflict with other enemies.

    Returns the list of engine column numbers where the start enemy was placed
    (always contiguous since it occupies a fixed region at the top of the bank).
    """
    data = tile_cache[start_enemy]
    cols = len(data) // 16
    pos_base = 192 - cols  # Place at top of bank

    for sprite_set, enemies in group_enemies.items():
        if start_enemy not in enemies:
            continue
        if sprite_set not in _GROUP_SPRITE_ATTR:
            continue

        target = getattr(sprites, _GROUP_SPRITE_ATTR[sprite_set])
        rom_offset = (pos_base - _COL_START) * 16
        for k in range(len(data)):
            target[rom_offset + k] = data[k]

    return list(range(pos_base, pos_base + cols))


def _update_tile_frames(
    enemies: EnemyData,
    column_assignments: dict[Enemy, list[int]],
) -> None:
    """Update tile_frames for each enemy to reflect its new sprite set position.

    After repacking, each enemy's tile frame entries must be remapped from
    their old column positions to the new ones.  We build an explicit
    old_column → new_column mapping from the enemy's vanilla column range
    and its new assigned columns, then substitute each frame value through
    that mapping.  Frame values that reference columns outside the enemy's
    own sprite data (e.g. Wallmaster's shared block, Lanmola's OW-region
    tiles) are left unchanged — they reference fixed engine tile positions
    that aren't repacked.
    """
    for enemy, assigned_cols in column_assignments.items():
        if enemy not in enemies.tile_frames:
            continue

        frames = enemies.tile_frames[enemy]
        if not frames:
            continue

        vanilla_cols = _VANILLA_COLUMNS.get(enemy)
        if vanilla_cols is None:
            continue

        # Build old → new mapping from parallel vanilla/assigned column lists.
        col_map: dict[int, int] = {}
        for old_col, new_col in zip(vanilla_cols, assigned_cols):
            col_map[old_col] = new_col

        # Remap each frame value; leave unchanged if not in the enemy's
        # vanilla column range (references fixed engine tile positions).
        enemies.tile_frames[enemy] = [
            col_map.get(f, f) for f in frames
        ]


def _duplicate_companion_tile_frames(enemies: EnemyData) -> None:
    """Copy tile_frames from primary enemies to their companion variants.

    The C# does this via ROM byte copies (lines 582-598).  In our model,
    we copy the tile_frames list from the source enemy to the dest enemy.
    """
    for source, dest in _TILE_FRAME_COPIES:
        if enemies.tile_frames.get(source):
            enemies.tile_frames[dest] = list(enemies.tile_frames[source])


# ---------------------------------------------------------------------------
# Sorting and assignment
# ---------------------------------------------------------------------------

def _sort_enemies_by_tile_columns(enemies: list[Enemy], rng: Rng) -> list[Enemy]:
    """Sort enemies by tile column count ascending, with RNG tie-breaking.

    Implements the bubble sort from the C# (lines 96004-96034).  The original
    sorts ascending by enemyRoomCounts with random tie-breaking, then processes
    enemies from smallest to largest.

    The C# also does a pre-sort +2 adjustment to Wallmaster's column count
    (lines 95996-96002).  We apply that here.
    """
    # Copy the column counts and apply Wallmaster's +2 adjustment.
    adjusted_columns: dict[Enemy, int] = dict(_ENEMY_TILE_COLUMNS)
    adjusted_columns[Enemy.WALLMASTER] = _ENEMY_TILE_COLUMNS[Enemy.WALLMASTER] + 2

    result = list(enemies)

    # Bubble sort with RNG tie-breaking (matching C# exactly).
    for i in range(len(result)):
        for j in range(i + 1, len(result)):
            do_swap: bool
            if adjusted_columns[result[i]] > adjusted_columns[result[j]]:
                do_swap = True
            elif adjusted_columns[result[i]] == adjusted_columns[result[j]]:
                do_swap = (int(rng.random() * 2) == 0)
            else:
                do_swap = False

            if do_swap:
                result[i], result[j] = result[j], result[i]

    return result


def _pick_start_enemy(
    sorted_enemies: list[Enemy],
    rng: Rng,
) -> Enemy:
    """Pick a random enemy with tile column count == 4 and not Lanmola.

    The C# (lines 96036-96041) scans for an index where roomCount==4 and
    enemyID!=58.  This enemy is shared across groups 1 (B) and 2 (C).

    NOTE: If we wanted to remove the "start enemy shared between two groups"
    constraint in the future, we could skip this step entirely and just
    assign all enemies through the normal assignment loop.  The start enemy
    mechanism exists to guarantee that groups B and C always share at least
    one common small enemy (for rooms where the original had ZOL, which is
    always replaced by the start enemy).
    """
    candidates = [
        e for e in sorted_enemies
        if _ENEMY_TILE_COLUMNS[e] == 4
        and e != Enemy.RED_LANMOLA
        and e != Enemy.WALLMASTER  # adjusted cost is 6 (shared block), not 4
    ]

    # The C# uses a while loop with RNG: pick random index, check if it
    # matches.  We just pick from the filtered candidates.
    return rng.choice(candidates)


def _effective_column_cost(enemy: Enemy) -> int:
    """Return the true column cost for capacity tracking.

    Wallmaster requires 2 extra columns for its shared sprite block
    (written at the start of each bank), beyond the 4 columns of its
    own tile data.
    """
    cost = _ENEMY_TILE_COLUMNS[enemy]
    if enemy == Enemy.WALLMASTER:
        cost += _WALLMASTER_SHARED_BLOCK_SIZE // 16  # +2
    return cost


def _assign_enemies_to_groups(
    sorted_enemies: list[Enemy],
    start_enemy: Enemy,
    rng: Rng,
    overworld: bool,
    force_wizzrobes_to_9: bool,
    vire_is_wizzrobe_compat: bool,
) -> dict[EnemySpriteSet, list[Enemy]] | None:
    """Assign each safe enemy to a sprite-set group.

    Returns a dict mapping each group to its list of primary enemies,
    or None if placement failed after max retries.

    Constraints:
    - Lanmola and Wallmaster are mutually exclusive (can't share a group).
    - Certain enemies can't go in the overworld group.
    - Each group's accumulated tile columns can't exceed 34.
    - Every group must contain at least one wizzrobe-compatible enemy.
    - The start enemy is pre-seeded into groups B and C.
    - If force_wizzrobes_to_9, RED_WIZZROBE is pre-seeded into group C.
    """
    num_groups = 4 if overworld else 3

    # Build the wizzrobe compat set.
    wizzrobe_compat = set(_WIZZROBE_COMPAT_BASE)
    if vire_is_wizzrobe_compat:
        wizzrobe_compat.add(Enemy.VIRE)

    group_lists: dict[EnemySpriteSet, list[Enemy]] = {
        _GROUP_ORDER[g]: [] for g in range(num_groups)
    }

    # Capacity tracking: tile columns used per group.
    capacities: dict[EnemySpriteSet, int] = {
        _GROUP_ORDER[g]: 0 for g in range(num_groups)
    }

    # Overworld group capacity pre-fill.
    # C#: capacity[3] = 34 - sum(overworldGroupDest) = 34 - (4+16+16) = -2
    # This effectively gives the overworld group a budget of 36 columns total.
    if overworld:
        capacities[EnemySpriteSet.OW] = -2

    # Pre-seed start enemy into groups B and C.
    start_cost = _effective_column_cost(start_enemy)
    group_lists[EnemySpriteSet.B].append(start_enemy)
    group_lists[EnemySpriteSet.C].append(start_enemy)
    capacities[EnemySpriteSet.B] += start_cost
    capacities[EnemySpriteSet.C] += start_cost

    # Pre-seed RED_WIZZROBE into group C if forced.
    if force_wizzrobes_to_9:
        group_lists[EnemySpriteSet.C].append(Enemy.RED_WIZZROBE)
        capacities[EnemySpriteSet.C] += _effective_column_cost(Enemy.RED_WIZZROBE)

    # Assign remaining enemies.
    for enemy in sorted_enemies:
        if enemy == start_enemy:
            continue
        if enemy == Enemy.RED_WIZZROBE and force_wizzrobes_to_9:
            continue

        columns = _effective_column_cost(enemy)

        for _retry in range(_MAX_ASSIGNMENT_RETRIES):
            group_idx = int(rng.random() * num_groups)
            group = _GROUP_ORDER[group_idx]

            # Mutual exclusion check.
            for a, b in _MUTUALLY_EXCLUSIVE:
                if enemy == a and b in group_lists[group]:
                    break
                if enemy == b and a in group_lists[group]:
                    break
            else:
                # Overworld forbidden check.
                if group == EnemySpriteSet.OW and enemy in _FORBIDDEN_FROM_OVERWORLD:
                    continue

                # Capacity check.
                if capacities[group] + columns > _GROUP_CAPACITY:
                    continue

                # Passed all checks.
                group_lists[group].append(enemy)
                capacities[group] += columns
                break
            continue  # Mutual exclusion failed, retry.
        else:
            # Exhausted retries for this enemy — assignment failed.
            return None

    # Wizzrobe-compat coverage check: every group needs at least one.
    for g in range(num_groups):
        group = _GROUP_ORDER[g]
        if not any(e in wizzrobe_compat for e in group_lists[group]):
            return None

    return group_lists


# ---------------------------------------------------------------------------
# Overworld replacement
# ---------------------------------------------------------------------------

def _replace_overworld_enemies(
    world: GameWorld,
    rng: Rng,
    group_enemies: dict[EnemySpriteSet, list[Enemy]],
) -> None:
    """Replace overworld screen enemies based on the new OW sprite group.

    Safety constraints:
    - Blue Moblins can't go on bracelet-required screens.
    - Wizzrobes can't go on certain banned screens.
    """
    ow_pool = group_enemies.get(EnemySpriteSet.OW, [])
    if not ow_pool:
        return

    for screen in world.overworld.screens:
        enemy = screen.enemy_spec.enemy
        is_group = screen.enemy_spec.is_group
        members = screen.enemy_spec.group_members

        # The C# checks the high flag bit (0x80) of the flag byte.
        # In our model, mixed enemy groups (is_group=True) correspond to
        # the flagged entries.
        if is_group:
            needs_replacement = False

            # Check Blue Moblin + bracelet safety.
            has_blue_moblin = _screen_has_enemy(enemy, Enemy.BLUE_MOBLIN, is_group, members)
            if has_blue_moblin and _needs_bracelet(screen.screen_num):
                needs_replacement = True

            # Check Wizzrobe + bad screen safety.
            has_wizzrobe = (
                _screen_has_enemy(enemy, Enemy.RED_WIZZROBE, is_group, members)
                or _screen_has_enemy(enemy, Enemy.BLUE_WIZZROBE, is_group, members)
            )
            if has_wizzrobe and screen.screen_num in _BAD_FOR_WIZZROBE_SCREENS:
                needs_replacement = True

            if not needs_replacement:
                continue

            # Decompose the group into a single enemy for replacement.
            # The C# clears the flag and writes enemy ID 3 (BLUE_MOBLIN).
            screen.enemy_spec = type(screen.enemy_spec)(
                enemy=Enemy.BLUE_MOBLIN,
                is_group=False,
                group_members=None,
            )

        # The original decompiled code searches CaveGroups (not
        # enemyGroups) starting at group 3.  Only enemies that were
        # assigned to a CaveGroup during the assignment phase get
        # replaced — fairies, ghinis, nothing, falling rocks, etc.
        # are left untouched.
        ow_enemy_id = screen.enemy_spec.enemy
        if ow_enemy_id not in ow_pool:
            continue

        # Pick a random replacement from the overworld pool.
        for _attempt in range(_MAX_ROOM_RETRIES):
            new_enemy = rng.choice(ow_pool)

            # Blue Moblin can't go on bracelet-required screens.
            if new_enemy == Enemy.BLUE_MOBLIN and _needs_bracelet(screen.screen_num):
                continue

            # Wizzrobes can't go on banned screens.
            if new_enemy in (Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE):
                if screen.screen_num in _BAD_FOR_WIZZROBE_SCREENS:
                    continue

            screen.enemy_spec.enemy = new_enemy
            break


# ---------------------------------------------------------------------------
# Mixed enemy group fixup
# ---------------------------------------------------------------------------

def _update_mixed_group_members(
    world: GameWorld,
    group_enemies: dict[EnemySpriteSet, list[Enemy]],
    rng: Rng,
) -> None:
    """Replace shuffleable members in mixed enemy groups after sprite group reassignment.

    Each dungeon mixed group is owned by one sprite set (A/B/C).  After the
    shuffle, the enemies in that sprite set's pool may have changed.  For every
    member that is a shuffleable enemy, replace it with a random enemy from the
    owning sprite set's new pool.

    Also handles cross-set removals: rooms that use a mixed group in a level
    whose sprite set doesn't match the group's owner are decomposed into
    single-enemy rooms drawn from the level's pool.

    Updates both the canonical ``world.enemies.mixed_groups`` table (which is
    serialized back to ROM) and every room ``EnemySpec.group_members`` that
    references the modified group.
    """
    # --- Step 1: Decompose cross-set rooms ---
    for level in world.levels:
        level_pool = group_enemies.get(level.enemy_sprite_set)
        if not level_pool:
            continue

        for room in level.rooms:
            if not room.enemy_spec.is_group:
                continue
            code = room.enemy_spec.enemy.value
            group_owner = _MIXED_GROUP_SPRITE_SET.get(code)
            if group_owner is None or group_owner == level.enemy_sprite_set:
                continue

            for _attempt in range(_MAX_ROOM_RETRIES):
                new_enemy = rng.choice(level_pool)
                if not is_safe_for_room(new_enemy, room.room_type,
                                        has_push_block=room.movable_block):
                    continue
                room.enemy_spec = EnemySpec(enemy=new_enemy)
                break

    # --- Step 2: Substitute shuffleable members in the raw data blob ---
    # Operate directly on mixed_enemy_data so overlapping groups that share
    # bytes in the ROM get a single consistent substitution per byte.
    data = world.enemies.mixed_enemy_data
    offsets = world.enemies.mixed_group_offsets
    for code, offset in offsets.items():
        owner_set = _MIXED_GROUP_SPRITE_SET.get(code)
        if owner_set is None:
            continue
        pool = group_enemies.get(owner_set)
        if not pool:
            continue
        for i in range(8):
            member = Enemy(data[offset + i])
            if member in _SHUFFLEABLE_ENEMIES:
                data[offset + i] = rng.choice(pool).value

    # --- Step 3: Rebuild mixed_groups dict and propagate to room EnemySpecs ---
    for code, offset in offsets.items():
        world.enemies.mixed_groups[code] = [
            Enemy(data[offset + i]) for i in range(8)
        ]

    for level in world.levels:
        for room in level.rooms:
            if not room.enemy_spec.is_group:
                continue
            code = room.enemy_spec.enemy.value
            updated = world.enemies.mixed_groups.get(code)
            if updated is not None:
                room.enemy_spec.group_members = list(updated)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def change_dungeon_enemy_groups(
    world: GameWorld,
    rng: Rng,
    overworld: bool = False,
    force_wizzrobes_to_9: bool = False,
) -> None:
    """Redistribute enemies across the three (or four) enemy sprite-set groups.

    1. Sort enemies by sprite tile column count (ascending) with RNG tie-breaking.
    2. Pick a "start enemy" (small, not Lanmola) shared between groups B and C.
    3. Assign each enemy to a random group (A/B/C, optionally OW), respecting
       column budgets, mutual exclusion, and wizzrobe-compat constraints.
    4. Repack sprite tile data into the target sets.
    5. Update tile frame mappings so the engine finds sprites in the new sets.
    6. Duplicate tile frames from primaries to companion variants.
    7. Expand companion variants into each group.
    8. Replace enemies in dungeon rooms (and optionally overworld screens).
    9. Store the final group assignments in world.enemies.cave_groups.

    Only Q1 levels (1-9) are processed for dungeons.

    Args:
        world: The game world to modify.
        rng: Seeded RNG for deterministic output.
        overworld: If True, also shuffle enemies in the overworld sprite group.
        force_wizzrobes_to_9: If True, force RED_WIZZROBE into group C.
    """
    # --- Build the sorted enemy list ---
    safe_enemies = list(_ENEMY_TILE_COLUMNS.keys())
    sorted_enemies = _sort_enemies_by_tile_columns(safe_enemies, rng)

    # --- Pick start enemy ---
    start_enemy = _pick_start_enemy(sorted_enemies, rng)

    # --- Check Vire's HP for wizzrobe compatibility ---
    # If Vire's HP is low enough (≤ 4), it's considered wizzrobe-compatible (because it can drop bombs).
    vire_hp = world.enemies.hp.get(Enemy.VIRE, 4)
    vire_is_wizzrobe_compat = (vire_hp <= 4)

    # --- Assignment loop (retries until all constraints pass) ---
    group_enemies: dict[EnemySpriteSet, list[Enemy]] | None = None
    for _outer in range(_MAX_OUTER_RETRIES):
        group_enemies = _assign_enemies_to_groups(
            sorted_enemies, start_enemy, rng,
            overworld, force_wizzrobes_to_9,
            vire_is_wizzrobe_compat,
        )
        if group_enemies is not None:
            break
    else:
        raise RuntimeError(
            "change_dungeon_enemy_groups: failed to assign enemies to groups "
            f"after {_MAX_OUTER_RETRIES} attempts"
        )

    # --- Read tile data before overwriting ---
    tile_cache: dict[Enemy, bytes] = {}
    for enemy in _VANILLA_SPRITE_SET:
        tile_cache[enemy] = _read_enemy_tiles(world.sprites, enemy)
    wallmaster_shared_block = _read_wallmaster_shared_block(world.sprites)

    # --- Repack sprite tile data ---
    column_assignments = _repack_enemy_sprites(
        world.sprites, group_enemies, wallmaster_shared_block, start_enemy,
    )

    # --- Pack start enemy into all groups that contain it ---
    start_cols = _repack_start_enemy(
        world.sprites, start_enemy, group_enemies, tile_cache,
    )
    column_assignments[start_enemy] = start_cols

    # --- Update tile frame mappings ---
    _update_tile_frames(world.enemies, column_assignments)

    # --- Duplicate tile frames from primaries to companions ---
    _duplicate_companion_tile_frames(world.enemies)

    # TODO: Engine patches for overworld Wizzrobes (enemy 36 / BLUE_WIZZROBE).
    # The C# writes 6502 code patches to ROM when the overworld group contains
    # BLUE_WIZZROBE (lines 790-823):
    #   - 18 bytes at ROM 73275 (0x11E4B)
    #   - 11 bytes at ROM 77829 (0x13005)
    #   - 41 bytes at ROM 81680 (0x13F10)
    #   - 3 bytes at ROM 77102 (0x12D2E)
    # These are NES engine code patches — implement as BehaviorPatches when
    # integrating with the rest of the randomizer.

    # --- Expand companion variants into each group ---
    for group in group_enemies.values():
        additions: list[Enemy] = []
        for enemy in group:
            if enemy in _COMPANION_EXPANSIONS:
                additions.append(_COMPANION_EXPANSIONS[enemy])
        group.extend(additions)

    # --- Store the final group assignments ---
    world.enemies.cave_groups = dict(group_enemies)

    # --- Update mixed enemy group members ---
    _update_mixed_group_members(world, group_enemies, rng)

    # --- Replace enemies in dungeon rooms ---
    # Build a set of all enemies that belong to any vanilla group, for
    # filtering out non-group enemies (bubbles, traps, etc.).
    _all_vanilla_group_enemies: frozenset[Enemy] = frozenset().union(
        *_VANILLA_ENEMY_GROUPS.values()
    )

    for level in world.levels:
        # Draw replacements from the pool matching the level's sprite set.
        # After shuffle_monsters_between_levels, a level may use a different
        # sprite set than vanilla, so we must use the level's actual set —
        # not the enemy's vanilla group — to avoid sprite/bank mismatches.
        level_pool = group_enemies.get(level.enemy_sprite_set)

        for room in level.rooms:
            # Skip staircase rooms — the C# skips rooms where
            # (flag_byte & 0x3F) is 62 or 63, which are
            # TRANSPORT_STAIRCASE (0x3E) and ITEM_STAIRCASE (0x3F).
            if room.room_type in (RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE):
                continue

            enemy = room.enemy_spec.enemy

            # Skip boss rooms — bosses are handled by change_dungeon_boss_groups.
            # Exception: Lanmola's sprites live in enemy sprite banks (not
            # boss sprite banks), so Lanmola rooms must be replaced here to
            # keep them in levels whose active enemy sprite set matches.
            if enemy.is_boss and enemy not in (Enemy.RED_LANMOLA, Enemy.BLUE_LANMOLA):
                continue

            # ZOL is always replaced with the start enemy.
            if enemy == Enemy.ZOL:
                room.enemy_spec.enemy = start_enemy
                continue

            # Only replace enemies that belong to a vanilla group (A/B/C).
            # Non-group enemies (bubbles, traps, etc.) are left unchanged.
            if enemy not in _all_vanilla_group_enemies:
                continue

            if not level_pool:
                continue

            # Pick a random replacement, retrying on safety failures.
            for _attempt in range(_MAX_ROOM_RETRIES):
                new_enemy = rng.choice(level_pool)

                if not is_safe_for_room(new_enemy, room.room_type, has_push_block=room.movable_block):
                    continue

                room.enemy_spec.enemy = new_enemy
                break

    # --- Replace overworld enemies ---
    if overworld:
        _replace_overworld_enemies(world, rng, group_enemies)
