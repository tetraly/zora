"""The test channel's own browser storage (docs/releasing.md "Channels"; web/widgets.js channelKey and
pageStorage, web/zora-web.js copyRegularChannelSettings): the test page reads and writes only keys
behind "zora-test:", so testing never changes the regular page's presets or settings; on its first
load it copies the regular page's saved settings into its own keys, in its own format, and never
writes the regular keys. The page's own code, run in Node on a stand-in localStorage."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
WIDGETS_SCRIPT = (REPO / "web" / "widgets.js").read_text()
PREFIX = "zora-test:"
PAGE_CONSTANTS = ["CUSTOM_PRESETS_KEY", "CUSTOM_SLOT_COUNT", "PLAYER_NAME_KEY", "THEME_KEY", "TAB_KEY", "NES_PALETTE",
                  "BLACKER_THAN_BLACK", "EXCLUDED_COLORS", "PLAYER_SETTINGS_KEY", "PLAYER_CHOICES", "PLAYER_COLORS",
                  "COLOR_SLOTS", "MULTIWORLD_CHOICES", "ALL_CHOICES", "COPIED_FROM_REGULAR_KEY"]
PAGE_FUNCTIONS = ["defaultPlayerSettings", "isPickableColor", "checkedPlayerSettings", "checkedCustomPresets",
                  "copyRegularChannelSettings", "readCustomPresets", "writeCustomPresets", "loadPlayerSettings"]
WIDGET_CONSTANTS = ["REGULAR_CHANNEL", "TEST_CHANNEL", "TEST_STORAGE_PREFIX"]
# Saved by an earlier regular page: four preset slots (no ZORA flags in one), a player-settings object
# with a retired key and a color the page no longer allows, a name, a theme and a tab.
REGULAR = {
    "zora.customPresets": json.dumps([{"name": "Race", "flags": "AAAA", "zoraFlags": "4.T9Jvg"}, None,
                                      {"name": "Old", "flags": "BBBB"}, None]),
    "zora-player-settings": json.dumps({"music": "off", "statisticsScreen": "on", "heart": 0x0D, "greenTunic": 0x2A}),
    "zora.playerName": "Tester", "zora-theme": "dark", "zora-tab": "flags",
}


def source_block(script: str, kind: str, name: str) -> str:
    """A top-level `const NAME = ...;` or `function NAME(...) {...}` of SCRIPT, to its closing line."""
    start = re.search(rf"^{kind} {name}\b", script, re.MULTILINE)
    assert start, name
    lines = script[start.start():].split("\n")
    code = [re.sub(r"\s*//.*$", "", line) for line in lines]          # a line's trailing comment aside
    end = next(index for index, line in enumerate(code)
               if (kind == "const" and line.endswith(";") and (index == 0 or not line.startswith(" ")))
               or (kind == "function" and line == "}"))
    return "\n".join(lines[:end + 1])


def run(channel: str, stored: dict[str, str], script: str) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = "\n".join([
        "const store = new Map(Object.entries(" + json.dumps(stored) + "));",
        "const writes = [];",
        "const localStorage = { getItem: (k) => store.has(k) ? store.get(k) : null,",
        "  setItem: (k, v) => { writes.push(k); store.set(k, String(v)); }, removeItem: (k) => store.delete(k) };",
        *(source_block(WIDGETS_SCRIPT, "const", name) for name in WIDGET_CONSTANTS),
        f"const PAGE_CHANNEL = {json.dumps(channel)};",
        source_block(WIDGETS_SCRIPT, "function", "channelKey"),
        source_block(WIDGETS_SCRIPT, "const", "pageStorage"),
        *(source_block(PAGE_SCRIPT, "const", name) for name in PAGE_CONSTANTS),
        *(source_block(PAGE_SCRIPT, "function", name) for name in PAGE_FUNCTIONS),
        script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


def test_the_first_test_load_copies_the_regular_settings_in_the_newer_format_and_never_writes_back() -> None:
    found = run("test", REGULAR, """
