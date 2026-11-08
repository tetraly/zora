"""The drop-square model's three inferences, checked in the emulator (tests/emulator.py) before any new
drop square is used (Universal Drops v2.0; docs/reports/research-universal-drops-balance.md
section 3.3, "The model").

A test ROM: the PRG0 base with room $45 of the level-1-6 block and its four neighbors made open plain
rooms without monsters, room $45 given the layout under test. Squares are $XY tiles of 16 pixels (an
item at $XY stands at pixel X * 16, Y * 16; Link's square is his X and his Y + 3, the offset the game's
own block test uses).

  - The door squares: through each door Link first stands on the model's door squares, the floor
    squares next to the doorway (north and south: columns $7 and $8 of the top and bottom rows; west
    and east: row $9 at the walls). In the narrow stair room ($1B), whose east door opens onto its
    stairs, entering from the east takes Link down the stairs.
  - The ladder: Link never steps onto water without it; with it he crosses a water strip one square
    wide (vertical moat, $13), but never two squares of water in a row (T room, $12); and with it he
    takes an item standing on water (horizontal moat, $18, at four right one up, $C8).
  - An item under the push block: Remove Most Open Stairs (B30) with Universal Drops v2.0 off leaves
    an item at the center ($89) of the single block room it makes ($62, trigger "push reveals stairs"),
    a square the block can slide onto. Link takes it without pushing; and after pushing the block onto
    it and leaving the room, the item is still there to take.
  - The push block (FindAndCreatePushBlockObject, disassembly Z_05.asm): in every push-block room the
    block is the first block in the middle row (Y $9) from the west wall, or the object stands at $D9
    when that row has none; a push moves it exactly one square, in each direction, and only once."""
from functools import cache

import pytest

from tests.emulator import (
    ITEMS,
    OBJ_STATE,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    ROOM_ITEM_SLOT,
    Button,
    Emulator,
    Mode,
)
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import TAKEN, Console
from zora.generate.item_spots import FLOORS
from zora.model.enums import Enemy, Item, ItemPosition, RoomAction, RoomType, WallType
from zora.model.rooms import PUSH_BLOCK_VARIANT, EnemyInfo, ItemInfo, LayoutInfo, SecretInfo, WallSet
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

pytestmark = [needs_base_rom, pytest.mark.slow]

LEVEL = 1
ROOM = 0x45
NEIGHBORS = {"north": ROOM - 0x10, "south": ROOM + 0x10, "west": ROOM - 1, "east": ROOM + 1}
SQUARE = 0x10                       # pixels per square
LINK_Y_OFFSET = 3                   # UpdateBlock0Idle compares Link's Y + 3 with the block's
WALK_LIMIT = 400
SETTLE_FRAMES = 30
# Link's spot before the door he leaves a neighbor by (toward the room under test), and the button
LEAVE = {"north": (0x78, 0xBD, Button.DOWN), "south": (0x78, 0x5D, Button.UP),
         "west": (0xD0, 0x8D, Button.RIGHT), "east": (0x20, 0x8D, Button.LEFT)}
INTO = {"north": Button.DOWN, "south": Button.UP, "west": Button.RIGHT, "east": Button.LEFT}
# The model's door squares (reach.DOORS in the research): $XY of the floor squares next to each doorway
DOOR_SQUARES = {"north": {0x76, 0x86}, "south": {0x7C, 0x8C}, "west": {0x29}, "east": {0xD9}}
PLAY_TOP, PLAY_LEFT, PLAY_RIGHT, PLAY_BOTTOM = 0x6, 0x2, 0xD, 0xC
STAIRWAY_MODE = 0x09
LADDER = ITEMS + 0x0C
LADDER_FRAMES = 120
# The push block: its object slot and type, and the RAM the push sets once the block lands
BLOCK_SLOT = 11
BLOCK = 0x68
BLOCK_PUSH_COMPLETE = 0x4CF
MIDDLE_ROW = 3                      # FLOORS row of Y $9
NO_BLOCK_FOUND = 0xD9
PUSH_FRAMES = 200
PUSHES = {Button.UP: (0, SQUARE - LINK_Y_OFFSET), Button.DOWN: (0, -SQUARE - LINK_Y_OFFSET),
          Button.LEFT: (SQUARE, -LINK_Y_OFFSET), Button.RIGHT: (-SQUARE, -LINK_Y_OFFSET)}
