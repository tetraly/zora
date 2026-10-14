"""Every item place and every event has a rule some item set satisfies, and the goal stays
reachable (docs/reports/unreachable-places.md; docs/archipelago.md "The two walks").

Archipelago's rules come from the logic walk (dungeon_walk.LOGIC_WALK): the ladder crosses the
three moat layouts from any side, the turnstile room turns as the emulator measured it, a target
room may be walked through, and level 9's last-boss shutters are open while the Triforce of Power
is held. That event is Ganon's fixed drop (his room reached, his family list unblocked); the places
past those shutters require it, and so does Zelda. Before the logic walk, 39 places of 36 builds
(the five flag cases x seeds 0-99) had a FALSE rule; REPORTED keeps the report's seeds and causes.

Cases: tests/archipelago_cases.py, plus All Swords No Boards (Add L4 Sword = Level 2, Level 9
Entrance = Level 4 sword), whose level-9 entry is a sword count."""
from dataclasses import replace

import pytest

from tests.archipelago_cases import FLAG_CASES
from zora import archipelago
from zora.flags.presets import ASNB_FLAGS, ASNB_ZORA_FLAGS
from zora.generate.logic import FALSE, TRIFORCE_OF_POWER_EVENT, ZELDA_EVENT, EventTerm, sweep
from zora.generate.places import read_item
from zora.model.enums import Item
from zora.model.item_names import ITEM_NAMES
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

CASES = {**FLAG_CASES, "all swords no boards": (ASNB_FLAGS, ASNB_ZORA_FLAGS)}
SCAN_SEEDS = range(100)
# The sweep runs as chunks of 10 seeds, so no one test holds a worker for minutes at the end of
# the slow suite (docs/design/test-speed.md 3.3): the same seeds and the same check in all
SCAN_CHUNKS = [SCAN_SEEDS[start:start + 10] for start in range(0, len(SCAN_SEEDS), 10)]
# The default options' FALSE places before the logic walk, by cause (the report's seeds).
REPORTED: dict[int, dict[str, str]] = {
    0: {"Level 9 Room 37 Cellar": "after Ganon"},     # stair room faces Zelda's room
    2: {"Level 9 Room 21 Cellar": "turnstile"},
    6: {"Level 9 Room 73 Cellar": "after Ganon"},     # behind Ganon's room
    32: {"Level 2 Room 15": "ladder"},                # double moat by N
    83: {"Level 5 Room 3C": "ladder"},                # horizontal moat by N
    87: {"Level 9 Room 0B Cellar": "after Ganon"},
    93: {"Level 9 Room 20 Cellar": "after Ganon", "Level 9 Room 46 Cellar": "after Ganon"},
}
# The first seed of each other case that had a FALSE place, and two of ASNB's.
OTHER_SEEDS = {"every owner flag on": 15, "every turn-off value, every owner flag on": 0,
               "magical sword and letter": 1, "every ZORA flag on": 8, "all swords no boards": 3}
QUICK = [("baseline", seed) for seed in REPORTED] + list(OTHER_SEEDS.items()) + [("all swords no boards", 4)]


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


_BUILDS: dict[tuple[str, int], archipelago.BuildResult] = {}


def built(case: str, seed: int, base: bytes) -> archipelago.BuildResult:
    if (case, seed) not in _BUILDS:
        _BUILDS[case, seed] = archipelago.build_from_strings(*CASES[case], seed, base)
    return _BUILDS[case, seed]


def false_rules(result: archipelago.BuildResult) -> list[str]:
    """The places, events and goal whose rule no item set satisfies."""
    logic = result.logic
    found = [name for name, rule in logic.places.items() if rule == FALSE]
    found += [f"event {name}" for name, rule in logic.events.items() if rule == FALSE]
    return found + (["the goal"] if logic.goal == FALSE else [])


def requires_triforce_of_power(rule: frozenset) -> bool:
    return bool(rule) and all(EventTerm(TRIFORCE_OF_POWER_EVENT) in clause for clause in rule)


@pytest.mark.parametrize(("case", "seed"), QUICK)
def test_no_false_rule(base: bytes, case: str, seed: int) -> None:
    assert false_rules(built(case, seed, base)) == []


@pytest.mark.parametrize(("case", "seed"), QUICK)
def test_every_place_and_the_goal_stay_reachable(base: bytes, case: str, seed: int) -> None:
    """With every item of the pool received (each place's item), the sweep collects every place
    and reaches Zelda: no place's rule needs more than the pool holds (the Triforce of Power is
    an event, never received)."""
    result = built(case, seed, base)
    swept = sweep(result.logic, {}, [read_item(result.state.world, place) for place in result.state.places])
    assert swept.places == set(result.logic.places)
    assert swept.reaches_goal and TRIFORCE_OF_POWER_EVENT in swept.events


@pytest.mark.parametrize("seed", list(REPORTED))
def test_the_reported_places_get_real_rules(base: bytes, seed: int) -> None:
    """Each reported place is still a place, with a rule; those past the last-boss shutters
    require the Triforce of Power, the others never do."""
    logic = built("baseline", seed, base).logic
    for name, cause in REPORTED[seed].items():
        rule = logic.places[name]
        assert rule != FALSE, name
        assert requires_triforce_of_power(rule) == (cause == "after Ganon"), (name, cause)


@pytest.mark.parametrize(("case", "seed"), QUICK)
def test_the_triforce_of_power_is_one_event(base: bytes, case: str, seed: int) -> None:
    """The Triforce of Power is the model's one Ganon event (no second "Ganon" event): Zelda requires
    it, it is never a place or in the pool, and no place requires it unless the logic walk's
    shutters do (it never appears outside level 9)."""
    result = built(case, seed, base)
    logic = result.logic
    assert "Ganon" not in logic.events and TRIFORCE_OF_POWER_EVENT in logic.events
    assert requires_triforce_of_power(logic.events[ZELDA_EVENT])
    assert ITEM_NAMES[Item.TRIFORCE_OF_POWER] not in result.pool
    assert all(read_item(result.state.world, place) != Item.TRIFORCE_OF_POWER for place in result.state.places)
    for place in result.state.places:
        if any(EventTerm(TRIFORCE_OF_POWER_EVENT) in clause for clause in logic.places[place.name]):
            assert place.level == 9, place.name


def test_a_place_behind_ganons_shutters_requires_the_triforce_of_power(base: bytes) -> None:
    """Seed 6's L9 $73 cellar: $73's only door is Ganon's room's south shutter. Its rule requires
    the Triforce of Power; with the event's own requirements (and everything else) met but the event
    left out, the place is not collected."""
    result = built("baseline", 6, base)
    name = "Level 9 Room 73 Cellar"
    assert requires_triforce_of_power(result.logic.places[name])
    pool = [read_item(result.state.world, place) for place in result.state.places]
    without = replace(result.logic, events={event: rule for event, rule in result.logic.events.items()
                                            if event != TRIFORCE_OF_POWER_EVENT})
    assert name not in sweep(without, {}, pool).places
    assert name in sweep(result.logic, {}, pool).places


@pytest.mark.slow
@pytest.mark.parametrize("chunk", SCAN_CHUNKS, ids=lambda chunk: f"seeds {chunk[0]}-{chunk[-1]}")
@pytest.mark.parametrize("case", list(CASES))
def test_no_false_rule_over_100_seeds(base: bytes, case: str, chunk: range) -> None:
    """No FALSE place, event or goal in seeds 0-99 of any case (ten seeds per test)."""
    found = {seed: names for seed in chunk
             if (names := false_rules(archipelago.build_from_strings(*CASES[case], seed, base)))}
    assert not found, found
