"""Loading an Archipelago YAML on the Multiworld tab (2026-11-21, a player's request): the page's own reader
(web/zora-web.js parseSettingsYaml, lenient) parses the file in the browser, and zora_web.multiworld.read_yaml
turns its options, name, player settings and DeathLink back into the page's, best effort. A YAML the page
exported loads back to the same page values; whatever can't be applied (an unknown key, a value not offered, a
setting Archipelago leaves out, a line that can't be read) is listed and the rest still loads; a hand-edited
YAML works."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from zora import archipelago
from zora.flags import codec, zora_flags
from zora.flags import form as flag_form
from zora.rom.player_settings import player_settings_from_page
from zora_web import multiworld

REPO = Path(__file__).resolve().parent.parent
PAGE = (REPO / "web" / "index.html").read_text()
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
WORKER = (REPO / "web" / "zora-worker.js").read_text()
DEFAULT_FLAGS = flag_form.metadata()["defaultFlags"]
NAME = "Tetra"


def page_function(name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def page_constant(name: str) -> str:
    match = re.search(rf"^const {name} = .*?;(?=\s*(?://.*)?$)", PAGE_SCRIPT, re.MULTILINE)
    assert match, name
    return match.group(0)


READER = "\n".join([*(page_constant(name) for name in ("NOT_A_SETTINGS_FILE", "YAML_KEY")),
                    "class SettingsFileError extends Error {}", page_function("parseSettingsYaml")])


def parse(text: str) -> tuple[Any, list[str]]:
    """The page's lenient reading of TEXT, in Node: what it read and the lines it could not."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (f"{READER}\nconst problems = [];\nconst parsed = parseSettingsYaml({json.dumps(text)}, problems);\n"
              "console.log(JSON.stringify({ parsed, problems }));")
    done = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
    return done["parsed"], done["problems"]


def load(text: str) -> dict[str, Any]:
    """The page's load of TEXT: its reader, then read_yaml; the reader's problems first."""
    parsed, problems = parse(text)
    answer = multiworld.read_yaml(parsed)
    return {**answer, "problems": problems + answer["problems"]}


def exportable_presets() -> list[dict[str, Any]]:
    """The page's presets whose settings Archipelago takes (others are refused at export)."""
    presets = flag_form.metadata()["presets"]
    return [preset for preset in presets
            if multiworld.check(preset["flags"], preset.get("zoraFlags") or "", {})["ok"]]


CASES: dict[str, tuple[str, str, dict[str, Any]]] = {
    "defaults": (DEFAULT_FLAGS, "", {}),
    "player settings": (DEFAULT_FLAGS, "", {"selectButton": "swap", "lowHealthBeep": "kept", "deathWarp": "p2-up-a",
                                            "greenTunic": 0x1A, "heart": 0x30, "levelWord": "LAIR",
                                            "bossSoundWord": "RANDOM", "itemArrivalSound": "none",
                                            "deathLink": "on"}),
    **{f"preset {preset['label']}": (preset["flags"], preset.get("zoraFlags") or "", {})
       for preset in exportable_presets()[:6]},
}


def test_several_presets_are_exported() -> None:
    assert len([case for case in CASES if case.startswith("preset")]) >= 3


