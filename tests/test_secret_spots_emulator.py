"""Change Secret Spots (B05; overworld-behavior.md OW-ENTR-01) in the emulator and on the finished
layouts, on its Check string (CP-5 with B05 on), the spec's three in-play questions:

  - Where Link comes out: on a screen whose bombable rock wall moved, leaving its cave puts Link on the
    wall's square (the exit bytes follow the wall). A moved rock's, tree's or gravestone's screen keeps
    PRG0's exit bytes in the spec; ZORA moves the exit with them (docs/deviations.md), so Link comes
    out next to the new stairs.
  - The edge-monster bit: on a screen whose distance test failed, the monsters first appear elsewhere
    than with the bit cleared.
  - Reach: every moved secret has an open ground square beside it (step 3's test) in the same open
    region as one beside PRG0's secret on that screen, or in one reaching the screen's edge.

Measured on seeds 1-3; a summary of the stairs' distances goes to temp/emulator/secret_spots.txt."""
from collections import deque
from functools import cache
from pathlib import Path

import pytest

from tests.emulator import CUR_LEVEL, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID
from tests.needs import needs_base_rom
from tests.test_asnb_emulator import MONSTER_SLOTS
from tests.test_progressive_emulator import LEAVE_CAVE_MODE, UNDERGROUND_EXIT_TYPE, Game
from zora.generate.pipeline import generate_rom
from zora.generate.steps.change_secret_spots import BOMBABLE_ROCK_WALL, OPEN_SQUARES, PLAIN_TWINS
from zora.model.overworld import Screen
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom.vanilla_overworld.layouts import read_overworld_layouts

pytestmark = [needs_base_rom, pytest.mark.slow]

B05_ON = "8hq4BeR1JXo89KDXqv36FsuRUlUJ3A"       # OW-ENTR-01's Check string
SEEDS = (1, 2, 3)
SQUARE = 0x10
PLAY_AREA_TOP = 0x40                           # Link's Y on the top row of squares
ROWS, COLUMNS = 11, 16
SPAWN_FRAMES = 90
REPORT = Path(__file__).resolve().parent.parent / "temp" / "emulator" / "secret_spots.txt"


@cache
def rom(seed: int) -> bytes:
    return generate_rom(B05_ON, seed, remember_repo_base_rom()).rom


def secret_at(rom_bytes: bytes, screen: Screen) -> tuple[int, int, int] | None:
    """The screen's secret square on its finished layout: (column, row, square)."""
    layouts = read_overworld_layouts(rom_bytes, b"")
    for column, code in enumerate(layouts.layouts[screen.screen_code]):
        for row, square in enumerate(layouts.squares[code]):
            if square in PLAIN_TWINS:
                return column, row, square
    return None


@cache
def moved(seed: int) -> list[tuple[Screen, tuple[int, int, int]]]:
    base = remember_repo_base_rom()
    before = {screen.screen_num: secret_at(base, screen) for screen in parse_rom(base).overworld.screens}
    found = []
    for screen in parse_rom(rom(seed)).overworld.screens:
        spot, old = secret_at(rom(seed), screen), before.get(screen.screen_num)
        if spot is not None and old is not None and spot[:2] != old[:2]:
            found.append((screen, spot))
    return found


def come_out(seed: int, screen: Screen) -> tuple[int, int]:
    game = Game(rom(seed))
    game.go_to_screen(screen.screen_num)
    return game.emu[OBJ_X], game.emu[OBJ_Y]


