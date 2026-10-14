"""The requirement hints know the owner's overworld gates (HT-HINT-01; overworld_gates.py).

A player's 2.0 beta 2 report: seed 1109332123 (Extra Raft Blocks on) put level 2's door on a new
raft block, $1F, and level 2 said THE PRINCESS NEEDS NO RAFT (now THE HERO'S PATH). HT-HINT-01's screen sets are PRG0's;
hint_text.gated_screens adds each gate's screens to its means (the raft blocks to the raft, the
bracelet blocks to the bracelet, Randomize Dead Woods' west half to the ladder), as the acceptance
check's screen needs already do.

Each candidate's claim is checked against the acceptance check's screen needs (gates included)
and the logic model's sweep, everything in the pool given but the means:
  - "X NEEDS THE M" from a door (rule 1): M is among the needs of the door of a level holding X;
    for levels 1-8 the sweep collects none of that level's X without M (level 9's entry asks for
    every long item, VA-REJ-08, so the sweep cannot tell there). A rule-2 claim (the spec's
    inside-dungeon walk) is accepted as the spec's;
  - "THE X CAVE NEEDS THE M": M is among the white-sword cave screen's needs;
  - "THE HERO'S PATH NEEDS NO M": no level's door needs M, and the sweep takes every triforce
    without M (a door behind a maze needs what the maze's hint shop needs, hint_text.door_needs).
  - "THE PATH TO X LIES BENEATH A GRAVESTONE": HT-HINT-01's bracelet door set holds the
    graveyard's $20 and $21, whose door opens by pushing a gravestone, without the bracelet
    (owner ruling, 2026-10-10; emulator): a level holding X has its door there. Every other
    bracelet door text says NEEDS THE BRACELET.
The coast's ladder text is PRG0's fact. Cases: each gate, every gate, the report's flags, and with
no gate the first quest and the mixed overworld quest (C01 = 2, where $20 can be a door too)."""
import json
from dataclasses import replace
from typing import Any

import pytest

from tests.test_coop_reserved import BASELINE_FOR_OWNER_FLAGS, z1r_with
from zora import archipelago
from zora.flags import zora_flags
from zora.flags.fields import OverworldQuest, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.logic import LogicModel, Swept, sweep, triforce_event
from zora.generate.pipeline import Built, extra_options
from zora.generate.places import read_item
from zora.generate.steps import hint_text
from zora.generate.steps.hint_text import Form, Requirement
from zora.generate.steps.overworld_gates import NO_GATES
from zora.model.enums import Destination, Item
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora_web.api import generate_rom, seed_report

PLAYER_FLAGS = ("8hq4BeR1JXo7ygQD!vLBwTXdKSUJ3A", "4.Ea9wH")   # the report's strings
PLAYER_SEED = 1109332123
OWNER_Z1R = z1r_with(toggles=BASELINE_FOR_OWNER_FLAGS)
GATE_FLAGS = ("extra_raft_blocks", "extra_power_bracelet_blocks", "randomize_lost_hills", "randomize_dead_woods")


def with_gates(*names: str) -> tuple[str, str]:
    on: dict[str, Any] = dict.fromkeys(names, ThreeState.ON)
    return OWNER_Z1R, zora_flags.encode(replace(zora_flags.DEFAULT, **on))


CASES = {**{name: with_gates(name) for name in GATE_FLAGS}, "every gate": with_gates(*GATE_FLAGS),
         "the report's flags": PLAYER_FLAGS, "no gate": (MVP_BASELINE_LEVEL_ENCODING_OFF, ""),
         "mixed overworld quest": (z1r_with(options={"C01": OverworldQuest.MIXED_FIRST_QUEST_VARIANT}), "")}
QUICK_SEEDS = range(3)
SWEEP_SEEDS = range(100)
# The sweep runs as chunks of 10 seeds, so no one test holds a worker for minutes at the end of
# the slow suite (docs/design/test-speed.md 3.3): the same seeds and the same check in all
SWEEP_CHUNKS = [SWEEP_SEEDS[start:start + 10] for start in range(0, len(SWEEP_SEEDS), 10)]
MEANS = {Form.RAFT: Item.RAFT, Form.LADDER: Item.LADDER, Form.BRACELET: Item.POWER_BRACELET,
         Form.RECORDER: Item.RECORDER, Form.BOW: Item.BOW, Form.NO_RAFT: Item.RAFT,
         Form.NO_BRACELET: Item.POWER_BRACELET}
TRIFORCE_LEVELS = range(1, 9)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


def candidates(built: Built) -> tuple[list[tuple[int, int]], list[Requirement]]:
    """The build's level items and every HT-HINT-01 candidate (the drawn ten among them)."""
    shuffled = built.result.item_shuffle_result
    assert shuffled is not None
    level_items = [(place.item, place.level) for place in shuffled.tracked if place.level is not None]
    return level_items, hint_text.requirement_candidates(built.world, level_items, shuffled.items_within_levels,
                                                         extra_options(built.plan).gates)


