"""VA-REJ-03 steps 4-8 (the special-room fixes, placement, Zelda's room), level
9's extras (VA-REJ-01.3) and the tail that runs once all levels are accepted."""

from ...model import room_grid
from ...model.enums import BossSound, Enemy, Item, RoomAction, RoomType, Side, WallType
from ...model.levels import (
    GANON_LIST,
    L9_ENTRY_PERSON,
    L9_ENTRY_PERSON_LIST,
    LEVEL_9,
    ZELDA_LIST,
    Level,
    LevelBlock,
)
from ...model.rooms import (
    DIAMOND_STAIRS_PUSH,
    PUSH_BLOCK_VARIANT,
    TURNSTILE_PUSH,
    DoorPair,
    Room,
    StaircaseRoom,
)
from ..shapes.world import (
    D_BOMB,
    D_KEY1,
    D_KEY2,
    D_OPEN,
    D_SHUTTER,
    D_WALL,
    GRID_COLS,
    GRID_ROWS,
    set_side,
    side_of,
    sides_of,
)
from .blocks import (
    GANON_ITEM,
    LAST_BOSS_SECRET,
    LEVELS_7_TO_9,
    NO_ITEM,
    GateBlock,
    _clear_push_block,
    _room_table,
    _rooms,
    _set_trigger,
)

# A43: the facing side's door-field bits in a room's A (0) / B (1) byte.
_EXIT_FIELD = {Side.NORTH: (0, 0xE0), Side.SOUTH: (0, 0x1C), Side.WEST: (1, 0xE0),
               Side.EAST: (1, 0x1C)}
_RAW_STEP = {Side.NORTH: -16, Side.EAST: +1, Side.SOUTH: +16, Side.WEST: -1}
BLOCK_ROOMS = GRID_COLS * GRID_ROWS


def _shutter_ganon_sides(room: Room) -> None:
    """Ganon's room: every side that is neither a wall nor bombable becomes
    a shutter."""
    for side in Side:
        if side_of(room, side) not in (D_WALL, D_BOMB):
            set_side(room, side, D_SHUTTER)


def _shutter_open_and_locked_sides(room: Room) -> None:
    """The life-or-money room: its open and key sides become shutters."""
    for side in Side:
        if side_of(room, side) in (D_OPEN, D_KEY1, D_KEY2):
            set_side(room, side, D_SHUTTER)


def _has_shutter(room: Room) -> bool:
    return D_SHUTTER in sides_of(room)


def exit_position(exit_layout_codes: tuple[int, int]) -> tuple[int, int]:
    """late-gate.md step 2: a staircase's exit-position byte (X, Y nibbles)
    comes from its two exit rooms' layout bytes without the monster bit —
    $B8 if either is $4E, else $65 if either is $0F, else $69 (the
    SH-STAIR-04 default). A cellar's two exits are its return room."""
    if RoomType.VERTICAL_CHUTE_ROOM | PUSH_BLOCK_VARIANT in exit_layout_codes:
        return 0xB, 0x8
    if RoomType.HORIZONTAL_CHUTE_ROOM in exit_layout_codes:
        return 0x6, 0x5
    return 0x6, 0x9


def _set_exit_positions(block: LevelBlock) -> None:
    """Every staircase's exit position from its exit rooms as they stand."""
    for stair in block.staircases:
        if stair.room_type == RoomType.ITEM_STAIRCASE:
            first = second = stair.return_dest
        else:
            first, second = stair.left_exit, stair.right_exit
        assert first is not None and second is not None
        stair.exit_x, stair.exit_y = exit_position(
            (block.room(first).layout_code, block.room(second).layout_code)
        )


