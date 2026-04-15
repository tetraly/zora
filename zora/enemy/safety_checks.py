"""Room-type safety checks for enemy and boss placement.

The NES engine has room layout constraints that make certain enemies
incompatible with certain room types. For example, Lanmola needs open
floor space and can't fit in rooms with narrow corridors or moats;
Gleeok's multi-head sprite collides with pillars in certain layouts.

This module centralizes all room-type safety data in one place. Each
enemy (or enemy category) maps to the set of RoomType values where it
CANNOT be placed. Consumer modules call ``is_safe_for_room`` instead of
maintaining their own copies of the restriction sets.

"""

from zora.data_model import Enemy, RoomType

# ---------------------------------------------------------------------------
# Unsafe room types per category.
# ---------------------------------------------------------------------------

_UNSAFE_ROOMS_TRAPS: frozenset[RoomType] = frozenset({
    RoomType.THREE_ROWS,             # 7
    RoomType.REVERSE_C,              # 8
    RoomType.CIRCLE_WALL,            # 9
    RoomType.MAZE_ROOM,              # 12
    RoomType.HORIZONTAL_CHUTE_ROOM,  # 15
    RoomType.T_ROOM,                 # 18
    RoomType.SPIRAL_STAIR_ROOM,      # 28
    RoomType.TRIFORCE_ROOM,          # 41
})

_UNSAFE_ROOMS_LANMOLA: frozenset[RoomType] = frozenset({
    RoomType.SPIKE_TRAP_ROOM,        # 1
    RoomType.AQUAMENTUS_ROOM,        # 4
    RoomType.CIRCLE_WALL,            # 9
    RoomType.LAVA_MOAT,              # 11
    RoomType.MAZE_ROOM,              # 12
    RoomType.HORIZONTAL_CHUTE_ROOM,  # 15
    RoomType.ZIGZAG_ROOM,            # 17
    RoomType.T_ROOM,                 # 18
    RoomType.CHEVY_ROOM,             # 22
    RoomType.NSU,                    # 23
    RoomType.NARROW_STAIR_ROOM,      # 27
    RoomType.SPIRAL_STAIR_ROOM,      # 28
    RoomType.TURNSTILE_ROOM,         # 32
    RoomType.ZELDA_ROOM,             # 39
    RoomType.TRIFORCE_ROOM,          # 41
    # Original also includes 51 (0x33)
})

_UNSAFE_ROOMS_RUPEE_BOSS: frozenset[RoomType] = frozenset({
    RoomType.CIRCLE_WALL,            # 9
    RoomType.LAVA_MOAT,              # 11
    RoomType.MAZE_ROOM,              # 12
    RoomType.VERTICAL_CHUTE_ROOM,    # 14
    RoomType.HORIZONTAL_CHUTE_ROOM,  # 15
    RoomType.VERTICAL_ROWS,          # 16
    RoomType.T_ROOM,                 # 18
    RoomType.VERTICAL_MOAT_ROOM,     # 19
    RoomType.CIRCLE_MOAT_ROOM,       # 20
    RoomType.CHEVY_ROOM,             # 22
    RoomType.NSU,                    # 23
    RoomType.HORIZONTAL_MOAT_ROOM,   # 24
    RoomType.DOUBLE_MOAT_ROOM,       # 25
    RoomType.DIAMOND_STAIR_ROOM,     # 26
    RoomType.SINGLE_SIX_BLOCK_ROOM,  # 30
    RoomType.TURNSTILE_ROOM,         # 32
})

_UNSAFE_ROOMS_GOHMA: frozenset[RoomType] = frozenset({
    RoomType.LAVA_MOAT,              # 11
    RoomType.VERTICAL_CHUTE_ROOM,    # 14
    RoomType.HORIZONTAL_CHUTE_ROOM,  # 15
    RoomType.T_ROOM,                 # 18
})

_UNSAFE_ROOMS_DODONGO: frozenset[RoomType] = frozenset({
    RoomType.CIRCLE_WALL,            # 9
    RoomType.LAVA_MOAT,              # 11
    RoomType.VERTICAL_CHUTE_ROOM,    # 14
    RoomType.HORIZONTAL_CHUTE_ROOM,  # 15
    RoomType.T_ROOM,                 # 18
})

