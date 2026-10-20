"""Highlight No-Drop Rooms in the emulator (tests/emulator.py): the ROM with the flag on against
the same plan with it resolved off, run with the same inputs from the same state, so every pixel
that differs is a room's inner palette, the one thing the flag changes.

  - A scroll pair: a marked room (palette 2 off, 3 on) and its unmarked neighbor (3 off, 2 on)
    through an open door, entered and left in both directions (seed 1, level 9, rooms $46 and $56,
    north and south; seed 2, level 5, rooms $2C and $2D, east and west). In each room only the
    inner area differs, and the two rooms' colors swap: the marked room shows the colors the
    unmarked one showed with the flag off, and the other way round.
  - A marked dark room lit with the candle and left (1st Quest dungeons, seed 1, level 6, room $39,
    into the unchanged room $3A): a step in from the doorway (where no item can be used), the
    candle lights the room (its inner area brightens), and lit only its inner area differs; next
    door nothing differs.
  - A block pushed in a marked room (seed 2, level 5, room $2C): while it slides (a sprite) and
    once it lands, only the inner area differs; down the stairs it opened and back up, the room
    shows the same colors (the stairway's exit draws it).
Walls, the status bar, Link and the monsters never differ."""
from functools import cache

import numpy as np
import pytest

from tests.emulator import ITEMS, NAMETABLE_BASE, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID, SELECTED_ITEM_SLOT, Button, Mode
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import Console
from tests.test_highlight_no_drop_rooms import SOURCES, roms

pytestmark = needs_base_rom

# The play area's inner squares on screen: below the status bar (64 lines) and inside the walls
# (two squares, 32 pixels, on each side of the 256 x 176 play area).
STATUS_BAR_HEIGHT = 64
WALL = 32
INNER_TOP, INNER_BOTTOM = STATUS_BAR_HEIGHT + WALL, STATUS_BAR_HEIGHT + 176 - WALL
INNER_LEFT, INNER_RIGHT = WALL, 256 - WALL
# Link's square before each door of a room, and the direction through it
DOORS = {"east": (0xD0, 0x8D, Button.RIGHT), "west": (0x20, 0x8D, Button.LEFT),
         "north": (0x78, 0x5D, Button.UP), "south": (0x78, 0xBD, Button.DOWN)}
STEPS = {"east": 1, "west": -1, "north": -0x10, "south": 0x10}
OPPOSITE = {"east": "west", "west": "east", "north": "south", "south": "north"}
SCROLL_LIMIT = 400
SETTLE_FRAMES = 30
# The candle: InvCandle (Items + 4), 1 for the blue one; its B-item slot (SelectedItemSlot, the
# WieldItem_JumpTable index: 3 is the bow's). Link uses it a step inside the room, out of the doorway,
# where no item can be used; the fade's three brighter steps take about 60 frames.
INV_CANDLE = ITEMS + 4
BLUE_CANDLE = 1
CANDLE_SLOT = 4
INSIDE_EAST_DOOR = (0xB0, 0x8D)
STEP_FRAMES = 10
USE_FRAMES = 4
LIGHT_FRAMES = 90
# The push block: its object type (UpdateObject_JumpTable index $68, UpdateBlock) and the RAM the
# push sets once the block lands (src/Variables.inc)
BLOCK = 0x68
BLOCK_PUSH_COMPLETE = 0x4CF
MONSTER_SLOTS = range(1, 12)
# The stairs a push opens: their top-left tile in the nametable, and the stairway's mode
STAIRS_TILE = 0x70
PLAY_AREA_TILES = 0x3C0
TILE_COLUMNS = 32
TILE_SIZE = 8
STAIRWAY_MODE = 0x09
STAIRWAY_FRAMES = 90
PUSH_LIMIT = 200
LINK_Y_OFFSET = 3                    # UpdateBlock0Idle compares Link's Y + 3 with the block's
ONE_SQUARE = 0x10
PUSHES = {Button.UP: (0, ONE_SQUARE - LINK_Y_OFFSET), Button.DOWN: (0, -ONE_SQUARE - LINK_Y_OFFSET),
          Button.LEFT: (ONE_SQUARE, -LINK_Y_OFFSET), Button.RIGHT: (-ONE_SQUARE, -LINK_Y_OFFSET)}

