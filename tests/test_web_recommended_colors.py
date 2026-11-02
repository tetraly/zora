"""The page's recommended colors (web/zora-web.js, beta 11 player feedback, 2026-10-30): "Use recommended
colors" makes all five of a set's colors the player's own (its three tunic colors and its two other
colors, whether its color 1 is clothing or art), so Playable character's colors reads My own and the
ROM gets every color as the set was drawn; each recommended color is labeled in text with its NES
palette value and a plain name. The page's own code, run in Node."""
import json
import re
import shutil
import subprocess
from typing import Any

import pytest

from tests.test_web_channel_storage import (
    PAGE_CONSTANTS,
    PAGE_FUNCTIONS,
    PAGE_SCRIPT,
    WIDGET_CONSTANTS,
    WIDGETS_SCRIPT,
    source_block,
)
from zora.flags.form import metadata
from zora.rom.player_settings import CharacterColors, player_settings_from_page, shown_link_colors

LABEL_CONSTANTS = ["LINK_SPRITE_BUILT_IN", "NES_HUE_NAMES", "NES_ROW_SHADES", "NES_NAMED_COLORS", "NES_HUE_MASK",
                   "NES_ROW_SHIFT", "NES_FIRST_BLACK_COLUMN"]
LABEL_FUNCTIONS = ["paletteValue", "nesColorName", "nesColorLabel", "recommendedColorSettings"]
BUILT_IN_CHOICE = re.search(r'^const LINK_SPRITE_BUILT_IN = ("[^"]*");', PAGE_SCRIPT, re.MULTILINE)
assert BUILT_IN_CHOICE
LINK_SPRITE_BUILT_IN = json.loads(BUILT_IN_CHOICE[1])
FIVE_SLOTS = ["greenTunic", "blueRingTunic", "redRingTunic", "linkColor2", "linkColor3"]


def run(script: str, stored: dict[str, str] | None = None) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = "\n".join([
        "const store = new Map(Object.entries(" + json.dumps(stored or {}) + "));",
        "const localStorage = { getItem: (k) => store.has(k) ? store.get(k) : null,",
        "  setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) };",
        *(source_block(WIDGETS_SCRIPT, "const", name) for name in WIDGET_CONSTANTS),
        'const PAGE_CHANNEL = "regular";',
        source_block(WIDGETS_SCRIPT, "function", "channelKey"),
        source_block(WIDGETS_SCRIPT, "const", "pageStorage"),
        *(source_block(PAGE_SCRIPT, "const", name) for name in PAGE_CONSTANTS + LABEL_CONSTANTS),
        *(source_block(PAGE_SCRIPT, "function", name) for name in PAGE_FUNCTIONS + LABEL_FUNCTIONS),
        script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


def offered_sets() -> dict[str, dict[str, Any]]:
    """The built-in sets the page is offered that carry recommended colors."""
    return {entry["id"]: entry for entry in metadata()["linkSpriteSet"]["builtIn"] if "recommendedColors" in entry}


@pytest.mark.parametrize("set_id, color_one", [("zeromeaning-link-female", "clothing"), ("zeromeaning-samus", "art")])
def test_the_button_sets_all_five_colors(set_id: str, color_one: str) -> None:
    """For a clothing set and an art set: the five color settings take the set's values and the choice
    reads My own, which the saved settings keep and the ROM writer applies as every color the set has."""
    entry = offered_sets()[set_id]
    recommended = entry["recommendedColors"]
    assert recommended.get("colorOne", "clothing") == color_one
    settings = run(f"""
const settings = {{ ...defaultPlayerSettings(), linkSprite: "{LINK_SPRITE_BUILT_IN}{set_id}" }};
Object.assign(settings, recommendedColorSettings({json.dumps(recommended)}));
const reloaded = checkedPlayerSettings(JSON.parse(JSON.stringify(settings)));
console.log(JSON.stringify({{ applied: settings, reloaded }}));""")
    expected = [*recommended["tunics"], *recommended["other"]]
    for name in ("applied", "reloaded"):
        assert [settings[name][key] for key in FIVE_SLOTS] == expected, name
        assert settings[name]["characterColors"] == "mine", name
    page = {**settings["reloaded"], "linkSprite": "set", "linkSpriteSet": entry}
    sent = [*FIVE_SLOTS, "linkSprite", "linkSpriteSet", "characterColors"]
    page = {key: value for key, value in page.items() if key in sent}
    player = player_settings_from_page(page)
    assert player.character_colors is CharacterColors.MINE
    assert shown_link_colors(player) == (tuple(recommended["tunics"]), tuple(recommended["other"]))


def test_the_labels_name_each_sets_recommended_values() -> None:
    sets = offered_sets()
    colors = {set_id: [*entry["recommendedColors"]["tunics"], *entry["recommendedColors"]["other"]]
              for set_id, entry in sets.items()}
    labels = run(f"const sets = {json.dumps(colors)};\n"
                 "console.log(JSON.stringify(Object.fromEntries(Object.entries(sets).map(([id, values]) => "
                 "[id, values.map(nesColorLabel)]))));")
    assert len(labels) >= 20
    for set_id, values in colors.items():
        assert [label.split(" ")[0] for label in labels[set_id]] == [f"${value:02X}" for value in values], set_id
        assert all(re.fullmatch(r"\$[0-9A-F]{2} [a-z]+( [a-z]+)*", label) for label in labels[set_id]), set_id
    # Each row's shade of a plain hue, the named colors that are not one, and the blacks (no shade).
    named = {0x06: "dark red", 0x16: "red", 0x27: "light orange", 0x38: "pale yellow", 0x2A: "light green",
             0x0C: "dark cyan", 0x32: "lavender", 0x18: "olive", 0x17: "brown", 0x30: "white", 0x1C: "teal",
             0x00: "dark gray", 0x0F: "black", 0x3E: "black"}
    labels = run(f"console.log(JSON.stringify({json.dumps(list(named))}.map(nesColorLabel)));")
    assert labels == [f"${color:02X} {name}" for color, name in named.items()]
    every = run("console.log(JSON.stringify(Array.from({ length: 64 }, (_, color) => nesColorName(color))));")
    assert all(re.fullmatch(r"[a-z]+( [a-z]+)*", name) for name in every)
    assert every[0x2A] != every[0x1A] != every[0x0A]          # a hue's rows read apart


def test_the_button_shows_only_with_a_sets_recommended_colors() -> None:
    """Built in the set's branch with recommended colors; Random (no set) returns before it."""
    start = PAGE_SCRIPT.index("function showLinkSpriteInfo(")
    body = PAGE_SCRIPT[start:PAGE_SCRIPT.index("\n}\n", start)]
    random = body.index("if (!set) {")
    assert random < body.index("return;", random) < body.index("if (recommended) {") \
        < body.index('"Use recommended colors"')


@pytest.mark.parametrize("saved, colors", [
    ({"music": "off", "greenTunic": 0x2A}, "mine"),                  # before the choice, a tunic of its own
    ({"music": "off", "linkSprite": "link"}, "set"),                 # before the choice, the game's colors
    ({"characterColors": "set", "linkColor2": 0x30}, "set"),         # after it
    ({"characterColors": "bogus", "greenTunic": 0x0D}, "set"),       # unknown, and a color not allowed
])
def test_old_saved_settings_still_load(saved: dict[str, Any], colors: str) -> None:
    settings = run("console.log(JSON.stringify(loadPlayerSettings()));",
                   {"zora-player-settings": json.dumps(saved)})
    assert settings["characterColors"] == colors
    assert set(FIVE_SLOTS) <= set(settings)
