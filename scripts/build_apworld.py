"""Build zora.apworld, ZORA's Archipelago world, from one commit (docs/archipelago.md).

    python3 scripts/build_apworld.py [--rev REV] [--uncommitted-world] [--out PATH]

The .apworld is a zip holding one folder, zora/, as Archipelago's "Build APWorlds" makes it:
- archipelago/'s files (the world: __init__.py, client.py, ..., test/) at the folder's top;
- ZORA's zora/ package inside it, as zora/zora/ (the world imports it as worlds.zora.zora);
- LICENSE;
- archipelago.json, the manifest: archipelago/archipelago.json with Archipelago's container
  version and compatible version (7) added.
Everything comes from REV's committed tree (default HEAD), as a release is built, so the world
and ZORA's generator in it are always from the same commit as the web page. --uncommitted-world
takes archipelago/ from the working tree instead (its tracked and new files), for trying the
world before committing it; zora/ and LICENSE still come from REV.

The zip is reproducible: entries in path order, each with a fixed date and mode, so the same
commit always builds the same bytes. Caches, hidden files and ROMs are left out, and the build
refuses any path under private/ (the private level-encoding module never ships).

It prints the file, its size and SHA-256, the world's version, ZORA's version and the zora/
copy's source hash (zora.archipelago.source_hash, which every recipe the world writes pins).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "temp" / "archipelago" / "zora.apworld"
WORLD_FOLDER = "zora"                   # the .apworld's name and its one folder: worlds.zora
WORLD_SOURCE = "archipelago"            # the world's own files in this repository
PACKAGE = "zora"                        # ZORA's generator, zora/zora/ in the .apworld
LICENSE = "LICENSE"
MANIFEST = "archipelago.json"
CONTAINER_VERSION = 7                   # Archipelago's APContainer version (worlds/Files.py)
ZIP_DATE = (1980, 1, 1, 0, 0, 0)        # the earliest a zip can hold: no build time in the file
FILE_MODE = 0o644
LEFT_OUT_NAMES = {"__pycache__", ".DS_Store", "__MACOSX"}
LEFT_OUT_SUFFIXES = (".pyc", ".pyo", ".nes")
REFUSED_PREFIXES = ("private/",)


class BuildRefused(RuntimeError):
    pass


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, check=True).stdout


def resolve(rev: str) -> str:
    try:
        return git("rev-parse", "--verify", f"{rev}^{{commit}}").decode().strip()
    except subprocess.CalledProcessError as unknown:
        raise BuildRefused(f"unknown revision {rev!r}") from unknown


def committed_files(commit: str, paths: list[str]) -> dict[str, bytes]:
    """REV's committed files under `paths`, by repository path."""
    archive = git("archive", "--format=tar", commit, *paths)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                extracted = tar.extractfile(member)
                assert extracted is not None
                files[member.name] = extracted.read()
    return files


def working_tree_files(folder: str) -> dict[str, bytes]:
    """The working tree's tracked and new (not ignored) files under `folder`."""
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", folder).decode().split("\0")
    return {name: (REPO / name).read_bytes() for name in listed if name and (REPO / name).is_file()}


