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
from functools import cache
from typing import Any

from zora.flags.codec import ALPHABET, FlagStringError, canonicalize, decode, encode
from zora.flags.dependencies import apply_dependencies, check_dependencies, correct_merchant_toll
from zora.flags.fields import (
    BOMB_UPGRADE_PERSON_SHUFFLE,
    ENCODE_LEVEL_DATA,
    HUNGRY_GORIYA_SHUFFLE,
    MAGICAL_SWORD_HIGHEST_BASE,
    MAGICAL_SWORD_LOWEST_BASE,
    MAX_TRIFORCE_PIECES,
    MONEY_OR_LIFE_ROOMS,
    MONEY_OR_LIFE_TOLL,
    OPTION_FIELDS,
    TOGGLE_FIELDS,
    WHITE_SWORD_HIGHEST_BASE,
    WHITE_SWORD_LOWEST_BASE,
    OptionField,
    PinnedItem,
    Settings,
    ThreeState,
    ToggleField,
)
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF, PRESETS
from zora.flags.support import ENCODE_LEVEL_DATA_NOT_RANDOM, Support, mvp_baseline_settings, support
from zora.flags.zora_form import zora_flags_from_values, zora_metadata, zora_state
from zora.generate.pipeline import NOT_PRODUCED_PREFIX, FlagsRefused, plan
from zora.rom import level_encoding
from zora.version import PLAYER_VERSION

NOT_PRODUCED_TEXT = "Not produced by ZORA yet"
NOT_AVAILABLE_TEXT = "Not available in this build"
CURRENT_NOT_PRODUCED_TEXT = "This value is not produced by ZORA yet"
# FL-DEP-06: the toll re-draw has no meaning without the merchants.
TOLL_NEEDS_MERCHANTS_TEXT = f"Needs {MONEY_OR_LIFE_ROOMS.id} ({MONEY_OR_LIFE_ROOMS.setting})"
TOLL_TURNED_OFF_NOTE = (f"FL-DEP-06: {MONEY_OR_LIFE_TOLL.id} was turned off because "
                        f"{MONEY_OR_LIFE_ROOMS.id} is off")

# Owner ruling: the page may call the MVP baseline "Consternation".
PRESET_LABELS = {"MVP baseline": "Consternation"}
# CP-5: the MVP baseline with level encoding off. Listed with the presets so
# a build without level encoding has a preset it can produce.
LEVEL_ENCODING_OFF_PRESET = ("MVP baseline, level encoding off", "Consternation without level encoding",
                             MVP_BASELINE_LEVEL_ENCODING_OFF)

THREE_STATE_LABELS = {ThreeState.OFF: "Off", ThreeState.ON: "On", ThreeState.POSSIBLE: "Possible (decided per seed)"}

