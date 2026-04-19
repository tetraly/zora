"""Redistribute bosses across boss sprite-set groups, then update rooms.

Instead of assigning a fixed tier per dungeon (like shuffle_bosses.py),
this routine redistributes *which bosses belong to which sprite-set group*
(A/B/C), then replaces every existing boss room with a random pick from
its group's new pool.

Ported from changeDungeonBossGroups (change_dungeon_boss_groups.cs).
"""

from zora.data_model import (
    BossSpriteSet,
    Enemy,
    EnemyData,
    GameWorld,
    RoomType,
    SpriteData,
)
from zora.enemy.safety_checks import is_safe_for_room
from zora.rng import Rng

# Maximum retries when assigning a boss to a group with insufficient column budget.
_MAX_ASSIGNMENT_RETRIES = 1000

# Maximum retries when a safety check rejects a random boss pick for a room.
_MAX_ROOM_RETRIES = 1000


# ---------------------------------------------------------------------------
# Boss definitions: sprite tile sizes, companions, and group membership.
# ---------------------------------------------------------------------------

# Number of 16-byte sprite tile columns each primary boss requires.
# Each sprite set has a fixed column budget (64 columns = 1024 bytes for
# groups A/B/C, 32 columns = 512 bytes for the shared group).  A boss can
# only be assigned to a group that has enough remaining columns.
_BOSS_TILE_COLUMNS: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:        20,
    Enemy.TRIPLE_DODONGO:    36,
    Enemy.TRIPLE_DIGDOGGER:   4,
    Enemy.MANHANDLA:         14,
    Enemy.GLEEOK_1:          32,
    Enemy.BLUE_GOHMA:        16,
    Enemy.PATRA_2:            4,
}

# Some bosses require additional columns for companion sprites that must be
# loaded in the same group (DIGDOGGER_SPAWN with TRIPLE_DIGDOGGER,
# FLYING_GLEEOK_HEAD with GLEEOK_1, PATRA_SPAWN with PATRA_2).  The
# companions are not added to the replacement pool, but their sprite tiles
# are packed alongside the primary by _repack_boss_sprites.
_BOSS_TILE_COLUMNS_WITH_COMPANION: dict[Enemy, int] = {
    Enemy.GLEEOK_1:          32 + 2,  # 34
    Enemy.TRIPLE_DIGDOGGER:   4 + 4,  #  8
    Enemy.PATRA_2:            4 + 4,  #  8
}

# ---------------------------------------------------------------------------
# Sprite tile layout.
#
# Each boss occupies a contiguous run of 16-byte "columns" within its vanilla
# boss sprite set.  The number of columns matches _BOSS_TILE_COLUMNS.
# Companion bosses share their primary's sprite set and are packed adjacent.
#
# Derived from bossStatOffsets + 16400 in the C# minus each set's base address:
#   BOSS_SET_A = 0xDFEB (57323)
#   BOSS_SET_B = 0xE3EB (58347)
#   BOSS_SET_C = 0xE7EB (59371)
# ---------------------------------------------------------------------------

_VANILLA_SPRITE_SET: dict[Enemy, BossSpriteSet] = {
    Enemy.AQUAMENTUS:         BossSpriteSet.A,
    Enemy.TRIPLE_DODONGO:     BossSpriteSet.A,
    Enemy.TRIPLE_DIGDOGGER:   BossSpriteSet.A,
    Enemy.DIGDOGGER_SPAWN:    BossSpriteSet.A,
    Enemy.MANHANDLA:          BossSpriteSet.B,
    Enemy.GLEEOK_1:           BossSpriteSet.B,
    Enemy.BLUE_GOHMA:         BossSpriteSet.B,
    Enemy.FLYING_GLEEOK_HEAD: BossSpriteSet.B,
    Enemy.PATRA_2:            BossSpriteSet.C,
    Enemy.PATRA_SPAWN:        BossSpriteSet.C,
}