def _clear_exit_bits(stair: StaircaseRoom, table: int, mask: int) -> None:
    """A43: the tail write clears bits of a staircase's exit byte (table 0
    is its A byte, 1 its B byte). The staircase keeps the rooms it leads to
    for the passes that follow (the map move, the acceptance walk, the hint
    probes); the cleared bits are recorded and applied when it is
    serialized (StaircaseRoom.exit_bytes)."""
    if table == 0:
        stair.cleared_a_bits |= mask
    else:
        stair.cleared_b_bits |= mask


def _tail(gate_block: GateBlock) -> None:
    """Once per pass after all nine levels are accepted, over the whole
    block (quest 1 only: the quest-2 half is MAY, omitted — shipped ROMs are
    locked to quest 1): Ganon's-room door shutters on every $3E room;
    life-or-money merchant shutters; each $0B person room with the monster
    high bit opens, for every one of ITS OWN shutter sides, the NEIGHBOUR's
    facing side (north/east/west skipped toward a monster-bit-less Ganon
    room; south never skipped — A30); trigger-4 rooms without a shutter
    lose the push block. Then every staircase's exit position is set from
    its exit rooms (late-gate.md step 2)."""
    # A35: the three door fixes are ONE grid-order sweep, each room taking
    # the FIRST that applies; the trigger-4 push clear is a second sweep.
    block = gate_block.block
    stair_writes: list[tuple[StaircaseRoom, int, int]] = []
    for room in gate_block.owned_rooms:
        if room.enemy == GANON_LIST:
            _shutter_ganon_sides(room)
        elif room.is_person_room and room.room_action == RoomAction.MONEY_OR_LIFE:
            _shutter_open_and_locked_sides(room)
        elif room.monster_byte == L9_ENTRY_PERSON_LIST and room.has_monster_bit:
            for side in Side:
                if side_of(room, side) != D_SHUTTER:
                    continue
                # A42: no level or grid-edge guard — east/west are the rooms
                # numbered one above/below (wrapping across a row end),
                # north/south sixteen below/above, whatever holds them. A
                # top-row north or bottom-row south write falls outside the
                # 128-room table (UNKNOWN in the spec) and is not modelled.
                # A43: the write acts on the raw bytes — on a staircase or
                # item cellar it clears the same bits of its exit bytes; on
                # an unowned cell it clears that side of the walls the
                # shapes stage wrote there (SH-GRID-17).
                neighbour_number = room.room_num + _RAW_STEP[side]
                if not 0 <= neighbour_number < BLOCK_ROOMS:
                    continue
                neighbour_cell = block[neighbour_number]
                if isinstance(neighbour_cell, StaircaseRoom):
                    stair_writes.append((neighbour_cell, *_EXIT_FIELD[side.opposite]))
                    continue
                if side != Side.SOUTH and neighbour_cell.enemy == GANON_LIST:
                    continue
                set_side(neighbour_cell, side.opposite, D_OPEN)
    for room in gate_block.owned_rooms:
        if room.room_action == RoomAction.BLOCK_DOOR and room.movable_block and not _has_shutter(room):
            _clear_push_block(room)
    for stair, table, mask in stair_writes:
        _clear_exit_bits(stair, table, mask)
    _set_exit_positions(block)


def _wipe_boss_sound(level: Level) -> None:
    """Step 4 (A1): clear the boss-sound bits on EVERY room of the level
    before any special-room fixing; step 5 re-marks Ganon's neighbours."""
    for room in _rooms(level):
        if room.item_info.boss_sound != BossSound.NONE:
            room.boss_sound = BossSound.NONE


BOSS_SOUND_20 = 1            # byte-E bit $20 = boss-sound index bit 0