def false_requirements(built: Built, logic: LogicModel) -> list[str]:
    """Each candidate whose claim the acceptance check's screen needs or the sweep refutes."""
    rules = extra_options(built.plan).logic_rules
    caves = built.result.overworld
    assert caves is not None
    door = {level: caves.entry_door(level) for level in range(1, 10)}
    pool = [read_item(built.world, place) for place in built.places]
    level_items, found = candidates(built)
    coast = hint_text.coast_item(built.world)
    refuted = []
    for candidate in found:
        if candidate.form == Form.BOSS or (candidate.form == Form.LADDER and candidate.item == coast
                                            and not candidate.white_sword_cave):
            continue
        means = MEANS[candidate.form]
        without = sweep(logic, {}, [item for item in pool if item != means])
        if candidate.item is None:
            holds = (not any(means in rules.needs(screen) for screen in door.values())
                     and all(triforce_event(level) in without.events for level in TRIFORCE_LEVELS))
        elif candidate.gravestone:
            holds = any(door[level] in hint_text.GRAVESTONE_SCREENS for item, level in level_items
                        if item == candidate.item)
        elif candidate.white_sword_cave:
            holds = all(means in rules.needs(screen) for screen in caves.movable_screens(Destination.WHITE_SWORD_CAVE))
        else:
            holds = any(door_claim_holds(built, without, door[level], level, candidate.item, means)
                        or inside_claim_holds(built, level, candidate.item, means)
                        for item, level in level_items if item == candidate.item)
        text = " ".join(hint_text.requirement_text(candidate))
        if candidate.form == Form.BRACELET and not candidate.white_sword_cave:
            holds = holds and (("BENEATH A GRAVESTONE" in text) == candidate.gravestone
                               and ("NEEDS THE BRACELET" in text) != candidate.gravestone)
        if not holds:
            refuted.append(f"{candidate.form}: {candidate.item and Item(candidate.item).name}"
                           f"{' (white-sword cave)' if candidate.white_sword_cave else ''}")
    return refuted


def door_claim_holds(built: Built, without: Swept, screen: int, level: int, item: int, means: Item) -> bool:
    """Rule 1: the level's door needs the means; for levels 1-8 the sweep without it collects none
    of the level's places holding the item."""
    if means not in extra_options(built.plan).logic_rules.needs(screen):
        return False
    if level == 9:
        return True
    holders = [place.name for place in built.places
               if place.level == level and int(read_item(built.world, place)) == item]
    return bool(holders) and not any(name in without.places for name in holders)


def inside_claim_holds(built: Built, level: int, item: int, means: Item) -> bool:
    """Rule 2 (the spec's inside-dungeon walk): the sword alone does not enter the item's room, the
    sword and the means do."""
    place = hint_text.item_place(built.world.levels, level, item)
    return place is not None and means in {MEANS[form] for form in hint_text.inside_dungeon_needs(place, item)}


_BUILDS: dict[tuple[str, int], archipelago.BuildResult] = {}


def built_case(case: str, seed: int, base: bytes) -> archipelago.BuildResult:
    if (case, seed) not in _BUILDS:
        _BUILDS[case, seed] = archipelago.build_from_strings(*CASES[case], seed, base)
    return _BUILDS[case, seed]


def test_the_reported_seed(base: bytes) -> None:
    """Level 2's door is on raft block $1F (and level 7's on bracelet block $12): no NEEDS NO
    RAFT (or BRACELET) candidate; level 2's item is said to need the raft; every claim holds."""
    result = built_case("the report's flags", PLAYER_SEED, base)
    built = result.state
    assert built.result.overworld is not None
    assert built.result.overworld.entry_door(2) == 0x1F and built.result.overworld.entry_door(7) == 0x12
    level_items, found = candidates(built)
    forms = {candidate.form for candidate in found}
    assert Form.NO_RAFT not in forms and Form.NO_BRACELET not in forms
    level_2_items = {item for item, level in level_items if level == 2}
    assert any(candidate.form == Form.RAFT and candidate.item in level_2_items for candidate in found)
    assert false_requirements(built, result.logic) == []


def test_the_reported_seeds_hints(base: bytes) -> None:
    """The finished ROM's hint texts: no NEEDS NO RAFT or NEEDS NO BRACELET."""
    made = generate_rom(PLAYER_FLAGS[0], PLAYER_SEED, base, zora_flag_string=PLAYER_FLAGS[1])
    texts = [hint["text"] for hint in json.loads(seed_report(made.rom, PLAYER_FLAGS[0], PLAYER_SEED,
                                                             PLAYER_FLAGS[1])["json"])["hints"]]
    assert not any("NEEDS NO" in text for text in texts), texts


