"""The public flags spec for outside tools (docs/flags-api.md): docs/flags-api/zora-flags.json and its JSON
Schema, docs/flags-api/zora-flags.schema.json, generated from zora/flags/, never written by hand.

    python3 scripts/flags_api.py            write both files
    python3 scripts/flags_api.py --check    exit 1 when either differs from what zora/flags/ gives now (the
                                            spec's zora_version aside: the release stamps it)
    python3 scripts/flags_api.py --published FOLDER
                                            the release's copy, zora-flags-<version>.json with this checkout's
                                            ZORA_VERSION, and the schema (make_release.py, publish_site.sh)
    python3 scripts/flags_api.py --presets-against PUBLISHED NEW
                                            whether presets.json NEW should replace PUBLISHED, the site's
                                            copy: prints "write" or "keep", exit 1 when they conflict
                                            (scripts/gh_pages_commit.sh)

Each run without an option also writes docs/flags-api/presets.json, the presets a race bot can roll
(https://zora.gg/presets.json; docs/flags-api.md "Presets"), from zora/flags/presets.py's PRESET_LIST: every
preset with a ZORA string. Its revision is the committed counter in docs/flags-api/presets-revision.json,
which the run raises by one whenever the presets change; --check fails until it has, and checks the file
against every rule the bot checks (validate_presets).

The spec holds what a tool needs to read ZORA's two flag strings without copying ZORA's code: how to decode
them (the alphabet, each field's place and radix, the ZORA string's version rules), what each value means
(page names, Random, the page's starting value, beta), and tracker hints (the items a player can know from
the flags alone, at the start). Every fact comes from the code that ZORA itself runs: zora/flags/ for the
fields and names, and the generation steps for the hints' items and conditions.

tests/test_flags_api.py checks that both files are current and decodes a corpus of real flag strings with
the spec alone, comparing the result with zora/flags/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora.flags import form, zora_flags, zora_form  # noqa: E402
from zora.flags.codec import ALIASES, ALPHABET, canonicalize  # noqa: E402
from zora.flags.fields import (  # noqa: E402
    INERT_TOGGLES,
    ITEM_SHUFFLE_SCOPE,
    OPTION_FIELDS,
    PRINT_QUEST_INFO,
    THREE_STATE_LABELS,
    TOGGLE_FIELDS,
    OptionField,
    Settings,
    ThreeState,
    ToggleField,
)
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF, PRESET_LIST, Preset  # noqa: E402
from zora.flags.zora_flags import (  # noqa: E402
    CURRENT_VERSION,
    RETIRED_FIELDS,
    THREE_STATE_FIELDS,
    VERSION_SEPARATOR,
    ZoraField,
    ZoraFlags,
)
from zora.flags.zora_flags import FIELDS as ZORA_FIELDS  # noqa: E402
from zora.version import ZORA_VERSION  # noqa: E402
from zora_export.tracker_hints import page_default_settings, tracker_hints, z1r_settings_with  # noqa: E402

PAGE_SCRIPT = REPO / "web" / "zora-web.js"
SPEC_DIR = REPO / "docs" / "flags-api"
SPEC_FILE = SPEC_DIR / "zora-flags.json"
SCHEMA_FILE = SPEC_DIR / "zora-flags.schema.json"
# The spec's own version (docs/flags-api.md "Stability"): the minor number grows when the spec gains a
# property, the major number only for a change a tool written for the old spec would misread.
SPEC_VERSION = "1.0"
# Where each release publishes it (docs/flags-api.md "Where to get it").
SITE_ADDRESS = "https://zora.gg/flags/"
SCHEMA_ID = f"{SITE_ADDRESS}zora-flags.schema.json"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

THREE_STATE_KIND = "three_state"
SWITCH_KIND = "switch"
OPTION_KIND = "option"
RANDOM = int(ThreeState.POSSIBLE)
COIN_FLIP = [int(ThreeState.OFF), int(ThreeState.ON)]


# ---------------------------------------------------------------------------
# The page's view of a value: its control's number, for names and beta
# ---------------------------------------------------------------------------

def _base63(number: int) -> str:
    digits = []
    while number:
        number, digit = divmod(number, len(ALPHABET))
        digits.append(ALPHABET[digit])
    return "".join(reversed(digits)) or ALPHABET[0]


def zora_flags_with(digits: Mapping[str, int]) -> ZoraFlags:
    """The ZORA flags whose string holds these digits and 0 elsewhere, read by ZORA's own decoder: the
    string is built the way the spec says to read it, so each name below is the name of that digit."""
    if not digits:
        return zora_flags.decode("")
    version = max(field.version for field in ZORA_FIELDS if field.name in digits)
    number, place = 0, 1
    for field in ZORA_FIELDS:
        if field.version > version:
            continue
        number += digits.get(field.name, 0) * place
        place *= field.slots
    return zora_flags.decode(f"{version}{VERSION_SEPARATOR}{_base63(number)}")


# The page's controls that stand for two string fields (form.py, zora_form.py): each with the function giving
# its control's number from both strings, its value names, and the key the beta file uses for it.
CombinedControl = tuple[str, tuple[str, str], Callable[[Settings, ZoraFlags], int], Mapping[int, str], str]


def _l4_sword_row() -> dict[str, Any]:
    return next(row for row in zora_form.FIELDS if row["name"] == zora_form.L4_SWORD_FIELD)


def _l4_sword_labels() -> dict[int, str]:
    return {entry["value"]: entry["label"] for entry in _l4_sword_row()["values"]}


@cache
def combined_controls() -> tuple[CombinedControl, ...]:
    item_shuffle_labels = {value: form.value_label(ITEM_SHUFFLE_SCOPE, value)
                           for value in range(ITEM_SHUFFLE_SCOPE.count)}
    item_shuffle_labels[form.ITEM_SHUFFLE_NO_VANILLA_CHOICE] = form.ITEM_SHUFFLE_NO_VANILLA_LABEL
    return (
        (form.field_label(ITEM_SHUFFLE_SCOPE), (ITEM_SHUFFLE_SCOPE.id, zora_flags.ITEM_SHUFFLE_NO_VANILLA_FIELD),
         lambda z1r, zora: form._page_value(z1r, ITEM_SHUFFLE_SCOPE, zora), item_shuffle_labels,
         ITEM_SHUFFLE_SCOPE.id),
        (form.SPOILER_LEVEL_LABEL, (PRINT_QUEST_INFO.id, zora_flags.DETAILED_SPOILER_LOG_FIELD),
         lambda z1r, zora: form._page_value(z1r, PRINT_QUEST_INFO, zora), form.SPOILER_LEVEL_LABELS,
         PRINT_QUEST_INFO.id),
        (_l4_sword_row()["label"], (zora_form.L4_SWORD_FIELD, "l4_sword_in_level_2"),
         lambda z1r, zora: zora_form.control_value(zora, zora_form.L4_SWORD_FIELD), _l4_sword_labels(),
         zora_form.L4_SWORD_FIELD),
    )


def _control_of(key: str) -> CombinedControl | None:
    return next((control for control in combined_controls() if key in control[1]), None)


def _is_z1r_key(key: str) -> bool:
    return key[:1] in "CB" and key[1:].isdigit()


def page_value(key: str, digit: int) -> tuple[str, int]:
    """The page's control (its beta-file key) and the number it holds for one field at `digit`, the
    other fields at the page's starting values."""
    control = _control_of(key)
    z1r_digits = {key: digit} if _is_z1r_key(key) else {}
    zora_digits = {} if _is_z1r_key(key) else {key: digit}
    z1r, zora = z1r_settings_with(z1r_digits), zora_flags_with(zora_digits)
    if control is not None:
        return control[4], control[2](z1r, zora)
    if _is_z1r_key(key):
        return key, digit
    return key, zora_form.control_value(zora, key)