_UNSAFE_ROOMS_GLEEOK: frozenset[RoomType] = frozenset({
    RoomType.CIRCLE_WALL,            # 9
    RoomType.LAVA_MOAT,              # 11
    RoomType.VERTICAL_CHUTE_ROOM,    # 14
    RoomType.HORIZONTAL_CHUTE_ROOM,  # 15
    RoomType.T_ROOM,                 # 18
    RoomType.CIRCLE_MOAT_ROOM,       # 20
    RoomType.TWO_FIREBALL_ROOM,      # 35
    RoomType.FOUR_FIREBALL_ROOM,     # 36
})

# Combined with the base Gleeok restrictions.
_UNSAFE_ROOMS_GLEEOK_4: frozenset[RoomType] = _UNSAFE_ROOMS_GLEEOK | frozenset({
    RoomType.VERTICAL_MOAT_ROOM,     # 19
    RoomType.POINTLESS_MOAT_ROOM,    # 21
    RoomType.CHEVY_ROOM,             # 22
    RoomType.NSU,                    # 23
    RoomType.HORIZONTAL_MOAT_ROOM,   # 24
    RoomType.DOUBLE_MOAT_ROOM,       # 25
})

_UNSAFE_ROOMS_THE_BEAST: frozenset[RoomType] = frozenset({
    RoomType.SPIKE_TRAP_ROOM,        # 1
    RoomType.FOUR_TALL_ROOM,         # 3
    RoomType.GLEEOK_ROOM,            # 5
    RoomType.GOHMA_ROOM,             # 6
    RoomType.THREE_ROWS,             # 7
    RoomType.REVERSE_C,              # 8
    RoomType.CIRCLE_WALL,            # 9
    RoomType.DOUBLE_BLOCK,           # 10
    RoomType.LAVA_MOAT,              # 11
    RoomType.MAZE_ROOM,              # 12
    RoomType.GRID_ROOM,              # 13
    RoomType.VERTICAL_CHUTE_ROOM,    # 14
    RoomType.HORIZONTAL_CHUTE_ROOM,  # 15
    RoomType.VERTICAL_ROWS,          # 16
    RoomType.ZIGZAG_ROOM,            # 17
    RoomType.T_ROOM,                 # 18
    RoomType.DIAMOND_STAIR_ROOM,     # 26
    RoomType.NARROW_STAIR_ROOM,      # 27
    RoomType.SPIRAL_STAIR_ROOM,      # 28
    RoomType.DOUBLE_SIX_BLOCK_ROOM,  # 29
    RoomType.SINGLE_SIX_BLOCK_ROOM,  # 30
    RoomType.FIVE_PAIR_ROOM,         # 31
    RoomType.TURNSTILE_ROOM,         # 32
    RoomType.SINGLE_BLOCK_ROOM,      # 34
    RoomType.TWO_FIREBALL_ROOM,      # 35
    RoomType.FOUR_FIREBALL_ROOM,     # 36
    RoomType.ZELDA_ROOM,             # 39
    RoomType.TRIFORCE_ROOM,          # 41
})

_UNSAFE_ROOMS_THE_KIDNAPPED: frozenset[RoomType] = frozenset({
    RoomType.CIRCLE_WALL,            # 9
    RoomType.HORIZONTAL_CHUTE_ROOM,  # 15
    RoomType.VERTICAL_ROWS,          # 16
    RoomType.SINGLE_SIX_BLOCK_ROOM,  # 30
})

# Extra rooms unsafe for THE_KIDNAPPED when "must beat Gannon" is enabled.
_UNSAFE_ROOMS_THE_KIDNAPPED_MUST_BEAT_GANNON: frozenset[RoomType] = frozenset({
    RoomType.NARROW_STAIR_ROOM,      # 27
    RoomType.SPIRAL_STAIR_ROOM,      # 28
})


# ---------------------------------------------------------------------------
# Enemy → unsafe room types mapping.
# ---------------------------------------------------------------------------

