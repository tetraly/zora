"""The two walks (dungeon_walk.WalkRules; docs/archipelago.md "The two walks").

Generation, its acceptance check and the hint text walk by VA-REJ-17/18 as written (SPEC_WALK),
so ZORA-mode output and the original randomizer's validator are untouched, but for ZORA's own E10,
whose Ganon is judged on LOGIC_WALK with the last-boss shutters shut (docs/deviations.md);
Archipelago's rules and FINISH's sanity check walk by LOGIC_WALK, whose corrections were measured in the emulator
(docs/reports/unreachable-places.md):
  - the ladder crosses a horizontal, double or vertical moat room from any side;
  - the turnstile room ($60) turns from N or S to W and E, from W or E to N and S;
  - a target room may be walked through, to arrive by another side;
  - level 9's last-boss shutters are open while the Triforce of Power is held."""
from dataclasses import replace
from typing import Any

import pytest

from tests.archipelago_cases import FLAG_CASES
from zora.flags.presets import ASNB_FLAGS, ASNB_ZORA_FLAGS, MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate import acceptance_check, dungeon_walk
from zora.generate.acceptance_check import LEVEL9_ENTRY, LONG_ITEMS, AcceptanceCheck, LogicRules, logic_walk_rules
from zora.generate.dungeon_walk import (
    FAMILY_ITEMS,
    LADDER_MOAT_LAYOUTS,
    LOGIC_WALK,
    MEASURED_TURNSTILE_ROW,
    SPEC_WALK,
    TURNSTILE_PUSH_ROW,
    WalkRules,
    walk_level,
)
from zora.generate.pipeline import build, extra_options, plan
from zora.generate.steps import add_l4_sword, hint_text, randomize_magical_sword
from zora.model.enums import Item, RoomType, Side
from zora.model.levels import Level
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

CASES = {**FLAG_CASES, "all swords no boards": (ASNB_FLAGS, ASNB_ZORA_FLAGS)}
HELD = frozenset(FAMILY_ITEMS | LONG_ITEMS | {LEVEL9_ENTRY})
WALK_CALLERS = (acceptance_check, hint_text, add_l4_sword, randomize_magical_sword)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


def level_of(base: bytes, seed: int, level_num: int) -> Level:
    world = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, ""), base).world
    return next(level for level in world.levels if level.level_num == level_num)


# --- generation keeps the spec walk ------------------------------------------------------------

