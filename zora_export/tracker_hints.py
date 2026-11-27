"""The flags spec's tracker hints (docs/flags-api.md "Tracker hints"): what a player can know at the start from
the flag strings alone, items pinned to a place and start items, and the settings that change what a hinted item
is. One copy of the rules, read by the spec's generator (scripts/flags_api.py, which writes them into
docs/flags-api/zora-flags.json) and by the starter tracker save (zora_export/tracker_file.py starter_file), which
evaluates them for one seed's flags (start_knowledge).

Every fact comes from the code ZORA runs: zora/flags/ for the fields, and the generation steps for the items and
the conditions. Nothing here depends on the seed: where a seed's draw decides, the hint is unknown.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from functools import cache
from typing import Any

from zora.flags import form, zora_flags
from zora.flags.codec import decode
from zora.flags.dependencies import start_item_limit
from zora.flags.fields import (
    ARMOS_PIN,
    COAST_PIN,
    DUNGEON_LAYOUT_SOURCE,
    ITEM_SHUFFLE_SCOPE,
    LEVEL_9_FIRST_PIN,
    LEVEL_9_SECOND_PIN,
    OPTION_FIELDS,
    START_ITEM_LIMIT,
    WHITE_SWORD_CAVE_PIN,
    WOODEN_SWORD_STATE,
    DungeonLayoutSource,
    ItemShuffleScope,
    OptionField,
    Settings,
    ThreeState,
)
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import NO_VANILLA_ITEM_SHUFFLES, SWORDLISH_RANDOM_STATES, SWORDS_WITHOUT_SWAP, Swordlish
from zora.generate.places import SELLER_SUFFIX
from zora.generate.steps.hint_text import BOOMERANG_LINE, BOOTS_LINE, UPGRADE_LINES
from zora.generate.steps.shuffle_items import FORCED_ITEM_OPTIONS, NON_HEART, RANDOM_ITEM
from zora.generate.steps.start_items import START_ITEM_ORDER
from zora.generate.steps.swap_swords_and_rings import SWAPPED_PAIRS
from zora.generate.steps.sword_states import BOMB_UPGRADE_STATES
from zora.model.enums import Item
from zora.model.item_names import ITEM_NAMES, PEGASUS_BOOTS_NAMES
from zora.model.level_items import LEVELS, LevelItemKind, level_item_name

RANDOM = int(ThreeState.POSSIBLE)
PEGASUS_BOOTS = "pegasus_boots"          # the modifier's id, the ZORA field's name


@cache
def page_default_settings() -> Settings:
    """The Z1R settings a fresh page starts with (form.metadata()'s defaultFlags)."""
    return decode(MVP_BASELINE_LEVEL_ENCODING_OFF)


def z1r_settings_with(digits: Mapping[str, int]) -> Settings:
    """The page's starting Z1R settings with these fields changed."""
    options = {key: value for key, value in digits.items() if key in {field.id for field in OPTION_FIELDS}}
    toggles = {key: value for key, value in digits.items() if key not in options}
    return page_default_settings().updated(options=options, toggles=toggles)


def item_name(item: Item) -> str:
    return ITEM_NAMES[item]


def _values_where(field: OptionField, wanted: Callable[[int], bool]) -> list[int]:
    return [value for value in range(field.count) if wanted(value)]


def pins_apply() -> dict[str, list[dict[str, list[int]]]]:
    """When the pins act (shuffle_items.py: only inside the deal; PS-ITEM-10's None deals nothing, except under
    Mixed dungeons, AlternativeValues.item_deal; Random (No Vanilla) always deals)."""
    dealing = [int(scope) for scope in ItemShuffleScope
               if scope not in (ItemShuffleScope.NONE, ItemShuffleScope.RANDOM)]
    mixed = int(DungeonLayoutSource.MIXED)
    random_with_mixed = _values_where(DUNGEON_LAYOUT_SOURCE,
                                      lambda value: mixed in DUNGEON_LAYOUT_SOURCE.random_choices.get(value, ()))
    random_scope = int(ItemShuffleScope.RANDOM)
    none = int(ItemShuffleScope.NONE)
    no_vanilla = zora_flags.ITEM_SHUFFLE_NO_VANILLA_FIELD
    assert all(scope in dealing for scope in NO_VANILLA_ITEM_SHUFFLES)
    return {
        "applies_when": [{ITEM_SHUFFLE_SCOPE.id: dealing},
                         {ITEM_SHUFFLE_SCOPE.id: [none], DUNGEON_LAYOUT_SOURCE.id: [mixed]},
                         {ITEM_SHUFFLE_SCOPE.id: [random_scope], no_vanilla: [1]}],
        "unknown_when": [{ITEM_SHUFFLE_SCOPE.id: [random_scope], no_vanilla: [0]},
                         {ITEM_SHUFFLE_SCOPE.id: [none], DUNGEON_LAYOUT_SOURCE.id: random_with_mixed}],
    }


PIN_LOCATIONS = (("armos", ARMOS_PIN), ("coast", COAST_PIN), ("white_sword_cave", WHITE_SWORD_CAVE_PIN),
                 ("level_9_first_item", LEVEL_9_FIRST_PIN), ("level_9_second_item", LEVEL_9_SECOND_PIN))


def pin_values() -> list[dict[str, Any]]:
    """Each pin value: no pin, one item, or an unknown item (Non-Heart: any item but a Heart Container)."""
    out: list[dict[str, Any]] = []
    for value, code in enumerate(FORCED_ITEM_OPTIONS):
        if code == RANDOM_ITEM:
            out.append({"value": value, "status": "not_pinned"})
        elif code == NON_HEART:
            out.append({"value": value, "status": "unknown", "not_item": item_name(Item.HEART_CONTAINER)})
        else:
            out.append({"value": value, "status": "item", "item": item_name(Item(code))})
    return out


def start_items() -> dict[str, Any]:
    random_limits = sorted(START_ITEM_LIMIT.random_choices)
    limits: list[dict[str, Any]] = []
    for value in range(START_ITEM_LIMIT.count):
        if value in random_limits:
            limits.append({"value": value, "random": True})
        else:
            limits.append({"value": value, "limit": start_item_limit(z1r_settings_with({START_ITEM_LIMIT.id: value}))})
    return {
        "about": ("A start item's field at On gives the item at the start when the limit keeps every chosen item: "
                  "its limit is null, or the count of start-item fields that are not Off is at most the limit. "
                  "Otherwise, and for a field at Random, the item is unknown (the seed draws it)."),
        "fields": [{"field": field.id, "item": item_name(item)} for field, item in START_ITEM_ORDER],
        "limit_field": START_ITEM_LIMIT.id,
        "limits": limits,
    }


def _start_field_of(item: Item) -> str:
    return next(field.id for field, start_item in START_ITEM_ORDER if start_item == item)


def modifiers() -> list[dict[str, Any]]:
    """Settings that change what a hinted item is (or what it does), in the order a tool applies them."""
    wooden_sword_random = sorted(WOODEN_SWORD_STATE.random_choices)
    with_swords = [value for value in range(WOODEN_SWORD_STATE.count)
                   if value not in SWORDS_WITHOUT_SWAP and value not in wooden_sword_random]
    swap = zora_flags.SWAP_FIELD
    swordlish = zora_flags.SWORDLISH_FIELD
    not_random_swordlish = [int(state) for state in Swordlish if state is not Swordlish.RANDOM]
    swordlish_random_reaches = any(state in BOMB_UPGRADE_STATES for state in SWORDLISH_RANDOM_STATES)
    assert swordlish_random_reaches, "Swordlish's Random can pick a state without the swap"
    lines = {item_name(Item(code)): line.title() for code, line in UPGRADE_LINES.items()}
    boots_lines = {PEGASUS_BOOTS_NAMES[Item(code)]: BOOTS_LINE.title()
                   for code, line in UPGRADE_LINES.items() if line == BOOMERANG_LINE}
    return [
        {"id": "swap_swords_and_rings", "applies_to": ["locations"],
         "applies_when": [{swap: [1], WOODEN_SWORD_STATE.id: with_swords, swordlish: not_random_swordlish}],
         "unknown_when": [{swap: [RANDOM]},
                          {swap: [1], WOODEN_SWORD_STATE.id: wooden_sword_random},
                          {swap: [1], swordlish: [int(Swordlish.RANDOM)]}],
         "pairs": [{"items": [item_name(first), item_name(second)],
                    "start_item_fields": [_start_field_of(first), _start_field_of(second)]}
                   for first, second in SWAPPED_PAIRS],
         "about": ("Each pair's two items trade places. A pair is not swapped when the seed starts with either of "
                   "its items: when one of its start_item_fields is not Off, the pair's items are swapped only if "
                   "both are certainly not start items, kept as they are if one certainly is, and unknown "
                   "otherwise.")},
        {"id": PEGASUS_BOOTS, "applies_to": ["locations", "start_items"],
         "applies_when": [{PEGASUS_BOOTS: [1]}], "unknown_when": [{PEGASUS_BOOTS: [RANDOM]}],
         "rename": {item_name(item): name for item, name in PEGASUS_BOOTS_NAMES.items()},
         "about": "The boomerangs' items are the boots (the seed format's names)."},
        {"id": "bomb_upgrade", "applies_to": ["locations"],
         "applies_when": [{WOODEN_SWORD_STATE.id: sorted(int(state) for state in BOMB_UPGRADE_STATES)}],
         "unknown_when": [{WOODEN_SWORD_STATE.id: wooden_sword_random}, {swordlish: [int(Swordlish.RANDOM)]}],
         "acts_as": {item_name(Item.WHITE_SWORD): "bomb upgrade"},
         "about": ("Wood Sword Only and Swordless: the White Sword item is still named so, but taking it adds two "
                   "bombs to the bomb capacity instead of giving a sword.")},
        *level_item_pool_modifiers(),
        bomb_upgrade_sellers(),
        {"id": "progressive_items", "applies_to": ["locations"],
         "applies_when": [{"progressive_items": [1]}], "unknown_when": [],
         "upgrade_lines": {**lines, **boots_lines},
         "about": ("Each item of an upgrade line found in the world gives the next item of that line the player "
                   "lacks, whichever item of the line it is named. Start items are not changed: a start item is "
                   "the item itself. Each line's items are listed lowest first.")},
    ]


# Triforce Shuffle and Map & Compass Shuffle (docs/design/archipelago-items.md piece 7): each acts under every Item
# Shuffle but None. Anywhere reaches as far as Item Shuffle does; Between levels keeps each kind in its own spots
ACTING_SCOPES = [int(scope) for scope in NO_VANILLA_ITEM_SHUFFLES]
REACH = {str(int(ItemShuffleScope.DUNGEON_ITEMS_ONLY)): "anywhere",
         str(int(ItemShuffleScope.WITHIN_EACH_DUNGEON)): "own_level", str(int(ItemShuffleScope.FULL)): "anywhere"}
LEVEL_ITEM_SHUFFLE_KINDS = {zora_flags.TRIFORCE_SHUFFLE_FIELD: (LevelItemKind.TRIFORCE,),
                            zora_flags.MAP_COMPASS_SHUFFLE_FIELD: (LevelItemKind.MAP, LevelItemKind.COMPASS)}
ANYWHERE = int(zora_flags.LevelItemShuffle.ANYWHERE)
BETWEEN_LEVELS = int(zora_flags.LevelItemShuffle.BETWEEN_LEVELS)


def _acting_when(field: str, value: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A level-item shuffle's value acting (applies_when) and maybe acting (unknown_when: Item Shuffle Random, which
    may draw None unless Random (No Vanilla))."""
    random_scope = int(ItemShuffleScope.RANDOM)
    no_vanilla = zora_flags.ITEM_SHUFFLE_NO_VANILLA_FIELD
    return ([{field: [value], ITEM_SHUFFLE_SCOPE.id: ACTING_SCOPES},
             {field: [value], ITEM_SHUFFLE_SCOPE.id: [random_scope], no_vanilla: [1]}],
            [{field: [value], ITEM_SHUFFLE_SCOPE.id: [random_scope], no_vanilla: [0]}])


def level_item_pool_modifiers() -> list[dict[str, Any]]:
    """The two level-item shuffles. Anywhere: the level's piece (or map and compass) is an item of its own, shuffled
    as far as Item Shuffle reaches. Between levels: each level still holds one of each, but which level's is drawn."""
    entries = []
    for field, kinds in LEVEL_ITEM_SHUFFLE_KINDS.items():
        items = [level_item_name(kind, level) for kind in kinds for level in LEVELS[kind]]
        applies, unknown = _acting_when(field, ANYWHERE)
        entries.append({
            "id": field, "applies_to": ["locations"], "applies_when": applies, "unknown_when": unknown,
            "reach": {"field": ITEM_SHUFFLE_SCOPE.id, "by_value": REACH},
            "items": items,
            "about": ("Anywhere: each named item is an item of its own, shuffled with the others: within its own "
                      "level (own_level) or into any level, cave or shop ware the shuffle reaches (anywhere). Where "
                      "Item Shuffle is Random the reach is unknown. A level's Triforce room, map room and compass "
                      "room then hold whatever the shuffle put there."),
        })
        applies, unknown = _acting_when(field, BETWEEN_LEVELS)
        entries.append({
            "id": f"{field}_between_levels", "applies_to": ["locations"], "applies_when": applies,
            "unknown_when": unknown, "items": items,
            "about": ("Between levels: each level still holds exactly one item of each named kind, where Off would "
                      "put it, but which level's it is was shuffled among that kind's levels: level 3's Triforce "
                      "room may hold Level 6 Triforce. Each shows its own level's number and works for that level."),
        })
    return entries


# Bomb Upgrades in the Item Pool (docs/design/archipelago-items.md piece 8): the two bomb upgraders that sell are
# places, named by their rooms; a switch, Multiworld games only, so never Random
SELLERS_PER_SEED = 2


def bomb_upgrade_sellers() -> dict[str, Any]:
    """The pool switch of piece 8: each selling bomb upgrader is a place, his ware the item placed there."""
    field = zora_flags.BOMB_UPGRADES_FIELD
    return {
        "id": field, "applies_to": ["locations"], "applies_when": [{field: [1]}], "unknown_when": [],
        "locations": {"name": f"Level N Room XX {SELLER_SUFFIX}", "count": SELLERS_PER_SEED},
        "items": [item_name(Item.BOMB_UPGRADE)],
        "about": ("Multiworld games only. Each of the two bomb upgraders that sell is a place, named by his level "
                  "and room (XX in hex): he shows the item placed there and gives it for his price, once. Which "
                  "rooms they are is the seed's draw. Each seller's own Bomb Upgrade, which raises the bomb "
                  "capacity by the seed's upgrade amount, is an item of its own, placed anywhere in the "
                  "multiworld."),
    }


@cache
def tracker_hints() -> dict[str, Any]:
    return {
        "about": ("What a player can know at the start from the flags alone: items pinned to a place, and start "
                  "items. A condition list matches when any of its conditions does; a condition matches when "
                  "every field it names (a Z1R key or a ZORA key) holds one of the listed values. Nothing here "
                  "depends on the seed: where a seed's draw decides, the hint is unknown."),
        "pins": {
            "about": ("A pin value names the item at its place when the pins apply (applies_when); when unknown_when "
                      "matches it may or may not be there; otherwise the pins do nothing and the place's item is not "
                      "known from the flags. A level 9 pin names the item at the first (or second) of level 9's item "
                      "places; it does nothing if level 9 has no such place."),
            **pins_apply(),
            "locations": [{"location": location, "field": field.id, "name": form.field_label(field)}
                          for location, field in PIN_LOCATIONS],
            "values": pin_values(),
        },
        "start_items": start_items(),
        "modifiers": modifiers(),
    }


# ---------------------------------------------------------------------------
# One seed's flags: what the hints say a player knows at the start
# ---------------------------------------------------------------------------

Condition = Mapping[str, Iterable[int]]


class Status(Enum):
    """A hint rule for one seed's flags: it acts, the seed decides, or it does nothing."""
    APPLIES = "applies"
    UNKNOWN = "unknown"
    OFF = "off"


def flag_digits(flag_string: str, zora_flag_string: str) -> dict[str, int]:
    """Every field's digit, by its spec key (C01-C27 and B01-B94, then the ZORA fields' names), as the spec's
    decoding gives it: the values the hints' conditions name."""
    settings = decode(flag_string)
    digits = {key: int(value) for key, value in settings.options.items()}
    digits |= {key: int(value) for key, value in settings.toggles.items()}
    return digits | zora_flags.field_digits(zora_flags.decode(zora_flag_string))


def matches(conditions: Iterable[Condition], digits: Mapping[str, int]) -> bool:
    """A condition list matches when any condition does; a condition when every field it names holds a listed value."""
    return any(all(digits[key] in values for key, values in condition.items()) for condition in conditions)


def status(rule: Mapping[str, Any], digits: Mapping[str, int]) -> Status:
    if matches(rule["unknown_when"], digits):
        return Status.UNKNOWN
    return Status.APPLIES if matches(rule["applies_when"], digits) else Status.OFF


def modifier(modifier_id: str) -> dict[str, Any]:
    """One of the spec's modifiers by its id."""
    return next(entry for entry in tracker_hints()["modifiers"] if entry["id"] == modifier_id)



def pegasus_boots(digits: Mapping[str, int]) -> Status:
    """The spec's Pegasus Boots modifier for these digits: the boomerangs are the boots, the seed decides, or not."""
    return status(modifier(PEGASUS_BOOTS), digits)


@dataclass(frozen=True)
class StartKnowledge:
    """What the flags tell a player at the start, the modifiers applied: the item at each pinned place (by the
    spec's location names), the start items, whether the White Sword item is a bomb upgrade (None when the
    seed decides), and whether the boomerangs are the boots (the Pegasus Boots modifier's status). Places and
    start items the seed decides are left out."""
    places: dict[str, str]
    start_items: tuple[str, ...]
    bomb_upgrade: bool | None
    pegasus_boots: Status


def _start_fields(hints: Mapping[str, Any], digits: Mapping[str, int]) -> tuple[set[str], set[str]]:
    """The start-item fields certainly giving their item, and those certainly not (Off); the rest are unknown."""
    rules = hints["start_items"]
    limit = next(entry for entry in rules["limits"] if entry["value"] == digits[rules["limit_field"]])
    chosen = [entry["field"] for entry in rules["fields"] if digits[entry["field"]] != int(ThreeState.OFF)]
    keeps_all = not limit.get("random") and (limit["limit"] is None or len(chosen) <= limit["limit"])
    certain = {field for field in chosen if keeps_all and digits[field] == int(ThreeState.ON)}
    absent = {entry["field"] for entry in rules["fields"]} - set(chosen)
    return certain, absent


def _renamed(items: dict[str, str], rename: Mapping[str, str], rule: Status) -> dict[str, str]:
    """Each key's item renamed (APPLIES), dropped when the seed decides whether it is (UNKNOWN), else kept."""
    if rule is Status.APPLIES:
        return {key: rename.get(item, item) for key, item in items.items()}
    if rule is Status.UNKNOWN:
        return {key: item for key, item in items.items() if item not in rename}
    return items


def start_knowledge(flag_string: str, zora_flag_string: str) -> StartKnowledge:
    """The spec's tracker hints evaluated for these flags (docs/flags-api.md "Tracker hints"), as a tool reading
    only the spec would: the pins when they act, the start items the limit certainly keeps, then each modifier
    in its listed order on what it applies_to."""
    hints = tracker_hints()
    digits = flag_digits(flag_string, zora_flag_string)
    pins = hints["pins"]
    values = {entry["value"]: entry for entry in pins["values"]}
    places: dict[str, str] = {}
    if status(pins, digits) is Status.APPLIES:
        for location in pins["locations"]:
            pin = values[digits[location["field"]]]
            if pin["status"] == "item":
                places[location["location"]] = pin["item"]
    certain, absent = _start_fields(hints, digits)
    field_items = {entry["field"]: entry["item"] for entry in hints["start_items"]["fields"]}
    starts = {field: field_items[field] for field in certain}
    bomb_upgrade: bool | None = False
    for modifier in hints["modifiers"]:
        rule = status(modifier, digits)
        if modifier["id"] == "swap_swords_and_rings":
            places = _swapped(places, modifier, rule, certain, absent)
        elif "rename" in modifier:
            places = _renamed(places, modifier["rename"], rule)
            starts = _renamed(starts, modifier["rename"], rule)
        elif "acts_as" in modifier:
            bomb_upgrade = {Status.APPLIES: True, Status.UNKNOWN: None, Status.OFF: False}[rule]
        # Progressive Items acts only on items found in the world: a start item is the item itself (the ROM's
        # starting table holds it as drawn)
    start_items = tuple(starts.values())
    return StartKnowledge(places, start_items, bomb_upgrade, pegasus_boots(digits))


def _swapped(places: dict[str, str], modifier: Mapping[str, Any], rule: Status, certain: set[str],
             absent: set[str]) -> dict[str, str]:
    """Swap Swords and Rings on the pinned places: each pair's items trade places unless either is a start item
    (both fields Off: swapped; one certainly a start item: kept; otherwise unknown, so the place is left out)."""
    if rule is Status.OFF:
        return places
    out = dict(places)
    for pair in modifier["pairs"]:
        first, second = pair["items"]
        fields = pair["start_item_fields"]
        if rule is Status.UNKNOWN:
            pair_rule = Status.UNKNOWN
        elif all(field in absent for field in fields):
            pair_rule = Status.APPLIES
        elif any(field in certain for field in fields):
            pair_rule = Status.OFF
        else:
            pair_rule = Status.UNKNOWN
        for location, item in places.items():
            if item not in (first, second) or pair_rule is Status.OFF:
                continue
            if pair_rule is Status.UNKNOWN:
                del out[location]
            else:
                out[location] = second if item == first else first
    return out
