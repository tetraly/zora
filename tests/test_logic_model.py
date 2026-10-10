"""Archipelago's access rules on built seeds (zora/generate/logic.py; docs/archipelago.md "Logic"),
Archipelago Phase 3 tests 1 and 4:
  1. with ZORA's own placement, sweep collects exactly the tracked items and completes exactly the
     levels AcceptanceCheck.closure() does (the heart terms set aside: the closure has none; the
     sword caves' hearts are test 5's, tests/test_logic_hearts.py);
  4. the 2.0 flags: each gate's need (the raft, the bracelet, a maze's hint) is required behind
     its screens when the gate is on and never when it is off; Progressive Items turns the
     silver arrows into an arrow count; Shop Items in the Item Pool adds candle counts on burnable
     screens.
Every rule the model holds went through derive's monotonicity assertion (test 3 makes sure it
is live)."""
from collections.abc import Callable
from dataclasses import replace
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.shared_builds import prebuild
from tests.test_assignment import _built, identity
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.logic import (
    ARROW,
    CANDLE,
    GANON_EVENT,
    LETTER_EVENT,
    TRUE,
    CountTerm,
    EventTerm,
    HeartsTerm,
    ItemTerm,
    LogicModel,
    Rule,
    Term,
    logic_model,
    rule_of,
    sweep,
    triforce_event,
)
from zora.generate.pipeline import Built, extra_options
from zora.generate.places import major_pool
from zora.generate.steps.cave_entries import BRACELET_SCREENS, BURNABLE_SCREENS, RAFT_SCREENS
from zora.generate.steps.overworld_gates import (
    BRACELET_BLOCK_SCREENS,
    DEAD_WOODS_GATED,
    LOST_HILLS_GATED,
    RAFT_BLOCK_SCREENS,
)
from zora.model.enums import Item
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

SEEDS = range(1, 7)
MANY_SEEDS = range(1, 41)
TRIFORCE_LEVELS = range(1, 9)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


@cache
def model(case: str, seed: int) -> LogicModel:
    return logic_model(_built(case, seed))


def without_hearts(logic: LogicModel) -> LogicModel:
    """The model with its heart terms set aside, as ZORA's closure judges."""
    def kept(rule: Rule) -> Rule:
        return frozenset(frozenset(term for term in clause if not isinstance(term, HeartsTerm)) for clause in rule)
    return replace(logic, places={name: kept(rule) for name, rule in logic.places.items()},
                   events={name: kept(rule) for name, rule in logic.events.items()})


def closure_of(built: Built) -> tuple[set[int], set[int]]:
    state, caves = built.result.item_shuffle_result, built.result.overworld
    assert state is not None and caves is not None
    return AcceptanceCheck(built.world.levels, state, built.world.overworld, caves,
                           extra_options(built.plan).logic_rules).closure()


def terms(rule: Rule) -> set[Term]:
    return {term for clause in rule for term in clause}


def every_term(logic: LogicModel) -> set[Term]:
    return set().union(*(terms(rule) for rule in (*logic.places.values(), *logic.events.values())))


def requires(rule: Rule, term: Term) -> bool:
    """Every clause of the rule has the term."""
    return bool(rule) and all(term in clause for clause in rule)


# --- test 1: the same verdicts as ZORA's closure --------------------------------------------------

def same_verdicts(case: str, seed: int) -> None:
    built = _built(case, seed)
    assignment = identity(built)
    swept = sweep(without_hearts(model(case, seed)), assignment)
    held, completed = closure_of(built)
    assert built.result.item_shuffle_result is not None
    tracked = {place.item for place in built.result.item_shuffle_result.tracked}
    collected = {int(item) for name, item in assignment.items() if name in swept.places and isinstance(item, Item)}
    if LETTER_EVENT in swept.events:
        collected.add(Item.LETTER)             # the letter in its own cave (Shuffle Blue Potion)
    assert collected & tracked == held & tracked, (case, seed)
    assert {level for level in TRIFORCE_LEVELS if triforce_event(level) in swept.events} == completed, (case, seed)
    assert swept.reaches_goal, (case, seed)    # an accepted seed passes E1 and E3


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_same_verdicts_as_the_closure(base: bytes, case: str, seed: int) -> None:
    same_verdicts(case, seed)


@pytest.mark.slow
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_same_verdicts_as_the_closure_many_seeds(base: bytes, case: str) -> None:
    prebuild([FLAG_CASES[case]], MANY_SEEDS)
    for seed in MANY_SEEDS:
        same_verdicts(case, seed)


# --- test 4: the 2.0 flags ------------------------------------------------------------------------