MOVES = {Button.UP: -0x01, Button.DOWN: 0x01, Button.LEFT: -0x10, Button.RIGHT: 0x10}
OPEN = WallSet(WallType.OPEN_DOOR, WallType.OPEN_DOOR, WallType.OPEN_DOOR, WallType.OPEN_DOOR)


@cache
def rom_with(layout_code: int, item_square: int | None = None, action: RoomAction = RoomAction.NONE) -> bytes:
    """The base ROM with room $45 (layout `layout_code`, trigger `action`) and its neighbors open and
    empty; with `item_square`, the room holds five rupees there (level 1's first position, standing
    from the start)."""
    base = remember_repo_base_rom()
    world = parse_rom(base)
    block = world.blocks[0]
    for num in (ROOM, *NEIGHBORS.values()):
        room = block.room(num)
        room.walls = OPEN
        room.enemy_info = EnemyInfo(Enemy.NOTHING)
        room.layout_info = LayoutInfo.from_layout_code(layout_code if num == ROOM else RoomType.PLAIN_ROOM)
        room.item_info = ItemInfo(Item.NOTHING)
        room.secret_info = SecretInfo(RoomAction.NONE)
    if item_square is not None:
        world.levels[LEVEL - 1].item_position_table[0] = item_square
        block.room(ROOM).item_info = ItemInfo(Item.FIVE_RUPEES)
        block.room(ROOM).secret_info = SecretInfo(action, ItemPosition.POSITION_A)
    return serialize_to_rom(world, base)


@cache
def console(layout_code: int, item_square: int | None = None, action: RoomAction = RoomAction.NONE) -> Console:
    return Console(rom_with(layout_code, item_square, action))


