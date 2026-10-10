"""Assemble GameWorld blocks and Levels from generated SetWorlds (final
write step).

Preserved per level (untouched): palette_raw, fade_palette_raw, start_y,
item_position_table, map_start, map_cursor_offset, map_ppu_commands,
qty_table, rom_level_num, screen_status_ram_offset.
"""
from ...model.enums import (
    BossSound,
    BossSpriteSet,
    Direction,
    Enemy,
    EnemySpriteSet,
    Item,
    ItemPosition,
    RoomAction,
    RoomType,
    WallType,
)
from ...model.levels import GANON_LIST, LEVEL_9, LEVEL_BLOCK_ROOMS, ZELDA_LIST, Cell, Level, LevelBlock
from ...model.rooms import (
    ITEM_POSITION_SHIFT,
    NO_ITEM_CODE,
    EnemyInfo,
    ItemInfo,
    LayoutInfo,
    Room,
    SecretInfo,
    StaircaseRoom,
    WallSet,
)
from ..late_gate.fixes import exit_position
from .tables import LEVEL_BOSS_SET, LEVEL_ENEMY_BANK
from .world import BOSS_CODES, DOOR_PASS_SELECTOR, SetWorld, StairKind, StairPlan

# SH-STAIR-16: an item cellar shows its item at screen position $89 (X $80,
# Y $90: the middle of the upper ledge).
CELLAR_ITEM_POSITION = 0x89
_ENEMY_SET = {"A": EnemySpriteSet.A, "B": EnemySpriteSet.B, "C": EnemySpriteSet.C}
_BOSS_SET = {"A": BossSpriteSet.A, "B": BossSpriteSet.B, "C": BossSpriteSet.C}

# plan side codes match WallType values
_WALL = [WallType.OPEN_DOOR, WallType.SOLID_WALL, WallType.WALK_THROUGH_WALL_1,
         WallType.WALK_THROUGH_WALL_2, WallType.BOMB_HOLE, WallType.LOCKED_DOOR_1,
         WallType.LOCKED_DOOR_2, WallType.SHUTTER_DOOR]


def _walls(world: SetWorld, cell: int) -> WallSet:
    plan = world.plans[cell]
    return WallSet(north=_WALL[plan.walls[0]], east=_WALL[plan.walls[1]],
                   south=_WALL[plan.walls[2]], west=_WALL[plan.walls[3]])


def _room_from_plan(world: SetWorld, cell: int) -> Room:
    """An owned cell's finished room."""
    plan = world.plans[cell]
    assert plan.layout is not None and plan.inner_palette is not None
    enemy_code = plan.enemy if plan.enemy is not None else 0x00
    if enemy_code in BOSS_CODES:
        count_index = 0                    # SH-BOSS-07: count written as code 0
    else:
        count_index = plan.qty_code if plan.qty_code is not None else 0
    item_code = plan.item if plan.item is not None else NO_ITEM_CODE
    item = Item.NOTHING if item_code == NO_ITEM_CODE else Item(item_code)
    return Room(
        room_num=cell,
        walls=_walls(world, cell),
        enemy_info=EnemyInfo(Enemy(enemy_code), count_index),
        layout_info=LayoutInfo(RoomType(plan.layout), plan.movable),
        # the boss sound is set by the late gate
        item_info=ItemInfo(item, BossSound(plan.boss_sound), plan.dark),
        secret_info=SecretInfo(RoomAction(plan.trigger), ItemPosition(plan.item_pos or 0)),
        palette_0=DOOR_PASS_SELECTOR,   # SH-DOOR-01
        palette_1=plan.inner_palette,
    )


def _cellar_item_position_bits(world: SetWorld, house: int) -> int:
    """SH-STAIR-16: an item cellar's item-position bits (LevelBlockAttrsF
    bits 5-4) are the index of position $89 among its level's four standard
    item positions (T6), times $10. The level is the one owning the cellar's
    return room: level 1's table gives $20, levels 4 and 5's $30, the others
    $00. No draw."""
    level_num = world.levels[world.blob_of[house]]
    return world.pos_tables[level_num].index(CELLAR_ITEM_POSITION) << ITEM_POSITION_SHIFT


def _staircase_from_plan(world: SetWorld, sp: StairPlan) -> StaircaseRoom:
    """A staircase or item cellar as the plans stand before the late gate,
    which moves its exits with their rooms and sets its exit position again."""
    if sp.kind is StairKind.CELLAR:
        assert sp.house is not None
        ex, ey = _exit_position(world, sp.house, sp.house)
        return StaircaseRoom(
            room_num=sp.cell, room_type=RoomType.ITEM_STAIRCASE,
            exit_x=ex, exit_y=ey,
            item=(None if sp.item is None
                  else Item.NOTHING if sp.item == NO_ITEM_CODE else Item(sp.item)),
            return_dest=sp.house,
            t5_raw=_cellar_item_position_bits(world, sp.house),
        )
    assert sp.first is not None and sp.second is not None
    # SH-STAIR-14 (spec-confirmed): first room = left exit, second = right exit.
    ex, ey = _exit_position(world, sp.first, sp.second)
    return StaircaseRoom(
        room_num=sp.cell, room_type=RoomType.TRANSPORT_STAIRCASE,
        exit_x=ex, exit_y=ey,
        left_exit=sp.first, right_exit=sp.second,
        t5_raw=0,                          # SH-STAIR-16: a transport's position bits stay $00
    )


