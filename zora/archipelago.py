"""Archipelago's interface to ZORA (Archipelago Phases 4a and 4c; docs/archipelago.md "Interface").

The one module the Archipelago world calls; it never reaches further into ZORA. It wraps what
Phases 1-3 built: BUILD makes a whole ZORA seed and lists the places its items sit in, with
Archipelago's access rules (logic.py); FINISH writes Archipelago's assignment into it and makes
the ROM. Items are named by the seed format's names (model/item_names.py), places by their fixed
names (places.all_place_names), another player's item by FOREIGN.

Imports only from zora/, relatively (scripts/check_imports.py), so it works copied in alone as
worlds.zora.zora, perhaps from a zip. ZORA-mode output and the page are untouched.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any

from .flags import form as flag_form
from .flags import zora_flags, zora_form
from .flags.codec import decode, encode
from .flags.dependencies import apply_dependencies, check_dependencies, correct_merchant_toll
from .flags.fields import (
    ENCODE_LEVEL_DATA,
    ITEM_SHUFFLE_SCOPE,
    THREE_STATE_LABELS,
    ItemShuffleScope,
    OptionField,
    Settings,
    ThreeState,
)
from .flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from .generate.finish import FOREIGN, AssignmentRefused, AssignmentUnbeatable, Foreign
from .generate.logic import LogicModel, logic_model
from .generate.pipeline import Built, FlagsRefused, GenerationPlan, plan
from .generate.pipeline import build as build_seed
from .generate.pipeline import finish as finish_seed
from .generate.places import Place, PlaceKind, read_item
from .model.enums import Item
from .model.item_names import ITEM_NAMES, ITEMS_BY_NAME
from .rom import inventory, slot_identity
from .rom.base_rom import BaseRomMismatch, NoPlayerRom, is_prg0, player_rom, remember_base_rom
from .rom.code_patches import SHOPS_BY_NUMBER
from .rom.player_settings import BLACKER_THAN_BLACK as REFUSED_COLOUR
from .rom.player_settings import (
    BOSS_SOUND_WORD_CHARACTERS,
    BOSS_SOUND_WORD_LENGTH,
    BOSS_SOUND_WORDS,
    LEVEL_WORD_CHARACTERS,
    LEVEL_WORD_CHOICES,
    LEVEL_WORD_DASH_MAX_LENGTH,
    LEVEL_WORD_MAX_LENGTH,
    PAGE_BOSS_SOUND_WORD,
    PAGE_CHOICES,
    PAGE_HEART_SLOT,
    PAGE_LEVEL_WORD,
    PAGE_TUNIC_SLOTS,
    PALETTE_SIZE,
    RANDOM_BOSS_SOUND_WORD,
    PlayerSettingError,
    PlayerSettings,
    player_settings_from_page,
)
from .version import PLAYER_NAME, ZORA_VERSION

__all__ = [
    "CHECKS_STATE",
    "DEFAULT_FLAGS",
    "DEFAULT_ZORA_FLAGS",
    "FOREIGN",
    "GOAL_STATE",
    "MAX_READ_LENGTH",
    "NOT_RECEIVABLE",
    "NO_MEMORY",
    "READ_RANGES",
    "RECEIVABLE_ITEMS",
    "RECEIVED_COUNT",
    "RECEIVE_STATE",
    "STATE_ADDRESSES",
    "BuildResult",
    "ClientMemory",
    "ClientNotReady",
    "ClientTables",
    "ClientTablesRefused",
    "Decision",
    "Foreign",
    "NotReceivable",
    "OptionSpec",
    "OptionsConflict",
    "PlaceInfo",
    "PlayerSettingSpec",
    "RamCheck",
    "ReceivedItem",
    "RecipeNotReproduced",
    "RecipeRefused",
    "RomIdentity",
    "ServerView",
    "SlotNameRefused",
    "TextRule",
    "UnknownItem",
    "build",
    "build_from_strings",
    "check_player_settings",
    "checks_readable",
    "client_ready",
    "client_step",
    "client_tables",
    "client_tables_from_json",
    "client_tables_of",
    "client_tables_to_json",
    "finish",
    "flag_strings",
    "give_rules",
    "goal_reached",
    "may_receive",
    "option_corrections",
    "option_fields",
    "option_keys",
    "option_value_keys",
    "page_player_settings",
    "pickup_checks",
    "player_setting_fields",
    "player_setting_problem",
    "receivable",
    "receive",
    "recipe",
    "recipe_give_rules",
    "rom_from_recipe",
    "rom_identity",
    "source_hash",
]


# --- options (spec "Design" 1) -------------------------------------------------------------------

# Owner decision 1: Archipelago's defaults are the page's default preset (form.metadata's
# defaultFlags: CP-5, the MVP baseline with level encoding off; every ZORA flag off).
DEFAULT_FLAGS = MVP_BASELINE_LEVEL_ENCODING_OFF
DEFAULT_ZORA_FLAGS = ""
# Encode level data (B82) is never offered and always off: its encoder is private, and an
# encoded seed is refused at plan time anyway (owner decision 2).
FORCED_OFF = ENCODE_LEVEL_DATA.id
# Item Shuffle (C06) is never offered and always Full (owner ruling, 2026-10-10): Archipelago
# places the items itself, so ZORA's item-shuffle scope has nothing to decide.
FIXED_OPTIONS = {ITEM_SHUFFLE_SCOPE.id: ItemShuffleScope.FULL}
NOT_OFFERED = frozenset({FORCED_OFF, *FIXED_OPTIONS})
# Values ZORA generates but Archipelago holds back until each passes C2's logic scan (owner
# ruling, 2026-10-10); a held toggle offers only Off. C01 = 1, 3, 4, C04 = 2, 3, B81, B03,
# Helpful hints (C03 = 1), Dungeon Quest 1st Quest (C02 = 0), the nine start items' on and Random
# (FP-START-02 to -05) and Allow Important Items in 9 (B25) passed (tests/archipelago_cases.py).
# Dungeon Quest 2nd Quest (C02 = 1) passed on 2026-10-11, once ZORA's late gate walked item
# cellars as late-gate.md says: 119 of 1,000 seeds had put an item cellar, which the game never
# reaches, under the Vertical Chute push room ($4E); now none do (docs/archipelago.md "Interface").
# Shuffle Dungeon Start Room (B26, PS-START) on and Random passed on 2026-10-11 (100 of 100 seeds
# at each, with the baseline's dungeons and with 2nd Quest's), once its row-7 fix landed (4aa8fc5).
# Nothing is held back now; a value ZORA newly generates waits here for its scan.
HELD_BACK: dict[str, frozenset[int]] = {}
CHOICE, THREE_STATE, SWITCH = "choice", "three_state", "switch"
# A switch's two values; every on/off/random value is labelled as on the page (zora/flags/fields.py).
SWITCH_STATES = (ThreeState.OFF, ThreeState.ON)


@dataclass(frozen=True)
class OptionSpec:
    """One ZORA flag field as an Archipelago option: its key (its name in a player's YAML,
    stable from beta 3 on: option_key), its id (a Z1R field's, "C01" or "B08", or a ZORA flag's
    name), name and description; its kind ("choice"; "three_state": off, on, or random per
    seed; "switch": off or on); the values it offers, each with a label (only values ZORA
    generates: the support matrix's, "?" only where it allows one); and the default.
    value_keys pairs each offered value with its key (its name in a player's YAML, stable from
    beta 3 on: value_key), in the order of choices; the labels may change, the keys never."""
    key: str
    id: str
    name: str
    description: str
    kind: str
    choices: tuple[tuple[int, str], ...]
    default: int
    value_keys: tuple[tuple[int, str], ...] = ()

    @property
    def values(self) -> tuple[int, ...]:
        return tuple(value for value, _label in self.choices)

    def value_of_key(self, key: str) -> int | None:
        """The offered value this key names, or None."""
        return next((value for value, value_key in self.value_keys if value_key == key), None)


class OptionsConflict(ValueError):
    """Option values ZORA refuses together (a dependency rule), named for the player."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("ZORA cannot generate these options: " + "; ".join(reasons))
        self.reasons = reasons


# Words a key spells differently from the community's flag names (owner, before beta 3 froze the
# keys): force_ganon_fight, shuffle_ganon_and_zelda, set_ganon_hp_to_0.
KEY_SPELLINGS = {"gannon": "ganon"}


def key_of(name: str) -> str:
    """An option key from a name: its words in lowercase, joined by underscores ("Level 9 Entry":
    level_9_entry; '"Most" Enemy HP': most_enemy_hp)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def option_key(field: flag_form.FieldDef) -> str:
    """A Z1R field's option key: its community name (docs/spec/flag-names-reference.csv, as
    zora/flags/names.json holds it; the spec label where it has none) by key_of, never its code.
    Stable from beta 3 on: tests/test_archipelago_option_keys.py pins every key, so renaming a
    flag on the page never renames an option. A key spells a word as the game does
    (KEY_SPELLINGS: the community's "Gannon" is Ganon in a key); the page's labels keep the
    community's wording."""
    name = str(flag_form.owner_names().get(field.id, {}).get("name") or flag_form.spec_field_label(field))
    return "_".join(KEY_SPELLINGS.get(word, word) for word in key_of(name).split("_"))


# --- value keys (stable from beta 3 on) ---------------------------------------------------------------

# Archipelago reserves a choice named "random" for "Archipelago picks one", so ZORA's own Random
# (resolved per seed from the seed, FL-DEP-04) is random_per_seed in every key.
RANDOM_PER_SEED = "random_per_seed"
THREE_STATE_KEYS = {ThreeState.OFF: "off", ThreeState.ON: "on", ThreeState.POSSIBLE: RANDOM_PER_SEED}
# A key spells out what a label abbreviates; ordinals become words, so no key starts with a digit.
VALUE_SPELLINGS = (("+/-", " plus minus "), ("+", " plus "), ("%", " percent "))
VALUE_WORDS = {"1st": "first", "2nd": "second", "random": RANDOM_PER_SEED}
# A label that is only a number gets its option's unit first ("3" in Starting Hearts: hearts_3).
VALUE_UNITS = {"C16": "hearts", "C17": "items", "C18": "pieces", "C20": "hearts", "C21": "hearts",
               "C22": "hearts", "C23": "hearts", "C24": "triforces", "C25": "triforces"}
DEFAULT_VALUE_UNIT = "value"              # a new field's number labels, until it is given a unit
# Keys the rule below would spell unevenly (Level 9 Entry's "1 triforce", Starting Hearts' range).
VALUE_KEY_OVERRIDES = {("C08", 7): "triforces_1", ("C16", 16): "hearts_1_to_5"}


def value_key(label: str, unit: str | None = None) -> str:
    """A value's key from its label: its words by key_of, abbreviations spelled out, ordinals as
    words, Random as random_per_seed, and a leading number moved last behind its unit or noun
    ("Mixed Quest - 1st": mixed_quest_first; "+/- 2": plus_minus_2; "8 triforces": triforces_8;
    "0 HP": hp_0; "3" with unit hearts: hearts_3, without one value_3)."""
    text = label
    for written, spelled in VALUE_SPELLINGS:
        text = text.replace(written, spelled)
    words = [VALUE_WORDS.get(word, word) for word in key_of(text).split("_")]
    if words[0].isdigit():
        if len(words) == 1:
            words = [unit or DEFAULT_VALUE_UNIT, *words]
        else:
            words = [*words[1:], words[0]]
    return "_".join(words)


def _z1r_value_keys(field: flag_form.FieldDef) -> dict[int, str]:
    """Every value of a Z1R field (offered or not) and its key."""
    if not isinstance(field, OptionField):
        return {int(state): key for state, key in THREE_STATE_KEYS.items()}
    return {index: VALUE_KEY_OVERRIDES.get((field.id, index))
            or value_key(flag_form.value_label(field, index), VALUE_UNITS.get(field.id))
            for index in range(field.count)}


def _zora_value_keys(field: Mapping[str, Any]) -> dict[int, str]:
    """Every value of a ZORA flag and its key."""
    if field["kind"] == "option":
        return {value["value"]: value_key(value["label"]) for value in field["values"]}
    states = THREE_STATE_KEYS if field["kind"] == zora_form.THREE_STATE_KIND else dict.fromkeys(SWITCH_STATES)
    return {int(state): THREE_STATE_KEYS[state] for state in states}


def option_value_keys() -> dict[str, dict[int, str]]:
    """Each offered option's id and the key of every one of its values, offered or not (a value
    released later keeps the key it has now): docs/archipelago.md "Value keys"."""
    keys = {field.id: _z1r_value_keys(field) for field in flag_form.ALL_FIELDS if field.id not in NOT_OFFERED}
    keys |= {field["name"]: _zora_value_keys(field) for field in zora_form.FIELDS}
    for option, values in keys.items():
        assert len(set(values.values())) == len(values), f"two values of {option} share a key"
    return keys


def _z1r_spec(field: flag_form.FieldDef, defaults: Settings) -> OptionSpec:
    is_option = isinstance(field, OptionField)
    held = HELD_BACK.get(field.id, frozenset())
    choices = tuple((int(value), flag_form.value_label(field, value)) for value in flag_form.supported_values(field)
                    if value not in held)
    preset = defaults.options if is_option else defaults.toggles
    default = int(preset[field.id]) if field.id in preset else choices[0][0]     # a field newer than the preset
    keys = _z1r_value_keys(field)
    return OptionSpec(option_key(field), field.id, flag_form.field_label(field), field.setting,
                      CHOICE if is_option else THREE_STATE, choices, default,
                      tuple((value, keys[value]) for value, _label in choices))


def _zora_spec(field: Mapping[str, Any], defaults: zora_flags.ZoraFlags) -> OptionSpec:
    name = field["name"]
    if field["kind"] == "option":
        kind, choices = CHOICE, tuple((value["value"], value["label"]) for value in field["values"])
    elif field["kind"] == zora_form.THREE_STATE_KIND:
        kind, choices = THREE_STATE, tuple((int(state), label) for state, label in THREE_STATE_LABELS.items())
    else:
        kind, choices = SWITCH, tuple((int(state), THREE_STATE_LABELS[state]) for state in SWITCH_STATES)
    default = zora_form.control_value(defaults, name) if hasattr(defaults, name) else choices[0][0]
    keys = _zora_value_keys(field)
    return OptionSpec(name, name, field["label"], field["help"], kind, choices, default,     # key: its name
                      tuple((value, keys[value]) for value, _label in choices))


def option_fields() -> list[OptionSpec]:
    """Every ZORA flag field Archipelago offers, from zora/flags (the page's fields, labels,
    support matrix and ZORA Extras tab), so a new field appears here by itself: the Z1R fields
    but B82 and C06 (NOT_OFFERED), without the HELD_BACK values, then the ZORA flags."""
    defaults = decode(DEFAULT_FLAGS)
    zora_defaults = zora_flags.decode(DEFAULT_ZORA_FLAGS)
    specs = [_z1r_spec(field, defaults) for field in flag_form.ALL_FIELDS if field.id not in NOT_OFFERED]
    specs += [_zora_spec(field, zora_defaults) for field in zora_form.FIELDS]
    keys = [spec.key for spec in specs]
    assert len(set(keys)) == len(keys), "two options share a key"
    return specs


def option_keys() -> dict[str, str]:
    """Each offered option's id and its key (C16: starting_hearts)."""
    return {spec.id: spec.key for spec in option_fields()}


def _chosen(values: Mapping[str, object]) -> dict[str, int]:
    """Every option's value by id: the given ones (each option by its key or its id, each value
    by its number or its value key, one value the option offers), the rest the defaults."""
    fields = option_fields()
    specs = {spec.id: spec for spec in fields} | {spec.key: spec for spec in fields}
    unknown = sorted(set(values) - set(specs))
    if unknown:
        raise OptionsConflict([f"unknown options {unknown}"])
    twice = sorted(spec.key for spec in fields if spec.key != spec.id and spec.key in values and spec.id in values)
    if twice:
        raise OptionsConflict([f"options given by key and by id: {twice}"])
    chosen = {spec.id: spec.default for spec in fields}
    for name, given in values.items():
        spec = specs[name]
        value = spec.value_of_key(given) if isinstance(given, str) else given
        if not isinstance(value, int) or value not in spec.values:
            names = spec.key if spec.key == spec.id else f"{spec.key}, {spec.id}"
            offered = [f"{number} ({key})" for number, key in spec.value_keys]
            raise OptionsConflict([f"{spec.name} ({names}): {given!r} is not one of {offered}"])
        chosen[spec.id] = int(value)
    return chosen


def _settings(chosen: Mapping[str, int]) -> Settings:
    toggles = {field.id: ThreeState(chosen[field.id]) for field in flag_form.ALL_FIELDS
               if not isinstance(field, OptionField) and field.id != FORCED_OFF}
    options = {field.id: chosen[field.id] for field in flag_form.ALL_FIELDS
               if isinstance(field, OptionField) and field.id not in FIXED_OPTIONS}
    return decode(DEFAULT_FLAGS).updated(options={**options, **FIXED_OPTIONS},
                                         toggles={**toggles, FORCED_OFF: ThreeState.OFF})


def option_corrections(values: Mapping[str, object]) -> list[str]:
    """What ZORA changes in these options, as the page shows it, never refused: FL-DEP-06 turns
    B23 off while B22 is off, and FL-DEP-02 rule 4 turns B28 and B29 off with second-quest,
    mixed or mixed-with-shapes dungeons."""
    asked = _settings(_chosen(values))
    corrected = correct_merchant_toll(asked)
    notes = [flag_form.TOLL_TURNED_OFF_NOTE] if corrected != asked else []
    adjusted = apply_dependencies(corrected)
    notes += [f"FL-DEP-02 rule 4 turns {field_id} off" for field_id in sorted(adjusted.toggles)
              if adjusted.toggle(field_id) != corrected.toggle(field_id)]
    return notes


def flag_strings(values: Mapping[str, object]) -> tuple[str, str]:
    """Archipelago's option values (OptionSpec key or id -> value, by number or value key; a missing
    option takes its default)
    as ZORA's (flag string, ZORA flag string). Every dependency rule is checked here, so a
    refusal never comes later from inside generation: OptionsConflict names each conflict (the
    pin and prerequisite rules, Progressive Items with Extra Candles, Add L4 Sword without
    Progressive Items, Extra Power Bracelet Blocks with B04, the magical sword's heart cap). B23
    with B22 off is corrected instead, as on the page (option_corrections)."""
    chosen = _chosen(values)
    settings = correct_merchant_toll(_settings(chosen))
    zora = zora_flags.decode(zora_form.zora_flags_from_values(
        {field["name"]: chosen[field["name"]] for field in zora_form.FIELDS}))
    reasons = [f"{refusal.rule}: {refusal.message}" for refusal in check_dependencies(settings)]
    reasons += zora_flags.validate(zora, apply_dependencies(settings))
    if reasons:
        raise OptionsConflict(reasons)
    strings = encode(settings), zora_flags.encode(zora)
    try:
        plan(strings[0], 0, strings[1])
    except FlagsRefused as refused:          # the last guard: any rule not named above
        raise OptionsConflict(list(refused.reasons)) from refused
    return strings


# --- player settings (P3) ----------------------------------------------------------------------------

COLOUR, WORD = "colour", "word"
# The page's labels (web/zora-web.js PLAYER_CHOICES, PLAYER_COLOURS and the two word rows, its
# Cosmetic tab); tests/test_archipelago_player_settings.py reads the page and checks it says the same.
# Keys, values, defaults and rules come from zora/rom/player_settings.py, which finish() reads.
PLAYER_SETTING_LABELS = {
    "selectButton": "Select button", "lowHealthBeep": "Low-health beep", "deathWarp": "Death-warp",
    "reduceFlashing": "Reduce flashing", "music": "Music", "statisticsScreen": "Statistics screen",
    "greenTunic": "Green tunic", "blueRingTunic": "Blue ring", "redRingTunic": "Red ring", PAGE_HEART_SLOT: "Hearts",
    PAGE_LEVEL_WORD: "Level name", PAGE_BOSS_SOUND_WORD: "Boss-sound label",
}
PLAYER_CHOICE_LABELS = {
    "selectButton": {"off": "Off", "swap": "Swap only", "toggle": "Toggle"},
    "lowHealthBeep": {"removed": "Removed", "kept": "Kept"},
    "deathWarp": {"p2-up-a": "Controller 2 Up+A", "p1-up-a": "Controller 1 Up+A",
                  "p1-up-select": "Controller 1 Up+Select"},
    "reduceFlashing": {"off": "Off", "on": "On"},
    "music": {"on": "On", "off": "Off"},
    "statisticsScreen": {"on": "On", "off": "Off"},
}
RANDOM_WORD_LABEL = "Random"
# Every NES palette value but $0D (FP-SET-02, FP-SET-03; player_settings.check_palette_value).
ALLOWED_COLOURS = tuple(value for value in range(PALETTE_SIZE) if value != REFUSED_COLOUR)


@dataclass(frozen=True)
class TextRule:
    """A word setting's rule. What the player types loses its outer spaces and becomes capitals;
    the word is then `min_length` to `max_length` of `characters` (the game's font), or `random`
    (the boss-sound label's Random). The level name's label keeps its dash for a word of at most
    `dash_max_length` characters ("LEVEL-1"; "PALACE1")."""
    min_length: int
    max_length: int
    characters: str
    random: str | None = None
    dash_max_length: int | None = None


@dataclass(frozen=True)
class PlayerSettingSpec:
    """One player setting as data: its key (as a recipe's playerSettings holds it; finish() also
    takes it), label and kind: "choice" (one of `choices`, (value, label) pairs), "colour" (one of
    `colours`, NES palette values) or "word" (one of `choices`, or any word `rule` allows); and
    its default. yaml_key is its name in a player's YAML and value_keys pairs each listed value
    with its YAML name (a choice's in underscore words, a colour's as hex, a listed word's in
    lowercase, the boss-sound label's Random as random_word), both stable from beta 3 on;
    finish() and recipe() take either form (page_player_settings)."""
    key: str
    label: str
    kind: str
    default: str | int
    choices: tuple[tuple[str, str], ...] = ()
    colours: tuple[int, ...] = ()
    rule: TextRule | None = None
    yaml_key: str = ""
    value_keys: tuple[tuple[str | int, str], ...] = ()


LEVEL_WORD_RULE = TextRule(1, LEVEL_WORD_MAX_LENGTH, LEVEL_WORD_CHARACTERS, dash_max_length=LEVEL_WORD_DASH_MAX_LENGTH)
BOSS_SOUND_WORD_RULE = TextRule(BOSS_SOUND_WORD_LENGTH, BOSS_SOUND_WORD_LENGTH, BOSS_SOUND_WORD_CHARACTERS,
                                random=RANDOM_BOSS_SOUND_WORD)


# Each player setting's YAML key, by its page key (stable from beta 3 on).
PLAYER_SETTING_KEYS = {
    "selectButton": "select_button", "lowHealthBeep": "low_health_beep", "deathWarp": "death_warp",
    "reduceFlashing": "reduce_flashing", "music": "music", "statisticsScreen": "statistics_screen",
    "greenTunic": "green_tunic", "blueRingTunic": "blue_ring_tunic", "redRingTunic": "red_ring_tunic",
    PAGE_HEART_SLOT: "hearts", PAGE_LEVEL_WORD: "level_word", PAGE_BOSS_SOUND_WORD: "boss_sound_word",
}
RANDOM_WORD_KEY = "random_word"           # the boss-sound label's RANDOM, which the recipe keeps


def colour_key(colour: int) -> str:
    """A colour's value key: its NES palette value in hex ("0x29")."""
    return f"0x{colour:02X}"


def _player_value_keys(kind: str, key: str, values: Iterable[str | int]) -> tuple[tuple[str | int, str], ...]:
    if kind == COLOUR:
        return tuple((value, colour_key(int(value))) for value in values)
    if kind == WORD:
        return tuple((value, RANDOM_WORD_KEY if key == PAGE_BOSS_SOUND_WORD and value == RANDOM_BOSS_SOUND_WORD
                      else str(value).lower()) for value in values)
    return tuple((value, str(value).replace("-", "_")) for value in values)


def player_setting_fields() -> list[PlayerSettingSpec]:
    """Every player setting, in the page's order (P3): the choices, the tunic and heart colours,
    the level name and the boss-sound label. A player's YAML gives each by its key; a recipe's
    playerSettings holds them as given, and finish() and rom_from_recipe accept exactly these."""
    defaults = PlayerSettings()
    assert set(PLAYER_CHOICE_LABELS) == set(PAGE_CHOICES), "a page choice without labels"
    specs = []
    for key, (field, values) in PAGE_CHOICES.items():
        default = next(value for value, setting in values.items() if setting == getattr(defaults, field))
        specs.append(PlayerSettingSpec(key, PLAYER_SETTING_LABELS[key], CHOICE, default,
                                       tuple((value, PLAYER_CHOICE_LABELS[key][value]) for value in values)))
    slots = (*zip(PAGE_TUNIC_SLOTS, defaults.tunic_colours, strict=True), (PAGE_HEART_SLOT, defaults.heart_colour))
    specs += [PlayerSettingSpec(key, PLAYER_SETTING_LABELS[key], COLOUR, default, colours=ALLOWED_COLOURS)
              for key, default in slots]
    specs.append(PlayerSettingSpec(PAGE_LEVEL_WORD, PLAYER_SETTING_LABELS[PAGE_LEVEL_WORD], WORD, defaults.level_word,
                                   tuple((word, word) for word in LEVEL_WORD_CHOICES), rule=LEVEL_WORD_RULE))
    boss_words = ((defaults.boss_sound_word, defaults.boss_sound_word), (RANDOM_BOSS_SOUND_WORD, RANDOM_WORD_LABEL),
                  *((word, word) for word in BOSS_SOUND_WORDS))
    specs.append(PlayerSettingSpec(PAGE_BOSS_SOUND_WORD, PLAYER_SETTING_LABELS[PAGE_BOSS_SOUND_WORD], WORD,
                                   defaults.boss_sound_word, boss_words, rule=BOSS_SOUND_WORD_RULE))
    return [replace(spec, yaml_key=PLAYER_SETTING_KEYS[spec.key], value_keys=_player_value_keys(
        spec.kind, spec.key, spec.colours if spec.kind == COLOUR else (value for value, _label in spec.choices)))
        for spec in specs]


def page_player_settings(values: Mapping[str, Any]) -> dict[str, Any]:
    """Player settings as the page names them (a recipe's playerSettings, as finish() reads them),
    from a player's YAML or a recipe: each setting by its page key (selectButton) or its YAML key
    (select_button), each value as the page has it (p1-up-a, 41, RANDOM) or by its value key
    (p1_up_a, "0x29", random_word). Page forms pass through unchanged, so a recipe written before
    the keys reads as it did; anything else is left for player_settings_from_page to judge."""
    specs = {spec.key: spec for spec in player_setting_fields()}
    by_yaml = {spec.yaml_key: spec for spec in specs.values() if spec.yaml_key != spec.key}
    both = sorted(spec.yaml_key for spec in by_yaml.values() if spec.yaml_key in values and spec.key in values)
    if both:
        raise PlayerSettingError(f"player settings given by YAML key and by page key: {both}")
    page: dict[str, Any] = {}
    for name, value in values.items():
        spec = by_yaml.get(name) or specs.get(name)
        if spec is None:
            page[name] = value
            continue
        page[spec.key] = _page_value(spec, value)
    return page


def _page_value(spec: PlayerSettingSpec, value: Any) -> Any:
    """A value by its value key as the page has it; any other value unchanged. A word is typed
    freely (any case), so only random_word is a key there."""
    if not isinstance(value, str):
        return value
    listed = {key: page_value for page_value, key in spec.value_keys}
    if spec.kind == COLOUR:
        return {key.lower(): colour for key, colour in listed.items()}.get(value.lower(), value)
    if spec.kind == WORD:
        return listed[value] if value == RANDOM_WORD_KEY and value in listed else value
    return listed.get(value, value)


# --- build and finish (spec "Design" 2 and 3) ------------------------------------------------------

class UnknownItem(ValueError):
    """An item name that is not the seed format's name of an item."""


class NotReceivable(ValueError):
    """An item name that is never an Archipelago item (receivable() is False), given to receive()."""


@dataclass(frozen=True)
class PlaceInfo:
    """One place Archipelago may put an item in: its fixed name, its kind ("room", "cellar",
    "cave", "shop ware", "potion shop"), the items it must never hold (by name), and the heart
    containers its cave asks for before handing over its item (the sword caves; R2)."""
    name: str
    kind: str
    forbids: tuple[str, ...]
    hearts: int | None


@dataclass(frozen=True)
class BuildResult:
    """BUILD's answer for Archipelago's generation: the places, the access rules, the items this
    seed adds to the pool (by name, one per place) and `state`, opaque, for finish()."""
    places: tuple[PlaceInfo, ...]
    logic: LogicModel
    pool: tuple[str, ...]
    state: Built


def place_info(place: Place) -> PlaceInfo:
    hearts = next((required.hearts for required in place.requires), None)
    return PlaceInfo(place.name, place.kind.value, tuple(sorted(ITEM_NAMES[item] for item in place.forbids)), hearts)


def checked_rom(rom: bytes) -> bytes:
    """The player's ROM, refused unless it is the PRG0 release, and remembered for ZORA's reads
    of the original game's bytes (base_rom)."""
    if not is_prg0(rom):
        raise BaseRomMismatch("not The Legend of Zelda (USA, PRG0): ZORA needs that exact ROM "
                              "(MD5 337bd6f1a1163df31bf2633665589ab0)")
    remember_base_rom(rom)
    return rom


def build(values: Mapping[str, object], seed: int, rom: bytes) -> BuildResult:
    """BUILD from Archipelago's option values (flag_strings) and ZORA's seed number, which the
    Archipelago world draws from its own random generator, with the player's PRG0 ROM."""
    return build_from_strings(*flag_strings(values), seed, rom)


def build_from_strings(flag_string: str, zora_flag_string: str, seed: int, rom: bytes) -> BuildResult:
    """BUILD from ZORA's two flag strings and seed number, with the player's PRG0 ROM."""
    built = build_seed(plan(flag_string, seed, zora_flag_string), checked_rom(rom))
    return BuildResult(places=tuple(place_info(place) for place in built.places), logic=logic_model(built),
                       pool=tuple(ITEM_NAMES[read_item(built.world, place)] for place in built.places), state=built)


def item_named(name: str) -> Item:
    if name not in ITEMS_BY_NAME:
        raise UnknownItem(f"{name!r} is not an item name of the seed format")
    return ITEMS_BY_NAME[name]


# Owner rulings (beta 3): rupees, regular hearts, fairies, maps, compasses, regular Triforce
# pieces and the clock are never Archipelago items, and the Triforce of Power is the goal event,
# not an item. All but the clock are the items the game's TakeItem does not give through the
# inventory (the "complex" slots, RupeesToAdd and the refills: inventory.give refuses them); the
# clock it does give (InvClock), but it is a pickup's passing effect, not something to send.
NOT_RECEIVABLE = frozenset({"Rupee", "5 Rupees", "Heart", "Fairy", "Map", "Compass", "Triforce",
                            "Triforce of Power", "Clock"})
RECEIVABLE_ITEMS = frozenset(name for name in ITEMS_BY_NAME if name not in NOT_RECEIVABLE)


def receivable(name: str) -> bool:
    """Whether `name` is an Archipelago item: the one list the world builds its item table from
    and receive() gives. False for any name that is not the seed format's."""
    return name in RECEIVABLE_ITEMS


def assigned_items(assignment: Mapping[str, str | Foreign]) -> dict[str, Item | Foreign]:
    """Archipelago's assignment by name as FINISH takes it: item names become items, FOREIGN
    (another player's item) stays."""
    return {place: value if isinstance(value, Foreign) else item_named(value) for place, value in assignment.items()}


def received_items(received: Iterable[str]) -> list[Item]:
    return [item_named(name) for name in received]


def finish(result: BuildResult, assignment: Mapping[str, str | Foreign], received: Iterable[str] = (),
           player_settings: Mapping[str, Any] | None = None, ap_name: bytes | None = None) -> bytes:
    """FINISH: the ROM with Archipelago's items in their places. `received`: this player's items
    that other worlds hold, which the sanity check grants (R4). `player_settings`: the page's
    names (selectButton, greenTunic, ...) or the YAML keys (page_player_settings). `ap_name`: the
    slot name the client logs in with (1 to 23 bytes, no zero byte; rom_identity reads it back),
    written into the ROM, so each slot's seed code differs. Raises AssignmentRefused (a place's
    rule broken), AssignmentUnbeatable (the sanity check) or SlotNameRefused, never a ROM that
    ZORA's walk rejects."""
    record = b"" if ap_name is None else slot_identity.slot_identity_record(ap_name, FORMAT_VERSION_NUMBERS)
    return finish_seed(result.state, player_rom(), assigned_items(assignment),
                       player_settings_from_page(page_player_settings(player_settings or {})),
                       received=received_items(received), check=True, slot_identity=record)


# --- the slot identity (Phase 4c) ------------------------------------------------------------------

RomIdentity = slot_identity.SlotIdentity
SlotNameRefused = slot_identity.SlotNameRefused


def rom_identity(rom: bytes) -> RomIdentity | None:
    """The slot identity a finished .nes file holds (the recipe format version that wrote it and
    the slot name), or None for a ROM without one (ZORA mode, or no ap_name given)."""
    return slot_identity.read_slot_identity(rom)


# --- the recipe (spec "Design" 4) -----------------------------------------------------------------

RECIPE_FORMAT = "zora-ap-recipe"
RECIPE_FORMAT_VERSION = "1.1"             # 1.1 (Phase 4c): apName
FORMAT_VERSION_NUMBERS = (1, 1)           # the same, as the slot identity's two bytes
FOREIGN_JSON = {"foreign": True}          # owner decision 4: no player or item names
HASH_PREFIX = "sha256:"


def _package_files(folder: Traversable, prefix: str = "") -> Iterator[tuple[str, Traversable]]:
    """Every file of the package below `folder`, by its path inside the package, in a fixed
    order; caches and hidden files (a folder's .DS_Store) are not part of it."""
    for entry in sorted(folder.iterdir(), key=lambda entry: entry.name):
        if entry.name.startswith(".") or entry.name == "__pycache__" or entry.name.endswith(".pyc"):
            continue
        path = f"{prefix}{entry.name}"
        if entry.is_dir():
            yield from _package_files(entry, f"{path}/")
        else:
            yield path, entry


def source_hash() -> str:
    """sha256 over this copy of the zora package: each file's path inside it and its bytes, in
    path order, read through importlib.resources, so a folder and a zip (the .apworld) give the
    same hash. A recipe is rebuilt only by a copy with the same hash: output may change between
    builds without a version bump (zora/version.py), so the hash, not the version, is the pin."""
    digest = hashlib.sha256()
    for path, entry in _package_files(files(__package__)):
        data = entry.read_bytes()
        for part in (path.encode(), len(data).to_bytes(8, "big"), data):
            digest.update(part)
    return HASH_PREFIX + digest.hexdigest()


def _assignment_json(assignment: Mapping[str, str | Foreign]) -> dict[str, Any]:
    return {place: dict(FOREIGN_JSON) if isinstance(value, Foreign) else value for place, value in assignment.items()}


def recipe(result: BuildResult, assignment: Mapping[str, str | Foreign], received: Iterable[str] = (),
           player_settings: Mapping[str, Any] | None = None, ap_name: bytes | None = None) -> dict[str, Any]:
    """The recipe a player's machine rebuilds this ROM from with its own PRG0 ROM
    (rom_from_recipe): plain JSON data, no ROM bytes. The producer and seed blocks are the seed
    document's (docs/seed-format/), with this copy's source hash; items by the seed format's
    names; another player's item as {"foreign": true}; the slot name as hex (apName, null
    without one). Unknown names and slot names the ROM cannot hold are refused here, at
    generation, never on the player's machine."""
    assigned_items(assignment)
    received_items(received)
    if ap_name is not None:
        slot_identity.slot_identity_record(ap_name, FORMAT_VERSION_NUMBERS)
    chosen = result.state.plan
    return {
        "format": RECIPE_FORMAT,
        "formatVersion": RECIPE_FORMAT_VERSION,
        "producer": {"name": PLAYER_NAME, "version": ZORA_VERSION, "sourceHash": source_hash()},
        "seed": {"number": str(chosen.seed), "flags": chosen.flag_string, "zoraFlags": chosen.zora_flag_string},
        "playerSettings": page_player_settings(player_settings or {}),
        "assignment": _assignment_json(assignment),
        "received": list(received),
        "apName": None if ap_name is None else ap_name.hex(),
    }


class RecipeRefused(ValueError):
    """A recipe this copy of ZORA does not rebuild: another format, or another ZORA (version or
    source hash), named with this copy's."""


class RecipeNotReproduced(RuntimeError):
    """The rebuilt seed failed the sanity check generation passed: a determinism bug (the same
    copy of ZORA, recipe and ROM must give the same seed), never the player's fault."""


def _recipe_assignment(data: Mapping[str, Any]) -> dict[str, str | Foreign]:
    return {place: FOREIGN if value == FOREIGN_JSON else value for place, value in data.items()}


def check_recipe(data: Mapping[str, Any]) -> None:
    """RecipeRefused unless this copy of ZORA made the recipe's kind of seed."""
    if (data.get("format"), data.get("formatVersion")) != (RECIPE_FORMAT, RECIPE_FORMAT_VERSION):
        raise RecipeRefused(f"not a {RECIPE_FORMAT} {RECIPE_FORMAT_VERSION} recipe: "
                            f"{data.get('format')!r} {data.get('formatVersion')!r}")
    producer = data.get("producer", {})
    made_by = (producer.get("version"), producer.get("sourceHash"))
    running = (ZORA_VERSION, source_hash())
    if made_by != running:
        raise RecipeRefused(f"this recipe was made by ZORA {made_by[0]} ({made_by[1]}), but this is "
                            f"ZORA {running[0]} ({running[1]}): rebuild it with the .apworld that generated it")


def rom_from_recipe(data: Mapping[str, Any], rom: bytes) -> bytes:
    """The ROM a recipe names, made from the player's own PRG0 ROM: BUILD and FINISH as at
    generation, with the same sanity check (RecipeNotReproduced if it now fails)."""
    check_recipe(data)
    seed = data["seed"]
    result = build_from_strings(seed["flags"], seed["zoraFlags"], int(seed["number"]), rom)
    try:
        ap_name = None if data["apName"] is None else bytes.fromhex(data["apName"])
        return finish(result, _recipe_assignment(data["assignment"]), data["received"], data["playerSettings"],
                      ap_name)
    except (AssignmentRefused, AssignmentUnbeatable) as failure:
        raise RecipeNotReproduced(f"the rebuilt seed fails where generation passed ({failure}): a determinism "
                                  f"bug in ZORA {ZORA_VERSION}; please report it with the recipe") from failure



# --- the client's tables (spec "Design" 5) ----------------------------------------------------------

@dataclass(frozen=True)
class RamCheck:
    """A place's item is taken once `ram[address] & mask` is nonzero."""
    address: int
    mask: int

    def is_set(self, ram: Mapping[int, int]) -> bool:
        return bool(ram[self.address] & self.mask)


def pickup_check(place: Place) -> RamCheck:
    """Where the game records that the place's item was taken: a room's or cellar's item bit in
    its level's room flags, a cave's (and the Armos and coast items') in its overworld screen's,
    and a ware place's ShopBoughtFlags bit (External mode sells every ware place once)."""
    if place.kind in (PlaceKind.ROOM, PlaceKind.CELLAR):
        assert place.level is not None and place.room_num is not None
        return RamCheck(inventory.room_flags(place.level) + place.room_num, inventory.ITEM_TAKEN)
    if place.is_shop:
        assert place.destination is not None and place.position is not None
        return RamCheck(inventory.SHOP_BOUGHT_FLAGS + place.position, 1 << SHOPS_BY_NUMBER.index(place.destination))
    screen = place.screens[0] if place.screens else inventory.COAST_SCREEN
    return RamCheck(inventory.room_flags(0) + screen, inventory.ITEM_TAKEN)


def pickup_checks(result: BuildResult) -> dict[str, RamCheck]:
    """Each place's RamCheck, by place name: the client reports a place collected when its check
    is set (only during normal play: docs/archipelago.md "Interface", when to read and write)."""
    return {place.name: pickup_check(place) for place in result.state.places}


def _give_rules(chosen: GenerationPlan) -> inventory.GiveRules:
    return inventory.GiveRules(progressive_items=chosen.zora.progressive_items,
                               l4_sword=chosen.zora_resolved.is_on("add_l4_sword"),
                               four_potions=chosen.zora_resolved.is_on("four_potion_inventory"))


def give_rules(result: BuildResult) -> inventory.GiveRules:
    """The flags that change how this seed gives an item (receive), as resolved for it."""
    return _give_rules(result.state.plan)


def recipe_give_rules(data: Mapping[str, Any]) -> inventory.GiveRules:
    """give_rules for a recipe's seed: its flags resolve as at generation, and no ROM is needed."""
    seed = data["seed"]
    return _give_rules(plan(seed["flags"], int(seed["number"]), seed["zoraFlags"]))


NO_RULES = inventory.GiveRules()


class ClientNotReady(NoPlayerRom):
    """receive() called in a process that has no player ROM: client_ready(rom) comes first."""


def client_ready(rom: bytes) -> None:
    """Make this process ready to receive items: `rom` is the player's PRG0 ROM (the one
    Archipelago's settings name, not the finished .nes), refused as by build (BaseRomMismatch)
    and remembered, since receive reads the game's own item tables from it. A client calls it
    once, before its first receive(), whenever it starts on its own or restarts mid-game; a
    process that built or finished a seed (build, rom_from_recipe) has remembered it already."""
    checked_rom(rom)


def receive(item: str, ram: Mapping[int, int], rules: inventory.GiveRules = NO_RULES) -> dict[int, int]:
    """The RAM writes that give a received item as the game gives a picked-up one (address ->
    value; `ram` holds at least the inventory, $0657-$067C): a line item at its next level with
    Progressive Items (Add L4 Sword: a sword at level 3 gives 4), else the higher of the two
    grades; a heart container one more container and one more heart; an amount added within its
    cap. Another player's item is never received. Call it only during normal play, and only
    after client_ready(rom) (or a build in this process): ClientNotReady otherwise. UnknownItem
    for a name that is no item, NotReceivable for one that is never an Archipelago item."""
    given = item_named(item)
    if not receivable(item):
        raise NotReceivable(f"{item!r} is never an Archipelago item")
    try:
        return inventory.give(given, ram, rules)
    except NoPlayerRom as missing:
        raise ClientNotReady("receive() needs the player's PRG0 ROM: call "
                             "archipelago.client_ready(rom) once before the first receive()") from missing


def may_receive(ram: Mapping[int, int]) -> bool:
    """Whether the client may write a received item now: in normal play only, never during a
    transition, the item screen, a pause, an item being lifted or text (`ram` holds
    inventory.RECEIVE_STATE's addresses). Pickup checks may be read at any time in play."""
    return inventory.may_receive(ram)



# --- the received count and the goal (Phase 4c) ------------------------------------------------------

RECEIVE_STATE = inventory.RECEIVE_STATE
# The saved count of items the client has given (Items+$24, saved with the file, 0 in a new file):
# when may_receive, give item number `count` with receive and write count + 1 in the same writes.
RECEIVED_COUNT = inventory.RECEIVED_COUNT
GOAL_STATE = inventory.GOAL_STATE


def goal_reached(ram: Mapping[int, int]) -> bool:
    """Whether the player has won: Zelda rescued (`ram` holds GOAL_STATE's addresses). True from
    the frame Link reaches Zelda through the ending (mode $13); never before, and false again
    once the game leaves the ending, so the client reports the goal the first time it sees it."""
    return inventory.goal_reached(ram)


# --- when the pickup checks hold the loaded file ------------------------------------------------------

CHECKS_STATE = inventory.CHECKS_STATE


def checks_readable(ram: Mapping[int, int]) -> bool:
    """Whether the pickup flags (pickup_checks) hold the loaded save file (`ram` holds
    CHECKS_STATE's addresses): true from the frame a chosen file's flags are loaded (mode 2) until
    the game leaves it (a reset's RAM clear, a save, or the title and file-select screens), and
    never before the reset code has run since power-on, while RAM holds whatever it powered on
    with. A pickup check read while this is false means nothing: the flags may be garbage, zero, or
    another file's. may_receive is true only in play, which this also covers once the game has
    started; a client asks both before it writes (docs/archipelago.md "Interface")."""
    return inventory.checks_readable(ram)


# --- client_step: the client's decisions as one pure function (beta 3) ------------------------------
# docs/design/archipelago-client-step.md, with the Archipelago planning session's review: the
# world's client reads the bytes the tables list, calls client_step and does what the Decision says;
# every rule about what to report, write or send lives here. docs/archipelago.md "client_step".

CLIENT_TABLES_FORMAT = "zora-ap-client-tables"
CLIENT_TABLES_VERSION = 1
MAX_READ_LENGTH = 252                     # bytes per read: a console bridge's read limit
# The state bytes every predicate here reads (checks_readable, may_receive, goal_reached): one
# scattered read, made first and again last (the bracket).
STATE_ADDRESSES = tuple(sorted({*CHECKS_STATE, *RECEIVE_STATE, *GOAL_STATE}))
# The inventory ($0657-$067E, with the received count and ShopBoughtFlags) and the world flags
# ($067F-$07FE, every pickup check), as (first address, length) reads of MAX_READ_LENGTH or less.
_BLOCK_START, _BLOCK_END = inventory.ITEMS, inventory.WORLD_FLAGS + 3 * inventory.WORLD_FLAGS_SIZE
READ_RANGES = tuple((start, min(MAX_READ_LENGTH, _BLOCK_END - start))
                    for start in range(_BLOCK_START, _BLOCK_END, MAX_READ_LENGTH))

Guard = tuple[int, int]                   # (address, the value the write expects there)
Write = tuple[int, int]                   # (address, value)


@dataclass(frozen=True)
class ClientTables:
    """What client_step needs of a seed, made once: each place's pickup check (by place name,
    pickup_checks), the seed's give rules (give_rules), and the reads a client makes each poll:
    `state_addresses` first, then each of `ranges` ((first address, length), each at most
    MAX_READ_LENGTH bytes), then `state_addresses` again."""
    checks: Mapping[str, RamCheck]
    rules: inventory.GiveRules
    state_addresses: tuple[int, ...] = STATE_ADDRESSES
    ranges: tuple[tuple[int, int], ...] = READ_RANGES

    def addresses(self) -> tuple[int, ...]:
        """Every byte client_step reads, sorted."""
        return tuple(sorted({*self.state_addresses,
                             *(address for start, length in self.ranges for address in range(start, start + length))}))


class ClientTablesRefused(ValueError):
    """Client tables in JSON that this copy of ZORA does not read (another format or version, or
    a malformed entry)."""


def client_tables_of(result: BuildResult) -> ClientTables:
    """A built seed's client tables."""
    return ClientTables(pickup_checks(result), give_rules(result))


def client_tables(recipe_data: Mapping[str, Any]) -> ClientTables:
    """A recipe's client tables (ZORA's tests): its seed rebuilt with the PRG0 ROM this process
    remembered (client_ready, or a build)."""
    check_recipe(recipe_data)
    seed = recipe_data["seed"]
    return client_tables_of(build_from_strings(seed["flags"], seed["zoraFlags"], int(seed["number"]), player_rom()))


def client_tables_to_json(result: BuildResult) -> dict[str, Any]:
    """The client tables as plain JSON for Archipelago's slot data: small and versioned. Each
    check as [place name, address, mask]; the give rules by name. The reads are ZORA's constants
    (client_tables_from_json restores them)."""
    rules = give_rules(result)
    return {
        "format": CLIENT_TABLES_FORMAT,
        "version": CLIENT_TABLES_VERSION,
        "checks": [[name, check.address, check.mask] for name, check in pickup_checks(result).items()],
        "rules": {"progressiveItems": rules.progressive_items, "l4Sword": rules.l4_sword,
                  "fourPotions": rules.four_potions},
    }


def client_tables_from_json(data: Mapping[str, Any]) -> ClientTables:
    """ClientTables from client_tables_to_json's form; ClientTablesRefused for another format or
    version, or a malformed entry."""
    if (data.get("format"), data.get("version")) != (CLIENT_TABLES_FORMAT, CLIENT_TABLES_VERSION):
        raise ClientTablesRefused(f"not {CLIENT_TABLES_FORMAT} version {CLIENT_TABLES_VERSION}: "
                                  f"{data.get('format')!r} {data.get('version')!r}")
    try:
        checks = {str(name): RamCheck(int(address), int(mask)) for name, address, mask in data["checks"]}
        rules = data["rules"]
        give = inventory.GiveRules(progressive_items=bool(rules["progressiveItems"]), l4_sword=bool(rules["l4Sword"]),
                                   four_potions=bool(rules["fourPotions"]))
    except (KeyError, TypeError, ValueError) as malformed:
        raise ClientTablesRefused(f"malformed client tables: {malformed}") from malformed
    return ClientTables(checks, give)


@dataclass(frozen=True)
class ReceivedItem:
    """One entry of the server's received-items list for this slot, in its order: ZORA's item
    name (item_named takes it) and, only when the finding player is this slot, the place it was
    found at, by place name (None for another world's item or a server-given one)."""
    name: str
    location: str | None = None


@dataclass(frozen=True)
class ServerView:
    """What the server has said, as of this poll: every item received for this slot in its order,
    this slot's places it holds as checked, and whether it already has this slot's goal."""
    received: tuple[ReceivedItem, ...] = ()
    checked: frozenset[str] = frozenset()
    goal_known: bool = False


@dataclass(frozen=True)
class ClientMemory:
    """What the client carries from one poll to the next (start with ClientMemory()); all of it
    may be lost safely. reported: places sent and not yet in the server's checked set;
    awaiting_count: the received count the last writes set, until RAM shows it; goal_sent: the
    goal was sent at least once."""
    reported: frozenset[str] = frozenset()
    awaiting_count: int | None = None
    goal_sent: bool = False


NO_MEMORY = ClientMemory()                # what a client starts with (or restarts mid-game with)


@dataclass(frozen=True)
class Decision:
    """client_step's answer for one poll. readable: the snapshot held the loaded file; report:
    places to send now (LocationChecks); writes and guards: RAM writes to make, in order, with
    Archipelago's guarded_write(writes, guards), never a plain write (at most 2 writes and 11
    guards of one byte each); gives / skips / cannot_give: the received item the writes give, or
    count without giving (already held), or count without giving because it is no item ZORA gives
    (receivable() is False, or no item name at all); goal: send the goal now; memory: for the next
    poll, kept only when the guarded write succeeded or there was nothing to write."""
    readable: bool
    report: tuple[str, ...] = ()
    writes: tuple[Write, ...] = ()
    guards: tuple[Guard, ...] = ()
    gives: str | None = None
    skips: str | None = None
    cannot_give: str | None = None
    goal: bool = False
    memory: ClientMemory = NO_MEMORY


class _RecordedReads(Mapping[int, int]):
    """A RAM mapping that remembers which addresses were read (receive's guards)."""

    def __init__(self, ram: Mapping[int, int]) -> None:
        self.ram = ram
        self.read: dict[int, int] = {}

    def __getitem__(self, address: int) -> int:
        self.read[address] = self.ram[address]
        return self.read[address]

    def __iter__(self) -> Iterator[int]:
        return iter(self.ram)

    def __len__(self) -> int:
        return len(self.ram)


def _bracket_holds(ram: Mapping[int, int], ram_after: Mapping[int, int]) -> bool:
    """Both reads of the state bytes hold the loaded file, the same save slot and game mode: the
    snapshot between them is one file's, in one mode."""
    return (checks_readable(ram) and checks_readable(ram_after)
            and ram[inventory.CUR_SAVE_SLOT] == ram_after[inventory.CUR_SAVE_SLOT]
            and ram[inventory.GAME_MODE] == ram_after[inventory.GAME_MODE])


def client_step(ram: Mapping[int, int], ram_after: Mapping[int, int], server: ServerView, tables: ClientTables,
                memory: ClientMemory = NO_MEMORY) -> Decision:
    """The client's decisions for one poll, pure: `ram` holds the bytes of tables.addresses() as
    read this poll (the state bytes first, then the ranges), `ram_after` the state bytes read
    again last. In order:
      1. Unless both reads hold the loaded file with the same save slot and game mode, nothing:
         no report, writes or goal (memory kept, but for the awaited count, dropped).
      2. Each place whose pickup check is set and that is neither checked by the server nor
         reported and awaiting it, in tables.checks' order.
      3. The goal while goal_reached in both reads and the server does not know it.
      4. While may_receive in both reads, the server's next item, one per poll: number `count`
         (RECEIVED_COUNT) of server.received. If it is no item ZORA gives (receivable() is
         False), only the count goes up (cannot_give): the client moves on, never raising for a
         received item. If it was found at one of this slot's places whose pickup check is set in
         the loaded file, the game gave it already: only the count goes up (skips). Else
         receive's writes, then the count (gives). Nothing while the count the last writes set is
         not yet in RAM (one poll).
    The writes depend on the guards' bytes only: RECEIVE_STATE (as `ram_after` holds it), the
    count, and the inventory bytes receive read or writes (or the pickup flag, for a skip)."""
    if not _bracket_holds(ram, ram_after):
        return Decision(readable=False, memory=replace(memory, awaiting_count=None))
    reported = memory.reported - server.checked
    report = tuple(name for name, check in tables.checks.items()
                   if check.is_set(ram) and name not in server.checked and name not in reported)
    goal = goal_reached(ram) and goal_reached(ram_after) and not server.goal_known
    next_memory = ClientMemory(reported | frozenset(report), memory.awaiting_count, memory.goal_sent or goal)
    decision = Decision(readable=True, report=report, goal=goal, memory=next_memory)
    if not (may_receive(ram) and may_receive(ram_after)):
        return decision
    count = ram[RECEIVED_COUNT]
    if memory.awaiting_count is not None and memory.awaiting_count != count:
        return replace(decision, memory=replace(next_memory, awaiting_count=None))   # wait one poll
    if count >= len(server.received):
        return replace(decision, memory=replace(next_memory, awaiting_count=None))
    item = server.received[count]
    guards = {address: ram_after[address] for address in RECEIVE_STATE}
    guards[RECEIVED_COUNT] = count
    check = tables.checks.get(item.location) if item.location is not None else None
    if not receivable(item.name):
        writes: tuple[Write, ...] = ((RECEIVED_COUNT, count + 1),)
        gives, skips, cannot_give = None, None, item.name
    elif check is not None and check.is_set(ram):
        guards[check.address] = ram[check.address]
        writes = ((RECEIVED_COUNT, count + 1),)
        gives, skips, cannot_give = None, item.name, None
    else:
        recorded = _RecordedReads(ram)
        given = receive(item.name, recorded, tables.rules)
        guards |= recorded.read
        writes = (*sorted(given.items()), (RECEIVED_COUNT, count + 1))
        gives, skips, cannot_give = item.name, None, None
    return replace(decision, writes=writes, guards=tuple(sorted(guards.items())), gives=gives, skips=skips,
                   cannot_give=cannot_give, memory=replace(next_memory, awaiting_count=count + 1))


# --- player settings, checked (for the world) -----------------------------------------------------------

def player_setting_problem(spec_key: str, value: Any) -> str | None:
    """What is wrong with one player setting's value (by its page key or YAML key, the value in
    the page's form or by its value key), or None when finish() accepts it."""
    try:
        check_player_settings({spec_key: value})
    except PlayerSettingError as problem:
        return str(problem)
    return None


def check_player_settings(values: Mapping[str, Any]) -> None:
    """PlayerSettingError unless finish() accepts these player settings as they are: every key a
    player setting's (page or YAML key, not both), every value one it takes."""
    known = {key for spec in player_setting_fields() for key in (spec.key, spec.yaml_key)}
    unknown = sorted(str(key) for key in values if key not in known)
    if unknown:
        raise PlayerSettingError(f"unknown player settings: {unknown}")
    player_settings_from_page(page_player_settings(values))
