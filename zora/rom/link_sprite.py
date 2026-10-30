"""Link sprite sets (features-behavior.md FP-LINK-01, FP-LINK-02): a player setting that redraws Link.

Link is drawn from 40 tiles in six groups of the game's sprite patterns (FP-LINK-01's table): the
common sprite tiles $00 to $1B, two pairs in the title story's patterns, and the common tiles $54
and $55, $58 to $5B, and $60 and $61. A sprite set is 640 bytes of tile data for those 40 tiles, in
that order, each tile in the console's 2-bit format (eight low-plane bytes, then eight high-plane
bytes), with a name, an author and a note on where the art comes from and the permission given.
Its 640 bytes are written over the six groups after generation (FP-SET-01), and nothing else
changes: generation never reads or writes these groups, so the file-select code, the item and
sprite appearance (C15) and z1rr-coop are unaffected. The areas hold the same bytes in PRG0 and
PRG1. The set is drawn with sprite palette 0: color 1 is the tunic (FP-SET-02), colors 2 and 3
are the palette's other two entries as the game sets them, and color 0 is transparent.

ZORA ships built-in sets (BUILT_IN_SETS_FOLDER, beside this module: Irenepunmaster's, given for ZORA,
2026-10-26), and the player may load a set of their own. A set holds only its author's own art, or
art given with permission (FP-LINK-02), and never a run of the original game's bytes (the release
scan reads each built-in set's tiles).

The file format (docs/link-sprite-sets.md): UTF-8 JSON, one object,

    {"format": "zora-link-sprite-set", "version": 1, "name": "...", "author": "...",
     "provenance": "...", "tiles": "<base64 of the 640 bytes>",
     "recommendedColors": {"tunics": [green, blue ring, red ring], "other": [color 2, color 3],
                           "colorOne": "clothing" or "art"},
     "fromGame": [[start, end], ...]}

recommendedColors is optional (an older file has none): the NES colors the art was drawn for, which
the ROM gets unless the player picks their own (player_settings.shown_link_colors). colorOne (optional,
"clothing" by default) says what color 1 draws: clothing keeps the player's tunic colors, art (a
body, scales or a visor) takes the set's three. fromGame (optional) lists byte ranges of the 640, end
excluded, that hold the original Link's bytes in the art: the file has zeros there, and the bytes
are read from the player's ROM at the same places when the set is written (link_art.sprite_set_tiles),
so a set that keeps Link's shield ships none of the game's bytes.

Any tile content is accepted; a file with another amount of tile data, or without a name or an
author, is refused with a message (SpriteSetError) and no ROM is made."""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

TILE_SIZE = 16                        # the console's 2-bit format: 8 low-plane bytes, 8 high-plane bytes
# FP-LINK-01's six groups, in a set's order: (file offset, tiles)
LINK_TILE_GROUPS: tuple[tuple[int, int], ...] = (
    (0x808F, 28),                     # common sprite patterns, tiles $00-$1B
    (0x4E44, 2),                      # the title story's sprite patterns
    (0x4EC4, 2),
    (0x85CF, 2),                      # common sprite patterns, tiles $54 and $55
    (0x860F, 4),                      # tiles $58-$5B
    (0x868F, 2),                      # tiles $60 and $61
)
SPRITE_SET_SIZE = TILE_SIZE * sum(tiles for _offset, tiles in LINK_TILE_GROUPS)     # 640
# A sprite is two 8x16 halves of two tiles each (top, bottom), so the 40 tiles are 20 halves. Their
# names, in the set's order: the game's tile numbers $00-$1B, the title-story pairs ($78 and $80 in
# play), $54, $58, $5A and $60 (scripts/link_sprite_sheet.py says which pose draws each).
HALF_SIZE = 2 * TILE_SIZE
LINK_HALVES = ("$00", "$02", "$04", "$06", "$08", "$0A", "$0C", "$0E", "$10", "$12", "$14", "$16", "$18",
               "$1A", "$78", "$80", "$54", "$58", "$5A", "$60")
assert HALF_SIZE * len(LINK_HALVES) == SPRITE_SET_SIZE
FILE_FORMAT = "zora-link-sprite-set"
FILE_VERSION = 1
FILE_EXTENSION = ".json"
BUILT_IN_SETS_FOLDER = "link_sprites"   # zora/rom/link_sprites/<id>.json, package data
# Sprite palette 0's colors 2 and 3 as the game sets them (every level's palette: $29, $27, $17): a
# set's colors 2 and 3 always show in these (the page's preview draws them)
LINK_FIXED_COLORS = (0x27, 0x17)


