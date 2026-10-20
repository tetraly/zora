"""The web page's settings file (web/zora-web.js; owner, 2026-10-17): everything the page remembers as
one YAML file, loaded in another browser or after clearing site data. The page writes it, reads it
back, reads the same saved again by another YAML tool, refuses a newer format with a clear message,
and keeps reading format 1 (FORMAT_1_FILE, as the page wrote it on 2026-10-17: never change it)."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()

SETTINGS: dict[str, Any] = {
    "zora_page_settings": 1,
    "saved_by": "ZORA v2.0 beta 6 2026-10-17 f21cf91",
    "mode": "single",
    "flags": "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A",
    "zora_flags": "",
    "player_settings": {"selectButton": "toggle", "greenTunic": 41, "levelWord": "LAIR", "bossSoundWord": "ROAR"},
    "custom_presets": [{"name": "Race: \"fast\" # 1", "flags": "AAAA?!", "zoraFlags": "B"}, None,
                       {"name": "Ünïcode 'quoted'", "flags": "CCCC", "zoraFlags": ""}, None, None, None, None, None],
    "player_name": "Link",
    "theme": "dark",
    "open_tab": None,
}
FORMAT_1_FILE = """\
# ZORA settings: load this file in ZORA's Presets window (Load a file).
# It holds your flags, mode, cosmetic settings, presets, player name and theme.
zora_page_settings: 1
saved_by: "ZORA v2.0 beta 6 2026-10-17 f21cf91"
mode: "multiworld"
flags: "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A"
zora_flags: "AB"
player_settings:
  selectButton: "swap"
  lowHealthBeep: "removed"
  deathWarp: "p1-up-a"
  reduceFlashing: "off"
  music: "on"
  greenTunic: 41
  blueRingTunic: 50
  redRingTunic: 22
  heart: 22
  levelWord: "LEVEL"
  bossSoundWord: "ROAR"
custom_presets:
  - name: "Mine"
    flags: "AAAA"
    zoraFlags: "B"
  - null
  - null
  - null
  - null
  - null
  - null
  - null
