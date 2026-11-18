"""The web page's Start Items tab (web/flag-tabs.json, web/zora-web.js): every start-item
setting on one tab, a layout change only, and the note shown while Max Start Items keeps none
of the chosen items."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from zora.flags import codec
from zora.flags import form as flag_form
from zora.flags import presets as flags_presets
from zora.flags.fields import (
    START_ITEM_LIMIT,
    START_ITEM_LIMIT_ALL_CHOSEN,
    START_ITEM_LIMIT_RANDOM,
    START_ITEM_LIMIT_RANDOM_CHOICES,
    STARTING_HEARTS,
    STARTING_PIECES,
    ThreeState,
)
from zora.generate.steps.start_items import START_ITEM_ORDER

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = REPO / "web" / "zora-web.js"
FLAG_TABS = json.loads((REPO / "web" / "flag-tabs.json").read_text())
START_TAB = "Start Items"
START_ITEM_IDS = {field.id for field, _ in START_ITEM_ORDER}
KEEPS_NO_START_ITEMS = min(START_ITEM_LIMIT_RANDOM_CHOICES)      # Max Start Items "0"
RAFT, RECORDER, BOW = "B57", "B60", "B58"


def with_values(options: dict[str, int] | None = None, toggles: dict[str, ThreeState] | None = None) -> str:
    """The page's default string with some fields changed, canonical."""
    base = codec.decode(flag_form.metadata()["defaultFlags"])
    return codec.encode(base.updated(options=options, toggles=toggles))


def test_the_tab_holds_every_starting_items_setting() -> None:
    on_tab = {code for code, entry in FLAG_TABS.items() if entry["tab"] == START_TAB}
    assert on_tab == {STARTING_HEARTS.id, START_ITEM_LIMIT.id, STARTING_PIECES.id, *START_ITEM_IDS}
    assert {code for code, entry in FLAG_TABS.items() if entry.get("startItem")} == START_ITEM_IDS
    assert [code for code, entry in FLAG_TABS.items() if "keepsNoStartItems" in entry] == [START_ITEM_LIMIT.id]
    assert FLAG_TABS[START_ITEM_LIMIT.id]["keepsNoStartItems"] == KEEPS_NO_START_ITEMS
    limit = next(field for field in flag_form.metadata()["fields"] if field["id"] == START_ITEM_LIMIT.id)
    assert next(value["label"] for value in limit["values"] if value["value"] == KEEPS_NO_START_ITEMS) == "0"


def test_the_page_offers_the_tab_after_overworld() -> None:
    """The original program's tabs (issue #15): Start Items after Overworld, Advanced last (after ZORA extras)."""
    page = PAGE_SCRIPT.read_text()
    assert f'const START_TAB = "{START_TAB}";' in page
    assert ('const FLAG_TABS = ["Shops", "Dungeon Items", "Dungeons", "Monsters", "Misc", "Overworld", START_TAB, '
            'ADVANCED_TAB];') in page


def test_every_field_keeps_a_tab_and_help() -> None:
    assert set(FLAG_TABS) == {field["id"] for field in flag_form.metadata()["fields"]}
    assert all(entry["help"] for entry in FLAG_TABS.values())


def test_the_defaults_are_unchanged() -> None:
    """The default string is still the level-encoding-off baseline, and it keeps three hearts, no
    pieces, Max Start Items at 0 and every Start setting Off."""
    metadata = flag_form.metadata()
    assert metadata["defaultFlags"] == flags_presets.MVP_BASELINE_LEVEL_ENCODING_OFF
    fields = flag_form.form_state(metadata["defaultFlags"])["fields"]
    assert fields[STARTING_HEARTS.id]["value"] == 2                  # "3"
    assert fields[START_ITEM_LIMIT.id]["value"] == KEEPS_NO_START_ITEMS
    assert fields[STARTING_PIECES.id]["value"] == 0
    assert all(fields[code]["value"] == ThreeState.OFF for code in START_ITEM_IDS)


START_STRINGS = [
    with_values(),
    with_values({START_ITEM_LIMIT.id: START_ITEM_LIMIT_ALL_CHOSEN},
                {RAFT: ThreeState.ON, RECORDER: ThreeState.POSSIBLE}),
    with_values({START_ITEM_LIMIT.id: START_ITEM_LIMIT_RANDOM}, dict.fromkeys(START_ITEM_IDS, ThreeState.ON)),
    with_values({START_ITEM_LIMIT.id: 3, STARTING_HEARTS.id: 3}, {BOW: ThreeState.ON}),
]


@pytest.mark.parametrize("flag_string", START_STRINGS)
def test_start_item_strings_round_trip_through_the_form(flag_string: str) -> None:
    """A string read into the controls encodes back exactly; the page's own string is that one."""
    state = flag_form.form_state(flag_string)
    values = {code: int(field["value"]) for code, field in state["fields"].items()}
    assert state["flags"] == flag_string
    assert flag_form.flags_from_values(values) == flag_string


# --- the note, run in Node ---------------------------------------------------------------------

