"""The web page's flag form (zora/flags/form.py): the metadata the worker
hands the page matches zora/flags/, and the page's data path (metadata ->
controls -> string) round-trips every preset. No browser: the controls are
simulated as the page builds them, one string value per field id."""
import json
import re
from pathlib import Path

import pytest

from zora.flags import form as flag_form
from zora.flags import codec
from zora.flags import dependencies
from zora.flags import fields as flags_fields
from zora.flags import presets as flags_presets
from zora.flags import support
from zora.rom import level_encoding
from zora.flags.fields import OptionField, ThreeState, ToggleField

REPO = Path(__file__).resolve().parent.parent
WORKER = REPO / "web" / "zora-worker.js"
PAGE_SCRIPT = REPO / "web" / "zora-web.js"


@pytest.fixture(params=["installed", "absent"])
def build(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Both builds: with the private level-encoding module and without it."""
    if request.param == "absent":
        monkeypatch.setattr(level_encoding, "_ENCODER", None)
    elif not level_encoding.is_available():
        pytest.skip("the private level-encoding module is not installed")
    return str(request.param)


def worker_metadata() -> dict:
    """The metadata as the worker receives it: through JSON."""
    received: dict = json.loads(json.dumps(flag_form.metadata()))
    return received


def worker_state(flag_string: str) -> dict:
    state: dict = json.loads(json.dumps(flag_form.form_state(flag_string)))
    return state


def controls_from(metadata: dict, state: dict) -> dict[str, str]:
    """What the page's controls hold after it renders a state: one control
    per metadata field, set to the state's value, read back as a string."""
    controls = {}
    for field in metadata["fields"]:
        value = state["fields"][field["id"]]["value"]
        assert value in [entry["value"] for entry in field["values"]], (field["id"], value)
        controls[field["id"]] = str(value)
    return controls


def test_metadata_fields_match_flags_module() -> None:
    metadata = worker_metadata()
    fields = metadata["fields"]
    expected: list[OptionField | ToggleField] = [*flags_fields.OPTION_FIELDS, *flags_fields.TOGGLE_FIELDS]
    assert [field["id"] for field in fields] == [field.id for field in expected]
    for entry, field in zip(fields, expected):
        assert entry["setting"] == field.setting
        if isinstance(field, OptionField):
            assert entry["kind"] == "option"
            assert entry["slots"] == field.slots
            assert [v["value"] for v in entry["values"]] == list(range(field.count))
            assert entry["randomValues"] == sorted(field.random_choices)
        else:
            assert entry["kind"] == "toggle"
            # Encode level data is a two-state switch (owner ruling, 2026-10-06)
            states = ((ThreeState.OFF, ThreeState.ON) if field == flags_fields.ENCODE_LEVEL_DATA
                      else tuple(ThreeState))
            assert [v["value"] for v in entry["values"]] == [int(state) for state in states]
        assert all(v["label"] for v in entry["values"])
        assert len({v["label"] for v in entry["values"]}) == len(entry["values"]), field.id
    assert metadata["alphabet"] == codec.ALPHABET
    assert metadata["defaultFlags"] == flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF


def test_metadata_support_matrix_matches_flags_module() -> None:
    """The baseline value, the turn-off values (FL-OFF-07), the alternative values (FL-ALT, owner
    ruling) and, where both values of a three-state field are supported, its "?"; B23's off and "?"
    need B22 off, so they are not offered here."""
    baseline = support.mvp_baseline_settings()
    both = [ThreeState.OFF, ThreeState.ON, ThreeState.POSSIBLE]
    for entry in worker_metadata()["fields"]:
        field_id = entry["id"]
        if field_id == flags_fields.ENCODE_LEVEL_DATA.id:
            assert entry["supportedValues"] == [ThreeState.OFF, ThreeState.ON]     # never "?"
        elif entry["kind"] == "option":
            expected = ({baseline.option(field_id)} | support.TURN_OFF_OPTIONS.get(field_id, frozenset())
                        | support.ALTERNATIVE_OPTIONS.get(field_id, frozenset()))
            assert entry["supportedValues"] == sorted(expected)
        elif (field_id in support.TURN_OFF_TOGGLES or field_id in support.OWNER_TURN_OFF_TOGGLES) \
                and field_id != "B23":
            assert entry["supportedValues"] == both
        else:
            assert entry["supportedValues"] == [baseline.toggle(field_id)]


def test_metadata_level_encoding_text_is_the_owners(build: str) -> None:
    metadata = worker_metadata()
    encode = next(f for f in metadata["fields"] if f["id"] == metadata["encodeLevelData"])
    assert encode["label"] == "Encode level data" == metadata["levelEncoding"]["label"]
    assert encode["help"] == level_encoding.HELP_TEXT == metadata["levelEncoding"]["help"]
    assert metadata["levelEncoding"]["available"] == level_encoding.is_available()
    assert metadata["levelEncoding"]["unavailable"] == "Not available in this build"


def test_metadata_presets_are_the_spec_presets(build: str) -> None:
    presets = worker_metadata()["presets"]
    assert [p["name"] for p in presets[:4]] == list(flags_presets.PRESETS)
    assert [p["flags"] for p in presets[:4]] == [codec.canonicalize(s) for s in flags_presets.PRESETS.values()]
    assert presets[0]["label"] == "Consternation"
    assert presets[4]["flags"] == flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF and presets[4]["available"]
    for preset in presets[1:4]:          # the published variants have fields the MVP does not produce
        assert not preset["available"] and preset["reasons"][0].startswith("not produced: ")
        assert preset["reason"] == "Not produced by ZORA yet"
    if build == "installed":
        assert presets[0]["available"] and presets[0]["reason"] is None
    else:
        assert presets[0]["reason"] == "Encode level data: not available in this build"


def test_metadata_lists_every_rule_the_check_can_give() -> None:
    listed = {rule["rule"] for rule in worker_metadata()["dependencyRules"]}
    zero = flags_fields.Settings.zero()
    breaking = [
        zero.updated(options={"C12": flags_fields.PinnedItem.LADDER}),
        zero.updated(options={"C11": 3, "C13": 3}),
        zero.updated(toggles={"B02": ThreeState.ON}),
        zero.updated(toggles={"B26": ThreeState.ON}),
        zero.updated(toggles={"B36": ThreeState.ON}),
    ]
    given = {refusal.rule for settings in breaking for refusal in dependencies.check_dependencies(settings)}
    assert given == listed - {"FL-DEP-02 rule 4"}


@pytest.mark.parametrize("name", [*flags_presets.PRESETS, "CP-5"])
def test_preset_round_trips_through_the_controls(name: str) -> None:
    preset = flags_presets.PRESETS.get(name, flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF)
    metadata = worker_metadata()
    state = worker_state(preset)
    assert state["ok"]
    controls = controls_from(metadata, state)
    assert flag_form.flags_from_values(controls) == codec.canonicalize(preset) == state["flags"]


def test_pasted_string_is_shown_canonical_and_bad_strings_show_the_decoders_error() -> None:
    state = worker_state("0" + flags_presets.MVP_BASELINE)
    assert state["flags"] == flags_presets.MVP_BASELINE and state["preset"] == "MVP baseline"
    def without_zora(state: dict) -> dict:
        return {key: value for key, value in state.items() if key != "zora"}
    assert without_zora(worker_state("abc?")) == {"ok": False, "error": "Flag string: invalid character '?'"}
    assert without_zora(worker_state("")) == {"ok": False, "error": "Flag string: empty string"}


def test_fields_at_their_only_produced_value_are_disabled_with_the_reason() -> None:
    state = worker_state(flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF)
    assert state["generateRefusals"] == []
    selectable = {*support.TURN_OFF_TOGGLES, *support.OWNER_TURN_OFF_TOGGLES, *support.TURN_OFF_OPTIONS,
                  *support.ALTERNATIVE_OPTIONS} - {"B23"}
    for field_id, field in state["fields"].items():
        if field_id == flags_fields.ENCODE_LEVEL_DATA.id:
            assert not field["disabled"] or not level_encoding.is_available()
        elif field_id in selectable:
            produced = (support.TURN_OFF_OPTIONS.get(field_id, frozenset())
                        | support.ALTERNATIVE_OPTIONS.get(field_id, frozenset())) or {ThreeState.OFF}
            assert not field["disabled"], field_id
            assert all(text != "Not produced by ZORA yet" for value, text in field["blocked"].items()
                       if int(value) in produced), field_id
        else:
            assert field["disabled"] and field["reason"] == "Not produced by ZORA yet", field_id


def test_fl_dep_06_b23_is_greyed_while_b22_is_off_and_the_string_is_corrected() -> None:
    """FL-DEP-06: a string with B22 off and B23 on is shown as the canonical string with both off,
    with a note, B23 greyed and displayed off; it is not refused."""
    cp5 = codec.decode(flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF)
    pasted = codec.encode(cp5.updated(toggles={"B22": ThreeState.OFF}))
    pair = codec.encode(cp5.updated(toggles={"B22": ThreeState.OFF, "B23": ThreeState.OFF}))
    state = worker_state(pasted)
    assert state["flags"] == pair != pasted
    assert state["adjustments"][0] == flag_form.TOLL_TURNED_OFF_NOTE
    assert state["fields"]["B23"]["value"] == ThreeState.OFF and state["fields"]["B23"]["disabled"]
    assert state["generateRefusals"] == [] and worker_state(pair)["adjustments"] == []


def test_a_pasted_unproduced_value_stays_editable_and_generation_is_refused() -> None:
    state = worker_state(flags_presets.PUBLISHED_VARIANT_A)
    c01 = state["fields"]["C01"]
    assert not c01["disabled"] and c01["reason"] == flag_form.CURRENT_NOT_PRODUCED_TEXT
    assert "0" not in c01["blocked"]                 # the produced value (first quest) can be picked
    assert state["generateRefusals"][0] == "not produced: C01 (Overworld quest), C06 (Item shuffle scope)"
    # its alternative values (FL-ALT-02 to FL-ALT-04) are produced (owner ruling)
    for field_id in ("C03", "C16", "C20"):
        assert state["fields"][field_id]["reason"] != flag_form.CURRENT_NOT_PRODUCED_TEXT, field_id


def test_a_choice_that_breaks_a_rule_is_blocked_with_the_rules_message() -> None:
    # From the zero string: pinning the Ladder to the coast cave breaks FL-DEP-01 rule 1.
    state = worker_state("0")
    assert state["fields"]["C12"]["blocked"]["5"] == "FL-DEP-01 rule 1: the Ladder cannot be pinned to the coast cave"
    assert state["fields"]["B02"]["blocked"]["1"].startswith("FL-DEP-02 rule 1: ")
    values = controls_from(worker_metadata(), state)
    values["C12"] = "5"
    changed = flag_form.form_change("0", values)
    assert changed["flags"] == "0" and changed["blockedChange"].startswith("FL-DEP-01 rule 1")
    values["C12"] = "3"
    assert flag_form.form_change("0", values)["flags"] == codec.encode(
        flags_fields.Settings.zero().updated(options={"C12": 3}))


def test_level_encoding_choice_follows_the_build(build: str) -> None:
    encode = flags_fields.ENCODE_LEVEL_DATA.id
    off = worker_state(flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF)["fields"][encode]
    on = worker_state(flags_presets.MVP_BASELINE)
    if level_encoding.is_available():
        assert "1" not in off["blocked"] and on["generateRefusals"] == []
    else:
        assert off["blocked"]["1"] == "Not available in this build"
        assert on["fields"][encode]["reason"] == "Not available in this build"
        assert not on["fields"][encode]["disabled"]          # it can still be turned off
        assert on["generateRefusals"] == ["Encode level data: Not available in this build"]


def test_page_has_no_field_list_of_its_own() -> None:
    """The page builds its controls from the metadata: no field ids, option
    labels or preset strings are written in its JavaScript."""
    worker = WORKER.read_text()
    page = PAGE_SCRIPT.read_text()
    assert "flag_form.metadata()" in worker and "flag_form.form_state(" in worker
    for script in (worker, page):
        assert not re.search(r"""["'][BC]\d\d["']""", script)
        for preset in flags_presets.PRESETS.values():
            assert preset not in script


def test_a_pasted_question_mark_on_level_encoding_is_refused_in_the_owners_words() -> None:
    """Owner ruling (2026-10-06): Encode level data is on or off. A pasted "?" there is shown as
    a problem with the owner's message, and generation is refused with it."""
    question = codec.encode(codec.decode(flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        toggles={flags_fields.ENCODE_LEVEL_DATA.id: ThreeState.POSSIBLE}))
    state = flag_form.form_state(question)
    field = state["fields"][flags_fields.ENCODE_LEVEL_DATA.id]
    assert field["problem"] and field["reason"] == support.ENCODE_LEVEL_DATA_NOT_RANDOM
    assert set(field["blocked"]) <= {"0", "1"}
    assert state["generateRefusals"] == [support.ENCODE_LEVEL_DATA_NOT_RANDOM]
    assert not flag_form.form_state(flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF)["generateRefusals"]
