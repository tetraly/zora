"""Spoiler log information levels (owner rulings, 2026-11-06; docs/design/spoiler-levels.md): Print Quest Info
(B51) and the ZORA flag Detailed Spoiler Log (version 20) give levels 0 to 3, which the page shows as one
setting, Spoiler Log Detail Level."""
from zora.flags import form
from zora.flags.codec import decode
from zora.flags.fields import PRINT_QUEST_INFO, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import CURRENT_VERSION, SpoilerLevel, ZoraFlags, spoiler_level
from zora.flags.zora_flags import decode as decode_zora
from zora.flags.zora_flags import encode as encode_zora

START = MVP_BASELINE_LEVEL_ENCODING_OFF
# The frozen beta 12 string "random settings 3", which has Print Quest Info on
B51_ON_BETA_12 = "2LFtoxTvZRrVB!zn7LPDzL4hAp!0Vd7Crx58vuDDg"
B51 = PRINT_QUEST_INFO.id
# Each page value: B51 as the Z1R string holds it, and Detailed Spoiler Log
PAGE_VALUES = {0: (ThreeState.OFF, False), 1: (ThreeState.ON, False), form.SPOILER_MEDIUM_CHOICE: (ThreeState.OFF, True),
               form.SPOILER_FULL_CHOICE: (ThreeState.ON, True), 2: (ThreeState.POSSIBLE, False)}


def test_the_two_bits_give_four_levels() -> None:
    assert [spoiler_level(b51, detailed) for detailed in (False, True) for b51 in (False, True)] == list(SpoilerLevel)
    assert [level.value for level in SpoilerLevel] == [0, 1, 2, 3]


def test_detailed_spoiler_log_is_version_20_and_off_by_default() -> None:
    assert CURRENT_VERSION == 20
    assert ZoraFlags().detailed_spoiler_log is False
    assert encode_zora(ZoraFlags()) == ""
    assert decode_zora(encode_zora(ZoraFlags(detailed_spoiler_log=True))).detailed_spoiler_log is True


def test_the_page_shows_one_setting_with_five_values() -> None:
    entry = next(field for field in form.metadata()["fields"] if field["id"] == B51)
    assert entry["label"] == "Spoiler Log Detail Level"
    assert [(value["value"], value["label"]) for value in entry["values"]] == [
        (0, "None"), (1, "Basic"), (form.SPOILER_MEDIUM_CHOICE, "Medium"), (form.SPOILER_FULL_CHOICE, "Full"),
        (2, "Random")]
    hidden = next(field for field in form.metadata()["zora"]["fields"] if field["name"] == "detailed_spoiler_log")
    assert hidden["hidden"] is True


def test_each_value_writes_both_strings_and_reads_back() -> None:
    start = form.form_state(START)
    values = {field_id: field["value"] for field_id, field in start["fields"].items()}
    assert start["fields"][B51]["value"] == 0
    for choice, (b51, detailed) in PAGE_VALUES.items():
        state = form.form_change(START, {**values, B51: choice}, "")
        assert decode(state["flags"]).toggle(B51) is b51, choice
        assert decode_zora(state["zora"]["flags"]).detailed_spoiler_log is detailed, choice
        assert form.form_state(state["flags"], state["zora"]["flags"])["fields"][B51]["value"] == choice


def test_random_shows_as_random_whatever_the_zora_field_says() -> None:
    """A "?" picks both bits (ruling 4), so a pasted pair of B51 "?" and the ZORA field on reads as Random."""
    random = form.form_change(START, {**{k: f["value"] for k, f in form.form_state(START)["fields"].items()},
                                      B51: 2}, "")["flags"]
    on = encode_zora(ZoraFlags(detailed_spoiler_log=True))
    assert form.form_state(random, on)["fields"][B51]["value"] == 2


def test_every_level_but_none_is_beta() -> None:
    """Prompt 660 ruling 1: every level stays beta, Basic too, until the files load in ZTracker and ZoraTracker;
    None is the one level that isn't, and Random, which resolves to Basic, Medium or Full, is beta."""
    assert form.beta_values()[B51] == {1, form.SPOILER_MEDIUM_CHOICE, form.SPOILER_FULL_CHOICE, 2}
    assert form.form_state(START)["beta"] == []


def test_a_beta_12_string_with_print_quest_info_on_turns_on_beta_settings() -> None:
    """A loaded string from before the levels, with Print Quest Info on (B51), now reads as Basic, a beta value."""
    loaded = form.form_state(B51_ON_BETA_12)
    assert loaded["fields"][B51]["value"] == 1
    assert [entry["field"] for entry in loaded["beta"]] == [B51]
