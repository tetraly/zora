"""Sword heart ranges at every value (C20 to C23; flags-behavior.md FL-ALT-05): the white sword's
range 4 + C20 to 6 - C21, the magical sword's 10 + C22 to 14 - C23, swapped when the lowest is
above the highest (FL-DEP-03); one draw each, also for a one-count range; only under B10 (with it
off the caves keep PRG0's 5 and 12). The tournament sets' values: Muffle Rug's white 5 and magical
12, Pick 5's white 5 and magical 10."""
from functools import cache
from itertools import product

import pytest

from tests.needs import needs_base_rom
from zora.flags import codec
from zora.flags.dependencies import magical_sword_hearts, white_sword_hearts
from zora.flags.fields import ThreeState
from zora.flags.form import metadata
from zora.flags.support import Support, support
from zora.flags.zora_flags import (
    HEARTS_CAP_CHOICES,
    SWORD_HEARTS_CAP_CONFLICT_FIELDS,
    ZoraFlags,
    magical_sword_heart_range,
    validate,
)
from zora.flags.zora_form import zora_state
from zora.generate.pipeline import Built, FlagsRefused, build, plan
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.steps.change_sword_hearts import change_sword_hearts
from zora.model.enums import Destination
from zora.model.overworld import ItemCave, Overworld
from zora.rom.base_rom import remember_repo_base_rom

DEFAULT_SETTINGS = codec.decode(metadata()["defaultFlags"])      # CP-5
VANILLA_WHITE, VANILLA_MAGICAL = 5, 12
SEEDS = range(1, 7)


@pytest.mark.parametrize(("field_id", "count"), [("C20", 3), ("C21", 3), ("C22", 5), ("C23", 5)])
def test_every_value_is_supported(field_id: str, count: int) -> None:
    for index in range(count):
        assert support(DEFAULT_SETTINGS.updated(options={field_id: index}))[field_id] is Support.SUPPORTED


@pytest.mark.parametrize(("options", "white", "magical"), [
    ({}, (4, 6), (10, 14)),
    ({"C20": 1, "C21": 1}, (5, 5), (10, 14)),           # both tournament sets' white sword
    ({"C20": 2, "C21": 2}, (4, 6), (10, 14)),           # 6 to 4, swapped
    ({"C21": 2}, (4, 4), (10, 14)),
    ({"C22": 2, "C23": 2}, (4, 6), (12, 12)),           # Muffle Rug's magical sword
    ({"C22": 0, "C23": 4}, (4, 6), (10, 10)),           # Pick 5's
    ({"C22": 2, "C23": 4}, (4, 6), (10, 12)),           # 12 to 10, swapped
    ({"C22": 4}, (4, 6), (14, 14)),
])
def test_the_ranges(options: dict[str, int], white: tuple[int, int], magical: tuple[int, int]) -> None:
    settings = DEFAULT_SETTINGS.updated(options=options)
    assert (white_sword_hearts(settings), magical_sword_hearts(settings)) == (white, magical)


class _Cave:
    def __init__(self) -> None:
        self.heart_requirement = 0


class _Overworld:
    """The two sword caves, all change_sword_hearts reads."""
    def __init__(self) -> None:
        self.caves = {Destination.WHITE_SWORD_CAVE: _Cave(), Destination.MAGICAL_SWORD_CAVE: _Cave()}

    def get_cave(self, destination: Destination, _kind: type[ItemCave]) -> _Cave:
        return self.caves[destination]


def test_a_one_count_range_still_takes_its_draw() -> None:
    """FL-ALT-05: one draw each whatever the range, so the stream after the pass is the same."""
    overworld = _Overworld()
    rng = ScriptedRng([0, 0])
    change_sword_hearts(overworld, rng, magical_sword_hearts=range(12, 13),  # type: ignore[arg-type]
                        white_sword_hearts=range(5, 6))
    with pytest.raises(IndexError):                    # both draws were taken
        rng.below(1)
    assert overworld.caves[Destination.WHITE_SWORD_CAVE].heart_requirement == 5
    assert overworld.caves[Destination.MAGICAL_SWORD_CAVE].heart_requirement == 12


def test_draws_spread_over_a_range() -> None:
    """h = lo + (n mod (hi - lo + 1)): each count of the range is reachable."""
    seen = set()
    for draw in range(3):
        overworld = _Overworld()
        change_sword_hearts(overworld, ScriptedRng([draw, 0]), white_sword_hearts=range(4, 7))  # type: ignore[arg-type]
        seen.add(overworld.caves[Destination.WHITE_SWORD_CAVE].heart_requirement)
    assert seen == {4, 5, 6}


