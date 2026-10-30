"""The page's flag names are the community's (owner ruling, 2026-10-10): the original
randomizer's names, docs/spec/flag-names-reference.csv, imported through docs/flag-names.csv
(scripts/flag_names.py reference, then import). Only labels change: flag strings and output stay."""
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from zora.flags import codec
from zora.flags import form as flag_form
from zora.flags import presets as flags_presets
from zora.flags.fields import (
    ENCODE_LEVEL_DATA,
    INERT_TOGGLES,
    ITEM_SHUFFLE_SCOPE,
    THREE_STATE_LABELS,
    OptionField,
    ThreeState,
)

REPO = Path(__file__).resolve().parent.parent
REFERENCE = REPO / "docs" / "spec" / "flag-names-reference.csv"
SWITCH = ["Off", "On"]
THREE_WAY_SWITCH = [*SWITCH, "Random"]
# The table is installed with the spec but, like every CSV there, not committed (.gitignore):
# a checkout without it still checks the names against docs/flag-names.csv (test_flag_names.py).
needs_reference = pytest.mark.skipif(not REFERENCE.exists(),
                                     reason="docs/spec/flag-names-reference.csv is not installed")


def reference() -> dict[str, list[dict[str, str]]]:
    rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    with REFERENCE.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            rows[row["code"]].append(row)
    return {code: sorted(field_rows, key=lambda row: int(row["value"])) for code, field_rows in rows.items()}


def page_fields() -> dict[str, dict[str, Any]]:
    return {field["id"]: field for field in flag_form.metadata()["fields"]}


# Item Shuffle's Random (No Vanilla): a page choice for Random with a ZORA flag (form.ITEM_SHUFFLE_NO_VANILLA_CHOICE),
# no Z1R value, so neither in the community's table nor written by flags_from_values (form_change writes both strings;
# tests/test_item_shuffle_no_vanilla.py)
PAGE_ONLY_VALUES = {ITEM_SHUFFLE_SCOPE.id: flag_form.ITEM_SHUFFLE_NO_VANILLA_CHOICE}


def z1r_values(code: str, field: dict[str, Any]) -> list[dict[str, Any]]:
    return [value for value in field["values"] if PAGE_ONLY_VALUES.get(code) != value["value"]]


# The fields the community names table predates (the 7e32c5c export's B92 to B94): the page names them
# as the spec does (FP-MAP-01, FP-MAP-02: Remove Maps, All Maps, All Compasses)
NOT_IN_THE_REFERENCE = {"B92": "Remove Maps", "B93": "All Maps", "B94": "All Compasses"}


@needs_reference
def test_the_reference_names_every_z1r_field() -> None:
    assert set(reference()) == set(page_fields()) - set(NOT_IN_THE_REFERENCE)


@needs_reference
def test_option_values_are_the_reference_names() -> None:
    table = reference()
    for code, field in page_fields().items():
        if field["kind"] == "option":
            labels = [value["label"] for value in z1r_values(code, field)]
            assert labels == [row["value_name"] for row in table[code]], code


def test_option_fields_keep_their_names() -> None:
    """The original randomizer names no option field (C01-C27): each keeps the page's name."""
    owner = flag_form.owner_names()
    for code, field in page_fields().items():
        if field["kind"] == "option":
            assert field["label"] == owner[code]["name"] and field["label"], code


@needs_reference
def test_switches_are_named_as_the_reference_names_them() -> None:
    """Every B field's name, but Encode level data's: ZORA's B82 is not the original randomizer's (Race ROM).
    FL-DEP-05's two fields, which change nothing in ZORA, say so after the name. Two switches have
    ZORA's own neutral names (owner decision, 2026-10-12; form.OWN_SWITCH_NAMES)."""
    table = reference()
    inert = {field.id for field in INERT_TOGGLES}
    for code, field in page_fields().items():
        if field["kind"] == "toggle" and code != ENCODE_LEVEL_DATA.id:
            suffix = " (no effect in ZORA)" if code in inert else ""
            name = (flag_form.OWN_SWITCH_NAMES.get(code) or NOT_IN_THE_REFERENCE.get(code)
                    or table[code][0]["field_name"])
            assert field["label"] == name + suffix, code
    assert page_fields()[ENCODE_LEVEL_DATA.id]["label"] == "Encode level data"
    assert page_fields()["B14"]["label"] == "Shuffle Dungeon Items (no effect in ZORA)"
    assert page_fields()["B16"]["label"] == "Shuffle Dungeon Hearts (no effect in ZORA)"
    assert page_fields()["B29"]["label"] == "Shuffle Bomb Upgraders"
    assert page_fields()["B48"]["label"] == "Book to Understand NPCs"


