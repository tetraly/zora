"""Player settings for Archipelago (zora/archipelago.py player_setting_fields; docs/archipelago.md
"Player settings"). Players choose cosmetics in their YAML, so the world reads every setting as
data.

P3: player_setting_fields() describes every setting finish() and rom_from_recipe accept: each
key (a recipe's playerSettings key), its default, every choice, color and listed word accepted,
the word rules agreeing with zora/rom/player_settings.py, and the page (web/zora-web.js, read
only) using the same keys, labels, choices and defaults.

P4: settings never change what Archipelago relies on. Over recipes with Progressive Items and
with the sword entrance (All Swords No Boards), each choice of each setting at least once: the ROM
differs from the defaults' ROM only inside that setting's written_offsets (the level name's
include the hint lines it rewrites); the slot identity, give_rules, the placements and the pickup
checks are unchanged; FINISH's sanity check passes (finish() runs it). In the emulator, the
client's loop on the defaults' ROM and on a ROM with every setting changed leaves the same RAM at
every address the client reads or writes."""
import json
import re
from functools import cache
from pathlib import Path

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.emulator import Emulator
from tests.test_archipelago_recipe import accepted_assignment
from zora import archipelago
from zora.flags.presets import ASNB_FLAGS, ASNB_ZORA_FLAGS
from zora.generate.places import read_item
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.link_art import offered_sprite_sets
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import (
    PAGE_BOSS_SOUND_WORD,
    PAGE_CHOICES,
    PAGE_HEART_SLOT,
    PAGE_LEVEL_WORD,
    PAGE_LINK_COLORS,
    PAGE_LINK_SPRITE,
    PAGE_TUNIC_SLOTS,
    RANDOM_COLOR,
    PlayerSettingError,
    PlayerSettings,
    boss_sound_word_problem,
    level_word_problem,
    player_settings_from_page,
    written_offsets,
)
from zora.rom.text_encoding import CHAR_TO_BYTE

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

REPO = Path(__file__).resolve().parent.parent
CASES = {"baseline": FLAG_CASES["baseline"], "progressive items": FLAG_CASES["every ZORA flag on"],
         "sword entrance": (ASNB_FLAGS, ASNB_ZORA_FLAGS)}
SEED = 1
AP_NAME = b"Link"
# Each setting's PlayerSettings field (written_offsets' name).
FIELD = {**{key: field for key, (field, _values) in PAGE_CHOICES.items()},
         **dict.fromkeys(PAGE_TUNIC_SLOTS, "tunic_colors"), PAGE_HEART_SLOT: "heart_color",
         PAGE_LEVEL_WORD: "level_word", PAGE_BOSS_SOUND_WORD: "boss_sound_word", PAGE_LINK_SPRITE: "link_sprite",
         **dict.fromkeys(PAGE_LINK_COLORS, "link_colors")}
CUSTOM_WORDS = {PAGE_LEVEL_WORD: ("X", "PALACE", "ZORA1", "A-B.C"), PAGE_BOSS_SOUND_WORD: ("?!?!", "ZZ9Z")}
# The ROM's own settings, and the Archipelago games' settings (multiworld_only), which change no ROM
# byte ZORA's player settings write.
ALL_SPECS = {spec.key: spec for spec in archipelago.player_setting_fields()}
SPECS = {key: spec for key, spec in ALL_SPECS.items() if not spec.multiworld_only}
MULTIWORLD_SPECS = {key: spec for key, spec in ALL_SPECS.items() if spec.multiworld_only}
# Multiworld settings the page has no row for yet (its rows in web/zora-web.js come next, emptying
# this set; owner decision 2026-10-18).
PAGE_PENDING: frozenset[str] = frozenset()
# The playable character's rows have their own shape on the page (a select with the sets and a file button;
# colors under their heading): checked apart in test_the_page_has_the_playable_characters_rows
PAGE_OWN_ROWS = frozenset({PAGE_LINK_SPRITE, *PAGE_LINK_COLORS})
CLIENT_FRAMES = 240
# Graphics theme: read at the world's build (its tiles go in before generation), so its cases build anew
GRAPHICS_THEME, GRAPHICS_THEME_OFF = "graphicsTheme", "off"
RECEIVED = ("Bow", "Raft", "Ladder", "Recorder")


