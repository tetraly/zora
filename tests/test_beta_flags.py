"""Beta flags (zora/flags/beta.py, zora/flags/flags.json; owner rulings, 2026-11-05 and 2026-11-06): the shipped
file loads; a flag or a single value marked beta (here through the `beta_marked` fixture, never the file), and
any Random that can resolve to one, reaches the page's metadata and each state's in-use list, while flag
strings, refusals and output stay exactly as they were. Archipelago offers no beta value."""
import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.test_web_conflict_tabs import page_function
from zora.flags import beta
from zora.flags import codec
from zora.flags import form as flag_form
from zora.flags.fields import ItemShuffleScope
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_form import zora_flags_from_values
from zora.rom import base_rom

REPO = Path(__file__).resolve().parent.parent
FLAGS_FILE = REPO / "zora" / "flags" / beta.FLAGS_FILE
PAGE = REPO / "web" / "index.html"
CAVE_SHUFFLE = "C05"
ITEM_SHUFFLE = "C06"
HARDER_GANON = "harder_ganon"
HARDER_GANON_LEVEL_3 = 3
PEGASUS_BOOTS = "pegasus_boots"
START = MVP_BASELINE_LEVEL_ENCODING_OFF
Marker = Callable[[Mapping[str, Any]], None]


@pytest.fixture
def beta_marked(monkeypatch: pytest.MonkeyPatch) -> Marker:
    """Mark flags beta for one test, in place of the shipped file: each flag's "beta", as the file holds it."""
    def mark(flags: Mapping[str, Any]) -> None:
        monkeypatch.setattr(beta, "flags_config",
                            lambda: {beta.FLAGS_KEY: {key: {beta.BETA_KEY: listed} for key, listed in flags.items()}})
    return mark


def with_value(field_id: str, value: int, flags: str = START) -> str:
    """The flag string with one Z1R field at a value (through the page's own path)."""
    values = {field.id: str(flag_form._value_of(codec.decode(flags), field)) for field in flag_form.ALL_FIELDS}
    return flag_form.flags_from_values({**values, field_id: value})


def harder_ganon_level_3() -> str:
    return zora_flags_from_values({HARDER_GANON: HARDER_GANON_LEVEL_3})


def test_the_shipped_file_marks_universal_drops_v2_and_loads() -> None:
    """Ruling 6 shipped no flag in beta; Universal Drops v2.0 is the first (owner ruling 1,
    2026-11-05), every value but Off. The file parses against the page's flags, and the start preset
    uses no beta value."""
    assert json.loads(FLAGS_FILE.read_text(encoding="utf-8"))[beta.FLAGS_KEY] == {
        "universal_drops_v2": {beta.BETA_KEY: beta.ALL_VALUES}, "B51": {beta.BETA_KEY: ["Basic", "Medium", "Full"]},
        "wizzrobes_shoot_wallmasters": {beta.BETA_KEY: beta.ALL_VALUES},
        "item_counter": {beta.BETA_KEY: beta.ALL_VALUES}}
    # Spoiler Log Detail Level (owner rulings, 2026-11-06, and Prompt 660): every level but None, and Random
    levels = {1, flag_form.SPOILER_MEDIUM_CHOICE, flag_form.SPOILER_FULL_CHOICE, 2}
    assert flag_form.beta_values() == {"universal_drops_v2": frozenset({1, 2}), "B51": frozenset(levels),
                                       "wizzrobes_shoot_wallmasters": frozenset({1, 2}),
                                       "item_counter": frozenset({1, 2})}
    assert flag_form.metadata()["beta"]["values"] == {"universal_drops_v2": [1, 2], "B51": sorted(levels),
                                                      "wizzrobes_shoot_wallmasters": [1, 2],
                                                      "item_counter": [1, 2]}
    assert flag_form.form_state(START)["beta"] == []


def test_the_page_has_the_switch_off_by_default() -> None:
    page = PAGE.read_text(encoding="utf-8")
    assert '<div class="beta-bar" id="beta-bar" hidden>' in page
    assert 'id="beta-off" data-choice="off" aria-pressed="true"' in page
    assert 'id="beta-on" data-choice="on" aria-pressed="false"' in page
    assert '<aside class="beta-banner" id="beta-banner" role="note" aria-label="Beta notice" hidden>' in page
    assert "Beta settings are on. They're less tested, so some bugs are to be expected." in page
    assert '<a href="https://discord.gg/zescSjDtme" target="_blank" rel="noopener">ZORA Discord</a>' in page


# The page's beta functions on a fake page: each element by id, its hidden flag and text
FAKE_BETA_PAGE = """
const elements = {};
const $ = (id) => (elements[id] = elements[id] || { hidden: true, textContent: "", attributes: {},
  setAttribute(name, value) { this.attributes[name] = value; } });
let form = null;
const metadata = { beta: { values: { B51: [1] }, warning: "w", inUse: "u" } };
let betaOn = false;
let betaTurnedOnByFlags = false;
const shown = () => [elements["beta-banner"].hidden, elements["beta-warning"].hidden];
"""


