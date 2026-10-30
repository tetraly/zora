"""Link sprite sets of the game's own art (built-in art): Link redrawn from the player's own tiles.

A built-in-art set is a kind of Link sprite set beside FP-LINK-02's 640-byte sets (link_sprite.py).
It holds no tile data. It is an arrangement: for each of Link's 20 halves (link_sprite.LINK_HALVES,
two 8x16 tiles each), which half of the game's sprite patterns draws it, whether mirrored, and what
the source's colors 1 to 3 become in Link's palette. The 640 bytes are assembled from the player's
ROM when the ROM is made (art_tiles, through base_rom.original_bytes), so a ROM with custom graphics
gives its own art, and ZORA ships only the arrangement, never a tile.

The arrangements are ZORA's own design, made from the game's art and the disassembly's object
animations (ObjAnimations, ObjAnimFrameHeap): a monster's walking frames are its side frames 0 and
1, its down frame 2 and its up frame 3, each a left half at tile T and a right half at T+2, drawn
facing right and flipped by the game for left (SetUpHorizontalWalkingSprites); a cave person is one
half, drawn mirrored (DrawCavePerson).

The file format (docs/link-sprite-sets.md "Built-in art"): UTF-8 JSON, one object,

    {"format": "zora-link-sprite-arrangement", "version": 1, "name": "...", "author": "...",
     "provenance": "...",
     "halves": {"$00": {"block": "PatternBlockOWSP", "tile": "$F0"},
                "$5A": {"block": "PatternBlockOWSP", "tile": "$FA", "mirror": true}, ...},
     "colors": [1, 2, 3], "recommendedColors": {...}}

A person set may add "swap": [{"block": ..., "tile": ..., "link": "$0A", "mirror": true}, ...], the
person's own halves redrawn as the original Link's (a half of LINK_HALVES, from the player's ROM,
mirrored and recolored as asked), written only when the player turns the swap on (swap_writes). A
swap redraws only the people's own halves (SWAP_TARGETS), so it never reaches a tile generation reads.

halves names all 20 of Link's halves; a block is one of ART_BLOCKS (the disassembly's labels), and a
tile is the half's top tile as the game numbers it while the block is loaded (an even number; the
half is that tile and the next). colors (optional, [1, 2, 3] by default) gives the Link color each
source color 1, 2 and 3 becomes (0 is transparent); color 0 stays transparent."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

from .base_rom import original_bytes
from .link_sprite import (
    FILE_EXTENSION,
    HALF_SIZE,
    LINK_HALVES,
    LINK_TILE_GROUPS,
    SPRITE_SET_SIZE,
    TILE_SIZE,
    RecommendedColors,
    SpriteSet,
    SpriteSetError,
    built_in_sprite_sets,
    recommended_colors,
    recommended_colors_object,
    sprite_set_from_object,
    sprite_set_object,
)

FILE_FORMAT = "zora-link-sprite-arrangement"
FILE_VERSION = 1
BUILT_IN_ART_FOLDER = "link_art"      # zora/rom/link_art/<id>.json, package data
COLORS = 4                            # a sprite tile's 2-bit colors; 0 is transparent
IDENTITY_COLORS = (1, 2, 3)


@dataclass(frozen=True)
class ArtBlock:
    """A block of the game's sprite patterns: its PRG0 file offset (with the header), the tile number
    its first tile has while loaded, and its tiles. PRG1 holds every block at the same offset."""
    offset: int
    first_tile: int
    tiles: int


# The disassembly's pattern blocks a set may draw from (src/bins.xml; Z_03.asm's PatternBlockPpuAddrs:
# the common sprites at PPU $0000, a level's sprites at $08E0, a dungeon group's at $09E0, its bosses'
# at $0C00).
ART_BLOCKS: dict[str, ArtBlock] = {
    "CommonSpritePatterns": ArtBlock(0x808F, 0x00, 112),
    "PatternBlockOWSP": ArtBlock(0xD16B, 0x8E, 114),
    "PatternBlockUWSP": ArtBlock(0xDCCB, 0x8E, 16),
    "PatternBlockUWSP127": ArtBlock(0xDDCB, 0x9E, 34),
    "PatternBlockUWSP358": ArtBlock(0xD88B, 0x9E, 34),
    "PatternBlockUWSP469": ArtBlock(0xDAAB, 0x9E, 34),
    "PatternBlockUWSPBoss1257": ArtBlock(0xDFEB, 0xC0, 64),
    "PatternBlockUWSPBoss3468": ArtBlock(0xE3EB, 0xC0, 64),
    "PatternBlockUWSPBoss9": ArtBlock(0xE7EB, 0xC0, 64),
}


@dataclass(frozen=True)
class ArtHalf:
    """One of Link's halves: the source half's block and top tile, and whether it is mirrored."""
    block: str
    tile: int
    mirror: bool = False

    def __post_init__(self) -> None:
        block = ART_BLOCKS.get(self.block)
        if block is None:
            raise SpriteSetError(f"a built-in-art set names an unknown block {self.block!r}")
        if not (isinstance(self.tile, int) and self.tile % 2 == 0
                and block.first_tile <= self.tile and self.tile + 1 < block.first_tile + block.tiles):
            raise SpriteSetError(f"tile {self.tile!r} is not the top tile of a half in {self.block} "
                                 f"(an even number from ${block.first_tile:02X} to "
                                 f"${block.first_tile + block.tiles - 2:02X})")

    @property
    def offset(self) -> int:
        """The source half's PRG0 file offset."""
        block = ART_BLOCKS[self.block]
        return block.offset + (self.tile - block.first_tile) * TILE_SIZE


