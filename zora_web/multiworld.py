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
from zora.flags.fields import OptionField, ThreeState
from zora.rom.link_art import offered_sprite_sets
from zora.rom.player_settings import PAGE_LINK_SPRITE, PlayerSettingError
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
# Every field Archipelago never offers, with the one value it uses's reason. The page shows only the ones held
# for now (archipelago.NOT_OFFERED_YET), locked; the PERMANENTLY_OFF ones are not on the Multiworld tab at all
# (owner, 2026-11-21), and a value of one in the page's strings is ignored, with a note (ignored_notes).
FIXED_REASONS = {
    archipelago.FORCED_OFF: "Always off in Archipelago.",
    **dict.fromkeys(archipelago.FIXED_OPTIONS, "Always Full in Archipelago: Archipelago places the items itself."),
    **archipelago.ZORA_FORCED_OFF,
    **archipelago.Z1R_FORCED_OFF,
}
SHOWN_FIXED = {field_id: reason for field_id, reason in FIXED_REASONS.items()
               if field_id in archipelago.NOT_OFFERED_YET}


class ExportRefused(ValueError):
    """The page's settings cannot become a YAML: each reason, worded for the player."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


# Archipelago's own DeathLink (docs/design/archipelago-items.md piece 2): no ZORA setting, so the
# page sends it beside the multiworld settings as deathLink, and the YAML names it death_link.
DEATH_LINK_KEY = "deathLink"
DEATH_LINK_YAML_KEY = "death_link"
DEATH_LINK_VALUES = {"off": "false", "on": "true"}


def archipelago_option_values(settings: Mapping[str, Any]) -> dict[str, str]:
    """Archipelago's own options from the page's settings, by their YAML keys (DeathLink, Off by
    default). ExportRefused for a value the page never offers."""
    value = settings.get(DEATH_LINK_KEY, "off")
    if value not in DEATH_LINK_VALUES:
        raise ExportRefused([f"DeathLink: {value!r} is neither off nor on"])
    return {DEATH_LINK_YAML_KEY: DEATH_LINK_VALUES[value]}


def _fixed_value(field_id: str) -> int:
    return int(archipelago.FIXED_OPTIONS.get(field_id, 0))      # B82 and ZORA_FORCED_OFF are off


def metadata() -> dict[str, Any]:
    """What the page needs for multiworld mode: per field (a Z1R field's id, a ZORA flag's name)
    the values Archipelago offers, and those of them that are beta values (not through the logic
    scan: offered only with Enable Beta Flags on, with the warning); the fields it does not offer
    yet, with the one value it uses and why; the reason a value is not offered; the name's limit,
    the game's name and where this version's zora.apworld is. A field in none of offered and fixed
    (archipelago.PERMANENTLY_OFF) is not on the Multiworld tab."""
    specs = archipelago.option_fields()
    offered = {spec.id: list(spec.values) for spec in specs}
    beta = {spec.id: list(spec.beta) for spec in specs if spec.beta}
    fixed = {field_id: {"value": _fixed_value(field_id), "reason": reason}
             for field_id, reason in SHOWN_FIXED.items()}
    return {"offered": offered, "beta": beta, "fixed": fixed, "notOffered": NOT_OFFERED_YET, "game": GAME,
            "betaTitle": archipelago.MULTIWORLD_BETA_TITLE, "betaWarning": archipelago.MULTIWORLD_BETA_WARNING,
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


def _field_labels() -> dict[str, str]:
    labels = {field.id: flag_form.field_label(field) for field in flag_form.ALL_FIELDS}
    return labels | {field["name"]: field["label"] for field in zora_form.FIELDS}


def ignored_notes(flag_string: str, zora_flag_string: str) -> list[str]:
    """A note for each field off in Archipelago for good (archipelago.PERMANENTLY_OFF, not on the Multiworld
    tab) that these strings set away from the value Archipelago uses: the YAML leaves it out, and the
    world uses its value."""
    page = _page_values(flag_string, zora_flag_string)
    labels = _field_labels()
    notes = [f"{labels[field_id]}: {_label_of(field_id, page[field_id])} in these flags is ignored. {reason}"
             for field_id, reason in FIXED_REASONS.items()
             if field_id in archipelago.PERMANENTLY_OFF and page[field_id] != _fixed_value(field_id)]
    return notes + sword_hearts_notes(page)


def sword_hearts_notes(page: Mapping[str, int]) -> list[str]:
    """A note for each magical-sword heart value these strings set above what Archipelago allows
    (archipelago.SWORD_HEARTS_CLAMPED): the YAML names the value it is read as."""
    return [f"{spec.name}: {label} is read as {dict(spec.choices)[read]} in Archipelago: the Magical Sword Cave "
            f"never asks for more than {archipelago.MAX_MAGICAL_SWORD_HEARTS} hearts there."
            for spec in archipelago.option_fields() for value, read, _key, label in spec.clamped
            if page[spec.id] == value]


def _label_of(field_id: str, value: int) -> str:
    return next((label for number, label in _all_labels(field_id) if number == value), str(value))


def beta_in_use(flag_string: str, zora_flag_string: str) -> list[str]:
    """The beta values (OptionSpec.beta: not through the logic scan) these strings use, each as "Name: Label"."""
    page = _page_values(flag_string, zora_flag_string)
    return [f"{spec.name}: {dict(spec.choices)[page[spec.id]]}" for spec in archipelago.option_fields()
            if page[spec.id] in spec.beta]


def option_values(flag_string: str, zora_flag_string: str) -> dict[str, str]:
    """The page's settings as Archipelago options, every one by its key and value key.
    ExportRefused names each value Archipelago does not offer (or a field not offered yet away from
    the one value Archipelago uses). A field off for good (archipelago.PERMANENTLY_OFF) is left out
    whatever its value: ignored_notes names it."""
    page = _page_values(flag_string, zora_flag_string)
    labels = _field_labels()
    reasons = [f"{labels[field_id]}: {reason}" for field_id, reason in SHOWN_FIXED.items()
               if page[field_id] != _fixed_value(field_id)]
    values = {}
    for spec in archipelago.option_fields():
        key = dict(spec.value_keys).get(spec.read_as(page[spec.id]))
        if key is None:
            reasons.append(f"{spec.name}: {_label_of(spec.id, page[spec.id])} is not offered in Archipelago yet")
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


def _comment(text: str, width: int = 100) -> list[str]:
    """TEXT as comment lines of at most about WIDTH characters."""
    lines, line = [], "#"
    for word in text.split():
        if len(line) + 1 + len(word) > width and line != "#":
            lines.append(line)
            line = "#"
        line += " " + word
    return [*lines, line]


def yaml_text(name: str, options: Mapping[str, str], player_settings: Mapping[str, str],
              archipelago_options: Mapping[str, str] | None = None) -> str:
    """The YAML file: the beta warning when an option has a beta value (archipelago.beta_in_use), the
    two flag strings the options make (to paste back into the page; a reader skips comments), then
    name, game and description, then the game's block, options first, then player settings, then
    Archipelago's own options (DeathLink)."""
    flag_string, zora_flag_string = archipelago.flag_strings(options)
    beta = archipelago.beta_in_use(options)
    warning = [*_comment(f"WARNING: {archipelago.MULTIWORLD_BETA_TITLE}: {'; '.join(beta)}. "
                         f"{archipelago.MULTIWORLD_BETA_WARNING}"), "#"] if beta else []
    lines = [*warning,
             f"# ZORA {ZORA_VERSION}: Archipelago player options, exported from the web page.",
             "# Put this file in Archipelago's Players folder with the other players' YAMLs.",
             "# The same settings as flag strings, for the web page's flag boxes:",
             f"# {FLAG_STRING_COMMENT}: {flag_string}",
             f"# {ZORA_FLAG_STRING_COMMENT}: {zora_flag_string}".rstrip(),
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
    if archipelago_options:
        lines.append("  # Archipelago's own options")
        lines += [f"  {key}: {_scalar(value)}" for key, value in archipelago_options.items()]
    return "\n".join(lines) + "\n"


FLAG_STRING_COMMENT, ZORA_FLAG_STRING_COMMENT = "Z1R flags", "ZORA flags"


def file_name(name: str) -> str:
    """The YAML's file name: the player name's letters, digits, dashes and underscores."""
    stem = "".join(char if char.isascii() and (char.isalnum() or char in "-_") else "_" for char in name.strip())
    return f"{stem.strip('_') or 'player'}.yaml"


def check(flag_string: str, zora_flag_string: str, settings: Mapping[str, Any]) -> dict[str, Any]:
    """Whether the page's settings can become a YAML (the name aside): the reasons they cannot,
    and the corrections ZORA makes on its own (option_corrections), as the page shows them; and
    whatever the verdict, the beta values in use (beta_in_use) and the values the YAML leaves out
    (ignored_notes)."""
    shown = {"beta": beta_in_use(flag_string, zora_flag_string),
             "ignored": ignored_notes(flag_string, zora_flag_string)}
    try:
        options = option_values(flag_string, zora_flag_string)
        archipelago.flag_strings(options)
        notes = archipelago.option_corrections(options)
        player_setting_values(settings)
        archipelago_option_values(settings)
    except ExportRefused as refused:
        return {"ok": False, "reasons": refused.reasons, "notes": [], **shown}
    except archipelago.OptionsConflict as conflict:
        return {"ok": False, "reasons": list(conflict.reasons), "notes": [], **shown}
    except PlayerSettingError as problem:
        return {"ok": False, "reasons": [str(problem)], "notes": [], **shown}
    return {"ok": True, "reasons": [], "notes": notes, **shown}


def export_yaml(name: str, flag_string: str, zora_flag_string: str, settings: Mapping[str, Any]) -> dict[str, str]:
    """The player's YAML and its file name. ExportRefused for a bad name or settings check refuses."""
    problem = player_name_problem(name)
    verdict = check(flag_string, zora_flag_string, settings)
    reasons = ([f"Player name: {problem}"] if problem else []) + verdict["reasons"]
    if reasons:
        raise ExportRefused(reasons)
    text = yaml_text(name, option_values(flag_string, zora_flag_string), player_setting_values(settings),
                     archipelago_option_values(settings))
    return {"yaml": text, "fileName": file_name(name)}


# --- loading a player's YAML back into the page (2026-11-21) ----------------------------------------

YAML_TOP_KEYS = ("name", "game", "description")
ARCHIPELAGO_RANDOM = "random"            # Archipelago's own random: a value drawn when it generates
NOT_A_YAML = "This file has no ZORA: block, so the page loaded nothing from it."
# death_link as a YAML may write it (True and False are also 1 and 0)
DEATH_LINK_READ: dict[object, str] = {True: "on", False: "off", "true": "on", "false": "off", "on": "on",
                                      "off": "off", "yes": "on", "no": "off"}


def _weighted(given: Any) -> tuple[Any, str | None]:
    """A YAML value, or the one value a weighted choice ({value: weight}) can draw; the problem otherwise."""
    if not isinstance(given, dict):
        return given, None
    drawn = [value for value, weight in given.items() if isinstance(weight, int) and weight > 0]
    if len(drawn) == 1:
        return drawn[0], None
    return None, f"{json.dumps(given)} is weighted: Archipelago draws one when it generates"


def _option_value(spec: archipelago.OptionSpec, given: Any) -> tuple[int | None, str | None]:
    """One option's value from a YAML (its value key, any case; its number; an unquoted true or false for a
    switch), or why it can't be read."""
    given, problem = _weighted(given)
    if problem:
        return None, problem
    if isinstance(given, bool) and spec.kind != archipelago.CHOICE:
        given = int(ThreeState.ON if given else ThreeState.OFF)
    if isinstance(given, str):
        text = given.strip().lower()
        if text == ARCHIPELAGO_RANDOM:
            return None, "random: Archipelago picks a value when it generates"
        value = spec.value_of_key(text)
    elif isinstance(given, int) and not isinstance(given, bool) and given in spec.values:
        value = given
    else:
        value = None
    if value is None:
        keys = ", ".join(key for _value, key in spec.value_keys)
        return None, f"{json.dumps(given)} is not offered (one of: {keys})"
    return value, None


def _left_out_keys() -> dict[str, tuple[str, str, int]]:
    """Every YAML key of a setting Archipelago leaves out (never offered or retired), by option key and by
    id: (its name, its reason, the one value Archipelago uses)."""
    labels = _field_labels()
    left: dict[str, tuple[str, str, int]] = {}
    for spec in archipelago.never_offered_fields():
        left[spec.key] = (spec.name, spec.description, spec.default)
    for field_id, reason in FIXED_REASONS.items():
        field = flag_form.FIELDS_BY_ID.get(field_id)
        keys = (field_id, archipelago.option_key(field)) if field is not None else (field_id,)
        for key in keys:
            left[key] = (labels[field_id], reason, _fixed_value(field_id))
    return left


# How the page keeps a built-in sprite set chosen (web/zora-web.js LINK_SPRITE_BUILT_IN): its id after this
LINK_SPRITE_BUILT_IN = "built-in:"


def _page_setting(spec: archipelago.PlayerSettingSpec, given: Any) -> Any:
    """A player setting's YAML value (checked) as the page keeps it: a built-in sprite set by "built-in:" and
    its id (the page fetches the set), anything else as archipelago.page_player_settings reads it."""
    if spec.key == PAGE_LINK_SPRITE and isinstance(given, str):
        page_value = {key: value for value, key in spec.value_keys}.get(given.strip().lower(), given)
        return f"{LINK_SPRITE_BUILT_IN}{page_value}" if page_value in offered_sprite_sets() else page_value
    return archipelago.page_player_settings({spec.yaml_key: given})[spec.key]


def read_yaml(document: Any) -> dict[str, Any]:
    """A player's Archipelago YAML, as the page's reader parsed it, as the page's settings, best effort
    (owner request, 2026-11-21): {"loaded", "flags", "zoraFlags", "name" (None when the YAML names none),
    "playerSettings" (by page key: only those the YAML names and the page takes, DeathLink among them),
    "problems"}. Every option, player setting and the name are applied where they can be; each key or value
    that can't be (a key the page doesn't know, a value not offered, a setting Archipelago leaves out, a
    weighted or random choice) is named in problems, and never stops the rest. An option the YAML leaves
    out takes Archipelago's default, as the world would. loaded is False, and nothing else is given, when
    the file has no ZORA block."""
    if not isinstance(document, dict) or not isinstance(document.get(GAME), dict):
        return {"loaded": False, "problems": [NOT_A_YAML]}
    problems = [f"{key}: not a ZORA setting, so the page doesn't read it" for key in document
                if key not in (*YAML_TOP_KEYS, GAME)]
    name = document.get("name")
    if name is not None and not isinstance(name, str):
        problems.append(f"name: {json.dumps(name)} is not text, so the player name is unchanged")
        name = None
    game = document.get("game")
    if game != GAME and not (isinstance(game, dict) and GAME in game):
        problems.append(f"game: {json.dumps(game)} is not {GAME}")
    specs = {spec.key: spec for spec in archipelago.option_fields()}
    settings_by_key = {spec.yaml_key: spec for spec in archipelago.player_setting_fields()}
    left_out = _left_out_keys()
    chosen: dict[str, int] = {}
    player: dict[str, Any] = {}
    for key, given in document[GAME].items():
        where = f"{GAME}: {key}"
        if key in specs:
            value, problem = _option_value(specs[key], given)
            if value is None:
                problems.append(f"{where}: {problem}; {specs[key].name} keeps its default")
            else:
                chosen[specs[key].id] = value
        elif key in settings_by_key:
            spec = settings_by_key[key]
            setting, problem = _weighted(given)
            try:
                if problem:
                    raise PlayerSettingError(problem)
                archipelago.check_player_settings({key: setting})
            except PlayerSettingError as refused:
                problems.append(f"{where}: {refused}; {spec.label} is unchanged")
            else:
                value = _page_setting(spec, setting)
                # a word as the page and the world hold it: capitals, no outer spaces
                player[spec.key] = value.strip().upper() if spec.kind == archipelago.WORD else value
        elif key == DEATH_LINK_YAML_KEY:
            death_link, problem = _weighted(given)
            text = death_link.strip().lower() if isinstance(death_link, str) else death_link
            if problem or not isinstance(text, str | int) or text not in DEATH_LINK_READ:
                problems.append(f"{where}: {problem or json.dumps(death_link) + ' is neither true nor false'}; "
                                f"DeathLink is unchanged")
            else:
                player[DEATH_LINK_KEY] = DEATH_LINK_READ[text]
        elif key in archipelago.RENAMED_OPTIONS:
            setting, problem = _weighted(given)
            new_key, value, note = archipelago.renamed_option(key, setting)
            if problem or value is None:
                problems.append(f"{where}: {problem or note}")
            elif new_key in document[GAME]:
                problems.append(f"{where}: {note}, but the YAML gives {new_key} too, which wins")
            else:
                chosen[specs[new_key].id] = value
                problems.append(f"{where}: {note}")
        elif key in left_out:
            label, reason, _value = left_out[key]
            kept = ("it stays off" if key in archipelago.NOT_OFFERED_YET
                    else "it is not on the Multiworld tab, so the page leaves it out")
            problems.append(f"{where}: {label}: {kept}. {reason}")
        else:
            problems.append(f"{where}: not a setting this page knows, so it was left out")
    flag_string, zora_flag_string = archipelago.page_flag_strings(chosen)
    return {"loaded": True, "flags": flag_string, "zoraFlags": zora_flag_string, "name": name,
            "playerSettings": player, "problems": problems}