def _first_special_room_fix(gate_block: GateBlock, level: Level) -> None:
    """Step 5, the first special-room fix part, for every room of the level
    in grid order; then (levels 7-9) the level-9 $4B-room and entrance
    forcings, which act on level-9 room numbers."""
    room_numbers = set(level.room_nums)
    for room in _rooms(level):
        if _has_shutter(room) and room.room_action == RoomAction.BLOCK_STAIRS:
            _open_shutters(room)
        if _has_shutter(room) and room.room_action in (RoomAction.NONE, RoomAction.RINGLEADER):
            _set_trigger(room, RoomAction.ALL_DEAD)
        if room.room_action == RoomAction.BLOCK_DOOR and not _has_shutter(room):
            _clear_push_block(room)
        if room.room_action == RoomAction.LAST_BOSS and room.enemy != GANON_LIST:
            _set_trigger(room, RoomAction.ALL_DEAD)
            if room.item == Item.TRIFORCE_OF_POWER:    # whole item byte -> $03
                room.item_info = NO_ITEM
        if room.enemy == GANON_LIST:
            _shutter_ganon_sides(room)
            room.item_info = GANON_ITEM                # $8E
            _set_trigger(room, RoomAction.LAST_BOSS)
            for side in Side:
                neighbour = room_grid.neighbour(room.room_num, side)
                if neighbour is not None and neighbour in room_numbers:
                    beside = level.block.room(neighbour)
                    beside.boss_sound = BossSound(beside.boss_sound | BOSS_SOUND_20)
    if level.level_num in LEVELS_7_TO_9:
        _force_level9_entry(gate_block)


def _force_level9_entry(gate_block: GateBlock) -> None:
    """Step 5's level-9 forcings: the $4B person room's south side open and
    its other sides shutter unless wall; the entrance's own north/south
    open, own east/west wall, and the east/west neighbours' facing sides
    wall (written only on cells that are rooms of the set)."""
    level9 = gate_block.level9
    if level9 is None:
        return
    for room in _rooms(level9):
        if room.enemy == L9_ENTRY_PERSON:
            for side in (Side.NORTH, Side.EAST, Side.WEST):
                if side_of(room, side) != D_WALL:
                    set_side(room, side, D_SHUTTER)
            room.walls.south = D_OPEN
    entrance = next((room for room in _rooms(level9) if room.layout_code == RoomType.ENTRANCE_ROOM), None)
    if entrance is None:
        return
    entrance.walls.north = entrance.walls.south = D_OPEN
    entrance.walls.east = entrance.walls.west = D_WALL
    for side in (Side.EAST, Side.WEST):
        neighbour = room_grid.neighbour(entrance.room_num, side)
        if neighbour is not None and neighbour in gate_block.owned_set:
            set_side(gate_block.room(neighbour), side.opposite, D_WALL)


def _reforce_level9_person_sides(level: Level) -> None:
    """VA-REJ-19: after the repair, the level-9 $4B room's north, east and
    west sides are forced again as step 5 forces them (shutter unless wall).
    The spec leaves the mechanism open (K-3). This one keeps every property
    VA-REJ-19 states: a side that step 6, placement or the repair opened
    ships as a shutter, and an all-wall deal cuts the level's interior off
    (the entrance's east and west sides are walls), so the repair must open
    one of the three pairs and the side becomes a shutter. The repair sets
    the room's trigger to 1 when it opens a pair, which keeps the walk's
    verdict (0 of 5,500 passing level-9 walks changed) and gives the
    finals' trigger split (QUESTIONS #66.2)."""
    if level.level_num != LEVEL_9:
        return
    for room in _rooms(level):
        if room.enemy == L9_ENTRY_PERSON:
            for side in (Side.NORTH, Side.EAST, Side.WEST):
                if side_of(room, side) != D_WALL:
                    set_side(room, side, D_SHUTTER)


def _open_shutters(room: Room) -> None:
    for side in Side:
        if side_of(room, side) == D_SHUTTER:
            set_side(room, side, D_OPEN)


def _open_pair(block: LevelBlock, room_number: int, side: Side, wall_type: WallType = D_OPEN) -> None:
    neighbour = room_grid.neighbour(room_number, side)
    set_side(block.room(room_number), side, wall_type)
    if neighbour is not None:
        set_side(block.room(neighbour), side.opposite, wall_type)


