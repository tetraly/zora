"""The flag form: everything the web page builds its controls from.

The page (web/zora-web.js) has no field list of its own. Its worker calls
`metadata()` once and `form_state()` / `form_change()` as the player edits,
and renders what comes back, so the controls cannot drift from zora/flags/:
the fields, their option meanings (flags-behavior.md FL-ENC-04 and
FL-ENC-05), the presets (FL-PRE), the dependency rules (FL-DEP-01/02, judged
by `flags.check_dependencies`, never re-implemented in JavaScript) and the
support matrix (FL-SUP-01). Every result is plain JSON data.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from functools import cache
from typing import Any

from ..generate.pipeline import NOT_PRODUCED_PREFIX, FlagsRefused, plan
from ..rom import level_encoding
from ..rom.link_art import ART_BLOCKS, link_sprite_set_object, offered_sprite_sets
from ..rom.link_art import FILE_FORMAT as LINK_ART_FILE_FORMAT
from ..rom.link_sprite import FILE_FORMAT as LINK_SPRITE_FILE_FORMAT
from ..rom.link_sprite import FILE_VERSION as LINK_SPRITE_FILE_VERSION
from ..rom.link_sprite import (
    LINK_FIXED_COLORS,
    LINK_HALVES,
    LINK_TILE_GROUPS,
    SPRITE_SET_SIZE,
)
from ..rom.player_settings import (
    BOSS_SOUND_WORD_CHARACTERS,
    BOSS_SOUND_WORD_LENGTH,
    BOSS_SOUND_WORDS,
    DEFAULT_BOSS_SOUND_WORD,
    DEFAULT_LEVEL_WORD,
    LEVEL_WORD_CHARACTERS,
    LEVEL_WORD_CHOICES,
    LEVEL_WORD_DASH_MAX_LENGTH,
    LEVEL_WORD_MAX_LENGTH,
    MARKER_HIDING_COLORS,
    RANDOM_BOSS_SOUND_WORD,
    RANDOM_COLOR,
    RANDOM_LEVEL_WORD,
)
from ..version import PLAYER_VERSION
from . import beta
from .codec import ALPHABET, FlagStringError, canonicalize, decode, encode
from .dependencies import apply_dependencies, check_dependencies
from .fields import (
    BOMB_UPGRADE_PERSON_SHUFFLE,
    ENCODE_LEVEL_DATA,
    HUNGRY_GORIYA_SHUFFLE,
    INERT_TOGGLES,
    ITEM_SHUFFLE_SCOPE,
    LEVEL_9_REQUIREMENT,
    MAGICAL_SWORD_HIGHEST_BASE,
    MAGICAL_SWORD_LOWEST_BASE,
    MAX_TRIFORCE_PIECES,
    OPTION_FIELDS,
    PIECE_RANGE_HIGH,
    PIECE_RANGE_LOW,
    PRINT_QUEST_INFO,
    STARTING_HEARTS,
    STARTING_HEARTS_RANDOM,
    THREE_STATE_LABELS,
    TOGGLE_FIELDS,
    WHITE_SWORD_HIGHEST_BASE,
    WHITE_SWORD_LOWEST_BASE,
    ItemShuffleScope,
    Level9Requirement,
    OptionField,
    PinnedItem,
    Settings,
    ThreeState,
    ToggleField,
)
from .presets import MVP_BASELINE_LEVEL_ENCODING_OFF, PRESETS, ZORA_PRESETS
from .support import (
    ENCODE_LEVEL_DATA_RANDOM_NOTICE,
    POSTPONED_TOGGLES,
    Support,
    encode_level_data_is_random,
    is_postponed,
    mvp_baseline_settings,
    postponed_notices,
    support,
)
from .zora_flags import (
    NO_VANILLA_ITEM_SHUFFLES,
    SWORDLISH_FIELD,
    SpoilerLevel,
    Swordlish,
    ZoraFlags,
    ZoraFlagStringError,
    spoiler_level,
)
from .zora_flags import decode as decode_zora
from .zora_flags import encode as encode_zora
from .zora_form import FIELDS as ZORA_FIELDS
from .zora_form import THREE_STATE_KIND, control_value, zora_flags_from_values, zora_metadata, zora_state

NOT_PRODUCED_TEXT = "Not produced by ZORA yet"
NOT_AVAILABLE_TEXT = "Not available in this build"
CURRENT_NOT_PRODUCED_TEXT = "This value is not produced by ZORA yet"
# Triforce Range (C24, C25) is read only by Level 9 Entry's Triforce Range and Specific Triforces, and
# by Random, which can pick either (FP-TRIF-04, FP-TRIF-05; FL-ALT-06): under any other value the page
# locks it, so nobody sets it expecting it to change the count (a player report, beta 7)
RANGE_READERS = frozenset({Level9Requirement.RANDOM_COUNT_IN_RANGE, Level9Requirement.SPECIFIC_PIECES,
                           Level9Requirement.RANDOM})
RANGE_UNUSED_TEXT = ("No effect: only Level 9 Entry = Triforce Range or Specific Triforces (or Random) uses the "
                     "range. Level 9 Entry sets how many pieces level 9 asks for.")
# ZORA's Level 9 Entrance = Level 4 sword decides level 9's entrance itself (zora_flags.asnb_conflicts)
LEVEL_9_ENTRY_BY_SWORD_TEXT = ("Level 9 Entrance = Level 4 sword (ZORA Extras) decides what level 9's entrance "
                               "asks for: four sword upgrades")

# Owner rulings: the page may call the MVP baseline "Consternation", and calls published variants A
# and C by their community names, "Consternation Remastered" and "Hopla" (presets.HOPLA; beta 5),
# both with level encoding on as published.
PRESET_LABELS = {"MVP baseline": "Consternation", "Published variant A": "Consternation Remastered",
                 "Published variant C": "Hopla"}
# Kept in presets.py but not on the menu (owner, beta 5): Random%, published variant B. ZORA produces
# every field of it since the beta 8 export (flags-behavior.md FL-SUP-01); it stays off the menu.
HIDDEN_PRESETS = frozenset({"Published variant B"})
# CP-5: the MVP baseline with level encoding off. Listed with the presets so
# a build without level encoding has a preset it can produce.
LEVEL_ENCODING_OFF_PRESET = ("MVP baseline, level encoding off", "Consternation without level encoding",
                             MVP_BASELINE_LEVEL_ENCODING_OFF)

# The dependency rules as the page lists them; the check itself is flags.check_dependencies.
DEPENDENCY_RULES = (
    ("FL-DEP-01 rule 1", "The Ladder cannot be pinned to the coast cave."),
    ("FL-DEP-01 rule 2", "No item may be pinned to two places."),
    ("FL-DEP-01 rule 3", ("Set Ganon HP to 0 (B41) and Maximum Boss Health (B46) cannot both be on; when one "
                          "or both are random, a seed never turns both on.")),
    ("FL-DEP-01 rule 5", ("Level 9 Item 1 or 2 at the Bow, the Ladder, the Power Bracelet, the Raft or the "
                          "Recorder, or at the Wand with Swords at Swordless or Random, needs Allow Important "
                          "Items in 9 (B25) on; at Random it is on.")),
    ("FL-DEP-02 rule 1", ("Moving the wooden-sword cave (B02) or shuffling the take-any-road caves (B04) "
                          "needs a cave shuffle that moves non-dungeon caves; when it has none, each seed "
                          "either moves them too or leaves the wooden-sword and take-any-road caves in place, "
                          "with equal chance.")),
    ("FL-DEP-02 rule 2", ("Shuffling the hungry goriya (B28), moving the start room (B26) and Ganon must be "
                          "beaten (B18) need the dungeon room shuffle; when it is off, each seed either turns "
                          "it on (within each dungeon) or turns them off, with equal chance.")),
    ("FL-DEP-02 rule 3", ("Moving monsters between levels (B36) and Ganon and Zelda in the shuffles (B33) "
                          "need the dungeon monster shuffle (B32); when it is off, each seed either turns it "
                          "on or turns them off, with equal chance.")),
    ("FL-DEP-02 rule 4", ("Second-quest, mixed, and mixed-with-shapes dungeons turn the hungry-goriya and "
                          "bomb-upgrade-person shuffles (B28, B29) off.")),
)

_PINNED_ITEM_LABELS = (
    "None pinned", "Book of Magic", "Wooden Boomerang", "Bow", "Heart Container", "Ladder",
    "Magical Boomerang", "Magical Key", "Power Bracelet", "Raft", "Recorder", "Red Candle", "Red Ring",
    "Silver Arrow", "Wand", "White Sword", "Any item except a Heart Container",
)
_HIT_POINT_LABELS = ("Normal", "Each moves by up to 2", "Each moves by up to 4", "All zero", "Random")

# FL-ENC-04 "Index meanings", one label per index.
_OPTION_LABELS: dict[str, tuple[str, ...]] = {
    "C01": ("First quest", "Second quest", "Mixed (first-quest variant)", "Mixed (second-quest variant)",
            "Random"),
    "C02": ("First quest", "Second quest", "Mixed", "Generated shapes", "Mixed with shapes",
            "Random without shapes", "Random"),
    "C03": ("Normal", "Helpful", "Community", "Deceptive", "Mixed", "Blank", "Random"),
    "C04": ("Normal", "Easy shuffle", "Full shuffle", "Wooden-sword screen"),
    "C05": ("Vanilla", "Dungeon doors only", "Non-dungeon caves only", "All caves", "Random"),
    "C06": ("None", "Dungeon items only", "Within each dungeon",
            "Full (dungeons, caves and overworld together)", "Random"),
    "C07": ("Normal", "Wooden sword only", "No wooden sword", "Swordless", "Random"),
    "C08": (*(f"{MAX_TRIFORCE_PIECES - i} pieces" if i < 7 else "1 piece" for i in range(8)),
            "Level 9 is open", "Random count inside the range", "Specific pieces", "An item instead of pieces",
            "Random"),
    "C09": _HIT_POINT_LABELS,
    "C10": _HIT_POINT_LABELS,
    "C11": _PINNED_ITEM_LABELS,
    "C12": _PINNED_ITEM_LABELS,
    "C13": _PINNED_ITEM_LABELS,
    "C14": ("Vanilla", "Within each dungeon", "Full (rooms trade between dungeons)", "Random"),
    "C15": ("Normal", "Fun percentage", "Sprite shuffle", "Random"),
    "C16": (*(f"{i + 1} heart" + ("s" if i else "") for i in range(16)), "Random, 1 to 5"),
    "C17": ("All chosen start items", *(f"At most {i - 1}" for i in range(1, 22)), "Random limit, 0 to 20"),
    "C18": (*(f"{i} piece" + ("" if i == 1 else "s") for i in range(MAX_TRIFORCE_PIECES + 1)),
            "Random, 0 to 8"),
    "C19": ("Vanilla (takes the sword away)", "Inverted controls", "Slow speed", "Random"),
    "C20": tuple(f"{WHITE_SWORD_LOWEST_BASE + i} hearts" for i in range(3)),
    "C21": tuple(f"{WHITE_SWORD_HIGHEST_BASE - i} hearts" for i in range(3)),
    "C22": tuple(f"{MAGICAL_SWORD_LOWEST_BASE + i} hearts" for i in range(5)),
    "C23": tuple(f"{MAGICAL_SWORD_HIGHEST_BASE - i} hearts" for i in range(5)),
    "C24": tuple(str(i) for i in range(MAX_TRIFORCE_PIECES + 1)),
    "C25": tuple(str(MAX_TRIFORCE_PIECES - i) for i in range(MAX_TRIFORCE_PIECES + 1)),
    "C26": _PINNED_ITEM_LABELS,
    "C27": _PINNED_ITEM_LABELS,
}
assert len(_PINNED_ITEM_LABELS) == len(PinnedItem)

FieldDef = OptionField | ToggleField
ALL_FIELDS: tuple[FieldDef, ...] = (*OPTION_FIELDS, *TOGGLE_FIELDS)
FIELDS_BY_ID: dict[str, FieldDef] = {field.id: field for field in ALL_FIELDS}


def field_values(field: FieldDef) -> tuple[int, ...]:
    """The values a field's control offers: every option index, or the three states; Encode
    level data offers on and off only (owner ruling, 2026-10-06: a two-state switch)."""
    if isinstance(field, OptionField):
        return tuple(range(field.count))
    if field == ENCODE_LEVEL_DATA:
        return (ThreeState.OFF, ThreeState.ON)
    return tuple(ThreeState)


# FL-DEP-05's two fields keep the community's names, marked so a player knows they change nothing
# (owner request, 2026-10-10).
NO_EFFECT_SUFFIX = " (no effect in ZORA)"

# A short note the page shows beside a value whose community name could mislead (owner request,
# 2026-10-10): the original randomizer's labels stay, the note says what the value does.
# The pinned-item fields' (C11-C13, C26, C27) "No item pinned" beside Random was taken out so Dungeon Items
# fits (issue #15 review).
VALUE_NOTES: dict[tuple[str, int], str] = {
    (ITEM_SHUFFLE_SCOPE.id, ItemShuffleScope.DUNGEON_ITEMS_ONLY): "Major items only; Heart Containers stay in place",
    (STARTING_HEARTS.id, STARTING_HEARTS_RANDOM): "One random count from 1 to 5",
    (LEVEL_9_REQUIREMENT.id, Level9Requirement.ITEM_INSTEAD_OF_PIECES):
        "Level 9 opens for an item instead of Triforce pieces",
}

# Item Shuffle: Random (No Vanilla) (owner, 2026-10-29): Item Shuffle's sixth choice on the page, after Random. No
# Z1R string holds it: it stands for Item Shuffle: Random (C06 = 4) with the ZORA field item_shuffle_no_vanilla on,
# which narrows Random's draw to Item Only, Intra-Dungeon and Full (zora_flags.resolve_item_shuffle_no_vanilla).
# The page's C06 control holds it like any value; form_change writes both strings.
ITEM_SHUFFLE_NO_VANILLA_CHOICE = ItemShuffleScope.RANDOM + 1
ITEM_SHUFFLE_NO_VANILLA_LABEL = "Random (No Vanilla)"

# Spoiler Log Detail Level (owner rulings, 2026-11-06; docs/design/spoiler-levels.md): the page's one setting for
# Print Quest Info (B51) and the ZORA field Detailed Spoiler Log. Its control is B51's, holding B51's three states
# for None, Basic and Random, and two page-only values for Medium (B51 off, the ZORA field on) and Full (both on).
# Random is B51's "?", which resolves to Basic, Medium or Full (pipeline.resolve_spoiler_level). The names stay
# on the page: the seed document and the log keep B51's own.
SPOILER_LEVEL_LABEL = "Spoiler Log Detail Level"
SPOILER_MEDIUM_CHOICE = int(ThreeState.POSSIBLE) + 1
SPOILER_FULL_CHOICE = SPOILER_MEDIUM_CHOICE + 1
SPOILER_LEVEL_CHOICES = {int(ThreeState.OFF): SpoilerLevel.NONE, int(ThreeState.ON): SpoilerLevel.BASIC,
                         SPOILER_MEDIUM_CHOICE: SpoilerLevel.MEDIUM, SPOILER_FULL_CHOICE: SpoilerLevel.FULL}
SPOILER_LEVEL_LABELS = {int(ThreeState.OFF): "None", int(ThreeState.ON): "Basic", SPOILER_MEDIUM_CHOICE: "Medium",
                        SPOILER_FULL_CHOICE: "Full", int(ThreeState.POSSIBLE): "Random"}

# The owner's names for the fields and option values (owner-authored; owner
# decision 2026-10-03), edited in docs/flag-names.csv and imported into
# zora/flags/names.json by scripts/flag_names.py. A field or value without
# one keeps its spec label; Encode level data always keeps its own label.
OWNER_NAMES_FILE = "names.json"
# Switches the page names in ZORA's own words, not the community's (owner decision,
# 2026-10-12: neutral wording); scripts/flag_names.py reference keeps them. Their
# Archipelago keys stay as beta 3 froze them (zora/archipelago.py KEPT_KEYS).
OWN_SWITCH_NAMES = {"B29": "Shuffle Bomb Upgraders", "B48": "Book to Understand NPCs"}


@cache
def owner_names() -> dict[str, dict[str, Any]]:
    from importlib.resources import files
    names: dict[str, dict[str, Any]] = json.loads(
        # This package by its own name: copied in under another one (Archipelago's worlds.zora.zora,
        # perhaps from a zip), "zora.flags" would not be importable.
        files(__package__).joinpath(OWNER_NAMES_FILE).read_text(encoding="utf-8")
    )
    return names


def spec_value_label(field: FieldDef, value: int) -> str:
    if isinstance(field, OptionField):
        return _OPTION_LABELS[field.id][value]
    return THREE_STATE_LABELS[ThreeState(value)]


def spec_field_label(field: FieldDef) -> str:
    if field == ENCODE_LEVEL_DATA:
        return level_encoding.LABEL
    return field.setting


def value_label(field: FieldDef, value: int) -> str:
    """The owner's name for an option value when there is one, else the spec label."""
    owner_values = owner_names().get(field.id, {}).get("values", [])
    if isinstance(field, OptionField) and value < len(owner_values) and owner_values[value]:
        return str(owner_values[value])
    return spec_value_label(field, value)