# The dependency rules as the page lists them; the check itself is flags.check_dependencies.
DEPENDENCY_RULES = (
    ("FL-DEP-01 rule 1", "The Ladder cannot be pinned to the coast cave."),
    ("FL-DEP-01 rule 2", "No item may be pinned to two places."),
    ("FL-DEP-02 rule 1", "Moving the wooden-sword cave (B02) or shuffling the take-any-road caves (B04) "
                         "needs a cave shuffle that moves non-dungeon caves."),
    ("FL-DEP-02 rule 2", "Shuffling the hungry goriya (B28), moving the start room (B26) and Ganon must be "
                         "beaten (B18) need the dungeon room shuffle."),
    ("FL-DEP-02 rule 3", "Moving monsters between levels (B36) and Ganon and Zelda in the shuffles (B33) "
                         "need the dungeon monster shuffle."),
    ("FL-DEP-02 rule 4", "Second-quest, mixed, and mixed-with-shapes dungeons turn the hungry-goriya and "
                         "bomb-upgrade-person shuffles (B28, B29) off."),
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


# The owner's names for the fields and option values (owner-authored; owner
# decision 2026-10-03), edited in docs/flag-names.csv and imported into
# zora/flags/names.json by scripts/flag_names.py. A field or value without
# one keeps its spec label; Encode level data always keeps its own label.
OWNER_NAMES_FILE = "names.json"


@cache
def owner_names() -> dict[str, dict[str, Any]]:
    from importlib.resources import files
    names: dict[str, dict[str, Any]] = json.loads(
        files("zora.flags").joinpath(OWNER_NAMES_FILE).read_text(encoding="utf-8")
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
    return str(owner_names().get(field.id, {}).get("name") or spec_field_label(field))


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
    """FL-PRE-01 to FL-PRE-04, plus CP-5; each disabled with its reasons when ZORA cannot produce it."""
    entries = [(name, PRESET_LABELS.get(name, name), string) for name, string in PRESETS.items()]
    entries.append(LEVEL_ENCODING_OFF_PRESET)
    out = []
    for name, label, string in entries:
        reasons = generation_refusals(string)
        out.append({"name": name, "label": label, "flags": canonicalize(string),
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
        "values": [{"value": value, "label": value_label(field, value),
                    "specLabel": spec_value_label(field, value)} for value in field_values(field)],
        "supportedValues": list(supported_values(field)),
    }
    if isinstance(field, OptionField):
        entry["slots"] = field.slots
        entry["randomValues"] = sorted(field.random_choices)
    if field == ENCODE_LEVEL_DATA:
        entry["help"] = level_encoding.HELP_TEXT
    return entry


def metadata() -> dict[str, Any]:
    """What the page builds its controls from, once at start-up."""
    return {
        "fields": [_field_metadata(field) for field in ALL_FIELDS],
        "encodeLevelData": ENCODE_LEVEL_DATA.id,
        "levelEncoding": {"available": level_encoding.is_available(), "label": level_encoding.LABEL,
                          "help": level_encoding.HELP_TEXT, "unavailable": NOT_AVAILABLE_TEXT},
        "dependencyRules": [{"rule": rule, "text": text} for rule, text in DEPENDENCY_RULES],
        "presets": presets(),
        "defaultFlags": MVP_BASELINE_LEVEL_ENCODING_OFF,
        "alphabet": ALPHABET,
        "zora": zora_metadata(),
        "version": PLAYER_VERSION,
    }


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
    if field == MONEY_OR_LIFE_TOLL and settings.toggle(MONEY_OR_LIFE_ROOMS) is ThreeState.OFF:
        # FL-DEP-06: greyed out and shown off while the merchants are off
        return {"value": value, "disabled": True, "reason": TOLL_NEEDS_MERCHANTS_TEXT, "problem": False,
                "blocked": {str(v): TOLL_NEEDS_MERCHANTS_TEXT for v in field_values(field) if v != value}}
    blocked = _blocked_values(settings, field, refused)
    current_ok = value in supported_values(field) and _value_unavailable(field, value) is None
    others = [v for v in field_values(field) if v != value]
    disabled = current_ok and all(v in blocked for v in others)
    if field == ENCODE_LEVEL_DATA and value == ThreeState.POSSIBLE:
        reason = ENCODE_LEVEL_DATA_NOT_RANDOM     # a pasted string with "?" there
    elif not current_ok:
        reason = _value_unavailable(field, value) or CURRENT_NOT_PRODUCED_TEXT
    elif disabled and len(supported_values(field)) == 1:
        reason = NOT_PRODUCED_TEXT       # the rule texts stay on the values themselves
    elif blocked:
        reason = blocked[min(blocked)]
    else:
        reason = None
    return {"value": value, "disabled": disabled, "reason": reason, "problem": not current_ok,
            "blocked": {str(v): text for v, text in blocked.items()}}


def form_state(flag_string: str, zora_flag_string: str = "") -> dict[str, Any]:
    """The controls for a flag string and a ZORA flag string, or the decoder's error."""
    try:
        decoded = decode(flag_string)
    except FlagStringError as exc:
        return {"ok": False, "error": f"Flag string: {exc}", "zora": zora_state(zora_flag_string, None)}
    # FL-DEP-06: never refused; the corrected string replaces the pasted one
    settings = correct_merchant_toll(decoded)
    refused = _refusal_texts(settings)
    adjusted = apply_dependencies(settings)
    adjustments = [TOLL_TURNED_OFF_NOTE] if settings != decoded else []
    adjustments += [f"FL-DEP-02 rule 4 turns {field_id} off" for field_id in (
        HUNGRY_GORIYA_SHUFFLE.id, BOMB_UPGRADE_PERSON_SHUFFLE.id
    )
        if adjusted.toggle(field_id) != settings.toggle(field_id)]
    canonical = encode(settings)
    zora = zora_state(zora_flag_string, adjusted)
    return {
        "ok": True,
        "flags": canonical,
        "fields": {field.id: _field_state(settings, field, refused) for field in ALL_FIELDS},
        "refusals": sorted(refused),
        "adjustments": adjustments,
        "generateRefusals": generation_refusals(canonical, zora["flags"] if zora["ok"] else zora_flag_string),
        "preset": next((p["name"] for p in presets() if p["flags"] == canonical), None),
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
    """The player changed a control: the new state, or the change blocked with the rule it breaks."""
    previous = decode(previous_flags)
    new_flags = flags_from_values(values)
    broken = sorted(_refusal_texts(decode(new_flags)) - _refusal_texts(previous))
    if broken:
        state = form_state(previous_flags, zora_flag_string)
        state["blockedChange"] = "; ".join(broken)
        return state
    return form_state(new_flags, zora_flag_string)


def zora_form_change(flag_string: str, zora_values: Mapping[str, int | str]) -> dict[str, Any]:
    """The player changed a ZORA Extras control: the state with the new ZORA string. Nothing is
    blocked or adjusted: a sword-hearts conflict is shown, for the player to resolve."""
    return form_state(flag_string, zora_flags_from_values(zora_values))