def build_block(old: LevelBlock, world: SetWorld) -> LevelBlock:
    """One set's block as the late gate receives it: owned cells from their
    plans, staircases from their stair plans, and every other cell
    SH-GRID-17's blank room, keeping the old cell's palette bits and taking
    the plan's walls."""
    cells: list[Cell] = []
    for room_num in range(LEVEL_BLOCK_ROOMS):
        if room_num in world.stairs:
            cells.append(_staircase_from_plan(world, world.stairs[room_num]))
        elif world.blob_of[room_num] >= 0:
            cells.append(_room_from_plan(world, room_num))
        else:
            palette_0, palette_1 = old.palette_bits(room_num)
            cells.append(Room.blank(room_num, palette_0, palette_1,
                                    walls=_walls(world, room_num)))
    return LevelBlock(cells)


def _stairway_pool(world: SetWorld, blob: int) -> list[int]:
    """The level's staircases: those with a room in the level (each stair
    cell is listed in exactly one level's stairway pool)."""
    blob_cells = set(world.cells_by_blob[blob])
    pool = []
    for cell in sorted(world.stairs):
        sp = world.stairs[cell]
        stair_rooms = [sp.house] if sp.kind is StairKind.CELLAR else [sp.first, sp.second]
        if any(r is not None and r in blob_cells for r in stair_rooms):
            pool.append(cell)
    return pool


def build_level(old: Level, world: SetWorld, blob: int, block: LevelBlock) -> Level:
    level = world.levels[blob]
    entrance = world.entrance[level]
    pool = _stairway_pool(world, blob)
    # Terminate the stairway list explicitly: the level-info block has stale
    # vanilla bytes beyond +0x3E, and the parser's 0xFF-terminated read walks
    # off the end without a terminator.
    assert len(pool) <= 9, f"stair pool too large: {len(pool)}"
    stairway = bytes(pool) + b"\xFF" * (10 - len(pool))
    from .minimap import command_block, synthesize_minimap
    map_data, commands, map_start, map_cursor = synthesize_minimap(
        set(world.cells_by_blob[blob])
    )
    map_ppu = command_block(commands, old.map_ppu_commands)
    level_obj = Level(
        level_num=level,
        entrance_room=entrance,
        entrance_direction=Direction.SOUTH,
        palette_raw=old.palette_raw,
        fade_palette_raw=old.fade_palette_raw,
        staircase_room_pool=pool,
        room_nums=sorted(world.cells_by_blob[blob]),
        staircase_nums=pool,
        block=block,
        boss_room=old.boss_room,        # PS-L9REC-01: levels 1-8 keep vanilla's
        enemy_sprite_set=_ENEMY_SET[LEVEL_ENEMY_BANK[level]],
        boss_sprite_set=_BOSS_SET[LEVEL_BOSS_SET[level]],
        start_y=old.start_y,
        item_position_table=list(old.item_position_table),
        map_start=map_start,
        map_cursor_offset=map_cursor,
        map_data=map_data,
        map_ppu_commands=map_ppu,
        qty_table=list(old.qty_table),
        stairway_data_raw=stairway,
        rom_level_num=old.rom_level_num,
        screen_status_ram_offset=old.screen_status_ram_offset,
    )
    # relocated triforce: re-derive the triforce-room pointer at write
    level_obj.triforce_room_ptr = None
    return level_obj




def level9_records(level: Level, block: LevelBlock) -> None:
    """PS-L9REC-01: after the gate, level 9's block is scanned in room
    order; a room whose whole monster byte is $37 sets the Triforce-room
    record, one with $3E the boss-room record; the last match wins and no
    match leaves the record as it stands. The layout's monster bit is not
    consulted."""
    assert level.level_num == LEVEL_9
    for room in block.rooms:
        if room.monster_byte == ZELDA_LIST:
            level.triforce_room_ptr = room.room_num
        elif room.monster_byte == GANON_LIST:
            level.boss_room = room.room_num


def _exit_position(world: SetWorld, a: int, b: int) -> tuple[int, int]:
    """The exit position of a staircase between two exit rooms (a cellar's
    are both its return room)."""
    return exit_position((world.plans[a].layout_code, world.plans[b].layout_code))
