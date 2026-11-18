"""The public flags spec (docs/flags-api.md): docs/flags-api/zora-flags.json is what scripts/flags_api.py
generates from zora/flags/, it matches its JSON Schema, and a decoder that reads only the spec decodes a
corpus of real flag strings exactly as zora/flags/ does (the frozen strings of every release since beta 6,
every preset, random samples and malformed strings). That decoder is what a tool following
docs/flags-api.md writes, so it passing proves the spec is enough to decode correctly.

Releases ship the spec from 2.0.1 (release/allowlist.txt), so the tests run in the release tree too.
"""
from __future__ import annotations

import importlib.util
import json
import random
import re
import shutil
import subprocess
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SPEC_FILE = REPO / "docs" / "flags-api" / "zora-flags.json"
SCHEMA_FILE = REPO / "docs" / "flags-api" / "zora-flags.schema.json"
GENERATOR = REPO / "scripts" / "flags_api.py"
FROZEN = REPO / "tests" / "frozen_flag_strings"
PAGE_SCRIPT = REPO / "web" / "zora-web.js"

pytestmark = pytest.mark.skipif(not (SPEC_FILE.exists() and GENERATOR.exists()),
                                reason="the flags spec is not part of this tree")

from zora.flags import codec, zora_flags  # noqa: E402
from zora.flags.fields import OPTION_FIELDS, TOGGLE_FIELDS  # noqa: E402
from zora.flags.presets import PRESETS, ZORA_PRESETS  # noqa: E402

SAMPLE_SEED = 20261112
RANDOM_SAMPLES = 400