# Byte offset of each boss's tile data within its vanilla sprite set.
_SPRITE_OFFSET: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:           0,  # 0xDFEB - 0xDFEB
    Enemy.TRIPLE_DIGDOGGER:   320,  # 0xE12B - 0xDFEB
    Enemy.DIGDOGGER_SPAWN:    384,  # 0xE16B - 0xDFEB
    Enemy.TRIPLE_DODONGO:     448,  # 0xE1AB - 0xDFEB
    Enemy.GLEEOK_1:             0,  # 0xE3EB - 0xE3EB
    Enemy.MANHANDLA:          512,  # 0xE5EB - 0xE3EB
    Enemy.FLYING_GLEEOK_HEAD: 736,  # 0xE6DB - 0xE3EB
    Enemy.BLUE_GOHMA:         768,  # 0xE6FB - 0xE3EB
    Enemy.PATRA_2:            896,  # 0xEB6B - 0xE7EB
    Enemy.PATRA_SPAWN:        960,  # 0xEBAB - 0xE7EB
}

# Byte count of each boss's tile data (columns × 16 bytes per column).
_SPRITE_SIZE: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:         320,  # 20 × 16
    Enemy.TRIPLE_DODONGO:     576,  # 36 × 16
    Enemy.TRIPLE_DIGDOGGER:    64,  #  4 × 16
    Enemy.DIGDOGGER_SPAWN:     64,  #  4 × 16
    Enemy.MANHANDLA:          224,  # 14 × 16
    Enemy.GLEEOK_1:           512,  # 32 × 16
    Enemy.BLUE_GOHMA:         256,  # 16 × 16
    Enemy.FLYING_GLEEOK_HEAD:  32,  #  2 × 16
    Enemy.PATRA_2:             64,  #  4 × 16
    Enemy.PATRA_SPAWN:         64,  #  4 × 16
}

# Companion bosses: must be packed into the same sprite set as their primary.
# Maps primary → companion.
_COMPANIONS: dict[Enemy, Enemy] = {
    Enemy.TRIPLE_DIGDOGGER:  Enemy.DIGDOGGER_SPAWN,
    Enemy.GLEEOK_1:          Enemy.FLYING_GLEEOK_HEAD,
    Enemy.PATRA_2:           Enemy.PATRA_SPAWN,
}

# Number of 16-byte columns reserved at the start of boss_set_c that must
# not be overwritten.  The original pre-fills columns 192-247 (56 columns).
_BOSS_SET_C_RESERVED_BYTES = 56 * 16  # 896


# "Special" bosses: one is randomly forced into the shared group (group 3).
# Each restores some column budget to the shared group when selected.
_SPECIAL_BOSSES: list[Enemy] = [Enemy.AQUAMENTUS, Enemy.MANHANDLA, Enemy.TRIPLE_DIGDOGGER]
_SPECIAL_RESTORE: dict[Enemy, int] = {
    Enemy.AQUAMENTUS:       20,
    Enemy.MANHANDLA:        14,
    Enemy.TRIPLE_DIGDOGGER:  8,
}

# Variant expansion: after group assignment, these extra enemies are added
# to whichever group their base form ended up in.
_VARIANT_EXPANSIONS: dict[Enemy, list[Enemy]] = {
    Enemy.TRIPLE_DODONGO:   [Enemy.SINGLE_DODONGO],
    Enemy.TRIPLE_DIGDOGGER: [Enemy.SINGLE_DIGDOGGER],
    Enemy.BLUE_GOHMA:       [Enemy.RED_GOHMA],
    Enemy.PATRA_2:          [Enemy.PATRA_1],
    Enemy.GLEEOK_1:         [Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4],
}

# The vanilla boss groups — which bosses originally belong to each sprite set.
# Used to detect which group a room's current boss belongs to, so we know
# which new pool to draw from.
_VANILLA_BOSS_GROUPS: dict[BossSpriteSet, frozenset[Enemy]] = {
    BossSpriteSet.A: frozenset({
        Enemy.AQUAMENTUS,
        Enemy.TRIPLE_DODONGO, Enemy.SINGLE_DODONGO,
        Enemy.TRIPLE_DIGDOGGER, Enemy.SINGLE_DIGDOGGER,
    }),
    BossSpriteSet.B: frozenset({
        Enemy.MANHANDLA,
        Enemy.BLUE_GOHMA, Enemy.RED_GOHMA,
        Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4,
    }),
    BossSpriteSet.C: frozenset({
        Enemy.PATRA_1, Enemy.PATRA_2,
    }),
}


