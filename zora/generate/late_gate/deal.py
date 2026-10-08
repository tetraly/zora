"""VA-REJ-03 steps 1-3: re-deal a level's room contents, its staircase exits and
its internal door pairs."""

from zora.generate.late_gate.blocks import _room_table, _rooms
from zora.generate.rng import Rng
from zora.generate.shapes.world import D_WALL, GRID_COLS, GRID_ROWS, WITHOUT_HIGH_COUNT_BIT
from zora.model import room_grid
from zora.model.enums import RoomAction, RoomType, Side
from zora.model.levels import L9_ENTRY_PERSON, L9_ENTRY_PERSON_LIST, LEVEL_9, MERCHANT_LIST, ZELDA_LIST, Level
from zora.model.rooms import DoorPair, Room, StaircaseRoom

_SEAT_RULED = frozenset({RoomType.T_ROOM, RoomType.ZELDA_ROOM, RoomType.HORIZONTAL_CHUTE_ROOM,
                         RoomType.VERTICAL_CHUTE_ROOM})   # whole layout bytes


SWAP_DRAW_LIMIT = 1000


def _redeal_rooms(level: Level) -> list[Room]:
    """VA-REJ-03 step 1 list P: the level's rooms in grid order, skipping
    the Entrance room (layout byte without the monster bit = $21) and, in
    level 9, the room holding person code $4B (by content, not position).
    Nothing else is skipped: Zelda's content moves with the deal."""
    return [room for room in _rooms(level)
            if room.layout_code != RoomType.ENTRANCE_ROOM
            and not (level.level_num == LEVEL_9 and room.enemy == L9_ENTRY_PERSON)]


def _is_safe_seat(layout_byte: int, home: int, room_numbers: set[int]) -> bool:
    """Swap-safety rule for a content with WHOLE layout byte `layout_byte`
    against the OTHER content's home cell (VA-REJ-03 step 1 "The rules")."""
    row, column = room_grid.row(home), room_grid.column(home)
    if layout_byte in (RoomType.T_ROOM, RoomType.ZELDA_ROOM):   # cell below in the level
        return row < GRID_ROWS - 1 and home + 16 in room_numbers
    if layout_byte == RoomType.HORIZONTAL_CHUTE_ROOM:           # cell above in the level
        return row > 0 and home - 16 in room_numbers
    if layout_byte == RoomType.VERTICAL_CHUTE_ROOM:             # not col 0/15, both sides in
        return (0 < column < GRID_COLS - 1 and home - 1 in room_numbers and home + 1 in room_numbers)
    return True


def _redeal_contents(level: Level, rng: Rng) -> dict[int, int] | None:
    """VA-REJ-03 step 1, exact procedure (NOT a uniform shuffle): for
    i = 0..n-1 draw j uniformly from ALL slots, test the pair, swap on pass
    (each content carrying its home cell), redraw on fail; every draw counts
    and past 1,000 draws the attempt is a swap-safety rejection (None).
    On success the contents in slot k are written to room P[k]; returns
    {home cell: new cell} for every moved content.

    A room's contents (VA-REJ-03 step 1) are its monsters, layout, whole
    item byte, whole trigger byte and inner palette; the sides stay with the
    cell. Fast-pathed: the contents move as five references per room."""
    rooms = _redeal_rooms(level)
    count = len(rooms)
    if count == 0:
        return {}
    room_numbers = set(level.room_nums)
    content = [(room.enemy_info, room.layout_info, room.item_info, room.secret_info, room.palette_1)
               for room in rooms]
    layout_bytes = [room.layout_byte for room in rooms]
    cells_in_order = [room.room_num for room in rooms]
    home = list(cells_in_order)
    draw_below = rng.below
    draws = 0
    for slot in range(count):
        while True:
            if draws >= SWAP_DRAW_LIMIT:
                return None
            draws += 1
            other = draw_below(count)
            slot_layout, other_layout = layout_bytes[slot], layout_bytes[other]
            if ((slot_layout not in _SEAT_RULED
                 or _is_safe_seat(slot_layout, home[other], room_numbers))
                    and (other_layout not in _SEAT_RULED
                         or _is_safe_seat(other_layout, home[slot], room_numbers))):
                content[slot], content[other] = content[other], content[slot]
                layout_bytes[slot], layout_bytes[other] = other_layout, slot_layout
                home[slot], home[other] = home[other], home[slot]
                break
    for room, moved_in in zip(rooms, content, strict=True):
        (room.enemy_info, room.layout_info, room.item_info, room.secret_info,
         room.palette_1) = moved_in
    return {home[index]: cells_in_order[index] for index in range(count)}


def _internal_slots(room_numbers: set[int]) -> list[DoorPair]:
    """Each same-level adjacency once as (first, second, axis), the axis Side.EAST or Side.SOUTH."""
    slots: list[DoorPair] = []
    for room_number in sorted(room_numbers):
        for side in Side:
            neighbour = room_grid.neighbour(room_number, side)
            if neighbour is not None and neighbour in room_numbers and room_number < neighbour:
                slots.append(DoorPair(room_number, neighbour, side))
    return slots