def entry_doors(built: Built) -> dict[int, int]:
    assert built.result.overworld is not None
    return {level: built.result.overworld.entry_door(level) for level in TRIFORCE_LEVELS}


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_overworld_gates(base: bytes, case: str) -> None:
    """A level behind a gate's screens needs the gate's item (or hint) for its triforce, while the
    gate is on; with it off, a level on those screens (outside PRG0's own sets) never does, and
    the maze hints appear nowhere."""
    gate_needs: dict[str, tuple[frozenset[int], Term]] = {
        "raft_blocks": (RAFT_BLOCK_SCREENS - RAFT_SCREENS, ItemTerm(Item.RAFT)),
        "bracelet_blocks": (BRACELET_BLOCK_SCREENS - BRACELET_SCREENS, ItemTerm(Item.POWER_BRACELET)),
        "lost_hills": (LOST_HILLS_GATED, EventTerm("Lost Hills Hint")),
        "dead_woods": (DEAD_WOODS_GATED, EventTerm("Dead Woods Hint"))}
    seen = dict.fromkeys(gate_needs, 0)
    for seed in SEEDS:
        built, logic = _built(case, seed), model(case, seed)
        gates = extra_options(built.plan).gates
        for gate, (screens, need) in gate_needs.items():
            is_on = getattr(gates, gate)
            if isinstance(need, EventTerm):
                assert (need in every_term(logic)) <= is_on and (need.name in logic.events) == is_on
            for level, door in entry_doors(built).items():
                if door in screens:
                    seen[gate] += is_on
                    assert requires(logic.events[triforce_event(level)], need) == is_on, (gate, seed, level)
    gates = extra_options(_built(case, 1).plan).gates
    assert all(seen[gate] for gate in ("raft_blocks", "bracelet_blocks") if getattr(gates, gate)), seen


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_maze_hints_appear_when_on(base: bytes, case: str) -> None:
    gates = extra_options(_built(case, 1).plan).gates
    for name, is_on in (("Lost Hills Hint", gates.lost_hills), ("Dead Woods Hint", gates.dead_woods)):
        used = any(EventTerm(name) in every_term(model(case, seed)) for seed in SEEDS)
        assert used == is_on, (name, is_on)


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_progressive_items_count_arrows(base: bytes, case: str) -> None:
    for seed in SEEDS:
        built, logic = _built(case, seed), model(case, seed)
        extras = extra_options(built.plan)
        ganon = logic.events[GANON_EVENT]
        if extras.progressive_items:
            assert requires(ganon, CountTerm(ARROW, 2)) and ItemTerm(Item.SILVER_ARROWS) not in every_term(logic)
        else:
            assert requires(ganon, ItemTerm(Item.SILVER_ARROWS))
        if not extras.progressive_items and not extras.shop_items_in_pool:
            assert not any(isinstance(term, CountTerm) for term in every_term(logic))


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_shop_items_count_candles(base: bytes, case: str) -> None:
    burnable = 0
    for seed in SEEDS:
        built, logic = _built(case, seed), model(case, seed)
        is_on = extra_options(built.plan).shop_items_in_pool
        assert (CountTerm(CANDLE, 1) in every_term(logic)) <= is_on
        for level, door in entry_doors(built).items():
            if door in BURNABLE_SCREENS:
                burnable += 1
                assert requires(logic.events[triforce_event(level)], CountTerm(CANDLE, 1)) == is_on
    assert burnable


# --- the owner's pins (Phase 3 owner additions; docs/archipelago.md "Leniencies") ------------------

@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_wooden_sword_is_never_a_place(base: bytes, case: str) -> None:
    """The model assumes a sword (hence bombs, owner decision 1) from the start: the wooden sword
    is in no flag case's pool, no place holds it, and no rule names it."""
    for seed in SEEDS:
        built = _built(case, seed)
        assert Item.WOOD_SWORD not in major_pool(extra_options(built.plan))
        assert Item.WOOD_SWORD not in identity(built).values()
        assert ItemTerm(Item.WOOD_SWORD) not in every_term(model(case, seed))


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_armos_item_is_free_and_the_coast_needs_the_ladder(base: bytes, case: str,
                                                              record_property: Callable[[str, object], None]) -> None:
    """Owner decision 2, as ZORA's closure has it: the Armos item needs nothing, wherever Shuffle
    Armos moved the formation (gated screens included), and the coast exactly the ladder. Recorded
    as documentation (pytest's junit properties): the seeds whose Armos screen has needs."""
    gated_armos = []
    for seed in SEEDS:
        built, logic = _built(case, seed), model(case, seed)
        assert logic.places["Armos"] == TRUE
        assert logic.places["Coast"] == rule_of(ItemTerm(Item.LADDER))
        armos_screen = next(place for place in built.places if place.name == "Armos").screens[0]
        if extra_options(built.plan).logic_rules.needs(armos_screen):
            gated_armos.append(seed)
    record_property("seeds whose Armos screen has needs the rule ignores", gated_armos)