@pytest.mark.parametrize("case", CASES)
def test_an_exported_yaml_loads_back_to_the_same_page_values(case: str) -> None:
    flag_string, zora_flag_string, settings = CASES[case]
    exported = multiworld.export_yaml(NAME, flag_string, zora_flag_string, settings)["yaml"]
    parsed, problems = parse(exported)
    assert problems == [] and parsed == yaml.safe_load(exported)      # the page reads it as YAML does
    loaded = load(exported)
    assert loaded["loaded"] and loaded["problems"] == [] and loaded["name"] == NAME
    # The same flag strings the YAML stands for (the page's, with what Archipelago never offers at its value)
    expected = archipelago.flag_strings(multiworld.option_values(flag_string, zora_flag_string))
    assert (loaded["flags"], loaded["zoraFlags"]) == expected
    assert (codec.canonicalize(loaded["flags"]), zora_flags.encode(zora_flags.decode(loaded["zoraFlags"]))) == expected
    # Every player setting named; the page's own values, DeathLink among them
    death_link = loaded["playerSettings"].pop(multiworld.DEATH_LINK_KEY)
    assert death_link == settings.get(multiworld.DEATH_LINK_KEY, "off")
    page = {key: value for key, value in settings.items() if key != multiworld.DEATH_LINK_KEY}
    assert loaded["playerSettings"].items() >= page.items()
    defaults = {spec.key: spec.default for spec in archipelago.player_setting_fields()}
    assert player_settings_from_page(loaded["playerSettings"]) == player_settings_from_page(defaults | page)


def test_the_flag_strings_ride_along_as_comments() -> None:
    """The exported YAML names both flag strings at the top, to paste into the page's boxes; the reader skips them."""
    flags, zora = archipelago.flag_strings({"progressive_items": "on", "extra_candles": "off"})
    text = multiworld.export_yaml(NAME, flags, zora, {})["yaml"]
    assert f"# Z1R flags: {flags}\n" in text and f"# ZORA flags: {zora}\n" in text
    assert text.index("# Z1R flags") < text.index("name:")
    assert (load(text)["flags"], load(text)["zoraFlags"]) == (flags, zora)


def test_problems_are_listed_and_the_rest_still_loads() -> None:
    text = multiworld.export_yaml(NAME, DEFAULT_FLAGS, "", {"levelWord": "LAIR"})["yaml"]
    text = text.replace('  swords: "normal"', '  swords: "swordless"')                      # kept out of Archipelago
    text = text.replace('  dungeon_quest: "shapes"', '  dungeon_quest: "second_quest"')     # loads
    text = text.replace('  item_counter: "off"', '  item_counter: "on"')                      # a beta value: loads
    text += '  mystery_option: "yes"\n  shuffle_wood_sword: "off"\n'
    text += "requires:\n  version: 0.6.8\n"
    loaded = load(text)
    assert loaded["loaded"] and loaded["name"] == NAME
    problems = loaded["problems"]
    assert any(line.startswith('ZORA: swords: "swordless" is not offered') for line in problems), problems
    assert any(line.startswith("ZORA: mystery_option: not a setting this page knows") for line in problems)
    assert any(line.startswith("ZORA: shuffle_wood_sword: Shuffle Wood Sword: it is not on the Multiworld tab")
               for line in problems)
    assert any(line.startswith("requires: not a ZORA setting") for line in problems)
    assert len(problems) == 4
    # Item Counter loads (a beta value since 2.0.2: the page turns Enable Beta Flags on)
    # the page's export names Triforce Shuffle and Map & Compass Shuffle Off (Archipelago's default is Anywhere)
    expected = archipelago.flag_strings({"dungeon_quest": "second_quest", "item_counter": "on",
                                         "triforce_shuffle": "off", "map_compass_shuffle": "off"})
    assert (loaded["flags"], loaded["zoraFlags"]) == expected
    assert loaded["playerSettings"]["levelWord"] == "LAIR"


HAND_EDITED = """\
# my settings
name: Kai   # a comment after the name
game: ZORA
ZORA:
  dungeon_quest: Second_Quest
  progressive_items: true
  extra_candles: off
  universal_drops_v2:
    on: 50
    off: 0
  harder_ganon:
    level_1: 10
    level_2: 10
  green_tunic: 0x2A
  level_word: lair
  death_link: true
  this line is not yaml
\tbossy: tab
  hearts: "0x99"
  cave_shuffle: random
"""


