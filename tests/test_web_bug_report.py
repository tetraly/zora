"""The web page's copy buttons (web/zora-web.js): "Copy bug report info" (bugReportText; owner's
triage, 2026-10-17), one block with the version, the seed, both flag strings, the ROM (PRG0 or PRG1,
and modified graphics if so, from zora_web.api.identify_rom) and the seed code as its item names;
"Copy seed code" (seedCodeText; owner, 2026-10-17), the item names alone, for a race room; and "Copy
race info" (raceInfoText; owner, 2026-10-22), a short block for a race channel."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH
from zora.rom.revision import GRAPHICS_BLOCKS, NES_HEADER_SIZE
from zora_web import api

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
FLAGS = api.flag_form.metadata()["defaultFlags"]
CODE = ["Magical Key", "Wooden Arrow", "Heart Container", "Power Bracelet"]


def page_constant(name: str) -> str:
    match = re.search(rf"^const {name} = .*;$", PAGE_SCRIPT, re.MULTILINE)
    assert match, name
    return match.group(0)


def page_function(name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)




RACE_CONSTANTS = [page_constant(name) for name in ("RACE_ROM_ON", "RACE_ROM_OFF")]


def run_page(call: str) -> str:
    """CALL's result, with the page's two text functions defined, run in Node."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    functions = "\n".join([*RACE_CONSTANTS, *(page_function(name) for name in ("seedCodeText", "bugReportText",
                                                                                  "raceInfoText"))])
    source = f"{functions}\nprocess.stdout.write({call});"
    return subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout


def bug_report(info: dict[str, Any]) -> str:
    return run_page(f"bugReportText({json.dumps(info)})")


def graphics_inverted(rom: bytes) -> bytes:
    image = bytearray(rom)
    for _name, offset, length in GRAPHICS_BLOCKS:
        start = NES_HEADER_SIZE + offset
        image[start:start + length] = bytes(value ^ 0xFF for value in image[start:start + length])
    return bytes(image)


def identity(rom: bytes) -> dict[str, Any]:
    """The page's romIdentity: the worker passes identify_rom's answer through unchanged."""
    return api.identify_rom(rom)


@pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")
def test_prg0_with_both_flag_strings_and_the_seed_code() -> None:
    info = {"version": "2.0 beta 6", "seed": "2535214729", "flags": FLAGS, "zoraFlags": "AB",
            "identity": identity(BASE_ROM_PATH.read_bytes()), "code": CODE}
    assert bug_report(info) == ("ZORA 2.0 beta 6\nSeed: 2535214729\n"
                                f"Z1R flags: {FLAGS}\nZORA flags: AB\nROM: PRG0\n"
                                "Seed code: Magical Key, Wooden Arrow, Heart Container, Power Bracelet")


@pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="PRG1 ROM not found")
def test_prg1_with_modified_graphics_no_zora_flags_no_code() -> None:
    info = {"version": "v2.0.0b6", "seed": "7", "flags": FLAGS, "zoraFlags": "",
            "identity": identity(graphics_inverted(PRG1_ROM_PATH.read_bytes())), "code": []}
    assert bug_report(info).splitlines()[3:] == ["ZORA flags: (none)", "ROM: PRG1, modified graphics",
                                                 "Seed code: (none)"]


def test_the_seed_code_alone() -> None:
    """No "Seed code:" label: the four item names, as a race room takes them."""
    assert run_page(f"seedCodeText({json.dumps(CODE)})") == "Magical Key, Wooden Arrow, Heart Container, Power Bracelet"


def test_the_buttons_follow_each_generated_seed() -> None:
    """onGenerate adds them with what the result shows: the seed, the flags as asked for, the ROM
    chosen and the seed code; Copy seed code only when the seed has a code."""
    on_generate = page_function("onGenerate")
    assert "addCopyButtons({ version: $(\"version\").textContent, seed: result.seed, flags: requested.flags," \
           in on_generate
    assert "zoraFlags: requested.zoraFlags, identity: romIdentity, code," in on_generate
    assert "encoded: requested.encoded, notices: requested.notices });" in on_generate
    buttons = page_function("addCopyButtons")
    assert '"Copy bug report info", bugReportText(info)' in buttons
    assert '"Copy race info", raceInfoText(info)' in buttons
    assert 'if (info.code.length) {' in buttons and '"Copy seed code", seedCodeText(info.code)' in buttons


def race_info(**changes: Any) -> str:
    info = {"version": "2.0 beta 7", "seed": "2535214729", "flags": FLAGS, "zoraFlags": "", "code": CODE,
            "encoded": False, "notices": [], **changes}
    return run_page(f"raceInfoText({json.dumps(info)})")


def test_race_info_is_short_and_plain() -> None:
    assert race_info() == ("ZORA 2.0 beta 7\nSeed: 2535214729\n"
                           f"Flags: {FLAGS}\n"
                           "Seed code: Magical Key, Wooden Arrow, Heart Container, Power Bracelet\n"
                           "Race ROM: off (spoiler log available)")


def test_race_info_with_zora_flags_an_encoded_seed_and_a_notice() -> None:
    lines = race_info(zoraFlags="AB", encoded=True, code=[],
                      notices=["Mirrored overworld isn't supported yet; this seed is not mirrored"]).splitlines()
    assert lines[3:] == ["ZORA flags: AB", "Race ROM: on (level data encoded, no spoiler log)",
                         "Notice: Mirrored overworld isn't supported yet; this seed is not mirrored."]


def test_race_info_with_the_code_as_characters() -> None:
    """Under Item Sprites other than normal the page passes the four characters as the code."""
    assert "Seed code: 4K7Q" in race_info(code=["4K7Q"]).splitlines()
