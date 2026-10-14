"""The web page's multiworld mode: what Archipelago offers, the player name, and the player's
Archipelago YAML, all from zora/archipelago.py (docs/archipelago.md "Interface").

The page's settings stay its own flag strings and player settings; this module turns them into
the YAML the ZORA world reads (the shape of the world's own template: name, game, description,
then every option and player setting under the game's name) and refuses what the world would
refuse: a value Archipelago does not offer, a conflict flag_strings names, a player setting
check_player_settings refuses, a name Archipelago would cut short or the ROM cannot hold.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from zora import archipelago
from zora.flags import form as flag_form
from zora.flags import zora_flags, zora_form
from zora.flags.codec import decode
from zora.flags.fields import OptionField
from zora.rom.player_settings import PlayerSettingError
from zora.rom.slot_identity import MAX_NAME_LENGTH as SLOT_NAME_MAX_BYTES
from zora.version import ZORA_VERSION

# The game's name in Archipelago (the world's archipelago.json, "game").
GAME = "ZORA"
# Archipelago keeps a player name's first 16 characters (Generate.handle_name) and refuses this one.
PLAYER_NAME_MAX_LENGTH = 16
RESERVED_PLAYER_NAME = "Archipelago"

# Where each release's zora.apworld is (scripts/make_release.py builds it for that release's GitHub
# release, tagged v<ZORA_VERSION> like every earlier one): this page links its own version's world,
# whose generator is this page's.
RELEASES_URL = "https://github.com/tetraly/zora/releases"
APWORLD_FILE = "zora.apworld"


def release_tag(version: str = ZORA_VERSION) -> str:
    """The public repository's tag of a release, and of its GitHub release."""
    return f"v{version}"


def apworld_url(version: str = ZORA_VERSION) -> str:
    """The download link of a release's zora.apworld, a GitHub release asset."""
    return f"{RELEASES_URL}/download/{release_tag(version)}/{APWORLD_FILE}"


NOT_OFFERED_YET = "Not offered in Archipelago yet."
FIXED_REASONS = {
    archipelago.FORCED_OFF: "Always off in Archipelago.",
    **dict.fromkeys(archipelago.FIXED_OPTIONS, "Always Full in Archipelago: Archipelago places the items itself."),
}


class ExportRefused(ValueError):
    """The page's settings cannot become a YAML: each reason, worded for the player."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _fixed_value(field_id: str) -> int:
    return int(archipelago.FIXED_OPTIONS.get(field_id, 0))      # B82 (FORCED_OFF) is off


def metadata() -> dict[str, Any]:
    """What the page needs for multiworld mode: per field (a Z1R field's id, a ZORA flag's name)
    the values Archipelago offers; the fields it never offers, with the one value it uses and why;
    the reason a value is not offered; the name's limit, the game's name and where this version's
    zora.apworld is."""
    offered = {spec.id: list(spec.values) for spec in archipelago.option_fields()}
    fixed = {field_id: {"value": _fixed_value(field_id), "reason": reason}
             for field_id, reason in FIXED_REASONS.items()}
    return {"offered": offered, "fixed": fixed, "notOffered": NOT_OFFERED_YET, "game": GAME,
            "nameMaxLength": PLAYER_NAME_MAX_LENGTH, "apworldUrl": apworld_url()}


def player_name_problem(name: str) -> str | None:
    """What is wrong with a player name, or None: 1 to 16 characters once its outer spaces go
    (Archipelago cuts a longer one short), not "Archipelago", and at most 23 bytes as UTF-8 with
    no zero byte (the slot name the ROM holds)."""
    name = name.strip()
    if not name:
        return "type a player name"
    if len(name) > PLAYER_NAME_MAX_LENGTH:
        return f"at most {PLAYER_NAME_MAX_LENGTH} characters (this one has {len(name)})"
    if name == RESERVED_PLAYER_NAME:
        return f'Archipelago refuses the name "{RESERVED_PLAYER_NAME}"'
    if len(name.encode()) > SLOT_NAME_MAX_BYTES or "\0" in name:
        return f"too long for the ROM: at most {SLOT_NAME_MAX_BYTES} bytes as UTF-8 (fewer accented or other letters)"
    return None


def _page_values(flag_string: str, zora_flag_string: str) -> dict[str, int]:
    """Every page field's value by id (Z1R) or name (ZORA extras)."""
    settings = decode(flag_string)
    values = {field.id: int(settings.options[field.id] if isinstance(field, OptionField)
                            else settings.toggles[field.id]) for field in flag_form.ALL_FIELDS}
    flags = zora_flags.decode(zora_flag_string)
    values |= {field["name"]: zora_form.control_value(flags, field["name"]) for field in zora_form.FIELDS}
    return values


