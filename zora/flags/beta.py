"""Beta flags (owner rulings, 2026-11-05 and 2026-11-06; docs/beta-flags.md): which flags, or single values of
a flag, are still in beta, read from one file, zora/flags/flags.json.

Editing that file is the whole of marking a flag beta or graduating it: nothing else names a beta
flag. The page's Beta settings switch (UI only, never in a flag string) unlocks them; a string that
uses one is accepted and turns the switch on. Generation never reads this file, so marking or
graduating a flag changes no output.

The file's "flags" holds one object per flag, keyed by a Z1R flag's code ("C05") or a ZORA Extra's
field name ("harder_ganon"), so later per-flag fields (help text, author) can join it. Its "beta" is:
- "all" for the whole flag: every value but the one the page starts with (a fresh page never uses
  a beta setting); or
- a list of values, each the label the page shows ("Level 3") or the number its control holds (the
  index the flag string encodes for a Z1R option).
A Random that can resolve to a beta value is beta too (ruling 2026-11-06), whether listed or not.
Anything the page does not offer, and any key a flag's object does not know, is refused with the
reason, so a typo or a renamed value cannot quietly leave a flag out of beta
(tests/test_beta_flags.py loads the shipped file).
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from typing import Any

FLAGS_FILE = "flags.json"
FLAGS_KEY = "flags"
BETA_KEY = "beta"
FLAG_KEYS = frozenset({BETA_KEY})        # the keys a flag's object may hold
ALL_VALUES = "all"


class BetaConfigError(ValueError):
    """The flags file names a flag, key or value the page does not offer."""


@dataclass(frozen=True)
class FlagChoices:
    """One flag as the page offers it: its name, the value a fresh page starts with, each value's label by
    the number its control holds, and each Random value with the values it can resolve to."""
    name: str
    default: int
    labels: Mapping[int, str]
    randoms: Mapping[int, frozenset[int]] = field(default_factory=dict)


@cache
def flags_config() -> dict[str, Any]:
    """The shipped flags file, as data."""
    from importlib.resources import files
    config: dict[str, Any] = json.loads(files(__package__).joinpath(FLAGS_FILE).read_text(encoding="utf-8"))
    return config


def _value_of(key: str, choices: FlagChoices, given: object) -> int:
    """One listed value as its control's number: a label the page shows, or the number itself."""
    if isinstance(given, str):
        matches = [value for value, label in choices.labels.items() if label == given]
        if not matches:
            offered = ", ".join(f'"{label}"' for label in choices.labels.values())
            raise BetaConfigError(f'{key} ({choices.name}) has no value "{given}"; it offers {offered}')
        return matches[0]
    if isinstance(given, int) and not isinstance(given, bool) and given in choices.labels:
        return given
    raise BetaConfigError(f"{key} ({choices.name}) has no value {given!r}; its values are {sorted(choices.labels)}")


def _with_randoms(choices: FlagChoices, values: frozenset[int]) -> frozenset[int]:
    """The beta values with every Random that can resolve to one of them."""
    grown = set(values)
    while True:
        more = {random for random, outcomes in choices.randoms.items() if random not in grown and outcomes & grown}
        if not more:
            return frozenset(grown)
        grown |= more


def _listed_beta(key: str, choices: FlagChoices, listed: object) -> frozenset[int]:
    if listed == ALL_VALUES:
        return frozenset(choices.labels) - {choices.default}
    if isinstance(listed, list) and listed:
        return frozenset(_value_of(key, choices, given) for given in listed)
    raise BetaConfigError(f'{key} ({choices.name}): "{BETA_KEY}" must be "{ALL_VALUES}" or a list of values')


def beta_values(config: Mapping[str, Any], offered: Mapping[str, FlagChoices]) -> dict[str, frozenset[int]]:
    """The beta values of each flag the config marks, by its control's numbers, a Random that can resolve
    to one included (flags without one are left out)."""
    marked = config.get(FLAGS_KEY, {})
    if not isinstance(marked, Mapping):
        raise BetaConfigError(f'"{FLAGS_KEY}" must map each flag to its object, such as {{"{BETA_KEY}": ["Level 3"]}}')
    out: dict[str, frozenset[int]] = {}
    for key, entry in marked.items():
        choices = offered.get(key)
        if choices is None:
            raise BetaConfigError(f"{key} is not a flag the page offers (a Z1R code such as C05, or a ZORA "
                                  "Extra's field name such as harder_ganon)")
        if not isinstance(entry, Mapping):
            raise BetaConfigError(f'{key} ({choices.name}) must be an object, such as {{"{BETA_KEY}": ["Level 3"]}}')
        unknown = sorted(set(entry) - FLAG_KEYS)
        if unknown:
            raise BetaConfigError(f"{key} ({choices.name}) has unknown keys {unknown}; a flag's object may hold "
                                  f"{sorted(FLAG_KEYS)}")
        if BETA_KEY not in entry:
            continue
        values = _with_randoms(choices, _listed_beta(key, choices, entry[BETA_KEY]))
        if choices.default in values:
            raise BetaConfigError(f'{key} ({choices.name}): "{choices.labels[choices.default]}" is the value '
                                  "a fresh page starts with, so it cannot be beta")
        out[key] = values
    return out