# The halves a swap may redraw: each person's own (the cave people, drawn mirrored from one half in both
# sprite blocks, DrawCavePerson; Zelda's two frames in level 9's boss block), none of them read or
# written by generation (tests/test_link_art.py)
SWAP_TARGETS = frozenset({
    *((block, tile) for block in ("PatternBlockOWSP", "PatternBlockUWSP") for tile in (0x98, 0x9A, 0x9C)),
    ("PatternBlockUWSPBoss9", 0xF0), ("PatternBlockUWSPBoss9", 0xF6),
})


def swap_target_offsets() -> set[int]:
    """Every file offset a swap may write."""
    return {ArtHalf(block, tile).offset + i for block, tile in SWAP_TARGETS for i in range(HALF_SIZE)}


@dataclass(frozen=True)
class ArtSwap:
    """The swap of a person set: one of the person's own halves (block and top tile) redrawn as one of
    the original Link's halves (by its LINK_HALVES name), mirrored if asked and recolored for the
    person's palette, so the person looks like Link."""
    target: ArtHalf
    link_half: str
    mirror: bool = False
    colors: tuple[int, int, int] = IDENTITY_COLORS

    def __post_init__(self) -> None:
        if self.link_half not in LINK_HALVES:
            raise SpriteSetError(f"a built-in-art set's swap names Link's half {self.link_half!r}, not one of "
                                 f"{', '.join(LINK_HALVES)}")
        if (self.target.block, self.target.tile) not in SWAP_TARGETS:
            raise SpriteSetError(f"a built-in-art set's swap redraws a person's own half, not {self.target.block} "
                                 f"${self.target.tile:02X}")
        _check_colors(self.colors, "swap's ")


def _check_colors(colors: tuple[int, ...], whose: str = "") -> None:
    if len(colors) != len(IDENTITY_COLORS) or not all(isinstance(color, int) and 0 <= color < COLORS
                                                      for color in colors):
        raise SpriteSetError(f'a built-in-art set\'s {whose}"colors" are three of 0, 1, 2 and 3')


@dataclass(frozen=True)
class ArtSet:
    """A built-in-art set: a name and an author (both non-empty), a provenance note, a source for each
    of Link's 20 halves in LINK_HALVES' order, the Link color of each source color 1 to 3, and
    optionally the colors it suits."""
    name: str
    author: str
    provenance: str
    halves: tuple[ArtHalf, ...]
    colors: tuple[int, int, int] = IDENTITY_COLORS
    recommended: RecommendedColors | None = None
    # A person set's swap (the person drawn as Link), applied only when the player asks for it
    swaps: tuple[ArtSwap, ...] = ()

    def __post_init__(self) -> None:
        for field, value in (("name", self.name), ("author", self.author)):
            if not isinstance(value, str) or not value.strip():
                raise SpriteSetError(f"a Link sprite set needs a {field}")
        if not isinstance(self.provenance, str):
            raise SpriteSetError("a Link sprite set's provenance note is text")
        if len(self.halves) != len(LINK_HALVES):
            raise SpriteSetError(f"a built-in-art set names all {len(LINK_HALVES)} of Link's halves")
        _check_colors(self.colors)


def half_tiles(data: bytes, mirror: bool, colors: tuple[int, int, int]) -> bytes:
    """A half's two tiles (32 bytes, the console's 2-bit format) mirrored if asked and recolored:
    source color c (1-3) becomes colors[c - 1], and 0 stays transparent."""
    out = bytearray()
    for tile in (data[:TILE_SIZE], data[TILE_SIZE:HALF_SIZE]):
        low, high = bytearray(8), bytearray(8)
        for row in range(8):
            for column in range(8):
                bit = 7 - column
                color = (tile[row] >> bit & 1) | (tile[8 + row] >> bit & 1) << 1
                if color:
                    color = colors[color - 1]
                to = column if mirror else bit
                low[row] |= (color & 1) << to
                high[row] |= (color >> 1) << to
        out += low + high
    return bytes(out)


