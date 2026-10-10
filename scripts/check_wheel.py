"""Check a built zora wheel against the packages it was built from.

    python3 scripts/check_wheel.py WHEEL SOURCE_DIR

Every file the wheel carries outside its dist-info must exist under SOURCE_DIR
(the committed packages web/build.sh exported): a module the packages do not
have, such as a leftover from an old build/ folder, fails the check. So does a
wheel without one of PACKAGES: the page needs the generator (zora/) and its
siblings (the seed report and the worker's front door). The dist-info metadata
is not part of the packages and is not checked.
"""
import sys
import zipfile
from pathlib import Path

# zora/ is generation only (what Archipelago ships); the siblings never ship there
# (docs/packaging.md "Packages").
PACKAGES = ("zora", "zora_export", "zora_measure", "zora_web")
DIST_INFO = ".dist-info/"


def package_members(wheel: Path) -> list[str]:
    """The wheel's files, its dist-info aside."""
    with zipfile.ZipFile(wheel) as archive:
        return [name for name in archive.namelist() if DIST_INFO not in name and not name.endswith("/")]


def stray_members(wheel: Path, source: Path) -> list[str]:
    """The wheel's files that SOURCE has no file for."""
    return sorted(name for name in package_members(wheel) if not (source / name).is_file())


def missing_packages(wheel: Path) -> list[str]:
    """PACKAGES the wheel does not carry (no __init__.py)."""
    members = set(package_members(wheel))
    return [package for package in PACKAGES if f"{package}/__init__.py" not in members]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    wheel, source = Path(argv[0]), Path(argv[1])
    stray = stray_members(wheel, source)
    if stray:
        print(f"check_wheel: {wheel.name} carries {len(stray)} file(s) absent from {source}:", file=sys.stderr)
        for name in stray:
            print(f"  {name}", file=sys.stderr)
        return 1
    missing = missing_packages(wheel)
    if missing:
        print(f"check_wheel: {wheel.name} lacks the package(s) {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"check_wheel: {wheel.name}: {len(package_members(wheel))} package files ({', '.join(PACKAGES)}), "
          f"none absent from {source}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