def field_label(field: FieldDef) -> str:
    """The owner's name for a field when there is one, else the spec label."""
    if field == ENCODE_LEVEL_DATA:
        return level_encoding.LABEL
    label = str(owner_names().get(field.id, {}).get("name") or spec_field_label(field))
    return label + NO_EFFECT_SUFFIX if field in INERT_TOGGLES else label


def value_entry(field: FieldDef, value: int) -> dict[str, Any]:
    """One value as the page offers it: its label, the spec's, and a note where VALUE_NOTES has one."""
    entry: dict[str, Any] = {"value": value, "label": value_label(field, value),
                             "specLabel": spec_value_label(field, value)}
    note = VALUE_NOTES.get((field.id, int(value)))
    if note:
        entry["note"] = note
    return entry


def _with_value(settings: Settings, field: FieldDef, value: int) -> Settings:
    if isinstance(field, OptionField):
        return settings.updated(options={field.id: value})
    return settings.updated(toggles={field.id: value})


def _value_of(settings: Settings, field: FieldDef) -> int:
    if isinstance(field, OptionField):
        return settings.option(field)
    return int(settings.toggle(field))


@cache
def supported_values(field: FieldDef) -> tuple[int, ...]:
    """FL-SUP-01: the values of a field the MVP produces, everything else at the baseline."""
    baseline = mvp_baseline_settings()
    return tuple(value for value in field_values(field)
                 if support(_with_value(baseline, field, value))[field.id] is Support.SUPPORTED)


