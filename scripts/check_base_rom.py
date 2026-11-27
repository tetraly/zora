"""The base ROM the tests and scripts/verify.sh need, checked before anything else runs (2026-11-26).

Without it, or with another file under its name, a contributor's quick check used to pass its static
checks and then end in a traceback. This says what is wrong, which ROM is needed and how to check it.

    python3 scripts/check_base_rom.py [--rom PATH]     exit 0 if it is the PRG0 base ROM, else 1
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora.rom.base_rom import (  # noqa: E402
    BASE_ROM_NAME, BASE_ROM_PATH, EXPECTED_CRC32, EXPECTED_MD5, EXPECTED_SHA1, base_rom_hashes,
)
from zora.rom.revision import Revision, recognized  # noqa: E402

NEEDED = "the original US release of The Legend of Zelda (PRG0, not Rev 1)"


def how_to_check(name: str) -> str:
    return (f"  It must be {NEEDED}, the whole file with its 16-byte iNES header:\n"
            f"    SHA-1 {EXPECTED_SHA1}\n"
            f"    MD5 {EXPECTED_MD5}, CRC32 {EXPECTED_CRC32:08X}\n"
            f"  Check it on macOS or Linux:  shasum \"{name}\"\n"
            f"  or in Windows PowerShell:    Get-FileHash -Algorithm SHA1 \"{name}\"")


def problem(path: Path) -> str | None:
    """What is wrong with PATH as the base ROM, or None when it is the PRG0 base ROM."""
    if not path.is_file():
        return (f"no base ROM: put {NEEDED}, named \"{BASE_ROM_NAME}\", in {path.parent}\n"
                f"{how_to_check(BASE_ROM_NAME)}")
    if base_rom_hashes(path) == (EXPECTED_MD5, EXPECTED_SHA1, EXPECTED_CRC32):
        return None
    found = recognized(path.read_bytes())
    if found is None:
        what = "is not The Legend of Zelda (USA) as released (another game, a hack, a randomized ROM or a bad dump)"
    elif found.revision is Revision.PRG1:
        what = "is the Rev 1 (PRG1) release: players may use it, but the tests need PRG0"
    elif found.modified_graphics:
        what = "is PRG0 with modified graphics: the tests need the unmodified ROM"
    else:
        what = "is PRG0, but its 16-byte iNES header is not the standard dump's: the tests compare the whole file"
    return f"\"{path.name}\" {what}.\n{how_to_check(path.name)}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rom", type=Path, default=BASE_ROM_PATH, help="the file to check (default: the base ROM)")
    found = problem(parser.parse_args().rom)
    if found is None:
        return 0
    print(f"verify: {found}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
