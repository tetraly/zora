"""Generation's walk counts a joined sword wherever it lies (zora/generate/generation_pass.py sword_is_tracked; 2.0.2,
2026-11-22).

Randomize Magical Sword's sword and Add L4 Sword = Level 2's cellar sword join the pool by one exchange; until 2.0.2
the sword itself got a tracked record only under Level 9 Entrance = Level 4 sword, so under Offense Item Pacing
alone the walk counted fewer swords than Link has, while the logic model's Sword line counts them wherever they lie.
Now a joined sword is tracked whenever the walk counts swords (LogicRules.counts_swords), so BUILD judges seeds as
the logic does, and FINISH's rebuild_tracking (tests/test_finish_untracked_swords.py) finds its record.

- A seed whose shipped world is accepted only because the Magical Sword counts as the second sword.
- Not too lenient: every place and the goal of these seeds are reached by the logic model's sweep with the items
  where BUILD put them (a beatable seed; the longer scan is a separate run).
- Unchanged elsewhere: without pacing, the joined swords stay untracked.
- The Magical Sword Cave's hearts are counted under pacing, as the logic counts them."""
from dataclasses import replace
from functools import cache

import pytest

from tests.test_assignment import identity
from zora import archipelago
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import Pacing
from zora.generate.acceptance_check import acceptance_check
from zora.generate.dungeon_walk import item_cellar, item_room
from zora.generate.logic import sweep
from zora.generate.pipeline import shipped_logic_rules
from zora.generate.steps.level_2_sword import LEVEL_2_SWORD
from zora.model.enums import Item
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

MAGICAL_SWORD = replace(zora_flags.ZoraFlags(), randomize_magical_sword=True, magical_sword_hearts_highest=12)
LEVEL_2_SWORD_FLAGS = replace(zora_flags.ZoraFlags(), progressive_items=True, add_l4_sword=ThreeState.ON,
                              l4_sword_in_level_2=True)
CASES = {
    "magical sword, pacing earlier": (replace(MAGICAL_SWORD, offense_pacing=Pacing.EARLIER), Item.MAGICAL_SWORD),
    "magical sword, pacing later": (replace(MAGICAL_SWORD, offense_pacing=Pacing.LATER), Item.MAGICAL_SWORD),
    "level 2 sword, pacing normal": (replace(LEVEL_2_SWORD_FLAGS, offense_pacing=Pacing.NORMAL), LEVEL_2_SWORD),
}
UNPACED = {"magical sword": (MAGICAL_SWORD, Item.MAGICAL_SWORD), "level 2 sword": (LEVEL_2_SWORD_FLAGS, LEVEL_2_SWORD)}
# Found by searching seeds 1-40 (2026-11-22; 12 such): the shipped world fails E1 without the Magical Sword's record
SECOND_SWORD_SEED = 10
SEEDS = range(1, 6)


@pytest.fixture(scope="module", autouse=True)
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


@cache
def built(flags: zora_flags.ZoraFlags, seed: int) -> archipelago.BuildResult:
    return archipelago.build_from_strings(MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(flags), seed,
                                          remember_repo_base_rom())


def records(result: archipelago.BuildResult, sword: Item) -> int:
    state = result.state.result.item_shuffle_result
    assert state is not None
    return sum(record.item == sword for record in state.tracked)


def test_the_magical_sword_is_the_second_sword_and_the_seed_is_accepted() -> None:
    flags, _sword = CASES["magical sword, pacing earlier"]
    result = built(flags, SECOND_SWORD_SEED)
    state = result.state.result.item_shuffle_result
    assert state is not None and records(result, Item.MAGICAL_SWORD) == 1
    world = result.state.world
    caves = result.state.result.overworld
    assert caves is not None
    rules = shipped_logic_rules(result.state.plan, world)

    def verdict(tracked: list) -> str | None:
        return acceptance_check(world.levels, replace(state, tracked=tracked), world.overworld,
                                caves, rules, extras=result.state.result.extra_pool_items)

    assert verdict(list(state.tracked)) is None
    # without the sword's record the walk stops a sword short: the shipped world would be refused
    assert verdict([record for record in state.tracked if record.item != Item.MAGICAL_SWORD]) == "E1"


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", CASES)
def test_the_joined_sword_is_tracked_and_the_seed_is_beatable(case: str, seed: int) -> None:
    flags, sword = CASES[case]
    result = built(flags, seed)
    assert records(result, sword) >= 1
    swept = sweep(result.logic, identity(result.state))
    assert swept.reaches_goal
    assert {place.name for place in result.state.places} <= swept.places


@pytest.mark.parametrize("case", UNPACED)
def test_without_pacing_the_joined_sword_stays_untracked(case: str) -> None:
    flags, sword = UNPACED[case]
    result = built(flags, 1)
    assert records(result, sword) == 0


@pytest.mark.parametrize("seed", SEEDS)
def test_the_walk_finds_the_magical_sword_not_an_empty_room(seed: int) -> None:
    """dungeon_walk.item_room and item_cellar: an empty room's code is $03, the Magical Sword's, and never matches."""
    flags, _sword = CASES["magical sword, pacing earlier"]
    world = built(flags, seed).state.world
    for level in world.levels:
        room = item_room(level, Item.MAGICAL_SWORD)
        cellar = item_cellar(level, Item.MAGICAL_SWORD)
        assert room is None or level.block.room(room).item == Item.MAGICAL_SWORD
        assert cellar is None or next(stair for stair in level.block.staircases
                                      if stair.room_num == cellar).item == Item.MAGICAL_SWORD
        assert any(room.item == Item.NOTHING for room in level.rooms)        # the case the search must skip


# Scan of 2026-11-22: on 3bc98fe8 generation's heart check counted heart containers in levels Offense Item Pacing
# opens only with two swords, so these seeds' Magical Sword Cave asked for hearts the logic reaches only after the
# cave's own item (seed 142: the Ladder, which the second sword needs). randomize_magical_sword.AcceptanceHeartReach
# now enters a level only with its pacing counts held.
PACED_HEART_SEEDS = [("magical sword, pacing earlier", 142), ("magical sword, pacing normal", 196),
                     ("magical sword, pacing earlier", 183), ("magical sword, pacing normal", 18),
                     ("magical sword, pacing normal", 133)]
PACING_FLAGS = {"magical sword, pacing earlier": CASES["magical sword, pacing earlier"][0],
                "magical sword, pacing normal": replace(MAGICAL_SWORD, offense_pacing=Pacing.NORMAL)}


@pytest.mark.parametrize(("case", "seed"), PACED_HEART_SEEDS)
def test_the_magical_sword_caves_hearts_are_reached_under_pacing(case: str, seed: int) -> None:
    result = built(PACING_FLAGS[case], seed)
    swept = sweep(result.logic, identity(result.state))
    assert swept.reaches_goal
    assert {place.name for place in result.state.places} <= swept.places     # the cave's place among them
