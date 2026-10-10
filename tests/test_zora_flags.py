"""The ZORA flag string (zora/flags/zora_flags.py): codec, canonical form,
validation against the Z1R settings, seed derivation and the level-encoding
key text. Nothing here is wired into generation yet (docs/zora-extras.md)."""
from itertools import product

import pytest

from zora.flags import zora_flags
from zora.flags.codec import FlagStringError, decode as decode_z1r
from zora.flags.fields import (
    MAGICAL_SWORD_HIGHEST, MAGICAL_SWORD_LOWEST, STARTING_HEARTS, STARTING_HEARTS_RANDOM, ThreeState,
)
from zora.flags.presets import MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import (
    DEFAULT, HEARTS_CAP_CHOICES, REDRAW_SWORD_HEARTS, ZoraFlags, ZoraFlagStringError, canonicalize, decode,
    encode, generation_seed, level_encoding_text, magical_sword_heart_range, starting_heart_containers, validate,
)

BASELINE = decode_z1r(MVP_BASELINE)


def every_flag_set() -> list[ZoraFlags]:
    caps: list[int | None] = [None, *HEARTS_CAP_CHOICES]
    return [ZoraFlags(sword, letter, cap, progressive, shop)
            for sword, letter, cap, progressive, shop in product((False, True), (False, True), caps,
                                                                 (False, True), (False, True))]


def version_1_flag_sets() -> list[ZoraFlags]:
    return [flags for flags in every_flag_set() if not (flags.progressive_items or flags.shop_items_in_pool)]


# --- codec -------------------------------------------------------------------

def test_the_empty_string_is_every_default() -> None:
    assert decode("") == DEFAULT
    assert encode(DEFAULT) == ""
    assert DEFAULT.is_default


def test_every_flag_set_round_trips() -> None:
    strings = set()
    for flags in every_flag_set():
        string = encode(flags)
        assert decode(string) == flags
        assert canonicalize(string) == string
        strings.add(string)
    assert len(strings) == len(every_flag_set())


def test_a_string_is_version_dot_payload() -> None:
    assert encode(ZoraFlags(randomize_magical_sword=True)) == "1.1"
    assert encode(ZoraFlags(randomize_letter=True)) == "1.2"
    assert encode(ZoraFlags(randomize_magical_sword=True, magical_sword_hearts_highest=12)) == "1.D"


def test_version_2_holds_the_progressive_items_fields() -> None:
    """PI-FLAG-01: two booleans appended with version 2, progressive_items first."""
    assert zora_flags.CURRENT_VERSION >= 2
    assert encode(ZoraFlags(progressive_items=True)) == "2.O"
    assert encode(ZoraFlags(shop_items_in_pool=True)) == "2.m"
    assert encode(ZoraFlags(progressive_items=True, shop_items_in_pool=True)) == "2.19"
    assert encode(ZoraFlags(randomize_magical_sword=True, magical_sword_hearts_highest=12,
                            progressive_items=True)) == "2.b"
    # A version-2 string with the new fields off is spelled as version 1.
    assert canonicalize("2.D") == "1.D" and canonicalize("2.0") == ""


def test_every_version_1_string_keeps_its_meaning() -> None:
    """Every version-1 flag set keeps its version-1 string, and that string decodes to it with
    both new fields off."""
    for flags in version_1_flag_sets():
        string = encode(flags)
        assert string == "" or string.startswith("1.")
        assert decode(string) == flags and not decode(string).progressive_items


def test_canonical_form_drops_leading_zeros_and_all_default_payloads() -> None:
    assert canonicalize("1.0D") == "1.D"
    assert canonicalize("1.0") == ""


@pytest.mark.parametrize("string", ["D", "1D", "0.1", "01.1", "1.", ".1", "5.1", "1.?", "1.1 ", "1.O"])
def test_malformed_strings_are_refused(string: str) -> None:
    with pytest.raises(ZoraFlagStringError):
        decode(string)


def test_a_payload_beyond_the_version_fields_is_refused() -> None:
    # 2 x 2 x 6 = 24 payload values: N (23) is the last, every flag at its top.
    assert decode("1.N") == ZoraFlags(True, True, 14)
    with pytest.raises(ZoraFlagStringError):
        decode("1.O")


def test_the_two_strings_cannot_be_mistaken_for_each_other() -> None:
    with pytest.raises(ZoraFlagStringError):
        decode(MVP_BASELINE)
    with pytest.raises(FlagStringError):
        decode_z1r(encode(ZoraFlags(randomize_magical_sword=True)))


def test_a_cap_outside_its_choices_is_not_a_value() -> None:
    with pytest.raises(ValueError):
        ZoraFlags(magical_sword_hearts_highest=9)


# --- validation ----------------------------------------------------------------

def test_the_baseline_heart_range_is_10_to_14() -> None:
    assert magical_sword_heart_range(DEFAULT, BASELINE) == range(10, 15)
    assert magical_sword_heart_range(ZoraFlags(magical_sword_hearts_highest=12), BASELINE) == range(10, 13)


