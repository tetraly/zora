"""Flag strings stay backward compatible from beta 6 on (owner rule, 2026-10-18; AGENTS.md "Flag
strings"): a string keeps meaning the same settings in every later version, though its seeds may
change. tests/frozen_flag_strings/ holds, per release, that release's own decoding of every preset,
the tournament strings and a varied sample (random settings over every slot, raw strings that decode
by clamping, ZORA strings of every version), written by that release's code. Each must decode the same
today. A setting added since decodes to its default from an older string. At each release, add the
release's file: `python3 scripts/freeze_flag_strings.py COMMIT NAME` (beta6.json: f5a3859)."""
from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

from zora.flags import codec, zora_flags
from zora.flags.fields import OPTION_FIELDS, TOGGLE_FIELDS

FROZEN_FOLDER = Path(__file__).parent / "frozen_flag_strings"
FROZEN = [(path.stem, entry) for path in sorted(FROZEN_FOLDER.glob("*.json"))
          for entry in json.loads(path.read_text())["strings"]]


def z1r_meaning(flag_string: str) -> dict[str, int]:
    settings = codec.decode(flag_string)
    return {**{option.id: settings.option(option) for option in OPTION_FIELDS},
            **{toggle.id: int(settings.toggle(toggle)) for toggle in TOGGLE_FIELDS}}


def zora_meaning(flag_string: str) -> dict[str, bool | int | None]:
    def plain(value: object) -> bool | int | None:
        return value if value is None or isinstance(value, bool) else int(value)  # type: ignore[call-overload]
    flags = zora_flags.decode(flag_string)
    return {field.name: plain(getattr(flags, field.name)) for field in fields(zora_flags.ZoraFlags)}


def test_every_release_since_beta_6_is_frozen() -> None:
    """The presets and tournament strings are there, with the varied sample (82 strings frozen from
    f5a3859; the release re-freezes beta 6 from the commit that ships, with more)."""
    releases = {release for release, _entry in FROZEN}
    assert "beta6" in releases
    names = {entry["name"] for release, entry in FROZEN if release == "beta6"}
    assert {"preset MVP baseline", "preset All Swords No Boards", "preset Vanilla",
            "tournament TTP5: Pick 5", "tournament OHK0HPla Remastered"} <= names
    assert len(names) >= 82


@pytest.mark.parametrize(("release", "entry"), FROZEN, ids=[f"{release}: {entry['name']}" for release, entry in FROZEN])
def test_a_frozen_string_keeps_its_meaning(release: str, entry: dict) -> None:
    """Every field the release knew decodes as it did then, but one removed since (ignored, its place
    kept); any field added since is at its default."""
    z1r, zora = z1r_meaning(entry["z1r"]), zora_meaning(entry["zora"])
    z1r_default, zora_default = z1r_meaning("0"), zora_meaning("")
    assert {field: z1r[field] for field in entry["z1r_settings"]} == entry["z1r_settings"]
    # a setting removed since keeps its place in the string and is ignored (RETIRED_FIELDS)
    kept = {field: value for field, value in entry["zora_flags"].items() if field not in zora_flags.RETIRED_FIELDS}
    assert {field: zora[field] for field in kept} == kept
    assert {field: value for field, value in z1r.items() if field not in entry["z1r_settings"]} == {
        field: z1r_default[field] for field in z1r if field not in entry["z1r_settings"]}
    assert {field: value for field, value in zora.items() if field not in entry["zora_flags"]} == {
        field: zora_default[field] for field in zora if field not in entry["zora_flags"]}