Color = tuple[int, int, int]


@cache
def consoles(source: str, seed: int) -> tuple[Console, Console]:
    """Flag on, flag off: each from a new file, the same state."""
    on, off = roms(SOURCES[source], seed)
    return Console(on), Console(off)


def changed_colors(on: Console, off: Console) -> set[tuple[Color, Color]]:
    """The (flag off, flag on) colors of every pixel that differs, all inside the inner area; each
    off color maps to one on color, so the difference is a palette, not what is drawn."""
    frame_on, frame_off = on.emu.last_frame, off.emu.last_frame
    differs = np.any(frame_on != frame_off, axis=2)
    rows, columns = np.nonzero(differs)
    assert all(INNER_TOP <= row < INNER_BOTTOM for row in rows), "outside the inner area (rows)"
    assert all(INNER_LEFT <= column < INNER_RIGHT for column in columns), "outside the inner area (columns)"
    pairs = {(tuple(int(c) for c in frame_off[row, column]), tuple(int(c) for c in frame_on[row, column]))
             for row, column in zip(rows, columns, strict=True)}
    assert len({before for before, _ in pairs}) == len(pairs), "one off color became two on colors"
    return pairs  # type: ignore[return-value]


def both(consoles_: tuple[Console, Console], action: str, *args: object) -> None:
    for console in consoles_:
        getattr(Walker(console), action)(*args)


class Walker:
    """The moves a test makes, the same on either console."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self.emu = console.emu

    def enter(self, level: int, room: int) -> None:
        self.console.enter_room(level, room)
        self.clear()

    def clear(self) -> None:
        for slot in MONSTER_SLOTS:
            if self.emu[OBJ_TYPE + slot] != BLOCK:
                self.emu[OBJ_TYPE + slot] = 0
        self.emu.run(SETTLE_FRAMES)

    def walk(self, side: str) -> None:
        """Through the room's open door on `side`, into the next room."""
        target = self.emu[ROOM_ID] + STEPS[side]
        x, y, button = DOORS[side]
        self.emu[OBJ_X], self.emu[OBJ_Y] = x, y
        self.emu.run_until(lambda: self.emu[ROOM_ID] == target, buttons=button, limit=SCROLL_LIMIT)
        self.emu.run_until(lambda: self.emu.mode == Mode.PLAY, limit=SCROLL_LIMIT)
        self.emu.run(SETTLE_FRAMES)
        self.clear()

    def step_in(self) -> None:
        """A step in from the east door, facing west."""
        self.emu[OBJ_X], self.emu[OBJ_Y] = INSIDE_EAST_DOOR
        self.emu.run(STEP_FRAMES, Button.LEFT)

    def light(self) -> None:
        self.emu[INV_CANDLE] = BLUE_CANDLE
        self.emu[SELECTED_ITEM_SLOT] = CANDLE_SLOT
        self.emu.run(USE_FRAMES, Button.B)
        self.emu.run(LIGHT_FRAMES)

    def stand_by_block(self, button: Button) -> None:
        slot = next(slot for slot in MONSTER_SLOTS if self.emu[OBJ_TYPE + slot] == BLOCK)
        dx, dy = PUSHES[button]
        self.emu[OBJ_X] = self.emu[OBJ_X + slot] + dx
        self.emu[OBJ_Y] = self.emu[OBJ_Y + slot] + dy

    def push(self, button: Button, frames: int) -> None:
        self.emu.run(frames, button)

    def down_and_up(self) -> None:
        """Onto the room's stairs, into the stairway (mode 9), and back up its first ladder."""
        tiles = self.emu.nametable(NAMETABLE_BASE, PLAY_AREA_TILES)
        square = tiles.index(STAIRS_TILE)
        self.emu[OBJ_X] = square % TILE_COLUMNS * TILE_SIZE
        self.emu[OBJ_Y] = square // TILE_COLUMNS * TILE_SIZE - LINK_Y_OFFSET
        self.emu.run_until(lambda: self.emu.mode == STAIRWAY_MODE, limit=SCROLL_LIMIT)
        self.emu.run(STAIRWAY_FRAMES)
        self.emu.run(SETTLE_FRAMES, Button.DOWN)
        self.emu.run_until(lambda: self.emu.mode == Mode.PLAY, buttons=Button.UP, limit=SCROLL_LIMIT)
        self.emu.run(STAIRWAY_FRAMES)


