"""Levels: level information, rooms, staircases and the two level blocks."""

from zora.model.enums import (
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
from zora.model.levels import VANILLA_BOSS_SPRITE_SETS, VANILLA_ENEMY_SPRITE_SETS, Cell, Level, LevelBlock
from zora.model.room_grid import neighbour
from zora.model.rooms import (
    EnemyInfo,
    EnemySpec,
    ItemInfo,
    LayoutInfo,
    Room,
    SecretInfo,
    StaircaseRoom,
    WallSet,
)
from zora.rom.layout import DUNGEON_NOTHING_CODE, LEVEL_INFO_SIZE, LEVEL_TABLE_SIZE, NUM_TABLES, read_le16
from zora.rom.parse.bin_files import RawBinFiles

# ---------------------------------------------------------------------------
# Level info helpers
# ---------------------------------------------------------------------------

def _level_info_block(bins: RawBinFiles, level_index: int) -> bytes:
    """level_index 0 = overworld info slot, 1 = Level 1, ..., 9 = Level 9"""
    offset = level_index * LEVEL_INFO_SIZE
    return bins.level_info[offset:offset + LEVEL_INFO_SIZE]

def _level_info_block_by_index(bins: RawBinFiles, index: int) -> bytes:
    offset = index * LEVEL_INFO_SIZE
    return bins.level_info[offset:offset + LEVEL_INFO_SIZE]


# ---------------------------------------------------------------------------
# Room parsing
# ---------------------------------------------------------------------------

def _parse_staircase_room(
    room_num: int,
    t0: int, t1: int, t2: int, t3: int, t4: int, t5: int,
    nothing_code: int = DUNGEON_NOTHING_CODE,
) -> "StaircaseRoom":
    room_type = RoomType(t3 & 0x3F)
    exit_x = (t2 >> 4) & 0x0F
    exit_y = t2 & 0x0F
    if room_type == RoomType.TRANSPORT_STAIRCASE:
        return StaircaseRoom(
            room_num=room_num,
            room_type=room_type,
            exit_x=exit_x,
            exit_y=exit_y,
            left_exit=t0 & 0x7F,
            right_exit=t1 & 0x7F,
            t5_raw=t5,
        )
    # ITEM_STAIRCASE
    return StaircaseRoom(
        room_num=room_num,
        room_type=room_type,
        exit_x=exit_x,
        exit_y=exit_y,
        # the "no item" code decodes to the NOTHING meaning, as in rooms
        item=Item.NOTHING if t4 & 0x1F == nothing_code else Item(t4 & 0x1F),
        return_dest=t0 & 0x7F,
        return_dest_b=(t1 & 0x7F) if (t1 & 0x7F) != (t0 & 0x7F) else None,
        t5_raw=t5,
    )


def _parse_room(
    room_num: int,
    t0: int, t1: int, t2: int, t3: int, t4: int, t5: int,
    nothing_code: int = DUNGEON_NOTHING_CODE,
) -> Room:
    room_type = RoomType(t3 & 0x3F)
    movable_block = bool(t3 & 0x40)

    north_wall = WallType((t0 >> 5) & 0x07)
    south_wall = WallType((t0 >> 2) & 0x07)
    west_wall  = WallType((t1 >> 5) & 0x07)
    east_wall  = WallType((t1 >> 2) & 0x07)
    walls = WallSet(north=north_wall, east=east_wall,
                    south=south_wall, west=west_wall)
    palette_0 = t0 & 0x03
    palette_1 = t1 & 0x03

    enemy_code = t2 & 0x3F
    if t3 & 0x80:
        enemy_code += 0x40
    count_index = (t2 >> 6) & 0x03

    is_dark    = bool(t4 & 0x80)
    boss_sound = BossSound((t4 >> 5) & 0x03)
    item_code  = t4 & 0x1F

    if item_code == nothing_code:
        if nothing_code == Item.TRIFORCE_OF_POWER and enemy_code == Enemy.THE_BEAST:
            # ZORA_REMAP (QUESTIONS #39): $0E is the triforce of power only
            # in Ganon's room — the engine hides it at load (the patched
            # CreateRoomObjects compare) and only Ganon_ActivateRoomItem
            # reveals it. Anywhere else $0E is "no item".
            item = Item.TRIFORCE_OF_POWER
        else:
            item = Item.NOTHING      # the "no item" MEANING (see game_config)
    else:
        item = Item(item_code)

    item_position = ItemPosition((t5 >> 4) & 0x03)
    room_action   = RoomAction(t5 & 0x07)

    return Room(
        room_num=room_num,
        walls=walls,
        # a mixed group's members are GameWorld.enemies.mixed_groups[code]
        enemy_info=EnemyInfo(Enemy(enemy_code), count_index),
        layout_info=LayoutInfo(room_type, movable_block),
        item_info=ItemInfo(item, boss_sound, is_dark),
        secret_info=SecretInfo(room_action, item_position),
        palette_0=palette_0,
        palette_1=palette_1,
    )


# ---------------------------------------------------------------------------
# Level parsing
# ---------------------------------------------------------------------------

_CPU_TO_ENEMY_SET: dict[int, EnemySpriteSet] = {
    0x9DBB: EnemySpriteSet.A,
    0x987B: EnemySpriteSet.B,
    0x9A9B: EnemySpriteSet.C,
    0x965B: EnemySpriteSet.OW,
}

_CPU_TO_BOSS_SET: dict[int, BossSpriteSet] = {
    0x9FDB: BossSpriteSet.A,
    0xA3DB: BossSpriteSet.B,
    0xA7DB: BossSpriteSet.C,
}


def _read_cpu_addr(data: bytes, index: int) -> int:
    return read_le16(data, index)


def parse_enemy_sprite_set(pointer_data: bytes, level_num: int) -> EnemySpriteSet:
    cpu_addr = read_le16(pointer_data, level_num)
    return _CPU_TO_ENEMY_SET.get(cpu_addr, VANILLA_ENEMY_SPRITE_SETS[level_num])


def parse_boss_sprite_set(pointer_data: bytes, level_num: int) -> BossSpriteSet:
    cpu_addr = read_le16(pointer_data, level_num)
    return _CPU_TO_BOSS_SET.get(cpu_addr, VANILLA_BOSS_SPRITE_SETS[level_num])


def _parse_enemy_sprite_set(bins: RawBinFiles, level_num: int) -> EnemySpriteSet:
    return parse_enemy_sprite_set(bins.level_sprite_set_pointers, level_num)


def _parse_boss_sprite_set(bins: RawBinFiles, level_num: int) -> BossSpriteSet:
    return parse_boss_sprite_set(bins.boss_sprite_set_pointers, level_num)


def _flood_fill_level_rooms(
    entrance_room: int,
    staircase_slots: set[int],
    t: list[bytes],
) -> set[int]:
    """Flood-fill from entrance_room to find all reachable room slots.

    The fill follows every non-wall side, the entrance room's south side
    included, as the vanilla engine does: it returns to the overworld only
    when the next room ID is off the grid (Z_05 CalculateNextRoomForDoor).
    An entrance above the bottom row, whose room below belongs to another
    level (SH-ENT-01), therefore joins the two levels (QUESTIONS #54)."""
    def in_bounds(rn: int) -> bool:
        return 0x00 <= rn <= 0x7F

    def wall_fill(seeds: list[int], visited: set[int]) -> None:
        queue = list(seeds)
        while queue:
            rn = queue.pop()
            if rn in visited or not in_bounds(rn):
                continue
            visited.add(rn)
            if rn in staircase_slots:
                continue
            north_wall = WallType((t[0][rn] >> 5) & 0x07)
            south_wall = WallType((t[0][rn] >> 2) & 0x07)
            west_wall  = WallType((t[1][rn] >> 5) & 0x07)
            east_wall  = WallType((t[1][rn] >> 2) & 0x07)
            wall_by_dir = {
                Direction.NORTH: north_wall,
                Direction.SOUTH: south_wall,
                Direction.WEST:  west_wall,
                Direction.EAST:  east_wall,
            }
            for direction in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
                if wall_by_dir[direction] != WallType.SOLID_WALL:
                    other = neighbour(rn, direction.side)
                    if other is not None and other not in visited:
                        queue.append(other)

    visited: set[int] = set()
    wall_fill([entrance_room], visited)

    while True:
        new_seeds = []
        for rn in staircase_slots:
            if rn in visited:
                continue
            if RoomType(t[3][rn] & 0x3F) == RoomType.TRANSPORT_STAIRCASE:
                left_exit  = t[0][rn] & 0x7F
                right_exit = t[1][rn] & 0x7F
                if left_exit in visited or right_exit in visited:
                    visited.add(rn)
                    new_seeds.append(left_exit)
                    new_seeds.append(right_exit)
        if not new_seeds:
            break
        wall_fill(new_seeds, visited)

    return visited


_STAIRCASE_LAYOUTS = (RoomType.TRANSPORT_STAIRCASE.value, RoomType.ITEM_STAIRCASE.value)


def _block_tables(grid_data: bytes) -> list[bytes]:
    return [grid_data[table * LEVEL_TABLE_SIZE: (table + 1) * LEVEL_TABLE_SIZE]
            for table in range(NUM_TABLES)]


def _parse_block(
    grid_data: bytes,
    mixed_groups: dict[int, EnemySpec],
    nothing_code: int = DUNGEON_NOTHING_CODE,
) -> LevelBlock:
    """Decode all 128 rooms of one level block, owned or not: a cell whose
    layout is $3E/$3F is a staircase, every other cell an ordinary room."""
    t = _block_tables(grid_data)
    cells: list[Cell] = []
    for room_num in range(LEVEL_TABLE_SIZE):
        raw = {"t0": t[0][room_num], "t1": t[1][room_num], "t2": t[2][room_num],
               "t3": t[3][room_num], "t4": t[4][room_num], "t5": t[5][room_num]}
        if raw["t3"] & 0x3F in _STAIRCASE_LAYOUTS:
            cells.append(_parse_staircase_room(room_num, **raw, nothing_code=nothing_code))
        else:
            cells.append(_parse_room(room_num, **raw,
                                     nothing_code=nothing_code))
    return LevelBlock(cells)


# LevelInfo: the end-of-list marker of the stairway list, and the entrance
# direction byte's values (byte 61, $6BBB).
STAIRWAY_LIST_END = 0xFF
_DIR_BYTE_TO_DIRECTION = {1: Direction.NORTH, 2: Direction.SOUTH, 3: Direction.EAST, 4: Direction.WEST}
# Quirk: level 3's vanilla stairway list is empty; its staircase cell is $0F.
LEVEL_3_STAIRWAY_FALLBACK = 0x0F


def _parse_single_level(
    level_num: int,
    grid_data: bytes,
    block: LevelBlock,
    level_info: bytes,
) -> Level:
    """Parse one level's level-info fields and find the rooms it owns in
    its block (the flood fill from its entrance).

    Returned Level has default sprite sets — caller assigns those separately.
    """
    offset = level_num * LEVEL_INFO_SIZE
    info = level_info[offset:offset + LEVEL_INFO_SIZE]
    entrance_room = info[0x2F]
    stairway_data_raw = bytes(info[0x34:0x3E])
    staircase_room_pool = _staircase_room_pool(level_num, stairway_data_raw)
    room_nums, staircase_slots = _owned_cells(entrance_room, staircase_room_pool, block, _block_tables(grid_data))
    level = Level(
        level_num=level_num,
        entrance_room=entrance_room,
        entrance_direction=_entrance_direction(stairway_data_raw),
        palette_raw=bytes(info[0x00:0x24]),
        fade_palette_raw=bytes(info[0x7C:0xDC]),
        staircase_room_pool=staircase_room_pool,
        room_nums=room_nums,
        staircase_nums=sorted(staircase_slots),
        block=block,
        boss_room=info[0x3E],
        enemy_sprite_set=VANILLA_ENEMY_SPRITE_SETS[level_num],
        boss_sprite_set=VANILLA_BOSS_SPRITE_SETS[level_num],
        start_y=info[0x28],
        item_position_table=list(info[0x29:0x2D]),
        map_start=info[0x2D],
        map_cursor_offset=info[0x2E],
        map_data=bytes(info[0x3F:0x4F]),
        map_ppu_commands=bytes(info[0x4F:0x7C]),
        qty_table=list(info[0x24:0x28]),
        stairway_data_raw=stairway_data_raw,
        rom_level_num=info[0x33],
        screen_status_ram_offset=bytes(info[0x31:0x33]),
        triforce_room_ptr=info[0x30],
    )
    if level.entrance_room not in room_nums:
        raise RuntimeError(
            f"L{level_num}: entrance_room 0x{entrance_room:02X} is not present in "
            f"the rooms the flood fill found for the level — its level data may be malformed. "
            f"Known room nums: {sorted(f'0x{n:02X}' for n in room_nums)}"
        )
    return level


def _staircase_room_pool(level_num: int, stairway_data_raw: bytes) -> list[int]:
    """The stairway list up to its $FF end marker."""
    staircase_room_pool: list[int] = []
    for b in stairway_data_raw:
        if b == STAIRWAY_LIST_END:
            break
        staircase_room_pool.append(b)
    if level_num == 3 and len(staircase_room_pool) == 0:
        staircase_room_pool.append(LEVEL_3_STAIRWAY_FALLBACK)
    return staircase_room_pool


def _entrance_direction(stairway_data_raw: bytes) -> Direction:
    """Byte 61 ($6BBB) of the LevelInfo block stores the entrance direction
    enum (1=N, 2=S, 3=E, 4=W). In vanilla ROMs this slot is unset (0xFF or
    part of the stairway list), so we apply the visualizer's vanilla-format
    detection convention: if the last byte of the stairway list is not in
    1..4, treat as vanilla and default to Side.SOUTH."""
    return _DIR_BYTE_TO_DIRECTION.get(stairway_data_raw[-1], Direction.SOUTH)


def _owned_cells(entrance_room: int, staircase_room_pool: list[int], block: LevelBlock,
                 t: list[bytes]) -> tuple[list[int], set[int]]:
    """The level's rooms and staircases: the flood fill from its entrance.

    SH-STAIR-12/13: a stairway-pool cell is a real staircase only if its
    layout byte is actually $3E/$3F. Stale leftovers (the pool cell keeps
    ordinary room data) are treated as ordinary rooms for connectivity and
    are excluded from staircase_rooms; only the first live entry per cell
    counts."""
    staircase_slots = {rn for rn in staircase_room_pool if (t[3][rn] & 0x3F) in _STAIRCASE_LAYOUTS}
    stale_pool_cells = set(staircase_room_pool) - staircase_slots
    reachable = _flood_fill_level_rooms(entrance_room, staircase_slots, t)
    regular_room_slots = (reachable - staircase_slots) | (stale_pool_cells & reachable)
    # A cell with a staircase layout is never an ordinary room, even when
    # the flood reaches it (another level's staircase).
    room_nums = sorted(n for n in regular_room_slots if isinstance(block[n], Room))
    return room_nums, staircase_slots


def _parse_level(
    level_num: int,
    grid_data: bytes,
    block: LevelBlock,
    bins: RawBinFiles,
    level_info: bytes | None = None,
) -> Level:
    level = _parse_single_level(
        level_num=level_num,
        grid_data=grid_data,
        block=block,
        level_info=level_info if level_info is not None else bins.level_info,
    )
    level.enemy_sprite_set = _parse_enemy_sprite_set(bins, level_num)
    level.boss_sprite_set = _parse_boss_sprite_set(bins, level_num)
    return level
