"""The level-9 entry fix (owner decision 2026-10-08, beta 2; acceptance_check.AcceptanceCheck.can_enter):
a level-9 item is collected only once level 9 can be entered (the eight triforces). Before it, E1
asked level-9 entry only as a target, so an item a level 1-8 triforce needs could sit in level 9
alone and the seed was accepted though unbeatable. Only Shop Items in the Item Pool makes that
possible (Gohma's arrow, the burnable screens' candle).
  - every owner flag on, seeds 162 and 183 (the arrows, the candles in level 9) now generate
    seeds where every triforce is reached without level 9;
  - a constructed case, a triforce's only line items moved into level 9, is rejected, where the
    old rule accepted it;
  - the Phase 3 rules ask it too (Phase 3's test 2, tests/test_logic_agreement.py, still agrees)."""
import pytest

from tests.test_assignment import _built, identity
from zora.generate.acceptance_check import LONG_ITEMS, AcceptanceCheck
from zora.generate.finish import AssignmentUnbeatable, Foreign
from zora.generate.logic import (
    ARROW,
    CANDLE,
    LEVEL9_ENTRY_EVENT,
    CountTerm,
    EventTerm,
    LogicModel,
    logic_model,
    sweep,
    triforce_event,
)
from zora.generate.pipeline import Built, finish, finish_world
from zora.model.enums import Item
from zora.model.levels import LEVEL_9
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

CASE = "every owner flag on"
FIXED_SEEDS = (162, 183)
TRIFORCE_LEVELS = range(1, 9)
LINE_ITEMS = {ARROW: (Item.WOOD_ARROWS, Item.SILVER_ARROWS), CANDLE: (Item.BLUE_CANDLE, Item.RED_CANDLE)}
SEARCHED_SEEDS = range(1, 21)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


def old_can_enter(self: AcceptanceCheck, level: int, held: frozenset[int]) -> bool:
    """The rule before the fix: level 9 asked its door and the long items only."""
    needs = self.rules.needs(self.caves.entry_door(level))
    if level == LEVEL_9:
        needs |= LONG_ITEMS
    return needs <= held


@pytest.mark.parametrize("seed", FIXED_SEEDS)
def test_the_reported_seeds_now_reach_every_triforce_without_level_9(base: bytes, seed: int) -> None:
    """Under the fixed rules a level-9 item is collected only after Level 9 Entry, so a sweep that
    completes every triforce and reaches the goal needs nothing from level 9 before it."""
    built = _built(CASE, seed)
    logic = logic_model(built)
    level9 = [place.name for place in built.places if place.level == LEVEL_9]
    assert all(all(EventTerm(LEVEL9_ENTRY_EVENT) in clause for clause in logic.places[name]) for name in level9)
    swept = sweep(logic, identity(built))
    assert all(triforce_event(level) in swept.events for level in TRIFORCE_LEVELS) and swept.reaches_goal
    assert all(name in swept.places for name in level9)


def line_needed_by_a_triforce(logic: LogicModel) -> str | None:
    """A line (arrows or candles) every clause of some triforce's rule counts."""
    for level in TRIFORCE_LEVELS:
        rule = logic.events[triforce_event(level)]
        for line in LINE_ITEMS:
            if rule and all(CountTerm(line, 1) in clause for clause in rule):
                return line
    return None


def stranded_in_level_9(built: Built, line: str) -> dict[str, Item | Foreign] | None:
    """ZORA's own placement with every item of the line swapped into a level-9 place, or None
    when level 9 has too few places."""
    assignment = identity(built)
    level9 = [place.name for place in built.places if place.level == LEVEL_9
              and assignment[place.name] not in LINE_ITEMS[line]]
    holding = [name for name, item in assignment.items() if item in LINE_ITEMS[line]
               and next(place for place in built.places if place.name == name).level != LEVEL_9]
    if len(level9) < len(holding):
        return None
    for source, target in zip(holding, level9, strict=False):
        assignment[source], assignment[target] = assignment[target], assignment[source]
    return assignment


def old_rule_accepts(built: Built, assignment: dict[str, Item | Foreign], monkeypatch: pytest.MonkeyPatch) -> bool:
    with monkeypatch.context() as patched:
        patched.setattr(AcceptanceCheck, "can_enter", old_can_enter)
        return sanity_strict(built, assignment) is None


def sanity_strict(built: Built, assignment: dict[str, Item | Foreign]) -> str | None:
    try:
        _, finished = finish_world(built, assignment)
    except AssignmentUnbeatable as failure:
        return failure.sanity.strict
    assert finished.sanity is not None
    return finished.sanity.strict


def constructed_case(monkeypatch: pytest.MonkeyPatch) -> tuple[Built, dict[str, Item | Foreign]]:
    """A seed whose triforce needs a line, with the line moved into level 9, that the old rule
    accepted (moving the line can also make a cycle both rules reject: the bow behind Gohma)."""
    for seed in SEARCHED_SEEDS:
        built = _built(CASE, seed)
        line = line_needed_by_a_triforce(logic_model(built))
        if line is None or (assignment := stranded_in_level_9(built, line)) is None:
            continue
        if old_rule_accepts(built, assignment, monkeypatch):
            return built, assignment
    raise AssertionError("no seed gives a case the old rule accepted")


def test_a_triforce_item_only_in_level_9_is_rejected(base: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    """The old rule accepted it (the bug); the fixed rule rejects it."""
    built, assignment = constructed_case(monkeypatch)
    with pytest.raises(AssignmentUnbeatable) as failure:
        finish(built, base, assignment)
    assert failure.value.sanity.strict == "E1"
