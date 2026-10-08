"""OW-START-01 (overworld-behavior.md): the start screen is redrawn, and
screen 119's monster data moves with it.

The draw runs in the flow after the late room-deal gate and level 9's
post-gate record step (PS-L9REC, which draws nothing). The exchange is
applied when the pass ships, after the group passes have written the
overworld monsters, because it moves the start screen's monster group as it
stands after PS-OWM and PS-EGRP-05 (post-shapes-b8.md PS-OWM-03).
"""
from dataclasses import dataclass

from zora.generate.rng import IntRng, discard
from zora.model.overworld import Overworld

PRG0_START_SCREEN = 119
# OW-START-01: the 51 screens the draw accepts (normative as written; 119,
# PRG0's own start screen, is one of them).
START_SCREENS = frozenset({
    24, 28, 29, 39, 40, 41, 43, 44, 45, 58, 59, 61, 66, 70, 71, 72, 73, 74, 75,
    77, 78, 81, 83, 86, 88, 91, 94, 96, 99, 100, 102, 103, 104, 106, 107, 108,
    109, 110, 111, 112, 113, 114, 116, 117, 118, 119, 120, 121, 123, 124, 125,
})
SCREEN_DRAW_RANGE = 128                 # S = the number mod 128
NUMBER_RANGE = 1 << 31
SEED_DRAWS = 3                          # one number as the pass's (unused) seed, two discarded
# Step 2: Link's start row w(S) is 8 on every screen of the list but these.
START_ROWS = {44: 10, 66: 10, 109: 5, 110: 7, 114: 5, 117: 7, 118: 7, 121: 7}
DEFAULT_START_ROW = 8
ROW_HEIGHT = 16
START_Y_OFFSET = 13
BYTE_RANGE = 256
MIXED_CODE_BIT = 0x40       # the model's enemy code carries LevelBlockAttrsD bit 7 as $40


@dataclass(frozen=True)
class StartScreen:
    """The drawn start screen S, written when the pass ships."""
    screen: int


def start_y(screen: int) -> int:
    """OW-START-01 step 2: Link's Y on the start screen, (16 * w(S) + 13) mod 256."""
    row = START_ROWS.get(screen, DEFAULT_START_ROW)
    return (ROW_HEIGHT * row + START_Y_OFFSET) % BYTE_RANGE


def shuffle_start_screen(rng: IntRng) -> StartScreen:
    """OW-START-01: one number as the pass's seed (unused), two discarded,
    then one number per attempt until its value mod 128 is a listed screen.
    No ban refers to cave codes: S may carry any cave, a dungeon door or
    the wooden-sword cave."""
    discard(rng, SEED_DRAWS, NUMBER_RANGE)
    while True:
        screen = rng.below(NUMBER_RANGE) % SCREEN_DRAW_RANGE
        if screen in START_SCREENS:
            return StartScreen(screen)


def apply_start_screen(overworld: Overworld, start: StartScreen) -> None:
    """OW-START-01 steps 1-4. The start screen and Link's start Y change; S
    and 119 exchange their whole LevelBlockAttrsC byte (monster list low
    six bits and count index), and LevelBlockAttrsD bit 7 moves from S to
    119 when S's is set. Since 119's bit 7 is clear beforehand, both steps
    together swap the two screens' whole monster groups, which the model
    holds as the enemy spec (bit 7 as code $40) and the quantity. The cave
    bytes and every other screen attribute stay where OW-CAVE left them;
    the exchange follows the screens, not the caves. When S = 119 nothing
    moves."""
    overworld.start_screen = start.screen
    overworld.start_position_y = start_y(start.screen)
    old_start = overworld.screens[PRG0_START_SCREEN]
    new_start = overworld.screens[start.screen]
    # Quirk (OW-START-01 step 4): bit 7 only ever moves into 119, never out
    # of it; that is an exchange only because no earlier pass sets 119's.
    assert old_start.enemy_spec.enemy.value < MIXED_CODE_BIT, "119's table-D bit 7 is set"
    old_start.enemy_spec, new_start.enemy_spec = new_start.enemy_spec, old_start.enemy_spec
    old_start.enemy_quantity, new_start.enemy_quantity = new_start.enemy_quantity, old_start.enemy_quantity
