"""FINISH's sanity walk counts a joined sword wherever Archipelago's assignment puts it (2.0.2, 2026-11-22).

check_apworld's seed 13 failed everyone's generation (player ZORA5: Randomize Magical Sword, Offense Item Pacing
Earlier): Archipelago's logic counts the Magical Sword in the Sword line wherever it lies, and placed it as the
second sword; ZORA's walk kept no record of it, counted one sword fewer and FINISH refused the placement. The fix
is generation's (generation_pass.sword_is_tracked: a joined sword is tracked whenever the walk counts swords), and
FINISH's rebuild_tracking finds that record again wherever the assignment moves it. The case here fails with that
fix removed (and with 32b89313's FINISH-only rule, since retired, gone too).

The Letter (Randomize Letter) is the other item BUILD can deal without a record: the logic asks for it only at the
potion shop, a place only with Shuffle Blue Potion, and there FINISH already tracks it wherever it lies.

FINISH judges Offense Item Pacing's sword caves by the hearts the shipped caves ask, not the most their draw can give
(test_finish_asks_the_sword_caves_own_hearts)."""
from typing import Any

import pytest

from zora import archipelago
from zora.generate.finish import rebuild_tracking
from zora.generate.logic import CountTerm, sweep
from zora.generate.pipeline import finish_world
from zora.model.enums import Item
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

# Seed 0 (2.0.2's 12-heart cap changed Archipelago's default Magical Sword Hearts (max), and seed 2's builds with
# it): the sword swap stays beatable and fails without generation_pass.sword_is_tracked (seeds 0-9 checked; seed 2's
# swap was now unbeatable, which skipped the test), and the potion shop holds a tracked ware (the Bow), which FINISH
# tracks the Letter for (seed 2's held a Heart Container BUILD leaves untracked)
SEED = 0
PACED = {"randomize_magical_sword": "on", "magical_sword_hearts_highest": "at_most_12_hearts",
         "offense_pacing": "earlier"}
LETTER_CASES = {"letter alone": {"randomize_letter": "on"},
                "letter and blue potion": {"randomize_letter": "on", "shuffle_blue_potion": "on"}}


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


def own(result: archipelago.BuildResult) -> dict[str, Any]:
    """The build's own items, by place, as Archipelago names them."""
    return {place.name: name for place, name in zip(result.places, result.pool, strict=True)}


def second_sword_case(base: bytes) -> tuple[archipelago.BuildResult, dict[str, Any]]:
    """A paced seed whose Magical Sword (randomized, untracked by BUILD) sits where one sword opens, and whose White
    Sword sits where two swords are asked: the Magical Sword must be the second."""
    result = archipelago.build_from_strings(*archipelago.flag_strings(PACED), SEED, base)
    assignment = own(result)
    rules = result.logic.places
    magical = next(place for place, name in assignment.items() if name == "Magical Sword")
    white = next(place for place, name in assignment.items() if name == "White Sword")

    def swords_asked(place: str) -> int:
        terms = [term for clause in rules[place] for term in clause
                 if isinstance(term, CountTerm) and term.line == "Sword"]
        return max((term.count for term in terms), default=0)

    one = next(place for place in assignment if place.startswith("Level ") and swords_asked(place) <= 1
               and assignment[place] not in ("Magical Sword", "White Sword"))
    two = next(place for place in assignment if swords_asked(place) == 2
               and assignment[place] not in ("Magical Sword", "White Sword"))
    assignment[magical], assignment[one] = assignment[one], "Magical Sword"
    assignment[white], assignment[two] = assignment[two], "White Sword"
    return result, assignment


def test_the_magical_sword_counts_as_the_second_sword(base: bytes) -> None:
    result, assignment = second_sword_case(base)
    swept = sweep(result.logic, archipelago.assigned_items(assignment, result.state.world))
    if not swept.reaches_goal:
        pytest.skip("the swap made this seed unbeatable for the logic too")
    _world, finished = finish_world(result.state, archipelago.assigned_items(assignment, result.state.world))
    assert finished.sanity is not None and not finished.sanity.hard_failure
    assert any(record.item == Item.MAGICAL_SWORD for record in finished.tracking.tracked)
    archipelago.finish(result, assignment)


@pytest.mark.parametrize("case", LETTER_CASES)
def test_the_letter_is_asked_only_where_it_is_tracked(base: bytes, case: str) -> None:
    """Randomize Letter: the logic names the Letter only with Shuffle Blue Potion, and FINISH then tracks it wherever
    the assignment puts it, here a level room."""
    result = archipelago.build_from_strings(*archipelago.flag_strings(LETTER_CASES[case]), SEED, base)
    names_letter = any("LETTER" in str(rule) or "Letter" in str(rule) for rule in result.logic.places.values())
    blue_potion = "shuffle_blue_potion" in LETTER_CASES[case]
    assert names_letter == blue_potion
    assignment = own(result)
    letter = next(place for place, name in assignment.items() if name == "Letter")
    room = next(place for place in assignment if place.startswith("Level ") and assignment[place] != "Letter")
    assignment[letter], assignment[room] = assignment[room], "Letter"
    world, _finished = finish_world(result.state, archipelago.assigned_items(assignment, result.state.world),
                                    check=False)
    tracked = rebuild_tracking(world, result.state).tracked
    assert any(record.item == Item.LETTER for record in tracked) == blue_potion


# Scan of 2026-11-22 (Add L4 Sword: Level 2, Offense Item Pacing: Earlier): the logic model counts the Magical Sword
# Cave's own sword at the 10 hearts its cave asks; FINISH asked the 14 its draw could give at most, never counted
# that sword, and refused the assignment (E1). pipeline.shipped_logic_rules now asks the shipped caves' own counts.
CAVE_HEARTS_SEED, CAVE_HEARTS_SHUFFLE = 6, 0


def test_finish_asks_the_sword_caves_own_hearts(base: bytes) -> None:
    from dataclasses import replace

    from tests.test_assignment import permuted
    from zora.flags import zora_flags
    from zora.flags.fields import ThreeState
    from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
    from zora.flags.zora_flags import Pacing
    from zora.generate.logic import logic_model
    from zora.generate.pipeline import build, extra_options, plan, shipped_logic_rules
    from zora.model.enums import Destination
    from zora.model.overworld import ItemCave

    flags = replace(zora_flags.ZoraFlags(), progressive_items=True, add_l4_sword=ThreeState.ON,
                    l4_sword_in_level_2=True, offense_pacing=Pacing.EARLIER)
    built = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, CAVE_HEARTS_SEED, zora_flags.encode(flags)), base)
    cave = built.world.overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    drawn_highest = extra_options(built.plan).logic_rules.pacing_hearts
    shipped = shipped_logic_rules(built.plan, built.world).pacing_hearts
    assert cave is not None and drawn_highest is not None and shipped is not None
    assert shipped.magical_sword == cave.heart_requirement < drawn_highest.magical_sword
    assignment = permuted(built, CAVE_HEARTS_SEED * 1000 + CAVE_HEARTS_SHUFFLE)
    assert sweep(logic_model(built), assignment).reaches_goal
    _world, finished = finish_world(built, assignment)            # raised AssignmentUnbeatable (E1) before the fix
    assert finished.sanity is not None and not finished.sanity.hard_failure
