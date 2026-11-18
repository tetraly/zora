""""_" is an alias for "!" wherever ZORA reads a flag string (zora/flags/codec.py ALIASES): the page's file names
write "!" as "_" (docs/flags-api.md "Reading a file's name"), so flags copied from a file name paste as they are.
Both strings read it, in any mix with "!"; writing stays canonical, so ZORA shows, copies and stores "!" only. The
page's flag boxes show "!" as soon as "_" is typed or pasted (web/zora-web.js showAliasesAsDigits, in Node)."""
import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from zora.flags import codec, form, zora_flags
from zora.flags.presets import PRESETS, ZORA_PRESETS

REPO = Path(__file__).resolve().parent.parent
FROZEN = REPO / "tests" / "frozen_flag_strings"
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text(encoding="utf-8")
# A real file name from the page (the issue's example, tetraly/zora#18).
FILE_NAME = "zora-2.0.1-oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH-18.1DzpD8sDGgcF-3563927730.nes"


def string_pairs() -> list[tuple[str, str]]:
    pairs = []
    for path in sorted(FROZEN.glob("*.json")):
        pairs += [(entry["z1r"], entry["zora"]) for entry in json.loads(path.read_text())["strings"]]
    return pairs + [(string, "") for string in PRESETS.values()] + list(ZORA_PRESETS.values())


def z1r_values(text: str) -> tuple[object, ...]:
    settings = codec.decode(text)
    return (settings.options, settings.toggles)


def test_the_alias_reads_as_its_digit_in_both_strings() -> None:
    pairs = string_pairs()
    assert sum("!" in z1r for z1r, _ in pairs) > 20 and sum("!" in zora for _, zora in pairs) > 5
    for z1r, zora in pairs:
        assert z1r_values(z1r.replace("!", "_")) == z1r_values(z1r), z1r
        assert zora_flags.decode(zora.replace("!", "_")) == zora_flags.decode(zora), zora


def test_mixed_strings_read_the_same() -> None:
    """Some "!" written "_" and others kept, chosen at random per string."""
    rng = random.Random(703)
    pairs = [(z1r, zora) for z1r, zora in string_pairs() if "!" in z1r + zora]
    for z1r, zora in pairs:
        def mixed(text: str) -> str:
            return "".join("_" if character == "!" and rng.random() < 0.5 else character for character in text)
        assert z1r_values(mixed(z1r)) == z1r_values(z1r), z1r
        assert zora_flags.decode(mixed(zora)) == zora_flags.decode(zora), zora


def test_writing_stays_canonical() -> None:
    """Encoding, canonicalizing and the page's form state give "!" only, and the canonical string of an
    aliased one is the canonical string of the original."""
    for z1r, zora in string_pairs():
        aliased_z1r, aliased_zora = z1r.replace("!", "_"), zora.replace("!", "_")
        assert codec.canonicalize(aliased_z1r) == codec.canonicalize(z1r)
        assert "_" not in codec.canonicalize(aliased_z1r)
        assert zora_flags.canonicalize(aliased_zora) == zora_flags.canonicalize(zora)
        assert "_" not in zora_flags.canonicalize(aliased_zora)
    rng = random.Random(7031)
    for _ in range(300):
        number = rng.getrandbits(600)
        text = "".join(rng.choice(codec.ALPHABET + "_") for _ in range(rng.randint(1, 50)))
        assert "_" not in codec.encode(codec.decode(text)) and "_" not in codec._format_base63(number)
    assert "_" not in codec.ALPHABET and all(len(alias) == 1 for alias in codec.ALIASES)


def test_the_page_reads_flags_from_a_real_file_name() -> None:
    """Both flag parts of a page file name, pasted into the boxes: Python's form state (what the page shows
    and generates from) holds the strings with "!", and the same settings as the "!" strings."""
    _, _, z1r, zora, _ = FILE_NAME.removesuffix(".nes").split("-")
    assert "_" in z1r
    state = form.form_state(z1r, zora)
    canonical = form.form_state(z1r.replace("_", "!"), zora)
    assert state["ok"] and state["zora"]["ok"]
    assert state["flags"] == canonical["flags"] == "oIbnPfPb01Hll3D29Bc2!etrojQOSjJQZUULH"
    assert state["zora"]["flags"] == "18.1DzpD8sDGgcF"
    assert state["fields"] == canonical["fields"]
    assert form.metadata()["alphabetAliases"] == codec.ALIASES


def page_function(name: str) -> str:
    match = re.search(rf"^function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


BOX_IN_NODE = """
const metadata = { alphabetAliases: ALIASES };
const results = CASES.map(([value, cursor]) => {
  const input = { value, selectionStart: cursor, selectionEnd: cursor,
                  setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; } };
  showAliasesAsDigits(input);
  return [input.value, input.selectionStart, input.selectionEnd];
});
console.log(JSON.stringify(results));
"""


def test_the_flag_box_shows_a_pasted_alias_as_its_digit() -> None:
    """The box's own handler: a file name's flag part becomes the "!" string at once, the cursor where it was;
    a string without an alias is left alone."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    _, _, z1r, zora, _ = FILE_NAME.removesuffix(".nes").split("-")
    cases = [(z1r, len(z1r)), (z1r, 5), ("ab_c_!d", 3), (zora, len(zora)), ("oIbnPfPb01", 10), ("", 0)]
    source = page_function("showAliasesAsDigits") + BOX_IN_NODE.replace("ALIASES", json.dumps(
        form.metadata()["alphabetAliases"])).replace("CASES", json.dumps(cases))
    shown = json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)
    assert shown == [[z1r.replace("_", "!"), len(z1r), len(z1r)], [z1r.replace("_", "!"), 5, 5],
                     ["ab!c!!d", 3, 3], [zora, len(zora), len(zora)], ["oIbnPfPb01", 10, 10], ["", 0, 0]]
