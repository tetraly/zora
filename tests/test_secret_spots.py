"""Change Secret Spots (B05; overworld-behavior.md OW-ENTR-01) on its Check string: 54 screens hold one
secret square each, of the kind PRG0's screen holds; some move; a moved bombable wall's exit column and
row follow it, and moved stairs' exit is the square beside them (ZORA's rule), or PRG0's where no
square beside them can be named; with B05 off nothing moves."""
import pytest

from tests.needs import needs_base_rom
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.generate.steps.change_secret_spots import (BOMBABLE_ROCK_WALL, BURNABLE_TREE, EXIT_ROWS, PLAIN_TWINS,
                                                     first_secret, move_the_stairs_exit, stairs_exit, survey)
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.vanilla_overworld.layouts import read_overworld_layouts

pytestmark = needs_base_rom

B05_ON = "8hq4BeR1JXo89KDXqv36FsuRUlUJ3A"
SECRET_SCREENS = 54
EXIT_ROW_MASK = 0x07
OPEN, BLOCKED = 0x0E, 0x00
COLUMNS, ROWS = 16, 11


def secrets(rom: bytes) -> dict[int, tuple[int, int, int]]:
    layouts = read_overworld_layouts(rom, b"")
    found = {}
    for screen in parse_rom(rom).overworld.screens:
        spots = [(column, row, square) for column, code in enumerate(layouts.layouts[screen.screen_code])
                 for row, square in enumerate(layouts.squares[code]) if square in PLAIN_TWINS]
        if spots:
            assert len(spots) == 1, screen.screen_num
            found[screen.screen_num] = spots[0]
    return found


@pytest.mark.parametrize("seed", (1, 2, 3))
def test_secrets_move_along_their_screens(seed: int) -> None:
    base = remember_repo_base_rom()
    before = secrets(base)
    rom = generate_rom(B05_ON, seed, base).rom
    after = secrets(rom)
    assert len(after) == SECRET_SCREENS and after.keys() == before.keys()
    assert all(after[screen][2] == before[screen][2] for screen in after)
    assert any(after[screen][:2] != before[screen][:2] for screen in after)
    screens = {screen.screen_num: screen for screen in parse_rom(rom).overworld.screens}
    old_screens = {screen.screen_num: screen for screen in parse_rom(base).overworld.screens}
    layouts = read_overworld_layouts(rom, b"")
    for number, (column, row, square) in after.items():
        exit_bytes = screens[number].exit_x_position, screens[number].exit_y_position
        if square == BOMBABLE_ROCK_WALL:
            assert exit_bytes == (column, (row - 1) & EXIT_ROW_MASK)
        elif (column, row) != before[number][:2]:
            columns = [layouts.squares[code] for code in layouts.layouts[screens[number].screen_code]]
            old = old_screens[number]
            assert exit_bytes == (stairs_exit(column, row, columns) or (old.exit_x_position, old.exit_y_position))


def test_off_moves_nothing() -> None:
    base = remember_repo_base_rom()
    assert secrets(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base).rom) == secrets(base)


def columns_with(stairs: tuple[int, int], open_squares: list[tuple[int, int]]) -> list[tuple[int, ...]]:
    """A screen of blocked squares, stairs at (column, row), and the open squares given."""
    return [tuple(PLAIN_TWINS[BURNABLE_TREE] if (column, row) == stairs else OPEN if (column, row) in open_squares
                  else BLOCKED for row in range(ROWS)) for column in range(COLUMNS)]


def test_stairs_exit_takes_the_first_open_side_it_can_name() -> None:
    """Below, left, right, above; the exit's three row bits name rows 0 to 7 only."""
    around = [(5, 4), (4, 3), (6, 3), (5, 2)]
    assert stairs_exit(5, 3, columns_with((5, 3), around)) == (5, 4)
    assert stairs_exit(5, 3, columns_with((5, 3), around[1:])) == (4, 3)
    assert stairs_exit(5, 7, columns_with((5, 7), [(5, 8), (5, 6)])) == (5, 6)


@pytest.mark.parametrize(("stairs", "open_squares"), (
    ((5, 7), [(5, 8)]),                                     # a row-7 tree open only below, on row 8
    ((5, 9), [(5, 10), (4, 9), (6, 9), (5, 8)]),            # stairs on row 9: no side on rows 0-7
    ((5, 10), [(4, 10), (6, 10), (5, 9)]),
    ((5, 3), []),                                           # walled in
), ids=["row-7-open-below", "row-9", "row-10", "walled-in"])
def test_moved_stairs_with_no_nameable_side_keep_prg0s_exit(stairs: tuple[int, int],
                                                             open_squares: list[tuple[int, int]]) -> None:
    """The deliberate fallback (docs/deviations.md): the spec's own rule, PRG0's exit bytes."""
    screen = parse_rom(remember_repo_base_rom()).overworld.screens[0x0A]
    exit_bytes = screen.exit_x_position, screen.exit_y_position
    assert not move_the_stairs_exit(screen, *stairs, columns_with(stairs, open_squares))
    assert (screen.exit_x_position, screen.exit_y_position) == exit_bytes


def test_placeable_stairs_sit_on_rows_the_exit_can_name() -> None:
    """Only PRG0's own secret columns are placed, and theirs put stairs on rows 0 to 7 (2, 5, 6 and
    7): the fallback is left with a row-7 stairs square open only below. Measured: none in 1000 seeds
    (10,443 moved stairs), temp/b05-fallback.py."""
    base = remember_repo_base_rom()
    layouts = read_overworld_layouts(base, b"")
    screens = sorted(parse_rom(base).overworld.screens, key=lambda screen: screen.screen_num)
    tables = survey([list(layout) for layout in layouts.layouts], screens, layouts.squares)
    rows = {first_secret(layouts.squares[code]) for code in set(tables.secret.values())}
    assert all(row in EXIT_ROWS for row, square in rows if square != BOMBABLE_ROCK_WALL), rows