# VA-REJ-03 step 3 pin families, switched on one at a time (each needs the
# step-5 forcings and the step-9 walk to be joinable):
#   "drop27"     layout-$27 room: its north, east and west pairs
#   "stair1b"    layout-$1B room: the pair with its right-hand neighbour
#   "l9entrance" level-9 entrance ($21): its east and west pairs
#   "person"     person room ($26 + person flag, no push block; L1-8 codes
#                11-18 except 17, L9 codes 12-18 unless the room above is
#                life-or-money): the pair with the room above
#   "l9zelda"    level 9: Zelda's room next to a $4B person room or the
#                life-or-money room (Ganon must be beaten: always, under
#                the preset): the side between them
PIN_FAMILIES: frozenset[str] = frozenset(
    {"drop27", "stair1b", "l9entrance", "person", "l9zelda"}
)


def _pinned_pairs(level: Level, pairs: list[DoorPair]) -> set[DoorPair]:
    """Door pairs excluded from the step-3 shuffle, identified from the
    contents as they sit after step 1. Layout families match the layout byte
    with the monster bit ignored ($A7 pins like $27, $9B like $1B; push
    variants pin nowhere); the person family is exactly $A6 (A28)."""
    if not PIN_FAMILIES:
        return set()
    level_num = level.level_num
    room_at = _room_table(level.block).__getitem__
    pinned: set[DoorPair] = set()

    def has_plain_layout(room_number: int, layout: int) -> bool:
        return room_at(room_number).layout_code == layout        # the layout, no push block

    for pair in pairs:
        first, second, axis = pair
        # first is the west (axis Side.EAST) or north (axis Side.SOUTH) room of the pair.
        if "drop27" in PIN_FAMILIES:
            if axis == Side.EAST and (has_plain_layout(first, RoomType.ZELDA_ROOM)
                                      or has_plain_layout(second, RoomType.ZELDA_ROOM)):
                pinned.add(pair)
            if axis == Side.SOUTH and has_plain_layout(second, RoomType.ZELDA_ROOM):   # $27 room's north
                pinned.add(pair)
        if ("stair1b" in PIN_FAMILIES and axis == Side.EAST
                and has_plain_layout(first, RoomType.NARROW_STAIR_ROOM)):
            pinned.add(pair)
        if "l9entrance" in PIN_FAMILIES and level_num == LEVEL_9 and axis == Side.EAST:
            if any(room_at(room_number).layout_code == RoomType.ENTRANCE_ROOM
                   for room_number in (first, second)):
                pinned.add(pair)
        if "person" in PIN_FAMILIES and axis == Side.SOUTH:
            below = room_at(second)
            if below.is_person_room and not below.movable_block:
                code = below.monster_list
                if level_num <= 8:
                    pins_person = 11 <= code <= 18 and code != 17
                else:
                    pins_person = (12 <= code <= 18
                                   and room_at(first).room_action != RoomAction.MONEY_OR_LIFE)
                if pins_person:
                    pinned.add(pair)
        if "l9zelda" in PIN_FAMILIES and level_num == LEVEL_9:
            # A34: both rooms matched on the MONSTER BYTE with bit 7 (one
            # count-index bit) ignored, no layout-high-bit test: Zelda $37
            # next to a $0B person or the $11 life-or-money merchant.
            for zelda_room, other_room in ((first, second), (second, first)):
                if (room_at(zelda_room).monster_byte & WITHOUT_HIGH_COUNT_BIT == ZELDA_LIST
                        and room_at(other_room).monster_byte & WITHOUT_HIGH_COUNT_BIT
                        in (L9_ENTRY_PERSON_LIST, MERCHANT_LIST)):
                    pinned.add(pair)
    return pinned


STAIR_EXIT_LAYOUTS = frozenset({RoomType.DIAMOND_STAIR_ROOM, RoomType.NARROW_STAIR_ROOM,
                                RoomType.SPIRAL_STAIR_ROOM})
# the fields of a StaircaseRoom that name its exit rooms
CELLAR_EXIT = "return_dest"
TRANSPORT_EXITS = ("left_exit", "right_exit")


def _stair_slots(level: Level) -> list[tuple[StaircaseRoom, str]]:
    """Exit slots of the level's $3E/$3F rooms — those whose LEFT exit (a
    transport's first room, a cellar's return room) is in the level —
    in stair-cell order."""
    room_numbers = set(level.room_nums)
    slots: list[tuple[StaircaseRoom, str]] = []
    for stair in level.staircase_rooms:
        if stair.room_type == RoomType.ITEM_STAIRCASE:
            if stair.return_dest is not None and stair.return_dest in room_numbers:
                slots.append((stair, CELLAR_EXIT))
        elif stair.left_exit is not None and stair.left_exit in room_numbers:
            slots.extend((stair, attr) for attr in TRANSPORT_EXITS)
    return slots


def _is_shufflable_exit(level: Level, room_num: int | None, room_numbers: set[int]) -> bool:
    if room_num is None or room_num not in room_numbers:
        return False
    room = level.block.room(room_num)
    return room.room_type in STAIR_EXIT_LAYOUTS or room.room_action == RoomAction.BLOCK_STAIRS


# the two sides of an internal pair, by the pair's axis: (first's side, second's side)
_PAIR_SIDES = {Side.EAST: ("east", "west"), Side.SOUTH: ("south", "north")}


def _deal_level(level: Level, rng: Rng) -> list[DoorPair] | None:
    """VA-REJ-03 steps 1-3. Returns the recorded wall pairs, or None for a
    swap-safety rejection (step 1's draw limit)."""
    room_numbers = set(level.room_nums)

    # step 2 (before): uniformly permute the DISTINCT shufflable exit rooms
    # (layout bits 0-5 in {$1A,$1B,$1C}, or trigger 5) and apply it as a
    # room-to-room remap to every exit slot of the $3E/$3F rooms whose LEFT
    # exit is in the level; an exit room referenced by two slots moves as
    # one. Other slots stay pinned.
    slots = _stair_slots(level)
    shufflable = sorted({getattr(stair, attr) for stair, attr in slots
                         if _is_shufflable_exit(level, getattr(stair, attr), room_numbers)})
    if shufflable:
        shuffled = list(shufflable)
        rng.shuffle(shuffled)
        remap = dict(zip(shufflable, shuffled, strict=True))
        for stair, attr in slots:
            room = getattr(stair, attr)
            setattr(stair, attr, remap.get(room, room))
    before = [getattr(stair, attr) for stair, attr in slots]

    # step 1: re-deal room contents (exact draw procedure; walls stay put)
    moved = _redeal_contents(level, rng)
    if moved is None:
        return None

    # step 2 (after): exits follow their rooms into the new cells.
    for (stair, attr), room in zip(slots, before, strict=True):
        setattr(stair, attr, None if room is None else moved.get(room, room))

    # step 3: internal door pairs re-dealt as units (each keeps its own two
    # sides — one-ways arise); east-west pairs shuffle only among east-west
    # positions, north-south among north-south. Pinned pairs are excluded
    # and forced wall/wall (A36): in grid order each takes a free wall/wall
    # unit by SWAP (its own unit joins the shuffle), else is overwritten
    # with walls and its own unit leaves the shuffle; a pinned position
    # already wall/wall keeps it. The pool below is the same multiset the
    # swaps produce, and it is shuffled uniformly. Edge sides are never
    # touched.
    # Fast-pathed: the sides are read and written through the WallSet's
    # field for the pair's axis.
    pairs = _internal_slots(room_numbers)
    pinned = _pinned_pairs(level, pairs)
    walls_of = {room.room_num: room.walls for room in _rooms(level)}
    wall_unit = (D_WALL, D_WALL)
    recorded: list[DoorPair] = []
    free_by_axis: list[list[DoorPair]] = []
    for axis in (Side.EAST, Side.SOUTH):
        first_field, second_field = _PAIR_SIDES[axis]
        group = [pair for pair in pairs if pair.axis == axis]
        units = [(getattr(walls_of[first], first_field), getattr(walls_of[second], second_field))
                 for first, second, _axis in group]
        pool = list(units)
        free = [pair for pair in group if pair not in pinned]
        pins = [(pair, unit) for pair, unit in zip(group, units, strict=True) if pair in pinned]
        # a pinned position already holding wall/wall keeps it; the others
        # take a free wall/wall unit, else give up their own unit.
        for _pair, unit in pins:
            if unit == wall_unit:
                pool.remove(wall_unit)
        for _pair, unit in pins:
            if unit != wall_unit:
                pool.remove(wall_unit if wall_unit in pool else unit)
        for first, second, _axis in (pair for pair, _unit in pins):
            setattr(walls_of[first], first_field, D_WALL)
            setattr(walls_of[second], second_field, D_WALL)
        rng.shuffle(pool)
        for (first, second, _axis), (first_side, second_side) in zip(free, pool, strict=True):
            setattr(walls_of[first], first_field, first_side)
            setattr(walls_of[second], second_field, second_side)
        free_by_axis.append(free)
    # recording order: east-west first then north-south, each in grid
    # order; every re-dealt pair with a wall on either side. Pinned pairs
    # are never recorded.
    for pair in free_by_axis[0] + free_by_axis[1]:
        first_field, second_field = _PAIR_SIDES[pair.axis]
        if (getattr(walls_of[pair.first], first_field) == D_WALL
                or getattr(walls_of[pair.second], second_field) == D_WALL):
            recorded.append(pair)
    return recorded