# ---------------------------------------------------------------------------
# Group index ↔ BossSpriteSet mapping.
# ---------------------------------------------------------------------------

_GROUP_ORDER: list[BossSpriteSet] = [BossSpriteSet.A, BossSpriteSet.B, BossSpriteSet.C]

# Maps group index (0-2) to the SpriteData attribute name for that set.
_GROUP_SPRITE_ATTR: dict[int, str] = {
    0: "boss_set_a",
    1: "boss_set_b",
    2: "boss_set_c",
}


# The NES engine addresses sprite tiles by "column number", not byte offset.
# Column numbers start at a fixed base per group; byte offset within the
# sprite set = (column - column_start) * 16.
_COL_START_MAIN = 192    # groups 0-2 (boss_set_a/b/c)
_COL_START_EXPANSION = 48  # group 3 (boss_set_expansion)


# ---------------------------------------------------------------------------
# Sprite packing.
# ---------------------------------------------------------------------------

def _read_boss_tiles(sprites: SpriteData, boss: Enemy) -> bytes:
    """Extract a boss's sprite tile data from its vanilla sprite set."""
    vanilla_set = _VANILLA_SPRITE_SET[boss]
    source = getattr(sprites, _GROUP_SPRITE_ATTR[_GROUP_ORDER.index(vanilla_set)])
    offset = _SPRITE_OFFSET[boss]
    size = _SPRITE_SIZE[boss]
    return bytes(source[offset:offset + size])


def _repack_boss_sprites(
    sprites: SpriteData,
    group_bosses: list[list[Enemy]],
) -> dict[Enemy, int]:
    """Rewrite boss sprite sets to match the new group assignments.

    For groups 0-2 (A/B/C), boss tile data is packed sequentially into the
    corresponding boss_set_* bytearray.  Group 2 (C) preserves the first
    896 bytes (56 reserved columns) and packs new data after that.

    For group 3 (shared), tile data is packed into boss_set_expansion.

    Companion bosses (DIGDOGGER_SPAWN, FLYING_GLEEOK_HEAD, PATRA_SPAWN)
    follow their primary into whichever group it was assigned to.

    Returns a dict mapping each packed boss (including companions) to the
    engine column number where its tile data starts in the target set.
    """
    # Read all boss tile data from the vanilla sets before overwriting.
    tile_cache: dict[Enemy, bytes] = {}
    for boss in _VANILLA_SPRITE_SET:
        tile_cache[boss] = _read_boss_tiles(sprites, boss)

    # Maps each boss to its starting engine column in the new set.
    column_assignments: dict[Enemy, int] = {}

    # Repack groups 0-2 into boss_set_a/b/c.
    for g in range(3):
        target = getattr(sprites, _GROUP_SPRITE_ATTR[g])
        if g == 2:
            # Preserve the reserved region; pack new data after it.
            write_pos = _BOSS_SET_C_RESERVED_BYTES
        else:
            write_pos = 0

        for boss in group_bosses[g]:
            # Only pack primary bosses and companions that have sprite data.
            # Variant expansions (SINGLE_DODONGO, RED_GOHMA, etc.) share
            # their primary's sprites — they don't have separate tile entries.
            if boss not in tile_cache:
                continue

            column_assignments[boss] = _COL_START_MAIN + write_pos // 16

            data = tile_cache[boss]
            target[write_pos:write_pos + len(data)] = data
            write_pos += len(data)

            # Pack companion's tiles immediately after the primary.
            if boss in _COMPANIONS:
                companion = _COMPANIONS[boss]
                column_assignments[companion] = _COL_START_MAIN + write_pos // 16
                cdata = tile_cache[companion]
                target[write_pos:write_pos + len(cdata)] = cdata
                write_pos += len(cdata)

    # Pack group 3 (shared) into boss_set_expansion.
    write_pos = 0
    for boss in group_bosses[3]:
        if boss not in tile_cache:
            continue

        column_assignments[boss] = _COL_START_EXPANSION + write_pos // 16

        data = tile_cache[boss]
        sprites.boss_set_expansion[write_pos:write_pos + len(data)] = data
        write_pos += len(data)

        if boss in _COMPANIONS:
            companion = _COMPANIONS[boss]
            column_assignments[companion] = _COL_START_EXPANSION + write_pos // 16
            cdata = tile_cache[companion]
            sprites.boss_set_expansion[write_pos:write_pos + len(cdata)] = cdata
            write_pos += len(cdata)

    return column_assignments