def test_the_beta_notice_shows_only_while_the_switch_is_on() -> None:
    """The banner at the top of the page follows the switch (2026-11-07): hidden at first, shown the moment
    it is turned on, by a click or by loaded flags, and hidden again when it is turned off."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    functions = [page_function(name) for name in ("showBetaSwitch", "setBeta", "onBetaPicked")]
    script = """
const seen = [];
showBetaSwitch(); seen.push(shown());
onBetaPicked(true); seen.push(shown());
onBetaPicked(false); seen.push(shown());
setBeta(true, { byFlags: true }); seen.push(shown());
console.log(JSON.stringify(seen));
"""
    source = "\n".join([FAKE_BETA_PAGE, *functions, script])
    done = subprocess.run([node, "-e", source], capture_output=True, text=True, check=True)
    assert json.loads(done.stdout) == [[True, True], [False, False], [True, True], [False, False]]


def test_a_whole_flag_marks_every_value_but_a_fresh_pages(beta_marked: Marker) -> None:
    beta_marked({CAVE_SHUFFLE: beta.ALL_VALUES})
    fresh = flag_form.beta_offered()[CAVE_SHUFFLE].default
    offered = flag_form.FIELDS_BY_ID[CAVE_SHUFFLE]
    assert flag_form.beta_values()[CAVE_SHUFFLE] == frozenset(flag_form.field_values(offered)) - {fresh}
    meta = flag_form.metadata()["beta"]
    assert meta["flags"] == [CAVE_SHUFFLE]
    assert flag_form.form_state(START)["beta"] == []
    other = next(value for value in flag_form.field_values(offered) if value != fresh)
    used = flag_form.form_state(with_value(CAVE_SHUFFLE, other))["beta"]
    assert used == [{"field": CAVE_SHUFFLE, "value": other,
                     "text": f"Cave Shuffle: {flag_form.value_label(offered, other)}"}]


def test_a_single_value_is_beta_by_label_or_number(beta_marked: Marker) -> None:
    beta_marked({HARDER_GANON: ["Level 3"], CAVE_SHUFFLE: [1]})
    random = 4                          # Cave Shuffle: Random can draw Dungeons Only
    assert flag_form.beta_values() == {HARDER_GANON: frozenset({HARDER_GANON_LEVEL_3}),
                                       CAVE_SHUFFLE: frozenset({1, random})}
    meta = flag_form.metadata()["beta"]
    assert meta["flags"] == []          # single values: the flags themselves are not beta
    assert flag_form.form_state(START, zora_flags_from_values({HARDER_GANON: 2}))["beta"] == []
    used = flag_form.form_state(START, harder_ganon_level_3())["beta"]
    assert used == [{"field": HARDER_GANON, "value": HARDER_GANON_LEVEL_3, "text": "Harder Ganon: Level 3"}]
    assert flag_form.beta_settings_used(with_value(CAVE_SHUFFLE, 1), harder_ganon_level_3()) == [
        "Harder Ganon: Level 3", "Cave Shuffle: Dungeons Only"]


def test_item_shuffles_no_vanilla_choice_can_be_beta(beta_marked: Marker) -> None:
    beta_marked({ITEM_SHUFFLE: [flag_form.ITEM_SHUFFLE_NO_VANILLA_LABEL]})     # a Random itself, listed
    random = with_value(ITEM_SHUFFLE, ItemShuffleScope.RANDOM)
    no_vanilla = flag_form.with_item_shuffle_no_vanilla("", True)
    assert flag_form.form_state(random)["beta"] == []
    assert [entry["value"] for entry in flag_form.form_state(random, no_vanilla)["beta"]] == [
        flag_form.ITEM_SHUFFLE_NO_VANILLA_CHOICE]
    assert flag_form.beta_settings_used(random, no_vanilla) == ["Item Shuffle: Random (No Vanilla)"]


def test_a_random_that_can_resolve_to_a_beta_value_is_beta(beta_marked: Marker) -> None:
    """Ruling 2026-11-06: a switch's "?", an option's Random, Item Shuffle's Random (No Vanilla) and a
    ZORA Extra's Random are beta when any value they can resolve to is, and a string using one is in use."""
    beta_marked({PEGASUS_BOOTS: ["On"], ITEM_SHUFFLE: ["Intra-Dungeon"], "swordlish": ["On"], "B41": ["On"]})
    assert flag_form.beta_values() == {
        PEGASUS_BOOTS: frozenset({1, 2}),                      # On and "?"
        ITEM_SHUFFLE: frozenset({2, ItemShuffleScope.RANDOM, flag_form.ITEM_SHUFFLE_NO_VANILLA_CHOICE}),
        "swordlish": frozenset({1, 2}),                        # On and Random
        "B41": frozenset({1, 2}),                              # Set Ganon HP to 0: On and "?"
    }
    random_boots = zora_flags_from_values({PEGASUS_BOOTS: 2})
    assert flag_form.beta_settings_used(START, random_boots) == ["Pegasus Boots: Random"]
    beta_marked({CAVE_SHUFFLE: ["Vanilla"]})                   # Random can draw Vanilla
    assert flag_form.beta_values()[CAVE_SHUFFLE] == frozenset({0, 4})


