"""The flag summary (web/zora-web.js flagSummary; a player request, 2026-10-26): the settings in words,
one section per tab, Starting Items just before Misc, ZORA extras last and always
(None when every one is Off). Every choice field is listed, a switch only at
On or Random, a (min, max) pair as one line and left out while it has no effect. The page's own code,
run in Node on the form's real metadata and state."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from zora.flags import codec
from zora.flags import form as flag_form
from zora.flags.fields import ThreeState
from zora.flags.zora_form import zora_flags_from_values

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
PAGE_HTML = (REPO / "web" / "index.html").read_text()
FLAG_TABS = json.loads((REPO / "web" / "flag-tabs.json").read_text())
ON, OFF, RANDOM = ThreeState.ON, ThreeState.OFF, ThreeState.POSSIBLE
# The first example in the request: Mixed Quest - 1st, Shapes, Community hints, and so on.
EXAMPLE_OPTIONS = {"C01": 2, "C02": 3, "C03": 2, "C04": 1, "C05": 3, "C06": 2, "C08": 0, "C09": 1, "C10": 1,
                   "C14": 2, "C16": 3, "C20": 1, "C21": 0, "C22": 0, "C23": 0}
EXAMPLE_TOGGLES = {"B08": ON, "B09": ON, "B10": ON, "B18": ON, "B20": ON, "B40": ON, "B42": ON, "B43": ON,
                   "B49": ON, "B34": RANDOM}
PIECES = {"Level 9 Entry": 0, "Triforce Range": 9}    # C08: 8 triforces, Random count inside the range


def page_function(name: str) -> str:
    match = re.search(rf"^function {name}\(.*?^}}$", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def page_constant(name: str) -> str:
    match = re.search(rf"^const {name} = .*?;$", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def summary(options: dict[str, int], toggles: dict[str, ThreeState],
            zora_values: dict[str, int] | None = None) -> dict[str, Any]:
    """The summary's sections ({tab: lines}) and its text for these settings."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    base = codec.decode(flag_form.metadata()["defaultFlags"])
    flags = codec.encode(base.updated(options=options, toggles=toggles))
    zora_flags = zora_flags_from_values(zora_values or {})
    state = flag_form.form_state(flags, zora_flags)
    assert state["ok"] and state["zora"]["ok"]
    metadata = flag_form.metadata()
    constants = [page_constant(name) for name in (
        "TOGGLE_ON", "TOGGLE_OFF", "START_TAB", "FLAG_TABS", "FALLBACK_TAB", "ZORA_TAB", "SUMMARY_ORDER",
        "SUMMARY_NO_EXTRAS",
        "FIELD_ID", "FIELD_ID_WITH_NAME", "FIELD_IDS_IN_BRACKETS", "RULE_ID")]
    functions = [page_function(name) for name in ("plainText", "labelIn", "tabOf", "flagSummary", "flagSummaryText")]
    zora = {"fields": metadata["zora"]["fields"], "values": state["zora"]["values"],
            "forced": state["zora"]["forced"]}
    arguments = ", ".join(json.dumps(value) for value in (metadata["fields"], FLAG_TABS, state["fields"], zora))
    source = "\n".join([
        *constants, f"const metadata = {json.dumps(metadata)};", *functions,
        f"const sections = flagSummary({arguments});",
        (f"console.log(JSON.stringify({{sections, text: flagSummaryText(sections, {json.dumps(state['flags'])}, "
         f"{json.dumps(state['zora']['flags'])})}}));"),
    ])
    out = json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)
    return {"tabs": {section["tab"]: section["lines"] for section in out["sections"]},
            "order": [section["tab"] for section in out["sections"]], "text": out["text"]}