def link_squares(emu: Emulator) -> set[int]:
    """The squares Link's 16 x 16 body covers ($XY)."""
    x, y = emu[OBJ_X], emu[OBJ_Y] + LINK_Y_OFFSET
    columns = {x // SQUARE, (x + SQUARE - 1) // SQUARE}
    rows = {y // SQUARE, (y + SQUARE - 1) // SQUARE}
    return {column << 4 | row for column in columns for row in rows}


def inside(square: int) -> bool:
    return PLAY_LEFT <= square >> 4 <= PLAY_RIGHT and PLAY_TOP <= square & 0xF <= PLAY_BOTTOM


def enter_through(con: Console, side: str) -> None:
    """From the neighbor on `side`, through the door into room $45, by the game's own scroll: the
    room-entry shortcut (Console.enter_room) builds a room before its tiles, so its blocks and water
    would not stop Link, and the push block's search would find no block."""
    con.enter_room(LEVEL, NEIGHBORS[side])
    emu = con.emu
    emu[OBJ_X], emu[OBJ_Y], button = LEAVE[side]
    emu.run_until(lambda: emu[ROOM_ID] == ROOM, buttons=button, limit=WALK_LIMIT)
    emu.run_until(lambda: emu.mode == Mode.PLAY, limit=WALK_LIMIT)


# --- door squares -----------------------------------------------------------------------------------

@pytest.mark.parametrize("side", list(DOOR_SQUARES))
def test_through_each_door_link_first_stands_on_the_door_squares(side: str) -> None:
    con = console(RoomType.PLAIN_ROOM)
    enter_through(con, side)
    emu = con.emu
    assert not any(inside(square) for square in link_squares(emu)), "Link starts in the doorway"
    first = emu.run_until(lambda: all(inside(square) for square in link_squares(emu)),
                          buttons=INTO[side], limit=WALK_LIMIT)
    assert first > 0
    assert link_squares(emu) == DOOR_SQUARES[side]


def test_the_narrow_stair_rooms_east_door_opens_onto_its_stairs() -> None:
    """Through the east door Link stands on the stairs (four right of center, $D9) and gets no farther
    in: the model gives that door no start, so it reaches no square of the room. (Here the stairs
    lead nowhere; in a generated level they take Link down.)"""
    rows = FLOORS[RoomType.NARROW_STAIR_ROOM]
    assert rows[MIDDLE_ROW][-1] == "X"
    con = console(RoomType.NARROW_STAIR_ROOM)
    enter_through(con, "east")
    covered: set[int] = set()
    for _ in range(LADDER_FRAMES):
        con.emu.run(1, Button.LEFT)
        covered |= {square for square in link_squares(con.emu) if inside(square)}
    assert covered == {0xD9}


# --- the ladder -------------------------------------------------------------------------------------

def walk_from(con: Console, square: int, button: Button, ladder: bool, frames: int = LADDER_FRAMES) -> set[int]:
    """Link set on `square` in room $45, holding `button`; every square he covers on the way."""
    enter_through(con, "south")
    emu = con.emu
    emu[LADDER] = 1 if ladder else 0
    emu[OBJ_X], emu[OBJ_Y] = (square >> 4) * SQUARE, (square & 0xF) * SQUARE - LINK_Y_OFFSET
    emu.run(SETTLE_FRAMES)
    covered: set[int] = set()
    for _ in range(frames):
        emu.run(1, button)
        covered |= link_squares(emu)
    return covered


def test_no_water_without_the_ladder() -> None:
    # vertical moat: the water column is X $A; Link starts on its west side
    rows = FLOORS[RoomType.VERTICAL_MOAT_ROOM]
    assert rows[MIDDLE_ROW][8] == "~" and rows[MIDDLE_ROW][7] == "."
    covered = walk_from(console(RoomType.VERTICAL_MOAT_ROOM), 0x99, Button.RIGHT, ladder=False)
    assert max(square >> 4 for square in covered) == 0x9


def test_the_ladder_crosses_one_square_of_water() -> None:
    covered = walk_from(console(RoomType.VERTICAL_MOAT_ROOM), 0x99, Button.RIGHT, ladder=True)
    assert 0xA9 in covered and 0xB9 in covered


def test_the_ladder_never_crosses_two_squares_of_water() -> None:
    # T room: rows Y $9-$A hold water at X $3-$4 between floor at X $2 and X $5
    rows = FLOORS[RoomType.T_ROOM]
    assert rows[MIDDLE_ROW][1:4] == "~~."
    covered = walk_from(console(RoomType.T_ROOM), 0x59, Button.LEFT, ladder=True)
    assert 0x49 in covered, "Link steps onto the first square of water"
    assert min(square >> 4 for square in covered) == 0x4, "Link never reaches the second"


def test_an_item_on_water_is_taken_with_the_ladder() -> None:
    # horizontal moat: row Y $8 is water; the item at four right one up ($C8), Link below it
    rows = FLOORS[RoomType.HORIZONTAL_MOAT_ROOM]
    assert rows[2][10] == "~"
    con = console(RoomType.HORIZONTAL_MOAT_ROOM, 0xC8)
    walk_from(con, 0xC9, Button.UP, ladder=True)
    assert con.emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN


def test_without_the_ladder_an_item_on_water_is_still_touched_from_the_floor() -> None:
    """The model is stricter than the game here: Link never stands on the water without the ladder,
    but his pick-up reaches an item on a water square next to the floor he stands on. So the model's
    rule (water squares only in the ladder layouts, whose items the logic gives the ladder) never
    calls a square reachable that is not."""
    con = console(RoomType.HORIZONTAL_MOAT_ROOM, 0xC8)
    enter_through(con, "south")
    emu = con.emu
    emu[LADDER] = 0
    emu[OBJ_X], emu[OBJ_Y] = 0xC0, 0x9 * SQUARE - LINK_Y_OFFSET
    emu.run(SETTLE_FRAMES)
    highest = emu[OBJ_Y]
    for _ in range(LADDER_FRAMES):
        emu.run(1, Button.UP)
        highest = min(highest, emu[OBJ_Y])
    assert highest + LINK_Y_OFFSET > 0x8 * SQUARE, "Link never stands on the water square"
    assert emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN


# --- the push block ---------------------------------------------------------------------------------

def model_block(layout: int) -> int:
    """The model's push block: the first block square in the middle row from the west wall."""
    middle = FLOORS[layout][MIDDLE_ROW]
    column = next((column for column in range(len(middle) - 1) if middle[column] == "B"), None)
    return NO_BLOCK_FOUND if column is None else (column + PLAY_LEFT) << 4 | 0x9


def block_square(emu: Emulator) -> int:
    return int((emu[OBJ_X + BLOCK_SLOT] // SQUARE) << 4 | (emu[OBJ_Y + BLOCK_SLOT] // SQUARE))


PUSH_LAYOUTS = sorted(layout for layout in FLOORS if layout not in (RoomType.ENTRANCE_ROOM,))


@pytest.mark.parametrize("layout", PUSH_LAYOUTS, ids=[f"${layout:02X}" for layout in PUSH_LAYOUTS])
def test_the_push_block_is_the_first_block_in_the_middle_row(layout: int) -> None:
    con = console(layout | PUSH_BLOCK_VARIANT)
    enter_through(con, "south")
    assert con.emu[OBJ_TYPE + BLOCK_SLOT] == BLOCK
    assert block_square(con.emu) == model_block(layout)


@pytest.mark.parametrize("button", list(PUSHES), ids=[str(button.name).lower() for button in PUSHES])
def test_a_push_moves_the_block_one_square_once(button: Button) -> None:
    # double block: the block at two left of center ($69), floor on all four sides
    con = console(RoomType.DOUBLE_BLOCK | PUSH_BLOCK_VARIANT)
    enter_through(con, "south")
    emu = con.emu
    start = block_square(emu)
    assert start == 0x69
    dx, dy = PUSHES[button]
    emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + BLOCK_SLOT] + dx, emu[OBJ_Y + BLOCK_SLOT] + dy
    emu.run_until(lambda: emu[BLOCK_PUSH_COMPLETE] != 0, buttons=button, limit=PUSH_FRAMES)
    landed = block_square(emu)
    assert landed == start + MOVES[button]
    emu.run(PUSH_FRAMES, button)                          # pushing on moves it no farther
    assert block_square(emu) == landed


# --- an item under the push block (Remove Most Open Stairs, B30, with the flag off) -----------------

CENTER = 0x89
SINGLE_BLOCK_PUSH = RoomType.SINGLE_BLOCK_ROOM | PUSH_BLOCK_VARIANT       # $62, the block one left of center


def take_from_below(con: Console, square: int) -> None:
    """Link set on the square below `square`, walking up into it until he takes the room item."""
    emu = con.emu
    emu[OBJ_X], emu[OBJ_Y] = (square >> 4) * SQUARE, ((square & 0xF) + 1) * SQUARE - LINK_Y_OFFSET
    emu.run_until(lambda: emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN, buttons=Button.UP, limit=LADDER_FRAMES)


def walk_through_south_door_and_back(con: Console) -> None:
    emu = con.emu
    emu[OBJ_X], emu[OBJ_Y], _ = LEAVE["north"]
    emu.run_until(lambda: emu[ROOM_ID] == NEIGHBORS["south"], buttons=Button.DOWN, limit=WALK_LIMIT)
    emu.run_until(lambda: emu.mode == Mode.PLAY, limit=WALK_LIMIT)
    emu[OBJ_X], emu[OBJ_Y], _ = LEAVE["south"]
    emu.run_until(lambda: emu[ROOM_ID] == ROOM, buttons=Button.UP, limit=WALK_LIMIT)
    emu.run_until(lambda: emu.mode == Mode.PLAY, limit=WALK_LIMIT)
    emu.run(SETTLE_FRAMES)


def test_the_center_item_of_the_single_block_room_is_taken_without_a_push() -> None:
    con = console(SINGLE_BLOCK_PUSH, CENTER, RoomAction.BLOCK_STAIRS)
    enter_through(con, "south")
    assert block_square(con.emu) == CENTER - 0x10
    take_from_below(con, CENTER)
    assert con.emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN
    assert block_square(con.emu) == CENTER - 0x10, "taken without moving the block"


def test_the_center_item_of_the_single_block_room_is_taken_after_a_push_onto_it() -> None:
    con = console(SINGLE_BLOCK_PUSH, CENTER, RoomAction.BLOCK_STAIRS)
    enter_through(con, "south")
    emu = con.emu
    dx, dy = PUSHES[Button.RIGHT]
    emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + BLOCK_SLOT] + dx, emu[OBJ_Y + BLOCK_SLOT] + dy
    start = block_square(emu)
    moved_to = emu[OBJ_X + BLOCK_SLOT]
    for _ in range(PUSH_FRAMES):
        if emu[BLOCK_PUSH_COMPLETE]:
            break
        moved_to = max(moved_to, emu[OBJ_X + BLOCK_SLOT])
        emu.run(1, Button.RIGHT)
    # Once it lands, the block is drawn into the room's tiles and its object leaves (with this trigger,
    # for the stairway); it slid toward the center, and a push moves it exactly one square (above)
    assert emu[BLOCK_PUSH_COMPLETE] and moved_to > (start >> 4) * SQUARE
    assert start + MOVES[Button.RIGHT] == CENTER, "the block slid onto the item"
    assert emu[OBJ_STATE + ROOM_ITEM_SLOT] != TAKEN
    walk_through_south_door_and_back(con)
    assert emu[OBJ_STATE + ROOM_ITEM_SLOT] != TAKEN
    assert block_square(emu) == CENTER - 0x10, "leaving the room put the block back"
    take_from_below(con, CENTER)
    assert emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN
