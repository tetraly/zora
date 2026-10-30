"""Randomize Lost Hills and Randomize Dead Woods (docs/design/zora-flags-2.0.md sections 12-13;
owner decisions 2026-10-07): each maze's direction sequence is drawn anew, and the hint shop
offer that sells the path in PRG0 sells the new one, for 1 rupee, overriding whatever text that
offer showed.

The engine (aldonunez CheckMazes) repeats a maze screen until its four steps are walked in
order; the fourth leaves in its own direction. Steps 1-3 are drawn uniformly from three
directions, step 4 is fixed, and the maze's free exit is never used (the vanilla sequence comes
up about 1 time in 27):

  | Maze       | Steps 1-3          | Step 4 | Never |
  |------------|--------------------|--------|-------|
  | Lost Hills | up, down, right    | up     | left  |
  | Dead Woods | north, west, south | south  | east  |

Dead Woods' last step is south (owner decision), so the forest leads to $71, and Add Lost Woods
Shortcut (B88), which Randomize Dead Woods turns on (owner rule, beta 7), is the way into the west
half of the map without the ladder (overworld_gates.py).

With Mirror Overworld (B06, OW-MIR-04) the finished ROM's mazes take right for left and left for
right, so a hint names each step's mirror (ZORA's rule, docs/deviations.md): a randomized maze's
offer, and the offer of a maze left as it is whose path has a step left or right (PRG0's Dead Woods),
which then keeps its own price and replaces only a text naming that maze.
"""
from dataclasses import dataclass

from ...model.enums import OverworldDirection
from ...model.overworld import Overworld
from ..rng import IntRng

UP, DOWN, LEFT, RIGHT = (OverworldDirection.UP_NORTH, OverworldDirection.DOWN_SOUTH,
                         OverworldDirection.LEFT_WEST, OverworldDirection.RIGHT_EAST)
DRAWN_STEPS = 3


@dataclass(frozen=True)
class Maze:
    name: str
    choices: tuple[OverworldDirection, ...]       # steps 1-3
    last: OverworldDirection                      # step 4
    words: dict[OverworldDirection, str]          # how its hint names a direction
    hint_shop_offer: int                          # the offer (0-5, two shops of three) selling its path
    text: str                                     # the hint, {a} to {d} the steps; "|" breaks a line
    names_it: str                                 # the words of its hint that name the maze


@dataclass(frozen=True)
class MazeOffer:
    """A hint shop offer's new text: a randomized maze's path for MAZE_HINT_PRICE, or (Mirror
    Overworld) a path left as it is, named mirrored, at the offer's own price (price None)."""
    lines: list[str]
    price: int | None = None


# PRG0's path offers: Hint Shop 1's third (text 11, 20 rupees) and Hint Shop 2's second (text 12,
# 30 rupees); offers 0-2 are Hint Shop 1's, 3-5 Hint Shop 2's.
LOST_HILLS = Maze("Lost Hills", (UP, DOWN, RIGHT), UP,
                  {UP: "UP", DOWN: "DOWN", RIGHT: "RIGHT", LEFT: "LEFT"}, 2,
                  "GO {a}, {b},|{c}, {d}|THE MOUNTAIN AHEAD", "MOUNTAIN AHEAD")
DEAD_WOODS = Maze("Dead Woods", (UP, LEFT, DOWN), DOWN,
                  {UP: "NORTH", LEFT: "WEST", DOWN: "SOUTH", RIGHT: "EAST"}, 4,
                  "GO {a}, {b},|{c}, {d} TO|THE FOREST OF MAZE", "FOREST OF MAZE")
MAZE_HINT_PRICE = 1
# Mirror Overworld's flip of a step (OW-MIR-04 exchanges the mazes' right and left)
MIRRORED_STEP = {LEFT: RIGHT, RIGHT: LEFT}


def draw_sequence(maze: Maze, rng: IntRng) -> list[OverworldDirection]:
    return [maze.choices[rng.below(len(maze.choices))] for _ in range(DRAWN_STEPS)] + [maze.last]


def maze_hint(maze: Maze, sequence: list[OverworldDirection], mirrored: bool = False) -> list[str]:
    """The hint's lines for a sequence; mirrored, each step as the flipped ROM takes it."""
    a, b, c, d = (maze.words[MIRRORED_STEP.get(step, step) if mirrored else step] for step in sequence)
    return maze.text.format(a=a, b=b, c=c, d=d).split("|")


def randomize_mazes(overworld: Overworld, rng: IntRng, lost_hills: bool, dead_woods: bool,
                    mirrored: bool = False) -> dict[int, MazeOffer]:
    """Draw the chosen mazes' sequences into the overworld (Dead Woods' draws first, as the ROM
    stores it first); returns each hint shop offer's new text (the hint text step writes it and
    prices a randomized maze's offer at 1 rupee). With Mirror Overworld a maze left as it is whose
    path goes left or right is named mirrored too, at its offer's own price (no draw)."""
    offers: dict[int, MazeOffer] = {}
    for maze, randomized, field in ((DEAD_WOODS, dead_woods, "dead_woods_directions"),
                                    (LOST_HILLS, lost_hills, "lost_hills_directions")):
        if randomized:
            setattr(overworld, field, draw_sequence(maze, rng))
            offers[maze.hint_shop_offer] = MazeOffer(maze_hint(maze, getattr(overworld, field), mirrored),
                                                     MAZE_HINT_PRICE)
        elif mirrored and any(step in MIRRORED_STEP for step in getattr(overworld, field)):
            offers[maze.hint_shop_offer] = MazeOffer(maze_hint(maze, getattr(overworld, field), mirrored))
    return offers


MAZE_NAMES = {maze.hint_shop_offer: maze.names_it for maze in (DEAD_WOODS, LOST_HILLS)}
