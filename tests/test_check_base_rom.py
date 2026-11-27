"""scripts/check_base_rom.py, which verify.sh runs first (2026-11-26): a missing base ROM, or another file
under its name, stops the run at once with the ROM needed and how to check its hash, instead of a
traceback after the static checks."""
import subprocess
import sys
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, EXPECTED_SHA1, PRG1_ROM_PATH

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_base_rom.py"
HEADER_SIZE = 16

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="no PRG0 base ROM here")


def check(rom: Path) -> tuple[int, str]:
    done = subprocess.run([sys.executable, str(SCRIPT), "--rom", str(rom)], capture_output=True, text=True,
                          timeout=60)
    return done.returncode, done.stderr


def test_the_base_rom_passes_quietly() -> None:
    assert check(BASE_ROM_PATH) == (0, "")


def test_a_missing_rom_names_the_rom_needed_and_how_to_check_it(tmp_path: Path) -> None:
    status, message = check(tmp_path / "Legend of Zelda, The (USA).nes")
    assert status == 1 and "no base ROM: put the original US release of The Legend of Zelda (PRG0" in message
    assert EXPECTED_SHA1 in message and "shasum" in message and "Get-FileHash -Algorithm SHA1" in message


def test_another_file_says_what_it_is(tmp_path: Path) -> None:
    base = BASE_ROM_PATH.read_bytes()
    other_header = tmp_path / "header.nes"
    other_header.write_bytes(bytes([*base[:HEADER_SIZE - 1], base[HEADER_SIZE - 1] ^ 1]) + base[HEADER_SIZE:])
    status, message = check(other_header)
    assert status == 1 and "is PRG0, but its 16-byte iNES header is not the standard dump's" in message
    another = tmp_path / "another.nes"
    another.write_bytes(base[:HEADER_SIZE] + bytes(len(base) - HEADER_SIZE))
    status, message = check(another)
    assert status == 1 and "is not The Legend of Zelda (USA) as released" in message
    assert EXPECTED_SHA1 in message


@pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="no PRG1 ROM here")
def test_a_rev_1_rom_is_named_as_such() -> None:
    status, message = check(PRG1_ROM_PATH)
    assert status == 1 and "is the Rev 1 (PRG1) release: players may use it, but the tests need PRG0" in message
