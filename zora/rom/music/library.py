"""The music library: Quantam's FtRandoLib library format, read as FtRandoLib reads it.

A library has `single` modules and `groups` of modules; a module is one FamiTracker module (the
Dn-FamiTracker BIN export, compressed) holding one or more songs. Each song's settings come from the
song's own entry, else its module's, else its group's, else the importer's defaults (SongBase's
constructor). Quirk (FtRandoLib): `uses` is never taken from a group, only from the song or its
module, else the defaults.
"""
import base64
import binascii
import hashlib
import json
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from . import json5

DEFLATE_PREFIX, HEX_PREFIX = "deflate:", "hex:"
RAW_DEFLATE = -15                    # zlib's wbits for a raw deflate stream (.NET's DeflateStream)

# The Zelda importer's uses (ZeldaMusicRandomizer's MusicImporter: Uses and DefaultUses).
OVERWORLD, DUNGEON, LAST_DUNGEON, ENDING = "Overworld", "Dungeon", "LastDungeon", "Ending"
TITLE = "Title"                      # ZORA's area for the title screen (not a library use)
USES = (OVERWORLD, DUNGEON, LAST_DUNGEON, ENDING)
DEFAULT_USES = frozenset({DUNGEON, LAST_DUNGEON})
DEFAULT_PRIMARY_SQUARE_CHANNEL = 0
DEFAULT_STREAMING_SAFE = True
DEFAULT_ENABLED = True


class MusicError(ValueError):
    """Randomized music cannot be made as asked: the message says why, for the player."""


class LibraryError(MusicError):
    """The library holds something the importer cannot use."""


@dataclass(frozen=True)
class LibraryFile:
    """One of the player's library files (docs/design/music-settings.md section 4): its name, for
    messages, and its bytes."""
    name: str
    data: bytes

    @property
    def library_id(self) -> str:
        """The first 8 characters of its SHA-256, which the track list names it by."""
        return hashlib.sha256(self.data).hexdigest()[:8]


@dataclass(eq=False)
class Module:
    """One FamiTracker module: its title, the address its data is built for, the data."""
    title: str
    address: int
    data: bytes


@dataclass(eq=False)
class Song:
    """One song: `number` is its index inside its module; a built-in song (the original game's,
    module None) has its song-table index there instead."""
    title: str
    number: int
    uses: frozenset[str]
    module: Module | None
    author: str | None = None
    enabled: bool = DEFAULT_ENABLED
    streaming_safe: bool = DEFAULT_STREAMING_SAFE
    primary_square_channel: int = DEFAULT_PRIMARY_SQUARE_CHANNEL
    tags: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_original(self) -> bool:
        return self.module is None


# The original game's songs as candidates (MusicImporter.BuiltinSongs; GetBuiltinSongs gives them
# primary square channel 1, the game's own).
ORIGINAL_SONGS = (
    Song("Legend of Zelda - Overworld", 0, frozenset({OVERWORLD}), None, "Koji Kondo", primary_square_channel=1),
    Song("Legend of Zelda - Ending", 4, frozenset({ENDING}), None, "Koji Kondo", primary_square_channel=1),
    Song("Legend of Zelda - Last Dungeon", 5, frozenset({LAST_DUNGEON}), None, "Koji Kondo", primary_square_channel=1),
    Song("Legend of Zelda - Dungeon", 6, frozenset({DUNGEON}), None, "Koji Kondo", primary_square_channel=1),
)


def module_data(text: str) -> bytes:
    """A module's `data` string: "deflate:" base64 of a raw deflate stream, "hex:", or base64."""
    if text.startswith(DEFLATE_PREFIX):
        return zlib.decompress(base64.b64decode(text[len(DEFLATE_PREFIX):]), RAW_DEFLATE)
    if text.startswith(HEX_PREFIX):
        return bytes.fromhex(text[len(HEX_PREFIX):])
    return base64.b64decode(text)


