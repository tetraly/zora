"""The web page's single player / multiworld toggle (web/index.html, web/zora-web.js,
zora_web/multiworld.py): single-player mode unchanged; multiworld mode's Archipelago YAML, which
reads back to the page's choices; values Archipelago does not offer refused; the player name; and
the mode and both flag strings in a shared link."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from zora import archipelago
from zora.flags import codec, zora_flags, zora_form
from zora.flags import form as flag_form
from zora.flags.fields import ThreeState
from zora.rom.player_settings import player_settings_from_page
from zora_web import multiworld

REPO = Path(__file__).resolve().parent.parent
PAGE = (REPO / "web" / "index.html").read_text()
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
WORKER = (REPO / "web" / "zora-worker.js").read_text()
DEFAULT_FLAGS = flag_form.metadata()["defaultFlags"]
NAME = "Tetra"

ITEM_SHUFFLE, ENCODE_LEVEL_DATA, DUNGEON_QUEST, EXTRA_CANDLES, SWORDS = "C06", "B82", "C02", "B09", "C07"
SWORDLESS = 3                            # Swords: Swordless (C07 = 3), held back: Archipelago's player starts with a sword
ITEM_ONLY = 1                            # Item Shuffle: Item Only (C06 = 1)


def flags_with(options: dict[str, int] | None = None, toggles: dict[str, ThreeState] | None = None) -> str:
    """The page's default string with some fields changed, canonical."""
    return codec.encode(codec.decode(DEFAULT_FLAGS).updated(options=options, toggles=toggles))


def zora_with(**values: int) -> str:
    """A ZORA flag string from the ZORA extras' control values."""
    return zora_flags.encode(zora_flags.decode(zora_form.zora_flags_from_values(values)))


