"""Where a dungeon room may hold its item: not on a square the game draws as a block, a statue or a
staircase (ZORA's rule, beyond the spec; docs/deviations.md "Items on blocked squares").

A room's item stands at one of its level's four item positions (`item_position_table`, packed $XY
in squares of 16 pixels; the play area is X $2-$D, Y $6-$C). FLOORS is every underworld layout's
floor as the game draws it (zora/rom/parse/room_layouts.py reads it from the ROM, and
tests/test_item_spots.py keeps this table equal to it): 12 columns, one string per row from the
top, each square

    .  floor ($74)       :  sand ($68)       _  black ($24)      ~  water ($F4)
    B  block ($B0)       S, s  the two statues ($94, $B4)        X  a staircase ($70)

Floor, sand and black are walkable; an item on water is collected with the ladder, as the
original game's level 5 key over the river in room $34 (and the spec's own T5 row for layout $18,
spot $C8). Blocks and statues are not walkable, and an item on a staircase sits where the stairs
take Link down: those three hold no item. Every item of the original game's two quests (216
rooms) stands on a walkable or water square. The push-block variant (layout + $40) draws the
same floor, its block one of the layout's own.

The spec's shapes generator places items only on T5's positions (SH-ROOM-11, -16), all of them on
such squares but layout $18's $C8 (water). Add L4 Sword (ZORA) took a level-9 room's position as
it stood, which T5 never checked for a room without an item: on 34 of 999 random configurations
the sword stood on a block or a staircase (2026-10-22). check_item_spots now rejects any such
attempt, whatever placed the item."""
from __future__ import annotations

from ..model.enums import Item, ItemPosition
from ..model.levels import Level
from ..model.rooms import Room
from .errors import GenerationFailure

