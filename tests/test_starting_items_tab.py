"""The web page's Starting Items tab (web/flag-tabs.json, web/zora-web.js): every start-item
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
START_TAB = "Starting Items"
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


def test_the_page_offers_the_tab_after_items() -> None:
    page = PAGE_SCRIPT.read_text()
    assert f'const START_TAB = "{START_TAB}";' in page
    assert 'const FLAG_TABS = ["Overworld", "Dungeons", "Items", START_TAB, "Monsters", "Misc"];' in page


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
    shown = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
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
