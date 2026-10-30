"""The beta 9 export's possible values (flags-behavior.md FL-SUP-01, FL-DEP-02, FL-DEP-04), on the spec's
own Check strings:

  - Shuffle Take Any Road Caves (B04) at Random: a coin, then FL-DEP-02 rule 1 with OW-CAVE-10's coin
    (OW-CAVE-12); Shuffle Hungry Goriya and Shuffle Bomb Upgraders (B28, B29) at Random: coins first,
    then rule 4 (C02 = 1, 2, 4 turn both off), before rules 1 to 3, so a B28 rule 4 turned off does
    not meet rule 2.
  - Add Money or Life Rooms and Change Leave Your Rooms (B22, B23) at Random: each its own coin since
    the 2026-10-28 export (L113: ZORA's old rule is gone), so all four pairs come out, B22 on with B23
    off included (PS-MERCH-05).
  - Encode level data (B82, the spec's tournament mode) at Random reads as off (FP-TOURNEY-01; owner
    ruling: the page does not offer it)."""
from collections import Counter

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.dependencies import needs_room_prerequisite
from zora.flags.fields import DungeonLayoutSource, DungeonRoomShuffle, ThreeState
from zora.flags.support import is_fully_supported
from zora.generate.pipeline import build, finish, plan, resolve_question_marks
from zora.rom.base_rom import remember_repo_base_rom

B28_B29_POSSIBLE, B28_B29_POSSIBLE_SECOND_QUEST = "8hq4BeRs!KuZ63ioqOs3v61ejrUJ3A", "8hq4BeRs!KuZ63ioqOs3v61ejrUJ2v"
B04_POSSIBLE = "8hq4BeR1JXo89EHDHHWaOtyr5gUJ3A"
B22_B23_POSSIBLE, B22_ON_B23_POSSIBLE, B22_POSSIBLE_B23_OFF = (
    "8hq4BeR1OB37wB23fii!Yd3rarUJ3A", "8hq4BeR1N0!7zgbokubi1pIevQUJ3A", "8hq4BeR1HDg8GBRY9r1EQnTeYHUJ3A")
B82_POSSIBLE = "1bbCZpJp2JDVKrgOlla4xo!jj9C1JWRZx!UJ3A"
SEEDS = range(1, 81)
BOMB_SELLER_PATCH, BOMB_SELLER_NOPS = 0x04AED, b"\xea\xea"     # PS-BOMB-03


def resolved_pairs(flag_string: str, first: str, second: str) -> Counter[tuple[bool, bool]]:
    return Counter((plan(flag_string, seed).settings.is_on(first), plan(flag_string, seed).settings.is_on(second))
                   for seed in SEEDS)


@pytest.mark.parametrize("flag_string", [B28_B29_POSSIBLE, B04_POSSIBLE, B22_B23_POSSIBLE, B22_ON_B23_POSSIBLE,
                                         B22_POSSIBLE_B23_OFF, B82_POSSIBLE])
def test_the_checks_strings_are_produced(flag_string: str) -> None:
    assert plan(flag_string, 1)


def test_b28_and_b29_at_random_resolve_both_ways() -> None:
    assert set(resolved_pairs(B28_B29_POSSIBLE, "B28", "B29")) == {(False, False), (False, True), (True, False),
                                                                    (True, True)}


def test_rule_4_turns_both_off_under_second_quest_dungeons_whatever_the_coins() -> None:
    assert set(resolved_pairs(B28_B29_POSSIBLE_SECOND_QUEST, "B28", "B29")) == {(False, False)}


def test_rule_4_comes_before_rule_2() -> None:
    """A B28 come up on that rule 4 turns off does not meet rule 2: with second-quest dungeons and the
    room shuffle off, B28's coin never brings rule 2's coin in, so the room shuffle stays off."""
    asked = decode(B28_B29_POSSIBLE_SECOND_QUEST).updated(
        options={"C14": DungeonRoomShuffle.VANILLA}, toggles={"B18": ThreeState.OFF, "B26": ThreeState.OFF})
    flag_string = encode(asked)
    assert asked.option("C02") == DungeonLayoutSource.SECOND_QUEST
    for seed in range(1, 41):
        assert not needs_room_prerequisite(resolve_question_marks(asked, seed, flag_string))
        assert plan(flag_string, seed).settings.option("C14") == DungeonRoomShuffle.VANILLA


@needs_base_rom
def test_b29_at_random_patches_the_seller_exactly_when_it_comes_up_on() -> None:
    base = remember_repo_base_rom()
    for seed in range(1, 9):
        chosen = plan(B28_B29_POSSIBLE, seed)
        rom = finish(build(chosen, base), base)
        assert (rom[BOMB_SELLER_PATCH:BOMB_SELLER_PATCH + 2] == BOMB_SELLER_NOPS) is chosen.settings.is_on("B29")


def test_b04_at_random_resolves_both_ways() -> None:
    assert {plan(B04_POSSIBLE, seed).settings.is_on("B04") for seed in SEEDS} == {False, True}


def test_b22_and_b23_at_random_are_plain_coins() -> None:
    """FL-DEP-04 (L113): no rule between them, so every pair comes out, and each field as given stays."""
    assert set(resolved_pairs(B22_B23_POSSIBLE, "B22", "B23")) == {(True, True), (True, False), (False, True),
                                                                    (False, False)}
    assert set(resolved_pairs(B22_ON_B23_POSSIBLE, "B22", "B23")) == {(True, True), (True, False)}
    assert set(resolved_pairs(B22_POSSIBLE_B23_OFF, "B22", "B23")) == {(True, False), (False, False)}


def test_b23_off_beside_b22_on_is_supported() -> None:
    """FL-DEP-06 and PS-MERCH-05 (L111): B22 on with B23 off, given as such."""
    asked = decode(B22_ON_B23_POSSIBLE)
    assert is_fully_supported(asked.updated(toggles={"B23": ThreeState.OFF}))
    assert is_fully_supported(asked.updated(toggles={"B22": ThreeState.POSSIBLE, "B23": ThreeState.OFF}))


@needs_base_rom
def test_b82_at_random_is_made_as_off() -> None:
    off = encode(decode(B82_POSSIBLE).updated(toggles={"B82": ThreeState.OFF}))
    base = remember_repo_base_rom()
    for seed in (1, 2):
        assert finish(build(plan(B82_POSSIBLE, seed), base), base) == finish(build(plan(off, seed), base), base)
