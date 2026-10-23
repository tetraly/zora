"""The beta 8 export's flag rules, on the spec's own Check strings where it gives them:

  - FL-DEP-01 rule 3 (ZORA's rule, owner-ruled deviation): Set Ganon HP to 0 (B41) and Maximum Boss
    Health (B46) both on is refused; a "?" beside the other is resolved so both never come out on.
  - FL-DEP-01 rule 4 is not applied (owner, 2026-10-22; docs/deviations.md): ZORA's B47 leaves the Book
    in the pool, so B47 on or "?" beside a Book pin anywhere is neither refused nor turned off.
  - FL-DEP-02 rule 2's coin: B18, B26 or B28 on under Dungeon Room Shuffle off (C14 = 0) turns C14 to
    1 or the three off, with equal chance; never a refusal.
  - VA-REJ-02: under C14 = 0 with only vanilla sets neither the remap nor the gate runs; with a
    shape-stage set they run. C14 = 3 resolves to 0, 1 and 2.
  - B02 at "?" (OW-CAVE-12) generates; Print Quest Info (B51) changes nothing in the ROM.
  - The spoiler log names each rule after the "?" resolution, like the coins."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.dependencies import (
    BOSS_HEALTH_RULE_TEXT,
    check_dependencies,
    meet_room_prerequisite,
    without_both_boss_health_rules,
)
from zora.flags.fields import DungeonRoomShuffle, PinnedItem, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import Built, FlagsRefused, build, finish, plan
from zora.generate.rng import Rng
from zora.rom.base_rom import remember_repo_base_rom
from zora_export.seed_document import BOSS_HEALTH_RULE, ROOM_RULE, setting_entries
from zora_export.spoiler_log import flag_breakdown

ON, OFF, POSSIBLE = ThreeState.ON, ThreeState.OFF, ThreeState.POSSIBLE
CP5 = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
BOOK = PinnedItem.BOOK_OF_MAGIC
# VA-REJ-02's Check strings: CP-5 with B18 and B28 off and C14 = 0, under C02 = 0 and C02 = 3, and C14 = 3
C14_OFF_FIRST_QUEST = "8hq4BeQou4cxYVgPqbtlBZYk41PJ07"
C14_OFF_SHAPES = "8hq4BeQou4cxYVgPqbtlBZYk41PJ0V"
C14_RANDOM_FIRST_QUEST = "8hq4BeQou4cxYVgPqbtlBZpVdm1J47"
# FL-DEP-02 rule 2's Check string: CP-5 with C02 = 0 and C14 = 0, B18 and B28 on
RULE_2 = "8hq4BeR1JXo89BJ2!TFpTOpsWJPJ07"
B02_POSSIBLE = "8hq4BeR1JXo89Bdr8RxgnuRoTXGJ3A"           # OW-CAVE-12's Check
B51_ON = "91250lSP91Je8HLkCpkeByG3GHUJ3A"                  # FL-SUP-04's Check


def rules(asked: dict[str, ThreeState], **options: int) -> list[str]:
    return [refusal.rule for refusal in check_dependencies(CP5.updated(options=options, toggles=asked))]


@cache
def built(flag_string: str, seed: int) -> Built:
    return build(plan(flag_string, seed), remember_repo_base_rom())


def test_rule_3_refuses_both_on_only() -> None:
    assert rules({"B41": ON, "B46": ON}) == ["FL-DEP-01 rule 3"]
    for b41, b46 in ((ON, POSSIBLE), (POSSIBLE, ON), (POSSIBLE, POSSIBLE), (ON, OFF), (OFF, ON)):
        assert "FL-DEP-01 rule 3" not in rules({"B41": b41, "B46": b46})
    assert BOSS_HEALTH_RULE_TEXT


def test_rule_3_resolves_so_both_never_come_out_on() -> None:
    def outcome(b41: ThreeState, b46: ThreeState, coins: tuple[ThreeState, ThreeState]) -> tuple[bool, bool]:
        asked = CP5.updated(toggles={"B41": b41, "B46": b46})
        drawn = asked.updated(toggles={field: coin for field, coin, given in zip(("B41", "B46"), coins, (b41, b46),
                                                                                strict=True) if given is POSSIBLE})
        resolved = without_both_boss_health_rules(asked, drawn)
        return resolved.is_on("B41"), resolved.is_on("B46")
    assert outcome(ON, POSSIBLE, (ON, ON)) == (True, False)            # B41 on turns a possible B46 off
    assert outcome(POSSIBLE, ON, (ON, ON)) == (False, True)            # B46 on turns a possible B41 off
    assert outcome(POSSIBLE, POSSIBLE, (ON, ON)) == (True, False)      # B41 first
    assert outcome(POSSIBLE, POSSIBLE, (OFF, ON)) == (False, True)     # B41 off: B46 keeps its coin


def test_rule_3_check_strings() -> None:
    """FL-DEP-01's Check: B41 and B46 both on refused; B41 on with B46 possible not, B46 off every seed."""
    with pytest.raises(FlagsRefused):
        plan("143oNtDD4Q0Jy2HDoYWPmABPEYHgNQOAUa4pJW", 1)
    assert "FL-DEP-01 rule 3" in rules({"B41": ON, "B46": ON})
    assert not check_dependencies(decode("143oNtDD4Q5Y!anNV3nfC7cdwQ4qhqCJJ04pJW"))