def _build_group_column_maps(
    column_assignments: dict[Enemy, int],
    group_bosses: list[list[Enemy]],
) -> list[dict[int, int]]:
    """Build a vanilla-col → new-col mapping for each boss group.

    For every boss (and companion) packed into a group, maps each of its
    vanilla columns to the corresponding new column.  This covers ALL
    columns in the group's bank, not just the columns of a single boss,
    so cross-boss tile references within the same set resolve correctly.
    """
    group_maps: list[dict[int, int]] = [{} for _ in range(len(group_bosses))]

    boss_to_group: dict[Enemy, int] = {}
    for g, bosses in enumerate(group_bosses):
        for boss in bosses:
            boss_to_group[boss] = g

    for boss, new_start in column_assignments.items():
        if boss not in _SPRITE_OFFSET:
            continue
        grp = boss_to_group.get(boss)
        if grp is None:
            continue
        vanilla_start = _COL_START_MAIN + _SPRITE_OFFSET[boss] // 16
        num_cols = _SPRITE_SIZE[boss] // 16
        for i in range(num_cols):
            group_maps[grp][vanilla_start + i] = new_start + i

    return group_maps


# Which primary boss each variant/companion inherits its group from.
_VARIANT_PRIMARY: dict[Enemy, Enemy] = {
    Enemy.THE_BEAST: Enemy.AQUAMENTUS,
    Enemy.MOLDORM: Enemy.GLEEOK_1,
    Enemy.THE_KIDNAPPED: Enemy.BLUE_GOHMA,
}
for _primary, _variants in _VARIANT_EXPANSIONS.items():
    for _v in _variants:
        _VARIANT_PRIMARY[_v] = _primary
for _primary, _companion in _COMPANIONS.items():
    _VARIANT_PRIMARY[_companion] = _primary


def _update_tile_frames(
    enemies: EnemyData,
    column_assignments: dict[Enemy, int],
    group_bosses: list[list[Enemy]],
) -> None:
    """Update tile_frames for each boss to reflect its new sprite set position.

    Builds a per-group column mapping covering all bosses packed into each
    group, then remaps every boss's (and variant's) tile_frames through
    that mapping.  This handles cross-boss tile references within the same
    set (e.g. Aquamentus referencing Dodongo/Digdogger columns).

    Frames outside the boss bank range (192-255) and expansion range
    (48-79) are left unchanged — they reference fixed engine tiles.
    """
    group_maps = _build_group_column_maps(column_assignments, group_bosses)

    is_in_shared_group = set(group_bosses[3]) if len(group_bosses) > 3 else set()

    boss_to_group: dict[Enemy, int] = {}
    for g, bosses in enumerate(group_bosses):
        for boss in bosses:
            boss_to_group[boss] = g

    all_bosses_with_frames: set[Enemy] = set()
    for boss_set in _VANILLA_BOSS_GROUPS.values():
        all_bosses_with_frames |= boss_set
    all_bosses_with_frames |= {Enemy.THE_BEAST, Enemy.MOLDORM, Enemy.THE_KIDNAPPED}

    for boss in all_bosses_with_frames:
        if boss not in enemies.tile_frames:
            continue
        frames = enemies.tile_frames[boss]
        if not frames:
            continue

        # Determine which group this boss belongs to.
        grp = boss_to_group.get(boss)
        if grp is None:
            primary = _VARIANT_PRIMARY.get(boss)
            if primary is not None:
                grp = boss_to_group.get(primary)
        if grp is None:
            continue

        col_map = group_maps[grp]

        # Bonuses only apply to frames within the boss's own vanilla
        # column range, not to cross-boss references in the same set.
        own_primary = _VARIANT_PRIMARY.get(boss, boss)
        if own_primary in _SPRITE_OFFSET:
            own_start = _COL_START_MAIN + _SPRITE_OFFSET[own_primary] // 16
            own_end = own_start + _SPRITE_SIZE[own_primary] // 16
        else:
            own_start = own_end = -1

        in_shared = boss in is_in_shared_group or (
            own_primary in is_in_shared_group
        )
        is_aquamentus = boss in (Enemy.AQUAMENTUS, Enemy.THE_BEAST)

        remapped: list[int] = []
        for f in frames:
            if f in col_map:
                bonus = 0
                if own_start <= f < own_end:
                    if is_aquamentus:
                        bonus += 2
                    if in_shared:
                        bonus += 1
                remapped.append(col_map[f] + bonus)
            else:
                remapped.append(f)

        enemies.tile_frames[boss] = remapped


