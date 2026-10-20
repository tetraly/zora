"""Mixed overworld quest, first-quest variant (C01 = 2; overworld-behavior.md OW-MIX-01 to
OW-MIX-10): the deal, the quest fields, the recorder bytes, the walk, and finished ROMs. The
spec's Checks over 1,000 seeds: `python3 scripts/compare_corpus.py --set ow-mixed --seeds 1000
--first-seed 1`."""
import copy
from functools import cache

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import OVERWORLD_QUEST, OverworldQuest
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, plan
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.steps.cave_entries import (
    MIXED_RECORDER_SCREENS,
    RECORDER_SCREENS,
    SHORTCUT_POSITION_INDEX,
    Entry,
    recorder_screens,
)
from zora.generate.steps.mixed_overworld_quest import (
    FIRST_QUEST_SECRET_POSITIONS,
    NO_SCREEN,
    SCREEN_60,
    SCREEN_60_LAYOUT,
    SECOND_QUEST_SECRET_POSITIONS,
    SECRET_POSITIONS,
    WOOD_SWORD_LIST_INDEX,
    deal_secret_positions,
    mix_overworld_quest,
)
from zora.generate.steps.shuffle_caves import LADDER_ANY_ROAD_EXIT_X, write_back
from zora.model.enums import Destination, QuestVisibility
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.mixed_overworld import (
    MIXED_OVERWORLD_FLAGS,
    eleven_shown,
    hidden_positions_kept,
    one_visible_door_each,
    recorder_bytes,
    single_codes,
    visible_code_multiset,
)

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

SEEDS = (1, 2, 3, 4)


@cache
def _base() -> bytes:
    return remember_repo_base_rom()


@cache
def _prg0() -> GameWorld:
    return parse_rom(_base())


@cache
def finished(seed: int) -> GameWorld:
    return parse_rom(generate_rom(MIXED_OVERWORLD_FLAGS, seed, _base()).rom)


# --- the flag ------------------------------------------------------------------------------------

def test_the_mixed_finals_string_is_cp5_with_c01_2() -> None:
    settings = decode(MIXED_OVERWORLD_FLAGS)
    assert settings.option(OVERWORLD_QUEST) == OverworldQuest.MIXED_FIRST_QUEST_VARIANT
    assert encode(settings.updated(options={"C01": OverworldQuest.FIRST_QUEST})) == MVP_BASELINE_LEVEL_ENCODING_OFF
    assert plan(MIXED_OVERWORLD_FLAGS, 1).alternatives.mix_overworld_quest
    assert not plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1).alternatives.mix_overworld_quest


# --- OW-MIX-02 to OW-MIX-04: the deal -----------------------------------------------------------

def test_the_deal_exchanges_in_the_working_sequence() -> None:
    """OW-MIX-02: r in 0..31 - k for k = 1..11; r = 0 keeps T[k]."""
    assert deal_secret_positions(ScriptedRng([0] * 11)) == list(FIRST_QUEST_SECRET_POSITIONS)
    last = len(SECRET_POSITIONS) - 1
    dealt = deal_secret_positions(ScriptedRng([last] + [0] * 10))
    assert dealt[0] == SECRET_POSITIONS[last] and dealt[1:] == list(FIRST_QUEST_SECRET_POSITIONS[1:])


def test_the_list_quest_fields_and_recorder_bytes() -> None:
    overworld = copy.deepcopy(_prg0().overworld)
    entries = mix_overworld_quest(overworld, Rng(5))
    # p(1..10) follow the 61 regular entries; p(11) took the wooden-sword entry's place
    dealt = [entry.screen for entry in entries[61:71]] + [entries[WOOD_SWORD_LIST_INDEX].screen]
    assert len(entries) == 72 and sorted(dealt) == sorted(entry.screen for entry in entries
                                                          if entry.screen in SECRET_POSITIONS)
    assert entries[-1].screen == 119 and entries[-1].code == Destination.WOOD_SWORD_CAVE
    # the codes are the first-quest ones, in their order; the palettes the positions' own
    base = _prg0().overworld.screens
    codes = [base[screen].destination for screen in FIRST_QUEST_SECRET_POSITIONS]
    by_screen = {entry.screen: entry for entry in entries}
    assert [entry.code for entry in entries[61:71]] == codes[:10]
    assert by_screen[dealt[-1]].code == codes[10]
    assert all(by_screen[screen].inner_palette == base[screen].inner_palette for screen in dealt)
    for screen in SECRET_POSITIONS:
        visibility = overworld.screens[screen].quest_visibility
        if screen not in dealt:
            assert visibility is QuestVisibility.NEITHER_QUEST
        elif screen in FIRST_QUEST_SECRET_POSITIONS:
            assert visibility is QuestVisibility.FIRST_QUEST
        else:
            assert visibility is QuestVisibility.BOTH_QUESTS
    assert overworld.recorder_reveals_listed_secrets_in_first_quest
    for listed, byte in zip(_prg0().overworld.recorder_secret_screens, overworld.recorder_secret_screens,
                            strict=True):
        hidden = listed in SECOND_QUEST_SECRET_POSITIONS and listed not in dealt
        assert byte == (NO_SCREEN if hidden else listed)
    assert overworld.screens[SCREEN_60].screen_code == SCREEN_60_LAYOUT
    assert recorder_screens(overworld) == MIXED_RECORDER_SCREENS
    assert recorder_screens(_prg0().overworld) == RECORDER_SCREENS