@pytest.mark.parametrize(("case", "seed", "level", "door", "fallback"), [
    ("randomize_dead_woods", 10, 2, 0x70, Form.NO_RAFT),     # Hint Shop 2 behind the raft
    ("the report's flags", 267, 3, 0x0B, Form.NO_BRACELET),   # Lost Hills -> Hint Shop 1 behind
    ("the report's flags", 320, 1, 0x71, Form.NO_RAFT),       # Dead Woods, Hint Shop 2 behind Lost
])                                                            # Hills, Hint Shop 1 behind the raft
def test_a_door_behind_a_maze_needs_what_its_hint_needs(base: bytes, case: str, seed: int, level: int, door: int,
                                                        fallback: str) -> None:
    """A level behind a randomized maze needs the maze's hint, so what every door of the maze's
    hint shop needs (through the other maze too): no fallback says it is not needed."""
    result = built_case(case, seed, base)
    built = result.state
    assert built.result.overworld is not None and built.result.overworld.entry_door(level) == door
    _, found = candidates(built)
    assert Requirement(fallback) not in found
    assert false_requirements(built, result.logic) == []


@pytest.mark.parametrize(("case", "seed", "level", "door", "item"), [
    ("no gate", 5, 1, 0x21, Item.WAND),                       # the emulator's: pushed open, no bracelet
    ("mixed overworld quest", 77, 6, 0x20, Item.WOOD_BOOMERANG),
])
def test_a_door_under_a_gravestone(base: bytes, case: str, seed: int, level: int, door: int, item: Item) -> None:
    """A bracelet door on the graveyard says the path lies beneath a gravestone; the finished ROM
    shows that text, and no text says the item needs the bracelet."""
    flags, zora_flag_string = CASES[case]
    built = built_case(case, seed, base).state
    assert built.result.overworld is not None and built.result.overworld.entry_door(level) == door
    _, found = candidates(built)
    assert Requirement(Form.BRACELET, item, gravestone=True) in found
    assert Requirement(Form.BRACELET, item) not in found
    made = generate_rom(flags, seed, base, zora_flag_string=zora_flag_string)
    texts = [hint["text"] for hint in json.loads(seed_report(made.rom, flags, seed, zora_flag_string)["json"])["hints"]
             if hint.get("speaker")]
    name = hint_text.item_name(item)
    assert f"THE PATH TO THE {name} LIES BENEATH A GRAVESTONE." in texts
    assert f"THE {name} NEEDS THE BRACELET" not in texts


def test_the_gravestone_text_fits_for_every_item() -> None:
    """Every item, upgrade line and another player's item, with its own article, in the box."""
    namings = (hint_text.VANILLA_NAMES, hint_text.PROGRESSIVE_NAMES, hint_text.ItemNames(foreign_code=Item.BAIT))
    for names in namings:
        for code in range(len(hint_text.ITEM_NAMES)):
            lines = hint_text.requirement_text(Requirement(Form.BRACELET, code, gravestone=True), names)
            assert 1 <= len(lines) <= hint_text.MAX_LINES and all(len(line) <= hint_text.LINE_WIDTH for line in lines)
            assert hint_text.quote_problems(lines) == [], lines
            assert " ".join(lines) == f"THE PATH TO {names.phrase(code)} LIES BENEATH A GRAVESTONE."


def test_no_gates_means_prg0s_sets() -> None:
    """With the gates off the screen sets are HT-HINT-01's, so ZORA-mode output is unchanged."""
    assert not any(hint_text.gated_screens(NO_GATES).values())
    assert hint_text.door_means(frozenset({66})) == hint_text.door_means(frozenset({66}), NO_GATES)


@pytest.mark.parametrize("seed", QUICK_SEEDS)
@pytest.mark.parametrize("case", list(CASES))
def test_every_requirement_hint_holds(base: bytes, case: str, seed: int) -> None:
    result = built_case(case, seed, base)
    assert false_requirements(result.state, result.logic) == []


@pytest.mark.slow
@pytest.mark.parametrize("chunk", SWEEP_CHUNKS, ids=lambda chunk: f"seeds {chunk[0]}-{chunk[-1]}")
@pytest.mark.parametrize("case", list(CASES))
def test_every_requirement_hint_holds_over_100_seeds(base: bytes, case: str, chunk: range) -> None:
    """Every requirement hint holds in seeds 0-99 of every case (ten seeds per test)."""
    found = {}
    for seed in chunk:
        result = archipelago.build_from_strings(*CASES[case], seed, base)
        if refuted := false_requirements(result.state, result.logic):
            found[seed] = refuted
    assert not found, found
