"""ZORA's options, generated from ZORA's own data, so a flag or setting added to ZORA appears here
without a change to this world:
- each flag field (zora.archipelago.option_fields) becomes a Choice named by its stable key, with
  its values named by their stable value keys (off, on, random_per_seed, first_quest, ...);
- each player setting (zora.archipelago.player_setting_fields) becomes a Choice too: a choice by
  its value keys, a color by its NES palette value ("0x29", which a YAML may also write
  unquoted), or a word as a TextChoice of the listed words that also takes any word ZORA's rule
  allows.

Archipelago's own `random` stays available everywhere: it picks one of the listed values, but never a beta
value (one that has not passed ZORA's logic scan, zora.archipelago.HELD_BACK). A YAML may name a beta value: it
generates, and the world logs ZORA's warning. ZORA's random_per_seed is a value of its own, ZORA's draw for the
seed.

A ZORA flag Archipelago never offers (zora.archipelago.never_offered_fields: Shuffle Wood Sword) is a
hidden option: a YAML may set it to off, and any other value is refused with ZORA's reason. A retired
flag a released world offered (Gatekeeper Bosses) is a hidden option too: any of its values is accepted
and ignored.
"""
import logging
import random
from dataclasses import make_dataclass
from typing import Any

from Options import Choice, DeathLink, OptionError, PerGameCommonOptions, TextChoice, Visibility

from .zora import archipelago as zora_ap


def normalized(word: str) -> str:
    """A typed word as ZORA's labels show it: capitals, no outer spaces (as the page does)."""
    return word.strip().upper()


def class_name_of(key: str) -> str:
    return "Zora" + "".join(part.capitalize() for part in key.split("_"))


def register(class_name: str, bases: tuple[type, ...], namespace: dict[str, Any]) -> type[Choice]:
    namespace |= {"__module__": __name__, "__qualname__": class_name}
    option_class = type(class_name, bases, namespace)
    assert class_name not in globals(), f"two options make the class {class_name}"
    globals()[class_name] = option_class        # so the class pickles by name, as AP's options must
    return option_class


def beta_note(spec: zora_ap.OptionSpec) -> str:
    """The option's text about its beta values, for the template and the options page."""
    labels = ", ".join(label for value, label in spec.choices if value in spec.beta)
    return (f"\nBeta values (not yet through ZORA's logic scan for multiworld): {labels}. "
            f"{zora_ap.MULTIWORLD_BETA_WARNING}")


def scanned_random(cls: type[Choice], text: str) -> Choice:
    """Archipelago's own random among the values that passed ZORA's logic scan, never a beta value; anything
    else as Choice reads it."""
    if text.lower() == "random":
        return cls(random.choice(cls.scanned_values))
    return Choice.from_text.__func__(cls, text)


def clamped_text(cls: type[Choice], text: str) -> Choice:
    """A value Archipelago reads as another (zora.archipelago.SWORD_HEARTS_CLAMPED: the magical-sword cave asks for at
    most 12 hearts), with a warning; anything else as the option reads it."""
    for _value, read, key, label in cls.clamped_values:
        if text.lower() in (key, label.lower()):
            option = cls(read)
            logging.warning(f"ZORA: {cls.display_name}: {label} is read as {option.current_option_name}: in "
                            f"Archipelago the Magical Sword Cave never asks for more than "
                            f"{zora_ap.MAX_MAGICAL_SWORD_HEARTS} hearts.")
            return option
    return (scanned_random if cls.beta_values else Choice.from_text.__func__)(cls, text)


def flag_class(spec: zora_ap.OptionSpec) -> type[Choice]:
    namespace: dict[str, Any] = {
        "__doc__": (spec.description or spec.name) + (beta_note(spec) if spec.beta else ""),
        "display_name": spec.name,
        "default": spec.default,
        "zora_id": spec.id,
        "beta_values": spec.beta,
        "scanned_values": spec.scanned_values,
    }
    namespace |= {f"option_{key}": value for value, key in spec.value_keys}
    if spec.beta:
        namespace["from_text"] = classmethod(scanned_random)
    if spec.clamped:
        namespace["clamped_values"] = spec.clamped
        namespace["from_text"] = classmethod(clamped_text)
    return register(class_name_of(spec.key), (Choice,), namespace)


