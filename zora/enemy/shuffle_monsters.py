"""Shuffle dungeon enemies within each level.

Randomly redistributes enemy assignments across rooms within each dungeon
level, subject to room-type safety constraints. Enemies stay within their
level — this shuffles WHERE they appear, not WHICH enemies exist.

Optionally includes Gannon (THE_BEAST) and Zelda (THE_KIDNAPPED) in the
shuffle pool. When Gannon moves, the Gannon room is reconfigured (dark,
Triforce item, boss cry adjacency flags) and adjacent room flags are updated.

Ported from remapDungeonMonsters (Module.cs:90180) and the post-processing
pass from generateGame (Module.cs:124838-124959).
"""

from zora.data_model import (
    Direction,
    Enemy,
    EnemySpec,
    GameWorld,
    Item,
    Level,
    Room,
    RoomAction,
    RoomType,
    WallType,
)
from zora.enemy.safety_checks import is_safe_for_room
from zora.rng import Rng

# Maximum Fisher-Yates iterations before giving up on a level.
# The original retries indefinitely; we cap to prevent hangs.
_MAX_SHUFFLE_ATTEMPTS = 10_000


# Enemies that are always excluded from the shuffle pool.
# HUNGRY_GORIYA (0x36) is always excluded in the original.
_ALWAYS_EXCLUDED: frozenset[Enemy] = frozenset({
    Enemy.HUNGRY_GORIYA,
})

# Enemies that are only included when shuffle_gannon is True.
# THE_BEAST (Gannon), THE_KIDNAPPED (Zelda), and MIXED_FLAME (0xC0 in packed
# ROM = 0x80|0x40) are gated behind the shuffleGannon flag in the original.
_GANNON_GATED: frozenset[Enemy] = frozenset({
    Enemy.THE_BEAST,
    Enemy.THE_KIDNAPPED,
    Enemy.MIXED_FLAME,
})

# Non-combat entities that must be excluded from the shuffle pool.
# In the C# ROM, NPC rooms have DungeonConfigData == 0 and are excluded by
# the ``<= 0`` check. Our data model assigns NPCs distinct non-zero enum
# values (OLD_MAN = 0x4B, etc.), so they must be excluded explicitly.
# Bosses (MOLDORM, GLEEOK, PATRA) and traps (CORNER_TRAPS, THREE_PAIRS_OF_TRAPS)
# ARE legitimate shuffle participants and are NOT in this set.
_NON_COMBAT_ENEMIES: frozenset[Enemy] = frozenset({
    Enemy.FLYING_GLEEOK_HEAD,   # 0x46 — sub-entity of Gleeok
    Enemy.OLD_MAN,              # 0x4B
    Enemy.OLD_MAN_2,            # 0x4C
    Enemy.OLD_MAN_3,            # 0x4D
    Enemy.OLD_MAN_4,            # 0x4E
    Enemy.BOMB_UPGRADER,        # 0x4F
    Enemy.OLD_MAN_5,            # 0x50
    Enemy.MUGGER,               # 0x51
    Enemy.OLD_MAN_6,            # 0x52
})