FLOORS: dict[int, tuple[str, ...]] = {
    0x00: ("............", "............", "............", "............",
           "............", "............", "............"),
    0x01: ("............", "............", "..B......B..", ".B........B.",
           "..B......B..", "............", "............"),
    0x02: ("............", "............", "..B......B..", "............",
           "..B......B..", "............", "............"),
    0x03: ("............", "..B......B..", "............", "............",
           "............", "..B......B..", "............"),
    0x04: (".......BBBBB", ".........BBB", "..........BB", "............",
           "..........BB", ".........BBB", ".......BBBBB"),
    0x05: ("BBBBB..BBBBB", "BBBB....BBBB", "BB........BB", "............",
           "............", "..B......B..", "............"),
    0x06: ("............", "............", "............", ".B........B.",
           "............", "...B....B...", "S..........s"),
    0x07: ("............", ".BBBBBBBBBB.", "............", ".BBBBBBBBBB.",
           "............", ".BBBBBBBBBB.", "............"),
    0x08: ("............", ".BBBBBBBBBB.", "..........B.", "..........B.",
           "..........B.", ".BBBBBBBBBB.", "............"),
    0x09: ("............", "..BBBBBBBB..", "..B......B..", "..B......B..",
           "..B......B..", "..BBBBBBBB..", "............"),
    0x0A: ("............", "............", "............", "....B..B....",
           "............", "............", "............"),
    0x0B: (".~~.........", ".~~~~~~~~~~.", ".~~~~~~~~~~.", ".~.......~~.",
           ".~~......~~.", ".~~......~~.", ".~~......~~."),
    0x0C: (".B.B........", ".B.BBB.BBB..", ".B...B...BBB", ".B.B.B...B..",
           ".BBB.B...B..", ".....B.B.B.B", "..B....B...B"),
    0x0D: ("............", ".B.B.BB.B.B.", "............", ".B.B.BB.B.B.",
           "............", ".B.B.BB.B.B.", "............"),
    0x0E: ("....B..B....", "....B..B....", "....B..B....", "....B..B....",
           "....B..B....", "....B..B....", "....B..B...."),
    0x0F: ("............", "............", "BBBBBBBBBBBB", "............",
           "BBBBBBBBBBBB", "............", "............"),
    0x10: ("............", ".B.B.BB.B.B.", ".B.B.BB.B.B.", ".B.B.BB.B.B.",
           ".B.B.BB.B.B.", ".B.B.BB.B.B.", "............"),
    0x11: ("..B........B", ".B...B....B.", "....B....B..", "...B....B...",
           "..B....B....", ".B....B...B.", "B........B.."),
    0x12: ("............", ".~~~~~~~~~~.", ".~~~~~~~~~~.", ".~~......~~.",
           ".~~......~~.", ".~~~~..~~~~.", ".~~~~..~~~~."),
    0x13: ("........~...", "........~...", "........~...", "........~...",
           "........~...", "........~...", "........~..."),
    0x14: ("............", ".~~~~~~~~~~.", ".~........~.", ".~........~.",
           ".~........~.", ".~~~~~~~~~~.", "............"),
    0x15: ("............", ".~~~....~~~.", ".~........~.", ".~.~~~~~~.~.",
           ".~........~.", ".~~~....~~~.", "............"),
    0x16: ("~~~~~..~~~~~", "~...~~~~...~", "~.~~~..~~~.~", "..~......~..",
           "~.~~~..~~~.~", "~...~~~~...~", "~~~~~..~~~~~"),
    0x17: ("~~~~~..~~~~~", "~...~....~.~", "~.~.~.~~.~.~", "..~.~..~.~..",
           "~.~.~~.~.~.~", "~.~....~...~", "~~~~~..~~~~~"),
    0x18: ("............", "............", "~~~~~~~~~~~~", "............",
           "............", "............", "............"),
    0x19: ("............", "~~~~~~~~~~~~", "............", "............",
           "............", "~~~~~~~~~~~~", "............"),
    0x1A: ("............", "......B.....", ".....B.B....", "....B.X.B...",
           ".....B.B....", "......B.....", "............"),
    0x1B: ("........BBBB", "........BBBB", ".........BBB", "...........X",
           ".........BBB", "........BBBB", "........BBBB"),
    0x1C: ("..........B.", ".BBBBBBBB.B.", ".B.....XB.B.", ".B...BBBB.B.",
           ".B........B.", ".BBBBBBBBBB.", "............"),
    0x1D: ("............", "............", "..BB....BB..", "..BB....BB..",
           "..BB....BB..", "............", "............"),
    0x1E: ("............", "............", ".....BB.....", ".....BB.....",
           ".....BB.....", "............", "............"),
    0x1F: ("............", ".BB......BB.", "............", ".....BB.....",
           "............", ".BB......BB.", "............"),
    0x20: ("BBBBB..BBBBB", "BBBBBB.BBBBB", "BBBBBB.BBBBB", "......B.....",
           "BBBBBB.BBBBB", "BBBBBB.BBBBB", "BBBBB..BBBBB"),
    0x21: ("............", ".S..S..s..s.", "............", ".S..S..s..s.",
           ".....::.....", ".S.:S::s:.s.", "...::::::..."),
    0x22: ("............", "............", "............", ".....B......",
           "............", "............", "............"),
    0x23: ("............", "............", "............", "....S..s....",
           "............", "............", "............"),
    0x24: ("S..........s", "............", "............", "............",
           "............", "............", "S..........s"),
    0x25: ("::::::::::::", "::::::::::::", "::::::::::::", "::::::::::::",
           "::::::::::::", "::::::::::::", "::::::::::::"),
    0x26: ("____________", "____________", "____________", "____________",
           "____________", "____________", "____________"),
    0x27: ("BBBBBBBBBBBB", "B...B__B...B", "B.BB____BB.B", "B.BB____BB.B",
           "B...S..s...B", "B..........B", "B.S......s.B"),
    0x28: ("S__......__s", "__.._.._..__", "__.__..__.__", "__.__..__.__",
           "__...__...__", "____....____", "S___....___s"),
    0x29: ("............", ".BBBBBBBBBB.", ".B..S..s..B.", ".B.S....s.B.",
           ".B........B.", ".BBBB..BBBB.", "............"),
}
LAYOUT_ID_MASK = 0x3F            # the push-block variant draws its layout's floor
FIRST_COLUMN_X, FIRST_ROW_Y = 0x2, 0x6
SPOT_X_SHIFT, SPOT_Y_MASK = 4, 0x0F
NO_ITEM_SQUARES = frozenset("BSsX")
MISPLACED_FAILURE = "item spots: an item on a block, statue or staircase"


def square_at(layout_code: int, spot: int) -> str | None:
    """The square under a packed $XY item position in the layout, None outside the play area."""
    column, row = (spot >> SPOT_X_SHIFT) - FIRST_COLUMN_X, (spot & SPOT_Y_MASK) - FIRST_ROW_Y
    rows = FLOORS.get(layout_code & LAYOUT_ID_MASK)
    if rows is None or not (0 <= row < len(rows) and 0 <= column < len(rows[row])):
        return None
    return rows[row][column]


def is_item_spot(layout_code: int, spot: int) -> bool:
    square = square_at(layout_code, spot)
    return square is not None and square not in NO_ITEM_SQUARES


def item_spot_positions(level: Level, room: Room) -> list[ItemPosition]:
    """The level's item positions where this room may hold its item, in table order."""
    return [ItemPosition(index) for index, spot in enumerate(level.item_position_table)
            if is_item_spot(room.layout_code, spot)]


def misplaced_items(levels: list[Level]) -> list[tuple[Level, Room]]:
    """Every level room holding an item on a square that holds none."""
    return [(level, room) for level in levels for room in level.rooms
            if room.item != Item.NOTHING
            and not is_item_spot(room.layout_code, level.item_position_table[room.item_position])]


def check_item_spots(levels: list[Level]) -> None:
    """The validation step: an attempt with any item on a block, statue or staircase restarts."""
    misplaced = misplaced_items(levels)
    if misplaced:
        rooms = ", ".join(f"level {level.level_num} room ${room.room_num:02X}" for level, room in misplaced)
        raise GenerationFailure(f"{MISPLACED_FAILURE} ({rooms})")
