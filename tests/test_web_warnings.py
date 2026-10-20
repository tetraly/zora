"""The page's warnings (web/zora-web.js showWarnings; Expanded Dungeon Locations, owner and Bogie
2026-10-18): a setting the flags accept but the page should note, shown beside each setting the
warning names, not red, never over a conflict's red note, never twice. Run in Node on the page's own
function, with the worker's warning for Dungeons Only with Shuffle Wood Sword Cave on."""
import json
import re
import shutil
import subprocess
from typing import Any

import pytest

from tests.test_web_conflict_tabs import PAGE_SCRIPT, page_function
from zora.flags import form, zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import CaveShuffle, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF

FAKE_PAGE = """
const control = () => ({ row: { hidden: true }, reason: { textContent: "" } });
const zoraControls = new Map([["expanded_dungeon_locations", control()]]);
const controls = new Map([["B02", control()], ["B04", control()]]);
const plainText = (text) => text;
const state = () => Object.fromEntries([...zoraControls, ...controls].map(([name, c]) =>
  [name, [c.row.hidden, c.reason.textContent]]));
"""
ON = zora_flags.encode(zora_flags.ZoraFlags(expanded_dungeon_locations=ThreeState.ON))


def run(script: str) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = "\n".join([page_function("showWarnings"), FAKE_PAGE, script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


def flags_with(**toggles: ThreeState) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        options={"C05": CaveShuffle.DUNGEON_DOORS_ONLY},
        toggles={"B02": ThreeState.OFF, "B04": ThreeState.OFF, **toggles}))


def test_the_worker_warns_only_for_dungeons_only_with_b02_or_b04() -> None:
    warned = form.form_state(flags_with(B02=ThreeState.ON), ON)["zora"]
    assert warned["conflicts"] == []
    assert [entry["fields"] for entry in warned["warnings"]] == [["expanded_dungeon_locations", "B02", "B04"]]
    assert form.form_state(flags_with(B04=ThreeState.POSSIBLE), ON)["zora"]["warnings"]
    assert form.form_state(flags_with(), ON)["zora"]["warnings"] == []
    assert form.form_state(flags_with(B02=ThreeState.ON), "")["zora"]["warnings"] == []
    all_caves = encode(decode(flags_with(B02=ThreeState.ON)).updated(options={"C05": CaveShuffle.ALL_CAVES}))
    assert form.form_state(all_caves, ON)["zora"]["warnings"] == []


def test_each_named_setting_shows_the_warning_once_and_not_over_a_conflict() -> None:
    warning = form.form_state(flags_with(B02=ThreeState.ON), ON)["zora"]["warnings"]
    answers = run(f"""
const warnings = {json.dumps(warning)};
showWarnings(warnings, new Map());
const once = state();
showWarnings(warnings, new Map());
const twice = state();
for (const c of [...zoraControls.values(), ...controls.values()]) {{ c.row.hidden = true; c.reason.textContent = ""; }}
controls.get("B04").reason.textContent = "red";
showWarnings(warnings, new Map([["B04", ["red"]]]));
console.log(JSON.stringify({{ once, twice, refused: state() }}));
""")
    text = warning[0]["message"]
    assert answers["once"] == answers["twice"] == {name: [False, text] for name in ("expanded_dungeon_locations",
                                                                                    "B02", "B04")}
    assert answers["refused"]["B04"] == [True, "red"] and answers["refused"]["B02"] == [False, text]


def test_the_page_shows_the_warnings_after_the_conflicts() -> None:
    show = page_function("showZoraState")
    assert show.index("showWarnings(zora.warnings || [], messages)") > show.index("setting--problem")
    assert "setting--problem" not in page_function("showWarnings")
    assert re.search(r"function showWarnings\(warnings, refused\)", PAGE_SCRIPT)