def _generator() -> Any:
    spec = importlib.util.spec_from_file_location("flags_api", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("flags_api", module)
    spec.loader.exec_module(module)
    return module


def _spec() -> dict[str, Any]:
    spec: dict[str, Any] = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    return spec


# ---------------------------------------------------------------------------
# A decoder that reads only the spec (what docs/flags-api.md tells a tool to write)
# ---------------------------------------------------------------------------

class SpecError(ValueError):
    """A string the spec says to refuse."""


def _number(spec: dict[str, Any], text: str) -> int:
    alphabet = spec["alphabet"]
    aliases = spec["alphabet_aliases"]
    number = 0
    for character in text:
        digit = alphabet.find(aliases.get(character, character))
        if digit < 0:
            raise SpecError(f"invalid character {character!r}")
        number = number * len(alphabet) + digit
    return number


def spec_decode_z1r(spec: dict[str, Any], text: str) -> dict[str, int]:
    if not text:
        raise SpecError("empty")
    number = _number(spec, text)
    values = {}
    for field in sorted(spec["z1r"]["fields"], key=lambda field: field["position"]):
        number, digit = divmod(number, field["radix"])
        values[field["key"]] = min(digit, len(field["values"]) - 1)
    return values


def spec_decode_zora(spec: dict[str, Any], text: str) -> dict[str, int]:
    """Every field's digit, retired ones included (a tool ignores those)."""
    import re
    section = spec["zora"]
    ordered = sorted(section["fields"], key=lambda field: field["position"])
    if text == "":
        return {field["key"]: field["default"] for field in ordered}
    match = re.fullmatch(section["pattern"], text)
    if match is None:
        raise SpecError("not a ZORA flag string")
    version = int(match.group(1))
    if version > section["current_version"]:
        raise SpecError("newer version")
    number = _number(spec, match.group(2))
    values = {}
    for field in ordered:
        if field["added_in_version"] <= version:
            number, values[field["key"]] = divmod(number, field["radix"])
        else:
            values[field["key"]] = field["default"]
    if number:
        raise SpecError("digits beyond the version's fields")
    return values


def zora_digits(text: str) -> dict[str, int]:
    """ZORA's own reading of a ZORA string, as each field's digit (retired fields left out)."""
    flags = zora_flags.decode(text)
    return {field.name: zora_flags._index_of(flags, field) for field in zora_flags.FIELDS
            if field.name not in zora_flags.RETIRED_FIELDS}


def z1r_digits(text: str) -> dict[str, int]:
    settings = codec.decode(text)
    return {**{field.id: settings.option(field) for field in OPTION_FIELDS},
            **{field.id: int(settings.toggle(field)) for field in TOGGLE_FIELDS}}


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------

def frozen_strings() -> list[tuple[str, str]]:
    pairs = []
    for path in sorted(FROZEN.glob("*.json")):
        pairs += [(entry["z1r"], entry["zora"]) for entry in json.loads(path.read_text())["strings"]]
    return pairs


def preset_strings() -> list[tuple[str, str]]:
    return [(string, "") for string in PRESETS.values()] + list(ZORA_PRESETS.values())


def random_z1r_strings(rng: random.Random) -> list[str]:
    """Random settings, canonical, and raw numbers (clamped digits, a part after the last field)."""
    alphabet = codec.ALPHABET
    raw = ["".join(rng.choice(alphabet) for _ in range(rng.randint(1, 50))) for _ in range(RANDOM_SAMPLES)]
    return raw + [codec.encode(codec.decode(text)) for text in raw]


def random_zora_strings(rng: random.Random) -> list[str]:
    """A string of every version with random digits in every field it holds."""
    out = []
    for _ in range(RANDOM_SAMPLES):
        version = rng.randint(1, zora_flags.CURRENT_VERSION)
        number, place = 0, 1
        for field in zora_flags.FIELDS:
            if field.version <= version:
                number += rng.randrange(field.slots) * place
                place *= field.slots
        payload = "".join(reversed(_base63_digits(number)))
        out.append(f"{version}.{payload or '0'}")
    return out


def _base63_digits(number: int) -> list[str]:
    digits = []
    while number:
        number, digit = divmod(number, codec.RADIX)
        digits.append(codec.ALPHABET[digit])
    return digits


MALFORMED_ZORA = ("0.1", "01.1", "1.", ".1", "1.1.1", "1.?", f"{zora_flags.CURRENT_VERSION + 1}.1",
                  "1.zzzzzzzz", "abc", "22", " 1.1")
MALFORMED_Z1R = ("", "abc?", "a b", "1.2")


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------

def test_the_spec_and_schema_are_what_zora_flags_gives() -> None:
    """Both files are current, apart from the spec's zora_version, which the release stamps
    (docs/flags-api.md): a version bump alone does not need the spec regenerated."""
    generator = _generator()
    built = json.loads(generator.render(generator.build()))
    committed = _spec()
    assert {**committed, "zora_version": None} == {**built, "zora_version": None}, \
        "run python3 scripts/flags_api.py"
    assert json.loads(SCHEMA_FILE.read_text(encoding="utf-8")) == json.loads(generator.render(generator.schema()))


def test_the_spec_matches_its_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_spec(), schema)


def test_the_spec_decodes_every_z1r_string_as_zora_does() -> None:
    spec = _spec()
    strings = [z1r for z1r, _ in frozen_strings() + preset_strings()] + random_z1r_strings(random.Random(SAMPLE_SEED))
    assert len(strings) > 1000
    for text in strings:
        assert spec_decode_z1r(spec, text) == z1r_digits(text), text


def test_the_spec_decodes_every_zora_string_as_zora_does() -> None:
    spec = _spec()
    retired = {field["key"] for field in spec["zora"]["fields"] if field.get("retired")}
    assert retired == zora_flags.RETIRED_FIELDS
    strings = ([zora for _, zora in frozen_strings() + preset_strings()]
               + random_zora_strings(random.Random(SAMPLE_SEED)))
    assert len({text.split(".")[0] for text in strings}) > zora_flags.CURRENT_VERSION   # every version and ""
    for text in strings:
        decoded = spec_decode_zora(spec, text)
        assert {key: digit for key, digit in decoded.items() if key not in retired} == zora_digits(text), text


def test_the_spec_refuses_what_zora_refuses() -> None:
    spec = _spec()
    for text in MALFORMED_ZORA:
        with pytest.raises(zora_flags.ZoraFlagStringError):
            zora_flags.decode(text)
        with pytest.raises(SpecError):
            spec_decode_zora(spec, text)
    for text in MALFORMED_Z1R:
        with pytest.raises(codec.FlagStringError):
            codec.decode(text)
        with pytest.raises(SpecError):
            spec_decode_z1r(spec, text)


