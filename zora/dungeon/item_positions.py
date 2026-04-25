"""Item-positioning utilities shared across dungeon randomization steps.

Defines the standard item-position byte table used by all levels after
shuffle/scramble, the per-room-type whitelist of safe item positions, and
the direction-reachability constraints for chute-style rooms. Also exposes
the ``_assign_valid_item_positions`` helper that picks a valid, reachable
item position for each room given those tables.

Previously colocated with ``scramble_dungeon_rooms``; relocated here
because these tables are general dungeon plumbing, not part of the
scramble logic itself.
"""

from zora.data_model import (
    Direction,
    ItemPosition,
    Room,
    RoomType,
    WallType,
)
from zora.rng import Rng


_STANDARD_ITEM_POSITION_TABLE: list[int] = [0x89, 0xD6, 0xC9, 0x2C]


_VALID_ITEM_POSITIONS: dict[RoomType, list[ItemPosition]] = {
    RoomType.PLAIN_ROOM:            [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.SPIKE_TRAP_ROOM:       [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_D],
    RoomType.FOUR_SHORT_ROOM:       [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.FOUR_TALL_ROOM:        [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.AQUAMENTUS_ROOM:       [ItemPosition.POSITION_D, ItemPosition.POSITION_A, ItemPosition.POSITION_C],
    RoomType.GLEEOK_ROOM:           [ItemPosition.POSITION_C, ItemPosition.POSITION_A, ItemPosition.POSITION_D],
    RoomType.GOHMA_ROOM:            [ItemPosition.POSITION_A, ItemPosition.POSITION_B],
    RoomType.THREE_ROWS:            [ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.REVERSE_C:             [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_D],
    RoomType.CIRCLE_WALL:           [ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.DOUBLE_BLOCK:          [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.LAVA_MOAT:             [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.MAZE_ROOM:             [ItemPosition.POSITION_D, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.GRID_ROOM:             [ItemPosition.POSITION_B, ItemPosition.POSITION_D],
    RoomType.VERTICAL_CHUTE_ROOM:   [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.HORIZONTAL_CHUTE_ROOM: [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.VERTICAL_ROWS:         [ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.ZIGZAG_ROOM:           [ItemPosition.POSITION_A, ItemPosition.POSITION_C],
    RoomType.T_ROOM:                [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_D],
    RoomType.VERTICAL_MOAT_ROOM:    [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C, ItemPosition.POSITION_D],
    RoomType.CIRCLE_MOAT_ROOM:      [ItemPosition.POSITION_A, ItemPosition.POSITION_B, ItemPosition.POSITION_C],
    RoomType.POINTLESS_MOAT_ROOM:   [ItemPosition.POSITION_B, ItemPosition.POSITION_D],
    RoomType.CHEVY_ROOM:            [ItemPosition.POSITION_A, ItemPosition.POSITION_C],
    RoomType.NSU:                   [ItemPosition.POSITION_A, ItemPosition.POSITION_C],
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
    RoomType.TRIFORCE_ROOM:         [ItemPosition.POSITION_A],
    RoomType.TRANSPORT_STAIRCASE:   [],
    RoomType.ITEM_STAIRCASE:        [ItemPosition.POSITION_A],
}


# For direction-sensitive room types, maps (room_type, item_position) to the
# set of entry directions from which the item can be collected. Positions not
# listed are reachable from any direction. Derived from the standard position
# table coordinates: A=(8,9) B=(D,6) C=(C,9) D=(2,C).
_REQUIRED_DIRECTIONS: dict[tuple[RoomType, ItemPosition], frozenset[Direction]] = {
    (RoomType.HORIZONTAL_CHUTE_ROOM, ItemPosition.POSITION_A): frozenset({Direction.EAST, Direction.WEST}),
    (RoomType.HORIZONTAL_CHUTE_ROOM, ItemPosition.POSITION_B): frozenset({Direction.NORTH}),
    (RoomType.HORIZONTAL_CHUTE_ROOM, ItemPosition.POSITION_C): frozenset({Direction.EAST, Direction.WEST}),
    (RoomType.HORIZONTAL_CHUTE_ROOM, ItemPosition.POSITION_D): frozenset({Direction.SOUTH}),
    (RoomType.VERTICAL_CHUTE_ROOM, ItemPosition.POSITION_A): frozenset({Direction.NORTH, Direction.SOUTH}),
    (RoomType.VERTICAL_CHUTE_ROOM, ItemPosition.POSITION_B): frozenset({Direction.EAST}),
    (RoomType.VERTICAL_CHUTE_ROOM, ItemPosition.POSITION_C): frozenset({Direction.EAST}),
    (RoomType.VERTICAL_CHUTE_ROOM, ItemPosition.POSITION_D): frozenset({Direction.WEST}),
    (RoomType.T_ROOM, ItemPosition.POSITION_A): frozenset({Direction.SOUTH}),
    (RoomType.T_ROOM, ItemPosition.POSITION_B): frozenset({Direction.WEST, Direction.NORTH, Direction.EAST}),
    (RoomType.T_ROOM, ItemPosition.POSITION_D): frozenset({Direction.WEST, Direction.NORTH, Direction.EAST}),
}


def _has_door(room: Room, direction: Direction) -> bool:
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
        door_valid = []
        for pos in valid:
            required = _REQUIRED_DIRECTIONS.get((room.room_type, pos))
            if required is None:
                door_valid.append(pos)
            elif any(_has_door(room, d) for d in required):
                door_valid.append(pos)
        room.item_position = rng.choice(door_valid if door_valid else valid)