@cache
def _built(options: tuple[tuple[str, int], ...], seed: int, toggles: tuple[tuple[str, int], ...] = ()) -> Built:
    settings = DEFAULT_SETTINGS.updated(options=dict(options), toggles=dict(toggles))
    return build(plan(codec.encode(settings), seed), remember_repo_base_rom())


def _hearts(built: Built) -> tuple[int, int]:
    overworld: Overworld = built.world.overworld
    white = overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    magical = overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    assert white is not None and magical is not None
    return white.heart_requirement, magical.heart_requirement


@needs_base_rom
@pytest.mark.parametrize(("options", "expected"), [
    ((("C20", 1), ("C21", 1), ("C22", 2), ("C23", 2)), {(5, 12)}),       # Muffle Rug's
    ((("C20", 1), ("C21", 1), ("C22", 0), ("C23", 4)), {(5, 10)}),       # Pick 5's
])
def test_tournament_values_in_seeds(options: tuple[tuple[str, int], ...], expected: set[tuple[int, int]]) -> None:
    assert {_hearts(_built(options, seed)) for seed in SEEDS} == expected


@needs_base_rom
def test_a_swapped_range_in_seeds() -> None:
    """C22 = 2 with C23 = 4: the magical sword asks for 10 to 12."""
    assert {_hearts(_built((("C22", 2), ("C23", 4)), seed))[1] for seed in SEEDS} <= {10, 11, 12}


@needs_base_rom
def test_only_under_b10() -> None:
    """FL-OFF-03: with B10 off the pass does not run, and the caves keep PRG0's counts."""
    options = (("C20", 2), ("C21", 0), ("C22", 4), ("C23", 0))
    assert {_hearts(_built(options, seed, (("B10", 0),))) for seed in SEEDS} == {(VANILLA_WHITE, VANILLA_MAGICAL)}


# --- the ZORA cap below the lowest (the 2026-10-18 Archipelago scan) ------------------------

CAPS = (None, *HEARTS_CAP_CHOICES)
# Magical Sword Hearts (min) 14 under Change Sword Hearts: Random, the ZORA cap at 13: the "?" was
# judged off (PRG0's 12, under the cap) and drew on, so the range was 14 to 13: "ValueError: n
# must be positive, got 0" in change_sword_hearts
SCAN_FLAGS, SCAN_ZORA_FLAGS, SCAN_SEED = "3yREHlULU8TlU2cmGGogQgYwAlburMwdf2nJ36Do", "5.4KZ737", 1


@pytest.mark.parametrize("redraw", list(ThreeState))
def test_no_sword_heart_combination_reaches_an_empty_range(redraw: ThreeState) -> None:
    """Every sword-heart value (C20 to C23), every ZORA cap, Randomize Magical Sword either way:
    the strings are refused, or under each way Change Sword Hearts' "?" resolves both caves'
    ranges hold a count and change_sword_hearts draws from them."""
    for white_low, white_high, magical_low, magical_high in product(range(3), range(3), range(5), range(5)):
        z1r = DEFAULT_SETTINGS.updated(options={"C20": white_low, "C21": white_high, "C22": magical_low,
                                                "C23": magical_high}, toggles={"B10": redraw})
        for cap, randomized in product(CAPS, (False, True)):
            flags = ZoraFlags(randomize_magical_sword=randomized, magical_sword_hearts_highest=cap)
            if validate(flags, z1r):
                continue
            outcomes = (ThreeState.OFF, ThreeState.ON) if redraw is ThreeState.POSSIBLE else (redraw,)
            for outcome in outcomes:
                resolved = z1r.updated(toggles={"B10": outcome})
                white, magical = white_sword_hearts(resolved), magical_sword_heart_range(flags, resolved)
                assert magical, (white_low, white_high, magical_low, magical_high, cap, randomized, outcome)
                change_sword_hearts(_Overworld(), Rng(0), magical_sword_hearts=magical,  # type: ignore[arg-type]
                                    white_sword_hearts=range(white[0], white[1] + 1))


def test_a_cap_below_the_lowest_is_refused_under_a_random_change_sword_hearts() -> None:
    """The scan's strings are refused before generation, with the cap named, not crashed on."""
    with pytest.raises(FlagsRefused, match="Magical-sword hearts, highest: the cap of 13 hearts is below the 14"):
        plan(SCAN_FLAGS, SCAN_SEED, SCAN_ZORA_FLAGS)


def test_the_page_shows_the_cap_conflict_in_red_at_its_settings() -> None:
    state = zora_state(SCAN_ZORA_FLAGS, codec.decode(SCAN_FLAGS))
    assert [conflict["fields"] for conflict in state["conflicts"]] == [list(SWORD_HEARTS_CAP_CONFLICT_FIELDS)]
    assert set(SWORD_HEARTS_CAP_CONFLICT_FIELDS) == {"magical_sword_hearts_highest", "B10", "C22", "C23"}