@cache
def beta_controls() -> dict[str, frozenset[int]]:
    """Each beta control's beta values by its control's numbers (zora/flags/flags.json, read by form)."""
    return form.beta_values()


def beta_digits(key: str, radix_values: Iterable[int]) -> list[int]:
    """The string values of a field that are beta, the other fields at the page's starting values."""
    out = []
    for digit in radix_values:
        control, number = page_value(key, digit)
        if number in beta_controls().get(control, frozenset()):
            out.append(digit)
    return out


# ---------------------------------------------------------------------------
# The Z1R string
# ---------------------------------------------------------------------------

def _z1r_value_names(field: OptionField | ToggleField) -> list[str]:
    if isinstance(field, OptionField):
        return [form.value_label(field, value) for value in range(field.count)]
    return [THREE_STATE_LABELS[state] for state in ThreeState]


def _z1r_randoms(field: OptionField | ToggleField) -> list[dict[str, Any]]:
    if isinstance(field, OptionField):
        return [{"value": int(value), "resolves_to": sorted(int(outcome) for outcome in outcomes)}
                for value, outcomes in sorted(field.random_choices.items())]
    return [{"value": RANDOM, "resolves_to": COIN_FLIP}]


def z1r_field(position: int, field: OptionField | ToggleField) -> dict[str, Any]:
    option = isinstance(field, OptionField)
    radix = field.slots if isinstance(field, OptionField) else len(ThreeState)
    value_count = field.count if isinstance(field, OptionField) else len(ThreeState)
    entry: dict[str, Any] = {
        "key": field.id,
        "position": position,
        "kind": OPTION_KIND if option else THREE_STATE_KIND,
        "radix": radix,
        "name": form.field_label(field),
        "description": form.spec_field_label(field),
        "values": _z1r_value_names(field),
        "random_values": _z1r_randoms(field),
        "default": (page_default_settings().option(field) if isinstance(field, OptionField)
                    else int(page_default_settings().toggle(field))),
        "beta_values": beta_digits(field.id, range(value_count)),
    }
    if field in INERT_TOGGLES:
        entry["no_effect"] = True
    control = _control_of(field.id)
    if control is not None:
        entry["page_control"] = control[0]
    return entry


def z1r_section() -> dict[str, Any]:
    all_fields: tuple[OptionField | ToggleField, ...] = (*OPTION_FIELDS, *TOGGLE_FIELDS)
    return {
        "about": ("One whole number written in the alphabet, most significant digit first. The fields are read "
                  "in position order, the first least significant: each field's value is the number modulo its "
                  "radix, and the number is then divided by the radix (whole division)."),
        "rules": {
            "empty_string": "refused",
            "character_outside_alphabet": "refused; an alphabet_aliases character reads as its digit",
            "leading_zeros": "ignored: '0' is the zero digit, so they change nothing",
            "option_digit_at_or_above_value_count": "read as the field's last value (len(values) - 1)",
            "number_left_after_the_last_field": "ignored",
        },
        "fields": [z1r_field(position, field) for position, field in enumerate(all_fields)],
    }


# ---------------------------------------------------------------------------
# The ZORA string
# ---------------------------------------------------------------------------

def _zora_row(name: str) -> dict[str, Any] | None:
    return next((row for row in zora_form.FIELDS if row["name"] == name), None)


def _zora_kind(field: ZoraField) -> str:
    if field.name in THREE_STATE_FIELDS or (field.name in RETIRED_FIELDS and field.slots == len(ThreeState)):
        return THREE_STATE_KIND
    if field.slots == 2 and field.name not in zora_flags.ENUM_FIELDS:
        return SWITCH_KIND
    return OPTION_KIND


