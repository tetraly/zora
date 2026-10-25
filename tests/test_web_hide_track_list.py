"""Hide track list (web/zora-web.js MUSIC_CHOICES and musicResult; TheGobOne's request for beta 9): a
page-only switch, off by default. On, the result's Music entry shows a button instead of the tracks
and the warnings (which can name tracks), and the button shows them; the copy buttons' texts never
carry tracks either way, and the ROM is the same (Python never reads the switch). The page's own
code, run in Node on a stand-in for the few DOM calls it makes."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from zora.rom.player_settings import player_settings_from_page

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
SWITCH = "musicHideTrackList"
RESULT = {"tracks": [["Title screen", "Song A"], ["Overworld", "Song B"]],
          "musicWarnings": ["Level 2: Song A is not tagged for this area"],
          "musicLibraries": [["mine.json5", "0123abcd"]]}
# A stand-in DOM: elements with children, text, listeners, prepend and replaceWith.
DOM = """
class FakeElement {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.parent = null; }
  append(...nodes) { for (const node of nodes) { node.parent = this; this.children.push(node); } }
  prepend(...nodes) { for (const node of nodes) node.parent = this; this.children.unshift(...nodes); }
  addEventListener(type, listener) { this.listeners[type] = listener; }
  replaceWith(node) { const siblings = this.parent.children; node.parent = this.parent;
                      siblings[siblings.indexOf(this)] = node; }
  remove() { const siblings = this.parent.children; siblings.splice(siblings.indexOf(this), 1); }
  get text() { return [this.textContent || "", ...this.children.map((child) => child.text)].join("|"); }
  find(id) { return this.id === id ? this : this.children.map((child) => child.find(id)).find(Boolean); }
}
const document = { createElement: (tag) => new FakeElement(tag) };
"""


def page_block(kind: str, name: str) -> str:
    pattern = rf"^const {name} = .*?^\];$" if kind == "const" else rf"^(?:async )?function {name}\(.*?^}}$"
    match = re.search(pattern, PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def run_page(script: str) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = "\n".join([DOM, page_block("function", "element"), page_block("function", "musicResult"), script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


def shown(hidden: bool) -> dict[str, str]:
    result: dict[str, str] = run_page(f"""
const music = musicResult({json.dumps(RESULT)}, {json.dumps(hidden)});
const before = music.text;
const button = music.find("show-music-tracks");
if (button) button.listeners.click();
console.log(JSON.stringify({{ before, after: music.text, button: button ? button.textContent : "" }}));""")
    return result


def test_the_switch_is_off_by_default_and_page_only() -> None:
    assert re.search(rf'key: "{SWITCH}", label: "Hide track list", default: "off"', PAGE_SCRIPT)
    assert SWITCH in page_block("const", "MUSIC_CHOICES")
    for value in ("on", "off"):          # Python never reads it: the same player settings, the same ROM
        assert player_settings_from_page({"music": "random-standard", SWITCH: value}) == \
            player_settings_from_page({"music": "random-standard"})


def test_off_the_tracks_show_as_before() -> None:
    result = shown(hidden=False)
    assert "Title screen: Song A" in result["before"] and "Level 2: Song A" in result["before"]
    assert "mine.json5 (0123abcd)" in result["before"] and not result["button"]


def test_on_a_button_shows_the_tracks_when_asked() -> None:
    result = shown(hidden=True)
    assert "Song A" not in result["before"] and "Song B" not in result["before"]
    assert result["button"] == "Show track list" and "mine.json5 (0123abcd)" in result["before"]
    assert "Title screen: Song A" in result["after"] and "Overworld: Song B" in result["after"]
    assert "Level 2: Song A is not tagged" in result["after"] and "Show track list" not in result["after"]
    assert "Track list hidden" in result["before"] and "hidden" not in result["after"]


def test_the_copy_texts_never_carry_tracks() -> None:
    for name in ("bugReportText", "raceInfoText"):
        assert "track" not in page_block("function", name)
    copy_info = re.search(r"addCopyButtons\(\{.*?\}\);", page_block("function", "onGenerate"), re.DOTALL)
    assert copy_info and "track" not in copy_info.group(0)
    assert "hideTracks" in page_block("function", "onGenerate")
