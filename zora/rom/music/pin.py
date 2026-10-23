"""The pinned music assets: Quantam's standard library at one commit of his ZeldaMusicRandomizer,
and his lozft patch.

Neither is in ZORA's source repositories. The library: the page fetches it from a CDN mirror of
that commit (ASSET_URLS, with GitHub's raw files as the fallback); scripts and tests read it from a
local clone (music/ZeldaMusicRandomizer, git-ignored; `git show COMMIT:PATH`). The patch is a newer
lozft than the commit's, Quantam's build of 2026-10-22 as he sent it, whose driver keeps its
variables in the stack page ($0150-$01B9) and SRAM $7F40-$7FFD, leaving $7F00-$7F3F to the
statistics screen. It holds the driver and its glue, no songs and no bytes of the original game
(those it takes from the player's ROM: zora/rom/music/lozft.py). Until Quantam publishes it, ZORA
hosts it beside the test page (gh-pages' test/music/, PATCH_URLS; jsDelivr's mirror of that commit
as the fallback); scripts and tests read it from music/lozft.bps (git-ignored). Either way the bytes
must match the SHA-256 below, so a changed or damaged file is refused and the same seed always gets
the same songs. Moving the pin is a deliberate change: new checksums.
"""
import hashlib
from dataclasses import dataclass

REPOSITORY = "TheRealQuantam/ZeldaMusicRandomizer"
COMMIT = "ed924c4ccd8313b499d3615e94774abb0be51b08"

LIBRARY_PATH = "ZeldaMusicRandomizer/Assets/StandardLibrary.json5"
PATCH_FILE = "lozft.bps"                 # in the music folder, beside the clone (scripts/music_assets.py)
LIBRARY_SHA256 = "ce8bf751d2e7b2f4c6c56070a4aa25dca9d43c802e2c5a578675ae62bdf3714c"
PATCH_SHA256 = "5db55a699e978200d6db98bbad079e85e23d4004ed2887e875c48049bd247e09"
# lozft's own bytes as the patch makes them from either release (zora/rom/music/lozft.py lozft_bytes;
# the same on PRG0 and PRG1), so a ROM that gives others (modified graphics where the patch takes
# zeros from blank tiles) is refused.
LOZFT_BYTES_SHA256 = "f5be6ca45f4b0fda368a08b5bd8cc7dff4268e2104b8f38ad3e370b713205149"

CDN = f"https://cdn.jsdelivr.net/gh/{REPOSITORY}@{COMMIT}"
RAW = f"https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}"
PATCH_HOSTED = "test/music/lozft-5db55a69.bps"                    # in the public repo's gh-pages
PATCH_HOSTED_COMMIT = "528869a16810989c61a90dfe429838bff30e3bf6"   # the gh-pages commit that added it
PATCH_URLS = (f"https://zora.gg/{PATCH_HOSTED}",
              f"https://cdn.jsdelivr.net/gh/tetraly/zora@{PATCH_HOSTED_COMMIT}/{PATCH_HOSTED}")
# Each asset's URLs, in the order the page tries them.
ASSET_URLS = {
    "library": (f"{CDN}/{LIBRARY_PATH}", f"{RAW}/{LIBRARY_PATH}"),
    "patch": PATCH_URLS,
}


class MusicAssetsInvalid(ValueError):
    """An asset does not match the pinned checksum."""


@dataclass(frozen=True)
class MusicAssets:
    """The standard library (JSON5 text as bytes) and lozft.bps, checked against the pin."""
    library: bytes
    patch: bytes

    def __post_init__(self) -> None:
        for name, data, expected in (("library", self.library, LIBRARY_SHA256),
                                     ("patch", self.patch, PATCH_SHA256)):
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                raise MusicAssetsInvalid(f"the music {name} is not the pinned one "
                                         f"(SHA-256 {actual[:12]}..., expected {expected[:12]}...)")
