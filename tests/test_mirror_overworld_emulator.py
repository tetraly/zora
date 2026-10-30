"""Mirror Overworld (B06; overworld-behavior.md OW-MIR-01 to OW-MIR-05, hints-behavior.md HT-MIR-01) in the
emulator, on CP-5 against CP-5 with B06 on, the same seed (the same world, flipped), made from PRG0 and from PRG1:

  - Walking: where Link walks off screen s's east edge onto s + 1 in the unmirrored seed, he walks off
    m(s)'s west edge onto m(s + 1) in the mirrored one, and both screens are drawn as each other's
    mirror image (most squares match; squares with a left and a right form are each other's twin).
  - A cave: entering a cave from its mirrored screen shows the same cave, and leaving it puts Link on
    the mirrored exit column (X becomes 240 - X).
  - A hint: a dungeon person whose text names where a level lies names, in the mirrored seed, the region
    of that level's door after the flip (HT-MIR-01), where the unmirrored seed's names the region before it.
  - The monsters of an overworld screen first appear on the flipped spots (OW-MIR-05's spawn copies).

Screens are measured on the play area's nametable (rows 8-29: 22 rows of 32 tiles, a square 2 by 2)."""
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID, Button
from tests.needs import needs_base_rom
from tests.test_asnb_emulator import MONSTER_SLOTS
from tests.test_assignment_emulator import Console
from tests.test_progressive_emulator import CAVE_MODE, Game
from tests.test_revision import prg1
from zora.generate.pipeline import generate_rom
from zora.generate.steps.hint_text import REGION_TABLE, region_phrase
from zora.generate.steps.mixed_overworld_quest import door_screen
from zora.model.enums import Destination
from zora.model.overworld import Screen
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.mirror_overworld import mirror_screen
from zora.rom.parse.rom_file import parse_rom
from zora.rom.text_encoding import BYTE_TO_CHAR, CHAR_TO_BYTE, QUOTE_CHAR_MASK
from zora.rom.vanilla_overworld.layouts import read_overworld_layouts

pytestmark = [needs_base_rom, pytest.mark.slow]

CP5 = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A"
B06_ON = "8hq4BeR1JXo89c2WXnefpphDg!UJ3A"
SEED = 1
OPEN_SQUARES = frozenset({0x0E, 0x07})
COLUMNS, ROWS = 16, 11
SQUARE = 0x10
PLAY_AREA_TOP = 0x40                     # Link's Y on the top row of squares
EAST_EDGE_X, WEST_EDGE_X = 0xE0, 0x10
WALK_LIMIT = 300
SCREEN_X_SPAN = 0xF0                     # a square column c at X 16c becomes 15 - c, at 240 - X
PLAYFIELD_START, PLAYFIELD_ROWS, TILES_PER_ROW = 0x2100, 22, 32
MIRROR_IMAGE_AT_LEAST = 0.75             # of the squares drawn the same, column c against 15 - c
TEXT_FRAMES = 400                        # long enough for the longest text to be written out
SPAWN_FRAMES = 90
CAVE_DESTINATIONS = (Destination.WHITE_SWORD_CAVE, Destination.MAGICAL_SWORD_CAVE)
# Each test on both releases: the flip is written in PRG0's layout and goes to PRG1's places with the rest
RELEASES = pytest.mark.parametrize("on_prg1", [
    pytest.param(False, id="PRG0"),
    pytest.param(True, id="PRG1", marks=pytest.mark.skipif(not PRG1_ROM_PATH.exists(),
                                                           reason="no PRG1 ROM beside the base"))])


@cache
def rom(flags: str, on_prg1: bool) -> bytes:
    return generate_rom(flags, SEED, prg1() if on_prg1 else remember_repo_base_rom()).rom


def squares(image: bytes, screen: Screen) -> list[tuple[int, ...]]:
    layouts = read_overworld_layouts(image, b"")
    return [layouts.squares[code] for code in layouts.layouts[screen.screen_code]]


