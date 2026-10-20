"""Start Screen: Full Start Shuffle (C04 = 2, OW-START-02) and Wood Sword Screen (C04 = 3,
OW-START-03). The Checks over 1,000 seeds: `python3 scripts/compare_corpus.py --set start-full`
and `--set start-wsword`."""
import copy
from functools import cache

import pytest

from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import START_SCREEN, StartScreen, ThreeState
from zora.flags.zora_flags import ZoraFlags
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, plan
from zora.generate.rng import Rng
from zora.generate.steps import overworld_gates as gates
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

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

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
def finished(flags: str, seed: int, zora_flag_string: str = "") -> GameWorld:
    return parse_rom(generate_rom(flags, seed, _base(), zora_flag_string=zora_flag_string).rom)


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


# The screens past each randomized maze, by the map (tests/test_overworld_gates.py derives them):
# $72's cave opens only to $71.
PAST_LOST_HILLS = frozenset({0x0B, 0x0C, 0x0D})
PAST_DEAD_WOODS = frozenset({0x70, 0x71, 0x72})


# Seeds whose start-screen draw landed on a screen an overworld gate gates or walls in before the
# draw left those out (raft seed 8: $34; bracelet seed 7: $01; Lost Hills seed 36: $0B; Dead Woods
# seed 129: $70 and seed 58: $72, and with Easy start shuffle seed 16: $71 and seed 15: $72);
# Extra Power Bracelet Blocks with B04 off, which it needs.
@pytest.mark.parametrize(("flag", "z1r_flags", "seed", "screens", "barred"), [
    ("extra_raft_blocks", FULL_START_FLAGS, 8, FULL_START_SCREENS, gates.RAFT_ENCLOSED_SCREENS),
    ("extra_power_bracelet_blocks", encode(decode(FULL_START_FLAGS).updated(toggles={"B04": ThreeState.OFF})), 7,
     FULL_START_SCREENS, gates.BRACELET_ENCLOSED_SCREENS),
    ("randomize_lost_hills", FULL_START_FLAGS, 36, FULL_START_SCREENS, PAST_LOST_HILLS),
    ("randomize_dead_woods", FULL_START_FLAGS, 129, FULL_START_SCREENS, PAST_DEAD_WOODS),
    ("randomize_dead_woods", FULL_START_FLAGS, 58, FULL_START_SCREENS, PAST_DEAD_WOODS),
    ("randomize_dead_woods", MVP_BASELINE_LEVEL_ENCODING_OFF, 16, START_SCREENS, PAST_DEAD_WOODS),
    ("randomize_dead_woods", MVP_BASELINE_LEVEL_ENCODING_OFF, 15, START_SCREENS, PAST_DEAD_WOODS)])
def test_the_start_is_never_past_an_overworld_gate(flag: str, z1r_flags: str, seed: int, screens: frozenset[int],
                                                  barred: frozenset[int]) -> None:
    """With a ZORA overworld gate on, the start-screen draw leaves out the screens it gates or walls
    in (OverworldGates.start_barred), as OW-START-02 leaves out PRG0's raft islands: Link never
    starts shut in, or past a maze he has not solved (owner decision, 2026-10-13)."""
    world = finished(z1r_flags, seed, zora_flags.encode(ZoraFlags(**{flag: ThreeState.ON})))  # type: ignore[arg-type]
    start = world.overworld.start_screen
    assert start in screens - barred
    assert world.overworld.start_position_y == start_y(start)


def test_dead_woods_keeps_the_west_half_as_a_start() -> None:
    """Only the screens past each maze are left out (owner decision, 2026-10-13); the west half,
    which the logic gates by the ladder, stays in the draw."""
    barred = gates.OverworldGates(lost_hills=True, dead_woods=True).start_barred()
    assert barred == PAST_LOST_HILLS | PAST_DEAD_WOODS
    assert not barred & gates.DEAD_WOODS_WEST