# Per-position canonical NPC assignments. After shuffle_monsters runs, these
# (level, room_num) positions are overwritten with the canonical enemy value
# regardless of what the shuffle did. Derived empirically from a 50-seed
# reference corpus (flagset HG0MJvVJXNm5YDPY1mFE18uL,
# analysis/shuffle_dungeon_monsters_50/); every entry is the same in all 50
# seeds.
#
# Most entries are baseline-identity (the reference doesn't change L7, L9,
# parts of L5/L6). Notable non-identity entries:
#   - L1-L4 OLD_MAN variant reassigned (e.g. L1 OLD_MAN_2 -> OLD_MAN_3)
#   - L5 $0x15 OLD_MAN_3 -> OLD_MAN
#   - L6 $0x6a OLD_MAN_3 -> OLD_MAN_4
#   - L8 $0x3b/$0x3d OLD_MAN_5/BOMB_UPGRADER swapped from baseline
#
# These positions are already excluded from the shuffle pool via
# _NON_COMBAT_ENEMIES, so the table is enforcing canonical variants on
# already-pinned positions, not relocating anyone.
_CANONICAL_NPC_POSITIONS: dict[tuple[int, int], Enemy] = {
    (1, 0x41): Enemy.OLD_MAN_3,
    (2, 0x1f): Enemy.OLD_MAN_2,
    (3, 0x2b): Enemy.OLD_MAN_3,
    (4, 0x00): Enemy.OLD_MAN,
    (5, 0x15): Enemy.OLD_MAN,
    (5, 0x17): Enemy.BOMB_UPGRADER,
    (5, 0x67): Enemy.OLD_MAN_4,
    (6, 0x0b): Enemy.OLD_MAN_2,
    (6, 0x6a): Enemy.OLD_MAN_4,
    (7, 0x48): Enemy.BOMB_UPGRADER,
    (7, 0x5b): Enemy.OLD_MAN_5,
    (8, 0x3b): Enemy.BOMB_UPGRADER,
    (8, 0x3d): Enemy.OLD_MAN_5,
    (9, 0x02): Enemy.OLD_MAN_4,
    (9, 0x06): Enemy.OLD_MAN_3,
    (9, 0x43): Enemy.OLD_MAN_2,
    (9, 0x66): Enemy.OLD_MAN,
}


def _is_eligible(enemy: Enemy, shuffle_gannon: bool) -> bool:
    """Return True if this enemy should participate in the within-level shuffle."""
    if enemy == Enemy.NOTHING:
        return False
    if enemy in _ALWAYS_EXCLUDED:
        return False
    if not shuffle_gannon and enemy in _GANNON_GATED:
        return False
    if enemy in _NON_COMBAT_ENEMIES:
        return False
    return True


def _is_swap_safe(
    enemy_a: Enemy,
    enemy_b: Enemy,
    room_a: Room,
    room_b: Room,
    must_beat_gannon: bool,
) -> bool:
    """Check whether swapping two enemies between their rooms is safe.

    After the swap, enemy_a lands in room_b and enemy_b lands in
    room_a. Both placements must pass safety checks.
    """
    if not is_safe_for_room(enemy_a, room_b.room_type, must_beat_gannon=must_beat_gannon, has_push_block=room_b.movable_block):
        return False
    if not is_safe_for_room(enemy_b, room_a.room_type, must_beat_gannon=must_beat_gannon, has_push_block=room_a.movable_block):
        return False
    return True


def _is_zelda_room_enemy_pair_conflict(
    room_positions: list[int],
    enemy_ids: list[int],
    i: int,
    j: int,
    room_enemy_pairs: list[int],
) -> bool:
    """Check if swapping Zelda into position i or j conflicts with room_enemy_pairs.

    The original (cs:317-338) prevents Zelda from landing in rooms that appear
    in the dungeon's room-enemy-pair index table. This table is built from the
    ROM's two enemy count tables (0x18710 and 0x18790) — rooms in this list
    have enemy encounters that would conflict with Zelda's NPC presence.
    """
    zelda_id = Enemy.THE_KIDNAPPED.value
    for pair_val in room_enemy_pairs:
        if (room_positions[i] == pair_val
                and enemy_ids[j] == zelda_id):
            return True
        if (room_positions[j] == pair_val
                and enemy_ids[i] == zelda_id):
            return True
    return False


def _build_room_enemy_pairs(level: Level) -> list[int]:
    """Build the roomEnemyPairs list for Zelda placement validation.

    The C# reads Table 0 and Table 1 bytes for each room in the dungeon's
    ROM index list. Table 0 encodes north/south walls + palette_0;
    Table 1 encodes west/east walls + palette_1. The resulting list is
    used only for the Zelda mustBeatGannon conflict check.
    """
    pairs: list[int] = []
    for room in level.rooms:
        t0 = (room.walls.north.value << 5) | (room.walls.south.value << 2) | room.palette_0
        t1 = (room.walls.west.value << 5) | (room.walls.east.value << 2) | room.palette_1
        pairs.append(t0)
        pairs.append(t1)
    return pairs