@pytest.mark.parametrize("seed", SEEDS)
def test_link_comes_out_of_a_moved_wall_on_the_wall(seed: int) -> None:
    walls = [(screen, spot) for screen, spot in moved(seed) if spot[2] == BOMBABLE_ROCK_WALL]
    assert walls
    for screen, (column, row, _square) in walls:
        x, y = come_out(seed, screen)
        assert x // SQUARE == column, (screen.screen_num, x, column)
        assert abs((y - PLAY_AREA_TOP) // SQUARE - row) <= 1, (screen.screen_num, y, row)


def test_link_comes_out_beside_moved_stairs() -> None:
    """ZORA's rule (docs/deviations.md): a moved rock's, tree's or gravestone's stairs take the exit with
    them, so Link comes out on a square next to the stairs. Each case goes to the report."""
    lines, far = [], []
    for seed in SEEDS:
        for screen, (column, row, square) in moved(seed):
            if square == BOMBABLE_ROCK_WALL:
                continue
            x, y = come_out(seed, screen)
            distance = abs(x // SQUARE - column) + abs((y - PLAY_AREA_TOP) // SQUARE - row)
            lines.append(f"seed {seed} screen ${screen.screen_num:02X} square ${square:02X}: stairs at column "
                         f"{column} row {row}, Link comes out at column {x // SQUARE} row "
                         f"{(y - PLAY_AREA_TOP) // SQUARE}, {distance} squares away")
            if distance > 1:
                far.append(lines[-1])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")
    assert lines and not far, far


def first_positions(rom_bytes: bytes, screen_num: int) -> list[tuple[int, int]]:
    """Each monster's place on the first frame it is there, coming out of the screen's cave."""
    game = Game(rom_bytes)
    game.emu[ROOM_ID], game.emu[CUR_LEVEL], game.emu[UNDERGROUND_EXIT_TYPE] = screen_num, 0, 1
    game.start_mode(LEAVE_CAVE_MODE)
    first: dict[int, tuple[int, int]] = {}
    for _frame in range(SPAWN_FRAMES):
        game.emu.run(1)
        for slot in MONSTER_SLOTS:
            if game.emu[OBJ_TYPE + slot] and slot not in first:
                first[slot] = (game.emu[OBJ_X + slot], game.emu[OBJ_Y + slot])
    return list(first.values())


@pytest.mark.parametrize("seed", SEEDS)
def test_monsters_come_from_the_edges_where_the_distance_test_failed(seed: int) -> None:
    """The edge bit changes where the screen's monsters first appear (coming out of the cave): the same
    screen with the bit cleared places them elsewhere. (Coming out of a cave does not show them at the
    edges: the game brings them in from the edges as Link walks onto the screen, not checked here.)"""
    edge_screens = [screen for screen, spot in moved(seed) if screen.enemies_from_sides and spot[2] == BOMBABLE_ROCK_WALL]
    for screen in edge_screens:
        with_bit = first_positions(rom(seed), screen.screen_num)
        world = parse_rom(rom(seed))
        next(other for other in world.overworld.screens if other.screen_num == screen.screen_num).enemies_from_sides = False
        without = first_positions(serialize_to_rom(world, rom(seed)), screen.screen_num)
        assert with_bit != without, (screen.screen_num, with_bit)


def regions(squares: list[tuple[int, ...]]) -> dict[tuple[int, int], int]:
    """Each open square's region of open squares (four-way)."""
    region: dict[tuple[int, int], int] = {}
    for column in range(COLUMNS):
        for row in range(ROWS):
            if squares[column][row] not in OPEN_SQUARES or (column, row) in region:
                continue
            label, queue = len(region), deque([(column, row)])
            region[(column, row)] = label
            while queue:
                here = queue.popleft()
                for step_column, step_row in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nxt = (here[0] + step_column, here[1] + step_row)
                    if (0 <= nxt[0] < COLUMNS and 0 <= nxt[1] < ROWS and nxt not in region
                            and squares[nxt[0]][nxt[1]] in OPEN_SQUARES):
                        region[nxt] = label
                        queue.append(nxt)
    return region


def open_beside(squares: list[tuple[int, ...]], column: int, row: int) -> list[tuple[int, int]]:
    return [(column + dc, row + dr) for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if 0 <= column + dc < COLUMNS and 0 <= row + dr < ROWS and squares[column + dc][row + dr] in OPEN_SQUARES]


@pytest.mark.parametrize("seed", SEEDS)
def test_every_moved_secret_opens_onto_ground_its_old_place_did(seed: int) -> None:
    """Every moved secret has an open square beside it (step 3's test), in the same open region as
    one beside PRG0's secret on that screen, or one reaching the screen's edge: Link reaches it
    wherever he reached the old one."""
    base = remember_repo_base_rom()
    old = {screen.screen_num: secret_at(base, screen) for screen in parse_rom(base).overworld.screens}
    layouts = read_overworld_layouts(rom(seed), b"")
    for screen, (column, row, _square) in moved(seed):
        squares = [layouts.squares[code] for code in layouts.layouts[screen.screen_code]]
        region = regions(squares)
        beside = open_beside(squares, column, row)
        assert beside, f"screen ${screen.screen_num:02X}: no open square beside its secret"
        old_spot = old[screen.screen_num]
        assert old_spot is not None
        old_regions = {region[spot] for spot in open_beside(squares, old_spot[0], old_spot[1])}
        edge_regions = {label for (spot_column, spot_row), label in region.items()
                        if spot_column in (0, COLUMNS - 1) or spot_row in (0, ROWS - 1)}
        assert {region[spot] for spot in beside} & (old_regions | edge_regions), f"screen ${screen.screen_num:02X}"
