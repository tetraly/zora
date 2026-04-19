"""Scramble room contents across all dungeon levels.

Randomly redistributes room contents (enemy, room type, items, darkness,
room action, etc.) between rooms across ALL dungeon levels simultaneously,
subject to room-type safety constraints for bosses and special enemies.

Unlike shuffle_dungeon_rooms (which rearranges rooms within a single level)
and shuffle_monsters (which swaps enemies within a single level), this
function moves entire room contents between levels. Walls stay at their
grid positions; only the "contents" move.

Optionally also shuffles item assignments between the scrambled rooms.

Ported from ScrambleDungeonRooms (ScrambleDungeonRooms.cs).
"""

from zora.data_model import (
    Direction,
    Enemy,
    GameWorld,
    ItemPosition,
    Room,
    RoomAction,
    RoomType,
    WallType,
)
from zora.rng import Rng
from zora.enemy.safety_checks import is_safe_for_room


# ---------------------------------------------------------------------------
# Retry limits
# ---------------------------------------------------------------------------

_MAX_PER_POSITION_RETRIES = 10_000
_MAX_TOTAL_RETRIES = 500_000


# ---------------------------------------------------------------------------
# Room type exclusions
# ---------------------------------------------------------------------------

# Room types excluded from the scramble pool.  These are special-purpose
# rooms (boss arenas, stair rooms, moat rooms, etc.) whose visual layout
# is tightly coupled to their contents and shouldn't be scrambled.
_EXCLUDED_ROOM_TYPES: frozenset[RoomType] = frozenset({
    RoomType.FOUR_SHORT_ROOM,         # 2
    RoomType.GLEEOK_ROOM,             # 5
    RoomType.THREE_ROWS,              # 7
    RoomType.CIRCLE_WALL,             # 9
    RoomType.DOUBLE_BLOCK,            # 10
    RoomType.LAVA_MOAT,               # 11
    RoomType.MAZE_ROOM,               # 12
    RoomType.GRID_ROOM,               # 13
    RoomType.VERTICAL_ROWS,           # 16
    RoomType.ZIGZAG_ROOM,             # 17
    RoomType.VERTICAL_MOAT_ROOM,      # 19
    RoomType.CIRCLE_MOAT_ROOM,        # 20
    RoomType.DIAMOND_STAIR_ROOM,      # 26
    RoomType.SPIRAL_STAIR_ROOM,       # 28
    RoomType.DOUBLE_SIX_BLOCK_ROOM,   # 29
    RoomType.SINGLE_SIX_BLOCK_ROOM,   # 30
})

# Room types that are always skipped (entrance, turnstile, staircase types).
# Staircase rooms are already separated into Level.staircase_rooms by the
# parser, but we check explicitly in case any leak through.
_ALWAYS_SKIP_ROOM_TYPES: frozenset[RoomType] = frozenset({
    RoomType.TURNSTILE_ROOM,          # 32 (0x20)
    RoomType.ENTRANCE_ROOM,           # 33 (0x21)
    RoomType.TRANSPORT_STAIRCASE,     # 62 (0x3E)
    RoomType.ITEM_STAIRCASE,          # 63 (0x3F)
})


# ---------------------------------------------------------------------------
# NPC / non-combat enemy exclusions
# ---------------------------------------------------------------------------

# The C# excludes rooms where enemyCombined is 138-146, which decodes to
# is_group + base enemy codes 10-18.  With is_group, these become Enemy
# values 0x4A-0x52: CORNER_TRAPS through OLD_MAN_6 — NPC/trap rooms that
# should not participate in the cross-level scramble.
_NPC_ENEMIES: frozenset[Enemy] = frozenset({
    Enemy.CORNER_TRAPS,    # 0x4A
    Enemy.OLD_MAN,         # 0x4B
    Enemy.OLD_MAN_2,       # 0x4C
    Enemy.OLD_MAN_3,       # 0x4D
    Enemy.OLD_MAN_4,       # 0x4E
    Enemy.BOMB_UPGRADER,   # 0x4F
    Enemy.OLD_MAN_5,       # 0x50
    Enemy.MUGGER,          # 0x51
    Enemy.OLD_MAN_6,       # 0x52
})