def art_tiles(art: ArtSet, read: Callable[[int, int], bytes] = original_bytes) -> bytes:
    """The set's 640 bytes, assembled from the player's ROM (read: PRG0 file offset and length to
    bytes; base_rom.original_bytes by default, the player's ROM in PRG0's layout)."""
    tiles = b"".join(half_tiles(read(half.offset, HALF_SIZE), half.mirror, art.colors) for half in art.halves)
    assert len(tiles) == SPRITE_SET_SIZE
    return tiles


def original_link_half(name: str, read: Callable[[int, int], bytes] = original_bytes) -> bytes:
    """One of the original Link's halves (by its LINK_HALVES name) from the player's ROM."""
    index = LINK_HALVES.index(name) * HALF_SIZE
    for offset, tiles in LINK_TILE_GROUPS:
        length = tiles * TILE_SIZE
        if index < length:
            return read(offset + index, HALF_SIZE)
        index -= length
    raise AssertionError(name)


def swap_writes(art: ArtSet, read: Callable[[int, int], bytes] = original_bytes) -> list[tuple[int, bytes]]:
    """The swap's writes (file offset, 32 bytes): each person half redrawn from the original Link's
    half in the player's ROM, whatever Link sprite the ROM gets."""
    return [(swap.target.offset, half_tiles(original_link_half(swap.link_half, read), swap.mirror, swap.colors))
            for swap in art.swaps]


def _tile_number(text: Any) -> int:
    if not (isinstance(text, str) and len(text) == 3 and text.startswith("$")):
        raise SpriteSetError(f'a built-in-art set\'s tile is written "$XX", not {text!r}')
    try:
        return int(text[1:], 16)
    except ValueError as exc:
        raise SpriteSetError(f'a built-in-art set\'s tile is written "$XX", not {text!r}') from exc


def art_set_from_object(data: Any) -> ArtSet:
    """A set from its file's JSON object (or the page's copy of it: the same keys)."""
    if not isinstance(data, dict):
        raise SpriteSetError("a Link sprite set file holds one JSON object")
    if data.get("format") != FILE_FORMAT:
        raise SpriteSetError(f'not a built-in-art set file (its "format" is not "{FILE_FORMAT}")')
    if data.get("version") != FILE_VERSION:
        raise SpriteSetError(f"a built-in-art set file of version {data.get('version')!r}: this ZORA reads "
                             f"version {FILE_VERSION}")
    halves = data.get("halves")
    if not isinstance(halves, dict) or set(halves) != set(LINK_HALVES):
        raise SpriteSetError(f'a built-in-art set\'s "halves" names each of Link\'s halves once: '
                             f'{", ".join(LINK_HALVES)}')
    sources = []
    for name in LINK_HALVES:
        half = halves[name]
        if not isinstance(half, dict) or not isinstance(half.get("mirror", False), bool):
            raise SpriteSetError(f'a built-in-art set\'s half {name} is {{"block", "tile", "mirror"}}')
        sources.append(ArtHalf(half.get("block", ""), _tile_number(half.get("tile")), half.get("mirror", False)))
    swaps = data.get("swap", [])
    if not isinstance(swaps, list) or not all(isinstance(swap, dict) and isinstance(swap.get("mirror", False), bool)
                                              for swap in swaps):
        raise SpriteSetError('a built-in-art set\'s "swap" is a list of {"block", "tile", "link", "mirror", "colors"}')
    return ArtSet(data.get("name", ""), data.get("author", ""), data.get("provenance", ""), tuple(sources),
                  _colors(data.get("colors", list(IDENTITY_COLORS))), recommended_colors(data.get("recommendedColors")),
                  tuple(ArtSwap(ArtHalf(swap.get("block", ""), _tile_number(swap.get("tile"))), swap.get("link", ""),
                                swap.get("mirror", False), _colors(swap.get("colors", list(IDENTITY_COLORS))))
                        for swap in swaps))


def _colors(colors: Any) -> tuple[int, int, int]:
    if not isinstance(colors, list) or len(colors) != len(IDENTITY_COLORS):
        raise SpriteSetError('a built-in-art set\'s "colors" are three of 0, 1, 2 and 3')
    return colors[0], colors[1], colors[2]