@pytest.mark.parametrize("case", list(CASES))
def test_generation_walks_by_the_spec(base: bytes, case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every walk generation runs (acceptance, the heart check, Add L4 Sword, the hints) is
    SPEC_WALK's, and the rules generation builds name it; E10's walk to Ganon alone is
    LOGIC_WALK's, its shutters shut (no Triforce of Power held)."""
    walks: list[tuple[WalkRules, bool]] = []          # each walk's rules, and whether E10 ran it
    in_e10: list[bool] = []
    judge_ganon = AcceptanceCheck.reaches_ganon_before_shutters_open

    def recording(*args: Any, walk_rules: WalkRules = SPEC_WALK, **kwargs: Any) -> dungeon_walk.Walk:
        walks.append((walk_rules, bool(in_e10)))
        assert not (walk_rules.triforce_of_power_opens and kwargs.get("is_last_boss_open"))
        return dungeon_walk.walk_level(*args, **{**kwargs, "walk_rules": walk_rules})

    def judged(check: AcceptanceCheck) -> bool:
        in_e10.append(True)
        try:
            return judge_ganon(check)
        finally:
            in_e10.pop()

    for module in WALK_CALLERS:
        monkeypatch.setattr(module, "walk_level", recording)
    monkeypatch.setattr(AcceptanceCheck, "reaches_ganon_before_shutters_open", judged)
    chosen = plan(*CASES[case][:1], 1, CASES[case][1])
    assert extra_options(chosen).logic_rules.walk is SPEC_WALK
    build(chosen, base)
    assert walks and all(walk is SPEC_WALK for walk, by_e10 in walks if not by_e10)
    assert any(by_e10 for _walk, by_e10 in walks)
    assert all(walk in (SPEC_WALK, LOGIC_WALK) for walk, by_e10 in walks if by_e10)


def test_the_defaults() -> None:
    assert LogicRules().walk is SPEC_WALK
    assert acceptance_check.DEFAULT_RULES.walk is SPEC_WALK
    assert logic_walk_rules(LogicRules()).walk is LOGIC_WALK
    assert SPEC_WALK == WalkRules() and not (SPEC_WALK.ladder_moats or SPEC_WALK.measured_turnstile
                                             or SPEC_WALK.through_target or SPEC_WALK.triforce_of_power_opens)


# --- the corrections ---------------------------------------------------------------------------

def test_the_measured_turnstile_holds_vareq18s_row() -> None:
    """Each entry side reaches both perpendicular doorways; VA-REJ-18's one turn is among them."""
    perpendicular = {Side.NORTH: {Side.WEST, Side.EAST}, Side.SOUTH: {Side.WEST, Side.EAST},
                     Side.WEST: {Side.NORTH, Side.SOUTH}, Side.EAST: {Side.NORTH, Side.SOUTH}}
    for side, turns in perpendicular.items():
        assert MEASURED_TURNSTILE_ROW[side] == turns
        assert TURNSTILE_PUSH_ROW[side] <= turns
    assert LADDER_MOAT_LAYOUTS == {RoomType.HORIZONTAL_MOAT_ROOM, RoomType.DOUBLE_MOAT_ROOM,
                                   RoomType.VERTICAL_MOAT_ROOM}


@pytest.mark.parametrize(("seed", "level_num", "room", "what"), [
    (32, 2, 0x15, "double moat entered by N and S"),
    (83, 5, 0x3C, "horizontal moat entered by N"),
    (110, 7, 0x06, "vertical moat entered by E"),
])
def test_the_ladder_crosses_a_moat(base: bytes, seed: int, level_num: int, room: int, what: str) -> None:
    level = level_of(base, seed, level_num)
    for walk_rules, ladder, accepted in ((SPEC_WALK, True, False), (LOGIC_WALK, True, True),
                                         (LOGIC_WALK, False, False)):
        held = HELD | {Item.LADDER} if ladder else HELD - {Item.LADDER}
        walk = walk_level(level, held, False, True, target=room, walk_rules=walk_rules)
        assert walk.accepts(level, room) == accepted, (what, walk_rules, ladder)


def test_the_turnstile_opens_level_9s_cellar(base: bytes) -> None:
    """Seed 370: level 9's item cellar $52 (under room $04) lies past a turnstile room, reached only by
    its measured line: the spec walk with the measured turnstile alone reaches it (seed 2's cellar $30
    until 114f280 moved it)."""
    level = level_of(base, 370, 9)
    held = HELD | {Item.LADDER}
    assert 0x52 not in walk_level(level, held, False, True, walk_rules=SPEC_WALK).cellars
    assert 0x52 in walk_level(level, held, False, True,
                              walk_rules=replace(SPEC_WALK, measured_turnstile=True)).cellars
    assert 0x52 in walk_level(level, held, False, True, walk_rules=LOGIC_WALK).cellars


def test_the_target_room_is_walked_through(base: bytes) -> None:
    """Seed 200: level 5's T room $45 (item position C) is reached by N only if the walk stops in
    it; walked through (out by E, round to S), its arrival rule accepts."""
    level = level_of(base, 200, 5)
    held = HELD | {Item.LADDER}
    assert not walk_level(level, held, False, True, target=0x45).accepts(level, 0x45)
    assert walk_level(level, held, False, True, walk_rules=LOGIC_WALK).accepts(level, 0x45)