class SpriteSetError(ValueError):
    """A sprite set ZORA refuses: its message says why."""


PALETTE_SIZE = 64
# recommendedColors' colorOne: what a set's color 1 draws
COLOR_ONE, CLOTHING, ART = "colorOne", "clothing", "art"
BLACKER_THAN_BLACK = 0x0D             # never offered (player_settings.check_palette_value)


@dataclass(frozen=True)
class RecommendedColors:
    """The colors a set was drawn for: a tunic color per ring state, and Link's colors 2 and 3;
    color_one_is_art: color 1 draws part of the art, not clothing, so the set's tunic colors apply
    with its other colors."""
    tunics: tuple[int, int, int]
    other: tuple[int, int]
    color_one_is_art: bool = False

    def __post_init__(self) -> None:
        for color in (*self.tunics, *self.other):
            if not isinstance(color, int) or not 0 <= color < PALETTE_SIZE or color == BLACKER_THAN_BLACK:
                raise SpriteSetError(f"a Link sprite set's recommended color {color!r} is not an NES palette "
                                     "value ($00-$3F, not $0D)")


@dataclass(frozen=True)
class SpriteSet:
    """FP-LINK-02's set: a name and an author (both non-empty), a free-text provenance note,
    exactly 640 bytes of tile data in LINK_TILE_GROUPS' order, optionally the colors it was
    drawn for, and the byte ranges taken from the player's ROM (from_game: zeros in tiles)."""
    name: str
    author: str
    provenance: str
    tiles: bytes
    recommended: RecommendedColors | None = None
    from_game: tuple[tuple[int, int], ...] = ()

    def __post_init__(self) -> None:
        for field, value in (("name", self.name), ("author", self.author)):
            if not isinstance(value, str) or not value.strip():
                raise SpriteSetError(f"a Link sprite set needs a {field}")
        if not isinstance(self.provenance, str):
            raise SpriteSetError("a Link sprite set's provenance note is text")
        if not isinstance(self.tiles, bytes) or len(self.tiles) != SPRITE_SET_SIZE:
            size = len(self.tiles) if isinstance(self.tiles, bytes) else "no"
            raise SpriteSetError(f"a Link sprite set holds exactly {SPRITE_SET_SIZE} bytes of tile data, "
                                 f"not {size}")
        previous_end = 0
        for start, end in self.from_game:
            if not (isinstance(start, int) and isinstance(end, int) and previous_end <= start < end <= SPRITE_SET_SIZE):
                raise SpriteSetError(f'a Link sprite set\'s "fromGame" ranges lie in order inside its '
                                     f"{SPRITE_SET_SIZE} bytes, apart: not [{start}, {end}]")
            if any(self.tiles[start:end]):
                raise SpriteSetError(f'a Link sprite set holds zeros where "fromGame" takes the game\'s bytes '
                                     f"({start} to {end})")
            previous_end = end


def sprite_set_from_object(data: Any) -> SpriteSet:
    """A set from its file's JSON object (or the page's copy of it: the same keys)."""
    if not isinstance(data, dict):
        raise SpriteSetError("a Link sprite set file holds one JSON object")
    if data.get("format") != FILE_FORMAT:
        raise SpriteSetError(f'not a Link sprite set file (its "format" is not "{FILE_FORMAT}")')
    if data.get("version") != FILE_VERSION:
        raise SpriteSetError(f"a Link sprite set file of version {data.get('version')!r}: this ZORA reads "
                             f"version {FILE_VERSION}")
    tiles = data.get("tiles")
    if not isinstance(tiles, str):
        raise SpriteSetError('a Link sprite set file needs its tile data ("tiles", base64)')
    try:
        tile_bytes = base64.b64decode(tiles, validate=True)
    except binascii.Error as exc:
        raise SpriteSetError("a Link sprite set's tile data is not base64") from exc
    return SpriteSet(data.get("name", ""), data.get("author", ""), data.get("provenance", ""), tile_bytes,
                     recommended_colors(data.get("recommendedColors")), _ranges(data.get("fromGame", [])))