def page_function(name: str) -> str:
    """A top-level function's source from web/zora-web.js."""
    match = re.search(rf"^function {name}\(.*?^}}\n", PAGE_SCRIPT.read_text(), re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


NOTE_CASES = [
    ({}, {}, False),                                                         # the defaults
    ({}, {RAFT: ThreeState.ON}, True),
    ({}, {RECORDER: ThreeState.POSSIBLE}, True),
    ({}, {BOW: ThreeState.ON}, True),                                        # a pasted unbuilt one too
    ({START_ITEM_LIMIT.id: START_ITEM_LIMIT_ALL_CHOSEN}, {RAFT: ThreeState.ON}, False),
    ({START_ITEM_LIMIT.id: KEEPS_NO_START_ITEMS + 1}, {RAFT: ThreeState.ON}, False),
    ({START_ITEM_LIMIT.id: START_ITEM_LIMIT_RANDOM}, {RAFT: ThreeState.POSSIBLE}, False),
    ({START_ITEM_LIMIT.id: START_ITEM_LIMIT_ALL_CHOSEN}, {}, False),
]


def test_the_note_shows_while_max_start_items_keeps_none() -> None:
    """startItemsAllDropped, run in Node on the form states Python gives the page: the note shows
    exactly while a Start setting is On or Random and Max Start Items is 0."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    states = [flag_form.form_state(with_values(options, toggles))["fields"] for options, toggles, _ in NOTE_CASES]
    script = "\n".join([page_function("startItemRules"), page_function("startItemsAllDropped"),
                        "const TOGGLE_OFF = 0;",
                        f"const rules = startItemRules({json.dumps(FLAG_TABS)});",
                        f"const states = {json.dumps(states)};",
                        "console.log(JSON.stringify(states.map((fields) => startItemsAllDropped(rules, fields))));"])
    # The script on stdin, not as one argument: the form states outgrow the kernel's limit on a
    # single argument (MAX_ARG_STRLEN, 128 KiB on Linux)
    shown = json.loads(subprocess.run([node, "-"], input=script, capture_output=True, text=True, check=True).stdout)
    assert shown == [expected for _, _, expected in NOTE_CASES]


def test_without_the_tabs_file_there_is_no_note() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = "\n".join([page_function("startItemRules"), page_function("startItemsAllDropped"),
                        "const TOGGLE_OFF = 0;",
                        "console.log(JSON.stringify([startItemRules({}), startItemsAllDropped(null, {})]));"])
    assert json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout) \
        == [None, False]


def test_the_page_shows_the_note_from_each_state() -> None:
    page = PAGE_SCRIPT.read_text()
    assert "const TOGGLE_OFF = 0;" in page
    assert '$("start-limit-note").hidden = !startItemsAllDropped(startRules, state.fields);' in page


# --- "Set all to" (tetraly/zora#22), run in Node on the page's own functions ---------------------

SET_ALL_FUNCTIONS = ("startItemRules", "blockedReason", "breaksRule", "setAllStartItems")


def set_all(flag_string: str, value: int) -> tuple[dict[str, str] | None, list[int]]:
    """setAllStartItems on the page state Python gives for FLAG_STRING: the control values it sends Python (as
    onControlChanged sends them; None when it sends nothing) and how often it asked."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    metadata = flag_form.metadata()
    state = flag_form.form_state(flag_string)
    supported = {field["id"]: field["supportedValues"] for field in metadata["fields"]}
    script = "\n".join([
        *map(page_function, SET_ALL_FUNCTIONS),
        f"const metadata = {{ dependencyRules: {json.dumps(metadata['dependencyRules'])} }};",
        f"const form = {{ fields: {json.dumps(state['fields'])} }};",
        f"const supported = {json.dumps(supported)};",
        "const controls = new Map(Object.entries(form.fields).map(([id, field]) =>",
        "  [id, { value: field.value, supported: new Set(supported[id]) }]));",
        f"const startRules = startItemRules({json.dumps(FLAG_TABS)});",
        "const sent = [];",
        "function onControlChanged() {",
        "  sent.push(Object.fromEntries([...controls].map(([id, control]) => [id, String(control.value)])));",
        "}",
        f"setAllStartItems({value});",
        "console.log(JSON.stringify(sent));",
    ])
    sent = json.loads(subprocess.run([node, "-"], input=script, capture_output=True, text=True, check=True).stdout)
    return (sent[-1] if sent else None), [len(sent)]


SET_ALL_START = with_values({START_ITEM_LIMIT.id: START_ITEM_LIMIT_ALL_CHOSEN, STARTING_HEARTS.id: 3},
                            {RAFT: ThreeState.ON, RECORDER: ThreeState.POSSIBLE})


@pytest.mark.parametrize("value", [ThreeState.OFF, ThreeState.ON, ThreeState.POSSIBLE], ids=["off", "on", "random"])
def test_set_all_sets_every_start_field_and_nothing_else(value: ThreeState) -> None:
    """One change for all 23, through the path a click takes (onControlChanged, then Python's form_change); the
    flag string afterward is the old one with every Start setting at the value, Max Start Items and the rest kept,
    and the page takes it: no rule refuses it and generation would take it."""
    values, asked = set_all(SET_ALL_START, int(value))
    assert asked == [1] and values is not None
    before = flag_form.form_state(SET_ALL_START)["fields"]
    assert {code for code in values if int(values[code]) != before[code]["value"]} <= START_ITEM_IDS
    after = flag_form.form_change(SET_ALL_START, values, "")
    assert after["flags"] == with_values({START_ITEM_LIMIT.id: START_ITEM_LIMIT_ALL_CHOSEN, STARTING_HEARTS.id: 3},
                                         dict.fromkeys(START_ITEM_IDS, value))
    assert after["refusals"] == [] and after["generateRefusals"] == []


def test_set_all_to_what_every_field_already_holds_changes_nothing() -> None:
    assert set_all(with_values(), int(ThreeState.OFF)) == (None, [0])


def test_set_all_is_an_action_never_a_setting() -> None:
    """Its buttons never show a value as chosen and it keeps no value of its own: nothing of it reaches a flag
    string, the saved preferences or the shared link (the page's other controls all come from the metadata)."""
    source = page_function("startAllRow") + page_function("setAllStartItems")
    assert "aria-pressed" not in source and "localStorage" not in source and "pageStorage" not in source
    assert "startAll" not in page_function("controlValues")
    assert "start-all" not in {field["id"] for field in flag_form.metadata()["fields"]}