def test_a_take_any_road_cave_on_a_ladder_screen_takes_its_exit() -> None:
    """OW-MIX-05 step 3 (V = 2 on both: exit row 4, LevelBlockAttrsA $9B)."""
    overworld = copy.deepcopy(_prg0().overworld)
    write_back(overworld, [Entry(24, Destination.ANY_ROAD, 0), Entry(25, Destination.ANY_ROAD, 0)])
    for screen in (24, 25):
        assert SHORTCUT_POSITION_INDEX[screen] == 2
        assert overworld.screens[screen].exit_y_position == 4
        assert overworld.screens[screen].exit_x_position == LADDER_ANY_ROAD_EXIT_X[2] == 9
        assert overworld.screens[screen].stairs_position_code == 2


# --- finished ROMs -------------------------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_finished_roms_hold_the_checks(seed: int) -> None:
    world = finished(seed)
    assert eleven_shown(world) and visible_code_multiset(world) and hidden_positions_kept(world)
    assert one_visible_door_each(world)
    assert all(recorder_bytes(world).values()) and all(single_codes(world).values())



# --- OW-MIX-08: the eleven-screen recorder set ----------------------------------------------------

def test_the_acceptance_rules_read_the_eleven_screen_recorder_set() -> None:
    """E1's entry-door and white-sword screens (OW-MIX-08)."""
    from zora.generate.pipeline import extra_options
    from zora.model.enums import Item
    mixed = extra_options(plan(MIXED_OVERWORLD_FLAGS, 1)).logic_rules
    first = extra_options(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1)).logic_rules
    for screen in MIXED_RECORDER_SCREENS:
        assert Item.RECORDER in mixed.needs(screen)
        assert (Item.RECORDER in first.needs(screen)) == (screen in RECORDER_SCREENS)


def test_the_shop_doors_and_hints_read_the_overworld_recorder_set() -> None:
    """E4/E5 (OW-SHOP-06) bar the recorder set's screens from the shops' front doors, and the
    hints' door-screen and white-sword means name the recorder there (OW-MIX-08)."""
    from zora.generate.steps.cave_entries import CaveShuffle
    from zora.generate.steps.hint_text import Form, door_means, white_sword_means
    from zora.generate.steps.shuffle_shop_items import front_door_failure
    from zora.model.enums import Item
    from zora.model.overworld import Shop
    overworld = copy.deepcopy(_prg0().overworld)
    overworld.recorder_reveals_listed_secrets_in_first_quest = True
    shops = [cave for cave in overworld.caves if isinstance(cave, Shop)]
    candle_shop = next(shop.destination for shop in shops if any(ware.item == Item.BLUE_CANDLE for ware in shop.items))
    arrow_shop = next(shop.destination for shop in shops if any(ware.item == Item.WOOD_ARROWS for ware in shop.items))
    doors = [Entry(110, candle_shop, 0), Entry(4, arrow_shop, 0)]
    assert front_door_failure(overworld, CaveShuffle(doors, 36)) == "(a) candle"
    overworld.recorder_reveals_listed_secrets_in_first_quest = False
    assert front_door_failure(overworld, CaveShuffle(doors, 36)) is None
    assert (MIXED_RECORDER_SCREENS, Form.RECORDER) in door_means(MIXED_RECORDER_SCREENS)
    assert (MIXED_RECORDER_SCREENS, Form.RECORDER) in white_sword_means(MIXED_RECORDER_SCREENS)


def test_a_recorder_warp_to_screen_0_stores_ff() -> None:
    """OW-WARP-01's s - 1 as a byte: under C01 = 2 an entry door can be screen 0 (the mixed finals
    store $FF)."""
    from zora.generate.steps import recorder_to_new_dungeons
    assert recorder_to_new_dungeons.recorder_bytes(0) == (0xFF, 0x8D)
    assert recorder_to_new_dungeons.recorder_bytes(14) == (29, 0x8D)