def test_randomize_magical_sword_needs_the_hearts_capped_at_12() -> None:
    refused = validate(ZoraFlags(randomize_magical_sword=True), BASELINE)
    assert len(refused) == 1 and "at most 12" in refused[0]
    for cap in (10, 11, 12):
        assert validate(ZoraFlags(randomize_magical_sword=True, magical_sword_hearts_highest=cap), BASELINE) == []
    for cap in (13, 14):
        assert validate(ZoraFlags(randomize_magical_sword=True, magical_sword_hearts_highest=cap), BASELINE)


def test_the_cap_follows_the_z1r_highest_when_lower() -> None:
    lowered = BASELINE.updated(options={MAGICAL_SWORD_HIGHEST: 2})        # 14 - 2 = 12
    assert validate(ZoraFlags(randomize_magical_sword=True), lowered) == []


def test_without_the_redraw_the_vanilla_12_passes() -> None:
    vanilla_hearts = BASELINE.updated(toggles={REDRAW_SWORD_HEARTS: ThreeState.OFF})
    assert magical_sword_heart_range(DEFAULT, vanilla_hearts) == range(12, 13)
    assert validate(ZoraFlags(randomize_magical_sword=True), vanilla_hearts) == []


def test_a_cap_below_the_lowest_is_refused_with_or_without_the_sword() -> None:
    raised_lowest = BASELINE.updated(options={MAGICAL_SWORD_LOWEST: 2})   # lowest 12
    for sword in (False, True):
        refused = validate(ZoraFlags(randomize_magical_sword=sword, magical_sword_hearts_highest=11), raised_lowest)
        assert len(refused) == 1 and "below" in refused[0]


def test_every_default_string_is_valid_for_the_presets() -> None:
    for preset in (MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF):
        assert validate(DEFAULT, decode_z1r(preset)) == []


def test_starting_heart_containers() -> None:
    assert starting_heart_containers(BASELINE) == 3
    assert starting_heart_containers(BASELINE.updated(options={STARTING_HEARTS: STARTING_HEARTS_RANDOM})) == 1


# --- seed and level-encoding key ---------------------------------------------------

def test_a_default_zora_string_keeps_todays_seed_and_key() -> None:
    for seed in (0, 1, 7, 1000, (1 << 64) - 1):
        assert generation_seed(seed, MVP_BASELINE, "") == seed
    assert level_encoding_text(MVP_BASELINE, "") == MVP_BASELINE


def test_any_zora_flag_moves_the_seed_and_the_key() -> None:
    seeds = set()
    for flags in every_flag_set():
        string = encode(flags)
        if not string:
            continue
        derived = generation_seed(7, MVP_BASELINE, string)
        assert 0 <= derived < 1 << 64 and derived != 7
        assert derived == generation_seed(7, MVP_BASELINE, string)
        seeds.add(derived)
        text = level_encoding_text(MVP_BASELINE, string)
        assert MVP_BASELINE in text and string in text and text != MVP_BASELINE
    assert len(seeds) == len(every_flag_set()) - 1


def test_the_derived_seed_depends_on_every_input() -> None:
    string = encode(ZoraFlags(randomize_letter=True))
    base = generation_seed(7, MVP_BASELINE, string)
    assert generation_seed(8, MVP_BASELINE, string) != base
    assert generation_seed(7, MVP_BASELINE_LEVEL_ENCODING_OFF, string) != base


def test_the_module_lists_one_field_per_flag() -> None:
    assert [field.name for field in zora_flags.FIELDS] == [
        "randomize_magical_sword", "randomize_letter", "magical_sword_hearts_highest",
        "progressive_items", "shop_items_in_pool", *zora_flags.OWNER_2_0_FIELDS,
        "l4_sword_in_level_2", "level_9_entrance_sword"]


# --- PI-FLAG-03: Progressive Items refuses Extra Candles ----------------------

def test_progressive_items_refuses_extra_candles_on() -> None:
    progressive = ZoraFlags(progressive_items=True)
    assert BASELINE.toggle(zora_flags.EXTRA_CANDLES) is ThreeState.ON       # the MVP baseline has B09 on
    assert validate(progressive, BASELINE) == [zora_flags.EXTRA_CANDLES_CONFLICT]
    assert zora_flags.conflicts(progressive, BASELINE) == [
        (zora_flags.EXTRA_CANDLES_CONFLICT, ("progressive_items", "B09"))]
    for value in (ThreeState.OFF, ThreeState.POSSIBLE):
        assert validate(progressive, BASELINE.updated(toggles={"B09": value})) == []
    # Shop Items in the Item Pool works with B09 (section 8).
    assert validate(ZoraFlags(shop_items_in_pool=True), BASELINE) == []


def test_a_possible_extra_candles_resolves_off_with_progressive_items() -> None:
    asked = BASELINE.updated(toggles={"B09": ThreeState.POSSIBLE})
    resolved = asked.updated(toggles={"B09": ThreeState.ON})
    progressive = ZoraFlags(progressive_items=True)
    assert zora_flags.without_extra_candles(progressive, resolved, asked).toggle("B09") is ThreeState.OFF
    assert zora_flags.without_extra_candles(DEFAULT, resolved, asked) == resolved
    assert zora_flags.without_extra_candles(progressive, BASELINE.updated(toggles={"B09": ThreeState.OFF}),
                                            BASELINE.updated(toggles={"B09": ThreeState.OFF})).toggle("B09") \
        is ThreeState.OFF