def _address(value: Any) -> int:
    """start_addr: a number or a hex string ("0x8000", "$8000" or "8000")."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    return int(value.removeprefix("0x").removeprefix("$"), 16)


def _first(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


# Zelda II's uses (Z2Randomizer's MusicImporter, Usage), so a Zelda II library loads as a local
# library (owner, 2026-10-22; docs/design/music-settings.md section 4): each as the Zelda area it is
# closest to. Overworld is the same in both. A song without uses keeps the defaults, which Zelda II's
# (Palace, GreatPalace) translate to too.
ZELDA_II_USES = {
    "town": OVERWORLD,
    "palace": DUNGEON, "cave": DUNGEON, "encounter": DUNGEON,
    "greatpalace": LAST_DUNGEON, "boss": LAST_DUNGEON, "lastboss": LAST_DUNGEON,
    "credits": ENDING,
}


def _uses(names: list[str]) -> frozenset[str]:
    """Use names as the importer spells them (FtRandoLib compares them ignoring case), a Zelda II
    use as its Zelda area (ZELDA_II_USES)."""
    canonical = {use.lower(): use for use in USES}
    return frozenset(canonical.get(name.lower(), ZELDA_II_USES.get(name.lower(), name)) for name in names)


def _merged_tags(*entries: dict[str, Any] | None) -> frozenset[str]:
    """Tags from the group, the module and the song in turn: "-tag" removes, "+tag" adds."""
    tags: set[str] = set()
    for entry in entries:
        for tag in (entry or {}).get("tags", ()):
            if tag.startswith("-"):
                tags.discard(tag[1:])
            else:
                tags.add(tag.removeprefix("+"))
    return frozenset(tags)


def _module_songs(group: dict[str, Any] | None, entry: dict[str, Any]) -> list[Song]:
    """FtRandoLib's LoadFtSongs for one module: one song per `songs` entry, or one song."""
    title = (f"{group['title']} - " if group else "") + entry["title"]
    try:
        module = Module(title, _address(entry.get("start_addr")), module_data(entry["data"]))
    except (binascii.Error, zlib.error, ValueError) as exc:
        raise LibraryError(f"{title}: its module data cannot be read ({exc})") from exc
    group_or_module = group or entry
    songs = []
    for info in entry.get("songs") or [None]:
        song_or_module = info or entry
        uses = song_or_module.get("uses") or entry.get("uses")
        songs.append(Song(
            title=title + (f" - {info['title']}" if info else ""),
            number=info["number"] if info else 0,
            uses=_uses(uses) if uses else DEFAULT_USES,
            module=module,
            author=_first(song_or_module.get("author"), entry.get("author"), group_or_module.get("author")),
            enabled=_first(song_or_module.get("enabled"), entry.get("enabled"), group_or_module.get("enabled"),
                           DEFAULT_ENABLED),
            streaming_safe=_first(song_or_module.get("streaming_safe"), entry.get("streaming_safe"),
                                  group_or_module.get("streaming_safe"), DEFAULT_STREAMING_SAFE),
            primary_square_channel=_first(song_or_module.get("primary_square_chan"),
                                          entry.get("primary_square_chan"),
                                          group_or_module.get("primary_square_chan"),
                                          DEFAULT_PRIMARY_SQUARE_CHANNEL),
            tags=_merged_tags(group, entry, info)))
    return songs


def library_songs(library: bytes, safe_only: bool = True) -> list[Song]:
    """Every enabled song of the library (and, with safe_only, only the streaming-safe ones), single
    modules first, then each group's (LoadLibrarySongs' order). A song for a use the Zelda importer
    does not have is refused, as FtRandoLib refuses it (InvalidUsageError)."""
    try:
        parsed = json5.loads(library.decode("utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise LibraryError(f"line {exc.lineno}: not JSON5 ({exc.msg})") from exc
    except UnicodeDecodeError as exc:
        raise LibraryError("not a text file") from exc
    if not isinstance(parsed, dict):
        raise LibraryError("not a library (no single modules or groups)")
    entries = [(None, entry) for entry in parsed.get("single", [])]
    entries += [(group, entry) for group in parsed.get("groups", []) for entry in group.get("items", [])]
    songs = []
    for group, entry in entries:
        try:
            module_songs = _module_songs(group, entry)
        except (KeyError, TypeError, AttributeError) as exc:
            where = (group or {}).get("title", "") if isinstance(group, dict) else ""
            raise LibraryError(f"a module{' of ' + where if where else ''} without a title or data ({exc})") from exc
        for song in module_songs:
            if not song.enabled or (safe_only and not song.streaming_safe):
                continue
            unknown = song.uses - set(USES)
            if unknown:
                raise LibraryError(f"{song.title}: no use {', '.join(sorted(unknown))} in The Legend of Zelda")
            songs.append(song)
    return songs


def local_library_songs(files: Sequence[LibraryFile]) -> tuple[list[Song], list[str]]:
    """Every enabled song of the player's library files, merged in the files' order (Z2R's rule),
    and the warnings: a song whose full title an earlier file already has is left out. A file the
    importer cannot use raises LibraryError naming it."""
    songs: list[Song] = []
    warnings: list[str] = []
    first_file: dict[str, str] = {}
    for file in files:
        try:
            file_songs = library_songs(file.data, safe_only=False)
        except LibraryError as exc:
            raise LibraryError(f"{file.name}: {exc}") from exc
        for song in file_songs:
            if song.title in first_file:
                warnings.append(f"{song.title}: in {first_file[song.title]} and {file.name}; the first is used")
                continue
            first_file[song.title] = file.name
            songs.append(song)
    return songs, warnings
