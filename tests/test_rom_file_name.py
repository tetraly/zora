"""The page's file names (tetraly/zora#18; web/zora-web.js seedFileStem): zora-<version>-<flag string>-<ZORA flag
string>-<seed>, the ROM .nes, its spoiler log .spoiler.txt and tracker file .tracker.json. Every character either
flag string can hold is safe in a name or has its stand-in ("!" becomes "_"), the version is the page's (on the
test channel with its build's commit) with "-test" on the test channel, and the name reads back from the right.
Run in Node on the page's own functions;
tests/test_web_seed_batch.py checks a batch's zip and its files."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from zora.flags import codec, zora_flags
from zora.flags.fields import ThreeState

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
CONSTANTS = ("FILE_NAME_STAND_INS", "FILE_NAME_UNSAFE")
FUNCTIONS = ("fileNameSafe", "fileNameVersion", "seedFileStem", "romFileName", "spoilerFileName", "trackerFileName")
# What every system and upload keeps as it is: letters, digits, ".", "_" and "-"
SAFE = re.compile(r"^[0-9A-Za-z._-]+$")
ZORA_ALPHABET = codec.ALPHABET + "."              # a ZORA string adds its version's dot (zora_flags)
EXAMPLE_FLAGS = "oIbnPfPb01Hll3D29Bc2!etrojQOSjJQZUULH"
EXAMPLE_ZORA = "18.1DzpD8sDGgcF"
EXAMPLE_SEED = "3563927730"


def page_part(kind: str, name: str) -> str:
    pattern = (rf"^const {name} = [^\n]*" if kind == "const"
               else rf"^(?:async )?function {name}\(.*?^}}\n")
    match = re.search(pattern, PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def run(calls: dict[str, str], version: str = "v2.0.1", channel: str = "regular") -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = "\n".join([
        f'const PAGE_CHANNEL = {json.dumps(channel)}, TEST_CHANNEL = "test";',
        f"const $ = () => ({{ textContent: {json.dumps(version)} }});",
        *(page_part("const", name) for name in CONSTANTS), *(page_part("function", name) for name in FUNCTIONS),
        "console.log(JSON.stringify({" + ", ".join(f"{json.dumps(key)}: {call}" for key, call in calls.items())
        + "}));",
    ])
    return json.loads(subprocess.run([node], input=source, capture_output=True, text=True, check=True).stdout)


def stem(flags: str, zora: str, seed: str) -> str:
    return f"seedFileStem({json.dumps(seed)}, {json.dumps(flags)}, {json.dumps(zora)})"


def test_the_issues_example() -> None:
    names = run({"rom": f"romFileName({{ fileStem: {stem(EXAMPLE_FLAGS, EXAMPLE_ZORA, EXAMPLE_SEED)} }})",
                 "log": f"spoilerFileName({{ fileStem: {stem(EXAMPLE_FLAGS, EXAMPLE_ZORA, EXAMPLE_SEED)} }})",
                 "tracker": f"trackerFileName({{ fileStem: {stem(EXAMPLE_FLAGS, EXAMPLE_ZORA, EXAMPLE_SEED)} }})"})
    base = "zora-2.0.1-oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH-18.1DzpD8sDGgcF-3563927730"
    assert names == {"rom": f"{base}.nes", "log": f"{base}.spoiler.txt", "tracker": f"{base}.tracker.json"}


def test_every_flag_string_character_is_safe_or_stands_in() -> None:
    """Both alphabets, character by character: kept when safe, "!" alone swapped (for "_", in neither)."""
    swapped = run({character: f"fileNameSafe({json.dumps(character)})" for character in ZORA_ALPHABET})
    assert {character: name for character, name in swapped.items() if character != name} == {"!": "_"}
    assert all(SAFE.match(name) for name in swapped.values())
    assert "_" not in ZORA_ALPHABET and "-" not in ZORA_ALPHABET


def test_real_flag_strings_read_back_from_the_name() -> None:
    """A real Z1R string with "!", a real ZORA string, and the empty ZORA string (every ZORA flag at its default):
    the name is safe (each string's "!" a "_"), and seed, ZORA string and flag string read back from the right."""
    z1r = codec.encode(codec.decode(EXAMPLE_FLAGS))
    zora = zora_flags.encode(zora_flags.ZoraFlags(item_counter=ThreeState.ON, pegasus_boots=ThreeState.ON))
    assert "!" in z1r and "." in zora and zora_flags.encode(zora_flags.ZoraFlags()) == ""
    names = run({"both": stem(z1r, zora, "7"), "default": stem(z1r, "", "7")})
    for name, expected_zora in ((names["both"], zora), (names["default"], "")):
        assert SAFE.match(name), name
        rest, seed = name.rsplit("-", 1)
        rest, read_zora = rest.rsplit("-", 1)
        version, read_flags = rest.rsplit("-", 1)
        assert (version, read_flags.replace("_", "!"), read_zora.replace("_", "!"), seed) == (
            "zora-2.0.1", z1r, expected_zora, "7")


@pytest.mark.parametrize(("shown", "channel", "expected"), [
    ("v2.0.1", "regular", "2.0.1"),
    ("v2.0.1", "test", "2.0.1-test"),
    ("v2.0.1 (a1b2c3d)", "test", "2.0.1-a1b2c3d-test"),          # the test channel's version with its commit
    ("v2.0 beta 1", "test", "2.0-beta-1-test"),
    ("v2.0.1 beta 1", "test", "2.0.1-beta-1-test"),
    ("v2.0.1 beta 1", "regular", "2.0.1-beta-1"),
    ("v2.0.1 2026-11-12 3a9845f modified", "regular", "2.0.1-2026-11-12-3a9845f-modified"),
])
def test_the_version_is_the_pages_with_its_channel(shown: str, channel: str, expected: str) -> None:
    assert run({"version": "fileNameVersion()"}, version=shown, channel=channel)["version"] == expected


def test_music_ends_the_name() -> None:
    """Music: Random, a player setting in neither flag string: "-music" ends each file's stem, so a seed with and
    without music never shares a name; without it the name is unchanged (the "--" of an empty ZORA string kept)."""
    music = f"seedFileStem({json.dumps(EXAMPLE_SEED)}, {json.dumps(EXAMPLE_FLAGS)}, '', true)"
    plain = f"seedFileStem({json.dumps(EXAMPLE_SEED)}, {json.dumps(EXAMPLE_FLAGS)}, '', false)"
    names = run({"rom": f"romFileName({{ fileStem: {music} }})", "log": f"spoilerFileName({{ fileStem: {music} }})",
                 "tracker": f"trackerFileName({{ fileStem: {music} }})",
                 "plain": f"romFileName({{ fileStem: {plain} }})"})
    base = "zora-2.0.1-oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH--3563927730"
    assert names == {"rom": f"{base}-music.nes", "log": f"{base}-music.spoiler.txt",
                     "tracker": f"{base}-music.tracker.json", "plain": f"{base}.nes"}