# --- P3: the fields ------------------------------------------------------------------------------------

def test_every_setting_once_with_its_default() -> None:
    assert list(ALL_SPECS) == [*PAGE_CHOICES, PAGE_LINK_SPRITE, *PAGE_TUNIC_SLOTS, *PAGE_LINK_COLORS, PAGE_HEART_SLOT,
                               PAGE_LEVEL_WORD, PAGE_BOSS_SOUND_WORD, *archipelago.MULTIWORLD_SETTINGS]
    defaults = archipelago.page_player_settings({key: spec.default for key, spec in SPECS.items()})
    assert player_settings_from_page(defaults) == PlayerSettings()


@pytest.mark.parametrize("key", list(MULTIWORLD_SPECS))
def test_a_multiworld_setting_takes_its_values_and_nothing_else(key: str) -> None:
    """Each listed value by its page value or its value key, by page key or YAML key; anything else
    refused (check_player_settings, as the world checks a YAML)."""
    spec = MULTIWORLD_SPECS[key]
    assert spec.kind == archipelago.CHOICE and spec.default in dict(spec.choices)
    for (value, _label), (_value, value_key) in zip(spec.choices, spec.value_keys, strict=True):
        for given in ({key: value}, {spec.yaml_key: value_key}):
            archipelago.check_player_settings(given)
            assert archipelago.multiworld_setting(given, key) == value
    for wrong in ("bogus", 1):
        with pytest.raises(PlayerSettingError):
            archipelago.check_player_settings({key: wrong})


def values_of(spec: archipelago.PlayerSettingSpec) -> list[str | int]:
    """Every value the spec lists: its choices or colors, and for a word its listed words and a
    few custom ones."""
    values: list[str | int] = list(spec.colors) if spec.kind == archipelago.COLOR else \
        [value for value, _label in spec.choices]
    return values + list(CUSTOM_WORDS.get(spec.key, ()))


@pytest.mark.parametrize("key", list(SPECS))
def test_every_listed_value_is_accepted_and_nothing_else(key: str) -> None:
    spec = SPECS[key]
    for value in values_of(spec):
        player_settings_from_page(archipelago.page_player_settings({key: value}))
    refused: dict[str, list[object]] = {archipelago.CHOICE: ["bogus", 1], archipelago.COLOR: [0x0D, 0x41, -1, "0x16"],
                                        archipelago.WORD: [7]}
    for wrong in refused[spec.kind]:
        with pytest.raises(PlayerSettingError):
            player_settings_from_page({key: wrong})
    assert spec.label and (spec.kind != archipelago.COLOR or 0x0D not in spec.colors)


def allowed_by_rule(rule: archipelago.TextRule, text: str) -> bool:
    word = text.strip().upper()
    return word == rule.random or (rule.min_length <= len(word) <= rule.max_length
                                   and all(char in rule.characters for char in word))


PROBES = ["", " ", "a", "Level", " roar ", "PALACE", "PALACES", "AB", "ABC", "ABCD", "ABCDE", "random", "Random",
          "A~B", "AB*D", "a b", "A,B!", "ÉTÉ", "1234567", "?", "LEV EL"]


@pytest.mark.parametrize(("key", "problem"), [(PAGE_LEVEL_WORD, level_word_problem),
                                              (PAGE_BOSS_SOUND_WORD, boss_sound_word_problem)])
def test_the_word_rules_are_finishs(key: str, problem: object) -> None:
    """TextRule says what player_settings_from_page (the text normalized) accepts, on every probe."""
    rule = SPECS[key].rule
    assert rule is not None
    assert set(rule.characters) == set(CHAR_TO_BYTE) - {"~"}
    for text in PROBES:
        try:
            player_settings_from_page({key: text})
            accepted = True
        except PlayerSettingError:
            accepted = False
        assert accepted == allowed_by_rule(rule, text), (key, text)
        assert accepted == (problem(text.strip().upper()) is None), (key, text)   # type: ignore[operator]


def page_source() -> str:
    return (REPO / "web" / "zora-web.js").read_text()


