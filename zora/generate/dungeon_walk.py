"""The inventory walk of a level (VA-REJ-17/18): which rooms a player holding
given items can enter and through which sides. The acceptance check and the
hint text both use it."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from ..model.enums import Item, RoomAction, RoomType, Side
from ..model.levels import GANON_LIST, L9_ENTRY_PERSON_LIST, MERCHANT_LIST, ZELDA_LIST, Level
from ..model.room_grid import neighbour
from ..model.rooms import (
    DIAMOND_STAIRS_PUSH,
    ITEM_MASK,
    NO_ITEM_CODE,
    PERSON_LAYOUT_BYTE,
    PUSH_BLOCK_VARIANT,
    TURNSTILE_PUSH,
    Room,
    StaircaseRoom,
)
from .late_gate.walk import level9_entry_room
from .shapes.world import D_SHUTTER, D_WALL

SHUTTERS_OPEN_TRIGGERS = frozenset({RoomAction.ALL_DEAD, RoomAction.ALL_DEAD_ITEM, RoomAction.BLOCK_DOOR,
                                    RoomAction.MONEY_OR_LIFE})                    # VA-WALK-03
SIDES = (Side.NORTH, Side.EAST, Side.SOUTH, Side.WEST)


def arrival_accepts(layout: int, was_entered: bool, sides: set[int]) -> bool:
    """VA-REJ-17's arrival rule, by the layout's low six bits."""
    if not was_entered:
        return False
    if layout == RoomType.HORIZONTAL_MOAT_ROOM:
        return bool(sides & {Side.SOUTH, Side.WEST, Side.EAST})
    if layout == RoomType.VERTICAL_CHUTE_ROOM:
        return bool(sides & {Side.NORTH, Side.SOUTH})
    if layout in (RoomType.HORIZONTAL_CHUTE_ROOM, RoomType.DOUBLE_MOAT_ROOM):
        return bool(sides & {Side.WEST, Side.EAST})
    if layout == RoomType.T_ROOM:
        return Side.SOUTH in sides and bool(sides & {Side.NORTH, Side.WEST, Side.EAST})
    if layout == RoomType.VERTICAL_MOAT_ROOM:
        return bool(sides & {Side.NORTH, Side.SOUTH, Side.WEST})
    if layout == RoomType.LAVA_MOAT:
        return bool(sides & {Side.NORTH, Side.EAST}) and bool(sides & {Side.SOUTH, Side.WEST})
    return True


# --- VA-REJ-17: the family lists ----------------------------------------------

MONSTER_VALUE_FLAG = 0x80          # the layout byte's bit 7, as bit 7 of the value
MIXED_LIST_BASE = 0x40             # list ID $40 + n appears as the value $80 + n
POLS_VOICE = 0x16
# The sword list's group values: $80 + (G - $40) for each group list G in
# $62-$7F whose members include Pols Voice. VA-REJ-17 reads them from the
# group table at the time of the check; these are PRG0's (groups $70, $78;
# tests/test_acceptance.py derives them). The sword list never blocks under
# the check's start set, so the staged group table is not consulted.
PRG0_POLS_VOICE_GROUP_VALUES = frozenset({0xB0, 0xB8})


@dataclass(frozen=True)
class FamilyList:
    """One VA-REJ-17 list: the monster values it blocks, and the item sets
    any one of which unblocks it (each set must be held whole)."""
    name: str
    values: frozenset[int]
    unblocked_by: tuple[frozenset[int], ...]

    def blocks(self, value: int, held: frozenset[int]) -> bool:
        return value in self.values and not any(items <= held for items in self.unblocked_by)


def group_value(group: int) -> int:
    """A mixed-group list ID as a monster value: bit 6 of the ID is the
    layout byte's bit 7, so $40 + n appears as $80 + n."""
    return MONSTER_VALUE_FLAG + (group - MIXED_LIST_BASE)


def pols_voice_group_values(groups: Mapping[int, Iterable[int]]) -> frozenset[int]:
    """The sword list's group values from group lists (list ID -> members)."""
    return frozenset(group_value(group) for group, members in groups.items() if POLS_VOICE in members)


