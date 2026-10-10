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

Dead Woods' last step is south (owner decision), so the forest leads to $71 and the west half
of the map needs the ladder in the logic (overworld_gates.py).
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


# PRG0's path offers: Hint Shop 1's third (text 11, 20 rupees) and Hint Shop 2's second (text 12,
# 30 rupees); offers 0-2 are Hint Shop 1's, 3-5 Hint Shop 2's.
LOST_HILLS = Maze("Lost Hills", (UP, DOWN, RIGHT), UP, {UP: "UP", DOWN: "DOWN", RIGHT: "RIGHT"}, 2,
                  "GO {a}, {b},|{c}, {d}|THE MOUNTAIN AHEAD")
DEAD_WOODS = Maze("Dead Woods", (UP, LEFT, DOWN), DOWN, {UP: "NORTH", LEFT: "WEST", DOWN: "SOUTH"}, 4,
                  "GO {a}, {b},|{c}, {d} TO|THE FOREST OF MAZE")
MAZE_HINT_PRICE = 1


def draw_sequence(maze: Maze, rng: IntRng) -> list[OverworldDirection]:
    return [maze.choices[rng.below(len(maze.choices))] for _ in range(DRAWN_STEPS)] + [maze.last]


def maze_hint(maze: Maze, sequence: list[OverworldDirection]) -> list[str]:
    """The hint's lines for a sequence."""
    a, b, c, d = (maze.words[step] for step in sequence)
    return maze.text.format(a=a, b=b, c=c, d=d).split("|")


def randomize_mazes(overworld: Overworld, rng: IntRng, lost_hills: bool, dead_woods: bool) -> dict[int, list[str]]:
    """Draw the chosen mazes' sequences into the overworld (Dead Woods' draws first, as the ROM
    stores it first); returns each hint shop offer's new text (the hint text step writes it and
    prices the offer at 1 rupee)."""
    offers: dict[int, list[str]] = {}
    if dead_woods:
        overworld.dead_woods_directions = draw_sequence(DEAD_WOODS, rng)
        offers[DEAD_WOODS.hint_shop_offer] = maze_hint(DEAD_WOODS, overworld.dead_woods_directions)
    if lost_hills:
        overworld.lost_hills_directions = draw_sequence(LOST_HILLS, rng)
        offers[LOST_HILLS.hint_shop_offer] = maze_hint(LOST_HILLS, overworld.lost_hills_directions)
    return offers