def color_from_any(cls: type[Choice], data: Any) -> Choice:
    """A color by its palette number (an unquoted 0x29 in a YAML is the number 41) or its key,
    refused by its hex name rather than its decimal one."""
    if type(data) is int and data not in cls.name_lookup:
        raise ValueError(f"{cls.display_name}: 0x{data:02X} is not offered: NES palette values 0x00-0x3F, "
                         f"but not 0x0D")
    return Choice.from_any.__func__(cls, data)


def setting_class(spec: zora_ap.PlayerSettingSpec) -> type[Choice]:
    """A player setting as a Choice whose values stand for the page's values (setting_value).
    A color's value is its palette number; a choice's or word's is its place in the list."""
    page_values = [value for value, _key in spec.value_keys]
    namespace: dict[str, Any] = {
        "__doc__": f"{spec.label} (a cosmetic setting: it changes only how this player's game looks or sounds)",
        "display_name": spec.label,
        "zora_key": spec.key,
    }
    if spec.kind == zora_ap.COLOR:
        namespace |= {f"option_{key}": value for value, key in spec.value_keys}
        namespace["default"] = spec.default
        namespace["page_values"] = None
        namespace["from_any"] = classmethod(color_from_any)
        return register(class_name_of(spec.yaml_key), (Choice,), namespace)
    namespace |= {f"option_{key}": index for index, (_value, key) in enumerate(spec.value_keys)}
    # the page's spellings too (p1-up-a), where they differ from the keys (p1_up_a)
    # (not Random's "random", which Archipelago reads as its own: any value, drawn at generation)
    namespace |= {f"alias_{value}": index for index, (value, key) in enumerate(spec.value_keys)
                  if spec.kind == zora_ap.CHOICE and str(value).lower() != key and value != zora_ap.RANDOM_CHOICE}
    namespace["default"] = page_values.index(spec.default)
    # a retired value (zora.archipelago.RETIRED_LINK_SPRITE_KEYS) still reads, as the default
    namespace |= {f"alias_{key}": namespace["default"] for key in spec.retired_keys}
    namespace["page_values"] = tuple(page_values)
    if spec.kind == zora_ap.WORD:
        rule = spec.rule
        assert rule is not None
        length = (f"{rule.min_length}" if rule.min_length == rule.max_length
                  else f"{rule.min_length} to {rule.max_length}")
        namespace["__doc__"] += (f"\nOne of the words below, or type your own: {length} letters, digits or "
                                 f"punctuation the game's font has.")

        def validate_text(cls: type[TextChoice], text: str) -> None:
            if (reason := zora_ap.player_setting_problem(cls.zora_key, normalized(text))) is not None:
                raise ValueError(f"{cls.display_name}: {text!r}: {reason}")

        namespace["validate_text"] = classmethod(validate_text)
        return register(class_name_of(spec.yaml_key), (TextChoice,), namespace)
    return register(class_name_of(spec.yaml_key), (Choice,), namespace)


def never_offered_class(spec: zora_ap.OptionSpec) -> type[Choice]:
    """A ZORA flag Archipelago never offers, as a hidden option (no template, page or spoiler line):
    off passes (ZORA uses it anyway), anything else is refused when the YAML is read, with
    zora.archipelago.never_offered_refusal's reason, which Archipelago shows under its "Error
    generating option" line naming the player's file. A retired flag's every value passes, ignored."""

    def from_any(cls: type[Choice], data: Any) -> Choice:
        if (refusal := zora_ap.never_offered_refusal(cls.zora_key, data)) is not None:
            raise OptionError(refusal)
        return cls(cls.default)

    namespace: dict[str, Any] = {
        "__doc__": spec.description,
        "display_name": spec.name,
        "default": spec.default,
        "zora_key": spec.key,
        "visibility": Visibility.none,
        "from_any": classmethod(from_any),
    }
    namespace |= {f"option_{key}": value for value, key in spec.value_keys}
    return register(class_name_of(spec.key), (Choice,), namespace)


RENAMED_NOT_GIVEN, RENAMED_OFF, RENAMED_ON = 0, 1, 2


