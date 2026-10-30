"""Change Secret Spots (B05; overworld-behavior.md OW-ENTR-01): each screen's secret square moves along
the screen.

The overworld's layouts are shared column codes (RoomLayoutsOW); a column code draws 11 squares, rows
0 to 10 from the top. A column holding one of the four secret squares (a pushable rock, a bombable rock
wall, a burnable tree, a pushable gravestone) is a secret column; its plain form has each secret square
replaced by its plain twin. The pass surveys every screen's columns, then, screen by screen, clears a
screen's secret column to a plain one and places a secret column again at an entry the two tests of
step 3 accept. A moved rock wall takes the screen's cave exit with it, and a distance test may have the
screen's monsters come in from the edges. Each secret keeps its kind and its screen, and only PRG0's own
secret column codes are placed.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ...model.enums import QuestVisibility
from ...model.overworld import OverworldLayouts, Screen
from ..rng import IntRng, discard

Squares = tuple[int, ...]

PUSHABLE_ROCK, BOMBABLE_ROCK_WALL, BURNABLE_TREE, PUSHABLE_GRAVESTONE = 0x26, 0x27, 0x28, 0x29
PLAIN_TWINS = {PUSHABLE_ROCK: 0x13, BOMBABLE_ROCK_WALL: 0x1B, BURNABLE_TREE: 0x19, PUSHABLE_GRAVESTONE: 0x14}
# The squares a secret needs beside it (above, below, left or right), and a spawn spot must stand on
OPEN_SQUARES = frozenset({0x0E, 0x07})
SCREENS = 0x80
CANDIDATE_ENTRIES = range(1, 15)          # entries 0 and 15, the screen's edges, never move
# Screens 124 and 125 share layout $76: 125 is skipped, its exit column follows 124's
SHARED_LAYOUT_SCREEN, ITS_TWIN = 125, 124
LEADING_DISCARDS = 2
# Step 4's distance test: a spawn spot counts when more than this many squares from the wall
DISTANCE = 2
SPAWN_ROW_OFFSET = 3
NIBBLE_SHIFT, LOW_NIBBLE = 4, 0x0F
EXIT_ROW_MASK = 0x07
# ZORA's exit beside moved stairs: below, left, right, above; and the rows an exit can name
STAIRS_EXIT_SIDES = ((0, 1), (-1, 0), (1, 0), (0, -1))
EXIT_ROWS = range(EXIT_ROW_MASK + 1)          # Link comes out on the row the three bits name
# LevelBlockAttrsF bit 7, the quest field's high bit: set, the distance test does not run
QUEST_FIELD_HIGH_BIT = frozenset({QuestVisibility.SECOND_QUEST, QuestVisibility.NEITHER_QUEST})


def plain_form(squares: Squares) -> Squares:
    return tuple(PLAIN_TWINS.get(square, square) for square in squares)


def secret_squares(squares: Squares) -> list[int]:
    return [square for square in squares if square in PLAIN_TWINS]


@dataclass
class Survey:
    """Step 1's tables: a secret column's squares and its plain form, and a plain column's squares,
    each a key for the column's code (a key met again takes the later code)."""
    secret: dict[Squares, int]
    plain: dict[Squares, int]


def survey(layouts: list[list[int]], screens: Sequence[Screen], squares: dict[int, Squares]) -> Survey:
    """OW-ENTR-01 step 1: screens 0 to 127 in order, each screen's 16 entries in order."""
    found = Survey({}, {})
    for screen in screens:
        for code in layouts[screen.screen_code]:
            column = squares[code]
            if secret_squares(column):
                found.secret[column] = code
                found.secret[plain_form(column)] = code
            else:
                found.plain[column] = code
    return found


def kind_of(column: Squares) -> int:
    """A secret column's kind: its last secret square."""
    return secret_squares(column)[-1]


def change_secret_spots(layouts_read: OverworldLayouts, screens: Sequence[Screen],
                        rng: IntRng) -> tuple[tuple[int, ...], ...]:
    """OW-ENTR-01 steps 1 to 4 on the staged screens: returns the 124 layouts' column codes, and
    writes a moved rock wall's exit column and row and the edge-monster bit into its screen, and
    (ZORA's rule) moved stairs' exit beside them. The
    accepted entry is drawn uniformly among the candidates that pass both tests (the MAY of step 3:
    drawing among all of them until one passes picks the same way)."""
    squares = layouts_read.squares
    layouts = [list(layout) for layout in layouts_read.layouts]
    by_number = {screen.screen_num: screen for screen in screens}
    ordered = [by_number[number] for number in range(SCREENS)]
    tables = survey(layouts, ordered, squares)
    discard(rng, LEADING_DISCARDS)
    for screen in ordered:
        if screen.screen_num == SHARED_LAYOUT_SCREEN:
            screen.exit_x_position = by_number[ITS_TWIN].exit_x_position
            continue
        layout = layouts[screen.screen_code]
        candidates = [entry for entry in CANDIDATE_ENTRIES if squares[layout[entry]] in tables.secret]
        kind = screen_kind(layout, candidates, squares, tables)
        if kind is None:
            continue
        before = secret_spot(layout, squares)
        clear(layout, candidates, squares, tables)
        cleared = [squares[code] for code in layout]
        passing = [entry for entry in candidates if accepts(layout, entry, kind, squares, tables)]
        assert passing, f"OW-ENTR-01: no entry of screen ${screen.screen_num:02X} passes step 3's tests"
        entry = passing[rng.below(len(passing))]
        secret = tables.secret[squares[layout[entry]]]
        layout[entry] = secret
        row, square = first_secret(squares[secret])
        if square == BOMBABLE_ROCK_WALL:
            move_the_cave_exit(screen, entry, row, cleared, layouts_read.spawn_spots)
        elif (entry, row) != before:
            move_the_stairs_exit(screen, entry, row, [squares[code] for code in layout])
    return tuple(tuple(layout) for layout in layouts)