# Maps each Enemy to the frozenset of room types where it CANNOT be placed.
# Enemies not in this dict have no room-type restrictions.
UNSAFE_ROOM_TYPES: dict[Enemy, frozenset[RoomType]] = {
    # Traps
    Enemy.THREE_PAIRS_OF_TRAPS: _UNSAFE_ROOMS_TRAPS,
    Enemy.CORNER_TRAPS:         _UNSAFE_ROOMS_TRAPS,

    # Lanmola (both colors)
    Enemy.RED_LANMOLA:          _UNSAFE_ROOMS_LANMOLA,
    Enemy.BLUE_LANMOLA:         _UNSAFE_ROOMS_LANMOLA,

    # Rupee Boss
    Enemy.RUPEE_BOSS:           _UNSAFE_ROOMS_RUPEE_BOSS,

    # Gohma (both colors)
    Enemy.BLUE_GOHMA:           _UNSAFE_ROOMS_GOHMA,
    Enemy.RED_GOHMA:            _UNSAFE_ROOMS_GOHMA,

    # Dodongo (both sizes)
    Enemy.TRIPLE_DODONGO:       _UNSAFE_ROOMS_DODONGO,
    Enemy.SINGLE_DODONGO:       _UNSAFE_ROOMS_DODONGO,

    # Gleeok (1-3 heads share base restrictions)
    Enemy.GLEEOK_1:             _UNSAFE_ROOMS_GLEEOK,
    Enemy.GLEEOK_2:             _UNSAFE_ROOMS_GLEEOK,
    Enemy.GLEEOK_3:             _UNSAFE_ROOMS_GLEEOK,

    # Gleeok 4-head gets additional restrictions
    Enemy.GLEEOK_4:             _UNSAFE_ROOMS_GLEEOK_4,

    # The Beast/Gannon
    Enemy.THE_BEAST:            _UNSAFE_ROOMS_THE_BEAST,

    # The Kidnapped (Zelda) — base restrictions only.
    # The mustBeatGannon extension is handled in is_safe_for_room().
    Enemy.THE_KIDNAPPED:        _UNSAFE_ROOMS_THE_KIDNAPPED,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_safe_for_room(
    enemy: Enemy,
    room_type: RoomType,
    must_beat_gannon: bool = False,
) -> bool:
    """Check whether an enemy can be placed in the given room type.

    Args:
        enemy: The enemy to check.
        room_type: The room's layout type.
        must_beat_gannon: When True, THE_KIDNAPPED also cannot be placed
            in NARROW_STAIR_ROOM or SPIRAL_STAIR_ROOM (rooms adjacent to
            Gannon that would let the player skip the fight).

    Returns:
        True if the placement is safe, False if the room type is incompatible.
    """
    unsafe = UNSAFE_ROOM_TYPES.get(enemy)
    if unsafe is not None and room_type in unsafe:
        return False

    if must_beat_gannon and enemy == Enemy.THE_KIDNAPPED:
        if room_type in _UNSAFE_ROOMS_THE_KIDNAPPED_MUST_BEAT_GANNON:
            return False

    return True

def unsafe_room_types_for(enemy: Enemy) -> frozenset[RoomType]:
    """Return the set of room types where this enemy cannot be placed.

    Returns an empty frozenset if the enemy has no restrictions.
    """
    return UNSAFE_ROOM_TYPES.get(enemy, frozenset())


# ---------------------------------------------------------------------------
# Convenience wrappers used by shuffle_monsters / shuffle_monsters_between_levels.
#
# These accept raw int room-type values (RoomType.value) because the shuffle
# code works with parallel int arrays extracted from the data model.
# ---------------------------------------------------------------------------

# Gleeok 4-head raw enemy id (low 6 bits) used in the shuffle arrays.
_GLEEOK_4_RAW_ID = 5


def safe_for_traps(room_type: int) -> bool:
    return is_safe_for_room(Enemy.CORNER_TRAPS, RoomType(room_type))


def safe_for_lanmola(room_type: int) -> bool:
    return is_safe_for_room(Enemy.RED_LANMOLA, RoomType(room_type))


def safe_for_rupees(room_type: int) -> bool:
    return is_safe_for_room(Enemy.RUPEE_BOSS, RoomType(room_type))


def safe_for_gohma(room_type: int) -> bool:
    return is_safe_for_room(Enemy.BLUE_GOHMA, RoomType(room_type))


def safe_for_dodongo(room_type: int) -> bool:
    return is_safe_for_room(Enemy.TRIPLE_DODONGO, RoomType(room_type))


def safe_for_gleeok(room_type: int, enemy_id: int) -> bool:
    enemy = Enemy.GLEEOK_4 if enemy_id == _GLEEOK_4_RAW_ID else Enemy.GLEEOK_1
    return is_safe_for_room(enemy, RoomType(room_type))


def safe_for_gannon(room_type: int) -> bool:
    return is_safe_for_room(Enemy.THE_BEAST, RoomType(room_type))


def safe_for_zelda(room_type: int, must_beat_gannon: bool) -> bool:
    return is_safe_for_room(
        Enemy.THE_KIDNAPPED, RoomType(room_type),
        must_beat_gannon=must_beat_gannon,
    )