def left_out(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return (any(part in LEFT_OUT_NAMES or part.startswith(".") for part in parts)
            or path.endswith(LEFT_OUT_SUFFIXES))


def apworld_path(path: str) -> str | None:
    """Where a repository file goes in the .apworld (None: not part of it)."""
    if path == f"{WORLD_SOURCE}/{MANIFEST}":
        return None                     # written as the manifest, with the container versions
    if path.startswith(f"{WORLD_SOURCE}/"):
        return f"{WORLD_FOLDER}/{path.removeprefix(f'{WORLD_SOURCE}/')}"
    if path.startswith(f"{PACKAGE}/"):
        return f"{WORLD_FOLDER}/{path}"
    if path == LICENSE:
        return f"{WORLD_FOLDER}/{LICENSE}"
    return None


def manifest(source: bytes) -> bytes:
    data = json.loads(source)
    for key in ("game", "world_version"):
        if key not in data:
            raise BuildRefused(f"{WORLD_SOURCE}/{MANIFEST} has no {key!r}")
    data |= {"version": CONTAINER_VERSION, "compatible_version": CONTAINER_VERSION}
    return (json.dumps(data, indent=2) + "\n").encode()


def contents(commit: str, uncommitted_world: bool) -> dict[str, bytes]:
    """The .apworld's files by their path in it."""
    files = committed_files(commit, [PACKAGE, LICENSE] if uncommitted_world else [WORLD_SOURCE, PACKAGE, LICENSE])
    if uncommitted_world:
        files |= working_tree_files(WORLD_SOURCE)
    refused = sorted(path for path in files if path.startswith(REFUSED_PREFIXES))
    if refused:
        raise BuildRefused(f"refusing files that never ship: {', '.join(refused)}")
    if f"{WORLD_SOURCE}/{MANIFEST}" not in files:
        raise BuildRefused(f"no {WORLD_SOURCE}/{MANIFEST} at {commit[:7]}: the world is not in this commit")
    out = {f"{WORLD_FOLDER}/{MANIFEST}": manifest(files[f"{WORLD_SOURCE}/{MANIFEST}"])}
    for path, data in files.items():
        target = apworld_path(path)
        if target is not None and not left_out(path):
            out[target] = data
    return out


def write_zip(files: dict[str, bytes], out: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, ZIP_DATE)
            info.external_attr = FILE_MODE << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, files[path], compresslevel=9)
    data = buffer.getvalue()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return data


def source_hash(files: dict[str, bytes], scratch: Path) -> str:
    """zora.archipelago.source_hash of the zora/ copy in the .apworld, computed by that copy (in
    an isolated interpreter, so this checkout's zora/ is never imported instead)."""
    package_root = scratch / "source-hash"
    prefix = f"{WORLD_FOLDER}/{PACKAGE}/"
    for path, data in files.items():
        if path.startswith(prefix):
            target = package_root / path.removeprefix(f"{WORLD_FOLDER}/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    code = (f"import sys; sys.path.insert(0, {str(package_root)!r}); "
            "from zora.archipelago import source_hash; from zora.version import ZORA_VERSION; "
            "print(source_hash()); print(ZORA_VERSION)")
    done = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True, check=True)
    return done.stdout.strip()


def build(rev: str = "HEAD", uncommitted_world: bool = False, out: Path = DEFAULT_OUT) -> dict[str, str]:
    """Build the .apworld; return what main prints."""
    import shutil
    import tempfile

    commit = resolve(rev)
    files = contents(commit, uncommitted_world)
    data = write_zip(files, out)
    (REPO / "temp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=REPO / "temp", prefix="build-apworld-") as scratch:
        hash_line, zora_version = source_hash(files, Path(scratch)).splitlines()
        shutil.rmtree(scratch, ignore_errors=True)
    world_manifest = json.loads(files[f"{WORLD_FOLDER}/{MANIFEST}"])
    return {
        "file": str(out.relative_to(REPO) if out.is_relative_to(REPO) else out),
        "from": commit[:7] + (" (archipelago/ from the working tree)" if uncommitted_world else ""),
        "files": str(len(files)),
        "bytes": f"{len(data):,}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "world version": world_manifest["world_version"],
        "ZORA version": zora_version,
        "source hash": hash_line,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rev", default="HEAD", help="the commit to build from (default HEAD)")
    parser.add_argument("--uncommitted-world", action="store_true",
                        help="take archipelago/ from the working tree (zora/ and LICENSE still from REV)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"default {DEFAULT_OUT.relative_to(REPO)}")
    args = parser.parse_args()
    try:
        built = build(args.rev, args.uncommitted_world, args.out.resolve())
    except BuildRefused as refused:
        print(f"build_apworld: refused: {refused}", file=sys.stderr)
        return 1
    for key, value in built.items():
        print(f"build_apworld: {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