def walkable_crossing(image: bytes) -> tuple[int, int]:
    """(screen s, row): rows `row` and `row` + 1 open on both sides of the edge between s and s + 1,
    two screens of the same row of the map."""
    screens = {screen.screen_num: screen for screen in parse_rom(image).overworld.screens}
    for number, screen in sorted(screens.items()):
        east = screens.get(number + 1)
        if east is None or (number + 1) % COLUMNS == 0:
            continue
        here, there = squares(image, screen), squares(image, east)
        for row in range(2, ROWS - 2):
            # Link stands across two rows of squares (his Y sits a few pixels below a row's top)
            rows = (row, row + 1)
            if all(here[column][r] in OPEN_SQUARES for column in (COLUMNS - 2, COLUMNS - 1) for r in rows) and \
                    all(there[column][r] in OPEN_SQUARES for column in (0, 1) for r in rows):
                return number, row
    raise AssertionError("no open crossing between two screens")


def walk(image: bytes, screen: int, row: int, x: int, button: Button) -> tuple[int, int]:
    """Link set on `screen` at (x, row), walking with `button` until the screen changes: the screen he
    reaches and his X there."""
    game = Game(image)
    game.go_to_screen(screen)
    game.emu[OBJ_X], game.emu[OBJ_Y] = x, PLAY_AREA_TOP + row * SQUARE
    game.emu.run_until(lambda: game.emu[ROOM_ID] != screen, buttons=button, limit=WALK_LIMIT)
    game.emu.run(30)
    return game.emu[ROOM_ID], game.emu[OBJ_X]


def playfield(image: bytes, screen: int) -> list[list[bytes]]:
    """The screen's squares as drawn: per row of squares, each square's four tiles."""
    game = Game(image)
    game.go_to_screen(screen)
    game.emu.run(60)
    tiles = game.emu.nametable(PLAYFIELD_START, PLAYFIELD_ROWS * TILES_PER_ROW)
    rows = []
    for square_row in range(ROWS):
        top = (2 * square_row) * TILES_PER_ROW
        bottom = top + TILES_PER_ROW
        rows.append([bytes(tiles[top + 2 * column:top + 2 * column + 2]
                           + tiles[bottom + 2 * column:bottom + 2 * column + 2]) for column in range(COLUMNS)])
    return rows


@RELEASES
def test_walking_east_unmirrored_is_walking_west_mirrored(on_prg1: bool) -> None:
    screen, row = walkable_crossing(rom(CP5, on_prg1))
    reached, x = walk(rom(CP5, on_prg1), screen, row, EAST_EDGE_X, Button.RIGHT)
    assert reached == screen + 1
    mirrored_reached, mirrored_x = walk(rom(B06_ON, on_prg1), mirror_screen(screen), row, WEST_EDGE_X, Button.LEFT)
    assert mirrored_reached == mirror_screen(screen + 1)
    assert abs(mirrored_x - (SCREEN_X_SPAN - x)) <= SQUARE // 2, (x, mirrored_x)
    drawn = playfield(rom(CP5, on_prg1), screen + 1)
    mirrored = playfield(rom(B06_ON, on_prg1), mirror_screen(screen + 1))
    same = sum(drawn[r][c] == mirrored[r][COLUMNS - 1 - c] for r in range(ROWS) for c in range(COLUMNS))
    assert same >= MIRROR_IMAGE_AT_LEAST * ROWS * COLUMNS, same


@RELEASES
@pytest.mark.parametrize("destination", CAVE_DESTINATIONS, ids=lambda d: d.name.lower())
def test_a_cave_is_entered_and_left_on_its_mirrored_screen(destination: Destination, on_prg1: bool) -> None:
    def visit(image: bytes) -> tuple[int, list[int], int]:
        screen = next(s.screen_num for s in parse_rom(image).overworld.screens if s.destination == destination)
        game = Game(image)
        game.go_to_screen(screen)
        game.start_mode(CAVE_MODE)
        game.wait_for_play(CAVE_MODE)
        game.emu.run(60)
        wares = game.wares()
        game.leave_cave()
        return screen, wares, game.emu[OBJ_X]
    screen, wares, x = visit(rom(CP5, on_prg1))
    mirrored_screen, mirrored_wares, mirrored_x = visit(rom(B06_ON, on_prg1))
    assert mirrored_screen == mirror_screen(screen) and mirrored_wares == wares
    assert mirrored_x == SCREEN_X_SPAN - x, (x, mirrored_x)