def _second_special_room_fix(gate_block: GateBlock, level: Level,
                             recorded: list[DoorPair]) -> None:
    """Step 6, the second special-room fix part."""
    level_num = level.level_num
    recorded_pairs = set(recorded)
    for room in _rooms(level):
        room_number = room.room_num
        # A45: neither person rule touches level 9's $4B room (monster byte
        # exactly $0B with the monster bit), so step 5's forced shutters stay.
        level9_entry_person = (level_num == LEVEL_9 and room.monster_byte == L9_ENTRY_PERSON_LIST
                               and room.has_monster_bit)
        if room.is_person_room and not level9_entry_person:
            if room.room_action == RoomAction.MONEY_OR_LIFE:
                _shutter_open_and_locked_sides(room)
            else:
                _open_shutters(room)
        # $12 / $27, monster high bit ignored (push variants not): a walled
        # south side with a RECORDED walled pair there opens (both sides).
        if (room.layout_code in (RoomType.T_ROOM, RoomType.ZELDA_ROOM)
                and room.walls.south == D_WALL
                and (room_number, room_number + 16, Side.SOUTH) in recorded_pairs):
            _open_pair(level.block, room_number, Side.SOUTH)
        # Zelda's room; the hungry goriya by content (monster byte exactly
        # $36, layout high bit clear); rooms whose layout byte with the
        # monster bit ignored is $36 (not $76) — shutters opened (A29).
        if (room.enemy == ZELDA_LIST
                or (room.monster_byte == Enemy.HUNGRY_GORIYA and not room.has_monster_bit)
                or room.layout_code == RoomType.LAYOUT_0x36):
            _open_shutters(room)
    # Levels 7-9's block push-block clear: on every level-9 attempt and no
    # other attempt (917a41f step 6).
    if level_num == LEVEL_9:
        _clear_block_push(gate_block)


def _clear_block_push(gate_block: GateBlock) -> None:
    """Every room of the whole 128-room block loses its push block unless
    its trigger is 4 or 5, or its layout byte with the monster bit ignored
    is $5A or $60 ($DA/$E0 protected too; A29)."""
    for room in gate_block.owned_rooms:
        if not room.movable_block:
            continue
        if (room.room_action in (RoomAction.BLOCK_DOOR, RoomAction.BLOCK_STAIRS)
                or room.layout_code in (DIAMOND_STAIRS_PUSH, TURNSTILE_PUSH)):
            continue
        _clear_push_block(room)


def _pair_key(room_number: int, side: Side) -> DoorPair | None:
    neighbour = room_grid.neighbour(room_number, side)
    if neighbour is None:
        return None
    if side in (Side.EAST, Side.SOUTH):
        return DoorPair(room_number, neighbour, side)
    return DoorPair(neighbour, room_number, side.opposite)


class _PlacementGrid:
    """Step 7's view of one level: its rooms by number, the recorded wall pairs
    and the two tests the layout rules use."""

    def __init__(self, level: Level, recorded: list[DoorPair]) -> None:
        self.room_numbers = set(level.room_nums)
        self.recorded_pairs = set(recorded)
        self.block = level.block
        self.room_at = _room_table(self.block).__getitem__

    def is_wall(self, room_number: int, side: Side) -> bool:
        return side_of(self.room_at(room_number), side) == D_WALL

    def same_level_neighbour(self, room_number: int, side: Side) -> int | None:
        neighbour = room_grid.neighbour(room_number, side)
        return neighbour if neighbour is not None and neighbour in self.room_numbers else None

    def try_open(self, room_number: int, side: Side) -> bool:
        """Open a solid wall towards a same-level neighbour where a recorded
        wall pair sits there; True when this rule opened it."""
        if self.same_level_neighbour(room_number, side) is None or not self.is_wall(room_number, side):
            return False
        if _pair_key(room_number, side) not in self.recorded_pairs:
            return False
        _open_pair(self.block, room_number, side)
        return True