def _value_unavailable(field: FieldDef, value: int) -> str | None:
    """Why this build cannot produce a supported value (level encoding without its module)."""
    if field == ENCODE_LEVEL_DATA and value == ThreeState.ON and not level_encoding.is_available():
        return NOT_AVAILABLE_TEXT
    return None


def generation_refusals(flag_string: str, zora_flag_string: str = "") -> list[str]:
    """Every reason the generator refuses these strings (generate.plan), or none."""
    try:
        plan(flag_string, 0, zora_flag_string)
    except FlagsRefused as exc:
        return list(exc.reasons)
    except level_encoding.LevelEncodingUnavailable:
        return [f"{level_encoding.LABEL}: {NOT_AVAILABLE_TEXT}"]
    return []


def presets() -> list[dict[str, Any]]:
    """The page's preset menu: FL-PRE-01 to FL-PRE-04 but HIDDEN_PRESETS, plus CP-5, then ZORA's own
    presets (ZORA_PRESETS: All Swords No Boards, Vanilla and three community flagsets), each with its
    ZORA string (`zoraFlags`, empty for the Z1R presets); each disabled with its reasons when ZORA
    cannot produce it. Variant A is on it with level encoding on only (owner, beta 5);
    presets.PUBLISHED_VARIANT_A_LEVEL_ENCODING_OFF stays for the code that needs it."""
    entries = [(name, PRESET_LABELS.get(name, name), string, "") for name, string in PRESETS.items()
               if name not in HIDDEN_PRESETS]
    entries.append((*LEVEL_ENCODING_OFF_PRESET, ""))
    entries += [(name, name, string, zora) for name, (string, zora) in ZORA_PRESETS.items()]
    out = []
    for name, label, string, zora in entries:
        reasons = generation_refusals(string, zora)
        out.append({"name": name, "label": label, "flags": canonicalize(string), "zoraFlags": zora,
                    "available": not reasons, "reasons": reasons, "reason": _short_reason(reasons)})
    return out