def _zora_name(field: ZoraField) -> str | None:
    if field.name in RETIRED_FIELDS:
        return None
    row = _zora_row(field.name)
    if row is not None:
        return str(row["label"])
    # Add L4 Sword's second field: the page shows it as that control's Level 2
    l4_row = _zora_row(zora_form.L4_SWORD_FIELD)
    assert l4_row is not None and field.name == "l4_sword_in_level_2", field.name
    level_2 = next(entry["label"] for entry in l4_row["values"] if entry["label"] == "Level 2")
    return f"{l4_row['label']}: {level_2}"


def _zora_value_names(field: ZoraField) -> list[str | None]:
    """Each digit's name: a three-state field's Off / On / Random, a switch's Off / On or its control's two names,
    an option's control names (the control's number worked out from the decoded digit)."""
    if field.name in RETIRED_FIELDS:
        return [None] * field.slots
    kind = _zora_kind(field)
    if kind == THREE_STATE_KIND:
        return [THREE_STATE_LABELS[state] for state in ThreeState]
    row = _zora_row(field.name)
    if row is None or row["kind"] != OPTION_KIND:
        return [THREE_STATE_LABELS[ThreeState.OFF], THREE_STATE_LABELS[ThreeState.ON]]
    labels = {entry["value"]: entry["label"] for entry in row["values"]}
    return [labels[zora_form.control_value(zora_flags_with({field.name: digit}), field.name)]
            for digit in range(field.slots)]


def _zora_randoms(field: ZoraField) -> list[dict[str, Any]]:
    if field.name in RETIRED_FIELDS:
        return []
    if _zora_kind(field) == THREE_STATE_KIND:
        return [{"value": RANDOM, "resolves_to": COIN_FLIP}]
    row = _zora_row(field.name)
    if row is None:
        return []
    return [{"value": value, "resolves_to": sorted(outcomes)}
            for value, outcomes in sorted(form._zora_randoms(row).items())]


def _zora_default(field: ZoraField) -> int:
    """The digit whose value is the default (every field's is 0: the fields are only appended, off at 0)."""
    default = getattr(ZoraFlags(), field.name, None)
    if field.name in RETIRED_FIELDS:
        return 0
    return next(digit for digit in range(field.slots)
                if getattr(zora_flags_with({field.name: digit}), field.name) == default)


def zora_field(position: int, field: ZoraField) -> dict[str, Any]:
    retired = field.name in RETIRED_FIELDS
    entry: dict[str, Any] = {
        "key": field.name,
        "position": position,
        "kind": _zora_kind(field),
        "radix": field.slots,
        "added_in_version": field.version,
        "name": _zora_name(field),
        "values": _zora_value_names(field),
        "random_values": _zora_randoms(field),
        "default": _zora_default(field),
        "beta_values": [] if retired else beta_digits(field.name, range(field.slots)),
    }
    if retired:
        entry["retired"] = True
    row = _zora_row(field.name)
    if row is not None and row.get("hidden"):
        entry["hidden"] = True
    control = _control_of(field.name)
    if control is not None:
        entry["page_control"] = control[0]
    return entry


def zora_section() -> dict[str, Any]:
    return {
        "about": ("'<version>.<payload>': a decimal version, a dot, then one whole number in the alphabet. The "
                  "fields whose added_in_version is at most the string's version are read in position order, "
                  "the first least significant, as in the Z1R string. A field added after the string's version "
                  "is at its default."),
        "separator": VERSION_SEPARATOR,
        "pattern": f"^{zora_flags._STRING_PATTERN.pattern}$",
        "current_version": CURRENT_VERSION,
        "rules": {
            "empty_string": "every field at its default",
            "version_above_current_version": "refused",
            "character_outside_alphabet": "refused; an alphabet_aliases character reads as its digit",
            "number_left_after_the_last_field": "refused (a mistyped string never turns into other flags)",
            "retired_field": "read and ignored: its place stays, so every older string still decodes",
            "canonical_spelling": ("empty when every field is at its default; otherwise the lowest version holding "
                                   "every field away from its default, then the payload without leading zeros"),
        },
        "fields": [zora_field(position, field) for position, field in enumerate(ZORA_FIELDS)],
    }


# ---------------------------------------------------------------------------
# The page's file names (web/zora-web.js seedFileStem)
# ---------------------------------------------------------------------------

def _page_text(pattern: str, group: int = 1) -> str:
    """One fact about the page's file names, read from the page's own code (web/zora-web.js)."""
    found = re.findall(pattern, PAGE_SCRIPT.read_text(encoding="utf-8"), re.MULTILINE)
    assert len(found) == 1, f"the page's file names changed ({pattern}): update file_name_section"
    return str(found[0] if group == 1 else found[0][group - 1])


def _page_file_names() -> dict[str, Any]:
    """What seedFileStem and the names after it write: the first part, the stand-ins, the characters a name
    keeps, the version's test-channel ending, the music ending, each file's extension and the zip's."""
    extensions = {kind: _page_text(rf"^function {kind}FileName\(result\) {{\n  return `\$\{{result\.fileStem\}}"
                                   r"(\.[a-z.]+)`;")
                  for kind in ("rom", "spoiler", "tracker")}
    return {
        "prefix": _page_text(r'^  const stem = \["([a-z]+)", version, fileNameSafe\(flags\)'),
        "stand_ins": json.loads(_page_text(r"^const FILE_NAME_STAND_INS = (\{[^}]*\});")),
        "kept": _page_text(r"^const FILE_NAME_UNSAFE = /\[\^([^\]]+)\]/g;"),
        "test": _page_text(r'channel === TEST_CHANNEL \? "(-[a-z]+)" : ""'),
        "music": _page_text(r"^  return music \? `\$\{stem\}(-[a-z]+)` : stem;"),
        "extensions": extensions,
        "zip": _page_text(r'^  return `\$\{seedFileStem\(first, flags, zoraFlags\)\}-\$\{last\}'
                          r'\$\{music \? "-music" : ""\}(\.[a-z]+)`;'),
    }