def _placement_check(level: Level, recorded: list[DoorPair]) -> bool:
    """Step 7, the placement check (VA-REJ-01.1), per room in grid order:
    (a) head rule and (d) Ganon four-walls test omitted (MAY: never fire);
    (b) other levels skipped; (c) layout tests with their recorded-pair
    openings (A19 masks, A20 priorities); (e) trigger-4 push clear; (f) $60
    copy. The first failing room rejects the attempt."""
    grid = _PlacementGrid(level, recorded)
    for room in _rooms(level):
        if not _is_placeable(grid, room):
            return False
        # (e) trigger-4 push clear, re-run after step 6's shutter changes
        if room.room_action == RoomAction.BLOCK_DOOR and room.movable_block and not _has_shutter(room):
            _clear_push_block(room)
        # (f) $60 copy, on the layout byte re-read after (e), monster bit ignored
        if room.layout_code == TURNSTILE_PUSH:
            _copy_turnstile_sides(grid, room)
    return True


# The first room number of the grid's bottom row: a room there has no room below.
BOTTOM_ROW_START = BLOCK_ROOMS - GRID_COLS


def _is_placeable(grid: _PlacementGrid, room: Room) -> bool:
    """(c): the layout tests, opening recorded wall pairs first where a rule
    allows it (in A20's priority order)."""
    room_number = room.room_num
    is_wall, try_open = grid.is_wall, grid.try_open
    if room.layout_code == RoomType.T_ROOM:
        below = room_number + GRID_COLS if room_number < BOTTOM_ROW_START else None
        return (not is_wall(room_number, Side.SOUTH)
                and not (is_wall(room_number, Side.NORTH) and is_wall(room_number, Side.EAST)
                         and is_wall(room_number, Side.WEST))
                and not (below is not None and below in grid.room_numbers
                         and grid.room_at(below).layout_code == RoomType.HORIZONTAL_CHUTE_ROOM))
    if room.layout_code == RoomType.ZELDA_ROOM:
        try_open(room_number, Side.SOUTH)
        return not is_wall(room_number, Side.SOUTH)
    if room.room_type == RoomType.VERTICAL_CHUTE_ROOM:
        if not try_open(room_number, Side.SOUTH):
            try_open(room_number, Side.NORTH)
        try_open(room_number, Side.EAST)
        try_open(room_number, Side.WEST)
        return (not (is_wall(room_number, Side.NORTH) and is_wall(room_number, Side.SOUTH))
                and not is_wall(room_number, Side.EAST) and not is_wall(room_number, Side.WEST))
    if room.room_type == RoomType.HORIZONTAL_CHUTE_ROOM:
        try_open(room_number, Side.NORTH)
        if not try_open(room_number, Side.EAST):
            try_open(room_number, Side.WEST)
        return (not (is_wall(room_number, Side.EAST) and is_wall(room_number, Side.WEST))
                and not is_wall(room_number, Side.NORTH))
    if room.room_type == RoomType.LAVA_MOAT:
        if not try_open(room_number, Side.NORTH):
            try_open(room_number, Side.EAST)
        return (not (is_wall(room_number, Side.EAST) and is_wall(room_number, Side.NORTH))
                and not (is_wall(room_number, Side.WEST) and is_wall(room_number, Side.SOUTH)))
    return True


def _copy_turnstile_sides(grid: _PlacementGrid, room: Room) -> None:
    """(f): each same-level neighbour's facing non-wall side is copied onto
    this room's side, a shutter as open. Quirk (A21/A31): the zero guard is on
    the ABOVE direction only: room 0 is never copied from above, but it can
    be copied as room 1's left neighbour."""
    for side in Side:
        neighbour = grid.same_level_neighbour(room.room_num, side)
        if neighbour is None or (side == Side.NORTH and neighbour == 0):
            continue
        facing = side_of(grid.room_at(neighbour), side.opposite)
        if facing != D_WALL:
            set_side(room, side, D_OPEN if facing == D_SHUTTER else facing)


