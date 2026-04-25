"""Test that direction-sensitive item positions are fixed after room shuffle."""
from zora.data_model import (
    BossSpriteSet,
    Direction,
    Enemy,
    EnemySpriteSet,
    EnemySpec,
    GameWorld,
    Item,
    ItemPosition,
    Level,
    Room,
    RoomAction,
    RoomType,
    WallSet,
    WallType,
)
from zora.dungeon.dungeon import _fix_direction_sensitive_item_positions, _get_entry_directions
from zora.dungeon.item_positions import _STANDARD_ITEM_POSITION_TABLE
from zora.parser import parse_game_world
from zora.rng import SeededRng

_PLAIN_ROOM_DEFAULTS: dict[str, object] = dict(
    room_type=RoomType.PLAIN_ROOM,
    enemy_spec=EnemySpec(Enemy.RED_DARKNUT),
    enemy_quantity=3,
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


def _make_room(room_num: int, walls: WallSet, **overrides: object) -> Room:
    kwargs = {**_PLAIN_ROOM_DEFAULTS, "room_num": room_num, "walls": walls}
    kwargs.update(overrides)
    return Room(**kwargs)  # type: ignore[arg-type]


def _make_minimal_level(rooms: list[Room], entrance_room: int,
                        entrance_direction: Direction) -> Level:
    return Level(
        level_num=1,
        entrance_room=entrance_room,
        entrance_direction=entrance_direction,
        palette_raw=b"\x00" * 0x24,
        fade_palette_raw=b"\x00" * 0x60,
        staircase_room_pool=[],
        rooms=rooms,
        staircase_rooms=[],
        boss_room=0,
        enemy_sprite_set=EnemySpriteSet.A,
        boss_sprite_set=BossSpriteSet.A,
        start_y=0,
        item_position_table=list(_STANDARD_ITEM_POSITION_TABLE),
        map_start=0,
        map_cursor_offset=0,
        map_data=b"\x00" * 16,
        map_ppu_commands=b"\x00" * 45,
        qty_table=[0, 0, 0, 0],
        stairway_data_raw=b"\x00" * 10,
    )


def _make_game_world_with_level(bins, level: Level) -> GameWorld:
    gw = parse_game_world(bins)
    gw.levels = [level]
    return gw


def test_t_room_item_position_fixed_when_only_south_entry(bins):
    """T_ROOM entered only from SOUTH should get an item position in the stem."""
    # Layout: entrance at 0x00 (plain room), south door leads to 0x10 (T_ROOM).
    # T_ROOM is only reachable from NORTH (entered from SOUTH of room 0x00,
    # so entry direction into 0x10 is NORTH... wait, let me think about this.
    #
    # Actually: room 0x00 is above 0x10. If entrance is 0x00 from NORTH,
    # player can exit SOUTH from 0x00 into 0x10, entering 0x10 from NORTH.
    #
    # For the T_ROOM: bar zone needs WEST/NORTH/EAST, stem needs SOUTH.
    # If entered from NORTH, bar positions (B, D) ARE reachable.
    # We want to test when only SOUTH entry exists.
    #
    # So: entrance at 0x10 (plain room), east door to 0x11 (T_ROOM).
    # Player enters 0x11 from WEST. T_ROOM bar needs W/N/E (reachable),
    # stem needs SOUTH (not reachable). If item is at POSITION_A (stem),
    # it should get reassigned.

    entrance = _make_room(
        0x10,
        WallSet(WallType.SOLID_WALL, WallType.OPEN_DOOR,
                WallType.SOLID_WALL, WallType.SOLID_WALL),
    )
    t_room = _make_room(
        0x11,
        WallSet(WallType.SOLID_WALL, WallType.SOLID_WALL,
                WallType.SOLID_WALL, WallType.OPEN_DOOR),
        room_type=RoomType.T_ROOM,
        item_position=ItemPosition.POSITION_A,  # stem — needs SOUTH
    )
    level = _make_minimal_level([entrance, t_room], 0x10, Direction.EAST)

    # Verify entry directions
    entry_dirs = _get_entry_directions(level)
    assert Direction.WEST in entry_dirs[0x11]
    assert Direction.SOUTH not in entry_dirs[0x11]

    # POSITION_A (stem) needs SOUTH, but room is only entered from WEST.
    # Fix should reassign to POSITION_B or POSITION_D (bar zone).
    gw = _make_game_world_with_level(bins, level)
    rng = SeededRng(42)
    _fix_direction_sensitive_item_positions(gw, rng)

    assert t_room.item_position in (ItemPosition.POSITION_B, ItemPosition.POSITION_D)


def test_t_room_item_position_fixed_when_only_north_entry(bins):
    """T_ROOM entered only from SOUTH door (entry dir NORTH... no).

    Let me reconsider: if the T_ROOM's only door is SOUTH, the player enters
    from below, so entry_direction = NORTH. Bar positions need W/N/E — NORTH
    is included, so bar IS reachable. Stem needs SOUTH — not available.

    To test stem-only scenario: T_ROOM only has SOUTH door, entered from NORTH.
    Item at POSITION_A (stem, needs SOUTH) should be reassigned since SOUTH
    entry isn't available.
    """
    # Room 0x20 (plain) above, south door to 0x30 (T_ROOM with only north door)
    entrance = _make_room(
        0x20,
        WallSet(WallType.SOLID_WALL, WallType.SOLID_WALL,
                WallType.OPEN_DOOR, WallType.SOLID_WALL),
    )
    t_room = _make_room(
        0x30,
        WallSet(WallType.OPEN_DOOR, WallType.SOLID_WALL,
                WallType.SOLID_WALL, WallType.SOLID_WALL),
        room_type=RoomType.T_ROOM,
        item_position=ItemPosition.POSITION_A,  # stem — needs SOUTH
    )
    level = _make_minimal_level([entrance, t_room], 0x20, Direction.NORTH)

    entry_dirs = _get_entry_directions(level)
    assert Direction.NORTH in entry_dirs[0x30]
    assert Direction.SOUTH not in entry_dirs.get(0x30, set())

    gw = _make_game_world_with_level(bins, level)
    rng = SeededRng(42)
    _fix_direction_sensitive_item_positions(gw, rng)

    assert t_room.item_position in (ItemPosition.POSITION_B, ItemPosition.POSITION_D)


def test_t_room_position_unchanged_when_reachable(bins):
    """T_ROOM item position should not change when it's reachable from entry dirs."""
    entrance = _make_room(
        0x20,
        WallSet(WallType.SOLID_WALL, WallType.SOLID_WALL,
                WallType.OPEN_DOOR, WallType.SOLID_WALL),
    )
    t_room = _make_room(
        0x30,
        WallSet(WallType.OPEN_DOOR, WallType.SOLID_WALL,
                WallType.SOLID_WALL, WallType.SOLID_WALL),
        room_type=RoomType.T_ROOM,
        item_position=ItemPosition.POSITION_B,  # bar — needs W/N/E
    )
    level = _make_minimal_level([entrance, t_room], 0x20, Direction.NORTH)

    gw = _make_game_world_with_level(bins, level)
    rng = SeededRng(42)
    _fix_direction_sensitive_item_positions(gw, rng)

    # POSITION_B needs NORTH — which is available. Should stay unchanged.
    assert t_room.item_position == ItemPosition.POSITION_B
