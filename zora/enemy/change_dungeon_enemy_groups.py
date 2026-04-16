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
# vanilla enemy sprite set.  The offset and size are derived from
# statOffsets[i] + 16400 minus the set's base ROM address:
#   ENEMY_SET_A = 0xD84B (55371)   ... actually spriteBanks[1] = 55435
#   ENEMY_SET_B = 0xD9EB (55787)   ... actually spriteBanks[2] = 55979
#   ENEMY_SET_C = 0xD24B (53835)   ... actually spriteBanks[3] = 53867
#
# NOTE: spriteBanks[0] = 56779 is the "shared" bank region used for
# Wallmaster's extra sprite data.  The main enemy set banks are indices 1-3.
# ---------------------------------------------------------------------------

_VANILLA_SPRITE_SET: dict[Enemy, EnemySpriteSet] = {
    Enemy.ZOL:            EnemySpriteSet.A,
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

# Sprite ROM bank addresses per group index (from spriteBanks in C#).
# Index 0 = shared bank, 1-3 = enemy_set_a/b/c.
# These are used to derive tile offsets within each set.
# spriteBanks = { 56779, 55435, 55979, 53867 }
# The shared bank (56779) is where Wallmaster's extra 32-byte prefix lives.

# Per-enemy stat offsets → sprite data ROM address = statOffsets[i] + 16400.
# We derive the byte offset within each vanilla set from these.
# For each enemy, offset_in_set = (statOffsets[i] + 16400) - spriteBanks[group].
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

# ROM bank base addresses per group (for deriving byte offsets within sets).
_SPRITE_BANK_BASES: dict[EnemySpriteSet, int] = {
    EnemySpriteSet.A: 55435,
    EnemySpriteSet.B: 55979,
    EnemySpriteSet.C: 53867,
}

# Shared bank base (for Wallmaster's extra data).
_SHARED_BANK_BASE = 56779


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
    their old column positions to the new ones.  The algorithm:
    1. Normalize frames (subtract minimum → 0-based sub-sprite indices).
    2. For each normalized index, look up the actual engine column number
       from the column assignment list.

    This handles non-contiguous column allocations correctly.  The C#
    (lines 502-563) does the same thing inline during packing: for each
    column slot ``s`` written, it scans ``statWork`` for entries equal to
    ``s`` and replaces them with ``slotBase``.
    """
    for enemy, assigned_cols in column_assignments.items():
        if enemy not in enemies.tile_frames:
            continue

        frames = enemies.tile_frames[enemy]
        if not frames:
            continue

        # Normalize: subtract minimum to get 0-based sub-sprite indices.
        min_val = min(frames)
        normalized = [f - min_val for f in frames]

        # Remap: each normalized index maps to the corresponding assigned
        # column.  Indices beyond the assigned columns are left as-is
        # (shouldn't happen with well-formed data).
        remapped = [
            assigned_cols[n] if n < len(assigned_cols) else n
            for n in normalized
        ]

        enemies.tile_frames[enemy] = remapped


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
        if _ENEMY_TILE_COLUMNS[e] == 4 and e != Enemy.RED_LANMOLA
    ]

    # The C# uses a while loop with RNG: pick random index, check if it
    # matches.  We just pick from the filtered candidates.
    return rng.choice(candidates)


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
    group_lists[EnemySpriteSet.B].append(start_enemy)
    group_lists[EnemySpriteSet.C].append(start_enemy)
    capacities[EnemySpriteSet.B] += _ENEMY_TILE_COLUMNS[start_enemy]
    capacities[EnemySpriteSet.C] += _ENEMY_TILE_COLUMNS[start_enemy]

    # Pre-seed RED_WIZZROBE into group C if forced.
    if force_wizzrobes_to_9:
        group_lists[EnemySpriteSet.C].append(Enemy.RED_WIZZROBE)
        capacities[EnemySpriteSet.C] += _ENEMY_TILE_COLUMNS[Enemy.RED_WIZZROBE]

    # Assign remaining enemies.
    for enemy in sorted_enemies:
        if enemy == start_enemy:
            continue
        if enemy == Enemy.RED_WIZZROBE and force_wizzrobes_to_9:
            continue

        columns = _ENEMY_TILE_COLUMNS[enemy]

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

        # The C# replaces every screen that reaches this point from
        # CaveGroups[3] (the OW pool).  The enemyGroups search starts at
        # index 3, but enemyGroups only has 3 entries (0-2), so the search
        # always falls through — every unflagged screen and every
        # dangerous-flagged screen gets a replacement from the OW pool.

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
    9. Store the final group assignments in world.enemies.sprite_sets.

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
    world.enemies.sprite_sets = dict(group_enemies)

    # --- Replace enemies in dungeon rooms ---
    for level in world.levels:
        for room in level.rooms:
            # Skip staircase rooms — the C# skips rooms where
            # (flag_byte & 0x3F) is 62 or 63, which are
            # TRANSPORT_STAIRCASE (0x3E) and ITEM_STAIRCASE (0x3F).
            if room.room_type in (RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE):
                continue

            enemy = room.enemy_spec.enemy

            # Skip boss rooms — bosses are handled by change_dungeon_boss_groups.
            if enemy.is_boss:
                continue

            # ZOL is always replaced with the start enemy.
            if enemy == Enemy.ZOL:
                room.enemy_spec.enemy = start_enemy
                continue

            # Determine which vanilla group this enemy belongs to.
            original_group: EnemySpriteSet | None = None
            for sprite_set, members in _VANILLA_ENEMY_GROUPS.items():
                if enemy in members:
                    original_group = sprite_set
                    break

            if original_group is None:
                continue

            pool = group_enemies.get(original_group)
            if not pool:
                continue

            # Pick a random replacement, retrying on safety failures.
            for _attempt in range(_MAX_ROOM_RETRIES):
                new_enemy = rng.choice(pool)

                if not is_safe_for_room(new_enemy, room.room_type, has_push_block=room.movable_block):
                    continue

                room.enemy_spec.enemy = new_enemy
                break

    # --- Replace overworld enemies ---
    if overworld:
        _replace_overworld_enemies(world, rng, group_enemies)