player_name: "Link"
theme: null
open_tab: "tab-items"
"""


def page_function(name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def page_constant(name: str) -> str:
    match = re.search(rf"^const {name} = .*?;(?=\s*(?://.*)?$)", PAGE_SCRIPT, re.MULTILINE)
    assert match, name
    return match.group(0)


PAGE_PIECES = "\n".join([
    "const SINGLE = 'single', MULTIWORLD = 'multiworld';",
    *(page_constant(name) for name in ("SETTINGS_FORMAT_KEY", "SETTINGS_FORMAT", "THEMES", "NOT_A_SETTINGS_FILE",
                                       "YAML_KEY")),
    "class SettingsFileError extends Error {}",
    *(page_function(name) for name in ("yamlScalar", "settingsYaml", "parseSettingsYaml", "checkedPageSettings")),
])


def run_page(script: str) -> Any:
    """SCRIPT's printed JSON, with the page's settings-file functions defined (run in Node). A
    SettingsFileError prints {"refused": message}."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = (f"{PAGE_PIECES}\ntry {{ console.log(JSON.stringify(({script}))); }} catch (err) {{\n"
              "  if (!(err instanceof SettingsFileError)) throw err;\n"
              "  console.log(JSON.stringify({ refused: err.message })); }")
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


def read(text: str) -> Any:
    return run_page(f"checkedPageSettings(parseSettingsYaml({json.dumps(text)}))")


def test_the_page_reads_back_what_it_writes_and_it_is_yaml() -> None:
    written = run_page(f"settingsYaml({json.dumps(SETTINGS)})")
    assert written.startswith("# ZORA settings: load this file")
    assert read(written) == SETTINGS
    assert yaml.safe_load(written) == SETTINGS


def test_format_1_is_read() -> None:
    """A file from 2026-10-17's page, whatever the page writes later."""
    settings = read(FORMAT_1_FILE)
    assert settings == yaml.safe_load(FORMAT_1_FILE)
    assert (settings["mode"], settings["zora_flags"], settings["custom_presets"][0]["name"]) == ("multiworld", "AB", "Mine")


def test_the_same_saved_again_by_another_yaml_tool_is_read() -> None:
    """PyYAML's own style: plain and single-quoted values, lists at the key's indentation."""
    again = yaml.safe_dump(SETTINGS, sort_keys=False, allow_unicode=True)
    assert "- name:" in again and "'" in again
    assert read(again) == SETTINGS


def test_hand_edits_are_read() -> None:
    edited = FORMAT_1_FILE.replace('mode: "multiworld"', "mode: single   # back to one player").replace(
        "  greenTunic: 41", "  greenTunic: 0x2A").replace('theme: null', "theme:")
    settings = read(edited)
    assert (settings["mode"], settings["player_settings"]["greenTunic"], settings["theme"]) == ("single", 0x2A, None)


def test_a_newer_format_is_refused_with_a_clear_message() -> None:
    newer = FORMAT_1_FILE.replace("zora_page_settings: 1", "zora_page_settings: 2")
    assert read(newer) == {"refused": "This file was saved by a newer ZORA page (ZORA v2.0 beta 6 2026-10-17 "
                                      "f21cf91), in settings format 2. This page reads format 1 and older: load the "
                                      "file on the newer page, or use a newer ZORA."}


@pytest.mark.parametrize(("text", "refusal"), [
    ("name: Link\n", "This isn't a ZORA settings file: it has no zora_page_settings line."),
    ("", "This isn't a ZORA settings file: it has no zora_page_settings line."),
    ("- 1\n- 2\n", "This isn't a ZORA settings file: it has no zora_page_settings line."),
    ("zora_page_settings: one\n", 'zora_page_settings must be a whole number from 1, not "one".'),
    ("zora_page_settings: 1\nmode: solo\n", "mode must be single or multiworld."),
    ("zora_page_settings: 1\ntheme: blue\n", "theme must be light or dark."),
    ("zora_page_settings: 1\nflags: 1234\n", "flags must be text."),
    ("zora_page_settings: 1\ncustom_presets: none\n", "custom_presets must be a list of presets."),
    ("zora_page_settings: 1\nmode: single\nmode: multiworld\n", "Line 3: mode appears twice."),
    ("zora_page_settings: 1\n\tmode: single\n", "Line 2: YAML can't be indented with tabs."),
    ("zora_page_settings: 1\njust some words\n", "Line 2: expected name: value."),
    ('zora_page_settings: 1\nflags: "AB" CD\n', "Line 2: text after the closing quote."),
    ("zora_page_settings: 1\n  mode: single\n", "Line 2: unexpected indentation."),
])
def test_what_is_refused(text: str, refusal: str) -> None:
    assert read(text) == {"refused": refusal}


def test_loading_keeps_each_part_and_opens_the_page_on_the_files_flags_and_mode() -> None:
    """applyPageSettings: each remembered part into this browser's storage (checked again where the
    page reads it), the address as a shared link names the flags and mode; a part the file leaves out
    keeps this page's own."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    keys = ("PLAYER_SETTINGS_KEY", "CUSTOM_PRESETS_KEY", "PLAYER_NAME_KEY", "THEME_KEY", "TAB_KEY",
            "LINK_FLAGS", "LINK_ZORA_FLAGS", "LINK_MODE", "LINK_SEED")
    source = "\n".join([
        PAGE_PIECES, *(page_constant(name) for name in keys),
        "const store = new Map(); const localStorage = { setItem: (k, v) => store.set(k, v) };",
        "const pageStorage = localStorage;     // the regular channel's keys (web/widgets.js)",
        "const location = { pathname: '/zora.html', search: '?pyodide=local&seed=5', hash: '' };",
        "const form = { flags: 'PAGEFLAGS', zora: { ok: true, flags: 'PZ' } }; const mode = 'single';",
        "const metadata = { defaultFlags: 'DEFAULT' };",
        page_function("linkSearch"), page_function("applyPageSettings"),
        f"const full = applyPageSettings(checkedPageSettings(parseSettingsYaml({json.dumps(FORMAT_1_FILE)})));",
        "const fullStore = Object.fromEntries(store); store.clear();",
        "const partial = applyPageSettings({ zora_page_settings: 1, theme: 'light' });",
        "console.log(JSON.stringify({ full, fullStore, partial, partialStore: Object.fromEntries(store) }));",
    ])
    done = json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)
    file = yaml.safe_load(FORMAT_1_FILE)
    assert done["full"] == "/zora.html?pyodide=local&flags=8hq4BeR1JXo89BJ2%21TFpTP02u8UJ3A&zora=AB&mode=multiworld"
    assert done["fullStore"] == {"zora-player-settings": json.dumps(file["player_settings"], separators=(",", ":")),
                                 "zora.customPresets": json.dumps(file["custom_presets"], separators=(",", ":")),
                                 "zora.playerName": "Link", "zora-tab": "tab-items"}
    assert done["partial"] == "/zora.html?pyodide=local&flags=PAGEFLAGS&zora=PZ&mode=single"
    assert done["partialStore"] == {"zora-theme": "light"}