def _short_reason(reasons: list[str]) -> str | None:
    """One phrase for a menu entry; the full reasons go in its tooltip."""
    if not reasons:
        return None
    if any(reason.startswith(NOT_PRODUCED_PREFIX) for reason in reasons):
        return NOT_PRODUCED_TEXT
    if reasons == [f"{level_encoding.LABEL}: {NOT_AVAILABLE_TEXT}"]:
        return f"{level_encoding.LABEL}: {NOT_AVAILABLE_TEXT.lower()}"
    return reasons[0]


def _field_metadata(field: FieldDef) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": field.id,
        "kind": "option" if isinstance(field, OptionField) else "toggle",
        "setting": field.setting,
        "label": field_label(field),
        "specLabel": spec_field_label(field),
        "values": [value_entry(field, value) for value in field_values(field)],
        "supportedValues": list(supported_values(field)),
    }
    if isinstance(field, OptionField):
        entry["slots"] = field.slots
        entry["randomValues"] = sorted(field.random_choices)
    if field == ITEM_SHUFFLE_SCOPE:
        entry["values"].append({"value": ITEM_SHUFFLE_NO_VANILLA_CHOICE, "label": ITEM_SHUFFLE_NO_VANILLA_LABEL,
                                "specLabel": ITEM_SHUFFLE_NO_VANILLA_LABEL})
        entry["supportedValues"].append(ITEM_SHUFFLE_NO_VANILLA_CHOICE)
        entry["randomValues"].append(ITEM_SHUFFLE_NO_VANILLA_CHOICE)
    if field == ENCODE_LEVEL_DATA:
        entry["help"] = level_encoding.HELP_TEXT
    if field == PRINT_QUEST_INFO:
        entry["label"] = SPOILER_LEVEL_LABEL
        entry["values"] = [{"value": value, "label": label, "specLabel": label}
                           for value, label in SPOILER_LEVEL_LABELS.items()]
        entry["supportedValues"] = [*entry["supportedValues"], SPOILER_MEDIUM_CHOICE, SPOILER_FULL_CHOICE]
    return entry


