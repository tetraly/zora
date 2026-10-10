"""Archipelago's access rules on assigned worlds (zora/generate/logic.py; docs/archipelago.md
"Logic"), Archipelago Phase 3 tests 2, 6 and 7:
  2. on Phase 2's shuffled assignments, sweep (the heart terms set aside, as the closure has none)
     reaches the goal and collects every tracked item exactly when ZORA's strict acceptance (E1
     and E3) passes. E1 asks for every tracked item, as Archipelago's full accessibility asks for
     every location; reaching the goal alone is weaker (an item the goal never needs may lock
     itself away). With the heart terms the model is never more lenient than E1 and E3;
  6. the same build gives the same model, and a JSON round trip gives an equal model;
  7. logic_model takes under 2 seconds on the slowest case.
"""
import json
import time
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.shared_builds import prebuild
from tests.test_assignment import _built, permuted
from tests.test_logic_model import without_hearts
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.finish import Foreign, with_tracking
from zora.generate.logic import (
    LETTER_EVENT,
    LogicModel,
    Swept,
    logic_model,
    model_from_json,
    model_to_json,
    sweep,
)
from zora.generate.pipeline import Built, build, extra_options, finish_world, plan
from zora.model.enums import Item
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

SEEDS = range(1, 4)
MANY_SEEDS = range(1, 21)
SHUFFLES = 6
SPEED_LIMIT = 2.0          # CPU seconds per seed (spec test 7)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


@cache
def model(case: str, seed: int) -> LogicModel:
    return logic_model(_built(case, seed))


def strict_acceptance(built: Built, assignment: dict[str, Item | Foreign]) -> bool:
    """ZORA's E1 and E3 on the assigned world (FINISH's tracked records)."""
    world, finished = finish_world(built, assignment, recompute=False, check=False)
    assert built.result.item_shuffle_result is not None and built.result.overworld is not None
    state = with_tracking(built.result.item_shuffle_result, finished.tracking, world, built.places)
    check = AcceptanceCheck(world.levels, state, world.overworld, built.result.overworld,
                            extra_options(built.plan).logic_rules)
    return check.collects_everything() and check.is_zelda_reachable()


def collects_every_tracked_item(built: Built, assignment: dict[str, Item | Foreign], swept: Swept) -> bool:
    assert built.result.item_shuffle_result is not None
    tracked = {place.item for place in built.result.item_shuffle_result.tracked}
    collected = {int(item) for name, item in assignment.items() if name in swept.places and isinstance(item, Item)}
    if LETTER_EVENT in swept.events:
        collected.add(Item.LETTER)
    return tracked <= collected


def disagreements(case: str, seed: int) -> list[str]:
    """Each shuffled assignment where the model and ZORA's strict acceptance part, described by
    the first place the closure collects that sweep does not (or the reverse)."""
    built, logic = _built(case, seed), model(case, seed)
    found = []
    for shuffle in range(SHUFFLES):
        assignment = permuted(built, seed * 1000 + shuffle)
        zora = strict_acceptance(built, assignment)
        swept = sweep(without_hearts(logic), assignment)
        agrees = swept.reaches_goal and collects_every_tracked_item(built, assignment, swept)
        with_hearts = sweep(logic, assignment)
        stricter = not (with_hearts.reaches_goal and collects_every_tracked_item(built, assignment, with_hearts)) \
            or zora
        if agrees != zora or not stricter:
            missing = sorted(name for name in logic.places if name not in swept.places)
            found.append(f"seed {seed} shuffle {shuffle}: ZORA {zora}, sweep {agrees}, hearts {not stricter}; "
                         f"assignment {assignment}; sweep misses {missing[:5]}")
    return found


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_agreement_on_shuffled_assignments(base: bytes, case: str, seed: int) -> None:
    found = disagreements(case, seed)
    assert not found, "\n".join(found)


@pytest.mark.slow
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_agreement_on_shuffled_assignments_many_seeds(base: bytes, case: str) -> None:
    prebuild([FLAG_CASES[case]], MANY_SEEDS)
    found = [line for seed in MANY_SEEDS for line in disagreements(case, seed)]
    assert not found, "\n".join(found)


# --- test 6: determinism and JSON -------------------------------------------------------------------

@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_same_build_gives_the_same_model(base: bytes, case: str) -> None:
    flag_string, zora_flag_string = FLAG_CASES[case]
    rebuilt = build(plan(flag_string, 2, zora_flag_string), base)
    assert logic_model(rebuilt) == model(case, 2)
    assert json.dumps(model_to_json(logic_model(rebuilt))) == json.dumps(model_to_json(model(case, 2)))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_a_json_round_trip_gives_an_equal_model(base: bytes, case: str, seed: int) -> None:
    logic = model(case, seed)
    text = json.dumps(model_to_json(logic))
    assert model_from_json(json.loads(text)) == logic
    assert json.dumps(model_to_json(model_from_json(json.loads(text)))) == text


# --- test 7: speed ------------------------------------------------------------------------------------

def test_logic_model_is_fast(base: bytes) -> None:
    """The slowest case (every ZORA flag on: the most checks and the largest universes)."""
    for seed in SEEDS:
        built = _built("every ZORA flag on", seed)
        # CPU time, not wall time: under load (other suites, xdist workers beside this one) the
        # process waits for a core, which says nothing about the model's speed.
        start = time.process_time()
        logic_model(built)
        assert time.process_time() - start < SPEED_LIMIT, seed