def test_the_page_shows_the_same_settings() -> None:
    """The page's Cosmetic tab: each choice's key, label, default and [value, label] pairs, each
    color slot's key, label and default, and the word rows' keys and names; the Multiworld
    settings' rows likewise, but those still PAGE_PENDING."""
    page = page_source()
    for key, spec in ALL_SPECS.items():
        if key in PAGE_PENDING | PAGE_OWN_ROWS:
            continue
        if spec.kind == archipelago.CHOICE:
            pattern = rf'\{{ key: "{key}", label: "([^"]+)", default: "([^"]+)",\s*choices: \[(.*?)\]\s*,\s*help'
            entry = re.search(pattern, page, re.S)
            assert entry, key
            pairs = tuple(re.findall(r'\["([^"]+)", "([^"]+)"\]', entry.group(3)))
            assert (entry.group(1), entry.group(2), pairs) == (spec.label, spec.default, spec.choices), key
        elif spec.kind == archipelago.COLOR:
            entry = re.search(rf'\{{ key: "{key}", label: "([^"]+)", default: (0x[0-9A-Fa-f]+)', page)
            assert entry and (entry.group(1), int(entry.group(2), 16)) == (spec.label, spec.default), key
        else:
            assert re.search(rf'key: "{key}", name: "{re.escape(spec.label)}"', page), key


def test_the_page_has_the_playable_characters_rows() -> None:
    """The world offers the built-in sets (not a loaded file) and the character's colors 2 and 3: the
    page has the same keys, the colors with the same defaults, and a built-in choice for every set the
    world lists."""
    page = page_source()
    for key, default in zip(PAGE_LINK_COLORS, (0x27, 0x17), strict=True):
        assert re.search(rf'key: "{key}", label: "Color [23]", default: 0x{default:02X}', page), key
        assert ALL_SPECS[key].default == default and RANDOM_COLOR not in ALL_SPECS[key].colors
    sprite = ALL_SPECS[PAGE_LINK_SPRITE]
    assert sprite.default == "link" and sprite.choices[0][0] == "link" and sprite.choices[-1][0] == "random"
    assert "player-linkSprite" in page and 'LINK_SPRITE_RANDOM = "random"' in page
    assert [value for value, _label in sprite.choices[1:-1]] == list(offered_sprite_sets())


# --- P4: settings never change what Archipelago relies on -----------------------------------------------

@cache
def recipe_parts(case: str, theme: str = GRAPHICS_THEME_OFF) -> tuple[archipelago.BuildResult, dict, tuple[str, ...]]:
    """A case's build (with a Graphics theme, built from its working copy: the world reads that
    setting at its build) and its accepted assignment."""
    themed = {GRAPHICS_THEME: theme} if theme != GRAPHICS_THEME_OFF else None
    result = archipelago.build_from_strings(*CASES[case], SEED, remember_repo_base_rom(), themed)
    assignment, received = accepted_assignment(result, SEED)
    return result, assignment, tuple(received)


def rom_with(case: str, settings: dict[str, object]) -> bytes:
    result, assignment, received = recipe_parts(case, str(settings.get(GRAPHICS_THEME, GRAPHICS_THEME_OFF)))
    return archipelago.finish(result, assignment, received, settings, AP_NAME)


@cache
def default_rom(case: str) -> bytes:
    return rom_with(case, {})


def changed(old: bytes, new: bytes) -> set[int]:
    return {offset for offset, (a, b) in enumerate(zip(old, new, strict=True)) if a != b}


def placements(case: str, rom: bytes) -> list[int]:
    result, _, _ = recipe_parts(case)
    world = parse_rom(rom)
    return [int(read_item(world, place)) for place in result.state.places]


def every_change() -> dict[str, list[str | int]]:
    """Each setting's values other than its default."""
    return {key: [value for value in values_of(spec) if value != spec.default] for key, spec in SPECS.items()}


@pytest.mark.parametrize("key", list(SPECS))
@pytest.mark.parametrize("case", list(CASES))
def test_a_setting_writes_only_its_own_bytes(case: str, key: str) -> None:
    base = default_rom(case)
    allowed = written_offsets(FIELD[key])
    if key == PAGE_LINK_SPRITE:
        # a set's own colors come with it (Playable character's colors: The set's own, the default)
        allowed |= written_offsets("tunic_colors") | written_offsets("link_colors")
    for value in every_change()[key]:
        rom = rom_with(case, {key: value})
        diff = changed(base, rom)
        # the playable character's Random may draw the original Link for this seed, which changes nothing
        assert diff or (key, value) == (PAGE_LINK_SPRITE, archipelago.RANDOM_CHOICE), (key, value)
        assert diff <= allowed, (key, value, sorted(diff - allowed)[:8])
        assert archipelago.rom_identity(rom) == archipelago.rom_identity(base)