def metadata() -> dict[str, Any]:
    """What the page builds its controls from, once at start-up."""
    return {
        "fields": [_field_metadata(field) for field in ALL_FIELDS],
        "encodeLevelData": ENCODE_LEVEL_DATA.id,
        "spoilerLevelField": PRINT_QUEST_INFO.id,      # Spoiler Log Detail Level's control (race info)
        "levelEncoding": {"available": level_encoding.is_available(), "label": level_encoding.LABEL,
                          "help": level_encoding.HELP_TEXT, "unavailable": NOT_AVAILABLE_TEXT},
        "dependencyRules": [{"rule": rule, "text": text} for rule, text in DEPENDENCY_RULES],
        "presets": presets(),
        "beta": beta_metadata(),
        "defaultFlags": MVP_BASELINE_LEVEL_ENCODING_OFF,
        "alphabet": ALPHABET,
        "zora": zora_metadata(),
        "version": PLAYER_VERSION,
        # The tunic colors that switch the map marker to Link's skin color (the page's note).
        "markerHidingColors": sorted(MARKER_HIDING_COLORS),
        # A color slot's Random (FP-SET-02, FP-SET-03): the value the page keeps for it.
        "randomColor": RANDOM_COLOR,
        # The level label's word (FP-LEVEL-01): the page's list, Random's value and the custom-word rule.
        "levelWord": {"default": DEFAULT_LEVEL_WORD, "random": RANDOM_LEVEL_WORD, "choices": list(LEVEL_WORD_CHOICES),
                      "maxLength": LEVEL_WORD_MAX_LENGTH, "dashMaxLength": LEVEL_WORD_DASH_MAX_LENGTH,
                      "characters": LEVEL_WORD_CHARACTERS},
        # The boss-sound label's word (FP-ROAR-01): the default, Random's value and list, the rule.
        "bossSoundWord": {"default": DEFAULT_BOSS_SOUND_WORD, "random": RANDOM_BOSS_SOUND_WORD,
                          "choices": list(BOSS_SOUND_WORDS), "length": BOSS_SOUND_WORD_LENGTH,
                          "characters": BOSS_SOUND_WORD_CHARACTERS},
        # A Link sprite set's file (FP-LINK-02; zora/rom/link_sprite.py): what the page checks first, ZORA's
        # own sets, and for the preview the groups a ROM keeps Link in and the palette's fixed colors.
        "linkSpriteSet": {"format": LINK_SPRITE_FILE_FORMAT, "version": LINK_SPRITE_FILE_VERSION,
                          "size": SPRITE_SET_SIZE,
                          "builtIn": [{"id": set_id, **link_sprite_set_object(sprite_set)}
                                      for set_id, sprite_set in offered_sprite_sets().items()],
                          # A built-in-art set (zora/rom/link_art.py): its format, Link's halves in a
                          # set's order, and each block's file offset and first tile, which the preview
                          # assembles it from in the player's ROM.
                          "art": {"format": LINK_ART_FILE_FORMAT, "halves": list(LINK_HALVES),
                                  "blocks": {name: [block.offset, block.first_tile]
                                             for name, block in ART_BLOCKS.items()}},
                          "groups": [list(group) for group in LINK_TILE_GROUPS],
                          "fixedColors": list(LINK_FIXED_COLORS)},
    }


# Beta settings (owner rulings, 2026-11-05 and 2026-11-06; zora/flags/beta.py): the page's switch and its warning.
# The switch lives on the page alone, never in a flag string.
BETA_SWITCH_LABEL = "Enable Beta Flags"            # the switch's name (issue #15 review)
BETA_WARNING = "Beta settings are less tested and more likely to have bugs."
BETA_ON_TEXT = "Note: Beta settings are on"            # the page's warning starts with it (issue #15 review)
BETA_LOCKED_TEXT = f"A beta setting: turn on {BETA_SWITCH_LABEL} to choose it"
BETA_IN_USE_TEXT = f"These flags use beta settings, so {BETA_SWITCH_LABEL} is on"
BETA_CURRENT_TEXT = f"A beta setting: turn on {BETA_SWITCH_LABEL}, or choose another value"


def _page_value(settings: Settings, field: FieldDef, zora_flags: ZoraFlags | None) -> int:
    """A Z1R field's value as the page's control holds it: Item Shuffle at Random with the ZORA string's
    No Vanilla on is its sixth choice."""
    value = _value_of(settings, field)
    if (field == ITEM_SHUFFLE_SCOPE and value == ItemShuffleScope.RANDOM and zora_flags is not None
            and zora_flags.item_shuffle_no_vanilla):
        return ITEM_SHUFFLE_NO_VANILLA_CHOICE
    if field == PRINT_QUEST_INFO and zora_flags is not None:
        return spoiler_level_choice(ThreeState(value), zora_flags.detailed_spoiler_log)
    return value


def spoiler_level_choice(print_quest_info: ThreeState, detailed_spoiler_log: bool) -> int:
    """Spoiler Log Detail Level's control value: Random for B51's "?", whatever the ZORA field says (the "?"
    picks both), else the level the two bits give."""
    if print_quest_info is ThreeState.POSSIBLE:
        return int(ThreeState.POSSIBLE)
    level = spoiler_level(print_quest_info is ThreeState.ON, detailed_spoiler_log)
    return next(choice for choice, choice_level in SPOILER_LEVEL_CHOICES.items() if choice_level == level)