REGEX_SPECIALS = re.compile(r"([.\\^$|?*+()\[\]{}])")
CLASS_SPECIALS = re.compile(r"([\\\]^])")


def _literal(text: str) -> str:
    """TEXT as a regular expression that Python and JavaScript (even with the u flag) both read the same."""
    return REGEX_SPECIALS.sub(r"\\\1", text)


def _character_class(characters: Iterable[str]) -> str:
    """A regular expression's class for these characters, runs of three or more as ranges, "-" last."""
    wanted = set(characters)
    runs: list[list[str]] = []
    for character in sorted(wanted - {"-"}, key=ord):
        if runs and ord(character) == ord(runs[-1][-1]) + 1:
            runs[-1].append(character)
        else:
            runs.append([character])
    text = "".join(f"{run[0]}-{run[-1]}" if len(run) >= 3 else "".join(run) for run in runs)
    return "[" + CLASS_SPECIALS.sub(r"\\\1", text) + ("-" if "-" in wanted else "") + "]"


def _class_members(page_class: str) -> list[str]:
    """The printable characters the page's character class (its source text) holds."""
    return [chr(code) for code in range(0x20, 0x7F) if re.fullmatch(f"[{page_class}]", chr(code))]


def file_name_section() -> dict[str, Any]:
    page = _page_file_names()
    stand_ins: dict[str, str] = page["stand_ins"]
    assert all(ALIASES.get(stand_in) == character for character, stand_in in stand_ins.items()), \
        "each character the page's file names swap must be swapped for an alias of it (zora/flags/codec.py ALIASES)"
    flag_characters = _character_class(stand_ins.get(character, character) for character in ALPHABET)
    version = f"({_character_class(_class_members(page['kept']))}+?)"
    zora = f"((?:[1-9][0-9]*{_literal(VERSION_SEPARATOR)}{flag_characters}+)?)"
    stem = f"^{page['prefix']}-{version}-({flag_characters}+)-{zora}-([0-9]+)"
    music = f"({_literal(page['music'])})?"
    extensions = "|".join(_literal(extension) for extension in page["extensions"].values())
    return {
        "about": ("The page names each seed's files <prefix>-<version>-<Z1R flag string>-<ZORA flag string>-<seed>, "
                  "then the music ending when the seed has randomized music, then the file's extension. The page "
                  "writes the alphabet's '!' as its alias '_' (alphabet_aliases), so each flag part is a flag "
                  "string as it stands: decode it as it is. An empty ZORA string (every ZORA "
                  "field at its default) leaves '--'. Neither flag string holds '-', so a name also reads from "
                  "the right: past any music ending, the seed, the ZORA string, the Z1R string, then the version, "
                  "which may hold '-'."),
        "prefix": page["prefix"],
        "separator": "-",
        "parts": [
            {"part": "version", "about": (
                "The ZORA version the page shows, its spaces as '-' and parentheses dropped: '2.0.1' on the "
                f"regular channel. On the test channel the build's short commit follows it and '{page['test']}' "
                f"ends it: '2.0.1-a1b2c3d{page['test']}'. A version is not a flag; ZoraTracker's ZoraVersion "
                "and the spec's zora_version are the release version without these.")},
            {"part": "z1r", "about": "The Z1R flag string."},
            {"part": "zora", "about": "The ZORA flag string; empty when every "
                                      "ZORA field is at its default."},
            {"part": "seed", "about": "The seed number, in decimal."},
            {"part": "music", "about": f"'{page['music']}' when the seed has randomized music (Music: Random, a "
                                       "player setting in neither flag string); absent otherwise."},
        ],
        "test_channel_ending": page["test"],
        "music_ending": page["music"],
        "extensions": {extension: kind for kind, extension in
                       (("rom", page["extensions"]["rom"]), ("spoiler_log", page["extensions"]["spoiler"]),
                        ("tracker_file", page["extensions"]["tracker"]))},
        "pattern": f"{stem}{music}({extensions})$",
        "groups": ["version", "z1r", "zora", "seed", "music", "extension"],
        "batch_zip": {
            "about": ("Several seeds at once: a .zip named for the first seed's stem, then '-' and the last seed, "
                      "then the music ending. It holds each seed's files under the names above; a batch saved to "
                      "a folder writes the same names."),
            "pattern": f"{stem}-([0-9]+){music}{_literal(page['zip'])}$",
            "groups": ["version", "z1r", "zora", "first_seed", "last_seed", "music"],
        },
        "tolerate": {
            "duplicate_suffix": {
                "about": ("A browser that saves a name twice adds a number before the extension: ' (1)' "
                          "(Chrome, Edge) or '(1)' (Firefox). Remove it before matching."),
                "pattern": r" ?\([0-9]+\)(?=\.[a-z.]+$)",
            },
            "renamed": ("A name that does not match the pattern is not the page's: read nothing from it, and ask "
                        "for the flag strings to be pasted instead."),
            "before_2_0_1": ("ZORA before 2.0.1 named files zora-seed-<seed>.nes (with '-encoded' or '-music' "
                             "before the extension) and batches zora-seeds-<first>-<last>.zip: those names hold "
                             "the seed only, no version or flags, and match neither pattern."),
            "archipelago": ("Archipelago names its files itself (AP_<multiworld seed>_P<player>_<player name>, "
                            ".apzora for the patch and .nes for the ROM it makes): they hold no ZORA flags, and "
                            "match neither pattern."),
        },
    }


