"""Randomized music on a finished ROM: the one entry point (docs/music.md,
docs/design/music-settings.md).

The ROM comes from generation with the player settings applied, a random Music value among them
(which writes the statistics screen's music choice). randomize_music adds lozft, places the
playlist's songs, and draws a song for each other area from the chosen library, on a stream of
its own from the seed, so the same seed, settings, libraries and playlist always give the same ROM.
"""
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from ...generate.rng import Rng
from .importer import AREA_SONGS, MUSIC_BANK_ROOM, Placed, RomFull, check_modules, draw_songs, modules_size, pack_songs
from .library import (
    LibraryError,
    LibraryFile,
    MusicError,
    Song,
    library_songs,
    local_library_songs,
)
from .lozft import with_lozft
from .pin import MusicAssets
from .playlist import AREA_KEYS, Playlist, resolve_playlist

if TYPE_CHECKING:
    from ..player_settings import PlayerSettings

MUSIC_STREAM = b"zora-music"
DRAWS = 8                    # Z2R's: a draw that does not fit is made again, up to this many times in all


class MusicSource(Enum):
    STANDARD = "standard"    # Quantam's standard library, pinned (zora.rom.music.pin)
    LOCAL = "local"          # the player's library files


@dataclass(frozen=True)
class MusicOptions:
    """source: the library the songs come from. Every area is drawn, the ending and credits too, unless
    the playlist pins it (a playlist's `original` puts the game's own song there). The title screen
    always gets an overworld track. distinct: every area gets its own track while the library has
    enough. safe_only: no track marked unsafe for streaming (Streaming-safe tracks only), the
    playlist's included. playlist: songs pinned to areas."""
    source: MusicSource = MusicSource.STANDARD
    distinct: bool = True
    safe_only: bool = True
    playlist: Playlist | None = None


@dataclass(frozen=True)
class MusicResult:
    rom: bytes
    placed: tuple[Placed, ...]
    warnings: tuple[str, ...] = ()
    libraries: tuple[tuple[str, str], ...] = ()     # (name, library_id) of each local library file

    def track_list(self) -> list[tuple[str, str]]:
        """(area, song title) per placed song, in the importer's order: "Level 3" for level 3."""
        names = {area.song_number: area.label for area in AREA_KEYS.values()}
        return [(names[place.song_number], place.song.title) for place in self.placed]


def music_rng(seed: int) -> Rng:
    """The music's own stream: the seed and a label, hashed (generation's streams are untouched)."""
    digest = hashlib.blake2b(MUSIC_STREAM + seed.to_bytes(8, "little"), digest_size=8).digest()
    return Rng(int.from_bytes(digest, "little"))


def options_for(settings: "PlayerSettings", playlist: Playlist | None = None) -> MusicOptions:
    """The options the player settings choose (Music's library, its switches) and the playlist."""
    from ..player_settings import Music
    return MusicOptions(source=MusicSource.LOCAL if settings.music is Music.RANDOM_LOCAL else MusicSource.STANDARD,
                        safe_only=settings.music_streaming_safe_only, playlist=playlist)


DEFAULT_OPTIONS = MusicOptions()


def _library(assets: MusicAssets, options: MusicOptions,
             local_libraries: Sequence[LibraryFile]) -> tuple[list[Song], list[str]]:
    """Every song of the chosen library, unsafe ones included, and its warnings."""
    if options.source is MusicSource.STANDARD:
        return library_songs(assets.library, safe_only=False), []
    if not local_libraries:
        raise MusicError("Random (local library) needs a library: choose your library files")
    songs, warnings = local_library_songs(local_libraries)
    for file in local_libraries:            # every module placed as a test (Z2R's TestSongs), by file
        try:
            check_modules(library_songs(file.data, safe_only=False))
        except LibraryError as exc:
            raise LibraryError(f"{file.name}: {exc}") from exc
    return songs, warnings


def randomize_music(rom: bytes, base: bytes, assets: MusicAssets, seed: int,
                    options: MusicOptions = DEFAULT_OPTIONS,
                    local_libraries: Sequence[LibraryFile] = ()) -> MusicResult:
    """rom: the finished ROM; base: the player's ROM it was made from (lozft is made from it).
    MusicError (LibraryError, PlaylistError, RomFull) when it cannot be made as asked."""
    library, warnings = _library(assets, options, local_libraries)
    pool = [song for song in library if song.streaming_safe or not options.safe_only]
    fixed: dict[int, Song] = {}
    if options.playlist is not None:
        fixed, playlist_warnings = resolve_playlist(options.playlist, library, options.safe_only)
        warnings += playlist_warnings
    areas = tuple(AREA_SONGS)
    drawn_numbers = {number for area in areas for number in AREA_SONGS[area]} - set(fixed)
    rng = music_rng(seed)
    for draw in range(DRAWS):
        placed = draw_songs(pool, rng, options.distinct, areas, fixed)
        out = with_lozft(rom, assets.patch, base)
        try:
            pack_songs(out, placed)
        except RomFull:
            if draw + 1 < DRAWS and drawn_numbers:
                continue
            raise RomFull(f"the songs need {modules_size(placed):,} bytes of modules; the music banks hold "
                          f"{MUSIC_BANK_ROOM:,}") from None
        libraries = tuple((file.name, file.library_id) for file in local_libraries) \
            if options.source is MusicSource.LOCAL else ()
        return MusicResult(bytes(out), tuple(placed), tuple(warnings), libraries)
    raise AssertionError("unreachable")