def test_every_zora_field_and_default_is_in_the_spec() -> None:
    """The spec's defaults are the decoded empty string's, and every ZoraFlags attribute has its field."""
    spec = _spec()
    by_key = {field["key"]: field for field in spec["zora"]["fields"]}
    assert {field.name for field in fields(zora_flags.ZoraFlags)} <= set(by_key)
    assert spec_decode_zora(spec, "") == {key: field["default"] for key, field in by_key.items()}
    assert {key: digit for key, digit in spec_decode_zora(spec, "").items()
            if key not in zora_flags.RETIRED_FIELDS} == zora_digits("")


def _matches(conditions: list[dict[str, list[int]]], values: dict[str, int]) -> bool:
    return any(all(values[key] in allowed for key, allowed in condition.items()) for condition in conditions)


def test_a_tracker_reads_a_pin_from_the_spec_alone() -> None:
    """The walkthrough of docs/flags-api.md: Armos Item = Book with Item Shuffle: Full pins the Book; with Item
    Shuffle: Random it is unknown; with Item Shuffle: None and the first-quest dungeons, nothing is pinned."""
    spec = _spec()
    pins = spec["tracker_hints"]["pins"]
    book = next(entry["value"] for entry in pins["values"] if entry.get("item") == "Book")
    base = codec.decode(PRESETS["MVP baseline"])
    for scope, expected in ((3, "applies"), (4, "unknown"), (0, "none")):
        z1r = spec_decode_z1r(spec, codec.encode(base.updated(options={"C11": book, "C06": scope, "C02": 0})))
        values = {**z1r, **spec_decode_zora(spec, "")}
        found = ("applies" if _matches(pins["applies_when"], values)
                 else "unknown" if _matches(pins["unknown_when"], values) else "none")
        assert found == expected, scope
        assert z1r["C11"] == book


# ---------------------------------------------------------------------------
# The page's file names, read with the spec alone (file_name)
# ---------------------------------------------------------------------------

def spec_read_file_name(spec: dict[str, Any], name: str) -> dict[str, str | None] | None:
    """What docs/flags-api.md tells a tool to do with a file's name: drop a browser's duplicate number, then
    match the seed-file pattern or the batch-zip one. Its flag parts are flag strings as they stand ("_" is
    the alphabet's alias for "!"). None: not the page's name (paste the flags instead)."""
    section = spec["file_name"]
    name = re.sub(section["tolerate"]["duplicate_suffix"]["pattern"], "", name)
    for pattern, groups in ((section["pattern"], section["groups"]),
                            (section["batch_zip"]["pattern"], section["batch_zip"]["groups"])):
        match = re.search(pattern, name)
        if match:
            return dict(zip(groups, match.groups(), strict=True))
    return None


FILE_NAME_FUNCTIONS = ("fileNameSafe", "fileNameVersion", "seedFileStem", "batchZipName", "romFileName",
                       "spoilerFileName", "trackerFileName")
FILE_NAME_CONSTANTS = ("FILE_NAME_STAND_INS", "FILE_NAME_UNSAFE")
# The page's version pill as each channel and build shows it, with the version part it gives a name.
PAGE_VERSIONS = (("v2.0.1", "regular", "2.0.1"), ("v2.0.1 (a1b2c3d)", "test", "2.0.1-a1b2c3d-test"),
                 ("v2.0.1", "test", "2.0.1-test"), ("v2.0 beta 1", "test", "2.0-beta-1-test"),
                 ("v2.0.1 2026-11-12 3a9845f modified", "regular", "2.0.1-2026-11-12-3a9845f-modified"))
