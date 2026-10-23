"""The music assets from the local music folder: the library from the clone of Quantam's
ZeldaMusicRandomizer at the pinned commit, and his newer lozft.bps beside it.

    from scripts.music_assets import pinned_assets, assets_available
    python3 scripts/music_assets.py          check the folder: the clone at the pinned commit, the patch, checksums

The folder is music/ (git-ignored; ZORA_MUSIC names another): music/ZeldaMusicRandomizer, the
clone, whose library is read from the pinned commit with `git show` (zora/rom/music/pin.py), never
its working tree, so other work in the clone cannot change a build, and music/lozft.bps, the patch
(Quantam's file of 2026-10-22, not yet in his repository). The bytes are then checked against the pin's checksums
(MusicAssets). docs/music.md says how to make the folder.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora.rom.music.pin import COMMIT, LIBRARY_PATH, PATCH_FILE, REPOSITORY, MusicAssets  # noqa: E402

DEFAULT_FOLDER = REPO / "music"
CLONE = "ZeldaMusicRandomizer"
CLONE_COMMAND = (f"git clone https://github.com/{REPOSITORY}.git music/ZeldaMusicRandomizer && "
                 f"git -C music/ZeldaMusicRandomizer checkout {COMMIT[:7]}")


class MusicAssetsMissing(RuntimeError):
    """No clone, the pinned commit not in it, or no patch."""


def music_folder() -> Path:
    return Path(os.environ.get("ZORA_MUSIC", DEFAULT_FOLDER))


def _pinned_file(clone: Path, path: str) -> bytes:
    result = subprocess.run(["git", "-C", str(clone), "show", f"{COMMIT}:{path}"], capture_output=True)
    if result.returncode != 0:
        raise MusicAssetsMissing(f"{clone} has no commit {COMMIT[:7]} with {path}: "
                                 f"fetch it (git -C {clone} fetch) or make the clone: {CLONE_COMMAND}")
    return result.stdout


def pinned_assets() -> MusicAssets:
    folder = music_folder()
    clone, patch = folder / CLONE, folder / PATCH_FILE
    if not (clone / ".git").exists():
        raise MusicAssetsMissing(f"no music clone at {clone}: {CLONE_COMMAND}")
    if not patch.is_file():
        raise MusicAssetsMissing(f"no {patch}: Quantam's lozft.bps of 2026-10-22 (docs/music.md)")
    return MusicAssets(_pinned_file(clone, LIBRARY_PATH), patch.read_bytes())


def assets_available() -> bool:
    try:
        pinned_assets()
    except MusicAssetsMissing:
        return False
    return True


if __name__ == "__main__":
    try:
        assets = pinned_assets()
    except MusicAssetsMissing as missing:
        print(missing, file=sys.stderr)
        sys.exit(1)
    print(f"music assets: the library at {COMMIT[:7]}, {len(assets.library)} bytes; the patch, {len(assets.patch)} bytes; "
          "checksums match")