def _ranges(data: Any) -> tuple[tuple[int, int], ...]:
    if not (isinstance(data, list) and all(isinstance(pair, list) and len(pair) == 2 for pair in data)):
        raise SpriteSetError('a Link sprite set\'s "fromGame" is a list of [start, end] pairs')
    return tuple((pair[0], pair[1]) for pair in data)


def recommended_colors(data: Any) -> RecommendedColors | None:
    """A file's recommendedColors object, or None when it has none."""
    if data is None:
        return None
    tunics, other = (data.get(key) if isinstance(data, dict) else None for key in ("tunics", "other"))
    if not (isinstance(tunics, list) and len(tunics) == 3 and isinstance(other, list) and len(other) == 2):
        raise SpriteSetError('a Link sprite set\'s "recommendedColors" holds "tunics" (three colors) and '
                             '"other" (two)')
    color_one = data.get(COLOR_ONE, CLOTHING)
    if color_one not in (CLOTHING, ART):
        raise SpriteSetError(f'a Link sprite set\'s color 1 ("{COLOR_ONE}") is "{CLOTHING}" or "{ART}", '
                             f"not {color_one}")
    return RecommendedColors((tunics[0], tunics[1], tunics[2]), (other[0], other[1]), color_one == ART)


def recommended_colors_object(recommended: RecommendedColors) -> dict[str, Any]:
    """recommendedColors as a file holds it (colorOne only when it is art)."""
    data: dict[str, Any] = {"tunics": list(recommended.tunics), "other": list(recommended.other)}
    if recommended.color_one_is_art:
        data[COLOR_ONE] = ART
    return data


def sprite_set_from_file(text: str | bytes) -> SpriteSet:
    """A set from its file's contents."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SpriteSetError("a Link sprite set file is JSON; this one does not read as JSON") from exc
    return sprite_set_from_object(data)


def sprite_set_object(sprite_set: SpriteSet) -> dict[str, Any]:
    """A set as its file's JSON object."""
    data: dict[str, Any] = {"format": FILE_FORMAT, "version": FILE_VERSION, "name": sprite_set.name,
                            "author": sprite_set.author, "provenance": sprite_set.provenance,
                            "tiles": base64.b64encode(sprite_set.tiles).decode("ascii")}
    if sprite_set.recommended is not None:
        data["recommendedColors"] = recommended_colors_object(sprite_set.recommended)
    if sprite_set.from_game:
        data["fromGame"] = [list(pair) for pair in sprite_set.from_game]
    return data


def sprite_set_file(sprite_set: SpriteSet) -> str:
    """A set's file contents."""
    return json.dumps(sprite_set_object(sprite_set), indent=2) + "\n"


def link_tiles(rom: bytes | bytearray) -> bytes:
    """The 640 bytes a ROM draws Link from, in a set's order."""
    return b"".join(bytes(rom[offset:offset + tiles * TILE_SIZE]) for offset, tiles in LINK_TILE_GROUPS)


def write_link_tiles(rom: bytearray, tiles: bytes) -> None:
    """A set's 640 bytes over the six groups."""
    assert len(tiles) == SPRITE_SET_SIZE
    start = 0
    for offset, count in LINK_TILE_GROUPS:
        length = count * TILE_SIZE
        rom[offset:offset + length] = tiles[start:start + length]
        start += length


def link_tile_offsets() -> set[int]:
    """Every file offset a set writes."""
    return {offset + i for offset, tiles in LINK_TILE_GROUPS for i in range(tiles * TILE_SIZE)}


@cache
def built_in_sprite_sets() -> dict[str, SpriteSet]:
    """ZORA's own sets by id (each file's name without .json), in id order: the order Random draws
    from (player_settings.LINK_SPRITE_STREAM), so a new set changes Random's draws."""
    # This package by its own name: copied in under another one (Archipelago's worlds.zora.zora,
    # perhaps from a zip), "zora.rom" would not be importable.
    folder = files(__package__).joinpath(BUILT_IN_SETS_FOLDER)
    found = sorted((entry.name.removesuffix(FILE_EXTENSION), entry) for entry in folder.iterdir()
                   if entry.name.endswith(FILE_EXTENSION))
    return {set_id: sprite_set_from_file(entry.read_text(encoding="utf-8")) for set_id, entry in found}
