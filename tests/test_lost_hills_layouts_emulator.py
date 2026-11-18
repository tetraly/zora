"""Randomize Lost Hills' own layouts for $0B (asm/flags2/lost-hills, zora/rom/extra_layouts.py) in the
emulator: the routine sends layouts $7C-$7F to ZORA's table, so

  - Link walks off $0B's east edge onto $0C where Lost Hills opens it, in the second quest's look (the
    fountain, $7C) and the first's (the 1Q5 doorway, $7D), mirrored too (off $04's west edge onto $03);
  - $0B is drawn as $3C, which keeps the layout $0B copies, in every square column but the east edge.

On PRG0 and PRG1, with level encoding on, and with Music: Random (lozft's MMC3 ROM). Screens are measured
on the play area's nametable (rows 8-29: 22 rows of 32 tiles, a square 2 by 2)."""
from functools import cache

import pytest

from tests.emulator import OBJ_X, OBJ_Y, ROOM_ID, Button
from tests.needs import needs_base_rom
from tests.test_cave_takes_emulator import _music_assets
from tests.test_mirror_overworld_emulator import EAST_EDGE_X, OPEN_SQUARES, SQUARE, WALK_LIMIT, WEST_EDGE_X, playfield
from tests.test_progressive_emulator import Game
from tests.test_revision import prg1
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import MIRROR_OVERWORLD, OVERWORLD_QUEST, OverworldQuest, ThreeState
from zora.flags.presets import MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.extra_layouts import EAST_EDGE_COLUMN, OWN_LAYOUTS
from zora.rom.mirror_overworld import mirror_screen
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import Music, PlayerSettings
from zora.rom.vanilla_overworld.layouts import read_screen_layout

pytestmark = [needs_base_rom, pytest.mark.slow]

SEED = 7
LOST_HILLS = zora_flags.encode(ZoraFlags(randomize_lost_hills=ThreeState.ON))
SCREEN_11, SCREEN_12, SCREEN_60 = 0x0B, 0x0C, 0x3C
ROWS = 11
LEVEL_BLOCK_ATTRS_D = 0x69FE                # RAM: each overworld screen's layout number (bit 7 the monsters')
TOP_ROW_Y = 0x3D                         # Link's Y standing on the top row of squares (a square's top less 3)
LOOKS = {"2nd Quest": OverworldQuest.SECOND_QUEST, "1st Quest": OverworldQuest.FIRST_QUEST}


def flags(look: str, base: str = MVP_BASELINE_LEVEL_ENCODING_OFF, mirrored: bool = False) -> str:
    settings = decode(base).updated(options={OVERWORLD_QUEST.id: LOOKS[look]})
    if mirrored:
        settings = settings.updated(toggles={MIRROR_OVERWORLD.id: ThreeState.ON})
    return encode(settings)


@cache
def rom(look: str, on_prg1: bool = False, encoded: bool = False, mirrored: bool = False, music: bool = False) -> bytes:
    base = prg1() if on_prg1 else remember_repo_base_rom()
    settings = PlayerSettings(music=Music.RANDOM_STANDARD) if music else PlayerSettings()
    finished = generate_rom(flags(look, MVP_BASELINE if encoded else MVP_BASELINE_LEVEL_ENCODING_OFF, mirrored),
                            SEED, base, settings, zora_flag_string=LOST_HILLS).rom
    if not music:
        return finished
    from zora.rom.music.randomize import randomize_music
    return randomize_music(finished, base, _music_assets(), SEED).rom


