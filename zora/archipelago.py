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
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any

from .flags import form as flag_form
from .flags import zora_flags, zora_form
from .flags.codec import decode, encode
from .flags.dependencies import apply_dependencies, check_dependencies, correct_merchant_toll
from .flags.fields import ENCODE_LEVEL_DATA, OptionField, Settings, ThreeState
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
from .rom.base_rom import BaseRomMismatch, is_prg0, player_rom, remember_base_rom
from .rom.code_patches import SHOPS_BY_NUMBER
from .rom.player_settings import player_settings_from_page
from .version import PLAYER_NAME, ZORA_VERSION

__all__ = [
    "DEFAULT_FLAGS",
    "DEFAULT_ZORA_FLAGS",
    "FOREIGN",
    "GOAL_STATE",
    "RECEIVED_COUNT",
    "RECEIVE_STATE",
    "BuildResult",
    "Foreign",
    "OptionSpec",
    "OptionsConflict",
    "PlaceInfo",
    "RamCheck",
    "RecipeNotReproduced",
    "RecipeRefused",
    "RomIdentity",
    "SlotNameRefused",
    "UnknownItem",
    "build",
    "build_from_strings",
    "finish",
    "flag_strings",
    "give_rules",
    "goal_reached",
    "may_receive",
    "option_corrections",
    "option_fields",
    "pickup_checks",
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
# encoded seed is refused at plan time anyway (owner decision 2: nothing else is left out).
FORCED_OFF = ENCODE_LEVEL_DATA.id
CHOICE, THREE_STATE, SWITCH = "choice", "three_state", "switch"
THREE_STATE_LABELS = {ThreeState.OFF: "Off", ThreeState.ON: "On", ThreeState.POSSIBLE: "Random (decided per seed)"}


@dataclass(frozen=True)
class OptionSpec:
    """One ZORA flag field as an Archipelago option: its id (a Z1R field's, "C01" or "B08", or a
    ZORA flag's name), name and description; its kind ("choice"; "three_state": off, on, or
    random per seed; "switch": off or on); the values it offers, each with a label (only values
    ZORA generates: the support matrix's, "?" only where it allows one); and the default."""
    id: str
    name: str
    description: str
    kind: str
    choices: tuple[tuple[int, str], ...]
    default: int

    @property
    def values(self) -> tuple[int, ...]:
        return tuple(value for value, _label in self.choices)


class OptionsConflict(ValueError):
    """Option values ZORA refuses together (a dependency rule), named for the player."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("ZORA cannot generate these options: " + "; ".join(reasons))
        self.reasons = reasons


def _z1r_spec(field: flag_form.FieldDef, defaults: Settings) -> OptionSpec:
    is_option = isinstance(field, OptionField)
    choices = tuple((int(value), flag_form.value_label(field, value)) for value in flag_form.supported_values(field))
    held = defaults.options if is_option else defaults.toggles
    default = int(held[field.id]) if field.id in held else choices[0][0]     # a field newer than the preset
    return OptionSpec(field.id, flag_form.field_label(field), field.setting, CHOICE if is_option else THREE_STATE,
                      choices, default)


def _zora_spec(field: Mapping[str, Any], defaults: zora_flags.ZoraFlags) -> OptionSpec:
    name = field["name"]
    if field["kind"] == "option":
        kind, choices = CHOICE, tuple((value["value"], value["label"]) for value in field["values"])
    elif field["kind"] == zora_form.THREE_STATE_KIND:
        kind, choices = THREE_STATE, tuple((int(state), label) for state, label in THREE_STATE_LABELS.items())
    else:
        kind, choices = SWITCH, ((0, "Off"), (1, "On"))
    default = zora_form.control_value(defaults, name) if hasattr(defaults, name) else choices[0][0]
    return OptionSpec(name, field["label"], field["help"], kind, choices, default)


def option_fields() -> list[OptionSpec]:
    """Every ZORA flag field Archipelago offers, from zora/flags (the page's fields, labels,
    support matrix and ZORA Extras tab), so a new field appears here by itself: the Z1R fields
    but B82, then the ZORA flags."""
    defaults = decode(DEFAULT_FLAGS)
    zora_defaults = zora_flags.decode(DEFAULT_ZORA_FLAGS)
    specs = [_z1r_spec(field, defaults) for field in flag_form.ALL_FIELDS if field.id != FORCED_OFF]
    specs += [_zora_spec(field, zora_defaults) for field in zora_form.FIELDS]
    return specs


def _chosen(values: Mapping[str, object]) -> dict[str, int]:
    """Every option's value: the given ones (each one the option offers), the rest the defaults."""
    specs = {spec.id: spec for spec in option_fields()}
    unknown = sorted(set(values) - set(specs))
    if unknown:
        raise OptionsConflict([f"unknown options {unknown}"])
    chosen = {name: spec.default for name, spec in specs.items()}
    for name, value in values.items():
        if not isinstance(value, int) or value not in specs[name].values:
            raise OptionsConflict([f"{specs[name].name} ({name}): {value!r} is not one of {list(specs[name].values)}"])
        chosen[name] = int(value)
    return chosen


def _settings(chosen: Mapping[str, int]) -> Settings:
    toggles = {field.id: ThreeState(chosen[field.id]) for field in flag_form.ALL_FIELDS
               if not isinstance(field, OptionField) and field.id != FORCED_OFF}
    return decode(DEFAULT_FLAGS).updated(
        options={field.id: chosen[field.id] for field in flag_form.ALL_FIELDS if isinstance(field, OptionField)},
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
    """Archipelago's option values (OptionSpec id -> value; a missing option takes its default)
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


# --- build and finish (spec "Design" 2 and 3) ------------------------------------------------------

class UnknownItem(ValueError):
    """An item name that is not the seed format's name of an item."""


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
    names (selectButton, greenTunic, ...). `ap_name`: the slot name the client logs in with
    (1 to 23 bytes, no zero byte; rom_identity reads it back), written into the ROM, so each
    slot's seed code differs. Raises AssignmentRefused (a place's rule broken),
    AssignmentUnbeatable (the sanity check) or SlotNameRefused, never a ROM that ZORA's walk
    rejects."""
    record = b"" if ap_name is None else slot_identity.slot_identity_record(ap_name, FORMAT_VERSION_NUMBERS)
    return finish_seed(result.state, player_rom(), assigned_items(assignment),
                       player_settings_from_page(player_settings or {}),
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
        "playerSettings": dict(player_settings or {}),
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


def receive(item: str, ram: Mapping[int, int], rules: inventory.GiveRules = NO_RULES) -> dict[int, int]:
    """The RAM writes that give a received item as the game gives a picked-up one (address ->
    value; `ram` holds at least the inventory, $0657-$067C): a line item at its next level with
    Progressive Items (Add L4 Sword: a sword at level 3 gives 4), else the higher of the two
    grades; a heart container one more container and one more heart; an amount added within its
    cap. Another player's item is never received. Call it only during normal play."""
    return inventory.give(item_named(item), ram, rules)


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