def test_a_hand_edited_yaml_loads() -> None:
    """Unquoted values in any case, YAML's true and false, a weighted choice that can draw only one value, an
    unquoted color; a line that can't be read, a tab, a bad color, a two-way weight and Archipelago's random
    are each named, and the rest loads. A beta value loads too: the page then turns Enable Beta Flags on."""
    loaded = load(HAND_EDITED)
    assert loaded["loaded"] and loaded["name"] == "Kai"
    values = {"dungeon_quest": "second_quest", "progressive_items": "on", "extra_candles": "off",
              "universal_drops_v2": "on"}
    assert (loaded["flags"], loaded["zoraFlags"]) == archipelago.flag_strings(values)
    assert loaded["playerSettings"] == {"greenTunic": 0x2A, "levelWord": "LAIR", multiworld.DEATH_LINK_KEY: "on"}
    problems = loaded["problems"]
    assert "Line 17: expected name: value." in problems
    assert "Line 18: YAML can't be indented with tabs." in problems
    assert any(line.startswith("ZORA: harder_ganon: ") and "weighted" in line for line in problems)
    assert any(line.startswith("ZORA: hearts: ") and "is unchanged" in line for line in problems)
    assert any(line.startswith("ZORA: cave_shuffle: random: Archipelago picks a value") for line in problems)
    assert len(problems) == 5


def test_a_file_with_no_zora_block_loads_nothing() -> None:
    for text in ("", "name: Kai\ngame: Other\n", "- 1\n- 2\n"):
        loaded = load(text)
        assert loaded == {"loaded": False, "problems": [multiworld.NOT_A_YAML]}


def test_the_strict_reader_is_unchanged() -> None:
    """Without a problems list (a settings file) the first bad line still refuses the file."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (f"{READER}\ntry {{ parseSettingsYaml('a: 1\\nnot yaml\\n'); console.log('read'); }}\n"
              "catch (err) { console.log(err.message); }")
    done = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout.strip()
    assert done == "Line 2: expected name: value."


def test_the_page_and_worker_wire_the_load() -> None:
    """The button on the Multiworld tab, the page's reader with a problems list, the worker's glue, and the
    report kept across the reload the load makes (applyPageSettings, as a settings file)."""
    assert re.search(r'<div class="yaml-load multiworld-only" id="yaml-load-row" hidden>', PAGE)
    assert ">Load an Archipelago YAML</button>" in PAGE
    loader = page_function("loadArchipelagoYaml")
    assert "parseSettingsYaml(await file.text(), problems)" in loader
    assert "applyPageSettings(settings)" in loader and "mode: MULTIWORLD" in loader
    assert 'type === "readArchipelagoYaml"' in WORKER
    glue = re.search(r"const GLUE = `\n(.*?)`;", WORKER, re.DOTALL)
    assert glue
    names: dict[str, Any] = {}
    exec(glue.group(1), names)
    text = multiworld.export_yaml(NAME, DEFAULT_FLAGS, "", {})["yaml"]
    assert json.loads(names["read_archipelago_yaml"](json.dumps(yaml.safe_load(text)))) == json.loads(
        json.dumps(multiworld.read_yaml(yaml.safe_load(text))))


def test_the_renamed_level_item_keys_still_load() -> None:
    """2.0.2's test builds' add_triforces_to_pool and add_maps_compasses_to_pool: on is Anywhere, off is Off, each
    with a note naming the new key."""
    text = multiworld.export_yaml(NAME, DEFAULT_FLAGS, "", {})["yaml"]
    text = text.replace('  triforce_shuffle: "off"\n', "").replace('  map_compass_shuffle: "off"\n', "")
    text += "  add_triforces_to_pool: true\n  add_maps_compasses_to_pool: off\n"
    loaded = load(text)
    zora = zora_flags.decode(loaded["zoraFlags"])
    assert (zora.triforce_shuffle, zora.map_compass_shuffle) == (zora_flags.LevelItemShuffle.ANYWHERE,
                                                                 zora_flags.LevelItemShuffle.OFF)
    notes = [line for line in loaded["problems"] if "was renamed" in line]
    assert len(notes) == 2 and "triforce_shuffle" in notes[0] and "Anywhere" in notes[0], notes