def test_misleading_values_have_notes() -> None:
    """The community's label stays; a note beside it says what the value does (owner request, 2026-10-10)."""
    notes = {(code, int(value["value"])): (value["label"], value["note"])
             for code, field in page_fields().items() for value in field["values"] if "note" in value}
    assert notes == {
        **{(code, 0): ("Random", "No item pinned") for code in ("C11", "C12", "C13", "C26", "C27")},
        ("C06", 1): ("Item Only", "Major items only; Heart Containers stay in place"),  # owner wording, 2026-10-15
        ("C16", 16): ("1-5 Hearts", "One random count from 1 to 5"),
        ("C08", 11): ("Other Item", "Level 9 opens for an item instead of Triforce pieces"),
    }


def test_the_page_shows_value_notes() -> None:
    page = (REPO / "web" / "zora-web.js").read_text()
    assert "noteIn(control.field.values, field.value)" in page


def test_switch_states_are_off_on_random() -> None:
    """The original randomizer's third state is "Possible"; the page calls it Random (owner ruling, 2026-10-10)."""
    assert THREE_STATE_LABELS == dict(zip(ThreeState, THREE_WAY_SWITCH, strict=True))
    for code, field in page_fields().items():
        if field["kind"] == "toggle":
            expected = SWITCH if code == ENCODE_LEVEL_DATA.id else THREE_WAY_SWITCH
            assert [value["label"] for value in field["values"]] == expected, code
            assert [int(value["value"]) for value in field["values"]] == list(range(len(expected))), code
    for field in flag_form.metadata()["zora"]["fields"]:
        if field["kind"] != "option":
            expected = THREE_WAY_SWITCH if field["kind"] == "three_state" else SWITCH
            assert [(value["value"], value["label"]) for value in field["values"]] == list(enumerate(expected))


def test_labels_within_a_field_are_distinct() -> None:
    for field in [*flag_form.metadata()["fields"], *flag_form.metadata()["zora"]["fields"]]:
        labels = [value["label"] for value in field["values"]]
        assert len(labels) == len(set(labels)), field["label"]


def test_the_page_names_no_switch_state_itself() -> None:
    page = (REPO / "web" / "zora-web.js").read_text()
    assert "TOGGLE_CHOICES" not in page


@pytest.mark.parametrize("flag_string",
                         [*flags_presets.PRESETS.values(), flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF])
def test_flag_strings_round_trip_through_the_form(flag_string: str) -> None:
    """The page's controls hold values, never labels: a string read into them encodes back the same."""
    state = flag_form.form_state(flag_string)
    values = {code: int(field["value"]) for code, field in state["fields"].items()}
    assert flag_form.flags_from_values(values) == codec.canonicalize(flag_string) == state["flags"]


def test_each_offered_value_encodes_as_itself() -> None:
    """Choosing a value on the page sets the field to that value, for every value of every field
    (Starting Hearts' "1" is value 0, Max Start Items' "All" is value 0, and so on)."""
    baseline = flag_form.form_state(flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF)
    start = {code: int(field["value"]) for code, field in baseline["fields"].items()}
    fields = {field.id: field for field in flag_form.ALL_FIELDS}
    for code, field in page_fields().items():
        for value in z1r_values(code, field):
            settings = codec.decode(flag_form.flags_from_values({**start, code: int(value["value"])}))
            field_def = fields[code]
            held = settings.option(field_def) if isinstance(field_def, OptionField) else settings.toggle(field_def)
            assert int(held) == int(value["value"]), (code, value)
