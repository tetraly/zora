"""Items within each dungeon (C06 = 2; post-shapes-b1.md PS-ITW-01 to PS-ITW-07): the flag, the
two deals, the hints and the ZORA extras. The spec's Checks over 1,000 seeds:
`python3 scripts/compare_corpus.py --set items-within --seeds 1000 --first-seed 1`."""
from collections import Counter
from functools import cache

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import ITEM_SHUFFLE_SCOPE, ItemShuffleScope
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import build, generate_rom, plan
from zora.generate.rng import Rng
from zora.generate.steps.hint_text import requirement_candidates
from zora.generate.steps.item_shuffle_result import ItemShuffleResult
from zora.generate.steps.shuffle_items import POOL_ORDER, _CavePosition, _find_item_place, deal_within_levels
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.model.rooms import ITEM_MASK
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.acceptance import CAVE_SLOT, item_places
from zora_measure.checkpoints.items_within import ITEMS_WITHIN_FLAGS, hearts_per_level, tracked_in_levels

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

SEEDS = (1, 2, 3, 4)
# C06 = 2 with Extra Candles off, so every ZORA extra that joins the pool can be on: Randomize
# Magical Sword and Letter, Progressive Items, Shop Items in the Item Pool, Shuffle Blue Potion
# and Add L4 Sword = Level 2
WITHIN_NO_CANDLES = "8hq4BeR1JXo7yjOOHjbxryVQW!U7m3"
EVERY_POOL_EXTRA = "4.9j6k3"


@cache
def _base() -> bytes:
    return remember_repo_base_rom()


@cache
def finished(flag_string: str, seed: int, zora: str = "") -> GameWorld:
    return parse_rom(generate_rom(flag_string, seed, _base(), zora_flag_string=zora).rom)


# --- the flag ------------------------------------------------------------------------------------

def test_the_within_finals_string_is_cp5_with_c06_2() -> None:
    settings = decode(ITEMS_WITHIN_FLAGS)
    assert settings.option(ITEM_SHUFFLE_SCOPE) == ItemShuffleScope.WITHIN_EACH_DUNGEON
    assert encode(settings.updated(options={"C06": ItemShuffleScope.FULL})) == MVP_BASELINE_LEVEL_ENCODING_OFF
    assert encode(settings) == ITEMS_WITHIN_FLAGS


def test_plan_switches_the_two_deals_on_only_for_c06_2() -> None:
    assert plan(ITEMS_WITHIN_FLAGS, 1).alternatives.shuffle_items_within_levels
    assert not plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1).alternatives.shuffle_items_within_levels


# --- PS-ITW-03: the second deal ----------------------------------------------------------------

def test_the_second_deal_keeps_each_item_in_its_level_and_counts_every_step() -> None:
    """On a built world's levels: the second deal moves items only within a level, skips the cave
    slots without a draw, redraws a partner from another level, and keeps the fifteen records on
    their items."""
    built = build(plan(ITEMS_WITHIN_FLAGS, 1), _base())
    levels = built.world.levels
    before = Counter((place, item) for item, places in item_places(built.world).items()
                     for place in places if place != CAVE_SLOT)
    state = ItemShuffleResult(caves={"armos": Item.POWER_BRACELET, "white_sword": Item.WHITE_SWORD,
                                     "coast": Item.HEART_CONTAINER})
    dealt = [(place, place.get()) for place in (_find_item_place(levels, code) for code in POOL_ORDER)
             if place is not None]
    dealt += [(_CavePosition(slot, state), state.caves[slot]) for slot in ("armos", "white_sword", "coast")]
    deal_within_levels(levels, state, Rng(1), dealt)
    after = Counter((place, item) for item, places in item_places(built.world).items()
                    for place in places if place != CAVE_SLOT)
    assert after == before                        # per level, the same items
    assert 0 < state.within_levels_iterations < 10_000
    assert [record.item for record in state.tracked] == [int(item) & ITEM_MASK for _place, item in dealt]
    assert [record.slot for record in state.tracked[-3:]] == ["armos", "white_sword", "coast"]


# --- PS-ITW-01, -02: finished ROMs --------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_hearts_stay_in_their_levels(seed: int) -> None:
    """PS-ITW-01: nine heart containers; levels 1-8 hold one or two, level 9 none or one. PS-ITW-02:
    twenty tracked items and hearts in level rooms and cellars."""
    world = finished(ITEMS_WITHIN_FLAGS, seed)
    per_level = hearts_per_level(world)
    assert all(count in (1, 2) for count in per_level[:8]) and per_level[8] in (0, 1), per_level
    assert tracked_in_levels(world) == 20


@pytest.mark.parametrize("seed", SEEDS)
def test_with_every_pool_extra_the_hearts_stay_in_their_levels(seed: int) -> None:
    """The ZORA extras join the pool without the dungeon hearts under C06 = 2 (ZORA's reading of
    PS-ITW-01: the hearts are not pool items at this scope), so no extra carries one out."""
    world = finished(WITHIN_NO_CANDLES, seed, EVERY_POOL_EXTRA)
    per_level = hearts_per_level(world)
    assert all(count >= 1 for count in per_level[:8]), per_level


def test_generation_is_repeatable() -> None:
    first = generate_rom(ITEMS_WITHIN_FLAGS, 7, _base()).rom
    assert generate_rom(ITEMS_WITHIN_FLAGS, 7, _base()).rom == first


# --- PS-ITW-05: the hints ------------------------------------------------------------------------

def test_requirement_candidates_name_hearts_only_within_each_dungeon() -> None:
    """HT-HINT-01 rules 1 and 5 except heart containers only under C06 = 3."""
    world = finished(ITEMS_WITHIN_FLAGS, 1)
    level_items = [(int(Item.HEART_CONTAINER), 3)]
    assert all(candidate.item != Item.HEART_CONTAINER for candidate in requirement_candidates(world, level_items)
               if candidate.level is not None)
    named = requirement_candidates(world, level_items, names_hearts=True)
    assert any(candidate.item == Item.HEART_CONTAINER and candidate.level == 3 for candidate in named)


def test_the_records_are_where_the_items_are() -> None:
    """PS-ITW-04: each of the fifteen records with a level names a level that holds its item."""
    built = build(plan(ITEMS_WITHIN_FLAGS, 2), _base())
    assert built.result.item_shuffle_result is not None
    tracked = built.result.item_shuffle_result.tracked
    places = item_places(built.world)
    assert len(tracked) == 15
    for record in tracked:
        if record.level is not None:
            assert record.level in places.get(Item(record.item), []), record