def shown_text(image: bytes, level: int, room: int) -> str:
    console = Console(image)
    console.enter_room(level, room)
    console.emu.run(TEXT_FRAMES)
    tiles = console.emu.nametable(PLAYFIELD_START, PLAYFIELD_ROWS * TILES_PER_ROW)
    return " ".join("".join(BYTE_TO_CHAR.get(tile & QUOTE_CHAR_MASK, " ") for tile in tiles).split())


@RELEASES
def test_a_dungeon_hint_names_the_door_s_region_after_the_flip(on_prg1: bool) -> None:
    """The first person room whose text names where a level lies, read off the screen in both seeds."""
    off, on = parse_rom(rom(CP5, on_prg1)), parse_rom(rom(B06_ON, on_prg1))
    for level in off.levels:
        for room in level.rooms:
            if not room.is_person_room:
                continue
            text = shown_text(rom(CP5, on_prg1), level.level_num, room.room_num)
            if "LIES" not in text:
                continue
            named = int(text.split("LEVEL-")[1][0])
            door_off, door_on = door_screen(off.overworld, named), door_screen(on.overworld, named)
            assert door_off is not None and door_on == mirror_screen(door_off)
            if " ".join(region_phrase(REGION_TABLE[door_off]).split()) not in text:
                continue            # a deceiving hint (mixed hints): the flip does not decide its region
            mirrored = shown_text(rom(B06_ON, on_prg1), level.level_num, room.room_num)
            assert " ".join(region_phrase(REGION_TABLE[door_on]).split()) in mirrored, (text, mirrored)
            return
    raise AssertionError("no person room of the seed names where a level lies")


def first_spots(image: bytes, screen: int) -> list[tuple[int, int]]:
    """Each monster's place on the first frame it is there, walking onto the screen from the north."""
    game = Game(image)
    game.go_to_screen(screen)
    first: dict[int, tuple[int, int]] = {}
    for _frame in range(SPAWN_FRAMES):
        game.emu.run(1)
        for slot in MONSTER_SLOTS:
            if game.emu[OBJ_TYPE + slot] and slot not in first:
                first[slot] = (game.emu[OBJ_X + slot], game.emu[OBJ_Y + slot])
    return sorted(first.values())


@RELEASES
def test_monsters_appear_on_the_flipped_spots(on_prg1: bool) -> None:
    """OW-MIR-05: the start screen's monsters (the same group in both seeds) come in at spots whose
    columns are flipped: their X becomes 240 - X."""
    start = parse_rom(rom(CP5, on_prg1)).overworld.start_screen
    spots, mirrored = first_spots(rom(CP5, on_prg1), start), first_spots(rom(B06_ON, on_prg1), mirror_screen(start))
    assert spots and len(spots) == len(mirrored)
    assert sorted((SCREEN_X_SPAN - x, y) for x, y in spots) == mirrored, (spots, mirrored)


@RELEASES
def test_a_new_game_starts_on_the_mirrored_start_screen(on_prg1: bool) -> None:
    """OW-MIR-03 item 1."""
    start = parse_rom(rom(CP5, on_prg1)).overworld.start_screen
    console = Console(rom(B06_ON, on_prg1))
    assert (console.emu[ROOM_ID], console.emu[CUR_LEVEL]) == (mirror_screen(start), 0)


TRIFORCE_CAPTION = bytes(CHAR_TO_BYTE[letter] for letter in "TRIFORCE")


@RELEASES
def test_the_item_screen_shows_the_triforce_caption(on_prg1: bool) -> None:
    """OW-MIR-05 item 2: the caption's record no longer ends on table A's first byte, so the item screen
    draws TRIFORCE in the mirrored seed as in the unmirrored one."""
    for image in (rom(CP5, on_prg1), rom(B06_ON, on_prg1)):
        game = Game(image)
        game.go_to_screen(parse_rom(image).overworld.start_screen)
        game.emu.run(60)
        game.emu.open_item_screen()
        game.emu.run(30)
        assert TRIFORCE_CAPTION in game.emu.ciram()
