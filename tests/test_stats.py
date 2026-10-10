"""Tests for zora_measure/statistics.py on synthetic levels."""
from zora.model.enums import (
    BossSpriteSet, Direction, Enemy, EnemySpriteSet, Item, RoomAction, RoomType, WallType,
)
from zora.model.rooms import EnemyInfo, ItemInfo, LayoutInfo, Room, SecretInfo, StaircaseRoom, WallSet
from zora.model.levels import Level, LevelBlock
from zora_measure.statistics import level_stats

W = WallType.SOLID_WALL
O = WallType.OPEN_DOOR


def _room(num: int, walls: WallSet, item: Item = Item.NOTHING) -> Room:
    return Room(
        room_num=num, walls=walls,
        enemy_info=EnemyInfo(Enemy.NOTHING),
        layout_info=LayoutInfo(RoomType.PLAIN_ROOM),
        item_info=ItemInfo(item),
        secret_info=SecretInfo(RoomAction.NONE),
        palette_0=2, palette_1=2,
    )


def _level(rooms: list[Room], stairs: list[StaircaseRoom] | None = None) -> Level:
    block = LevelBlock.blank()
    for room in rooms:
        block[room.room_num] = room
    for stair in stairs or []:
        block[stair.room_num] = stair
    return Level(
        level_num=1, entrance_room=rooms[0].room_num,
        entrance_direction=Direction.SOUTH, palette_raw=b"",
        fade_palette_raw=b"", staircase_room_pool=[s.room_num for s in stairs or []],
        room_nums=sorted(r.room_num for r in rooms),
        staircase_nums=sorted(s.room_num for s in stairs or []),
        block=block, boss_room=0x7F,
        enemy_sprite_set=EnemySpriteSet.A, boss_sprite_set=BossSpriteSet.A,
        start_y=0, item_position_table=[0] * 4, map_start=0,
        map_cursor_offset=0, map_data=b"", map_ppu_commands=b"",
        qty_table=[0, 2, 4, 8], stairway_data_raw=b"",
    )


def test_simple_row_level() -> None:
    # 3 rooms in a row along the bottom, doors open east/west, everything else solid.
    a = _room(0x78, WallSet(north=W, east=O, south=W, west=W))
    b = _room(0x79, WallSet(north=W, east=O, south=W, west=O), item=Item.KEY)
    c = _room(0x7A, WallSet(north=W, east=W, south=W, west=O))
    s = level_stats(_level([a, b, c]))
    assert s.rooms == 3
    assert s.grid_width == 3 and s.grid_height == 1
    assert s.footprint == 3
    assert s.door_open == 2
    assert s.dead_end_rooms == 1          # room C only; A is the entrance
    assert s.keys_dropped == 1
    assert s.nothing_rooms == 2
    assert s.wall_edge == 3              # south side of each room at grid bottom
    assert s.wall_crosslevel == 5        # sides facing absent cells (top row + open ends)
    assert s.stair_pieces == 1
    assert s.pieces_final == 1
    assert s.item_rooms == 1


def test_closed_pair_and_stair_join() -> None:
    # Two disconnected pieces joined only by a transport staircase.
    left = [
        _room(0x70, WallSet(north=W, east=W, south=W, west=W)),
    ]
    right = [
        _room(0x77, WallSet(north=W, east=W, south=W, west=W)),
    ]
    stair = StaircaseRoom(
        room_num=0x7F, room_type=RoomType.TRANSPORT_STAIRCASE,
        exit_x=0, exit_y=0, left_exit=0x70, right_exit=0x77,
    )
    s = level_stats(_level(left + right, [stair]))
    assert s.rooms == 2
    assert s.transport_stairs == 1
    assert s.item_cellars == 0
    assert s.footprint == 3              # rooms + stair cell
    assert s.stair_pieces == 2           # no door adjacency at all
    assert s.pieces_final == 1           # staircase joins them
    # both rooms have degree 0 and are dead ends? degree 0 → not counted
    assert s.dead_end_rooms == 0


def test_wall_and_bomb_doors() -> None:
    a = _room(0x71, WallSet(north=W, east=WallType.BOMB_HOLE, south=W, west=W))
    b = _room(0x72, WallSet(north=W, east=W, south=W, west=WallType.BOMB_HOLE))
    c = _room(0x73, WallSet(north=W, east=W, south=W, west=W))
    # b-c pair: both sides solid → closed wall doorway (same-level neighbors)
    s = level_stats(_level([a, b, c]))
    assert s.door_bomb == 1
    assert s.door_closed_wall == 1


def test_one_way_shutter() -> None:
    a = _room(0x71, WallSet(north=W, east=WallType.SHUTTER_DOOR, south=W, west=W))
    b = _room(0x72, WallSet(north=W, east=W, south=W, west=O))
    s = level_stats(_level([a, b]))
    assert s.door_oneway_shutter == 1


def test_grid_stats_membership_free() -> None:
    """grid_stats counts every cell of the block, owned by a level or not;
    door sides and pairs are counted over ordinary rooms only."""
    from zora_measure.statistics import grid_stats
    block = LevelBlock.blank()                     # all-wall rooms, item bombs
    entrance = block.room(0x00)
    entrance.walls = WallSet(north=W, east=WallType.SHUTTER_DOOR, south=O, west=W)
    entrance.room_type = RoomType.ENTRANCE_ROOM
    entrance.item = Item.NOTHING
    block.room(0x10).walls.north = O               # facing entrance's open south
    block[0x02] = StaircaseRoom(room_num=0x02, room_type=RoomType.ITEM_STAIRCASE,
                                exit_x=6, exit_y=9, item=Item.BOW, return_dest=0x01)
    gs = grid_stats("1-6", block)
    assert gs.cells_total == 128
    assert gs.layout_entrance_21 == 1
    assert gs.layout_cellar_3f == 1
    assert gs.item_none == 1                        # the entrance; the cellar holds a bow
    assert sum((gs.sides_open, gs.sides_wall, gs.sides_walk, gs.sides_bomb,
                gs.sides_key, gs.sides_shutter)) == 127 * 4
    assert (gs.sides_open, gs.sides_shutter) == (2, 1)
    assert gs.pairs_synced >= 1
    assert gs.pairs_shutter_oneway == 0             # the shutter faces a wall:
    assert gs.pairs_oneway_connector == 1           # one side solid
    assert gs.pairs_other_mismatch == 0


def test_grid_stats_trigger_tally() -> None:
    """Triggers: 0 → trigger_none, 1 → kill_all, 7 → kill_for_item,
    4 → push_door, 5 → push_stairs, 2/3/6 → other."""
    from zora_measure.statistics import grid_stats
    block = LevelBlock.blank()                     # blank rooms: trigger 1
    for room_num, act in enumerate([0, 1, 1, 2, 3, 4, 5, 6, 7, 7, 7]):
        block.room(room_num).room_action = RoomAction(act)
    gs = grid_stats("t", block)
    assert (gs.trigger_none, gs.trigger_kill_all, gs.trigger_kill_for_item,
            gs.trigger_push_door, gs.trigger_push_stairs, gs.trigger_other) == \
        (1, 2 + 117, 3, 1, 1, 3)
