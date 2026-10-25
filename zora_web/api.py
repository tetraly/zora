"""The web page's stable interface to ZORA: generation (zora/) and the seed report
(zora_export/), in a package of its own so that zora/ stays generation only.

web/zora-worker.js runs Python glue inside Pyodide that needs exactly these
names: the flag form, the base ROM's expected hashes and identify_rom, generate_rom, the
seed code's icons, the page's player settings, the seed report (the seed document and spoiler
log) and multiworld mode's Archipelago YAML (zora_web.multiworld). Keep
them importable from here whenever modules move.
"""
import json

from zora.flags import form as flag_form
from zora.generate.pipeline import generate_rom
from zora.rom import item_sprites, revision
from zora.rom.base_rom import EXPECTED_CRC32, EXPECTED_MD5, EXPECTED_SHA1
from zora.rom.music.library import LibraryFile, MusicError, local_library_songs, read_library
from zora.rom.music.pin import ASSET_URLS, MusicAssets, MusicAssetsInvalid
from zora.rom.music.playlist import AREA_KEYS, ORIGINAL, RANDOM, parse_playlist
from zora.rom.music.randomize import options_for, randomize_music
from zora.rom.player_settings import (
    PAGE_BOSS_SOUND_WORD,
    PAGE_CHOICES,
    PAGE_HEART_SLOT,
    PAGE_LEVEL_WORD,
    PAGE_TUNIC_SLOTS,
    PlayerSettingError,
    PlayerSettings,
    player_settings_from_page,
)
from zora.rom.revision import finished_in_prg0_layout
from zora.rom.seed_code_icons import seed_code_icons
from zora_export.seed_document import EncodedSeedRefused, seed_document_for
from zora_export.spoiler_log import spoiler_file_name, spoiler_log
from zora_web import multiworld

# The page's player-settings names live in zora/ (Archipelago's recipe uses them too); they are
# re-exported here under the names web/zora-worker.js and the scripts use.
__all__ = [
    "EXPECTED_CRC32",
    "EXPECTED_MD5",
    "EXPECTED_SHA1",
    "PAGE_BOSS_SOUND_WORD",
    "PAGE_CHOICES",
    "PAGE_HEART_SLOT",
    "PAGE_LEVEL_WORD",
    "PAGE_TUNIC_SLOTS",
    "EncodedSeedRefused",
    "MusicAssetsInvalid",
    "MusicError",
    "PlayerSettingError",
    "PlayerSettings",
    "code_icons",
    "code_text",
    "flag_form",
    "generate_rom",
    "identify_rom",
    "multiworld",
    "music_asset_urls",
    "music_library_songs",
    "music_playlist_areas",
    "music_rom",
    "player_settings_from_page",
    "seed_report",
]


def identify_rom(data: bytes) -> dict[str, object]:
    """The page's check of the ROM the player loads (zora.rom.revision.identify_rom, the one
    check generation, the scripts and Archipelago use): {"recognized": True, "revision": "PRG0"
    or "PRG1", "modifiedGraphics": bool, "message": ...}, or {"recognized": False, "message":
    "ROM not recognized. ..."}. generate_rom takes any recognized ROM."""
    try:
        identity = revision.identify_rom(data)
    except revision.RomNotRecognized as refused:
        return {"recognized": False, "message": str(refused)}
    return {"recognized": True, "revision": identity.revision.value,
            "modifiedGraphics": identity.modified_graphics, "message": identity.message}


def code_icons(rom: bytes) -> list[list[list[int]]]:
    """A finished ROM's seed code as its file-select screen draws it (zora.rom.seed_code_icons): four
    icons in screen order, each 16 rows of 16 NES palette values, for the page to paint; none when
    the screen shows the code as text (code_text)."""
    if code_text(rom) is not None:
        return []
    return [[list(row) for row in icon.pixels] for icon in seed_code_icons(rom)]


def code_text(rom: bytes) -> str | None:
    """The four characters the file-select screen shows instead of icons under Item Sprites other
    than normal (C15; FP-SPRITE-01), or None."""
    return item_sprites.code_text(finished_in_prg0_layout(rom))


def seed_report(rom: bytes, flag_string: str, seed: int, zora_flag_string: str = "") -> dict[str, str]:
    """For a finished ROM made from these strings and seed: the seed document as JSON text (the
    "View in Visualizer" hand-off), the spoiler log and its file name. Reads the ROM only, after
    it is made; EncodedSeedRefused for a seed with level encoding on."""
    document = seed_document_for(rom, flag_string, seed, zora_flag_string)
    return {"json": json.dumps(document), "spoiler": spoiler_log(document),
            "spoilerName": spoiler_file_name(document)}


def music_asset_urls() -> dict[str, list[str]]:
    """Where the page fetches the music assets, each in the order to try (zora.rom.music.pin: Quantam's
    repository at the pinned commit, through a CDN, then GitHub's raw files)."""
    return {name: list(urls) for name, urls in ASSET_URLS.items()}


def music_rom(rom: bytes, base: bytes, seed: int, library: bytes, patch: bytes,
              settings: PlayerSettings | None = None, local_libraries: list[tuple[str, bytes]] | None = None,
              playlist: str | None = None) -> dict[str, object]:
    """A finished ROM (made with a random Music value, from the player's ROM `base`) with lozft and the
    seed's songs, as the player settings choose them (docs/design/music-settings.md): {"rom", "tracks"
    ([area, title] pairs), "warnings", "libraries" ([name, id] of each local file)}. local_libraries:
    the player's library files as (name, bytes); playlist: a playlist file's text. MusicError (a
    library, playlist or size problem) or MusicAssetsInvalid when it cannot be made, LozftUnavailable
    for a ROM lozft cannot go on. The seed report reads the ROM from before this step: the music
    changes nothing it reads."""
    files = [LibraryFile(name, data) for name, data in local_libraries or ()]
    options = options_for(settings or PlayerSettings(), parse_playlist(playlist) if playlist else None)
    result = randomize_music(rom, base, MusicAssets(library, patch), seed, options, files)
    return {"rom": result.rom, "tracks": [list(pair) for pair in result.track_list()],
            "warnings": list(result.warnings), "libraries": [list(pair) for pair in result.libraries]}


def music_library_songs(library: bytes | None = None,
                        local_libraries: list[tuple[str, bytes]] | None = None) -> dict[str, object]:
    """The songs the playlist editor offers: from the standard library's bytes, or from the player's
    library files. {"songs": [{"title", "uses", "safe"}], "warnings"}, or {"error": message}."""
    try:
        if local_libraries is not None:
            songs, warnings = local_library_songs([LibraryFile(name, data) for name, data in local_libraries])
        else:
            songs, warnings = read_library(library or b"", safe_only=False)
    except MusicError as exc:
        return {"error": str(exc)}
    return {"songs": [{"title": song.title, "uses": sorted(song.uses), "safe": song.streaming_safe}
                      for song in songs],
            "warnings": warnings}


def music_playlist_areas() -> dict[str, object]:
    """The playlist's areas for the editor: [{"key", "label", "uses"}] (the uses a song tagged for
    the area has, zora.rom.music.importer.area_uses), and its two words."""
    from zora.rom.music.importer import area_uses
    return {"areas": [{"key": key, "label": area.label, "uses": list(area_uses(area.area))}
                      for key, area in AREA_KEYS.items()],
            "original": ORIGINAL, "random": RANDOM}