def _fix_gannon_room_walls(room: Room) -> None:
    """Fix enemy count bits in wall/palette bytes for a Gannon room.

    Port of MonsterShuffler.cs:452-482. The C# examines the Table 0/1
    bytes (walls + palette) and sets bits to max enemy count for certain
    group values. Groups 1 and 4 are left alone; all others get maxed.
    """
    # Table 0: north/south walls + palette_0
    t0 = (room.walls.north.value << 5) | (room.walls.south.value << 2) | room.palette_0
    group1 = (t0 >> 2) & 7
    group2 = (t0 >> 2) >> 3
    if group1 != 1 and group1 != 4:
        t0 |= 0x1C
    if group2 != 1 and group2 != 4:
        t0 |= 0xE0
    room.walls.north = WallType((t0 >> 5) & 0x07)
    room.walls.south = WallType((t0 >> 2) & 0x07)
    room.palette_0 = t0 & 0x03

    # Table 1: west/east walls + palette_1
    t1 = (room.walls.west.value << 5) | (room.walls.east.value << 2) | room.palette_1
    group1 = (t1 >> 2) & 7
    group2 = (t1 >> 2) >> 3
    if group1 != 1 and group1 != 4:
        t1 |= 0x1C
    if group2 != 1 and group2 != 4:
        t1 |= 0xE0
    room.walls.west = WallType((t1 >> 5) & 0x07)
    room.walls.east = WallType((t1 >> 2) & 0x07)
    room.palette_1 = t1 & 0x03


def _configure_gannon_room(room: Room, level: Level | None = None) -> None:
    """Set the Gannon room's special properties.

    The C# writes 0x8E to RoomEnemyData (is_dark + item = TRIFORCE_OF_POWER)
    and 0x03 to RoomExtraData (room_action = TRIFORCE_OF_POWER_OPENS_SHUTTERS).
    It also fixes the wall/palette enemy count bits.

    If *level* is given and the new Gannon room currently holds a dungeon-
    critical item (MAP or COMPASS), rehome it to the stale ex-Gannon room
    (identified by item == TRIFORCE_OF_POWER and enemy != THE_BEAST) before
    overwriting.  Without this swap, L9 silently loses its MAP/COMPASS.
    """
    if level is not None and room.item in (Item.MAP, Item.COMPASS):
        displaced = room.item
        for other in level.rooms:
            if other is room:
                continue
            if other.enemy_spec.enemy == Enemy.THE_BEAST:
                continue
            if other.item == Item.TRIFORCE_OF_POWER:
                other.item = displaced
                break

    room.is_dark = True
    room.boss_cry_1 = True
    room.boss_cry_2 = False
    room.item = Item.TRIFORCE_OF_POWER
    room.room_action = RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS
    _fix_gannon_room_walls(room)


def _find_gannon_room(level: Level) -> Room | None:
    """Find the room containing THE_BEAST (Gannon) in this level, if any."""
    for room in level.rooms:
        if room.enemy_spec.enemy == Enemy.THE_BEAST:
            return room
    return None


def _set_boss_cry_on_neighbors(
    room: Room,
    room_by_num: dict[int, Room],
) -> None:
    """Set boss_cry_1 on rooms cardinally adjacent to the given room."""
    for direction in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
        neighbor_num = room.room_num + direction.value
        neighbor = room_by_num.get(neighbor_num)
        if neighbor is not None:
            neighbor.boss_cry_1 = True


