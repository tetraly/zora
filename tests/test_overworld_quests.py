"""Overworld Quest: 2nd Quest (C01 = 1), Mixed Quest - 2nd (C01 = 3) and Random (C01 = 4)
(overworld-behavior.md OW-QST-01 to OW-QST-06). The Checks over 1,000 seeds: `python3
scripts/compare_corpus.py --set quest2`, `--set mixed2` and `--set quest-random`. That screens $0B
and $42 cannot be entered under 2nd Quest was checked in the emulator (the recorder reveals neither;
the 2026-10-10 report to the owner)."""
import copy
from functools import cache

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import OVERWORLD_QUEST, OverworldQuest
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import extra_options, generate_rom, plan
from zora.generate.rng import Rng
from zora.generate.steps.cave_entries import MIXED_RECORDER_SCREENS
from zora.generate.steps.mixed_overworld_quest import (
    NO_SCREEN,
    SECOND_QUEST_DEALT_POSITIONS,
    SECOND_QUEST_LEFTOVER_SCREENS,
    SECOND_QUEST_REGULAR_CODES,
    SECOND_QUEST_SECRET_POSITIONS,
    WOOD_SWORD_SCREEN,
    door_screen,
    mix_overworld_quest,
    second_quest_overworld,
)
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.overworld_quests import (
    MIXED_SECOND_QUEST_FLAGS,
    RANDOM_QUEST_FLAGS,
    SECOND_QUEST_FLAGS,
    mixed_second_shown,
    mixed_second_visible_caves,
    resolved_quest,
    second_quest_doors,
    second_quest_fields,
    second_quest_screens,
    second_quest_visible_caves,
)

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

SEEDS = (1, 2, 3)


@cache
def _base() -> bytes:
    return remember_repo_base_rom()


@cache
def _prg0() -> GameWorld:
    return parse_rom(_base())


@cache
def finished(flags: str, seed: int) -> GameWorld:
    return parse_rom(generate_rom(flags, seed, _base()).rom)


@pytest.mark.parametrize("flags, quest", [(SECOND_QUEST_FLAGS, OverworldQuest.SECOND_QUEST),
                                          (MIXED_SECOND_QUEST_FLAGS, OverworldQuest.MIXED_SECOND_QUEST_VARIANT),
                                          (RANDOM_QUEST_FLAGS, OverworldQuest.RANDOM)])
def test_the_corpus_strings_are_cp5_with_c01(flags: str, quest: OverworldQuest) -> None:
    settings = decode(flags)
    assert settings.option(OVERWORLD_QUEST) == quest
    assert encode(settings.updated(options={"C01": OverworldQuest.FIRST_QUEST})) == MVP_BASELINE_LEVEL_ENCODING_OFF
    plan(flags, 1)                                   # produced


def test_the_second_quest_list() -> None:
    """OW-QST-03: 59 regular entries (no 11, 66), the 20 second-quest positions; the seven codes
    on their entries and screens; the wooden-sword entry last; no draws."""
    overworld = copy.deepcopy(_prg0().overworld)
    entries = second_quest_overworld(overworld)
    screens = [entry.screen for entry in entries]
    assert len(entries) == 79 and not set(screens) & SECOND_QUEST_LEFTOVER_SCREENS
    assert set(SECOND_QUEST_SECRET_POSITIONS) <= set(screens) and screens[-1] == WOOD_SWORD_SCREEN
    for screen, (code, palette) in SECOND_QUEST_REGULAR_CODES.items():
        entry = next(entry for entry in entries if entry.screen == screen)
        assert (int(entry.code), entry.inner_palette) == (code, palette)
        assert (int(overworld.screens[screen].destination), overworld.screens[screen].inner_palette) == (code, palette)
    assert overworld.recorder_secret_screens[0] == NO_SCREEN
    assert overworld.recorder_secret_screens[1:] == _prg0().overworld.recorder_secret_screens[1:]


def test_the_mixed_second_quest_deal() -> None:
    """OW-QST-01/02: 18 codes dealt (61 + 18 = 79 entries), the seven codes on their entries."""
    overworld = copy.deepcopy(_prg0().overworld)
    entries = mix_overworld_quest(overworld, Rng(3), SECOND_QUEST_DEALT_POSITIONS)
    assert len(entries) == 79 and entries[-1].screen == WOOD_SWORD_SCREEN
    for screen, (code, palette) in SECOND_QUEST_REGULAR_CODES.items():
        entry = next(entry for entry in entries if entry.screen == screen)
        assert (int(entry.code), entry.inner_palette) == (code, palette)
    assert overworld.recorder_reveals_listed_secrets_in_first_quest


@pytest.mark.parametrize("seed", SEEDS)
def test_second_quest_finished_roms(seed: int) -> None:
    world = finished(SECOND_QUEST_FLAGS, seed)
    assert resolved_quest(world) == 1
    assert all(second_quest_fields(world).values()) and all(second_quest_screens(world).values())
    assert second_quest_visible_caves(world) and all(second_quest_doors(world).values())


@pytest.mark.parametrize("seed", SEEDS)
def test_the_doors_skip_the_leftover_screens(seed: int) -> None:
    """OW-QST-05: dungeons 5 and 7's doors are their entry doors, never 11 or 66."""
    world = finished(SECOND_QUEST_FLAGS, seed)
    for level in (5, 7):
        assert door_screen(world.overworld, level) not in SECOND_QUEST_LEFTOVER_SCREENS


@pytest.mark.parametrize("seed", SEEDS)
def test_mixed_second_quest_finished_roms(seed: int) -> None:
    world = finished(MIXED_SECOND_QUEST_FLAGS, seed)
    assert resolved_quest(world) == 3 and mixed_second_shown(world) and mixed_second_visible_caves(world)


def test_random_resolves_to_every_quest() -> None:
    """OW-QST-06: Random resolves to 0-3 per seed, and the seed is made as that value's."""
    resolved = {resolved_quest(finished(RANDOM_QUEST_FLAGS, seed)) for seed in range(1, 13)}
    assert resolved == {0, 1, 2, 3}


@pytest.mark.parametrize("flags", [SECOND_QUEST_FLAGS, MIXED_SECOND_QUEST_FLAGS])
def test_the_eleven_screen_recorder_set(flags: str) -> None:
    """OW-QST-02/04: the reachability rules read the eleven-screen recorder set."""
    rules = extra_options(plan(flags, 1)).logic_rules
    assert all(Item.RECORDER in rules.needs(screen) for screen in MIXED_RECORDER_SCREENS)