# A switch's "?" is decided per seed, On or Off.
COIN_FLIP = frozenset({int(ThreeState.OFF), int(ThreeState.ON)})


def _z1r_randoms(field: FieldDef) -> dict[int, frozenset[int]]:
    """Each value of a Z1R field that is decided per seed, with the values it can resolve to (FL-DEP-04);
    Item Shuffle's Random (No Vanilla) draws from Item Only, Intra-Dungeon and Full."""
    if isinstance(field, OptionField):
        randoms = {int(value): frozenset(int(outcome) for outcome in outcomes)
                   for value, outcomes in field.random_choices.items()}
        if field == ITEM_SHUFFLE_SCOPE:
            randoms[ITEM_SHUFFLE_NO_VANILLA_CHOICE] = frozenset(int(scope) for scope in NO_VANILLA_ITEM_SHUFFLES)
        return randoms
    if field == PRINT_QUEST_INFO:          # Random draws Basic, Medium or Full, never None
        return {int(ThreeState.POSSIBLE): frozenset(choice for choice, level in SPOILER_LEVEL_CHOICES.items()
                                                    if level is not SpoilerLevel.NONE)}
    return {int(ThreeState.POSSIBLE): COIN_FLIP} if ThreeState.POSSIBLE in field_values(field) else {}


def _zora_randoms(zora_field: Mapping[str, Any]) -> dict[int, frozenset[int]]:
    """A ZORA Extra's values decided per seed: a switch's "?", and Swordlish's Random (On or Off)."""
    if zora_field["kind"] == THREE_STATE_KIND:
        return {int(ThreeState.POSSIBLE): COIN_FLIP}
    if zora_field["name"] == SWORDLISH_FIELD:
        return {int(Swordlish.RANDOM): frozenset({int(Swordlish.OFF), int(Swordlish.ON)})}
    return {}


@cache
def beta_offered() -> dict[str, beta.FlagChoices]:
    """Every flag the page offers, as the flags file names it: a Z1R field by its code, a shown ZORA Extra
    by its field name, each with its page name, the value a fresh page starts with, its values' labels and
    its Random values' outcomes."""
    start = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    offered = {}
    for field in ALL_FIELDS:
        labels = {value: value_label(field, value) for value in field_values(field)}
        if field == ITEM_SHUFFLE_SCOPE:
            labels[ITEM_SHUFFLE_NO_VANILLA_CHOICE] = ITEM_SHUFFLE_NO_VANILLA_LABEL
        if field == PRINT_QUEST_INFO:
            labels = dict(SPOILER_LEVEL_LABELS)
        name = SPOILER_LEVEL_LABEL if field == PRINT_QUEST_INFO else field_label(field)
        offered[field.id] = beta.FlagChoices(name, _page_value(start, field, None), labels,
                                             _z1r_randoms(field))
    fresh = ZoraFlags()
    for zora_field in zora_metadata()["fields"]:
        if zora_field.get("hidden"):          # set from another tab (Item Shuffle's Random (No Vanilla))
            continue
        name = zora_field["name"]
        offered[name] = beta.FlagChoices(zora_field["label"], control_value(fresh, name),
                                         {entry["value"]: entry["label"] for entry in zora_field["values"]},
                                         _zora_randoms(zora_field))
    return offered


def beta_values() -> dict[str, frozenset[int]]:
    """Each beta flag's beta values, by its control's numbers, a Random that can resolve to one included
    (beta.beta_values of the shipped file)."""
    return beta.beta_values(beta.flags_config(), beta_offered())


def beta_metadata() -> dict[str, Any]:
    """What the page needs for its Beta settings switch: the beta values of each flag, the flags beta as a
    whole (every value but a fresh page's), the switch's name, its warning and the reasons it shows."""
    offered = beta_offered()
    values = beta_values()
    whole = [key for key, beta_set in values.items()
             if beta_set == frozenset(offered[key].labels) - {offered[key].default}]
    return {"values": {key: sorted(beta_set) for key, beta_set in values.items()}, "flags": whole,
            "label": BETA_SWITCH_LABEL, "warning": BETA_WARNING, "locked": BETA_LOCKED_TEXT,
            "inUse": BETA_IN_USE_TEXT, "current": BETA_CURRENT_TEXT, "on": BETA_ON_TEXT}


def _beta_in_use(z1r_values: Mapping[str, int], zora_values: Mapping[str, int]) -> list[dict[str, Any]]:
    offered = beta_offered()
    used = []
    for key, values in beta_values().items():
        value = z1r_values.get(key, zora_values.get(key))
        if value in values:
            choices = offered[key]
            used.append({"field": key, "value": value, "text": f"{choices.name}: {choices.labels[value]}"})
    return used


def beta_settings_used(flag_string: str, zora_flag_string: str = "") -> list[str]:
    """The beta settings these strings use, each "Name: Value" as the page shows it (for the scripts that
    take flag strings: they warn, never refuse). Strings that do not decode use none."""
    try:
        settings = decode(flag_string)
        zora_flags = decode_zora(zora_flag_string.strip())
    except (FlagStringError, ZoraFlagStringError):
        return []
    z1r_values = {field.id: _page_value(settings, field, zora_flags) for field in ALL_FIELDS}
    zora_values = {field["name"]: control_value(zora_flags, field["name"]) for field in ZORA_FIELDS}
    return [entry["text"] for entry in _beta_in_use(z1r_values, zora_values)]