FAMILY_LISTS = (
    FamilyList("recorder", frozenset({0x38, 0x39}), (frozenset({Item.RECORDER}),)),     # Digdogger
    FamilyList("bow", frozenset({0x33, 0x34}), (frozenset({Item.BOW}),)),               # Gohma
    # Zelda and Ganon: unblocked only when the bow AND the silver arrow are held
    FamilyList("arrow", frozenset({ZELDA_LIST, GANON_LIST}), (frozenset({Item.BOW, Item.SILVER_ARROWS}),)),
    # Gleeok, Patra, Pols Voice and the groups holding Pols Voice; the wand
    # unblocks it too, which never matters while the wooden sword is held
    FamilyList("sword", frozenset({0x82, 0x83, 0x84, 0x85, 0x87, 0x88, POLS_VOICE})
               | PRG0_POLS_VOICE_GROUP_VALUES,
               (frozenset({Item.WOOD_SWORD}), frozenset({Item.WAND}))),
)
FamilyLists = tuple[FamilyList, ...]


def family_items(family_lists: FamilyLists) -> frozenset[int]:
    """The held items that can change a family list's answer (the walk's cache key)."""
    return frozenset().union(*(items for family_list in family_lists for items in family_list.unblocked_by))


FAMILY_ITEMS = family_items(FAMILY_LISTS)


def monster_value(room: Room) -> int:
    """VA-REJ-17: the monster byte's low six bits, plus $80 when the layout
    byte's bit 7 is set (the count bits are ignored)."""
    return room.monster_list | (MONSTER_VALUE_FLAG if room.has_monster_bit else 0)


def is_family_blocked(room: Room, held: frozenset[int], family_lists: FamilyLists = FAMILY_LISTS) -> bool:
    """VA-REJ-07 (iii) / VA-REJ-17: the room's monster value is on a family
    list whose unblocking item is not held. family_lists: VA-REJ-17's, or the
    progressive items' (acceptance_check.logic_rules)."""
    value = monster_value(room)
    return any(family_list.blocks(value, held) for family_list in family_lists)


def item_code(item: Item) -> int:
    """An item as the walk compares it: its five-bit code ($03 is "no item")."""
    return NO_ITEM_CODE if item == Item.NOTHING else item.value & ITEM_MASK


@dataclass
class Walk:
    """What a walk entered: each room with the sides it was entered by (a
    step, not a turn; STAIRS for a stair arrival), and the item cellars it
    reached."""
    reached: dict[int, set[int]] = field(default_factory=dict)
    cellars: set[int] = field(default_factory=set)

    def accepts(self, level: Level, room: int) -> bool:
        """VA-REJ-17's arrival rule for a target room."""
        return room in self.reached and arrival_accepts(
            level.block.room(room).room_type, True, self.reached[room]
        )


# --- VA-REJ-18: the entry-side rule --------------------------------------------

STAIRS = 4                         # the fifth side, X: the room's staircase
ALL_SIDES = (Side.NORTH, Side.EAST, Side.SOUTH, Side.WEST, STAIRS)
OPPOSITE: dict[int, int] = {**{side: side.opposite for side in Side}, STAIRS: STAIRS}
PERSON_ROW_MONSTER_LIMIT = 0x20    # a person room's C byte over $20 does not restrict
TRAP_MONSTER_BYTES = frozenset({0x09, 0x0A})
TRAP_MONSTER_LISTS = frozenset({0x2D, 0x2E, 0x36, 0x37})
# VA-WALK-04: stairs usable even while the room is blocked
BLOCKED_USABLE_STAIR_LAYOUTS = frozenset({RoomType.NARROW_STAIR_ROOM, RoomType.SPIRAL_STAIR_ROOM})

Row = dict[int, frozenset[int]]    # entry side -> the sides the room may turn to


def _row(by_n: str, by_s: str, by_w: str, by_e: str, by_x: str) -> Row:
    """A VA-REJ-18 table line, its cells written as side letters."""
    letters = {"N": Side.NORTH, "S": Side.SOUTH, "W": Side.WEST, "E": Side.EAST, "X": STAIRS}
    cells = (by_n, by_s, by_w, by_e, by_x)
    return {side: frozenset(letters[letter] for letter in cell if letter != "-")
            for side, cell in zip((Side.NORTH, Side.SOUTH, Side.WEST, Side.EAST, STAIRS), cells, strict=True)}