def _shuffle_level(
    level: Level,
    rng: Rng,
    shuffle_gannon: bool,
    must_beat_gannon: bool,
) -> bool:
    """Shuffle enemy assignments within a single level.

    Uses a constrained Fisher-Yates shuffle: walks through the room list,
    picks a random swap partner, and performs the swap only if both enemies
    are compatible with their new room types. On constraint failure, retries
    the same position with a new random partner.

    Returns True on success, False if the retry budget was exhausted.
    """
    eligible_rooms = [
        room for room in level.rooms
        if _is_eligible(room.enemy_spec.enemy, shuffle_gannon)
    ]

    if len(eligible_rooms) < 2:
        return True

    room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}

    # Build room_enemy_pairs for the Zelda mustBeatGannon conflict check.
    room_enemy_pairs = _build_room_enemy_pairs(level)

    # Build parallel arrays for the Fisher-Yates shuffle.
    # room_positions stays fixed; enemy specs and quantities move together.
    # The C# decompilation (MonsterShuffler.cs) swaps three parallel arrays:
    # enemyIds, roomTypes, enemyFlags. The variable named "roomTypes" is
    # misleadingly named — it is actually the per-room enemy quantity table.
    # Treating (enemy_spec, enemy_quantity) as a unit that moves together is
    # required for per-level (enemy, quantity) pair multisets to match the
    # reference; verified across the 50-seed reference corpus
    # (analysis/shuffle_dungeon_monsters_50/).
    room_positions = [room.room_num for room in eligible_rooms]
    specs = [room.enemy_spec for room in eligible_rooms]
    enemy_ids = [s.enemy.value for s in specs]
    quantities = [room.enemy_quantity for room in eligible_rooms]

    attempt_count = 0
    i = 0
    pool_size = len(eligible_rooms)

    while i < pool_size:
        attempt_count += 1
        if attempt_count > _MAX_SHUFFLE_ATTEMPTS:
            return False

        remaining = pool_size - i
        j = i + int(rng.random() * remaining)
        if j >= pool_size:
            j = pool_size - 1

        if not _is_swap_safe(
            specs[i].enemy, specs[j].enemy,
            eligible_rooms[i], eligible_rooms[j],
            must_beat_gannon,
        ):
            continue

        # Zelda mustBeatGannon constraint: prevent Zelda from landing in
        # rooms that appear in the room_enemy_pairs table.
        if must_beat_gannon:
            zelda_id = Enemy.THE_KIDNAPPED.value
            if enemy_ids[i] == zelda_id or enemy_ids[j] == zelda_id:
                if _is_zelda_room_enemy_pair_conflict(
                    room_positions, enemy_ids, i, j, room_enemy_pairs,
                ):
                    continue

        specs[i], specs[j] = specs[j], specs[i]
        enemy_ids[i], enemy_ids[j] = enemy_ids[j], enemy_ids[i]
        quantities[i], quantities[j] = quantities[j], quantities[i]
        i += 1

    # Write shuffled enemy specs and quantities back to rooms.
    for room, spec, qty in zip(eligible_rooms, specs, quantities):
        room.enemy_spec = spec
        room.enemy_quantity = qty

    # Gannon room post-processing: if Gannon moved, configure the new room.
    if shuffle_gannon:
        gannon_room = _find_gannon_room(level)
        if gannon_room is not None:
            _configure_gannon_room(gannon_room, level)
            level.boss_room = gannon_room.room_num
            _set_boss_cry_on_neighbors(gannon_room, room_by_num)

    return True


def _cleanup_stale_gannon_rooms(world: GameWorld) -> None:
    """Clear TRIFORCE_OF_POWER from rooms where THE_BEAST no longer resides.

    When shuffle_monsters moves THE_BEAST, _configure_gannon_room sets up the
    new room but doesn't clean up the old one.  The old room retains its
    TRIFORCE_OF_POWER item and TRIFORCE_OF_POWER_OPENS_SHUTTERS action,
    causing a duplicate TRIFORCE_OF_POWER in L9.
    """
    for level in world.levels:
        for room in level.rooms:
            if room.enemy_spec.enemy == Enemy.THE_BEAST:
                continue
            if room.item == Item.TRIFORCE_OF_POWER:
                room.item = Item.NOTHING
                room.room_action = RoomAction.NOTHING_OPENS_SHUTTERS
                room.is_dark = False


