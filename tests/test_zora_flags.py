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


@pytest.mark.parametrize("string", ["D", "1D", "0.1", "01.1", "1.", ".1", "99.1", "1.?", "1.1 ", "1.O"])
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
        "progressive_items", "shop_items_in_pool", *zora_flags.OWNER_2_0_SLOTS,
        "l4_sword_in_level_2", "level_9_entrance_sword", "oops_all_enemies", "oops_all_bosses",
        *zora_flags.ZORA_1_0_FIELDS, "pegasus_boots", "expanded_dungeon_locations", "highlight_no_drop_rooms",
        "do_not_segment_dungeons", "disable_custom_music", "gatekeeper_bosses", *zora_flags.FULL_HEALTH_FIELDS,
        "harder_bosses", "harder_ganon", "offense_pacing", "defense_pacing", "recorder_warping",
        *zora_flags.SWAP_SWORDS_AND_RINGS_FIELDS, "swordlish", "swordlish_lowest", "swordlish_highest",
        "item_shuffle_no_vanilla"]


def field_named(name: str) -> zora_flags.ZoraField:
    return next(field for field in zora_flags.FIELDS if field.name == name)


@pytest.mark.parametrize("asked", [ThreeState.ON, ThreeState.POSSIBLE], ids=["on", "random"])
def test_version_8_holds_expanded_dungeon_locations_off_by_default(asked: ThreeState) -> None:
    """Version 8's one field, On / Off / ?, Off by default: a version-7 string decodes with it off
    and keeps its spelling; on or "?" it spells as version 8. It is produced: what it is refused with
    is a conflict (tests/test_expanded_dungeon_locations.py)."""
    field = field_named("expanded_dungeon_locations")
    assert (field.name, field.slots, field.version) == ("expanded_dungeon_locations", 3, 8)
    version_7 = encode(ZoraFlags(pegasus_boots=ThreeState.ON, randomize_letter=True))
    assert version_7.startswith("7.") and decode(version_7).expanded_dungeon_locations is ThreeState.OFF
    assert canonicalize(version_7) == version_7
    flags = ZoraFlags(expanded_dungeon_locations=asked)
    assert encode(flags).startswith("8.") and decode(encode(flags)) == flags
    assert zora_flags.unproduced_fields(flags) == zora_flags.unproduced_fields(DEFAULT) == []


@pytest.mark.parametrize("asked", [ThreeState.ON, ThreeState.POSSIBLE], ids=["on", "random"])
def test_version_9_holds_highlight_no_drop_rooms_off_by_default(asked: ThreeState) -> None:
    """Version 9's one field, On / Off / ?, Off by default: a version-8 string decodes with it off
    and keeps its spelling; on or "?" it spells as version 9, and it is produced
    (tests/test_highlight_no_drop_rooms.py)."""
    field = field_named("highlight_no_drop_rooms")
    assert (field.name, field.slots, field.version) == ("highlight_no_drop_rooms", 3, 9)
    version_8 = encode(ZoraFlags(expanded_dungeon_locations=ThreeState.ON, randomize_letter=True))
    assert version_8.startswith("8.") and decode(version_8).highlight_no_drop_rooms is ThreeState.OFF
    assert canonicalize(version_8) == version_8
    flags = ZoraFlags(highlight_no_drop_rooms=asked)
    assert encode(flags).startswith("9.") and decode(encode(flags)) == flags
    assert zora_flags.unproduced_fields(flags) == zora_flags.unproduced_fields(DEFAULT) == []


@pytest.mark.parametrize("asked", [ThreeState.ON, ThreeState.POSSIBLE], ids=["on", "random"])
def test_version_10_holds_do_not_segment_dungeons_off_by_default(asked: ThreeState) -> None:
    """Version 10's one field, On / Off / ?, Off by default: a version-9 string decodes with it off
    and keeps its spelling; on or "?" it spells as version 10, and it is produced
    (tests/test_do_not_segment_dungeons.py)."""
    field = field_named("do_not_segment_dungeons")
    assert (field.name, field.slots, field.version) == ("do_not_segment_dungeons", 3, 10)
    version_9 = encode(ZoraFlags(highlight_no_drop_rooms=ThreeState.ON, randomize_letter=True))
    assert version_9.startswith("9.") and decode(version_9).do_not_segment_dungeons is ThreeState.OFF
    assert canonicalize(version_9) == version_9
    flags = ZoraFlags(do_not_segment_dungeons=asked)
    assert encode(flags).startswith("10.") and decode(encode(flags)) == flags
    assert zora_flags.unproduced_fields(flags) == zora_flags.unproduced_fields(DEFAULT) == []



def test_version_11_holds_disable_custom_music_off_by_default() -> None:
    """Version 11's one field, a switch, Off by default: a version-10 string decodes with it off and
    keeps its spelling; on, it spells as version 11. It rules only the player settings, so the game's
    string (game_string), which the random streams and the level encoding key take, leaves it out."""
    field = field_named("disable_custom_music")
    assert (field.name, field.slots, field.version) == ("disable_custom_music", 2, 11)
    version_10 = encode(ZoraFlags(do_not_segment_dungeons=ThreeState.ON, randomize_letter=True))
    assert version_10.startswith("10.") and not decode(version_10).disable_custom_music
    assert canonicalize(version_10) == version_10
    raced = ZoraFlags(do_not_segment_dungeons=ThreeState.ON, randomize_letter=True, disable_custom_music=True)
    assert encode(raced).startswith("11.") and decode(encode(raced)) == raced
    assert zora_flags.game_string(raced) == version_10
    assert zora_flags.game_string(ZoraFlags(disable_custom_music=True)) == ""

# --- tetraly/zora#13: Progressive Items takes Extra Candles (PI-FLAG-03 lifted) ----

def test_progressive_items_takes_extra_candles() -> None:
    progressive = ZoraFlags(progressive_items=True)
    assert BASELINE.toggle("B09") is ThreeState.ON                          # the MVP baseline has B09 on
    for value in ThreeState:
        assert validate(progressive, BASELINE.updated(toggles={"B09": value})) == []
        assert zora_flags.conflicts(progressive, BASELINE.updated(toggles={"B09": value})) == []