def art_set_object(art: ArtSet) -> dict[str, Any]:
    """A set as its file's JSON object."""
    halves: dict[str, Any] = {}
    for name, half in zip(LINK_HALVES, art.halves, strict=True):
        halves[name] = {"block": half.block, "tile": f"${half.tile:02X}"}
        if half.mirror:
            halves[name]["mirror"] = True
    data: dict[str, Any] = {"format": FILE_FORMAT, "version": FILE_VERSION, "name": art.name,
                            "author": art.author, "provenance": art.provenance, "halves": halves}
    if art.colors != IDENTITY_COLORS:
        data["colors"] = list(art.colors)
    if art.recommended is not None:
        data["recommendedColors"] = recommended_colors_object(art.recommended)
    if art.swaps:
        data["swap"] = [_swap_object(swap) for swap in art.swaps]
    return data


def _swap_object(swap: ArtSwap) -> dict[str, Any]:
    data: dict[str, Any] = {"block": swap.target.block, "tile": f"${swap.target.tile:02X}", "link": swap.link_half}
    if swap.mirror:
        data["mirror"] = True
    if swap.colors != IDENTITY_COLORS:
        data["colors"] = list(swap.colors)
    return data


def art_set_from_file(text: str | bytes) -> ArtSet:
    """A set from its file's contents."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SpriteSetError("a Link sprite set file is JSON; this one does not read as JSON") from exc
    return art_set_from_object(data)


def art_set_file(art: ArtSet) -> str:
    """A set's file contents, one line per half."""
    data = art_set_object(art)
    halves = data.pop("halves")
    swaps = data.pop("swap", [])
    text = json.dumps(data, indent=2)
    lines = ",\n".join(f"    {json.dumps(name)}: {json.dumps(half)}" for name, half in halves.items())
    text = text[:-2] + f',\n  "halves": {{\n{lines}\n  }}'
    if swaps:
        text += ',\n  "swap": [\n' + ",\n".join(f"    {json.dumps(swap)}" for swap in swaps) + "\n  ]"
    return text + "\n}\n"


@cache
def built_in_art_sets() -> dict[str, ArtSet]:
    """ZORA's built-in-art sets by id (each file's name without .json), in id order."""
    folder = files(__package__).joinpath(BUILT_IN_ART_FOLDER)
    found = sorted((entry.name.removesuffix(FILE_EXTENSION), entry) for entry in folder.iterdir()
                   if entry.name.endswith(FILE_EXTENSION))
    return {set_id: art_set_from_file(entry.read_text(encoding="utf-8")) for set_id, entry in found}


# Either kind of Link sprite set: FP-LINK-02's 640 bytes, or built-in art.
LinkSpriteSet = SpriteSet | ArtSet


def sprite_set_tiles(sprite_set: LinkSpriteSet, read: Callable[[int, int], bytes] = original_bytes) -> bytes:
    """The 640 bytes a set draws Link from: a built-in-art set's assembled from the player's ROM, a
    640-byte set's with its fromGame ranges read from the player's ROM (the original Link's bytes at
    the same places)."""
    if isinstance(sprite_set, ArtSet):
        return art_tiles(sprite_set, read)
    if not sprite_set.from_game:
        return sprite_set.tiles
    tiles, original = bytearray(sprite_set.tiles), original_link_tiles(read)
    for start, end in sprite_set.from_game:
        tiles[start:end] = original[start:end]
    return bytes(tiles)


def original_link_tiles(read: Callable[[int, int], bytes] = original_bytes) -> bytes:
    """The original Link's 640 bytes in the player's ROM, in a set's order."""
    return b"".join(read(offset, tiles * TILE_SIZE) for offset, tiles in LINK_TILE_GROUPS)


def link_sprite_set_from_object(data: Any) -> LinkSpriteSet:
    """Either kind of set from its file's JSON object, by its "format"."""
    if isinstance(data, dict) and data.get("format") == FILE_FORMAT:
        return art_set_from_object(data)
    return sprite_set_from_object(data)


def link_sprite_set_object(sprite_set: LinkSpriteSet) -> dict[str, Any]:
    """Either kind of set as its file's JSON object."""
    return art_set_object(sprite_set) if isinstance(sprite_set, ArtSet) else sprite_set_object(sprite_set)


def offered_sprite_sets() -> dict[str, LinkSpriteSet]:
    """ZORA's sets the page offers by id: the 640-byte sets, then the built-in-art sets, each kind in
    id order. Random draws from them in this order (player_settings.random_sprite_set)."""
    tile_sets: dict[str, LinkSpriteSet] = dict(built_in_sprite_sets())
    art_sets = built_in_art_sets()
    assert not tile_sets.keys() & art_sets.keys(), "a built-in set's id names one set"
    return {**tile_sets, **art_sets}


def has_swap(sprite_set: LinkSpriteSet | None) -> bool:
    """A person set that can also draw the person as Link."""
    return isinstance(sprite_set, ArtSet) and bool(sprite_set.swaps)
