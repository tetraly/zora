"""The music asset from the local music folder: the library from the clone of Quantam's
ZeldaMusicRandomizer at the pinned commit.

    from scripts.music_assets import pinned_assets, assets_available
    python3 scripts/music_assets.py          check the folder: the clone at the pinned commit, its checksum

The folder is music/ (git-ignored; ZORA_MUSIC names another): music/ZeldaMusicRandomizer, the clone, whose
library is read from the pinned commit with `git show` (zora/rom/music/pin.py), never its working tree, so other
work in the clone cannot change a build. The bytes are then checked against the pin's checksum (MusicAssets).
docs/music.md says how to make the folder.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora.rom.music.pin import COMMIT, LIBRARY_PATH, REPOSITORY, MusicAssets  # noqa: E402

DEFAULT_FOLDER = REPO / "music"
CLONE = "ZeldaMusicRandomizer"
CLONE_COMMAND = (f"git clone https://github.com/{REPOSITORY}.git music/ZeldaMusicRandomizer && "
                 f"git -C music/ZeldaMusicRandomizer checkout {COMMIT[:7]}")


class MusicAssetsMissing(RuntimeError):
    """No clone, or the pinned commit not in it."""


def music_folder() -> Path:
    return Path(os.environ.get("ZORA_MUSIC", DEFAULT_FOLDER))


def _pinned_file(clone: Path, path: str) -> bytes:
    result = subprocess.run(["git", "-C", str(clone), "show", f"{COMMIT}:{path}"], capture_output=True)
    if result.returncode != 0:
        raise MusicAssetsMissing(f"{clone} has no commit {COMMIT[:7]} with {path}: "
                                 f"fetch it (git -C {clone} fetch) or make the clone: {CLONE_COMMAND}")
    return result.stdout


def pinned_assets() -> MusicAssets:
    clone = music_folder() / CLONE
    if not (clone / ".git").exists():
        raise MusicAssetsMissing(f"no music clone at {clone}: {CLONE_COMMAND}")
    return MusicAssets(_pinned_file(clone, LIBRARY_PATH))


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
    print(f"music assets: the library at {COMMIT[:7]}, {len(assets.library)} bytes; "
          "checksums match")