@pytest.mark.parametrize("pin", ["C11", "C12", "C13", "C26", "C27"])
def test_b47_beside_a_book_pin_is_kept(pin: str) -> None:
    """FL-DEP-01 rule 4 is not applied (docs/deviations.md): B47 on with any Book pin is no refusal,
    and a "?" B47 keeps its coin."""
    assert not rules({"B47": ON}, **{pin: BOOK})
    flag_string = encode(CP5.updated(options={pin: BOOK}, toggles={"B47": POSSIBLE}))
    assert {plan(flag_string, seed).settings.is_on("B47") for seed in range(20)} == {False, True}


def test_rule_2_coin_goes_both_ways_and_never_refuses() -> None:
    asked = decode(RULE_2)
    assert not check_dependencies(asked)
    outcomes = set()
    for seed in range(40):
        met = meet_room_prerequisite(asked, Rng(seed))
        turned_on = met.option("C14") == DungeonRoomShuffle.WITHIN_EACH_DUNGEON
        assert turned_on or not any(met.is_on(field) for field in ("B18", "B26", "B28"))
        outcomes.add(turned_on)
    assert outcomes == {True, False}


@needs_base_rom
@pytest.mark.parametrize("seed", (1, 2, 3))
def test_rule_2_strings_generate(seed: int) -> None:
    assert built(RULE_2, seed).world.levels


@needs_base_rom
@pytest.mark.parametrize("seed", (1, 2))
def test_c14_off_with_only_vanilla_sets_runs_no_gate(seed: int) -> None:
    result = built(C14_OFF_FIRST_QUEST, seed).result
    assert not result.gate_surveys and result.room_shuffle is None


@needs_base_rom
@pytest.mark.parametrize("seed", (1, 2))
def test_c14_off_with_a_shape_stage_set_runs_the_gate(seed: int) -> None:
    assert built(C14_OFF_SHAPES, seed).result.gate_surveys


def test_c14_random_resolves_to_each_value() -> None:
    assert {plan(C14_RANDOM_FIRST_QUEST, seed).settings.option("C14") for seed in range(30)} == {0, 1, 2}


@needs_base_rom
def test_b02_possible_generates() -> None:
    assert {plan(B02_POSSIBLE, seed).settings.is_on("B02") for seed in range(12)} == {True, False}
    assert built(B02_POSSIBLE, 1).world.levels


@needs_base_rom
def test_print_quest_info_changes_no_byte() -> None:
    base = remember_repo_base_rom()
    assert decode(B51_ON).toggle("B51") is ON
    without = encode(decode(B51_ON).updated(toggles={"B51": OFF}))
    assert finish(built(B51_ON, 1), base) == finish(built(without, 1), base)


def spoiler_line(flag_string: str, seed: int, field_id: str) -> str:
    entry = next(item for item in setting_entries(plan(flag_string, seed)) if item["id"] == field_id)
    return " ".join(flag_breakdown({"settings": [entry]})[4:]) if "final" in entry else ""


def test_the_spoiler_log_names_the_rules() -> None:
    both_random = encode(CP5.updated(toggles={"B41": POSSIBLE, "B46": POSSIBLE}))
    lines = [spoiler_line(both_random, seed, "B46") for seed in range(40)]
    assert any("? -> On -> Off (Ganon HP 0 rule)" in line for line in lines)
    assert not any(plan(both_random, seed).settings.is_on("B41") and plan(both_random, seed).settings.is_on("B46")
                   for seed in range(40))
    assert BOSS_HEALTH_RULE.startswith("Ganon HP 0 rule")
    found = [spoiler_line(RULE_2, seed, "C14") for seed in range(12)]
    assert any("(room shuffle coin)" in line for line in found) and ROOM_RULE.startswith("room shuffle coin")