# Each kind of file a seed gets (the zip is a batch's).
FILE_KINDS = ("rom", "spoiler", "tracker", "zip")
FILE_NAMES_IN_NODE = """
let shown = "", PAGE_CHANNEL = "regular";
const TEST_CHANNEL = "test";
const $ = () => ({ textContent: shown });
const [cases, patterns] = JSON.parse(require("fs").readFileSync(0, "utf8"));
const read = (name) => patterns.map((pattern) => (name.match(new RegExp(pattern, "u")) || []).slice(1));
console.log(JSON.stringify(cases.map(([seed, flags, zora, music, version, channel]) => {
  shown = version; PAGE_CHANNEL = channel;
  const fileStem = seedFileStem(seed, flags, zora, music);
  const names = [romFileName({ fileStem }), spoilerFileName({ fileStem }), trackerFileName({ fileStem }),
                 batchZipName(seed, String(BigInt(seed) + 9n), flags, zora, music)];
  return { names, javascript: names.map(read) };
})));
"""


def _page_part(pattern: str) -> str:
    match = re.search(pattern, PAGE_SCRIPT.read_text(encoding="utf-8"), re.MULTILINE | re.DOTALL)
    assert match, pattern
    return match.group(0)


def page_file_names(cases: list[tuple[str, str, str, bool, str, str]], patterns: list[str]) -> list[dict[str, Any]]:
    """Each case's four names from the page's own functions in Node, and what JavaScript's RegExp reads from
    each name with each pattern."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = "\n".join([*(_page_part(rf"^const {name} = [^\n]*") for name in FILE_NAME_CONSTANTS),
                        *(_page_part(rf"^function {name}\(.*?^}}\n") for name in FILE_NAME_FUNCTIONS),
                        FILE_NAMES_IN_NODE])
    result = subprocess.run([node, "-e", source], input=json.dumps([cases, patterns]), capture_output=True,
                            text=True, check=True)
    names: list[dict[str, Any]] = json.loads(result.stdout)
    return names


def test_every_page_file_name_reads_back_with_the_spec_alone() -> None:
    """Every frozen and preset pair of flag strings (as the page shows them), on every channel's version, with
    and without music, named as the page names a seed's ROM, spoiler log, tracker file and batch zip: the spec
    alone reads back the flag strings (each decoding, "_" and all, to exactly ZORA's settings for the string
    the page shows, and ZORA reading it the same), the version and the seed, and JavaScript's RegExp reads the
    same parts as Python's."""
    spec = _spec()
    section = spec["file_name"]
    pairs = sorted({(codec.encode(codec.decode(z1r)), zora_flags.encode(zora_flags.decode(zora)))
                    for z1r, zora in frozen_strings() + preset_strings()})
    assert any("!" in z1r for z1r, _ in pairs) and any(zora == "" for _, zora in pairs)
    assert any("!" in zora for _, zora in pairs)
    seeds = ("0", "7", "3563927730", str(2 ** 64 - 10))
    cases = [(seeds[index % len(seeds)], z1r, zora, index % 2 == 1, *PAGE_VERSIONS[index % len(PAGE_VERSIONS)][:2])
             for index, (z1r, zora) in enumerate(pairs)]
    patterns = [section["pattern"], section["batch_zip"]["pattern"]]
    answers = page_file_names(cases, patterns)
    assert len(answers) == len(cases) > 100
    extensions = {kind: extension for extension, kind in section["extensions"].items()}
    for index, ((seed, z1r, zora, music, _, _), answer) in enumerate(zip(cases, answers, strict=True)):
        version = PAGE_VERSIONS[index % len(PAGE_VERSIONS)][2]
        music_part = section["music_ending"] if music else None
        for kind, name, javascript in zip(FILE_KINDS, answer["names"], answer["javascript"], strict=True):
            read = spec_read_file_name(spec, name)
            assert read is not None, name
            read_z1r, read_zora = str(read["z1r"]), str(read["zora"] or "")
            assert "!" not in read_z1r + read_zora, name
            assert spec_decode_z1r(spec, read_z1r) == z1r_digits(z1r) == z1r_digits(read_z1r), name
            assert spec_decode_zora(spec, read_zora) == spec_decode_zora(spec, zora), name
            assert zora_digits(read_zora) == zora_digits(zora), name
            assert (codec.canonicalize(read_z1r), zora_flags.canonicalize(read_zora)) == (z1r, zora), name
            expected: dict[str, str | None] = {"version": version, "z1r": z1r.replace("!", "_"),
                                               "zora": zora.replace("!", "_"), "music": music_part}
            if kind == "zip":
                expected |= {"first_seed": seed, "last_seed": str(int(seed) + 9)}
            else:
                expected |= {"seed": seed, "extension": extensions[{"rom": "rom", "spoiler": "spoiler_log",
                                                                    "tracker": "tracker_file"}[kind]]}
            assert read == expected, name
            assert [part or "" for part in javascript[kind == "zip"]] == [
                str(part or "") for part in match_groups(spec, name, kind == "zip")], name
            assert javascript[kind != "zip"] == [], name