# ---------------------------------------------------------------------------
# The page's controls over two fields
# ---------------------------------------------------------------------------

def _digit_range(key: str) -> range:
    if _is_z1r_key(key):
        field = form.FIELDS_BY_ID[key]
        return range(field.count if isinstance(field, OptionField) else len(ThreeState))
    return range(next(field.slots for field in ZORA_FIELDS if field.name == key))


def combined_control(control: CombinedControl) -> dict[str, Any]:
    """One page control over two fields: each of its values with the two digits that stand for it (the first
    pair in digit order, the canonical one), and whether it is beta."""
    name, (first, second), number_of, labels, beta_key = control
    found: dict[int, dict[str, int]] = {}
    for first_digit in _digit_range(first):
        for second_digit in _digit_range(second):
            digits = {first: first_digit, second: second_digit}
            z1r = z1r_settings_with({key: value for key, value in digits.items() if _is_z1r_key(key)})
            zora = zora_flags_with({key: value for key, value in digits.items() if not _is_z1r_key(key)})
            found.setdefault(number_of(z1r, zora), digits)
    beta = beta_controls().get(beta_key, frozenset())
    return {"name": name, "fields": [first, second],
            "values": [{"name": labels[number], "fields": found[number], "beta": number in beta}
                       for number in sorted(found)]}


# ---------------------------------------------------------------------------
# The whole spec, and its schema
# ---------------------------------------------------------------------------

def build() -> dict[str, Any]:
    return {
        "$schema": SCHEMA_ID,
        "spec_version": SPEC_VERSION,
        "zora_version": ZORA_VERSION,
        "generated_by": "scripts/flags_api.py from zora/flags/ (docs/flags-api.md); do not edit",
        "alphabet": ALPHABET,
        "alphabet_aliases": ALIASES,
        "page_default": {"z1r": MVP_BASELINE_LEVEL_ENCODING_OFF, "zora": zora_flags.encode(ZoraFlags())},
        "z1r": z1r_section(),
        "zora": zora_section(),
        "combined_controls": [combined_control(control) for control in combined_controls()],
        "tracker_hints": tracker_hints(),
        "file_name": file_name_section(),
    }


def _condition_list() -> dict[str, Any]:
    return {"type": "array", "items": {"$ref": "#/$defs/condition"}}