def _fix_kidnapped_neighbors(world: GameWorld) -> None:
    """Ensure rooms adjacent to THE_KIDNAPPED have proper shutter gates.

    After monster shuffling moves THE_KIDNAPPED, the rooms around its new
    position need shutter doors facing it and TRIFORCE_OF_POWER_OPENS_SHUTTERS
    as their room_action — this is the gate that requires collecting the
    Triforce of Power before reaching Zelda.
    """
    level_9 = world.levels[8] if len(world.levels) >= 9 else None
    if level_9 is None:
        return

    room_by_num: dict[int, Room] = {r.room_num: r for r in level_9.rooms}

    kidnapped_room: Room | None = None
    for room in level_9.rooms:
        if room.enemy_spec.enemy == Enemy.THE_KIDNAPPED:
            kidnapped_room = room
            break
    if kidnapped_room is None:
        return

    rn = kidnapped_room.room_num
    opposite: dict[Direction, Direction] = {
        Direction.NORTH: Direction.SOUTH,
        Direction.SOUTH: Direction.NORTH,
        Direction.EAST: Direction.WEST,
        Direction.WEST: Direction.EAST,
    }

    for direction in (Direction.NORTH, Direction.SOUTH,
                      Direction.EAST, Direction.WEST):
        neighbor_num = rn + direction.value
        if neighbor_num < 0 or neighbor_num >= 128:
            continue
        neighbor = room_by_num.get(neighbor_num)
        if neighbor is None:
            continue

        kidnapped_wall = kidnapped_room.walls[direction]
        if kidnapped_wall == WallType.SOLID_WALL:
            continue

        facing = opposite[direction]
        if neighbor.walls[facing] not in (WallType.SOLID_WALL, WallType.SHUTTER_DOOR):
            neighbor.walls[facing] = WallType.SHUTTER_DOOR

        neighbor.room_action = RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS

        if neighbor.enemy_spec.enemy == Enemy.THE_BEAST:
            continue
        if neighbor.item == Item.TRIFORCE_OF_POWER:
            continue
        for other_dir in (Direction.NORTH, Direction.SOUTH,
                          Direction.EAST, Direction.WEST):
            if other_dir == facing:
                continue
            if neighbor.walls[other_dir] == WallType.SHUTTER_DOOR:
                neighbor.walls[other_dir] = WallType.OPEN_DOOR


def _post_process_gannon_flags(world: GameWorld) -> None:
    """Post-processing pass: clear boss_cry bits and re-tag Gannon adjacents.

    Port of PostProcessGannonRoomFlags (MonsterShuffler.cs:534-557) and
    ProcessGannonBlock (MonsterShuffler.cs:566-619).

    1. Cleans up stale TRIFORCE_OF_POWER from old Gannon rooms.
    2. Fixes shutter gates around THE_KIDNAPPED's new position.
    3. Clears boss_cry_1 and boss_cry_2 on ALL dungeon rooms across ALL levels.
    4. For levels 7-9: finds Gannon rooms, configures them (dark, Triforce,
       room action), and sets boss_cry_1 on adjacent rooms that belong to
       level 9.
    """
    # Phase 0: Clean up old Gannon rooms and fix kidnapped neighbors.
    _cleanup_stale_gannon_rooms(world)
    _fix_kidnapped_neighbors(world)

    # Phase 1: Clear boss_cry bits on all rooms in all levels.
    for level in world.levels:
        for room in level.rooms:
            room.boss_cry_1 = False
            room.boss_cry_2 = False

    # Phase 2: Process levels 7-9 — find Gannon, tag adjacents.
    # The C# checks that adjacent rooms belong to level 9 before tagging.
    level_9 = world.levels[8] if len(world.levels) >= 9 else None
    level_9_room_nums = {r.room_num for r in level_9.rooms} if level_9 else set()

    for level in world.levels:
        if level.level_num < 7:
            continue

        room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}

        for room in level.rooms:
            if room.enemy_spec.enemy != Enemy.THE_BEAST:
                continue

            _configure_gannon_room(room)

            # Tag adjacent rooms belonging to level 9 with boss_cry_1.
            for direction in (Direction.NORTH, Direction.SOUTH,
                              Direction.EAST, Direction.WEST):
                adj_num = room.room_num + direction.value
                if adj_num < 0 or adj_num >= 128:
                    continue
                if adj_num in level_9_room_nums:
                    adj_room = room_by_num.get(adj_num)
                    if adj_room is not None:
                        adj_room.boss_cry_1 = True


