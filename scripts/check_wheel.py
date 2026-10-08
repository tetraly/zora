"""Check a built zora wheel against the package it was built from.

    python3 scripts/check_wheel.py WHEEL SOURCE_DIR

Every file the wheel carries under zora/ must exist under SOURCE_DIR/zora/
(the committed package web/build.sh exported): a module the package does not
have, such as a leftover from an old build/ folder, fails the check. The
dist-info metadata is not part of the package and is not checked.
"""
import sys
import zipfile
from pathlib import Path

PACKAGE = "zora/"


def stray_members(wheel: Path, source: Path) -> list[str]:
    """The wheel's files under zora/ that SOURCE has no file for."""
    with zipfile.ZipFile(wheel) as archive:
        members = [name for name in archive.namelist() if name.startswith(PACKAGE) and not name.endswith("/")]
    return sorted(name for name in members if not (source / name).is_file())


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    wheel, source = Path(argv[0]), Path(argv[1])
    stray = stray_members(wheel, source)
    if stray:
        print(f"check_wheel: {wheel.name} carries {len(stray)} file(s) absent from {source / PACKAGE}:",
              file=sys.stderr)
        for name in stray:
            print(f"  {name}", file=sys.stderr)
        return 1
    with zipfile.ZipFile(wheel) as archive:
        count = sum(1 for name in archive.namelist() if name.startswith(PACKAGE) and not name.endswith("/"))
    print(f"check_wheel: {wheel.name}: {count} package files, none absent from {source / PACKAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
