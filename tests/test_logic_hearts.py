"""The sword caves' heart terms (zora/generate/logic.py; docs/archipelago.md "Logic"), Archipelago
Phase 3 test 5:
  - the white-sword cave carries HeartsTerm(N) for the built N (and the magical-sword cave its own);
  - the magical-sword cave's term gives check_magical_sword_hearts's verdict for the same
    placement (ZORA's own, and shuffled ones), the magical-sword cave's own item left out as
    ZORA leaves it out.
Where they differ, the difference is the heart check's own rule, which the model does not copy
(docs/archipelago.md "Leniencies"): it counts the potion shop's heart container once its door is
reached; the closure (E1), and so the model, also asks for the letter (the model is stricter)."""
import copy
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.shared_builds import prebuild
from tests.test_assignment import _built, identity, permuted
from zora.generate.finish import CAVE_SLOTS, Foreign, rebuild_tracking, with_tracking, written_item
from zora.generate.logic import LETTER_EVENT, HeartsTerm, LogicModel, Swept, logic_model, sweep
from zora.generate.pipeline import Built, extra_options
from zora.generate.places import PlaceKind, write_item
from zora.generate.steps.randomize_magical_sword import check_magical_sword_hearts
from zora.model.enums import Destination, Item
from zora.model.overworld import ItemCave
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

SWORD_CASES = [case for case in FLAG_CASES if case in ("magical sword and letter", "every ZORA flag on")]
SEEDS = range(1, 5)
MANY_SEEDS = range(1, 21)
SHUFFLES = 8
MAGICAL_SWORD_CAVE = "Magical Sword Cave"
WHITE_SWORD_CAVE = "White Sword Cave"


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


@cache
def model(case: str, seed: int) -> LogicModel:
    return logic_model(_built(case, seed))


def hearts_required(built: Built, name: str) -> int:
    place = next(place for place in built.places if place.name == name)
    return place.requires[0].hearts


def zora_verdict(built: Built, assignment: dict[str, Item | Foreign]) -> bool:
    """check_magical_sword_hearts on the assigned world: the world and BUILD's result copied
    together (the extras' wares keep pointing into the copy), the items written into both."""
    world, result = copy.deepcopy((built.world, built.result))
    assert result.item_shuffle_result is not None and result.extra_pool_items is not None
    assert result.overworld is not None
    for place in built.places:
        item = written_item(assignment[place.name])
        write_item(world, place, item)
        if place.destination in CAVE_SLOTS and CAVE_SLOTS[place.destination] in result.extra_pool_items.caves:
            result.extra_pool_items.caves[CAVE_SLOTS[place.destination]] = item
    copied = Built(built.plan, world, result, built.places)
    state = with_tracking(result.item_shuffle_result, rebuild_tracking(world, copied), world, built.places)
    extras = extra_options(built.plan)
    sword_caves = [world.overworld.get_cave(cave, ItemCave)
                   for cave in (Destination.MAGICAL_SWORD_CAVE, Destination.WHITE_SWORD_CAVE)]
    magical, white = (cave.heart_requirement for cave in sword_caves if cave is not None)
    return check_magical_sword_hearts(world.levels, state, result.extra_pool_items, world.overworld, result.overworld,
                                      magical, extras.starting_heart_containers, white, extras.logic_rules)


def explained(built: Built, assignment: dict[str, Item | Foreign], swept: Swept, zora: bool) -> bool:
    """A disagreement the heart check's own rule accounts for (the module docstring): the model
    stricter, the potion shop holding a heart container and no letter held."""
    has_letter = swept.items[Item.LETTER] > 0 or LETTER_EVENT in swept.events
    return zora and not has_letter and any(place.kind == PlaceKind.POTION_SHOP and
                                           assignment[place.name] == Item.HEART_CONTAINER
                                           for place in built.places)


def compare(case: str, seed: int) -> list[tuple[int, bool]]:
    """Each placement's ZORA verdict where the model's differs unexplained."""
    built, logic = _built(case, seed), model(case, seed)
    term = HeartsTerm(hearts_required(built, MAGICAL_SWORD_CAVE), take_any=True)
    unexplained = []
    placements = [identity(built), *(permuted(built, seed * 100 + shuffle) for shuffle in range(SHUFFLES))]
    for index, assignment in enumerate(placements):
        zora = zora_verdict(built, assignment)
        swept = sweep(logic, {**assignment, MAGICAL_SWORD_CAVE: None})    # its own item left out
        if swept.holds(logic, term) != zora and (
                index == 0 or not explained(built, assignment, swept, zora)):
            unexplained.append((index, zora))
    return unexplained


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_sword_caves_carry_their_hearts(base: bytes, case: str, seed: int) -> None:
    built, logic = _built(case, seed), model(case, seed)
    for name in (WHITE_SWORD_CAVE, MAGICAL_SWORD_CAVE):
        if name in logic.places:
            term = HeartsTerm(hearts_required(built, name), take_any=True)
            assert all(term in clause for clause in logic.places[name]), name
    assert logic.starting_hearts == extra_options(built.plan).starting_heart_containers


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", SWORD_CASES)
def test_the_magical_sword_term_matches_the_heart_check(base: bytes, case: str, seed: int) -> None:
    assert compare(case, seed) == []


@pytest.mark.slow
@pytest.mark.parametrize("case", SWORD_CASES)
def test_the_magical_sword_term_matches_the_heart_check_many_seeds(base: bytes, case: str) -> None:
    prebuild([FLAG_CASES[case]], MANY_SEEDS)
    assert {seed: found for seed in MANY_SEEDS if (found := compare(case, seed))} == {}
