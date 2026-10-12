"""Player settings for Archipelago (zora/archipelago.py player_setting_fields; docs/archipelago.md
"Player settings"). Players choose cosmetics in their YAML, so the world reads every setting as
data.

P3: player_setting_fields() describes every setting finish() and rom_from_recipe accept: each
key (a recipe's playerSettings key), its default, every choice, colour and listed word accepted,
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
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import (
    PAGE_BOSS_SOUND_WORD,
    PAGE_CHOICES,
    PAGE_HEART_SLOT,
    PAGE_LEVEL_WORD,
    PAGE_TUNIC_SLOTS,
    PlayerSettingError,
    PlayerSettings,
    boss_sound_word_problem,
    level_word_problem,
    player_settings_from_page,
    written_offsets,
)
from zora.rom.text_encoding import CHAR_TO_BYTE

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

REPO = Path(__file__).resolve().parent.parent
CASES = {"baseline": FLAG_CASES["baseline"], "progressive items": FLAG_CASES["every ZORA flag on"],
         "sword entrance": (ASNB_FLAGS, ASNB_ZORA_FLAGS)}
SEED = 1
AP_NAME = b"Link"
# Each setting's PlayerSettings field (written_offsets' name).
FIELD = {**{key: field for key, (field, _values) in PAGE_CHOICES.items()},
         **dict.fromkeys(PAGE_TUNIC_SLOTS, "tunic_colours"), PAGE_HEART_SLOT: "heart_colour",
         PAGE_LEVEL_WORD: "level_word", PAGE_BOSS_SOUND_WORD: "boss_sound_word"}
CUSTOM_WORDS = {PAGE_LEVEL_WORD: ("X", "PALACE", "ZORA1", "A-B.C"), PAGE_BOSS_SOUND_WORD: ("?!?!", "ZZ9Z")}
SPECS = {spec.key: spec for spec in archipelago.player_setting_fields()}
CLIENT_FRAMES = 240
RECEIVED = ("Bow", "Raft", "Ladder", "Recorder")


# --- P3: the fields ------------------------------------------------------------------------------------

def test_every_setting_once_with_its_default() -> None:
    assert list(SPECS) == [*PAGE_CHOICES, *PAGE_TUNIC_SLOTS, PAGE_HEART_SLOT, PAGE_LEVEL_WORD, PAGE_BOSS_SOUND_WORD]
    assert player_settings_from_page({key: spec.default for key, spec in SPECS.items()}) == PlayerSettings()


def values_of(spec: archipelago.PlayerSettingSpec) -> list[str | int]:
    """Every value the spec lists: its choices or colours, and for a word its listed words and a
    few custom ones."""
    values: list[str | int] = list(spec.colours) if spec.kind == archipelago.COLOUR else \
        [value for value, _label in spec.choices]
    return values + list(CUSTOM_WORDS.get(spec.key, ()))


@pytest.mark.parametrize("key", list(SPECS))
def test_every_listed_value_is_accepted_and_nothing_else(key: str) -> None:
    spec = SPECS[key]
    for value in values_of(spec):
        player_settings_from_page({key: value})
    refused: dict[str, list[object]] = {archipelago.CHOICE: ["bogus", 1], archipelago.COLOUR: [0x0D, 0x40, -1, "0x16"],
                                        archipelago.WORD: [7]}
    for wrong in refused[spec.kind]:
        with pytest.raises(PlayerSettingError):
            player_settings_from_page({key: wrong})
    assert spec.label and (spec.kind != archipelago.COLOUR or 0x0D not in spec.colours)


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
    colour slot's key, label and default, and the word rows' keys and names."""
    page = page_source()
    for key, spec in SPECS.items():
        if spec.kind == archipelago.CHOICE:
            pattern = rf'\{{ key: "{key}", label: "([^"]+)", default: "([^"]+)",\s*choices: \[(.*?)\]\s*,\s*help'
            entry = re.search(pattern, page, re.S)
            assert entry, key
            pairs = tuple(re.findall(r'\["([^"]+)", "([^"]+)"\]', entry.group(3)))
            assert (entry.group(1), entry.group(2), pairs) == (spec.label, spec.default, spec.choices), key
        elif spec.kind == archipelago.COLOUR:
            entry = re.search(rf'\{{ key: "{key}", label: "([^"]+)", default: (0x[0-9A-Fa-f]+)', page)
            assert entry and (entry.group(1), int(entry.group(2), 16)) == (spec.label, spec.default), key
        else:
            assert re.search(rf'key: "{key}", name: "{re.escape(spec.label)}"', page), key


# --- P4: settings never change what Archipelago relies on -----------------------------------------------

@cache
def recipe_parts(case: str) -> tuple[archipelago.BuildResult, dict, tuple[str, ...]]:
    result = archipelago.build_from_strings(*CASES[case], SEED, remember_repo_base_rom())
    assignment, received = accepted_assignment(result, SEED)
    return result, assignment, tuple(received)


def rom_with(case: str, settings: dict[str, object]) -> bytes:
    result, assignment, received = recipe_parts(case)
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
    for value in every_change()[key]:
        rom = rom_with(case, {key: value})
        diff = changed(base, rom)
        assert diff and diff <= allowed, (key, value, sorted(diff - allowed)[:8])
        assert archipelago.rom_identity(rom) == archipelago.rom_identity(base)


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
    assert archipelago.rom_identity(rom) == archipelago.rom_identity(base) == archipelago.RomIdentity((1, 1), AP_NAME)
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