def option_values(flag_string: str, zora_flag_string: str) -> dict[str, str]:
    """The page's settings as Archipelago options, every one by its key and value key.
    ExportRefused names each value Archipelago does not offer (or a never-offered field away from
    the one value Archipelago uses)."""
    page = _page_values(flag_string, zora_flag_string)
    labels = {field.id: flag_form.field_label(field) for field in flag_form.ALL_FIELDS}
    reasons = [f"{labels[field_id]}: {reason}" for field_id, reason in FIXED_REASONS.items()
               if page[field_id] != _fixed_value(field_id)]
    values = {}
    for spec in archipelago.option_fields():
        key = dict(spec.value_keys).get(page[spec.id])
        if key is None:
            label = next((label for value, label in _all_labels(spec.id) if value == page[spec.id]), str(page[spec.id]))
            reasons.append(f"{spec.name}: {label} is not offered in Archipelago yet")
        else:
            values[spec.key] = key
    if reasons:
        raise ExportRefused(reasons)
    return values


def _all_labels(option_id: str) -> list[tuple[int, str]]:
    """Every value of a page field with its page label, offered or not."""
    field = next((field for field in flag_form.ALL_FIELDS if field.id == option_id), None)
    if field is not None:
        return [(value, flag_form.value_label(field, value)) for value in flag_form.field_values(field)]
    zora_field = next(field for field in flag_form.metadata()["zora"]["fields"] if field["name"] == option_id)
    return [(int(entry["value"]), entry["label"]) for entry in zora_field["values"]]


def player_setting_values(settings: Mapping[str, Any]) -> dict[str, str]:
    """The page's player settings (its keys and values, the Look and feel tab) as the YAML's: each
    setting by its YAML key, a listed value by its value key, a typed word as typed. Every setting
    is named: a missing one takes its default. PlayerSettingError as finish() would raise it."""
    values = {}
    for spec in archipelago.player_setting_fields():
        value = settings.get(spec.key, spec.default)
        values[spec.yaml_key] = dict(spec.value_keys).get(value, value if isinstance(value, str) else str(value))
    archipelago.check_player_settings(values)
    return values


def _scalar(text: str) -> str:
    """A YAML double-quoted scalar: JSON's string form is one, so off and on stay text, never
    YAML 1.1's booleans, and any name or word is written safely."""
    return json.dumps(text, ensure_ascii=False)


def yaml_text(name: str, options: Mapping[str, str], player_settings: Mapping[str, str]) -> str:
    """The YAML file: name, game and description, then the game's block, options first."""
    lines = [f"# ZORA {ZORA_VERSION}: Archipelago player options, exported from the web page.",
             "# Put this file in Archipelago's Players folder with the other players' YAMLs.",
             "",
             f"name: {_scalar(name.strip())}",
             f"game: {_scalar(GAME)}",
             f"description: {_scalar(f'ZORA {ZORA_VERSION}, exported from the web page')}",
             "",
             f"{GAME}:",
             "  # Options (each by its key, every one named)"]
    lines += [f"  {key}: {_scalar(value)}" for key, value in options.items()]
    lines.append("  # How your game looks and sounds (only your game)")
    lines += [f"  {key}: {_scalar(value)}" for key, value in player_settings.items()]
    return "\n".join(lines) + "\n"


def file_name(name: str) -> str:
    """The YAML's file name: the player name's letters, digits, dashes and underscores."""
    stem = "".join(char if char.isascii() and (char.isalnum() or char in "-_") else "_" for char in name.strip())
    return f"{stem.strip('_') or 'player'}.yaml"


def check(flag_string: str, zora_flag_string: str, settings: Mapping[str, Any]) -> dict[str, Any]:
    """Whether the page's settings can become a YAML (the name aside): the reasons they cannot,
    and the corrections ZORA makes on its own (option_corrections), as the page shows them."""
    try:
        options = option_values(flag_string, zora_flag_string)
        archipelago.flag_strings(options)
        notes = archipelago.option_corrections(options)
        player_setting_values(settings)
    except ExportRefused as refused:
        return {"ok": False, "reasons": refused.reasons, "notes": []}
    except archipelago.OptionsConflict as conflict:
        return {"ok": False, "reasons": list(conflict.reasons), "notes": []}
    except PlayerSettingError as problem:
        return {"ok": False, "reasons": [str(problem)], "notes": []}
    return {"ok": True, "reasons": [], "notes": notes}


def export_yaml(name: str, flag_string: str, zora_flag_string: str, settings: Mapping[str, Any]) -> dict[str, str]:
    """The player's YAML and its file name. ExportRefused for a bad name or settings check refuses."""
    problem = player_name_problem(name)
    verdict = check(flag_string, zora_flag_string, settings)
    reasons = ([f"Player name: {problem}"] if problem else []) + verdict["reasons"]
    if reasons:
        raise ExportRefused(reasons)
    text = yaml_text(name, option_values(flag_string, zora_flag_string), player_setting_values(settings))
    return {"yaml": text, "fileName": file_name(name)}