def read_back(text: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """The YAML as Archipelago reads it: its top level, its options and its player settings."""
    document = yaml.safe_load(text)
    block = document[multiworld.GAME]
    setting_keys = {spec.yaml_key for spec in archipelago.player_setting_fields()}
    own = {multiworld.DEATH_LINK_YAML_KEY}                  # Archipelago's own options
    return (document, {key: value for key, value in block.items() if key not in setting_keys | own},
            {key: value for key, value in block.items() if key in setting_keys})


# --- single-player mode unchanged -------------------------------------------------------------------

def test_the_page_starts_in_single_player_mode() -> None:
    """Single player is pressed; the ROM step, the seed and Generate show; the world's step, the
    name and Export are hidden; the script starts in the mode the link names, single by default."""
    assert re.search(r'id="mode-single" aria-pressed="true"', PAGE)
    assert re.search(r'id="mode-multiworld" aria-pressed="false"', PAGE)
    assert re.search(r'<section class="step" id="step-apworld"[^>]* hidden>', PAGE)
    assert re.search(r'<div class="generate-row" id="export-row" hidden>', PAGE)
    assert re.search(r'<div id="export-result" class="result-card" hidden>', PAGE)
    assert re.search(r'<section class="step" id="step-rom"[^>]*>', PAGE)
    assert not re.search(r'id="step-rom"[^>]* hidden', PAGE)
    assert re.search(r'<div class="generate-row" id="generate-row">', PAGE)
    assert "let mode = sharedLink.mode;" in PAGE_SCRIPT
    assert "if (mode === MULTIWORLD) setMode(MULTIWORLD);" in PAGE_SCRIPT


def test_single_player_defaults_and_round_trips_are_unchanged() -> None:
    """The default string and every built-in preset load to themselves, and the link leaves them
    as they are; in single-player mode Archipelago refuses nothing on the page."""
    metadata = flag_form.metadata()
    assert flag_form.form_state(DEFAULT_FLAGS)["flags"] == DEFAULT_FLAGS
    for preset in metadata["presets"]:
        state = flag_form.form_state(preset["flags"], preset.get("zoraFlags") or "")
        assert state["flags"] == preset["flags"]
    defaults = json.dumps(DEFAULT_FLAGS)
    answers = run_page_functions(
        ["validSeed", "linkSettings", "linkSearch", "multiworldReason"],
        f"const metadata = {{multiworld: {json.dumps(multiworld.metadata())}}};\n"
        "let mode = SINGLE;\n"
        f"const presets = {json.dumps(metadata['presets'])};\n"
        "console.log(JSON.stringify({\n"
        "  reasons: Object.keys(metadata.multiworld.offered).concat(Object.keys(metadata.multiworld.fixed))\n"
        "    .map((id) => [0, 1, 2, 3, 4].map((value) => multiworldReason(id, value) ?? null)),\n"
        f"  bare: linkSearch('', {{flags: {defaults}, zoraFlags: '', mode: SINGLE}}, {defaults}),\n"
        "  trips: presets.map((p) => linkSettings(linkSearch('', {flags: p.flags, zoraFlags: p.zoraFlags || '',"
        f" mode: SINGLE}}, {defaults}))),\n"
        "}));")
    assert all(reason is None for values in answers["reasons"] for reason in values)
    assert answers["bare"] == ""
    for preset, trip in zip(metadata["presets"], answers["trips"], strict=True):
        expected = None if preset["flags"] == DEFAULT_FLAGS else preset["flags"]
        assert trip == {"flags": expected, "zoraFlags": preset.get("zoraFlags") or None, "mode": "single",
                        "seed": None}


# --- the YAML --------------------------------------------------------------------------------------

EXPORT_CASES: dict[str, tuple[str, str, dict[str, Any]]] = {
    "defaults": (DEFAULT_FLAGS, "", {}),
    "zora extras": (flags_with(toggles={EXTRA_CANDLES: ThreeState.OFF}),
                    zora_with(progressive_items=1, shop_items_in_pool=1, shuffle_blue_potion=2, add_l4_sword=2),
                    {}),
    "player settings": (DEFAULT_FLAGS, "",
                        {"selectButton": "swap", "lowHealthBeep": "kept", "deathWarp": "p2-up-a",
                         "reduceFlashing": "on", "music": "off", "greenTunic": 0x1A,
                         "blueRingTunic": 0x00, "redRingTunic": 0x3F, "heart": 0x30, "levelWord": "LAIR",
                         "bossSoundWord": "RANDOM"}),
    "typed words": (DEFAULT_FLAGS, "", {"levelWord": "ZQ-7", "bossSoundWord": "BZZT"}),
}


def read_by_archipelago(flag_string: str) -> str:
    """The page's flag string as Archipelago reads it: a magical-sword heart value above 12 read as 12 (owner rule,
    2026-11-23; archipelago.SWORD_HEARTS_CLAMPED). The page's preset asks for up to 14."""
    settings = codec.decode(flag_string)
    specs = {spec.id: spec for spec in archipelago.option_fields()}
    read = {field_id: specs[field_id].read_as(int(settings.options[field_id])) for field_id in ("C22", "C23")}
    return codec.encode(settings.updated(options=read))


# The page's note for its preset's Magical Sword Hearts (max) of 14 (multiworld.sword_hearts_notes)
PRESET_HEARTS_NOTE = ("Magical Sword Hearts (max): 14 is read as 12 in Archipelago: the Magical Sword Cave never asks "
                      "for more than 12 hearts there.")


@pytest.mark.parametrize("case", EXPORT_CASES)
def test_the_yaml_reads_back_to_the_pages_choices(case: str) -> None:
    flag_string, zora_flag_string, settings = EXPORT_CASES[case]
    exported = multiworld.export_yaml(f" {NAME} ", flag_string, zora_flag_string, settings)
    document, options, player_settings = read_back(exported["yaml"])
    assert exported["fileName"] == f"{NAME}.yaml"
    assert {key: document[key] for key in ("name", "game")} == {"name": NAME, "game": multiworld.GAME}
    assert isinstance(document["description"], str)
    # Every option and every player setting named, each value a string (never YAML 1.1's on/off booleans)
    assert list(options) == [spec.key for spec in archipelago.option_fields()]
    assert list(player_settings) == [spec.yaml_key for spec in archipelago.player_setting_fields()]
    assert all(isinstance(value, str) for value in (*options.values(), *player_settings.values()))
    # Options: the same flag strings as the page's, as Archipelago reads them
    assert archipelago.flag_strings(options) == (read_by_archipelago(codec.canonicalize(flag_string)),
                                                zora_flags.encode(zora_flags.decode(zora_flag_string)))
    # Player settings: the page's, every one (a missing one at its default), as the ROM gets them
    defaults = {spec.key: spec.default for spec in archipelago.player_setting_fields()}
    archipelago.check_player_settings(player_settings)
    assert (player_settings_from_page(archipelago.page_player_settings(player_settings))
            == player_settings_from_page(defaults | settings))


def test_the_worker_glue_exports_the_same_yaml() -> None:
    """The worker's Python glue, run here: the metadata, the check, the name and the YAML."""
    glue = re.search(r"const GLUE = `\n(.*?)`;", WORKER, re.DOTALL)
    assert glue
    names: dict[str, Any] = {}
    exec(glue.group(1), names)                   # the page's own glue
    assert json.loads(names["multiworld_metadata"]()) == json.loads(json.dumps(multiworld.metadata()))
    assert json.loads(names["multiworld_check"](DEFAULT_FLAGS, "", "{}")) == {"ok": True, "reasons": [], "notes": [],
                                                                         "beta": [], "ignored": [PRESET_HEARTS_NOTE]}
    assert json.loads(names["player_name_problem"]("")) == "type a player name"
    answer = json.loads(names["export_yaml"](NAME, DEFAULT_FLAGS, "", "{}"))
    assert answer == {"ok": True, **multiworld.export_yaml(NAME, DEFAULT_FLAGS, "", {})}
    refused = json.loads(names["export_yaml"]("", DEFAULT_FLAGS, "", "{}"))
    assert refused == {"ok": False, "reasons": ["Player name: type a player name"]}


def test_the_metadata_is_archipelagos_offer() -> None:
    """Each field's offered values are its option's, the beta ones listed apart (Item Counter was one until
    its logic scan passed, 7192e4c7); no field is held at one value for now (archipelago.NOT_OFFERED_YET is
    empty); the fields off for good are in neither, so the Multiworld tab leaves them out (owner, 2026-11-21)."""
    meta = multiworld.metadata()
    assert meta["offered"] == {spec.id: list(spec.values) for spec in archipelago.option_fields()}
    assert meta["beta"] == {spec.id: list(spec.beta) for spec in archipelago.option_fields() if spec.beta}
    assert meta["fixed"] == {}
    assert "item_counter" not in meta["beta"]
    assert meta["beta"]["universal_drops_v2"] == [ThreeState.ON, ThreeState.POSSIBLE]
    assert (meta["betaTitle"], meta["betaWarning"]) == (archipelago.MULTIWORLD_BETA_TITLE,
                                                        archipelago.MULTIWORLD_BETA_WARNING)
    assert meta["nameMaxLength"] == 16


PERMANENTLY_OFF = {ENCODE_LEVEL_DATA, ITEM_SHUFFLE, "B51", "shuffle_wood_sword", "disable_custom_music",
                   "detailed_spoiler_log", "item_shuffle_no_vanilla"}


def test_the_settings_off_for_good_are_not_on_the_multiworld_tab() -> None:
    """Shuffle Wood Sword, Disable Custom Music, Detailed Spoiler Log, Item Shuffle No Vanilla, Print Quest
    Info, Encode Level Data and Item Shuffle: absent from the tab's data, and the page hides their rows
    (hiddenInMultiworld) in multiworld mode only."""
    meta = multiworld.metadata()
    assert archipelago.PERMANENTLY_OFF == PERMANENTLY_OFF
    assert not PERMANENTLY_OFF & ({*meta["offered"], *meta["fixed"], *meta["beta"]})
    ids = [*PERMANENTLY_OFF, "item_counter", SWORDS]
    answers = run_page_functions(
        ["hiddenInMultiworld"],
        f"const metadata = {{multiworld: {json.dumps(meta)}}};\nlet mode = MULTIWORLD;\n"
        f"const multi = {json.dumps(ids)}.map(hiddenInMultiworld); mode = SINGLE;\n"
        f"console.log(JSON.stringify([multi, {json.dumps(ids)}.map(hiddenInMultiworld)]));")
    assert answers == [[True] * len(PERMANENTLY_OFF) + [False, False], [False] * len(ids)]
    assert re.search(r"\.multiworld-left-out \{ display: none", (REPO / "web" / "zora.css").read_text())


IGNORED_CASES = {
    "Encode level data on": (flags_with(toggles={ENCODE_LEVEL_DATA: ThreeState.ON}), "", "Encode level data: On"),
    "Item Shuffle not Full": (flags_with(options={ITEM_SHUFFLE: ITEM_ONLY}), "", "Item Shuffle: Item Only"),
    "Shuffle Wood Sword on": (DEFAULT_FLAGS, zora_with(shuffle_wood_sword=1), "Shuffle Wood Sword: On"),
}


@pytest.mark.parametrize("case", IGNORED_CASES)
def test_a_value_off_for_good_is_ignored_with_a_note(case: str) -> None:
    """A shared link or settings file may still set one: the YAML leaves it out (the world uses its value), and
    the page's note says so, never a refusal."""
    flag_string, zora_flag_string, named = IGNORED_CASES[case]
    verdict = multiworld.check(flag_string, zora_flag_string, {})
    assert verdict["ok"] and verdict["reasons"] == []
    [note] = [note for note in verdict["ignored"] if note != PRESET_HEARTS_NOTE]
    assert note.startswith(f"{named} in these flags is ignored.")
    text = multiworld.export_yaml(NAME, flag_string, zora_flag_string, {})["yaml"]
    assert text == multiworld.export_yaml(NAME, DEFAULT_FLAGS, "", {})["yaml"]


# --- what cannot be exported --------------------------------------------------------------------------

REFUSED_CASES = {
    "an unoffered value": (flags_with(options={SWORDS: SWORDLESS}), "", "not offered in Archipelago yet"),
    "a conflict": (DEFAULT_FLAGS, zora_with(add_l4_sword=1), "Add L4 Sword needs Progressive Items"),
}


@pytest.mark.parametrize("case", REFUSED_CASES)
def test_values_archipelago_does_not_take_cannot_be_exported(case: str) -> None:
    flag_string, zora_flag_string, named = REFUSED_CASES[case]
    verdict = multiworld.check(flag_string, zora_flag_string, {})
    assert not verdict["ok"]
    assert any(named in reason for reason in verdict["reasons"]), verdict["reasons"]
    with pytest.raises(multiworld.ExportRefused) as refused:
        multiworld.export_yaml(NAME, flag_string, zora_flag_string, {})
    assert refused.value.reasons == verdict["reasons"]


@pytest.mark.parametrize(("page", "written"), [(None, "false"), ("off", "false"), ("on", "true")])
def test_deathlink_is_archipelagos_own_option(page: str | None, written: str) -> None:
    """DeathLink (piece 2) is written last as death_link, a string Archipelago's Toggle reads; it
    is no player setting, so the settings check never sees it."""
    settings = {} if page is None else {multiworld.DEATH_LINK_KEY: page}
    text = multiworld.export_yaml(NAME, DEFAULT_FLAGS, "", settings)["yaml"]
    block = yaml.safe_load(text)[multiworld.GAME]
    assert block[multiworld.DEATH_LINK_YAML_KEY] == written and list(block)[-1] == multiworld.DEATH_LINK_YAML_KEY
    assert multiworld.check(DEFAULT_FLAGS, "", settings)["ok"]
    with pytest.raises(multiworld.ExportRefused, match="DeathLink"):
        multiworld.export_yaml(NAME, DEFAULT_FLAGS, "", {multiworld.DEATH_LINK_KEY: "maybe"})
    assert not multiworld.check(DEFAULT_FLAGS, "", {multiworld.DEATH_LINK_KEY: "maybe"})["ok"]


def test_a_refused_player_setting_cannot_be_exported() -> None:
    verdict = multiworld.check(DEFAULT_FLAGS, "", {"greenTunic": 0x0D})
    assert not verdict["ok"]
    with pytest.raises(multiworld.ExportRefused):
        multiworld.export_yaml(NAME, DEFAULT_FLAGS, "", {"levelWord": "TOOLONGWORD"})


def test_the_pages_offer_disables_what_archipelago_does_not_take() -> None:
    """In multiworld mode the page's own check (multiworldReason) refuses exactly the values the
    metadata leaves out, with the reason shown."""
    meta = multiworld.metadata()
    cases = [[spec.id, value] for spec in archipelago.option_fields()
             for value in {*spec.values, *(value for value, _ in multiworld._all_labels(spec.id))}]
    cases += [[field_id, value] for field_id in meta["fixed"] for value in range(5)]
    answers = run_page_functions(
        ["multiworldReason"],
        f"const metadata = {{multiworld: {json.dumps(meta)}}};\nlet mode = MULTIWORLD;\n"
        f"console.log(JSON.stringify({json.dumps(cases)}.map(([id, value]) => multiworldReason(id, value) ?? null)));")
    for (field_id, value), reason in zip(cases, answers, strict=True):
        fixed = meta["fixed"].get(field_id)
        if fixed:
            assert (reason is None) == (value == fixed["value"])
            assert reason in (None, fixed["reason"])
        else:
            assert (reason is None) == (value in meta["offered"][field_id])
            assert reason in (None, meta["notOffered"])


# --- beta values (owner, 2026-11-21) ----------------------------------------------------------------

def test_a_beta_value_is_choosable_only_with_the_switch_on() -> None:
    """In multiworld mode a value that waits for its logic scan is offered (multiworldReason passes it) and is
    locked like a beta setting while Enable Beta Flags is off (betaReason), labeled "(beta)"; with the switch
    on it can be chosen. Single-player mode never locks it for that. A state using one turns the switch on
    when loaded, and blocks Export while the switch is off (multiworldBetaBlocking)."""
    meta = multiworld.metadata()
    page_beta = flag_form.metadata()["beta"]
    cases = [[field_id, value] for field_id, values in meta["beta"].items() for value in values]
    assert cases
    state = {"fields": {"B79": {"value": int(ThreeState.ON)}}, "zora": {"ok": True, "values": {"harder_ganon": 0}}}
    script = f"""
const metadata = {{multiworld: {json.dumps(meta)}, beta: {json.dumps(page_beta)}}};
const BETA_SUFFIX = " (beta)";
let mode = MULTIWORLD, betaOn = false, form = {json.dumps(state)};
const cases = {json.dumps(cases)};
const ask = () => cases.map(([id, value]) => [multiworldReason(id, value) ?? null, betaReason(id, value) ?? null,
                                              betaLabel(id, value, "L")]);
const off = ask(); const blockedOff = multiworldBetaBlocking();
betaOn = true; const on = ask(); const blockedOn = multiworldBetaBlocking();
mode = SINGLE; betaOn = false; const single = ask();
console.log(JSON.stringify({{off, on, single, blockedOff, blockedOn, used: multiworldBetaIn(form)}}));"""
    done = run_page_functions(["betaValuesOf", "multiworldBetaValuesOf", "stateValue", "multiworldBetaIn",
                               "multiworldBetaBlocking", "betaReason", "betaLabel", "multiworldReason"], script)
    file_beta = {(field_id, value) for field_id, values in page_beta["values"].items() for value in values}
    for (field_id, value), off, on, single in zip(cases, done["off"], done["on"], done["single"], strict=True):
        assert off == [None, page_beta["locked"], "L (beta)"], (field_id, value)
        assert on == [None, None, "L (beta)"], (field_id, value)
        in_file = (field_id, value) in file_beta           # Universal Drops v2.0 is beta in single player too
        assert single == [None, page_beta["locked"] if in_file else None, "L (beta)" if in_file else "L"]
    assert (done["used"], done["blockedOff"], done["blockedOn"]) == (["B79"], ["B79"], [])
    # Loaded strings that use one turn the switch on, in multiworld mode, as the file's beta settings do
    assert re.search(r"usesBeta = state\.beta\.length > 0 \|\| \(mode === MULTIWORLD && multiworldBetaIn\(state\)",
                     PAGE_SCRIPT)
    assert "multiworldBetaBlocking().length === 0" in page_function("canExport")


def test_the_yaml_with_a_beta_value_starts_with_the_warning() -> None:
    """The exported YAML's first lines: the warning, naming each beta value; the check names them for the page's
    warning; Archipelago reads the YAML as ever."""
    zora_flag_string = zora_with(universal_drops_v2=1, swap_swords_and_rings=1)
    verdict = multiworld.check(DEFAULT_FLAGS, zora_flag_string, {})
    assert verdict["ok"] and verdict["beta"] == ["Universal Drops v2.0: On", "Swap Swords and Rings: On"]
    text = multiworld.export_yaml(NAME, DEFAULT_FLAGS, zora_flag_string, {})["yaml"]
    header = text.split("\n\n")[0].splitlines()
    warning = " ".join(line.removeprefix("#").strip() for line in header[:header.index("#")])
    assert warning == (f"WARNING: {archipelago.MULTIWORLD_BETA_TITLE}: Universal Drops v2.0: On; Swap Swords and "
                       f"Rings: On. {archipelago.MULTIWORLD_BETA_WARNING}")
    assert all(len(line) <= 100 for line in header)
    _document, options, _settings = read_back(text)
    assert (options["universal_drops_v2"], options["swap_swords_and_rings"]) == ("on", "on")
    assert not multiworld.export_yaml(NAME, DEFAULT_FLAGS, "", {})["yaml"].startswith("# WARNING")


def test_the_page_shows_the_big_warning() -> None:
    assert re.search(r'<div id="multiworld-beta-warning" class="mw-beta-warning" role="alert" hidden>', PAGE)
    shown = page_function("showMultiworldNotes")
    assert "metadata.multiworld.betaTitle" in shown and "metadata.multiworld.betaWarning" in shown


# --- the player name -------------------------------------------------------------------------------

NAME_CASES = {
    "": "type a player name",
    "   ": "type a player name",
    "A" * 16: None,
    " " + "A" * 16 + " ": None,
    "A" * 17: "at most 16 characters (this one has 17)",
    "Archipelago": 'Archipelago refuses the name "Archipelago"',
    "é" * 11: None,                                   # 22 bytes as UTF-8
    "é" * 12: "too long for the ROM",                 # 24 bytes
    "a\0b": "too long for the ROM",                   # a zero byte ends the ROM's slot name
}


@pytest.mark.parametrize("name", NAME_CASES)
def test_the_player_name(name: str) -> None:
    expected = NAME_CASES[name]
    problem = multiworld.player_name_problem(name)
    if expected is None:
        assert problem is None
        assert yaml.safe_load(multiworld.export_yaml(name, DEFAULT_FLAGS, "", {})["yaml"])["name"] == name.strip()
    else:
        assert problem is not None
        assert problem.startswith(expected)
        with pytest.raises(multiworld.ExportRefused):
            multiworld.export_yaml(name, DEFAULT_FLAGS, "", {})


@pytest.mark.parametrize("name", ['Ti"m: #1', "x: {y}", "'quoted'", "Zoë & Kai", "- dash"])
def test_any_allowed_name_reads_back_as_written(name: str) -> None:
    exported = multiworld.export_yaml(name, DEFAULT_FLAGS, "", {})
    assert yaml.safe_load(exported["yaml"])["name"] == name
    assert re.fullmatch(r"[A-Za-z0-9_-]+\.yaml", exported["fileName"])


# --- the shared link -------------------------------------------------------------------------------

LINK_CASES = [
    {"flags": DEFAULT_FLAGS, "zoraFlags": "", "mode": "multiworld"},
    {"flags": flags_with(options={DUNGEON_QUEST: 0}), "zoraFlags": zora_with(progressive_items=1),
     "mode": "multiworld"},
    {"flags": flags_with(options={DUNGEON_QUEST: 0}), "zoraFlags": "", "mode": "single"},
]


def test_the_mode_and_flag_strings_travel_in_the_link() -> None:
    """The page's link functions, run in Node: the mode and both strings round-trip (a default
    part left out), another parameter is kept, an unknown mode is single player."""
    answers = run_page_functions(
        ["validSeed", "linkSettings", "linkSearch"],
        f"const cases = {json.dumps(LINK_CASES)};\nconst defaults = {json.dumps(DEFAULT_FLAGS)};\n"
        "console.log(JSON.stringify({\n"
        "  searches: cases.map((c) => linkSearch('?pyodide=0.28.3', c, defaults)),\n"
        "  trips: cases.map((c) => linkSettings(linkSearch('', c, defaults))),\n"
        "  unknown: linkSettings('?mode=solo'),\n"
        "  old: linkSearch('?mode=multiworld&flags=X', {flags: defaults, zoraFlags: '', mode: SINGLE}, defaults),\n"
        "}));")
    for case, search, trip in zip(LINK_CASES, answers["searches"], answers["trips"], strict=True):
        assert search.startswith("?pyodide=0.28.3")
        assert ("mode=multiworld" in search) == (case["mode"] == "multiworld")
        assert trip == {"flags": None if case["flags"] == DEFAULT_FLAGS else case["flags"],
                        "zoraFlags": case["zoraFlags"] or None, "mode": case["mode"], "seed": None}
    assert answers["unknown"] == {"flags": None, "zoraFlags": None, "mode": "single", "seed": None}
    assert answers["old"] == ""


def test_the_page_loads_the_link() -> None:
    """At start the page loads the link's strings (under "the shared link") and mode, and every
    shown state writes them back to the address."""
    assert "const sharedLink = linkSettings(location.search);" in PAGE_SCRIPT
    assert "loadFlags(sharedLink.flags || metadata.defaultFlags, { rewrite: true, start: true, name: SHARED_LINK });" \
        in PAGE_SCRIPT
    assert re.search(r"showProblems\(\);\n  updateLink\(\);", PAGE_SCRIPT)


# --- Node -----------------------------------------------------------------------------------------

CONSTANTS = ("SINGLE", "MULTIWORLD", "LINK_FLAGS", "LINK_ZORA_FLAGS", "LINK_MODE", "LINK_SEED", "SEED_LIMIT")


def page_function(name: str) -> str:
    """A top-level function's source from web/zora-web.js."""
    match = re.search(rf"^function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def run_page_functions(names: list[str], script: str) -> Any:
    """The page's constants and these functions, then `script`, in Node; its JSON output."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    constants = [re.search(rf"^const {name} = .*;$", PAGE_SCRIPT, re.MULTILINE) for name in CONSTANTS]
    assert all(constants)
    source = "\n".join([*(match.group(0) for match in constants if match), *map(page_function, names), script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)
