"""The web page's custom presets (web/zora-web.js readCustomPresets, writeCustomPresets): 8 slots
since 2026-10-17 (owner; 4 before), and a list a player saved with 4 keeps every preset in its slot."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
KEY = "zora.customPresets"
OLD_SLOTS = [{"name": "Mine", "flags": "AAAA", "zoraFlags": "B"}, None,
             {"name": "Race", "flags": "CCCC", "zoraFlags": ""}, {"name": "Old", "flags": "DDDD"}]


def page_function(name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def page_constant(name: str) -> str:
    match = re.search(rf"^const {name} = .*?;$", PAGE_SCRIPT, re.MULTILINE)
    assert match, name
    return match.group(0)


def run_page(stored: str | None, script: str) -> Any:
    """SCRIPT's printed JSON, with this browser's storage holding STORED under the presets' key."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = "\n".join([
        "const store = new Map();",
        "const localStorage = { getItem: (k) => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)),",
        "                       removeItem: (k) => store.delete(k) };",
        "const pageStorage = localStorage;     // the regular channel's keys (web/widgets.js)",
        f"store.set({json.dumps(KEY)}, {json.dumps(stored)});" if stored is not None else "",
        page_constant("CUSTOM_PRESETS_KEY"), page_constant("CUSTOM_SLOT_COUNT"),
        page_function("readCustomPresets"), page_function("checkedCustomPresets"), page_function("writeCustomPresets"),
        script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


def test_eight_slots() -> None:
    assert page_constant("CUSTOM_SLOT_COUNT") == "const CUSTOM_SLOT_COUNT = 8;"
    assert run_page(None, "console.log(JSON.stringify(readCustomPresets()));") == [None] * 8


def test_a_list_saved_with_four_slots_keeps_its_presets() -> None:
    """Each saved preset stays in its slot (one saved before ZORA flags had a slot reads with an empty
    ZORA string), and slots 5 to 8 are empty; saving slot 8 keeps the first four."""
    slots = run_page(json.dumps(OLD_SLOTS), """
const slots = readCustomPresets();
slots[7] = { name: "New", flags: "EEEE", zoraFlags: "" };
writeCustomPresets(slots);
console.log(JSON.stringify([slots, readCustomPresets()]));""")
    expected = [{"name": "Mine", "flags": "AAAA", "zoraFlags": "B"}, None,
                {"name": "Race", "flags": "CCCC", "zoraFlags": ""}, {"name": "Old", "flags": "DDDD", "zoraFlags": ""},
                None, None, None, {"name": "New", "flags": "EEEE", "zoraFlags": ""}]
    assert slots == [expected, expected]