def match_groups(spec: dict[str, Any], name: str, batch: bool) -> tuple[str | None, ...]:
    section = spec["file_name"]
    match = re.search(section["batch_zip"]["pattern"] if batch else section["pattern"], name)
    assert match, name
    return match.groups()


EXAMPLE_STEM = "zora-2.0.1-oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH-18.1DzpD8sDGgcF-3563927730"


@pytest.mark.parametrize("name", [
    f"{EXAMPLE_STEM} (1).nes", f"{EXAMPLE_STEM}(2).spoiler.txt", f"{EXAMPLE_STEM} (12).tracker.json",
    f"{EXAMPLE_STEM}-3563927739 (1).zip",
])
def test_a_browsers_duplicate_number_is_dropped(name: str) -> None:
    read = spec_read_file_name(_spec(), name)
    assert read is not None
    assert (read["z1r"], read["zora"]) == ("oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH", "18.1DzpD8sDGgcF")


@pytest.mark.parametrize("name", [
    "my seed.nes",                                              # renamed
    "Legend of Zelda, The (USA).nes",
    "zora-seed-123.nes", "zora-seed-123-encoded-music.nes",   # before 2.0.1
    "zora-seeds-1-9.zip",
    "AP_12345678901234567890_P1_Link.nes", "AP_12345678901234567890_P1_Link.apzora",   # Archipelago
    f"{EXAMPLE_STEM}.txt",                                      # not one of the page's files
    f"{EXAMPLE_STEM}-12.nes",                                   # a last seed outside a zip
    f"{EXAMPLE_STEM}.zip",                                      # a zip without its last seed
    "zora-2.0.1-oIbnPfPb01Hll3D29Bc2!etrojQOSjJQZUULH-18.1DzpD8sDGgcF-3563927730.nes",   # "!" kept: not the page's
    # a ZORA string without its version
    "zora-2.0.1-oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH-1DzpD8sDGgcF-3563927730.nes",
    "zora-2.0.1-oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH-18.1DzpD8sDGgcF-.nes",              # no seed
    "zora-2.0.1--18.1DzpD8sDGgcF-3563927730.nes",                                         # no Z1R string
    "zora-2.0.1-oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH-18.1DzpD8sDGgcF-35639x7730.nes",
    "ZORA-2.0.1-oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH-18.1DzpD8sDGgcF-3563927730.NES",
    "zora--oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH--3563927730.nes",                       # no version
    "",
])
def test_names_that_are_not_the_pages_are_refused(name: str) -> None:
    assert spec_read_file_name(_spec(), name) is None


def test_the_docs_show_the_specs_patterns() -> None:
    """docs/flags-api.md prints both file-name patterns; they must be the spec's."""
    section = _spec()["file_name"]
    docs = (REPO / "docs" / "flags-api.md").read_text(encoding="utf-8")
    assert section["pattern"] in docs and section["batch_zip"]["pattern"] in docs


def test_the_spec_decoder_reads_the_alias() -> None:
    """A tool following the spec reads "_" as "!" in both strings, as ZORA does, and the spec says so."""
    spec = _spec()
    assert spec["alphabet_aliases"] == codec.ALIASES == {"_": "!"}
    assert "_" not in spec["alphabet"]
    pairs = [pair for pair in frozen_strings() + preset_strings() if "!" in pair[0] + pair[1]]
    assert len(pairs) > 20
    for z1r, zora in pairs:
        assert spec_decode_z1r(spec, z1r.replace("!", "_")) == spec_decode_z1r(spec, z1r) == z1r_digits(z1r)
        assert spec_decode_zora(spec, zora.replace("!", "_")) == spec_decode_zora(spec, zora)