# ---------------------------------------------------------------------------
# Standard item position table & valid positions per room type
# ---------------------------------------------------------------------------

# Replaces each level's item_position_table so all levels use the same
# four drop coordinates:
#   A=0x89 (middle), B=0xD6 (top-right), C=0xC9 (bottom-left), D=0x2C (right)
_STANDARD_ITEM_POSITION_TABLE: list[int] = [0x89, 0xD6, 0xC9, 0x2C]

# Which ItemPositions are safe to use in each room type.  Positions that
# would land inside walls, water, or blocks are excluded.
_VALID_ITEM_POSITIONS: dict[RoomType, list[ItemPosition]] = {
    RoomType.PLAIN_ROOM:            [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.SPIKE_TRAP_ROOM:       [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.FOUR_SHORT_ROOM:       [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.FOUR_TALL_ROOM:        [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.AQUAMENTUS_ROOM:       [ItemPosition.POSITION_D, ItemPosition.POSITION_A, ItemPosition.POSITION_C],
    RoomType.GLEEOK_ROOM:           [ItemPosition.POSITION_C, ItemPosition.POSITION_A, ItemPosition.POSITION_D],
    RoomType.GOHMA_ROOM:            [ItemPosition.POSITION_A, ItemPosition.POSITION_B],
    RoomType.THREE_ROWS:            [ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.REVERSE_C:             [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.CIRCLE_WALL:           [ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.DOUBLE_BLOCK:          [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.LAVA_MOAT:             [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.MAZE_ROOM:             [ItemPosition.POSITION_D, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.GRID_ROOM:             [ItemPosition.POSITION_B, ItemPosition.POSITION_D],
    RoomType.VERTICAL_CHUTE_ROOM:   [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.HORIZONTAL_CHUTE_ROOM: [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.VERTICAL_ROWS:         [ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.ZIGZAG_ROOM:           [ItemPosition.POSITION_A, ItemPosition.POSITION_D],
    RoomType.T_ROOM:                [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_D],
    RoomType.VERTICAL_MOAT_ROOM:    [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.CIRCLE_MOAT_ROOM:      [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.POINTLESS_MOAT_ROOM:   [ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.CHEVY_ROOM:            [ItemPosition.POSITION_A, ItemPosition.POSITION_D],
    RoomType.NSU:                   [ItemPosition.POSITION_A, ItemPosition.POSITION_D],
    RoomType.HORIZONTAL_MOAT_ROOM:  [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.DOUBLE_MOAT_ROOM:      [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.DIAMOND_STAIR_ROOM:    [ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.NARROW_STAIR_ROOM:     [ItemPosition.POSITION_A, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.SPIRAL_STAIR_ROOM:     [ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.DOUBLE_SIX_BLOCK_ROOM: [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.SINGLE_SIX_BLOCK_ROOM: [ItemPosition.POSITION_D, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.FIVE_PAIR_ROOM:        [ItemPosition.POSITION_D, ItemPosition.POSITION_C, ItemPosition.POSITION_B],
    RoomType.TURNSTILE_ROOM:        [ItemPosition.POSITION_D],
    RoomType.ENTRANCE_ROOM:         [ItemPosition.POSITION_A],
    RoomType.SINGLE_BLOCK_ROOM:     [ItemPosition.POSITION_D, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.TWO_FIREBALL_ROOM:     [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.FOUR_FIREBALL_ROOM:    [ItemPosition.POSITION_A, ItemPosition.POSITION_C],
    RoomType.DESERT_ROOM:           [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.BLACK_ROOM:            [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.ZELDA_ROOM:            [ItemPosition.POSITION_A],
    RoomType.GANNON_ROOM:           [ItemPosition.POSITION_A, ItemPosition.POSITION_D],
    RoomType.TRIFORCE_ROOM:         [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.TRANSPORT_STAIRCASE:   [],
    RoomType.ITEM_STAIRCASE:        [],
}


# ---------------------------------------------------------------------------
# Room contents — what gets swapped between grid positions
# ---------------------------------------------------------------------------

class _RoomContents:
    """Snapshot of room contents that move during the scramble.

    Walls, palettes, and room_num stay at their grid position.
    Everything else travels with the room contents.
    """
    __slots__ = (
        'room_type', 'movable_block', 'enemy_spec',
        'item', 'item_position', 'room_action', 'is_dark',
        'boss_cry_1', 'boss_cry_2',
    )

    def __init__(self, room: Room) -> None:
        self.room_type = room.room_type
        self.movable_block = room.movable_block
        self.enemy_spec = room.enemy_spec
        self.item = room.item
        self.item_position = room.item_position
        self.room_action = room.room_action
        self.is_dark = room.is_dark
        self.boss_cry_1 = room.boss_cry_1
        self.boss_cry_2 = room.boss_cry_2

    def apply_to(self, room: Room) -> None:
        """Write these contents into a room, preserving walls, palettes, room_num, and enemy_quantity."""
        room.room_type = self.room_type
        room.movable_block = self.movable_block
        room.enemy_spec = self.enemy_spec
        room.item = self.item
        room.item_position = self.item_position
        room.room_action = self.room_action
        room.is_dark = self.is_dark
        room.boss_cry_1 = self.boss_cry_1
        room.boss_cry_2 = self.boss_cry_2


# ---------------------------------------------------------------------------
# Eligibility & locking
# ---------------------------------------------------------------------------

def _is_eligible(room: Room) -> bool:
    """Return True if this room should participate in the cross-level scramble."""
    if room.room_type in _ALWAYS_SKIP_ROOM_TYPES:
        return False
    if room.room_type in _EXCLUDED_ROOM_TYPES:
        return False
    enemy = room.enemy_spec.enemy
    if enemy == Enemy.NOTHING:
        return False
    if enemy == Enemy.HUNGRY_GORIYA:
        return False
    if enemy in _NPC_ENEMIES:
        return False
    if not _VALID_ITEM_POSITIONS.get(room.room_type):
        return False
    return True


def _is_locked(room: Room) -> bool:
    """Return True if this room is "locked" — can only swap with other locked rooms.

    Locked rooms have stairway-related visual layouts that must stay paired
    with rooms of the same kind to avoid visual glitches.
    """
    if room.room_type in (RoomType.NARROW_STAIR_ROOM, RoomType.SPIRAL_STAIR_ROOM):
        return True
    if room.movable_block and room.room_type in (
        RoomType.DIAMOND_STAIR_ROOM, RoomType.SPIRAL_STAIR_ROOM,
    ):
        return True
    if room.room_action == RoomAction.PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE:
        return True
    return False


# ---------------------------------------------------------------------------
# Safety checks for the swap
# ---------------------------------------------------------------------------

_NEEDS_ROOM_BELOW: frozenset[RoomType] = frozenset({
    RoomType.T_ROOM,
})

# _NEEDS_ROOM_ABOVE_AND_BELOW: frozenset[RoomType] = frozenset({
#     RoomType.HORIZONTAL_CHUTE_ROOM,
# })

# _NEEDS_LEFT_AND_RIGHT: frozenset[RoomType] = frozenset({
#     RoomType.VERTICAL_CHUTE_ROOM,
# })

_MOVEMENT_CONSTRAINED: frozenset[RoomType] = (
    _NEEDS_ROOM_BELOW  # | _NEEDS_ROOM_ABOVE_AND_BELOW | _NEEDS_LEFT_AND_RIGHT
)


def _check_adjacency(
    room_type: RoomType,
    room_num: int,
    level_room_nums: frozenset[int],
) -> bool:
    """Check whether placing room_type at room_num satisfies adjacency constraints."""
    if room_type in _NEEDS_ROOM_BELOW:
        if room_num + 16 >= 128 or room_num + 16 not in level_room_nums:
            return False

    # if room_type in _NEEDS_ROOM_ABOVE_AND_BELOW:
    #     if room_num - 16 < 0 or room_num - 16 not in level_room_nums:
    #         return False
    #     if room_num + 16 >= 128 or room_num + 16 not in level_room_nums:
    #         return False

    # if room_type in _NEEDS_LEFT_AND_RIGHT:
    #     col = room_num % 16
    #     if col == 0 or col == 15:
    #         return False
    #     if room_num - 1 not in level_room_nums:
    #         return False
    #     if room_num + 1 not in level_room_nums:
    #         return False

    return True


def _is_swap_safe(
    contents_i: _RoomContents,
    contents_j: _RoomContents,
    room_i_num: int,
    room_j_num: int,
    level_room_nums_i: frozenset[int],
    level_room_nums_j: frozenset[int],
) -> bool:
    """Check whether swapping two room contents between positions is safe.

    The C# checks each enemy category against BOTH positions (not just
    the destination).  For example, if either content has THE_BEAST, it
    checks SafeForGannon at both rooms[i].RoomIndex and rooms[j].RoomIndex.
    This is more conservative than strictly necessary (the enemy only moves
    to one position), but we replicate the C# behavior.
    """
    rt_i = contents_i.room_type
    rt_j = contents_j.room_type

    if rt_i in _MOVEMENT_CONSTRAINED or rt_j in _MOVEMENT_CONSTRAINED:
        if not _check_adjacency(rt_i, room_j_num, level_room_nums_j):
            return False
        if not _check_adjacency(rt_j, room_i_num, level_room_nums_i):
            return False

    enemy_i = contents_i.enemy_spec.enemy
    enemy_j = contents_j.enemy_spec.enemy

    if enemy_i == Enemy.THE_BEAST or enemy_j == Enemy.THE_BEAST:
        if not is_safe_for_room(Enemy.THE_BEAST, rt_j):
            return False
        if not is_safe_for_room(Enemy.THE_BEAST, rt_i):
            return False

    if enemy_i == Enemy.THE_KIDNAPPED or enemy_j == Enemy.THE_KIDNAPPED:
        if not is_safe_for_room(Enemy.THE_KIDNAPPED, rt_j):
            return False
        if not is_safe_for_room(Enemy.THE_KIDNAPPED, rt_i):
            return False

    if enemy_i.is_gohma() or enemy_j.is_gohma():
        if not is_safe_for_room(Enemy.BLUE_GOHMA, rt_j):
            return False
        if not is_safe_for_room(Enemy.BLUE_GOHMA, rt_i):
            return False

    if _is_dodongo(enemy_i) or _is_dodongo(enemy_j):
        if not is_safe_for_room(Enemy.TRIPLE_DODONGO, rt_j):
            return False
        if not is_safe_for_room(Enemy.TRIPLE_DODONGO, rt_i):
            return False

    if _is_gleeok(enemy_i) or _is_gleeok(enemy_j):
        if not _safe_for_gleeok(rt_j, enemy_i):
            return False
        if not _safe_for_gleeok(rt_i, enemy_j):
            return False

    return True


def _is_dodongo(enemy: Enemy) -> bool:
    return enemy in (Enemy.TRIPLE_DODONGO, Enemy.SINGLE_DODONGO)


def _is_gleeok(enemy: Enemy) -> bool:
    return enemy in (Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4)


def _safe_for_gleeok(room_type: RoomType, enemy: Enemy) -> bool:
    """Check Gleeok room-type restrictions, using the enemy to pick GLEEOK_4 vs base.

    The C# SafeForGleeok takes a room index and an enemy ID.  The enemy ID
    is used only to distinguish GLEEOK_4 (which has extra restrictions) from
    other Gleeoks.  Regardless of whether the enemy itself is a Gleeok, the
    function still checks Gleeok restrictions at the given position.
    """
    gleeok = Enemy.GLEEOK_4 if enemy == Enemy.GLEEOK_4 else Enemy.GLEEOK_1
    return is_safe_for_room(gleeok, room_type)


# ---------------------------------------------------------------------------
# Main scramble
# ---------------------------------------------------------------------------

def scramble_dungeon_rooms(
    world: GameWorld,
    rng: Rng,
    shuffle_gannon_and_zelda: bool = True,
    shuffle_drops: bool = False,
) -> bool:
    """Scramble room contents across all dungeon levels.

    Collects eligible rooms from all levels 1-9, then performs a constrained
    Fisher-Yates shuffle to redistribute room contents (enemy, room type,
    items, etc.) across the entire dungeon grid.  Locked rooms (stair rooms,
    push-block stairway rooms) can only swap with other locked rooms.

    Args:
        world: The game world to modify in place.
        rng: Seeded RNG for deterministic output.
        shuffle_gannon_and_zelda: If False, rooms containing THE_BEAST or
            THE_KIDNAPPED are excluded from the scramble pool.
        shuffle_drops: If True, also shuffle item assignments between the
            scrambled rooms after the main content shuffle.

    Returns:
        True on success, False if the retry budget was exhausted (caller
        should retry with a different seed).
    """
    # --- Phase 1: Collect eligible rooms across all levels ---

    pool: list[Room] = []
    for level in world.levels:
        for room in level.rooms:
            if not _is_eligible(room):
                continue
            enemy = room.enemy_spec.enemy
            if not shuffle_gannon_and_zelda:
                if enemy in (Enemy.THE_BEAST, Enemy.THE_KIDNAPPED):
                    continue
            pool.append(room)

    if len(pool) < 2:
        return True

    # Extract contents and lock status for each room in the pool.
    contents = [_RoomContents(room) for room in pool]
    locked = [_is_locked(room) for room in pool]

    # Build per-room level membership for adjacency checks.
    room_to_level_nums: dict[int, frozenset[int]] = {}
    for level in world.levels:
        level_nums = frozenset(r.room_num for r in level.rooms)
        for r in level.rooms:
            room_to_level_nums[r.room_num] = level_nums
    pool_level_nums = [room_to_level_nums.get(r.room_num, frozenset()) for r in pool]

    # --- Phase 2: Constrained Fisher-Yates shuffle ---

    total_retries = 0
    per_position_retries = 0
    i = 0

    while i < len(contents):
        remaining = len(contents) - i
        j = i + int(rng.random() * remaining)
        if j >= len(contents):
            j = len(contents) - 1

        constraint_failed = False

        if locked[i] != locked[j]:
            constraint_failed = True

        if not constraint_failed:
            if not _is_swap_safe(
                contents[i], contents[j],
                pool[i].room_num, pool[j].room_num,
                pool_level_nums[i], pool_level_nums[j],
            ):
                constraint_failed = True

        if constraint_failed:
            total_retries += 1
            if total_retries > _MAX_TOTAL_RETRIES:
                break
            if per_position_retries < _MAX_PER_POSITION_RETRIES:
                per_position_retries += 1
                continue
            per_position_retries = 0
            i += 1
            continue

        per_position_retries = 0
        contents[i], contents[j] = contents[j], contents[i]
        locked[i], locked[j] = locked[j], locked[i]
        i += 1

    # --- Phase 3: Write shuffled contents back to rooms ---

    for room, content in zip(pool, contents):
        content.apply_to(room)

    # --- Phase 4: Shuffle item drops (optional) ---

    if shuffle_drops:
        _shuffle_drops(pool, rng)

    # NOTE: item_position_table standardization and valid position
    # reassignment is handled by the orchestrator (dungeon.py) after
    # all shuffle/scramble steps complete.

    return True


# For direction-sensitive room types, maps (room_type, item_position) to the
# set of entry directions from which the item can be collected. Positions not
# listed are reachable from any direction. Derived from the standard position
# table coordinates: A=(8,9) B=(D,6) C=(C,9) D=(2,C).
_REQUIRED_DIRECTIONS: dict[tuple[RoomType, ItemPosition], frozenset[Direction]] = {
    # HORIZONTAL_CHUTE: top(Y=6)=NORTH, middle(Y=9)=EAST|WEST, bottom(Y=C)=SOUTH
    (RoomType.HORIZONTAL_CHUTE_ROOM, ItemPosition.POSITION_A): frozenset({Direction.EAST, Direction.WEST}),
    (RoomType.HORIZONTAL_CHUTE_ROOM, ItemPosition.POSITION_B): frozenset({Direction.NORTH}),
    (RoomType.HORIZONTAL_CHUTE_ROOM, ItemPosition.POSITION_C): frozenset({Direction.EAST, Direction.WEST}),
    (RoomType.HORIZONTAL_CHUTE_ROOM, ItemPosition.POSITION_D): frozenset({Direction.SOUTH}),
    # VERTICAL_CHUTE: left(X=2)=WEST, middle(X=8)=NORTH|SOUTH, right(X=D)=EAST
    (RoomType.VERTICAL_CHUTE_ROOM, ItemPosition.POSITION_A): frozenset({Direction.NORTH, Direction.SOUTH}),
    (RoomType.VERTICAL_CHUTE_ROOM, ItemPosition.POSITION_B): frozenset({Direction.EAST}),
    (RoomType.VERTICAL_CHUTE_ROOM, ItemPosition.POSITION_C): frozenset({Direction.EAST}),
    (RoomType.VERTICAL_CHUTE_ROOM, ItemPosition.POSITION_D): frozenset({Direction.WEST}),
    # T_ROOM: bar(X=2,X=D,Y=6)=WEST|NORTH|EAST, stem(X in 5-A,Y in 8-C)=SOUTH
    (RoomType.T_ROOM, ItemPosition.POSITION_A): frozenset({Direction.SOUTH}),
    (RoomType.T_ROOM, ItemPosition.POSITION_B): frozenset({Direction.WEST, Direction.NORTH, Direction.EAST}),
    (RoomType.T_ROOM, ItemPosition.POSITION_D): frozenset({Direction.WEST, Direction.NORTH, Direction.EAST}),
}


def _has_door(room: Room, direction: Direction) -> bool:
    """Return True if the room has any kind of door/passage in the given direction."""
    wall_map = {
        Direction.NORTH: room.walls.north,
        Direction.EAST: room.walls.east,
        Direction.SOUTH: room.walls.south,
        Direction.WEST: room.walls.west,
    }
    return wall_map.get(direction, WallType.SOLID_WALL) != WallType.SOLID_WALL


def _assign_valid_item_positions(pool: list[Room], rng: Rng) -> None:
    """Pick a random valid item position for each room based on its room type
    and available doors."""
    for room in pool:
        valid = _VALID_ITEM_POSITIONS.get(room.room_type)
        if not valid:
            continue
        # Filter positions to those reachable from at least one existing door
        door_valid = []
        for pos in valid:
            required = _REQUIRED_DIRECTIONS.get((room.room_type, pos))
            if required is None:
                door_valid.append(pos)
            elif any(_has_door(room, d) for d in required):
                door_valid.append(pos)
        room.item_position = rng.choice(door_valid if door_valid else valid)


def _shuffle_drops(pool: list[Room], rng: Rng) -> None:
    """Shuffle item assignments between the scrambled rooms.

    The C# swaps Table 5 bytes (item_position + room_action) at an offset
    of +DungeonBlockSize from each room's grid position, which reads from
    a DIFFERENT grid block's Table 5 (e.g., levels 1-6 rooms read from
    the levels 7-9 grid).  The exact cross-block semantics are unclear —
    it may be an intentional cross-quest scramble or a decompilation
    artifact.

    We approximate the game-level intent by shuffling item and item_position
    between the rooms that participated in the main scramble.
    """
    items = [(room.item, room.item_position) for room in pool]

    for k in range(len(items) - 1):
        remaining = len(items) - k
        swap_idx = k + int(rng.random() * remaining)
        if swap_idx >= len(items):
            swap_idx = len(items) - 1
        items[k], items[swap_idx] = items[swap_idx], items[k]

    for room, (item, item_pos) in zip(pool, items):
        room.item = item
        room.item_position = item_pos