def schema() -> dict[str, Any]:
    """The spec's JSON Schema. Objects allow properties a later minor version adds (docs/flags-api.md)."""
    integer = {"type": "integer", "minimum": 0}
    integers = {"type": "array", "items": integer}
    strings = {"type": "array", "items": {"type": "string"}}
    random_values = {"type": "array", "items": {
        "type": "object", "required": ["value", "resolves_to"],
        "properties": {"value": integer, "resolves_to": integers}}}
    common_field = {
        "key": {"type": "string"}, "position": integer, "kind": {"enum": [OPTION_KIND, THREE_STATE_KIND, SWITCH_KIND]},
        "radix": {"type": "integer", "minimum": 2}, "values": {"type": "array", "items": {"type": ["string", "null"]}},
        "random_values": random_values, "default": integer, "beta_values": integers,
        "page_control": {"type": "string"},
    }
    return {
        "$schema": SCHEMA_DIALECT,
        "$id": SCHEMA_ID,
        "title": "ZORA flags spec",
        "description": "ZORA's two flag strings, how to decode them and what they mean (docs/flags-api.md).",
        "type": "object",
        "required": ["spec_version", "zora_version", "alphabet", "alphabet_aliases", "page_default", "z1r", "zora",
                     "combined_controls", "tracker_hints", "file_name"],
        "properties": {
            "$schema": {"type": "string"},
            "spec_version": {"type": "string", "pattern": r"^[0-9]+\.[0-9]+$"},
            "zora_version": {"type": "string"},
            "generated_by": {"type": "string"},
            "alphabet": {"type": "string", "minLength": 2},
            "alphabet_aliases": {"type": "object", "additionalProperties": {"type": "string", "minLength": 1,
                                                                            "maxLength": 1}},
            "page_default": {"type": "object", "required": ["z1r", "zora"],
                             "properties": {"z1r": {"type": "string"}, "zora": {"type": "string"}}},
            "z1r": {"type": "object", "required": ["rules", "fields"], "properties": {
                "fields": {"type": "array", "items": {
                    "type": "object",
                    "required": ["key", "position", "kind", "radix", "name", "values", "random_values", "default",
                                 "beta_values"],
                    "properties": {**common_field, "key": {"type": "string", "pattern": "^[CB][0-9]{2}$"},
                                   "name": {"type": "string"}, "description": {"type": "string"},
                                   "no_effect": {"type": "boolean"}}}}}},
            "zora": {"type": "object", "required": ["separator", "pattern", "current_version", "rules", "fields"],
                     "properties": {
                         "separator": {"type": "string"}, "pattern": {"type": "string"},
                         "current_version": {"type": "integer", "minimum": 1},
                         "fields": {"type": "array", "items": {
                             "type": "object",
                             "required": ["key", "position", "kind", "radix", "added_in_version", "name", "values",
                                          "random_values", "default", "beta_values"],
                             "properties": {**common_field, "key": {"type": "string", "pattern": "^[a-z0-9_]+$"},
                                            "added_in_version": {"type": "integer", "minimum": 1},
                                            "name": {"type": ["string", "null"]},
                                            "retired": {"type": "boolean"}, "hidden": {"type": "boolean"}}}}}},
            "combined_controls": {"type": "array", "items": {
                "type": "object", "required": ["name", "fields", "values"],
                "properties": {"name": {"type": "string"}, "fields": {"type": "array", "items": {"type": "string"}},
                               "values": {"type": "array", "items": {
                                   "type": "object", "required": ["name", "fields", "beta"],
                                   "properties": {"name": {"type": "string"},
                                                  "fields": {"type": "object", "additionalProperties": integer},
                                                  "beta": {"type": "boolean"}}}}}}},
            "tracker_hints": {"type": "object", "required": ["pins", "start_items", "modifiers"], "properties": {
                "pins": {"type": "object", "required": ["applies_when", "unknown_when", "locations", "values"],
                         "properties": {
                             "applies_when": _condition_list(), "unknown_when": _condition_list(),
                             "locations": {"type": "array", "items": {
                                 "type": "object", "required": ["location", "field", "name"],
                                 "properties": {"location": {"type": "string"}, "field": {"type": "string"},
                                                "name": {"type": "string"}}}},
                             "values": {"type": "array", "items": {
                                 "type": "object", "required": ["value", "status"],
                                 "properties": {"value": integer,
                                                "status": {"enum": ["not_pinned", "item", "unknown"]},
                                                "item": {"type": "string"}, "not_item": {"type": "string"}}}}}},
                "start_items": {"type": "object", "required": ["fields", "limit_field", "limits"], "properties": {
                    "fields": {"type": "array", "items": {
                        "type": "object", "required": ["field", "item"],
                        "properties": {"field": {"type": "string"}, "item": {"type": "string"}}}},
                    "limit_field": {"type": "string"},
                    "limits": {"type": "array", "items": {
                        "type": "object", "required": ["value"],
                        "properties": {"value": integer, "limit": {"type": ["integer", "null"]},
                                       "random": {"type": "boolean"}}}}}},
                "modifiers": {"type": "array", "items": {
                    "type": "object", "required": ["id", "applies_to", "applies_when", "unknown_when"],
                    "properties": {"id": {"type": "string"},
                                   "applies_to": {"type": "array", "items": {"enum": ["locations", "start_items"]}},
                                   "applies_when": _condition_list(), "unknown_when": _condition_list()}}}}},
            "file_name": {"type": "object", "required": ["prefix", "separator", "parts", "extensions",
                                                         "pattern", "groups", "batch_zip", "tolerate"],
                          "properties": {
                              "prefix": {"type": "string"}, "separator": {"type": "string"},
                              "parts": {"type": "array", "items": {
                                  "type": "object", "required": ["part", "about"],
                                  "properties": {"part": {"type": "string"}, "about": {"type": "string"}}}},
                              "test_channel_ending": {"type": "string"}, "music_ending": {"type": "string"},
                              "extensions": {"type": "object", "additionalProperties": {"type": "string"}},
                              "pattern": {"type": "string"}, "groups": strings,
                              "batch_zip": {"type": "object", "required": ["pattern", "groups"],
                                            "properties": {"pattern": {"type": "string"}, "groups": strings}},
                              "tolerate": {"type": "object", "required": ["duplicate_suffix"], "properties": {
                                  "duplicate_suffix": {"type": "object", "required": ["pattern"],
                                                       "properties": {"pattern": {"type": "string"}}}}}}},
        },
        "$defs": {"condition": {"type": "object", "additionalProperties": integers,
                                "description": "Every named field (a Z1R key or a ZORA key) holds one of its values."}},
    }


