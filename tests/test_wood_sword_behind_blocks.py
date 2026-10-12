"""Allow OW Blocks of Wood Sword (B03; overworld-behavior.md OW-CAVE-07): the wooden-sword cave may
land behind an item gate the free item opens. The Check over 1,000 seeds: `python3
scripts/compare_corpus.py --set b03` (no corpus: ZORA beside the figures the spec reports)."""
import copy
from functools import cache

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import WOOD_SWORD_CAVE_BEHIND_BLOCKS, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import Support, support
from zora.generate.pipeline import build, plan
from zora.generate.steps.cave_entries import BURNABLE_SCREENS, MIXED_RECORDER_SCREENS, RAFT_SCREENS
from zora.generate.steps.wood_sword_behind_blocks import (
    BRACELET_SCREENS_WITH_32_33,
    free_item,
    wood_sword_extra_screens,
)
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.overworld_quests import WOOD_SWORD_BLOCKS_FLAGS, wood_sword_widened

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")


@cache
def _base() -> bytes:
    return remember_repo_base_rom()


@cache
def _prg0() -> GameWorld:
    return parse_rom(_base())


def test_the_string_is_cp5_with_b03_on_and_supported() -> None:
    settings = decode(WOOD_SWORD_BLOCKS_FLAGS)
    assert settings.toggle(WOOD_SWORD_CAVE_BEHIND_BLOCKS) is ThreeState.ON
    off = settings.updated(toggles={WOOD_SWORD_CAVE_BEHIND_BLOCKS.id: ThreeState.OFF})
    assert encode(off) == MVP_BASELINE_LEVEL_ENCODING_OFF
    for state in ThreeState:
        judged = support(off.updated(toggles={WOOD_SWORD_CAVE_BEHIND_BLOCKS.id: state}))
        assert judged[WOOD_SWORD_CAVE_BEHIND_BLOCKS.id] is Support.SUPPORTED, state


@pytest.mark.parametrize("armos, coast, expected", [
    (Item.RECORDER, Item.HEART_CONTAINER, Item.RECORDER),
    (Item.LADDER, Item.RAFT, Item.RAFT),               # the Armos ladder: the coast item instead
    (Item.LADDER, Item.HEART_CONTAINER, None),
    (Item.BLUE_CANDLE, Item.HEART_CONTAINER, None),    # a blue candle as the free item does not count
    (Item.WHITE_SWORD, Item.POWER_BRACELET, None),     # the coast counts only behind an Armos ladder
])
def test_the_free_item(armos: Item, coast: Item, expected: Item | None) -> None:
    assert free_item(int(armos), int(coast)) == expected


@pytest.mark.parametrize("free, screens", [
    (Item.POWER_BRACELET, BRACELET_SCREENS_WITH_32_33), (Item.RAFT, RAFT_SCREENS),
    (Item.RED_CANDLE, BURNABLE_SCREENS), (Item.RECORDER, frozenset({66})), (Item.WHITE_SWORD, frozenset()),
])
def test_each_free_item_adds_its_set(free: Item, screens: frozenset[int]) -> None:
    assert wood_sword_extra_screens(_prg0().overworld, int(free), int(Item.HEART_CONTAINER)) == screens


def test_the_recorder_set_follows_the_quest() -> None:
    """Under every overworld quest but the first, the recorder adds the eleven screens."""
    overworld = copy.deepcopy(_prg0().overworld)
    overworld.recorder_reveals_listed_secrets_in_first_quest = True
    assert wood_sword_extra_screens(overworld, int(Item.RECORDER), 0) == MIXED_RECORDER_SCREENS


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_finished_roms(seed: int) -> None:
    built = build(plan(WOOD_SWORD_BLOCKS_FLAGS, seed), _base())
    assert wood_sword_widened(built.world)["on the widened set"]
