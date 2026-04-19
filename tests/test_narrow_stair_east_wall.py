"""Regression test: NARROW_STAIR_ROOM must never have a non-SOLID east wall.

The NARROW_STAIR tile layout has an impassable wall baked into its right side.
If the door data disagrees, the player sees an open doorway they can't walk
through — or worse, a room to the right with an open west door leading into
a wall.
"""
from zora.data_model import (
    Enemy,
    EnemySpec,
    Item,
    ItemPosition,
    Room,
    RoomAction,
    RoomType,
    WallSet,
    WallType,
)
from zora.dungeon.dungeon import _fix_narrow_stair_east_walls
from zora.dungeon.scramble_dungeon_rooms import scramble_dungeon_rooms
from zora.dungeon.shuffle_dungeon_rooms import shuffle_dungeon_rooms
from zora.parser import parse_game_world
from zora.rng import SeededRng


def _make_room(room_num: int, room_type: RoomType, walls: WallSet) -> Room:
    return Room(
        room_num=room_num,
        room_type=room_type,
        walls=walls,
        enemy_spec=EnemySpec(enemy=Enemy.NOTHING),
        enemy_quantity=1,
        item=Item.NOTHING,
        item_position=ItemPosition.POSITION_A,
        room_action=RoomAction.NOTHING_OPENS_SHUTTERS,
        is_dark=False,
        boss_cry_1=False,
        boss_cry_2=False,
        movable_block=False,
        palette_0=0,
        palette_1=0,
    )


def _assert_narrow_stair_invariant(world, context: str = "") -> None:
    for level in world.levels:
        for room in level.rooms:
            if room.room_type != RoomType.NARROW_STAIR_ROOM:
                continue
            assert room.walls.east == WallType.SOLID_WALL, (
                f"{context}L{level.level_num} room {room.room_num:#04x}: "
                f"NARROW_STAIR_ROOM has {room.walls.east.name} on east wall"
            )


def test_fix_narrow_stair_east_wall_open_door(bins):
    """_fix_narrow_stair_east_walls corrects an OPEN_DOOR east wall."""
    gw = parse_game_world(bins)
    for level in gw.levels:
        for room in level.rooms:
            if room.room_type == RoomType.NARROW_STAIR_ROOM:
                room.walls.east = WallType.OPEN_DOOR
    _fix_narrow_stair_east_walls(gw)
    _assert_narrow_stair_invariant(gw)


def test_fix_narrow_stair_east_wall_fixes_neighbor(bins):
    """The right neighbor's west wall is also forced to SOLID_WALL."""
    gw = parse_game_world(bins)

    for level in gw.levels:
        rooms_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}
        for room in level.rooms:
            if room.room_type != RoomType.NARROW_STAIR_ROOM:
                continue
            right_num = room.room_num + 1
            right = rooms_by_num.get(right_num)
            if room.room_num % 16 < 15 and right is not None:
                room.walls.east = WallType.OPEN_DOOR
                right.walls.west = WallType.OPEN_DOOR

    _fix_narrow_stair_east_walls(gw)

    for level in gw.levels:
        rooms_by_num = {r.room_num: r for r in level.rooms}
        for room in level.rooms:
            if room.room_type != RoomType.NARROW_STAIR_ROOM:
                continue
            right_num = room.room_num + 1
            right = rooms_by_num.get(right_num)
            if room.room_num % 16 < 15 and right is not None:
                assert right.walls.west == WallType.SOLID_WALL, (
                    f"Right neighbor {right_num:#04x} west wall not fixed"
                )


def test_narrow_stair_east_wall_after_scramble(bins):
    """After scramble_dungeon_rooms, no NARROW_STAIR_ROOM has a non-SOLID east wall."""
    for seed in range(50):
        gw = parse_game_world(bins)
        rng = SeededRng(seed)
        scramble_dungeon_rooms(gw, rng, shuffle_gannon_and_zelda=False)
        _fix_narrow_stair_east_walls(gw)
        _assert_narrow_stair_invariant(gw, f"seed {seed} ")


def test_narrow_stair_east_wall_after_shuffle_and_scramble(bins):
    """After both shuffle and scramble, the invariant holds."""
    for seed in range(50):
        gw = parse_game_world(bins)
        rng = SeededRng(seed)
        shuffle_dungeon_rooms(gw, rng)
        scramble_dungeon_rooms(gw, rng, shuffle_gannon_and_zelda=False)
        _fix_narrow_stair_east_walls(gw)
        _assert_narrow_stair_invariant(gw, f"seed {seed} ")