def _refusal_texts(settings: Settings) -> set[str]:
    return {f"{refusal.rule}: {refusal.message}" for refusal in check_dependencies(settings)}


def _blocked_values(settings: Settings, field: FieldDef, refused: set[str]) -> dict[int, str]:
    """The values of a field the player cannot pick from here, with the reason: a dependency
    rule the change would break (flags.check_dependencies), or the support matrix."""
    current = _value_of(settings, field)
    supported = supported_values(field)
    blocked = {}
    for value in field_values(field):
        if value == current:
            continue
        broken = sorted(_refusal_texts(_with_value(settings, field, value)) - refused)
        if broken:
            blocked[value] = "; ".join(broken)
        elif value not in supported:
            blocked[value] = NOT_PRODUCED_TEXT
        elif (unavailable := _value_unavailable(field, value)) is not None:
            blocked[value] = unavailable
    return blocked


def _field_state(settings: Settings, field: FieldDef, refused: set[str]) -> dict[str, Any]:
    value = _value_of(settings, field)
    blocked = _blocked_values(settings, field, refused)
    current_ok = value in supported_values(field) and _value_unavailable(field, value) is None
    # a pasted string's postponed value, and B82's "?" (read as off): accepted, with a notice
    postponed = is_postponed(settings, field.id) or (field == ENCODE_LEVEL_DATA and value == ThreeState.POSSIBLE)
    others = [v for v in field_values(field) if v != value]
    disabled = current_ok and all(v in blocked for v in others)
    if postponed:
        reason = POSTPONED_TOGGLES.get(field.id, ENCODE_LEVEL_DATA_RANDOM_NOTICE)
    elif not current_ok:
        reason = _value_unavailable(field, value) or CURRENT_NOT_PRODUCED_TEXT
    elif disabled and len(supported_values(field)) == 1:
        reason = NOT_PRODUCED_TEXT       # the rule texts stay on the values themselves
    elif blocked:
        reason = blocked[min(blocked)]
    else:
        reason = None
    state = {"value": value, "disabled": disabled, "reason": reason, "problem": not (current_ok or postponed),
             "blocked": {str(v): text for v, text in blocked.items()}}
    if postponed:
        state["notice"] = reason          # the page shows it on the row, which stays shown
    return state


def _locked(field: FieldDef, state: dict[str, Any], reason: str) -> dict[str, Any]:
    """A control the page shows at its value and does not let the player change, with the reason (a
    value that is not produced keeps its own state, so the player can still change it)."""
    if state["problem"]:
        return state
    others = {str(value): reason for value in field_values(field) if value != state["value"]}
    return {**state, "disabled": True, "reason": reason, "blocked": others}


def _item_shuffle_no_vanilla(zora_flag_string: str) -> bool:
    try:
        return decode_zora(zora_flag_string.strip()).item_shuffle_no_vanilla
    except ZoraFlagStringError:
        return False


def _with_no_vanilla_choice(state: dict[str, Any]) -> dict[str, Any]:
    """Item Shuffle's control at Random (No Vanilla) when the ZORA string narrows its Random: the same choices
    blocked as at Random, and Random itself (the ZORA field off) pickable."""
    blocked = {value: reason for value, reason in state["blocked"].items()
               if value != str(ITEM_SHUFFLE_NO_VANILLA_CHOICE)}
    return {**state, "value": ITEM_SHUFFLE_NO_VANILLA_CHOICE, "blocked": blocked}


def _with_no_vanilla_offered(state: dict[str, Any]) -> dict[str, Any]:
    """Item Shuffle's control elsewhere: Random (No Vanilla) blocked exactly when Random is."""
    random_reason = state["blocked"].get(str(ItemShuffleScope.RANDOM))
    if random_reason is None:
        return state
    return {**state, "blocked": {**state["blocked"], str(ITEM_SHUFFLE_NO_VANILLA_CHOICE): random_reason}}


def with_item_shuffle_no_vanilla(zora_flag_string: str, on: bool) -> str:
    """The ZORA string with Item Shuffle: Random (No Vanilla)'s field set; one that does not decode is
    returned as it is (its error stays shown)."""
    try:
        flags = decode_zora(zora_flag_string.strip())
    except ZoraFlagStringError:
        return zora_flag_string
    return encode_zora(replace(flags, item_shuffle_no_vanilla=on))


def _detailed_spoiler_log(zora_flag_string: str) -> bool:
    try:
        return decode_zora(zora_flag_string.strip()).detailed_spoiler_log
    except ZoraFlagStringError:
        return False


def with_detailed_spoiler_log(zora_flag_string: str, on: bool) -> str:
    """The ZORA string with Detailed Spoiler Log set; one that does not decode is returned as it is."""
    try:
        flags = decode_zora(zora_flag_string.strip())
    except ZoraFlagStringError:
        return zora_flag_string
    return encode_zora(replace(flags, detailed_spoiler_log=on))


def _with_spoiler_level(state: dict[str, Any], print_quest_info: ThreeState, zora_flag_string: str) -> dict[str, Any]:
    """Spoiler Log Detail Level's control: the level the two strings give."""
    return {**state, "value": spoiler_level_choice(print_quest_info, _detailed_spoiler_log(zora_flag_string))}


def _level_9_entrance_sword(zora_flag_string: str) -> bool:
    try:
        return decode_zora(zora_flag_string.strip()).level_9_entrance_sword
    except ZoraFlagStringError:
        return False


