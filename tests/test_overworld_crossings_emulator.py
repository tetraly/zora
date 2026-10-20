"""Add Lost Woods Shortcut (B88; features-behavior.md FP-WOODS-01) and Add Bridges to the River (B87;
FP-BRIDGE-01) in the emulator, on generated ROMs, against the same flags without them:
  - the shortcut: Link walks west from $52 into $51 and on along rows 4 to 6 into $50, arriving
    beside its rock edge column, keeps walking west, and walks south into $60; walking east from
    $50 at those rows he stops at the rock and stays on $50. Without it, $51's trees stop him.
  - the bridges: Link walks west over the river in $17 (rows 7 and 8) and $27 (row 5); without
    them the water stops him.
The spec measured these with a square-level walk only (FP-BRIDGE-01's Confidence); this is the run
in the game. Enemies are frozen by the clock and the hearts kept full, so nothing pushes Link."""
from functools import cache

import pytest

from tests.emulator import OBJ_X, OBJ_Y, ROOM_ID, Button, Emulator, Mode
from tests.test_flags2_emulator import FULL_HEARTS, HEART_VALUES, INV_CLOCK
from tests.test_progressive_emulator import IS_UPDATING_MODE, Game
from tests.test_river_bridges_and_shortcut import BRIDGES_ON, SHORTCUT_ON
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

SEED = 1
LEFT, RIGHT, DOWN = Button.LEFT, Button.RIGHT, Button.DOWN
# Link's Y on the overworld for a square row: the play area's first row is at $3D, 16 pixels a row
FIRST_ROW_Y, SQUARE = 0x3D, 0x10
SHORTCUT_ROOM, EAST_OF_IT, PAST_THE_ROCK, MAZE_EXIT_ROOM = 0x51, 0x52, 0x50, 0x60
SHORTCUT_ROW = 5                       # the middle of rows 4 to 6
ROCK_COLUMN_X = 0xF0                   # $50's square column 15, its rock east edge
WALK_FRAMES = 400                      # long enough to cross a screen (Link moves 1.5 pixels a frame)
# Each river crossing: the room and its bridge row; the river is square column 6, X $60 to $6F
RIVER_X = 0x60
EAST_OF_THE_RIVER_X = 0x90
CROSSINGS = [(0x17, 7), (0x17, 8), (0x27, 5)]


def row_y(row: int) -> int:
    return FIRST_ROW_Y + row * SQUARE


@cache
def rom(flags: str) -> bytes:
    return generate_rom(flags, SEED, remember_repo_base_rom()).rom


def steady(emu: Emulator) -> None:
    emu[INV_CLOCK] = 1
    emu[HEART_VALUES] = FULL_HEARTS


def walk_to(emu: Emulator, button: Button, room: int) -> bool:
    """Hold `button` until Link has scrolled onto `room` and play resumes; False if he never does."""
    try:
        emu.run_until(lambda: emu[ROOM_ID] == room and emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1,
                      limit=WALK_FRAMES, buttons=button)
    except AssertionError:
        return False
    return True


def on_room(flags: str, room: int, x: int, y: int) -> Emulator:
    """A new game on `room` (one with a cave, whose exit the leave-cave mode puts Link at), Link
    then set at (x, y)."""
    game = Game(rom(flags))
    game.go_to_screen(room)
    emu = game.emu
    steady(emu)
    emu[OBJ_X], emu[OBJ_Y] = x, y
    emu.run(2)
    return emu


def through_the_shortcut(flags: str) -> list[tuple[int, int]]:
    """From $51's cave, east into $52, then west back into $51 and on toward $50, then south: the
    room and Link's X after each leg, as far as he gets."""
    emu = on_room(flags, SHORTCUT_ROOM, 0xD0, row_y(SHORTCUT_ROW))
    legs = []
    assert walk_to(emu, RIGHT, EAST_OF_IT)                      # into $52
    emu[OBJ_Y] = row_y(SHORTCUT_ROW)
    for button, room in ((LEFT, SHORTCUT_ROOM), (LEFT, PAST_THE_ROCK)):
        steady(emu)
        if not walk_to(emu, button, room):
            legs.append((emu[ROOM_ID], emu[OBJ_X]))
            return legs
        legs.append((emu[ROOM_ID], emu[OBJ_X]))
    emu.run(40, LEFT)                                           # on past the rock column
    legs.append((emu[ROOM_ID], emu[OBJ_X]))
    steady(emu)
    walk_to(emu, DOWN, MAZE_EXIT_ROOM)
    legs.append((emu[ROOM_ID], emu[OBJ_X]))
    return legs


def test_the_shortcut_leads_from_52_through_51_into_50_and_on_to_60() -> None:
    (into_51, _), (into_50, arrival_x), (still_50, walked_x), (south, _) = through_the_shortcut(SHORTCUT_ON)
    assert (into_51, into_50, still_50, south) == (SHORTCUT_ROOM, PAST_THE_ROCK, PAST_THE_ROCK, MAZE_EXIT_ROOM)
    assert arrival_x >= ROCK_COLUMN_X - SQUARE          # he comes in beside the rock edge
    assert walked_x < arrival_x - SQUARE                # and walks on west


def test_without_the_shortcut_51s_trees_stop_link() -> None:
    legs = through_the_shortcut(MVP_BASELINE_LEVEL_ENCODING_OFF)
    assert legs[0][0] == SHORTCUT_ROOM and legs[-1][0] == SHORTCUT_ROOM


def test_walking_back_east_from_50_stops_at_the_rock() -> None:
    """In $50 on the shortcut's row, a little west of the rock column, Link holds right: he never
    leaves $50."""
    emu = on_room(SHORTCUT_ON, SHORTCUT_ROOM, 0xD0, row_y(SHORTCUT_ROW))
    assert walk_to(emu, LEFT, PAST_THE_ROCK)
    emu.run(40, LEFT)
    steady(emu)
    assert not walk_to(emu, RIGHT, SHORTCUT_ROOM)
    assert emu[ROOM_ID] == PAST_THE_ROCK and emu[OBJ_X] < ROCK_COLUMN_X


def across_the_river(flags: str, room: int, row: int) -> int:
    """Link's X after holding left from east of the river on `room`'s crossing row. $27 has a cave
    east of the river; $17 is walked into from $27's north edge, east of the river too."""
    emu = on_room(flags, 0x27, 0x80, row_y(2))
    if room == 0x17:
        steady(emu)
        assert walk_to(emu, Button.UP, 0x17)
    emu[OBJ_X], emu[OBJ_Y] = EAST_OF_THE_RIVER_X, row_y(row)
    emu.run(2)
    steady(emu)
    emu.run(120, LEFT)
    return emu[OBJ_X]


@pytest.mark.parametrize(("room", "row"), CROSSINGS)
def test_link_crosses_each_bridge(room: int, row: int) -> None:
    assert across_the_river(BRIDGES_ON, room, row) < RIVER_X - SQUARE
    assert across_the_river(MVP_BASELINE_LEVEL_ENCODING_OFF, room, row) >= RIVER_X + SQUARE