# ---------------------------------------------------------------------------
# Main entry point.
# ---------------------------------------------------------------------------

def change_dungeon_boss_groups(world: GameWorld, rng: Rng) -> None:
    """Redistribute bosses across the three boss sprite-set groups.

    1. Sort bosses by sprite size (descending) so largest bosses are placed first.
    2. Randomly pick a "special boss" forced into the shared pool.
    3. Assign each boss to a random group (0-2) or the shared pool (3),
       respecting each group's sprite tile column budget.
    4. Expand variant bosses into each group.
    5. Merge the shared pool into all three groups.
    6. For every room whose current enemy belongs to a vanilla boss group,
       replace it with a random boss from the same group's new pool,
       respecting room-type safety checks.

    Only Q1 levels (1-9) are processed.
    """
    # --- Sort bosses by sprite size descending (largest placed first) ---
    primary_bosses = list(_BOSS_TILE_COLUMNS)
    primary_bosses.sort(key=lambda b: _BOSS_TILE_COLUMNS[b], reverse=True)

    # --- Column budgets: groups 0-2 have 64 columns each, shared group has 32 ---
    group_budget = [64, 64, 64, 32]

    # --- Pre-fill: group 2 (BossSpriteSet.C) has 56 columns already reserved ---
    # The original reserves columns 192-247 (56 entries) in quadrant 2.
    group_budget[2] -= 56  # 64 - 56 = 8 columns available

    # --- Pick a special boss to force into the shared group ---
    special_boss = rng.choice(_SPECIAL_BOSSES)
    group_budget[3] -= _SPECIAL_RESTORE[special_boss]

    # --- Assignment: 4 groups (0=A, 1=B, 2=C, 3=shared) ---
    # Each group accumulates a list of primary boss enemies.
    group_bosses: list[list[Enemy]] = [[] for _ in range(4)]

    retry_count = 0

    i = 0
    while i < len(primary_bosses):
        boss = primary_bosses[i]

        # Columns needed, including companion sprites where applicable.
        columns = _BOSS_TILE_COLUMNS_WITH_COMPANION.get(
            boss, _BOSS_TILE_COLUMNS[boss],
        )

        # Pick a random group (0-3).
        group = int(rng.random() * 4)

        # Special boss is forced into group 3 (shared), with budget restored.
        if boss == special_boss:
            group = 3
            group_budget[3] += _SPECIAL_RESTORE[special_boss]

        # Check whether the group has enough columns remaining.
        if columns <= group_budget[group]:
            group_budget[group] -= columns
            group_bosses[group].append(boss)

            # Companion bosses (DIGDOGGER_SPAWN, FLYING_GLEEOK_HEAD,
            # PATRA_SPAWN) share a sprite set with their primary but are NOT
            # added to the replacement pool.  Their sprite tile data is
            # packed alongside their primary in _repack_boss_sprites.

            retry_count = 0
            i += 1
        else:
            # Retry same boss with a new random group.
            retry_count += 1
            if retry_count > _MAX_ASSIGNMENT_RETRIES:
                # Skip this boss to prevent infinite loop.
                retry_count = 0
                i += 1

    # --- Repack sprite tile data to match the new group assignments ---
    column_assignments = _repack_boss_sprites(world.sprites, group_bosses)

    # --- Update tile frame mappings so the engine finds tiles in the new sets ---
    _update_tile_frames(world.enemies, column_assignments, group_bosses)

    # TODO: Aquamentus engine sprite pointer patch.
    # The original writes to ROM 0x11898:
    #   value = tile_frames[AQUAMENTUS][3] + q3bonus - 2
    # where q3bonus is 1 if Aquamentus is in the shared group, else 0.
    # This likely tells the engine where to find Aquamentus's head/body
    # sprite within the active sprite set.  No data model property exists
    # for this yet.

    # TODO: Gleeok multi-head engine sprite pointer patches.
    # The original writes to three ROM addresses based on tile_frames[GLEEOK_1][0]:
    #   ROM 0x126F8 = tile_frames[GLEEOK_1][0] + q3bonus + 26
    #   ROM 0x126FE = tile_frames[GLEEOK_1][0] + q3bonus + 28
    #   ROM 0x6F5A  = tile_frames[GLEEOK_1][0] + q3bonus + 30
    # where q3bonus is 1 if GLEEOK_1 is in the shared group, else 0.
    # These likely point the engine at sprite tiles for additional Gleeok
    # heads.  No data model properties exist for these yet.

    # --- Expand variant bosses ---
    for boss_list in group_bosses:
        additions: list[Enemy] = []
        replacements: dict[Enemy, Enemy] = {}

        for boss in boss_list:
            if boss in _VARIANT_EXPANSIONS:
                additions.extend(_VARIANT_EXPANSIONS[boss])

        # Special case: GLEEOK_1 gets replaced by GLEEOK_2 in the pool.
        if Enemy.GLEEOK_1 in boss_list:
            replacements[Enemy.GLEEOK_1] = Enemy.GLEEOK_2

        # Apply replacements.
        for idx, boss in enumerate(boss_list):
            if boss in replacements:
                boss_list[idx] = replacements[boss]

        boss_list.extend(additions)

    # --- Merge shared group (3) into all three main groups ---
    if group_bosses[3]:
        for g in range(3):
            group_bosses[g].extend(group_bosses[3])

    # Build the final pools indexed by BossSpriteSet.
    new_pools: dict[BossSpriteSet, list[Enemy]] = {}
    for g, sprite_set in enumerate(_GROUP_ORDER):
        new_pools[sprite_set] = group_bosses[g]

    # --- Replace boss enemies in rooms ---
    for level in world.levels:
        for room in level.rooms:
            # Skip staircase rooms — the C# skips rooms where
            # (flag_byte & 0x3F) is 62 or 63, which are
            # TRANSPORT_STAIRCASE (0x3E) and ITEM_STAIRCASE (0x3F).
            if room.room_type in (RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE):
                continue
            enemy = room.enemy_spec.enemy

            # Determine which vanilla boss group this enemy belongs to.
            original_group: BossSpriteSet | None = None
            for sprite_set, members in _VANILLA_BOSS_GROUPS.items():
                if enemy in members:
                    original_group = sprite_set
                    break

            if original_group is None:
                continue

            pool = new_pools.get(original_group)
            if not pool:
                continue

            # Pick a random replacement, retrying on safety failures.
            for _attempt in range(_MAX_ROOM_RETRIES):
                new_boss = rng.choice(pool)

                if not is_safe_for_room(new_boss, room.room_type, has_push_block=room.movable_block):
                    continue

                room.enemy_spec.enemy = new_boss
                room.enemy_quantity = level.qty_table[0]
                break
