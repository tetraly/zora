"""Start Screen: Full Start Shuffle (C04 = 2, OW-START-02) and Wood Sword Screen (C04 = 3,
OW-START-03). The Checks over 1,000 seeds: `python3 scripts/compare_corpus.py --set start-full`
and `--set start-wsword`."""
import copy
from functools import cache

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import START_SCREEN, StartScreen
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, plan
from zora.generate.rng import Rng
from zora.generate.steps.shuffle_start_screen import (
    FULL_START_SCREENS,
    START_ROWS,
    START_SCREENS,
    shuffle_start_screen,
    start_on_wood_sword_screen,
    start_y,
)
from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.start_screens import FULL_START_FLAGS, WOOD_SWORD_START_FLAGS, wood_sword_start

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

SEEDS = (1, 2, 3, 4)
NEVER_START = frozenset({14, 35, 47, 69, 98})
ZERO_EXIT_SCREENS = frozenset({8, 23, 42, 46, 50, 53, 54, 56, 57, 62, 63, 64, 65, 67, 76, 79, 80, 82, 84, 85, 87,
                               89, 90, 92, 93, 95, 97, 101, 105, 115, 122, 126, 127})


@cache
def _base() -> bytes:
    return remember_repo_base_rom()


@cache
def _prg0() -> GameWorld:
    return parse_rom(_base())


@cache
def finished(flags: str, seed: int) -> GameWorld:
    return parse_rom(generate_rom(flags, seed, _base()).rom)


def test_the_corpus_strings_are_cp5_with_c04() -> None:
    for flags, value in ((FULL_START_FLAGS, StartScreen.FULL_SHUFFLE),
                         (WOOD_SWORD_START_FLAGS, StartScreen.WOODEN_SWORD_SCREEN)):
        settings = decode(flags)
        assert settings.option(START_SCREEN) == value
        assert encode(settings.updated(options={"C04": StartScreen.EASY_SHUFFLE})) == MVP_BASELINE_LEVEL_ENCODING_OFF
    assert plan(FULL_START_FLAGS, 1).alternatives.full_start_shuffle
    assert plan(WOOD_SWORD_START_FLAGS, 1).alternatives.start_on_wood_sword_screen


def test_the_90_screens_are_the_128_less_the_left_out_ones() -> None:
    """OW-START-02: less 14, 35, 47, 69, 98 and the 33 screens whose exit X is 0 (screen 36's is
    set to 4 by the Armos pass first); the 51 of OW-START-01 among them."""
    assert FULL_START_SCREENS == frozenset(range(128)) - NEVER_START - ZERO_EXIT_SCREENS
    assert len(FULL_START_SCREENS) == 90 and START_SCREENS <= FULL_START_SCREENS
    zero_exit = {screen.screen_num for screen in _prg0().overworld.screens if screen.exit_x_position == 0}
    assert zero_exit == ZERO_EXIT_SCREENS | {36}


def test_the_start_rows_are_the_full_table() -> None:
    """OW-START-02's w(S); OW-START-01's eight exceptions keep their values."""
    assert {screen: START_ROWS[screen] for screen in (44, 66, 109, 110, 114, 117, 118, 121)} == {
        44: 10, 66: 10, 109: 5, 110: 7, 114: 5, 117: 7, 118: 7, 121: 7}
    assert start_y(9) == 0x7D and start_y(10) == 0xAD and start_y(82) == 0x5D and start_y(0) == 0x8D


def test_the_full_draw_reaches_the_new_screens() -> None:
    drawn = {shuffle_start_screen(Rng(seed), FULL_START_SCREENS).screen for seed in range(400)}
    assert drawn <= FULL_START_SCREENS and drawn - START_SCREENS


@pytest.mark.parametrize("cave_screen, start", [(0x5E, 0x5E), (14, 30), (47, 63), (69, 85), (35, 51), (98, 114)])
def test_the_wood_sword_start_follows_code_16(cave_screen: int, start: int) -> None:
    """OW-START-03: the lowest screen with code 16; 14, 47 and 69 give the screen below, and so do
    35 and 98 (the entry's recommendation for the B03 cases, in place of the original randomizer's quirk)."""
    overworld = copy.deepcopy(_prg0().overworld)
    for screen in overworld.screens:
        if screen.destination == Destination.WOOD_SWORD_CAVE:
            screen.destination = Destination.NONE
    overworld.screens[cave_screen].destination = Destination.WOOD_SWORD_CAVE
    assert start_on_wood_sword_screen(overworld, Rng(1)).screen == start


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("flags", [FULL_START_FLAGS, WOOD_SWORD_START_FLAGS])
def test_finished_roms(flags: str, seed: int) -> None:
    """The start screen is a listed one (C04 = 2) or the wooden-sword screen (C04 = 3), and Link's
    start Y byte is the formula's."""
    world = finished(flags, seed)
    start = world.overworld.start_screen
    assert world.overworld.start_position_y == start_y(start)
    if flags == FULL_START_FLAGS:
        assert start in FULL_START_SCREENS
    else:
        assert all(wood_sword_start(world)[key] for key in ("code 16 once", "S follows code 16"))