def test_beta_changes_no_string_and_refuses_nothing(beta_marked: Marker) -> None:
    """Rulings 4 and 5: the strings, their canonical forms and generation's refusals are the same with a
    flag in beta; only the metadata's beta part and each state's in-use list differ."""
    strings = [(with_value(CAVE_SHUFFLE, 1), harder_ganon_level_3()), (START, "")]
    before_meta = flag_form.metadata()
    before = [flag_form.form_state(z1r, zora) for z1r, zora in strings]
    beta_marked({CAVE_SHUFFLE: beta.ALL_VALUES, HARDER_GANON: ["Level 3"]})
    after_meta = flag_form.metadata()
    after = [flag_form.form_state(z1r, zora) for z1r, zora in strings]
    assert {**after_meta, "beta": None} == {**before_meta, "beta": None}
    for old, new in zip(before, after, strict=True):
        assert {**new, "beta": None} == {**old, "beta": None}
    assert after[0]["beta"] and not after[0]["generateRefusals"]


def test_a_config_naming_what_the_page_does_not_offer_is_refused() -> None:
    offered = flag_form.beta_offered()
    refused: list[tuple[dict[str, Any], str]] = [
        ({"C99": beta.ALL_VALUES}, "not a flag the page offers"),
        ({"item_shuffle_no_vanilla": beta.ALL_VALUES}, "not a flag the page offers"),   # set from Item Shuffle
        ({HARDER_GANON: ["Level 9"]}, 'no value "Level 9"'),
        ({HARDER_GANON: [7]}, "no value 7"),
        ({HARDER_GANON: ["Off"]}, "the value a fresh page starts with"),
        ({HARDER_GANON: []}, "must be"),
        ({HARDER_GANON: "some"}, "must be"),
    ]
    for config, message in refused:
        with pytest.raises(beta.BetaConfigError, match=message):
            beta.beta_values({beta.FLAGS_KEY: {key: {beta.BETA_KEY: listed} for key, listed in config.items()}},
                             offered)
    for entry, message in (([beta.BETA_KEY], "must be an object"), ({"bta": ["Level 3"]}, "unknown keys")):
        with pytest.raises(beta.BetaConfigError, match=message):
            beta.beta_values({beta.FLAGS_KEY: {HARDER_GANON: entry}}, offered)
    assert beta.beta_values({beta.FLAGS_KEY: {HARDER_GANON: {}}}, offered) == {}      # no "beta": not beta


def archipelago_beta_values() -> list[str]:
    """Every beta value (a Random that can resolve to one included) an Archipelago option offers."""
    from zora import archipelago
    marked = flag_form.beta_values()
    return [f"{spec.key}: {label}" for spec in archipelago.option_fields()
            for value, label in spec.choices if value in marked.get(spec.id, frozenset())]


def test_archipelago_offers_no_beta_value() -> None:
    """Ruling 2026-11-06: beta flags and values are withheld from Archipelago for now. A flag marked beta in
    zora/flags/flags.json needs its beta values held back in zora/archipelago.py (HELD_BACK, or the whole
    flag kept from the world, as universal_drops_v2 is), Random among them when it can resolve to one."""
    assert archipelago_beta_values() == []


def test_the_archipelago_check_finds_an_offered_beta_value(beta_marked: Marker) -> None:
    """The check itself: Archipelago offers Pegasus Boots On and Random, so marking On beta (and Random with it)
    shows both."""
    beta_marked({PEGASUS_BOOTS: ["On"]})
    assert archipelago_beta_values() == ["pegasus_boots: On", "pegasus_boots: Random"]


def test_marking_a_flag_beta_changes_no_rom(beta_marked: Marker) -> None:
    """Generation never reads the beta file: a ROM with a beta value is the same either way."""
    from zora.generate.pipeline import generate_rom
    base_rom.remember_repo_base_rom()
    rom = Path(base_rom.BASE_ROM_PATH).read_bytes()
    flags = with_value(CAVE_SHUFFLE, 1)

    def digest() -> str:
        return hashlib.sha1(generate_rom(flags, 1, rom, zora_flag_string=harder_ganon_level_3()).rom).hexdigest()

    before = digest()
    beta_marked({CAVE_SHUFFLE: [1], HARDER_GANON: ["Level 3"]})
    assert flag_form.beta_settings_used(flags, harder_ganon_level_3())
    assert digest() == before
