"""Level-block model: one cell per room number, levels as views, and the
block encoder (SH-STAIR-09 fallout, SH-GRID-17, A43)."""
from zora.model.enums import (
    BossSpriteSet, Direction, Enemy, EnemySpriteSet, Item, RoomAction, RoomType, WallType,
)
from zora.model.rooms import EnemyInfo, ItemInfo, LayoutInfo, Room, SecretInfo, StaircaseRoom, WallSet
from zora.model.levels import Level, LevelBlock
from zora.rom.layout import LEVEL_TABLE_SIZE
from zora.rom.serialize.levels import encode_level_block

W, O = WallType.SOLID_WALL, WallType.OPEN_DOOR


def _room(num: int, layout: RoomType) -> Room:
    return Room(
        room_num=num,
        walls=WallSet(north=W, east=O, south=W, west=W),
        enemy_info=EnemyInfo(Enemy.AQUAMENTUS, count_index=1),
        layout_info=LayoutInfo(layout),
        item_info=ItemInfo(Item.BOMBS),
        secret_info=SecretInfo(RoomAction.NONE),
        palette_0=2, palette_1=2,
    )


def _level(num: int, block: LevelBlock, room_nums: list[int], stair_nums: list[int]) -> Level:
    return Level(
        level_num=num, entrance_room=room_nums[0] if room_nums else 0,
        entrance_direction=Direction.SOUTH, palette_raw=b"", fade_palette_raw=b"",
        staircase_room_pool=stair_nums, room_nums=room_nums, staircase_nums=stair_nums,
        block=block, boss_room=0xFF,
        enemy_sprite_set=EnemySpriteSet.A, boss_sprite_set=BossSpriteSet.A, start_y=0,
        item_position_table=[0] * 4, map_start=0, map_cursor_offset=0,
        map_data=b"", map_ppu_commands=b"", qty_table=[0, 2, 4, 8],
        stairway_data_raw=b"",
    )


def _cell_bytes(grid: bytes, room_num: int) -> list[int]:
    return [grid[table * LEVEL_TABLE_SIZE + room_num] for table in range(6)]


def test_levels_are_views_onto_their_block() -> None:
    block = LevelBlock.blank()
    block[0x02] = _room(0x02, RoomType.T_ROOM)
    level = _level(7, block, [0x02], [])
    level.rooms[0].item = Item.KEY          # a change through the level ...
    assert block.room(0x02).item == Item.KEY  # ... is a change to the block
    assert level.enemy_quantity(level.rooms[0]) == 2


def test_each_cell_is_encoded_once() -> None:
    # The SH-STAIR-09 clash (a room cell one level owns, another level's
    # stairway pool lists) cannot arise: the cell holds one thing.
    block = LevelBlock.blank()
    block[0x02] = _room(0x02, RoomType.T_ROOM)
    block[0x30] = StaircaseRoom(room_num=0x30, room_type=RoomType.ITEM_STAIRCASE,
                                exit_x=6, exit_y=9, item=Item.BOW, return_dest=0x21)
    grid = encode_level_block(block)
    assert _cell_bytes(grid, 0x02)[4] == Item.BOMBS.value & 0x1F
    assert _cell_bytes(grid, 0x30) == [0x21, 0x21, 0x69, 0x3F, Item.BOW.value, 0]


def test_blank_room_with_tail_openings() -> None:
    # SH-GRID-17 blank, then A43: a tail write opened the north (A bits
    # 5-7) and east (B bits 2-4) sides; palette bits kept
    walls = WallSet(north=O, east=O, south=W, west=W)
    block = LevelBlock.blank()
    block[5] = Room.blank(5, palette_0=3, palette_1=3, walls=walls)
    assert _cell_bytes(encode_level_block(block), 5) == [
        0x24 & ~0xE0 | 0x03, 0x24 & ~0x1C | 0x03, 0, 0, 0, 1]