def form_state(flag_string: str, zora_flag_string: str = "") -> dict[str, Any]:
    """The controls for a flag string and a ZORA flag string, or the decoder's error."""
    try:
        decoded = decode(flag_string)
    except FlagStringError as exc:
        return {"ok": False, "error": f"Flag string: {exc}", "zora": zora_state(zora_flag_string, None)}
    settings = decoded           # B23 kept as given, whatever B22 is (FL-DEP-06)
    refused = _refusal_texts(settings)
    adjusted = apply_dependencies(settings)
    adjustments = [f"FL-DEP-02 rule 4 turns {field_id} off" for field_id in (
        HUNGRY_GORIYA_SHUFFLE.id, BOMB_UPGRADE_PERSON_SHUFFLE.id
    )
        if adjusted.toggle(field_id) != settings.toggle(field_id)]
    canonical = encode(settings)
    zora = zora_state(zora_flag_string, adjusted)
    fields = {field.id: _field_state(settings, field, refused) for field in ALL_FIELDS}
    if settings.option(LEVEL_9_REQUIREMENT) not in RANGE_READERS:
        for field in (PIECE_RANGE_LOW, PIECE_RANGE_HIGH):
            fields[field.id] = _locked(field, fields[field.id], RANGE_UNUSED_TEXT)
    no_vanilla = (settings.option(ITEM_SHUFFLE_SCOPE) == ItemShuffleScope.RANDOM
                  and _item_shuffle_no_vanilla(zora_flag_string))
    fields[ITEM_SHUFFLE_SCOPE.id] = (_with_no_vanilla_choice if no_vanilla
                                     else _with_no_vanilla_offered)(fields[ITEM_SHUFFLE_SCOPE.id])
    fields[PRINT_QUEST_INFO.id] = _with_spoiler_level(fields[PRINT_QUEST_INFO.id],
                                                      settings.toggle(PRINT_QUEST_INFO), zora_flag_string)
    eight_pieces = settings.option(LEVEL_9_REQUIREMENT) == Level9Requirement.EIGHT_PIECES
    if eight_pieces and _level_9_entrance_sword(zora_flag_string):
        fields[LEVEL_9_REQUIREMENT.id] = _locked(LEVEL_9_REQUIREMENT, fields[LEVEL_9_REQUIREMENT.id],
                                                 LEVEL_9_ENTRY_BY_SWORD_TEXT)
    zora_values = zora["values"] if zora["ok"] else {}
    return {
        "ok": True,
        "flags": canonical,
        "fields": fields,
        # the beta settings in use (the page turns its switch on when loaded strings use one)
        "beta": _beta_in_use({field_id: state["value"] for field_id, state in fields.items()}, zora_values),
        "refusals": sorted(refused),
        "adjustments": adjustments,
        "notices": [*postponed_notices(settings),
                    *([ENCODE_LEVEL_DATA_RANDOM_NOTICE] if encode_level_data_is_random(settings) else [])],
        "generateRefusals": generation_refusals(canonical, zora["flags"] if zora["ok"] else zora_flag_string),
        "preset": next((p["name"] for p in presets() if p["flags"] == canonical
                        and p["zoraFlags"] == (zora["flags"] if zora["ok"] else zora_flag_string)), None),
        "zora": zora,
    }


def flags_from_values(values: Mapping[str, int | str]) -> str:
    """The canonical flag string of the controls' values (the page reads them as strings)."""
    missing = set(FIELDS_BY_ID) - set(values)
    unknown = set(values) - set(FIELDS_BY_ID)
    if missing or unknown:
        raise ValueError(f"missing fields {sorted(missing)}, unknown fields {sorted(unknown)}")
    return encode(Settings(
        {field.id: int(values[field.id]) for field in OPTION_FIELDS},
        {field.id: ThreeState(int(values[field.id])) for field in TOGGLE_FIELDS},
    ))


def form_change(previous_flags: str, values: Mapping[str, int | str],
                zora_flag_string: str = "") -> dict[str, Any]:
    """The player changed a control: the new state, or the change blocked with the rule it breaks. Item
    Shuffle at Random (No Vanilla) writes Random into the Z1R string and the ZORA field on; any other Item
    Shuffle value writes the field off. Spoiler Log Detail Level writes Print Quest Info (B51) and Detailed
    Spoiler Log: Medium and Full set the ZORA field, every other value clears it."""
    previous = decode(previous_flags)
    no_vanilla = int(values[ITEM_SHUFFLE_SCOPE.id]) == ITEM_SHUFFLE_NO_VANILLA_CHOICE
    if no_vanilla:
        values = {**values, ITEM_SHUFFLE_SCOPE.id: int(ItemShuffleScope.RANDOM)}
    spoiler_choice = int(values[PRINT_QUEST_INFO.id])
    detailed = spoiler_choice in (SPOILER_MEDIUM_CHOICE, SPOILER_FULL_CHOICE)
    if detailed:
        print_quest_info = ThreeState.ON if spoiler_choice == SPOILER_FULL_CHOICE else ThreeState.OFF
        values = {**values, PRINT_QUEST_INFO.id: int(print_quest_info)}
    new_flags = flags_from_values(values)
    broken = sorted(_refusal_texts(decode(new_flags)) - _refusal_texts(previous))
    if broken:
        state = form_state(previous_flags, zora_flag_string)
        state["blockedChange"] = "; ".join(broken)
        return state
    zora_flag_string = with_detailed_spoiler_log(zora_flag_string, detailed)
    return form_state(new_flags, with_item_shuffle_no_vanilla(zora_flag_string, no_vanilla))


def zora_form_change(flag_string: str, zora_values: Mapping[str, int | str]) -> dict[str, Any]:
    """The player changed a ZORA Extras control: the state with the new ZORA string. Nothing is
    blocked or adjusted: a sword-hearts conflict is shown, for the player to resolve."""
    return form_state(flag_string, zora_flags_from_values(zora_values))