@cache
def crossing_row(look: str) -> int:
    """The row of squares open on both sides of the edge from $0B to $0C (two squares on each side; the
    maze's one-square-high pass, where Link's lower half walks), read from the plain PRG0 build's layouts."""
    image = rom(look)
    screens = {screen.screen_num: screen for screen in parse_rom(image).overworld.screens}
    assert screens[SCREEN_11].screen_code in OWN_LAYOUTS.values()
    here = read_screen_layout(image, screens[SCREEN_11].screen_code)
    there = read_screen_layout(image, screens[SCREEN_12].screen_code)
    for row in range(ROWS):
        if all(here[column][row] in OPEN_SQUARES for column in (EAST_EDGE_COLUMN - 1, EAST_EDGE_COLUMN)) \
                and all(there[column][row] in OPEN_SQUARES for column in (0, 1)):
            return row
    raise AssertionError(f"{look}: no open crossing from $0B to $0C")


CASES = [
    pytest.param("2nd Quest", {}, id="2nd Quest"),
    pytest.param("1st Quest", {}, id="1st Quest"),
    pytest.param("2nd Quest", {"on_prg1": True}, id="2nd Quest PRG1",
                 marks=pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="no PRG1 ROM beside the base")),
    pytest.param("1st Quest", {"on_prg1": True}, id="1st Quest PRG1",
                 marks=pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="no PRG1 ROM beside the base")),
    pytest.param("2nd Quest", {"encoded": True}, id="2nd Quest level encoding"),
    pytest.param("2nd Quest", {"music": True}, id="2nd Quest Music Random"),
]


def walk(image: bytes, screen: int, row: int, x: int, button: Button, layout: int | None = None) -> int:
    """Link set on `screen` at (x, row), walking with `button` until the screen changes: the screen he
    reaches, or `screen` when he is still on it after WALK_LIMIT frames. With `layout`, the screen's
    layout number in RAM is that one while the screen is drawn."""
    game = Game(image)
    if layout is not None:
        game.emu[LEVEL_BLOCK_ATTRS_D + screen] = layout
    game.go_to_screen(screen)
    game.emu[OBJ_X], game.emu[OBJ_Y] = x, TOP_ROW_Y + row * SQUARE
    try:
        game.emu.run_until(lambda: game.emu[ROOM_ID] != screen, buttons=button, limit=WALK_LIMIT)
    except AssertionError:
        return screen
    return game.emu[ROOM_ID]


@pytest.mark.parametrize(("look", "options"), CASES)
def test_link_walks_from_0b_onto_0c(look: str, options: dict[str, bool]) -> None:
    reached = walk(rom(look, **options), SCREEN_11, crossing_row(look), EAST_EDGE_X, Button.RIGHT)
    assert reached == SCREEN_12


@pytest.mark.parametrize("look", list(LOOKS))
def test_the_shared_layout_shuts_0c_off(look: str) -> None:
    """The check above fails without the routine's layouts: $0B drawn from the layout it shares with $3C
    (its layout number set back in RAM) keeps Link on $0B."""
    shared = {own: shared for shared, own in OWN_LAYOUTS.items()}
    image = rom(look)
    own = next(screen.screen_code for screen in parse_rom(image).overworld.screens if screen.screen_num == SCREEN_11)
    assert walk(image, SCREEN_11, crossing_row(look), EAST_EDGE_X, Button.RIGHT, layout=shared[own]) == SCREEN_11


@pytest.mark.parametrize("look", list(LOOKS))
def test_mirrored_link_walks_west_onto_0c_s_mirror(look: str) -> None:
    image = rom(look, mirrored=True)
    reached = walk(image, mirror_screen(SCREEN_11), crossing_row(look), WEST_EDGE_X, Button.LEFT)
    assert reached == mirror_screen(SCREEN_12)


@pytest.mark.parametrize(("look", "options"), CASES)
def test_0b_is_drawn_as_3c_but_its_east_edge(look: str, options: dict[str, bool]) -> None:
    image = rom(look, **options)
    own, shared = playfield(image, SCREEN_11), playfield(image, SCREEN_60)
    for row in range(ROWS):
        assert own[row][:EAST_EDGE_COLUMN] == shared[row][:EAST_EDGE_COLUMN], row
    assert any(own[row][EAST_EDGE_COLUMN] != shared[row][EAST_EDGE_COLUMN] for row in range(ROWS))