@pytest.mark.parametrize("case", list(CASES))
def test_the_arrival_sound_changes_no_rom_byte(case: str) -> None:
    """item_arrival_sound reaches the client only (its tables): finish() and the recipe take it,
    and every choice gives the defaults' ROM."""
    for value in every_value_but_the_default(archipelago.PAGE_ITEM_ARRIVAL_SOUND):
        assert rom_with(case, {archipelago.PAGE_ITEM_ARRIVAL_SOUND: value}) == default_rom(case)


def every_value_but_the_default(key: str) -> list[str]:
    spec = MULTIWORLD_SPECS[key]
    return [value for value, _label in spec.choices if value != spec.default]


def all_changed() -> dict[str, object]:
    """Every setting at once away from its default (the last listed other value)."""
    return {key: values[-1] for key, values in every_change().items()}


@pytest.mark.parametrize("case", list(CASES))
def test_every_setting_changed_keeps_what_archipelago_reads(case: str) -> None:
    """With every setting changed: the bytes only inside the settings' ranges; the identity, the
    placements, give_rules from the recipe, the pickup checks unchanged; the recipe rebuilds it."""
    result, assignment, received = recipe_parts(case)
    base, rom = default_rom(case), rom_with(case, all_changed())
    allowed = set().union(*(written_offsets(field) for field in set(FIELD.values())))
    assert changed(base, rom) <= allowed
    identity = archipelago.RomIdentity(archipelago.FORMAT_VERSION_NUMBERS, AP_NAME)
    assert archipelago.rom_identity(rom) == archipelago.rom_identity(base) == identity
    assert placements(case, rom) == placements(case, base)
    plain = json.loads(json.dumps(archipelago.recipe(result, assignment, received, {}, AP_NAME)))
    dressed = json.loads(json.dumps(archipelago.recipe(result, assignment, received, all_changed(), AP_NAME)))
    rules = archipelago.give_rules(result)
    assert archipelago.recipe_give_rules(dressed) == archipelago.recipe_give_rules(plain) == rules
    assert {name: (check.address, check.mask) for name, check in archipelago.pickup_checks(result).items()}
    assert archipelago.rom_from_recipe(dressed, remember_repo_base_rom()) == rom


def client_ram(case: str, rom: bytes) -> dict[int, int]:
    """The client's loop for CLIENT_FRAMES frames of a new game, giving RECEIVED in order, then the
    RAM at every address the client reads or writes."""
    result, _, _ = recipe_parts(case)
    rules = archipelago.give_rules(result)
    emu = Emulator(rom)
    emu.new_game()
    for _ in range(CLIENT_FRAMES):
        if archipelago.may_receive({address: emu[address] for address in archipelago.RECEIVE_STATE}):
            count = emu[archipelago.RECEIVED_COUNT]
            if count < len(RECEIVED):
                inventory_ram = {address: emu[address] for address in range(inventory.ITEMS, inventory.MAX_BOMBS + 1)}
                writes = archipelago.receive(RECEIVED[count], inventory_ram, rules)
                writes[archipelago.RECEIVED_COUNT] = count + 1
                for address, value in writes.items():
                    emu[address] = value
        emu.run(1)
    addresses = {*range(inventory.ITEMS, inventory.MAX_BOMBS + 1), archipelago.RECEIVED_COUNT,
                 *archipelago.RECEIVE_STATE, *archipelago.GOAL_STATE,
                 *(check.address for check in archipelago.pickup_checks(result).values())}
    return {address: emu[address] for address in sorted(addresses)}


@pytest.mark.parametrize("case", list(CASES))
def test_the_clients_ram_is_the_same(case: str) -> None:
    plain = client_ram(case, default_rom(case))
    assert plain[archipelago.RECEIVED_COUNT] == len(RECEIVED)
    assert client_ram(case, rom_with(case, all_changed())) == plain
