"""The pinned music asset: Quantam's standard library at one commit of his ZeldaMusicRandomizer.

It is not in ZORA's source repositories. The page fetches it from a CDN mirror of that commit (ASSET_URLS, with
GitHub's raw files as the fallback); scripts and tests read it from a local clone
(music/ZeldaMusicRandomizer, git-ignored; `git show COMMIT:PATH`). Either way the bytes must match the SHA-256
below, so a changed or damaged file is refused and the same seed always gets the same songs. Moving the pin is
a deliberate change: a new checksum. lozft itself is in zora/rom/music/lozft_patch_data.py, built from source.
"""
import hashlib
from dataclasses import dataclass

REPOSITORY = "TheRealQuantam/ZeldaMusicRandomizer"
COMMIT = "ed924c4ccd8313b499d3615e94774abb0be51b08"

LIBRARY_PATH = "ZeldaMusicRandomizer/Assets/StandardLibrary.json5"
LIBRARY_SHA256 = "ce8bf751d2e7b2f4c6c56070a4aa25dca9d43c802e2c5a578675ae62bdf3714c"

CDN = f"https://cdn.jsdelivr.net/gh/{REPOSITORY}@{COMMIT}"
RAW = f"https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}"
# Each asset's URLs, in the order the page tries them.
ASSET_URLS = {
    "library": (f"{CDN}/{LIBRARY_PATH}", f"{RAW}/{LIBRARY_PATH}"),
}


class MusicAssetsInvalid(ValueError):
    """The library does not match the pinned checksum."""


@dataclass(frozen=True)
class MusicAssets:
    """The standard library (JSON5 text as bytes), checked against the pin."""
    library: bytes

    def __post_init__(self) -> None:
        actual = hashlib.sha256(self.library).hexdigest()
        if actual != LIBRARY_SHA256:
            raise MusicAssetsInvalid(f"the music library is not the pinned one "
                                     f"(SHA-256 {actual[:12]}..., expected {LIBRARY_SHA256[:12]}...)")
