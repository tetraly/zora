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

ZORA ships no sets yet (owner, 2026-10-24: until ZORA's own art is ready, the setting offers
PRG0's Link and a set the player loads). A set holds only its author's own art, or art given with
permission (FP-LINK-02).

The file format (docs/link-sprite-sets.md): UTF-8 JSON, one object,

    {"format": "zora-link-sprite-set", "version": 1, "name": "...", "author": "...",
     "provenance": "...", "tiles": "<base64 of the 640 bytes>"}

Any tile content is accepted; a file with another amount of tile data, or without a name or an
author, is refused with a message (SpriteSetError) and no ROM is made."""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
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
FILE_FORMAT = "zora-link-sprite-set"
FILE_VERSION = 1
FILE_EXTENSION = ".json"


class SpriteSetError(ValueError):
    """A sprite set ZORA refuses: its message says why."""


@dataclass(frozen=True)
class SpriteSet:
    """FP-LINK-02's set: a name and an author (both non-empty), a free-text provenance note, and
    exactly 640 bytes of tile data in LINK_TILE_GROUPS' order."""
    name: str
    author: str
    provenance: str
    tiles: bytes

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
    return SpriteSet(data.get("name", ""), data.get("author", ""), data.get("provenance", ""), tile_bytes)


def sprite_set_from_file(text: str | bytes) -> SpriteSet:
    """A set from its file's contents."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SpriteSetError("a Link sprite set file is JSON; this one does not read as JSON") from exc
    return sprite_set_from_object(data)


def sprite_set_object(sprite_set: SpriteSet) -> dict[str, Any]:
    """A set as its file's JSON object."""
    return {"format": FILE_FORMAT, "version": FILE_VERSION, "name": sprite_set.name, "author": sprite_set.author,
            "provenance": sprite_set.provenance, "tiles": base64.b64encode(sprite_set.tiles).decode("ascii")}


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