def zelda_cell(rooms: list[Room]) -> int | None:
    """Zelda's room: the LAST of the rooms, in block order, holding monster
    list $37 (VA-REJ-01.3), identified by content, any layout."""
    found = [room.room_num for room in rooms if room.enemy == ZELDA_LIST]
    return found[-1] if found else None


def _zelda_rewrite(gate_block: GateBlock, level: Level) -> bool:
    """Step 8 (level 9, Ganon must be beaten — always on under the preset):
    the rewrite around Zelda's room, then the Zelda-room cleanup and the
    block push-block clear again. False = rejected (a trigger-4/5 neighbour
    BELOW a $12 Zelda room)."""
    room_numbers = set(level.room_nums)
    block = gate_block.block
    zelda_number = zelda_cell(_rooms(level))
    if zelda_number is None:
        return True
    zelda = block.room(zelda_number)
    for side in (Side.NORTH, Side.EAST, Side.SOUTH, Side.WEST):
        neighbour = room_grid.neighbour(zelda_number, side)
        if neighbour is None or neighbour not in gate_block.owned_set:
            continue
        beside = block.room(neighbour)
        is_same_level = neighbour in room_numbers
        is_below = side == Side.SOUTH
        # a person room: monster byte exactly $0B; BELOW also requires the
        # layout's monster high bit (A17/A29).
        is_entry_person = beside.monster_byte == L9_ENTRY_PERSON_LIST and (
            not is_below or beside.has_monster_bit
        )
        if is_same_level and is_entry_person:
            _open_pair(block, zelda_number, side, D_WALL)
            continue
        # trigger 4/5: no level check above/left/right (can wall off a
        # level-7/8 neighbour); below is a same-level neighbour.
        if (beside.room_action in (RoomAction.BLOCK_DOOR, RoomAction.BLOCK_STAIRS)
                and (is_same_level or not is_below)):
            _open_pair(block, zelda_number, side, D_WALL)
            if beside.room_action == RoomAction.BLOCK_DOOR:
                _set_trigger(beside, RoomAction.ALL_DEAD)
            if is_below and zelda.room_type == RoomType.T_ROOM:
                return False
            continue
        if is_same_level and side_of(beside, side.opposite) != D_WALL:
            set_side(zelda, side, D_OPEN)
            set_side(beside, side.opposite, D_SHUTTER)
            # the WHOLE trigger byte becomes $03: item-position bits cleared
            # (A33); the push block is left to the cleanup's block clear
            # (A32)
            beside.secret_info = LAST_BOSS_SECRET
            for other_side in Side:
                if other_side != side.opposite and side_of(beside, other_side) == D_SHUTTER:
                    set_side(beside, other_side, D_OPEN)
    _open_shutters(zelda)
    _clear_block_push(gate_block)
    return True


def _level9_extras(gate_block: GateBlock, level: Level) -> bool:
    """VA-REJ-01.3: Zelda (the last $37 room in block order) is not in a
    $0E/$0F corridor without push block whose north AND south are walls;
    and Ganon's room — the FIRST room in block order whose monster byte is
    $3E (trigger-byte bit 7 is always clear in this model) — is entered by
    the boss-alive walk from level 9's start."""
    from .walk import is_ganon_reachable
    block_rooms = gate_block.owned_rooms
    zelda_number = zelda_cell(block_rooms)
    if zelda_number is not None:
        zelda = gate_block.room(zelda_number)
        if (zelda.layout_code in (RoomType.VERTICAL_CHUTE_ROOM, RoomType.HORIZONTAL_CHUTE_ROOM)
                and zelda.walls.north == D_WALL and zelda.walls.south == D_WALL):
            return False
    ganon_number = next((room.room_num for room in block_rooms if room.monster_byte == GANON_LIST), None)
    return is_ganon_reachable(level, ganon_number)
