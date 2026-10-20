"""The logic with Randomize Dead Woods (beta 7 rework; overworld_gates.py): a screen needs the maze's
hint only when its cave entrance is reached solely through the maze, $70, $71 and $72's cave. The
river's west half, FP-BRIDGE-01's 34 rooms, is walked into by Add Lost Woods Shortcut (B88, which
Randomize Dead Woods forces on; one-way from $51 into $50, out again by the maze's free east exit)
or over Add Bridges to the River (B87), so it needs neither the hint nor the ladder. On generated
seeds, the acceptance check and Archipelago's logic model (which derives its screen events from the
acceptance check's own rules) agree: every tracked item and level, the hint shop moved out of the
pocket, and nothing in the pocket without the hint."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from tests.test_assignment import identity
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.acceptance_check import DEFAULT_RULES, AcceptanceCheck
from zora.generate.logic import EventTerm, logic_model, sweep, triforce_event
from zora.generate.pipeline import Built, build, extra_options, plan
from zora.generate.steps import overworld_gates as gates
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom

DEAD_WOODS = zora_flags.encode(zora_flags.ZoraFlags(randomize_dead_woods=ThreeState.ON))
CASES = {"shortcut": MVP_BASELINE_LEVEL_ENCODING_OFF,
         "shortcut and bridges": encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B87": ThreeState.ON}))}
SEEDS = range(1, 9)
HINT = EventTerm("Dead Woods Hint")
TRIFORCE_LEVELS = range(1, 9)


@cache
def built(case: str, seed: int) -> Built:
    return build(plan(CASES[case], seed, DEAD_WOODS), remember_repo_base_rom())


def check(seed: Built) -> AcceptanceCheck:
    state, caves = seed.result.item_shuffle_result, seed.result.overworld
    assert state is not None and caves is not None
    return AcceptanceCheck(seed.world.levels, state, seed.world.overworld, caves, extra_options(seed.plan).logic_rules)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(CASES))
def test_only_the_pocket_needs_the_hint(case: str, seed: int) -> None:
    accepted = check(built(case, seed))
    assert extra_options(built(case, seed).plan).gates.river_west_open
    for screen in gates.DEAD_WOODS_WEST:
        assert accepted.rules.needs(screen) == DEFAULT_RULES.needs(screen), hex(screen)
    for screen in gates.DEAD_WOODS_GATED:
        assert not accepted.reaches_screen(screen, frozenset())
        assert accepted.reaches_screen(screen, frozenset({gates.DEAD_WOODS_HINT}))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(CASES))
def test_the_logic_model_agrees_with_the_acceptance_check(case: str, seed: int) -> None:
    """Every tracked item and level the closure takes, the sweep takes too, the goal included; a
    level whose door is in the pocket needs the hint, one in the west half never does."""
    seed_built = built(case, seed)
    model = logic_model(seed_built)
    swept = sweep(model, identity(seed_built))
    held, completed = check(seed_built).closure()
    assert swept.reaches_goal
    assert {level for level in TRIFORCE_LEVELS if triforce_event(level) in swept.events} == completed
    assert gates.DEAD_WOODS_HINT in held and HINT.name in swept.events
    caves = seed_built.result.overworld
    assert caves is not None
    for level in TRIFORCE_LEVELS:
        rule = model.events[triforce_event(level)]
        door = caves.entry_door(level)
        if door in gates.DEAD_WOODS_GATED:
            assert all(HINT in clause for clause in rule), (seed, level)
        if door in gates.DEAD_WOODS_WEST:
            assert not all(HINT in clause for clause in rule), (seed, level)


@pytest.mark.parametrize("seed", SEEDS)
def test_the_hint_shop_stays_out_of_the_pocket(seed: int) -> None:
    """The earlier fixes still hold: the hint shop selling the Dead Woods' path never stands in the
    pocket (sell_dead_woods_path_outside_the_forest, the cave walk's _is_gated_exchange)."""
    caves = built("shortcut", seed).result.overworld
    assert caves is not None
    shop = next(entry for entry in caves.entries if entry.code == gates.DEAD_WOODS_HINT_SHOP)
    assert shop.screen not in gates.DEAD_WOODS_GATED