def renamed_class(old_key: str) -> type[Choice]:
    """A renamed option's old key (zora.archipelago.RENAMED_OPTIONS) as a hidden option: not given by default; off or
    on (a YAML's false or true) is read as the new option's value, with a note (zora_values)."""
    namespace: dict[str, Any] = {
        "__doc__": f"Renamed {zora_ap.RENAMED_OPTIONS[old_key]}.",
        "display_name": old_key,
        "default": RENAMED_NOT_GIVEN,
        "visibility": Visibility.none,
        "option_not_given": RENAMED_NOT_GIVEN,
        "option_off": RENAMED_OFF,
        "option_on": RENAMED_ON,
        "alias_false": RENAMED_OFF,
        "alias_true": RENAMED_ON,
    }
    return register(class_name_of(old_key), (Choice,), namespace)


OPTION_SPECS: tuple[zora_ap.OptionSpec, ...] = tuple(zora_ap.option_fields())
SETTING_SPECS: tuple[zora_ap.PlayerSettingSpec, ...] = tuple(zora_ap.player_setting_fields())
OPTION_CLASSES: dict[str, type[Choice]] = {spec.key: flag_class(spec) for spec in OPTION_SPECS}
SETTING_CLASSES: dict[str, type[Choice]] = {spec.yaml_key: setting_class(spec) for spec in SETTING_SPECS}
NEVER_OFFERED_CLASSES: dict[str, type[Choice]] = {spec.key: never_offered_class(spec)
                                                   for spec in zora_ap.never_offered_fields()}
assert not set(OPTION_CLASSES) & set(SETTING_CLASSES), "a player setting shares an option's key"
assert not set(NEVER_OFFERED_CLASSES) & (set(OPTION_CLASSES) | set(SETTING_CLASSES)), "a hidden option is offered"
RENAMED_CLASSES: dict[str, type[Choice]] = {old_key: renamed_class(old_key) for old_key in zora_ap.RENAMED_OPTIONS}
assert not set(RENAMED_CLASSES) & (set(OPTION_CLASSES) | set(SETTING_CLASSES) | set(NEVER_OFFERED_CLASSES))

# Archipelago's own options, which are no ZORA flag or player setting: DeathLink (client-only,
# docs/design/archipelago-items.md piece 2) changes neither the ROM nor the recipe.
ARCHIPELAGO_OPTIONS: dict[str, type[Any]] = {"death_link": DeathLink}
assert not set(ARCHIPELAGO_OPTIONS) & (set(OPTION_CLASSES) | set(SETTING_CLASSES) | set(NEVER_OFFERED_CLASSES)
                                       | set(RENAMED_CLASSES))

ZoraOptions = make_dataclass("ZoraOptions", [*OPTION_CLASSES.items(), *SETTING_CLASSES.items(),
                                             *NEVER_OFFERED_CLASSES.items(), *RENAMED_CLASSES.items(),
                                             *ARCHIPELAGO_OPTIONS.items()],
                             bases=(PerGameCommonOptions,))


def zora_values(options: Any, player_name: str = "") -> dict[str, int]:
    """The chosen flags as zora.archipelago.flag_strings takes them: option key -> value. A renamed option's old
    key, when the YAML gives it, sets the new option, with a note in the log."""
    values = {key: int(getattr(options, key).value) for key in OPTION_CLASSES}
    for old_key in RENAMED_CLASSES:
        given = int(getattr(options, old_key).value)
        if given == RENAMED_NOT_GIVEN:
            continue
        new_key, value, note = zora_ap.renamed_option(old_key, "on" if given == RENAMED_ON else "off")
        assert value is not None
        values[new_key] = value
        logging.warning(f"ZORA ({player_name}): {note}." if player_name else f"ZORA: {note}.")
    return values


def setting_value(option: Choice) -> str | int:
    """A player setting's value as the page has it (finish and recipe take it)."""
    if isinstance(option.value, str):           # a typed word, as ZORA's label shows it
        return normalized(option.value)
    if option.page_values is None:              # a color
        return option.value
    return option.page_values[option.value]


def player_settings(options: Any) -> dict[str, str | int]:
    """The chosen player settings by their page keys, as finish and recipe take them."""
    return {option_class.zora_key: setting_value(getattr(options, key))
            for key, option_class in SETTING_CLASSES.items()}
