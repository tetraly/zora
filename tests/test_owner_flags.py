"""The owner's 2.0 flags (docs/design/zora-flags-2.0.md; owner decisions 2026-10-07): the ZORA
flag string's version 3, each flag On / Off / ?, the "?" stream and the dependencies."""
import pytest

from zora.flags import zora_flags
from zora.flags.codec import decode as decode_z1r
from zora.flags.codec import encode as encode_z1r
from zora.flags.fields import Settings, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import OWNER_2_0_FIELDS, ZoraFlags, canonicalize, decode, encode
from zora.generate.pipeline import FlagsRefused, plan

ON, OFF, MAYBE = ThreeState.ON, ThreeState.OFF, ThreeState.POSSIBLE
WITHOUT_EXTRA_CANDLES = encode_z1r(decode_z1r(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B09": OFF}))
B04_OFF = encode_z1r(decode_z1r(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B04": OFF}))
B04_MAYBE = encode_z1r(decode_z1r(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B04": MAYBE}))


def flags(**values: ThreeState | bool) -> ZoraFlags:
    return ZoraFlags(**values)  # type: ignore[arg-type]


# --- the string -------------------------------------------------------------------------------

def test_version_3_holds_thirteen_three_state_fields() -> None:
    """Thirteen slots; Auto Show Letter's is retired (always on since 2026-10-17), twelve are flags."""
    assert len(zora_flags.OWNER_2_0_SLOTS) == 13 and len(OWNER_2_0_FIELDS) == 12
    assert set(zora_flags.OWNER_2_0_SLOTS) - set(OWNER_2_0_FIELDS) == zora_flags.RETIRED_FIELDS == {"auto_show_letter"}
    assert all(field.version == 3 for field in zora_flags.FIELDS if field.name in OWNER_2_0_FIELDS)
    for name in OWNER_2_0_FIELDS:
        for value in (ON, MAYBE):
            one = flags(**{name: value})
            assert encode(one).startswith("3.") and decode(encode(one)) == one


@pytest.mark.parametrize("old", ["", "1.1", "1.2", "1.D", "1.N", "2.O", "2.m", "2.19", "2.b"])
def test_every_older_string_keeps_its_meaning_and_spelling(old: str) -> None:
    assert canonicalize(old) == old
    assert all(getattr(decode(old), name) is OFF for name in OWNER_2_0_FIELDS)


def test_a_version_3_string_with_its_new_fields_off_is_spelled_as_before() -> None:
    assert canonicalize("3.D") == "1.D" and canonicalize("3.O") == "2.O"


@pytest.mark.parametrize("retired", [ON, MAYBE])
def test_a_string_with_auto_show_letter_still_decodes(retired: ThreeState) -> None:
    """A string from before Auto Show Letter was retired, with it On or "?": its digit is dropped,
    every other field keeps its value, and it is spelled as the string without it."""
    slot = zora_flags.FIELDS.index(next(field for field in zora_flags.FIELDS if field.name == "auto_show_letter"))
    below = 1
    for field in zora_flags.FIELDS[:slot]:
        below *= field.slots
    with_progressive = encode(flags(progressive_items=True, four_potion_inventory=ON))
    number = zora_flags._parse_payload(with_progressive.split(".")[1]) + int(retired) * below
    old = f"3.{zora_flags._format_payload(number)}"
    assert old != with_progressive
    assert decode(old) == decode(with_progressive) and canonicalize(old) == with_progressive


# --- the "?" stream ---------------------------------------------------------------------------

def test_question_marks_come_from_their_own_stream_and_never_change_by_themselves() -> None:
    asked = flags(**dict.fromkeys(OWNER_2_0_FIELDS, MAYBE))
    canonical = encode(asked)
    one = zora_flags.resolve_question_marks(asked, 7, "z1r", canonical)
    assert one.is_resolved and one == zora_flags.resolve_question_marks(asked, 7, "z1r", canonical)
    outcomes = {zora_flags.resolve_question_marks(asked, seed, "z1r", canonical) for seed in range(40)}
    assert len(outcomes) > 30                       # 2^13 outcomes, drawn per seed
    for name in OWNER_2_0_FIELDS:                   # every field comes up both ways
        assert {getattr(outcome, name) for outcome in outcomes} == {ON, OFF}


def test_a_version_3_question_mark_leaves_the_z1r_draws_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Z1R "?" values (FL-DEP-04's stream) resolve the same with any ZORA string."""
    monkeypatch.setattr(zora_flags, "PRODUCED_OWNER_FIELDS", frozenset(OWNER_2_0_FIELDS))
    z1r = encode_z1r(decode_z1r(WITHOUT_EXTRA_CANDLES).updated(toggles={"B27": MAYBE, "B31": MAYBE}))
    for seed in range(10):
        plain = plan(z1r, seed, "2.O").settings
        with_maybe = plan(z1r, seed, encode(flags(progressive_items=True, four_potion_inventory=MAYBE)))
        assert all(plain.toggle(field) == with_maybe.settings.toggle(field) for field in ("B27", "B31"))


# --- the dependencies -------------------------------------------------------------------------

def test_add_l4_sword_on_without_progressive_items_is_refused() -> None:
    assert zora_flags.conflicts(flags(add_l4_sword=ON), decode_z1r(WITHOUT_EXTRA_CANDLES)) == [
        (zora_flags.L4_SWORD_CONFLICT, zora_flags.L4_SWORD_CONFLICT_FIELDS)]
    with pytest.raises(FlagsRefused, match="Add L4 Sword needs Progressive Items"):
        plan(WITHOUT_EXTRA_CANDLES, 1, encode(flags(add_l4_sword=ON)))


def test_add_l4_sword_question_mark_without_progressive_items_resolves_off() -> None:
    """A released string's "?" keeps beta 1's meaning (owner ruling, 2026-10-08)."""
    asked = flags(add_l4_sword=MAYBE)
    z1r = decode_z1r(WITHOUT_EXTRA_CANDLES)
    assert zora_flags.conflicts(asked, z1r) == []
    for seed in range(20):
        resolved = zora_flags.resolve_question_marks(asked, seed, "z", encode(asked))
        zora, _ = zora_flags.resolve_owner_dependencies(resolved, asked, z1r, z1r)
        assert zora.add_l4_sword is OFF


def test_add_l4_sword_question_mark_with_asnb_is_refused() -> None:
    """The "?" means Off or Level 9 only: with the Level 2 field or the level-4-sword entrance it
    is refused (docs/design/asnb.md section 1: neither has a random option)."""
    z1r = decode_z1r(WITHOUT_EXTRA_CANDLES)
    for asnb in ({"l4_sword_in_level_2": True}, {"level_9_entrance_sword": True},
                 {"l4_sword_in_level_2": True, "level_9_entrance_sword": True}):
        asked = flags(add_l4_sword=MAYBE, progressive_items=True, **asnb)
        assert zora_flags.validate(asked, z1r) == [zora_flags.L4_SWORD_RANDOM_WITH_ASNB], asnb


def test_bracelet_blocks_on_with_b04_on_is_refused() -> None:
    asked = flags(extra_power_bracelet_blocks=ON)
    found = zora_flags.conflicts(asked, decode_z1r(MVP_BASELINE_LEVEL_ENCODING_OFF))
    assert found == [(zora_flags.BRACELET_BLOCKS_CONFLICT, zora_flags.BRACELET_BLOCKS_CONFLICT_FIELDS)]
    assert zora_flags.conflicts(asked, decode_z1r(B04_OFF)) == []
    assert zora_flags.conflicts(asked, decode_z1r(B04_MAYBE)) == []


def test_a_question_mark_that_comes_up_into_the_bracelet_conflict_resolves_off() -> None:
    on_z1r = decode_z1r(MVP_BASELINE_LEVEL_ENCODING_OFF)
    asked = flags(extra_power_bracelet_blocks=MAYBE)
    zora, z1r = zora_flags.resolve_owner_dependencies(flags(extra_power_bracelet_blocks=ON), asked, on_z1r, on_z1r)
    assert zora.extra_power_bracelet_blocks is OFF and z1r.is_on("B04")
    # Bracelet Blocks set on, B04 "?" that comes up on: B04 is the "?" side, so it is off.
    asked = flags(extra_power_bracelet_blocks=ON)
    zora, z1r = zora_flags.resolve_owner_dependencies(asked, asked, on_z1r, decode_z1r(B04_MAYBE))
    assert zora.extra_power_bracelet_blocks is ON and not z1r.is_on("B04")


# Extra Raft Blocks with the raft kept in level 3 behind its own raft-blocked entrance ($34 on a 2nd
# Quest overworld): 2nd Quest overworld, shapes dungeons, Cave Shuffle Vanilla, Item Shuffle None
RAFT_TRAP = decode_z1r(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C01": 1, "C02": 3, "C05": 0, "C06": 0})
RAFT_ESCAPES = {"C01": (0, 2), "C02": (1, 2), "C05": (1, 3), "C06": (1, 2, 3)}
RAFT_RANDOMS = {"C01": 4, "C02": 6, "C05": 4, "C06": 4}
# The strings that failed after 2,000 attempts (seed 538939, 2026-10-22): Overworld Quest Mixed Quest - 2nd,
# Dungeon Quest Shapes, Cave Shuffle Random, Item Shuffle None, Extra Raft Blocks on
FAILED_Z1R, FAILED_ZORA, FAILED_SEED = "oIbnPfPjhr9ior71M7ubQtD3qIhQae3oL5ptQ", "3.6Mho4", 538939


def raft_conflicts(z1r: Settings, raft: ThreeState = ON) -> list[tuple[str, tuple[str, ...]]]:
    return [found for found in zora_flags.conflicts(flags(extra_raft_blocks=raft), z1r)
            if found[0] == zora_flags.RAFT_BLOCKS_CONFLICT]


def test_raft_blocks_with_the_raft_behind_its_own_block_are_refused() -> None:
    assert raft_conflicts(RAFT_TRAP) == [(zora_flags.RAFT_BLOCKS_CONFLICT, zora_flags.RAFT_BLOCKS_CONFLICT_FIELDS)]
    assert raft_conflicts(RAFT_TRAP, MAYBE) == []
    for field, values in RAFT_ESCAPES.items():
        for value in values:
            assert raft_conflicts(RAFT_TRAP.updated(options={field: value})) == [], (field, value)
    for field, value in RAFT_RANDOMS.items():
        assert raft_conflicts(RAFT_TRAP.updated(options={field: value})) != [], field
    with pytest.raises(FlagsRefused, match="Extra Raft Blocks cannot be used"):
        plan(FAILED_Z1R, FAILED_SEED, FAILED_ZORA)


def test_a_question_mark_that_comes_up_into_the_raft_trap_resolves_off() -> None:
    asked = flags(extra_raft_blocks=MAYBE)
    zora, _ = zora_flags.resolve_owner_dependencies(flags(extra_raft_blocks=ON), asked, RAFT_TRAP, RAFT_TRAP)
    assert zora.extra_raft_blocks is OFF
    free = RAFT_TRAP.updated(options={"C05": 1})
    zora, _ = zora_flags.resolve_owner_dependencies(flags(extra_raft_blocks=ON), asked, free, free)
    assert zora.extra_raft_blocks is ON


def test_b04_off_is_supported() -> None:
    assert plan(B04_OFF, 1).settings.toggle("B04") is OFF
    assert {plan(B04_MAYBE, seed).settings.toggle("B04") for seed in range(12)} == {ON, OFF}


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_with_b04_off_the_take_any_road_caves_keep_their_prg0_screens(seed: int) -> None:
    from zora.generate.pipeline import generate_rom
    from zora.model.enums import Destination
    from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
    from zora.rom.parse.rom_file import load_rom, parse_rom
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    base = load_rom(verify_base_rom())
    prg0 = parse_rom(base).overworld
    world = parse_rom(generate_rom(B04_OFF, seed, base).rom).overworld
    any_road = [s for s in range(128) if prg0.screens[s].destination == Destination.ANY_ROAD]
    assert any_road == [s for s in range(128) if world.screens[s].destination == Destination.ANY_ROAD]
    assert len(any_road) == 4
