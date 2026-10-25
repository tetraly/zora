"""A playlist: songs pinned to areas on top of the random draw (docs/design/music-settings.md section 5).

A JSON5 file:

    { version: 1, tracks: { title: "Radia Senki - 18 Elfas Castle", level1: "original", ... } }

Each key is an area (AREA_KEYS); each value is a song's full title from the chosen library,
`original` (the game's own song for that area) or `random`; an area left out is drawn at random.
"""
import json
from dataclasses import dataclass, field

from . import json5
from .importer import area_uses
from .library import DUNGEON, ENDING, LAST_DUNGEON, OVERWORLD, TITLE, MusicError, Song

PLAYLIST_VERSION = 1
ORIGINAL, RANDOM = "original", "random"
LEVELS = 8


class PlaylistError(MusicError):
    """A playlist that cannot be used: the message names the problem."""


@dataclass(frozen=True)
class Area:
    """One playlist key: its area (the importer's), its lozft song number, and the song number of
    the game's own song for it."""
    area: str
    song_number: int
    original_number: int
    label: str


# The areas, in the page's order: lozft's song numbers (importer.AREA_SONGS) and the original songs'.
AREA_KEYS: dict[str, Area] = {
    "title": Area(TITLE, 7, 7, "Title screen"),
    "overworld": Area(OVERWORLD, 0, 0, "Overworld"),
    **{f"level{level}": Area(DUNGEON, number, 6, f"Level {level}")
       for level, number in zip(range(1, LEVELS + 1), (6, 11, 12, 13, 14, 15, 16, 17), strict=True)},
    "level9": Area(LAST_DUNGEON, 5, 5, "Level 9"),
    "ending": Area(ENDING, 4, 4, "Ending and credits"),
}
ORIGINAL_TITLES = {TITLE: "Legend of Zelda - Title", OVERWORLD: "Legend of Zelda - Overworld",
                   DUNGEON: "Legend of Zelda - Dungeon", LAST_DUNGEON: "Legend of Zelda - Last Dungeon",
                   ENDING: "Legend of Zelda - Ending"}


@dataclass(frozen=True)
class Playlist:
    """The tracks it names, by area key: a title or ORIGINAL (RANDOM entries are left out)."""
    tracks: dict[str, str] = field(default_factory=dict)


def parse_playlist(text: str) -> Playlist:
    """A playlist file's text as a Playlist; PlaylistError for anything it cannot use."""
    try:
        parsed = json5.loads(text)
    except json.JSONDecodeError as exc:
        raise PlaylistError(f"the playlist, line {exc.lineno}: not JSON5 ({exc.msg})") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("tracks", {}), dict):
        raise PlaylistError("the playlist: not a playlist (expected { version: 1, tracks: { ... } })")
    if parsed.get("version", PLAYLIST_VERSION) != PLAYLIST_VERSION:
        raise PlaylistError(f"the playlist: version {parsed.get('version')!r}; this ZORA reads version "
                            f"{PLAYLIST_VERSION}")
    tracks: dict[str, str] = {}
    for key, value in parsed.get("tracks", {}).items():
        if key not in AREA_KEYS:
            raise PlaylistError(f"the playlist: no area {key!r} (the areas: {', '.join(AREA_KEYS)})")
        if not isinstance(value, str) or not value.strip():
            raise PlaylistError(f"the playlist, {key}: a song's title, {ORIGINAL!r} or {RANDOM!r}")
        if value.strip() != RANDOM:
            tracks[key] = value.strip()
    return Playlist(tracks)


def original_song(area: Area) -> Song:
    """The game's own song for an area, as a song the importer places (no module: its table entry)."""
    return Song(ORIGINAL_TITLES[area.area], area.original_number, frozenset({area.area}), None, "Koji Kondo",
                primary_square_channel=1)


def resolve_playlist(playlist: Playlist, songs: list[Song], safe_only: bool) -> tuple[dict[int, Song], list[str]]:
    """The playlist's songs by lozft song number, from `songs` (the chosen library, unsafe songs
    included), and its warnings. A title the library lacks is refused, and with safe_only a song
    marked unsafe for streaming; a song not tagged for its area is only warned about."""
    by_title = {song.title: song for song in reversed(songs)}
    fixed: dict[int, Song] = {}
    warnings: list[str] = []
    for key, track in playlist.tracks.items():
        area = AREA_KEYS[key]
        if track == ORIGINAL:
            fixed[area.song_number] = original_song(area)
            continue
        song = by_title.get(track)
        if song is None:
            raise PlaylistError(f"the playlist, {key}: no song {track!r} in the chosen library")
        if safe_only and not song.streaming_safe:
            raise PlaylistError(f"the playlist, {key}: {track!r} is marked unsafe for streaming "
                                "(turn Streaming-safe tracks only off to use it)")
        if not song.uses & set(area_uses(area.area)):
            warnings.append(f"{area.label}: {track} is not tagged for this area")
        fixed[area.song_number] = song
    return fixed, warnings