def secret_spot(layout: list[int], squares: dict[int, Squares]) -> tuple[int, int] | None:
    """The entry and row of the screen's secret square as the layout stands."""
    for entry, code in enumerate(layout):
        for row, square in enumerate(squares[code]):
            if square in PLAIN_TWINS:
                return entry, row
    return None


def move_the_stairs_exit(screen: Screen, entry: int, row: int, columns: list[Squares]) -> bool:
    """ZORA's rule (docs/deviations.md; OW-ENTR-01 keeps PRG0's bytes): a moved rock's, tree's or
    gravestone's stairs take the screen's cave exit with them, as a moved wall does (the A byte's high
    nibble its column, the F byte's bits 2-0 its row). Returns whether it moved the exit."""
    spot = stairs_exit(entry, row, columns)
    if spot is None:
        # The fallback, deliberately the spec's own rule: with no open square beside the stairs in
        # rows 0 to 7 (stairs on rows 9 or 10, or walled in there), the screen keeps PRG0's exit.
        return False
    screen.exit_x_position, screen.exit_y_position = spot
    return True


def stairs_exit(entry: int, row: int, columns: list[Squares]) -> tuple[int, int] | None:
    """The column and row Link comes out on beside stairs at (entry, row): the first open ground
    square below, left, right or above them that the exit's three row bits can name (rows 0 to 7);
    None when there is none."""
    for step_column, step_row in STAIRS_EXIT_SIDES:
        column, exit_row = entry + step_column, row + step_row
        if 0 <= column < len(columns) and exit_row in EXIT_ROWS and columns[column][exit_row] in OPEN_SQUARES:
            return column, exit_row
    return None


def screen_kind(layout: list[int], candidates: list[int], squares: dict[int, Squares], tables: Survey) -> int | None:
    """Step 2: the first secret square met in a candidate column once an own secret (a candidate
    whose table code is its own) has been seen, counting that column itself; None for a screen with
    no own secret, which is left as it is."""
    seen_own = False
    for entry in candidates:
        column = squares[layout[entry]]
        seen_own = seen_own or tables.secret[column] == layout[entry]
        if seen_own and secret_squares(column):
            return secret_squares(column)[0]
    return None


def clear(layout: list[int], candidates: list[int], squares: dict[int, Squares], tables: Survey) -> None:
    """Step 2: each candidate becomes the plain table's code for its plain form, where there is one."""
    for entry in candidates:
        plain = tables.plain.get(plain_form(squares[layout[entry]]))
        if plain is not None:
            layout[entry] = plain


def first_secret(column: Squares) -> tuple[int, int]:
    """The row and the square of a column's first secret square."""
    return next((row, square) for row, square in enumerate(column) if square in PLAIN_TWINS)


def accepts(layout: list[int], entry: int, kind: int, squares: dict[int, Squares], tables: Survey) -> bool:
    """Step 3's two tests on the secret column S the entry would take: S's kind is the screen's, and
    a square beside S's first secret square (above or below it in S, or at its row in the entries
    left and right as they now stand) is open ground."""
    secret = squares[tables.secret[squares[layout[entry]]]]
    if kind_of(secret) != kind:
        return False
    row, _square = first_secret(secret)
    beside = [secret[row - 1] if row > 0 else None, secret[row + 1] if row + 1 < len(secret) else None,
              squares[layout[entry - 1]][row], squares[layout[entry + 1]][row]]
    return any(square in OPEN_SQUARES for square in beside)


def move_the_cave_exit(screen: Screen, entry: int, wall_row: int, cleared: list[Squares], spawn_spots: bytes) -> None:
    """Step 4, a moved bombable rock wall: Link comes out of the cave at its column and row (the A
    byte's high nibble and the F byte's bits 2-0). Unless the F byte's bit 7 is set, the distance
    test: the first spawn spot standing on open ground (on the screen as step 2 left it) more than
    two columns from the wall passes when it is more than two rows from it; with none passing, the
    screen's monsters come in from the edges (F bit 3, which nothing clears)."""
    screen.exit_x_position = entry
    screen.exit_y_position = (wall_row - 1) & EXIT_ROW_MASK
    if screen.quest_visibility in QUEST_FIELD_HIGH_BIT:
        return
    for spot in spawn_spots:
        column, row = spot & LOW_NIBBLE, (spot >> NIBBLE_SHIFT) - SPAWN_ROW_OFFSET
        if cleared[column][row] not in OPEN_SQUARES or abs(column - entry) <= DISTANCE:
            continue
        if abs(row - wall_row) > DISTANCE:
            return
    screen.enemies_from_sides = True