def test_the_example_reads_by_tab() -> None:
    result = summary(EXAMPLE_OPTIONS, EXAMPLE_TOGGLES)
    assert result["order"] == ["Overworld", "Dungeons", "Items", "Monsters", "Starting Items", "Misc", "ZORA extras"]
    assert result["tabs"]["ZORA extras"] == ["None"]
    tabs = result["tabs"]
    assert tabs["Overworld"][:3] == ["Overworld Quest: Mixed Quest - 1st", "Start Screen: Easy start shuffle",
                                     "Cave Shuffle: All Caves"]
    assert {"Dungeon Quest: Shapes", "Level 9 Entry: 8 triforces", "Dungeon Room Shuffle: Full Shuffle",
            "Add 2nd Quest Rooms"} <= set(tabs["Dungeons"])
    assert {"Item Shuffle: Intra-Dungeon", "Armos Item: Random", "Shuffle Shop Items", "Extra Candles",
            "Book is an Atlas", "White Sword Hearts: 5 to 6",
            "Magical Sword Hearts: 10 to 14"} <= set(tabs["Items"])
    assert {"Starting Hearts: 4", "Triforce Pieces: 0"} <= set(tabs["Starting Items"])
    assert {'"Most" Enemy HP: +/- 2', "Boss HP: +/- 2", "Shuffle Enemy Groups", "Shuffle Overworld Group",
            "Randomize Boss Groups", "Red Bubble Curse: Swordless", "Shuffle Bosses: Random"} <= set(tabs["Monsters"])
    assert {"Hint Type: Community", "Force Gannon Fight"} <= set(tabs["Misc"])


def test_a_switch_at_off_is_left_out() -> None:
    lines = [line for tab in summary(EXAMPLE_OPTIONS, EXAMPLE_TOGGLES)["tabs"].values() for line in tab]
    assert "Mirror Overworld" not in " ".join(lines)        # never shown on the page, and Off
    assert not any(line.startswith("Start Raft") for line in lines)
    with_raft = summary(EXAMPLE_OPTIONS, {**EXAMPLE_TOGGLES, "B57": ON})
    assert "Start Raft" in with_raft["tabs"]["Starting Items"]


def test_a_range_without_effect_is_left_out() -> None:
    no_redraw = summary(EXAMPLE_OPTIONS, {**EXAMPLE_TOGGLES, "B10": OFF})["tabs"]["Items"]
    assert not any("Sword Hearts" in line for line in no_redraw)
    eight = summary(EXAMPLE_OPTIONS, EXAMPLE_TOGGLES)["tabs"]["Dungeons"]
    assert not any(line.startswith("Triforce Range") for line in eight)
    in_range = summary({**EXAMPLE_OPTIONS, "C08": PIECES["Triforce Range"]}, EXAMPLE_TOGGLES)["tabs"]["Dungeons"]
    assert "Triforce Range: 0 to 8" in in_range


def test_zora_extras_come_last_and_list_only_what_is_on() -> None:
    result = summary(EXAMPLE_OPTIONS, EXAMPLE_TOGGLES, {"progressive_items": 1, "add_l4_sword": 1})
    assert result["order"][-1] == "ZORA extras"
    assert result["tabs"]["ZORA extras"] == ["Progressive Items", "Add L4 Sword: Level 2"]
    text = result["text"]
    assert text.startswith("Flags: ") and "\nZORA flags: " in text
    assert "\n\nZORA extras\n- Progressive Items\n- Add L4 Sword: Level 2" in text


def test_swordlish_pieces_read_as_one_line_only_with_swordlish() -> None:
    """The pieces pair (controls count from 0: piece count - 1) is left out while Swordlish is Off, where its
    max control stands at 8 pieces (a bug in 24a8bb5 listed "Swordlish pieces (max): 8" then)."""
    assert summary(EXAMPLE_OPTIONS, EXAMPLE_TOGGLES, {"swordlish_highest": 7})["tabs"]["ZORA extras"] == ["None"]
    three = summary(EXAMPLE_OPTIONS, EXAMPLE_TOGGLES, {"swordlish": 1, "swordlish_lowest": 2, "swordlish_highest": 2})
    assert three["tabs"]["ZORA extras"] == ["Swordlish: On", "Swordlish pieces: 3"]
    ranged = summary(EXAMPLE_OPTIONS, EXAMPLE_TOGGLES, {"swordlish": 2, "swordlish_lowest": 1, "swordlish_highest": 4})
    assert ranged["tabs"]["ZORA extras"] == ["Swordlish: Random", "Swordlish pieces: 2 to 5"]


def test_the_page_shows_it_above_the_tabs_and_keeps_it_current() -> None:
    assert PAGE_HTML.index('id="flag-summary"') < PAGE_HTML.index('id="tabs"')
    assert 'id="flag-summary-copy"' in PAGE_HTML
    assert "showFlagSummary(state);" in page_function("showState")