const copied = copyRegularChannelSettings();
console.log(JSON.stringify({ copied, writes, store: Object.fromEntries(store), presets: readCustomPresets(),
                             settings: loadPlayerSettings() }));""")
    assert sorted(found["copied"]) == sorted(REGULAR)
    assert all(key.startswith(PREFIX) for key in found["writes"])                   # never a regular key
    assert {key: found["store"][key] for key in REGULAR} == REGULAR                 # the regular keys as they were
    presets = found["presets"]                                                      # eight slots, ZORA flags in each
    assert len(presets) == 8 and presets[0]["zoraFlags"] == "4.T9Jvg" and presets[2] == {
        "name": "Old", "flags": "BBBB", "zoraFlags": ""}
    settings = found["settings"]
    assert settings["music"] == "off" and settings["greenTunic"] == 0x2A
    assert "statisticsScreen" not in settings and settings["heart"] == 0x16        # retired key gone; $0D refused
    assert json.loads(found["store"][PREFIX + "zora-player-settings"]) == settings
    assert found["store"][PREFIX + "zora.playerName"] == "Tester"
    assert found["store"][PREFIX + "zora-theme"] == "dark" and found["store"][PREFIX + "zora-tab"] == "flags"


def test_the_copy_happens_once_and_never_over_the_test_pages_own_settings() -> None:
    """A second load copies nothing, even after the regular page changed; a setting the test page
    already has is never replaced."""
    found = run("test", {**REGULAR, PREFIX + "zora-theme": "light"}, """
const first = copyRegularChannelSettings();
store.set("zora.playerName", "Changed later");
const second = copyRegularChannelSettings();
console.log(JSON.stringify({ first, second, theme: store.get("zora-test:zora-theme"),
                             name: store.get("zora-test:zora.playerName") }));""")
    assert "zora-theme" not in found["first"] and found["second"] == []
    assert found["theme"] == "light" and found["name"] == "Tester"


def test_each_channel_reads_and_writes_only_its_own_keys() -> None:
    """The test page's saves land behind the prefix and leave the regular page's alone; the regular
    page's saves land on the plain keys, copy nothing, and never touch the test page's."""
    on_test = run("test", REGULAR, """
copyRegularChannelSettings();
writeCustomPresets([{ name: "Test", flags: "TTTT", zoraFlags: "" }]);
pageStorage.setItem(PLAYER_NAME_KEY, "Test name");
console.log(JSON.stringify(Object.fromEntries(store)));""")
    assert on_test["zora.customPresets"] == REGULAR["zora.customPresets"]
    assert on_test["zora.playerName"] == "Tester"
    assert json.loads(on_test[PREFIX + "zora.customPresets"])[0]["name"] == "Test"
    assert on_test[PREFIX + "zora.playerName"] == "Test name"
    on_regular = run("regular", {PREFIX + "zora.playerName": "Test name"}, """
const copied = copyRegularChannelSettings();
pageStorage.setItem(PLAYER_NAME_KEY, "Regular name");
console.log(JSON.stringify({ copied, writes, store: Object.fromEntries(store) }));""")
    assert on_regular["copied"] == [] and on_regular["writes"] == ["zora.playerName"]
    assert on_regular["store"] == {PREFIX + "zora.playerName": "Test name", "zora.playerName": "Regular name"}


def test_an_unreadable_regular_value_is_left_and_the_rest_copied() -> None:
    found = run("test", {**REGULAR, "zora.customPresets": "{not json"}, """
const copied = copyRegularChannelSettings();
console.log(JSON.stringify({ copied, store: Object.fromEntries(store) }));""")
    assert "zora.customPresets" not in found["copied"] and PREFIX + "zora.customPresets" not in found["store"]
    assert "zora-player-settings" in found["copied"]