def render(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def published_name(version: str = ZORA_VERSION) -> str:
    """The release's copy of the spec (make_release.py's asset, zora-flags-<version>.json)."""
    return f"zora-flags-{version}.json"


def stale(path: Path, text: str) -> bool:
    """Whether PATH differs from TEXT, the spec's zora_version aside: the repository's copy is a work copy whose
    zora_version is the release it was last written for, so a version bump never makes it stale; a published
    copy carries its real version (write_published)."""
    if not path.exists():
        return True
    found = path.read_text(encoding="utf-8")
    if path != SPEC_FILE:
        return found != text
    try:
        committed = json.loads(found)
    except ValueError:
        return True
    return found != render({**json.loads(text), "zora_version": committed.get("zora_version")})


def write_published(folder: Path) -> list[Path]:
    """The spec as a release publishes it, zora_version this checkout's ZORA_VERSION, and its schema, into FOLDER:
    zora-flags-<version>.json and zora-flags.schema.json."""
    folder.mkdir(parents=True, exist_ok=True)
    written = {folder / published_name(): render(build()), folder / SCHEMA_FILE.name: render(schema())}
    for path, text in written.items():
        path.write_text(text, encoding="utf-8")
    return list(written)


# ---------------------------------------------------------------------------
# presets.json: the presets a race bot can roll (docs/flags-api.md "Presets")
# ---------------------------------------------------------------------------

PRESETS_FILE = SPEC_DIR / "presets.json"
# The committed counter: the revision, when it was raised and the SHA-256 of the flagsets it was raised for.
# A run whose flagsets hash differently raises the revision; --check fails while they differ.
PRESETS_REVISION_FILE = SPEC_DIR / "presets-revision.json"
PRESETS_SCHEMA_VERSION = 1
# The race bot's rules (TTPBot's registry contract, tests/fixtures/flagsets-contract.json, and its ZORA
# category): any failure makes it refuse the whole file.
MAX_REVISION = 2**53 - 1
MAX_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 500
Z1R_FLAGS_PATTERN = re.compile(r"[A-Za-z0-9!]{1,200}")
ZORA_FLAGS_PATTERN = re.compile(r"[1-9][0-9]*\.[0-9A-Za-z!]{1,200}")
# The bot's own commands, which no shortcut may reduce to: the five it named for the ZORA category, and the
# rest of its registry contract's reservedCommands.
RESERVED_SHORTCUTS = frozenset({"flags", "race", "cancel", "summary", "help", "grace", "schedule", "info",
                                "ttpflags", "ttpbot", "matchup", "z1rr", "optout", "optin", "ttp2", "ttp3",
                                "ttp4", "ttp5"})


def reduced(text: str) -> str:
    """How the bot compares names and shortcuts: lowercased, everything but a-z and 0-9 removed."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def preset_flagset(preset: Preset) -> dict[str, Any]:
    """One preset as a flagset of the bot's registry format: its one string, the latest."""
    return {"name": preset.name, "description": None, "shortcuts": [preset.key],
            "strings": [{"flags": canonicalize(preset.flags), "zora": preset.zora, "isLatest": True}]}


def presets_flagsets() -> list[dict[str, Any]]:
    """Every preset with a ZORA string, then every preset of a Z1R string alone that the page's menu shows
    (zora ""; revision 2), each group in PRESET_LIST's order: the ZORA presets keep the places they had
    before the Z1R ones joined. Random% stays out, as it stays off the menu."""
    with_zora = [preset for preset in PRESET_LIST if preset.zora]
    z1r_alone = [preset for preset in PRESET_LIST if not preset.zora and not preset.hidden]
    return [preset_flagset(preset) for preset in with_zora + z1r_alone]


def flagsets_digest(flagsets: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(flagsets, sort_keys=True).encode("utf-8")).hexdigest()


def read_presets_revision() -> dict[str, Any] | None:
    if not PRESETS_REVISION_FILE.exists():
        return None
    record: dict[str, Any] = json.loads(PRESETS_REVISION_FILE.read_text(encoding="utf-8"))
    return record


def next_presets_revision(flagsets: list[dict[str, Any]], record: dict[str, Any] | None,
                          now: datetime | None = None) -> dict[str, Any]:
    """The counter for FLAGSETS: RECORD as it is when it was raised for them, else raised by one (from 1),
    updatedAt the time of raising, to the second."""
    digest = flagsets_digest(flagsets)
    if record is not None and record.get("sha256") == digest:
        return record
    stamp = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {"revision": (record["revision"] if record else 0) + 1, "updatedAt": stamp, "sha256": digest}


def presets_document(flagsets: list[dict[str, Any]], record: Mapping[str, Any]) -> dict[str, Any]:
    """presets.json: FLAGSETS under the counter RECORD's revision and time (so the file is the same on every
    run until the presets change)."""
    return {"schemaVersion": PRESETS_SCHEMA_VERSION, "revision": record["revision"],
            "updatedAt": record["updatedAt"], "flagsets": flagsets}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _string_errors(where: str, entry: Any, zora_required: bool) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{where} is not an object"]
    errors = []
    flags = entry.get("flags")
    if not (isinstance(flags, str) and Z1R_FLAGS_PATTERN.fullmatch(flags)):
        errors.append(f"{where}: flags {flags!r} must match {Z1R_FLAGS_PATTERN.pattern}")
    if not isinstance(entry.get("isLatest"), bool):
        errors.append(f"{where}: isLatest must be true or false")
    if "zora" in entry or zora_required:
        zora = entry.get("zora")
        if not (zora == "" or (isinstance(zora, str) and ZORA_FLAGS_PATTERN.fullmatch(zora))):
            errors.append(f'{where}: zora {zora!r} must match {ZORA_FLAGS_PATTERN.pattern}, or be ""')
    return errors


def _flagset_errors(where: str, flagset: Any, zora_required: bool) -> list[str]:
    if not isinstance(flagset, dict):
        return [f"{where} is not an object"]
    errors = []
    name = flagset.get("name")
    if not isinstance(name, str) or len(name) > MAX_NAME_LENGTH:
        errors.append(f"{where}: name must be a string of at most {MAX_NAME_LENGTH} characters")
    elif not reduced(name):
        errors.append(f"{where}: name {name!r} has no letter or digit to compare")
    if "description" not in flagset:
        errors.append(f"{where}: description is missing (null for none)")
    elif flagset["description"] is not None and not (isinstance(flagset["description"], str)
                                                      and len(flagset["description"]) <= MAX_DESCRIPTION_LENGTH):
        errors.append(f"{where}: description must be null or a string of at most {MAX_DESCRIPTION_LENGTH} characters")
    shortcuts = flagset.get("shortcuts")
    if not isinstance(shortcuts, list):
        errors.append(f"{where}: shortcuts must be a list")
    else:
        errors += [f"{where}: shortcut {shortcut!r} has no letter or digit to compare" for shortcut in shortcuts
                   if not isinstance(shortcut, str) or not reduced(shortcut)]
    strings = flagset.get("strings")
    if not isinstance(strings, list) or not strings:
        return [*errors, f"{where}: strings must be a non-empty list"]
    for index, entry in enumerate(strings):
        errors += _string_errors(f"{where} string {index}", entry, zora_required)
    latest = [entry for entry in strings if isinstance(entry, dict) and entry.get("isLatest") is True]
    if len(latest) != 1:
        errors.append(f"{where}: exactly one string must have isLatest true ({len(latest)} do)")
    return errors


def validate_presets(snapshot: Any, reserved: Iterable[str] = RESERVED_SHORTCUTS,
                     zora_required: bool = True) -> list[str]:
    """Every rule the race bot checks before it uses presets.json, each failure a line (none: it is used).
    RESERVED are the bot's commands; ZORA_REQUIRED wants a zora key in every string (the Z1R registry's
    files, the same format without it, pass False)."""
    if not isinstance(snapshot, dict):
        return ["the file is not an object"]
    errors = []
    if not (_is_int(snapshot.get("schemaVersion")) and snapshot["schemaVersion"] == PRESETS_SCHEMA_VERSION):
        errors.append(f"schemaVersion must be the integer {PRESETS_SCHEMA_VERSION}")
    if not (_is_int(snapshot.get("revision")) and 1 <= snapshot["revision"] <= MAX_REVISION):
        errors.append(f"revision must be an integer from 1 to {MAX_REVISION}")
    flagsets = snapshot.get("flagsets")
    if not isinstance(flagsets, list) or not flagsets:
        return [*errors, "flagsets must be a non-empty list"]
    for index, flagset in enumerate(flagsets):
        errors += _flagset_errors(f"flagset {index}", flagset, zora_required)
    if errors:
        return errors
    reserved_forms = {reduced(command) for command in reserved}
    owner_of: dict[str, int] = {}
    pair_owner: dict[tuple[str, str], int] = {}
    for index, flagset in enumerate(flagsets):
        for shortcut in flagset["shortcuts"]:
            if reduced(shortcut) in reserved_forms:
                errors.append(f"flagset {index}: shortcut {shortcut!r} is one of the bot's commands")
        for form_text in [flagset["name"], *flagset["shortcuts"]]:
            owner = owner_of.setdefault(reduced(form_text), index)
            if owner != index:
                errors.append(f"flagset {index}: {form_text!r} reads as flagset {owner}'s {reduced(form_text)!r}")
        for entry in flagset["strings"]:
            pair = (entry["flags"], entry.get("zora", ""))
            owner = pair_owner.setdefault(pair, index)
            if owner != index:
                errors.append(f"flagset {index}: the strings {pair} are flagset {owner}'s too")
    return errors


def wanted_presets() -> tuple[str, dict[str, Any]]:
    """presets.json as the presets are now, and the counter it needs (raised when they changed)."""
    flagsets = presets_flagsets()
    record = next_presets_revision(flagsets, read_presets_revision())
    return render(presets_document(flagsets, record)), record


def presets_check() -> list[str]:
    """Why the committed presets.json and its counter are not current, or break a bot rule (none: they are)."""
    flagsets = presets_flagsets()
    problems = [f"presets.json would break the bot's rule: {error}"
                for error in validate_presets(presets_document(flagsets, {"revision": 1, "updatedAt": ""}))]
    record = read_presets_revision()
    if record is None or record.get("sha256") != flagsets_digest(flagsets):
        problems.append(f"the presets changed: run python3 scripts/flags_api.py, which raises the revision in "
                        f"{PRESETS_REVISION_FILE.relative_to(REPO)}")
    elif stale(PRESETS_FILE, render(presets_document(flagsets, record))):
        problems.append(f"{PRESETS_FILE.relative_to(REPO)} is not current: run python3 scripts/flags_api.py")
    return problems


def presets_against(published_text: str, new_text: str) -> str:
    """Whether the site's presets.json (PUBLISHED_TEXT) is replaced by NEW_TEXT: "write" for a higher revision,
    "keep" for the same file or a higher published revision (a publish from an older commit never takes the
    bot back); ValueError for the same revision with other presets, which the bot would never reread."""
    published, new = json.loads(published_text), json.loads(new_text)
    if new["revision"] > published["revision"]:
        return "write"
    if new["revision"] == published["revision"] and new["flagsets"] != published["flagsets"]:
        raise ValueError(f"presets.json revision {new['revision']} is already published with other presets: "
                         "raise the revision (python3 scripts/flags_api.py) and commit it")
    return "keep"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    chosen = parser.add_mutually_exclusive_group()
    chosen.add_argument("--check", action="store_true",
                        help="exit 1 when a file is not current (the spec's zora_version aside)")
    chosen.add_argument("--published", metavar="FOLDER", type=Path,
                        help="write the release's copy, zora-flags-<version>.json with zora_version set to this "
                             "ZORA_VERSION, and the schema into FOLDER")
    chosen.add_argument("--presets-against", nargs=2, metavar=("PUBLISHED", "NEW"), type=Path,
                        help='print "write" when presets.json NEW should replace PUBLISHED (the site\'s copy), '
                             '"keep" when not; exit 1 when they conflict')
    args = parser.parse_args(argv)
    if args.published:
        for path in write_published(args.published):
            print(f"flags_api: wrote {path}")
        return 0
    if args.presets_against:
        try:
            published, new = args.presets_against
            print(presets_against(published.read_text(encoding="utf-8"), new.read_text(encoding="utf-8")))
        except ValueError as exc:
            print(f"flags_api: {exc}", file=sys.stderr)
            return 1
        return 0
    wanted = {SPEC_FILE: render(build()), SCHEMA_FILE: render(schema())}
    if args.check:
        stale_files = [path for path, text in wanted.items() if stale(path, text)]
        for path in stale_files:
            print(f"flags_api: {path.relative_to(REPO)} is not current: run python3 scripts/flags_api.py")
        presets_problems = presets_check()
        for problem in presets_problems:
            print(f"flags_api: {problem}")
        if not stale_files and not presets_problems:
            print("flags_api: the spec, its schema and presets.json are current")
        return 1 if stale_files or presets_problems else 0
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    presets_text, record = wanted_presets()
    errors = validate_presets(json.loads(presets_text))
    if errors:
        for error in errors:
            print(f"flags_api: presets.json would break the bot's rule: {error}", file=sys.stderr)
        return 1
    wanted[PRESETS_FILE] = presets_text
    wanted[PRESETS_REVISION_FILE] = render(record)
    for path, text in wanted.items():
        path.write_text(text, encoding="utf-8")
        print(f"flags_api: wrote {path.relative_to(REPO)}")
    print(f"flags_api: presets.json is revision {record['revision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
