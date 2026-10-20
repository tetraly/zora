"""The randomized mazes' hints in the logic (owner request, 2026-10-13): a maze's path is known
only once a door of the hint shop that sells it is reached, and with Book to Understand NPCs
(B48, HT-BOOK-01) only with the book as well, since without it every person, the hint shops'
too, shows text 0. The screens past a maze need its path; a hint shop is never behind its own
maze."""
from dataclasses import replace
from functools import cache
from itertools import combinations

import pytest

from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.generate.acceptance_check import AcceptanceCheck, logic_rules
from zora.generate.logic import EventTerm, ItemTerm, LogicModel, Rule, logic_model, triforce_event
from zora.generate.pipeline import Built, build, extra_options, plan
from zora.generate.steps import overworld_gates as gates
from zora.model.enums import Item
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

WITH_BOOK = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B48": ThreeState.ON}))
MAZES = zora_flags.encode(ZoraFlags(randomize_lost_hills=ThreeState.ON, randomize_dead_woods=ThreeState.ON))
FLAGS = {"mazes": MVP_BASELINE_LEVEL_ENCODING_OFF, "mazes and B48": WITH_BOOK}
SEEDS = range(1, 5)
TRIFORCE_LEVELS = range(1, 9)
HINTS = {"Lost Hills Hint": (gates.LOST_HILLS_HINT_SHOP, gates.LOST_HILLS_GATED),
         "Dead Woods Hint": (gates.DEAD_WOODS_HINT_SHOP, gates.DEAD_WOODS_GATED)}


@cache
def built(case: str, seed: int) -> Built:
    return build(plan(FLAGS[case], seed, MAZES), remember_repo_base_rom())


@cache
def model(case: str, seed: int) -> LogicModel:
    return logic_model(built(case, seed))


def requires(rule: Rule, term: object) -> bool:
    """Every clause of the rule has the term."""
    return bool(rule) and all(term in clause for clause in rule)


def checker(case: str, seed: int) -> AcceptanceCheck:
    world = built(case, seed)
    assert world.result.item_shuffle_result is not None and world.result.overworld is not None
    return AcceptanceCheck(world.world.levels, world.result.item_shuffle_result, world.world.overworld,
                           world.result.overworld, extra_options(world.plan).logic_rules)


def test_the_rules_need_the_book_only_with_b48_and_a_maze() -> None:
    both = gates.OverworldGates(lost_hills=True, dead_woods=True)
    assert logic_rules(False, False, both, maze_hints_need_book=True).maze_hints_need_book
    assert not logic_rules(False, False, both).maze_hints_need_book
    assert not logic_rules(False, False, maze_hints_need_book=True).maze_hints_need_book
    assert extra_options(plan(WITH_BOOK, 1, MAZES)).logic_rules.maze_hints_need_book
    assert not extra_options(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, MAZES)).logic_rules.maze_hints_need_book


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAGS))
def test_the_closure_knows_a_path_from_its_shop_and_with_b48_the_book(case: str, seed: int) -> None:
    """For every held set over the screen needs and the book: the path is known exactly when a
    door of its hint shop is reached, and with B48 the book is held."""
    check = checker(case, seed)
    needs = sorted({need for _, need in check.rules.screen_needs} | {Item.BOOK})
    book_needed = case == "mazes and B48"
    for size in range(len(needs) + 1):
        for chosen in combinations(needs, size):
            held = frozenset({Item.WOOD_SWORD, *chosen})
            for _, hint_shop in check.rules.maze_hints:
                expected = check.shop_door_reached(hint_shop, held) and (Item.BOOK in held or not book_needed)
                assert check.knows_maze_path(hint_shop, held) == expected, (hint_shop, sorted(held))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAGS))
def test_the_logic_model_hint_events(case: str, seed: int) -> None:
    """Archipelago's rules: each hint event needs the book exactly with B48."""
    logic = model(case, seed)
    for hint in HINTS:
        assert requires(logic.events[hint], ItemTerm(Item.BOOK)) == (case == "mazes and B48"), hint


def test_every_place_and_level_past_a_maze_needs_its_hint() -> None:
    """Archipelago's rules: a cave place past a maze, and a level whose entrance is past one,
    need the maze's hint (with B48, therefore the book too)."""
    seen = 0
    for case in FLAGS:
        for seed in range(1, 13):
            logic, world = model(case, seed), built(case, seed)
            assert world.result.overworld is not None
            for hint, (_, gated) in HINTS.items():
                rules = [logic.places[place.name] for place in world.places
                         if place.screens and set(place.screens) <= gated]
                rules += [logic.events[triforce_event(level)] for level in TRIFORCE_LEVELS
                          if world.result.overworld.entry_door(level) in gated]
                seen += len(rules)
                assert all(requires(rule, EventTerm(hint)) for rule in rules), (case, seed, hint)
    assert seen, "nothing past a maze in these seeds"


@pytest.mark.parametrize("case", list(FLAGS))
def test_a_hint_shop_is_never_behind_its_own_maze(case: str) -> None:
    for seed in range(1, 13):
        overworld = built(case, seed).world.overworld
        for hint_shop, gated in HINTS.values():
            doors = {screen.screen_num for screen in overworld.screens if screen.destination == hint_shop}
            assert doors and not doors & gated, (seed, hint_shop, sorted(doors))


@pytest.mark.parametrize("seed", SEEDS)
def test_with_b48_the_book_comes_before_any_maze_screen(seed: int) -> None:
    """The closure's held set without the book never holds a maze's hint, so nothing past a maze
    is counted before the book."""
    check = checker("mazes and B48", seed)
    held, _ = check.closure()
    assert Item.BOOK in held
    for hint, _shop in check.rules.maze_hints:
        assert hint in held
    everything_else = frozenset(held - {Item.BOOK, gates.LOST_HILLS_HINT, gates.DEAD_WOODS_HINT})
    assert not any(check.knows_maze_path(shop, everything_else) for _, shop in check.rules.maze_hints)


def test_a_starting_book_needs_no_finding() -> None:
    """Start Book (B67) is not produced yet; when the book is a kept start item (after Max Start
    Items, C17), the maze hints do not need it found (flags/support.py's TODO)."""
    chosen = plan(WITH_BOOK, 1, MAZES)
    starting = replace(chosen, alternatives=replace(chosen.alternatives, start_items=(Item.BOOK,)))
    assert extra_options(chosen).logic_rules.maze_hints_need_book
    assert not extra_options(starting).logic_rules.maze_hints_need_book