def enter_from(pair: tuple[Console, Console], level: int, room: int, side: str) -> None:
    """Into `room` from its neighbor on `side`, by a scroll: the room-entry shortcut the consoles
    use (Console.enter_room, the enter-room mode) draws a room without FillPlayAreaAttrs, so a
    room is checked only once the game's own scroll has drawn it (InitMode7)."""
    both(pair, "enter", level, room + STEPS[side])
    both(pair, "walk", OPPOSITE[side])
    assert pair[0].emu[ROOM_ID] == pair[1].emu[ROOM_ID] == room


def visit_pair(source: str, seed: int, level: int, marked: int, side: str) -> None:
    pair = consoles(source, seed)
    enter_from(pair, level, marked, side)
    marked_colors = changed_colors(*pair)
    assert marked_colors, "the marked room looks the same"
    both(pair, "walk", side)
    assert pair[0].emu[ROOM_ID] == marked + STEPS[side]
    unmarked_colors = changed_colors(*pair)
    assert unmarked_colors == {(after, before) for before, after in marked_colors}
    both(pair, "walk", OPPOSITE[side])
    assert pair[0].emu[ROOM_ID] == marked
    assert changed_colors(*pair) == marked_colors


@pytest.mark.parametrize(("seed", "level", "marked", "side"), [(1, 9, 0x46, "south"), (2, 5, 0x2C, "east")],
                         ids=["north and south", "east and west"])
def test_scrolling_between_a_marked_and_an_unmarked_room(seed: int, level: int, marked: int, side: str) -> None:
    visit_pair("MVP baseline", seed, level, marked, side)


def inner_area(console: Console) -> np.ndarray:
    return console.emu.last_frame[INNER_TOP:INNER_BOTTOM, INNER_LEFT:INNER_RIGHT].copy()


# Lit: most of the inner area brighter than before the candle (a sprite, Link or the flame, covers
# a few squares of it, about 2 percent each).
LIT_SHARE = 0.5


def test_a_marked_dark_room_lit_with_the_candle_and_left() -> None:
    pair = consoles("1st Quest", 1)
    enter_from(pair, 6, 0x39, "east")
    changed_colors(*pair)
    both(pair, "step_in")
    dark = [inner_area(console) for console in pair]
    both(pair, "light")
    for console, before in zip(pair, dark, strict=True):
        brighter = inner_area(console).astype(int).sum(axis=2) > before.astype(int).sum(axis=2)
        assert brighter.mean() > LIT_SHARE, f"the candle lit nothing ({brighter.mean():.0%} brighter)"
    assert changed_colors(*pair), "the lit marked room looks the same"
    both(pair, "walk", "east")
    assert pair[0].emu[ROOM_ID] == 0x3A
    assert changed_colors(*pair) == set()


def test_a_block_pushed_in_a_marked_room() -> None:
    pair = consoles("MVP baseline", 2)
    enter_from(pair, 5, 0x2C, "east")
    start = [console.emu.save() for console in pair]
    for button in PUSHES:
        for console, state in zip(pair, start, strict=True):
            console.emu.load(state)
        both(pair, "stand_by_block", button)
        both(pair, "push", button, ONE_SQUARE + 4)
        changed_colors(*pair)                              # pushing: Link and the block's sprite agree
        both(pair, "push", button, PUSH_LIMIT)
        if pair[0].emu[BLOCK_PUSH_COMPLETE]:
            break
    else:
        raise AssertionError("no side pushes the block")
    assert pair[1].emu[BLOCK_PUSH_COMPLETE]
    landed = changed_colors(*pair)
    assert landed, "the landed block's room looks the same"
    # The push opened the room's stairs (trigger 5): down them and back up, the room is drawn
    # by the stairway's exit, with the same colors.
    both(pair, "down_and_up")
    assert pair[0].emu[ROOM_ID] == pair[1].emu[ROOM_ID] == 0x2C
    assert changed_colors(*pair) == landed