VERTICAL_CHUTE_ROW = _row("S", "N", "-", "-", "E")             # $0E, $4E
HORIZONTAL_CHUTE_ROW = _row("-", "-", "E", "W", "N")           # $0F, $4F
T_ROOM_ROW = _row("NWEX", "S", "NWEX", "NWEX", "NWEX")         # $12
ZELDA_ROOM_ROW = _row("S", "-", "S", "S", "S")                 # $27
LAVA_MOAT_ROW = _row("E", "-", "-", "N", "-")                  # $0B, ladder not held
LAVA_MOAT_LADDER_ROW = _row("E", "W", "S", "N", "-")           # $0B, ladder held
PERSON_ROW = _row("N", "SWEX", "SWEX", "SWEX", "SWEX")         # $A6
TURNSTILE_PUSH_ROW = _row("W", "E", "N", "S", "-")             # $60
STRAIGHT_THROUGH_ROW = _row("N", "S", "W", "E", "-")           # $16; $14 with traps
HORIZONTAL_MOAT_ROW = _row("N", "SWEX", "SWEX", "SWEX", "SWEX")  # $18
VERTICAL_MOAT_ROW = _row("NSWX", "NSWX", "NSWX", "E", "NSWX")  # $13
DOUBLE_MOAT_ROW = _row("-", "-", "E", "W", "-")                # $19
POINTLESS_MOAT_ROW = _row("NSWE", "NSWE", "-", "-", "-")       # $15 with traps
ALWAYS_ROWS: dict[int, Row] = {
    RoomType.VERTICAL_CHUTE_ROOM: VERTICAL_CHUTE_ROW,
    RoomType.VERTICAL_CHUTE_ROOM | PUSH_BLOCK_VARIANT: VERTICAL_CHUTE_ROW,
    RoomType.HORIZONTAL_CHUTE_ROOM: HORIZONTAL_CHUTE_ROW,
    RoomType.HORIZONTAL_CHUTE_ROOM | PUSH_BLOCK_VARIANT: HORIZONTAL_CHUTE_ROW,
    RoomType.T_ROOM: T_ROOM_ROW,
    RoomType.ZELDA_ROOM: ZELDA_ROOM_ROW,
    TURNSTILE_PUSH: TURNSTILE_PUSH_ROW,
}
LADDERLESS_ROWS: dict[int, Row] = {
    RoomType.CHEVY_ROOM: STRAIGHT_THROUGH_ROW,
    RoomType.HORIZONTAL_MOAT_ROOM: HORIZONTAL_MOAT_ROW,
    RoomType.VERTICAL_MOAT_ROOM: VERTICAL_MOAT_ROW,
    RoomType.DOUBLE_MOAT_ROOM: DOUBLE_MOAT_ROW,
}
LADDERLESS_TRAP_ROWS: dict[int, Row] = {
    RoomType.CIRCLE_MOAT_ROOM: STRAIGHT_THROUGH_ROW,
    RoomType.POINTLESS_MOAT_ROOM: POINTLESS_MOAT_ROW,
}


def has_trap_monsters(room: Room) -> bool:
    """VA-REJ-18's trap monster list: the layout byte's bit 7 is set and the
    C byte is $09 or $0A, or has low six bits $2D, $2E, $36 or $37."""
    return room.has_monster_bit and (room.monster_byte in TRAP_MONSTER_BYTES
                                     or room.monster_list in TRAP_MONSTER_LISTS)


def entry_row(room: Room, is_level9_entry: bool, has_ladder: bool) -> Row | None:
    """VA-REJ-18: the room's table line, the first that fits; None is the
    default row ("all" for every entry side)."""
    code = room.layout_code                      # the layout byte's low seven bits
    if room.layout_byte == PERSON_LAYOUT_BYTE:
        unrestricted = (room.monster_byte == MERCHANT_LIST
                        or (room.monster_byte == L9_ENTRY_PERSON_LIST and is_level9_entry)
                        or room.monster_byte > PERSON_ROW_MONSTER_LIMIT)
        return None if unrestricted else PERSON_ROW
    if code in ALWAYS_ROWS:
        return ALWAYS_ROWS[code]
    if code == RoomType.LAVA_MOAT:
        return LAVA_MOAT_LADDER_ROW if has_ladder else LAVA_MOAT_ROW
    if has_ladder:
        return None                              # the ladder lifts every "ladder not held" line
    if code in LADDERLESS_ROWS:
        return LADDERLESS_ROWS[code]
    if code in LADDERLESS_TRAP_ROWS and has_trap_monsters(room):
        return LADDERLESS_TRAP_ROWS[code]
    return None


def are_stairs_usable(room: Room, is_blocked: bool) -> bool:
    """VA-WALK-03/04 (W1, A58): stairs work in the $1B and $1C layouts (both
    high bits of the layout byte ignored), the $5A layout (the monster bit
    ignored) and trigger-5 rooms. A family-blocked room's stairs are
    unusable except in the $1B and $1C layouts; a blocked $5A or trigger-5
    room's stairs are unusable (VA-REJ-17 bullet 2, VA-REJ-18)."""
    if room.room_type in BLOCKED_USABLE_STAIR_LAYOUTS:
        return True
    return not is_blocked and (room.layout_code == DIAMOND_STAIRS_PUSH
                            or room.room_action == RoomAction.BLOCK_STAIRS)