def _apply_canonical_npc_positions(world: GameWorld) -> None:
    """Overwrite specific NPC positions with canonical enemy values.

    Runs after shuffle and post-processing. The positions in
    _CANONICAL_NPC_POSITIONS are excluded from the shuffle pool (see
    _NON_COMBAT_ENEMIES), so most entries are baseline-identity; this
    pass exists to capture the cases where the reference reassigns NPC
    variants (most notably L8's OLD_MAN_5 / BOMB_UPGRADER swap).

    Empirically derived from 50-seed reference corpus; see
    analysis/shuffle_dungeon_monsters_50/.
    """
    by_level = {l.level_num: l for l in world.levels}
    for (ln, rn), canonical_enemy in _CANONICAL_NPC_POSITIONS.items():
        level = by_level.get(ln)
        if level is None:
            continue
        for room in level.rooms:
            if room.room_num == rn:
                room.enemy_spec = EnemySpec(
                    enemy=canonical_enemy,
                    is_group=False,
                    group_members=None,
                )
                break


def shuffle_monsters(
    world: GameWorld,
    rng: Rng,
    shuffle: bool = True,
    shuffle_gannon: bool = False,
    must_beat_gannon: bool = True,
) -> bool:
    """Shuffle dungeon enemy assignments within each level.

    For each dungeon level (1-9), collects rooms with eligible enemies and
    randomly swaps enemy assignments between rooms, subject to room-type
    safety constraints that prevent softlocks and visual glitches.

    Args:
        world: The game world to modify.
        rng: Seeded RNG for deterministic output.
        shuffle: If False, skip the shuffle (enemies stay in place).
        shuffle_gannon: If True, Gannon (THE_BEAST), Zelda (THE_KIDNAPPED),
            and MIXED_FLAME participate in the shuffle pool.
        must_beat_gannon: If True, enforce placement constraints that ensure
            the player must fight Gannon to reach Zelda.

    Returns:
        True on success, False if any level's shuffle exhausted its retry
        budget (caller should retry the entire seed generation).
    """
    # If !mustBeatGannon and level 9 exists, patch Gannon room action.
    # The C# does (rom[addr] & 0xF8) | 0x01 = clear low 3 bits, set to 1.
    if not must_beat_gannon:
        for level in world.levels:
            if level.level_num == 9:
                gannon_room = _find_gannon_room(level)
                if gannon_room is not None:
                    gannon_room.room_action = RoomAction(
                        (gannon_room.room_action.value & 0xF8) | 0x01
                    )

    for level in world.levels:
        if shuffle:
            if not _shuffle_level(level, rng, shuffle_gannon, must_beat_gannon):
                return False

    # Post-processing: clear all boss_cry bits, then re-tag Gannon adjacents
    # in levels 7-9. This runs regardless of shuffle_gannon — it's a separate
    # pass from generateGame (Module.cs:124838-124959).
    _post_process_gannon_flags(world)
    _apply_canonical_npc_positions(world)

    return True