def stair_partners(level: Level, room: int, staircases: list[StaircaseRoom]) -> list[int]:
    """Where the room's staircase leads: the item cellars it houses, and the
    level's rooms at the other end of its transport staircases. staircases:
    the block's (level.block.staircases; the walk reads the list once)."""
    partners = []
    for stair in staircases:
        if stair.room_type == RoomType.ITEM_STAIRCASE:
            if stair.return_dest == room:
                partners.append(stair.room_num)
        elif room in (stair.left_exit, stair.right_exit):
            other = stair.right_exit if room == stair.left_exit else stair.left_exit
            if other is not None and other in level.room_nums:
                partners.append(other)
    return partners


def walk_level(level: Level, held: frozenset[int], is_last_boss_open: bool,
               uses_families: bool, target: int | None = None, uses_entry_sides: bool = True,
               family_lists: FamilyLists = FAMILY_LISTS) -> Walk:
    """VA-REJ-17/18's inventory walk over (room, side) pairs, from the start
    room entered by its south side. A pair steps out through its own side
    (rule 1) and turns to the sides its room's row allows (rule 2); item
    cellars are entered over their stair link and have no exits (rule 3);
    the target is entered but never turned in or stepped out of (rule 4).
    Locked and bombable sides pass; a family-blocked room keeps its
    shutters closed and its stairs unusable.

    uses_entry_sides=False is the plain walk of VA-WALK (E3): every row is
    "all", and an accepted target is explored through."""
    room_numbers = set(level.room_nums)
    block = level.block
    staircases = block.staircases
    start = level.entrance_room
    level9_entry = level9_entry_room(level)         # VA-WALK-08, as the gate reads it
    has_ladder = Item.LADDER in held
    result = Walk()
    exits_of: dict[int, dict[int, list[int]]] = {}

    def exits(room: int) -> dict[int, list[int]]:
        """VA-WALK-02..06: the rooms behind each of the room's exits."""
        if room in exits_of:
            return exits_of[room]
        here = block.room(room)
        is_blocked = uses_families and is_family_blocked(here, held, family_lists)
        are_shutters_open = not is_blocked and (
            room == level9_entry or here.room_action in SHUTTERS_OPEN_TRIGGERS
            or (here.room_action == RoomAction.LAST_BOSS and is_last_boss_open)
        )
        found: dict[int, list[int]] = {}
        for side in SIDES:
            if side == Side.EAST and here.layout_code == RoomType.NARROW_STAIR_ROOM:
                continue
            door = here.walls[side.direction]
            if door == D_WALL or (door == D_SHUTTER and not are_shutters_open):
                continue
            behind = neighbour(room, side)
            if behind is not None and behind in room_numbers:
                found[side] = [behind]
        if are_stairs_usable(here, is_blocked):
            partners = stair_partners(level, room, staircases)
            if partners:
                found[STAIRS] = partners
        exits_of[room] = found
        return found

    seen: set[tuple[int, int]] = set()
    stack: list[tuple[int, int]] = []

    def arrive(room: int, side: int) -> None:
        result.reached.setdefault(room, set()).add(side)
        if room not in room_numbers:
            result.cellars.add(room)
            return
        if room == target and (uses_entry_sides or not result.accepts(level, room)):
            return
        if (room, side) not in seen:
            seen.add((room, side))
            stack.append((room, side))

    arrive(start, Side.SOUTH)
    while stack:
        room, side = stack.pop()
        room_exits = exits(room)
        row = entry_row(block.room(room), room == level9_entry, has_ladder) if uses_entry_sides else None
        turns = room_exits.keys() if row is None else row[side] & room_exits.keys()
        for turn in turns:
            if (room, turn) not in seen:
                seen.add((room, turn))
                stack.append((room, turn))
        for behind in room_exits.get(side, ()):
            arrive(behind, OPPOSITE[side])
    return result


def item_room(level: Level, item: int) -> int | None:
    """The level's first room, in room order, holding the item."""
    return next((room.room_num for room in level.rooms if item_code(room.item) == item), None)


def item_cellar(level: Level, item: int) -> int | None:
    """The first item cellar, in room order, that holds the item and returns
    to one of the level's rooms."""
    return next((stair.room_num for stair in level.block.staircases
                 if stair.room_type == RoomType.ITEM_STAIRCASE and stair.item is not None
                 and item_code(stair.item) == item and stair.return_dest in level.room_nums), None)
