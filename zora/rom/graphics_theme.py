"""Graphics theme (Look and feel; Halloween Mode, owner, 2026-10-29): a seasonal pack's tiles and
Ganon's palettes, purely cosmetic.

The tiles go into a working copy of the player's ROM before generation (themed_player_rom), the way
a ROM with modified graphics is handled: parse_rom reads the copy, so every tile the generation
copies (the boss and enemy group passes, Oops All Enemies and Oops All Bosses) carries the theme's
art to wherever it lands, and the finished ROM is written over the copy, so the background tiles
come along. The untouched ROM stays the player's: identify_rom, the release, the modified-graphics
flag and every read of the original game (base_rom.original_bytes) use it. After generation
(theme_after_generation, from write_player_settings) the theme writes Ganon's palettes, and the
fireball's tiles again, since Item and Sprite Appearance (C15) may have drawn an item there.

A theme is purely cosmetic: tiles and palettes only, never a layout, door or collision table, and
never CommonBackgroundPatterns $30-$5F (RESERVED_BACKGROUND_TILES). A ROM generated with a theme
differs from one without only in pattern-tile and palette bytes (tests/test_graphics_theme.py), and
a finished ROM cannot take one afterwards (player_settings.apply_player_settings refuses it).

The file format (zora/rom/themes/<theme>.json, package data, written by
scripts/z1m1_holiday_graphics.py): UTF-8 JSON, one object,

    {"format": "zora-graphics-theme", "version": 1, "name": "...", "author": "...", "provenance": "...",
     "blocks": {"PatternBlockOWBG": {"tiles": [0, 1, ...], "data": "<base64>", "fromGame": [[a, b], ...]},
                ...},
     "ganonPalettes": {"normal": [5, 24, 52], "second": [7, 21, 48]}}

A block is a pattern block of revision.GRAPHICS_BLOCKS (the disassembly's bins.xml labels); its tiles
are their indexes in the block, its data their 16 bytes each in that order, and fromGame the byte
ranges of data kept as the player's own (zeros in data, never written), as the Link sets' fromGame."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from enum import Enum
from functools import cache, lru_cache
from importlib.resources import files
from typing import Any

from .base_rom import PlayerRom, original_bytes, player_rom_of
from .revision import GRAPHICS_BLOCKS, NES_HEADER_SIZE

FILE_FORMAT = "zora-graphics-theme"
FILE_VERSION = 1
THEMES_FOLDER = "themes"                    # zora/rom/themes/<theme>.json, package data
TILE_BYTES = 16
# CommonBackgroundPatterns tiles a theme never writes: $30-$4F is the common boss block (Randomize
# Boss Groups' special boss, PS-BGRP-01), $50-$5F Change Hidden OW Tiles' secret squares (B89) and
# Pegasus Boots' blank priority sprites ($50/$51, which must stay blank).
RESERVED_BACKGROUND_TILES = range(0x30, 0x60)
COMMON_BACKGROUND = "CommonBackgroundPatterns"
COMMON_SPRITES = "CommonSpritePatterns"
# The fireball (Z_04 "Fireball tile" $44, an 8x16 pair): one of Item and Sprite Appearance's 34
# pictures (item_sprites.ITEM_PATTERNS 0x84CF), so a theme's fireball is written again after it.
FIREBALL_TILES = (0x44, 0x45)
# Ganon's palettes (headered file offsets): colors 1-3 of GanonPaletteRow7TransferBuf (bank 6), and
# GanonColorSets (bank 4), whose first set is the brown-and-white one and second the red-and-blue
# one, which PRG0 keeps equal to the normal palette (Z1M1's ZeldaEditor writes all three).
GANON_NORMAL_COLORS = 0x1A216
GANON_BROWN_COLORS = 0x12F74
GANON_BLUE_COLORS = 0x12F77
PALETTE_COLORS = 3


class GraphicsTheme(Enum):
    """Look and feel's Graphics theme: Off (the default) or a seasonal pack."""
    OFF = "off"
    HALLOWEEN = "halloween"


class ThemeError(ValueError):
    """A theme file ZORA cannot read."""


@dataclass(frozen=True)
class ThemeTile:
    """One tile of a theme: its pattern block and index there, its 16 bytes, and the byte ranges
    within them kept as the player's own."""
    block: str
    index: int
    data: bytes
    from_game: tuple[tuple[int, int], ...] = ()

    @property
    def offset(self) -> int:
        """Its file offset, header included (the same in PRG0 and PRG1: no graphics block moves)."""
        return NES_HEADER_SIZE + BLOCK_OFFSETS[self.block] + self.index * TILE_BYTES


@dataclass(frozen=True)
class ThemeData:
    name: str
    author: str
    provenance: str
    tiles: tuple[ThemeTile, ...]
    ganon_normal: tuple[int, int, int]
    ganon_second: tuple[int, int, int]

    @property
    def fireball(self) -> tuple[ThemeTile, ...]:
        return tuple(tile for tile in self.tiles if tile.block == COMMON_SPRITES and tile.index in FIREBALL_TILES)


# Each pattern block's offset in the ROM data (without the header) and its tile count
BLOCK_OFFSETS = {name: offset for name, offset, _length in GRAPHICS_BLOCKS}
BLOCK_TILES = {name: length // TILE_BYTES for name, _offset, length in GRAPHICS_BLOCKS}


def block_of_offset(offset: int) -> tuple[str, int]:
    """The pattern block holding a ROM data offset (no header) and the tile's index in it."""
    for name, start, length in GRAPHICS_BLOCKS:
        if start <= offset < start + length:
            return name, (offset - start) // TILE_BYTES
    raise ThemeError(f"ROM data offset 0x{offset:05X} is in no pattern block")


def _palette(values: object, which: str) -> tuple[int, int, int]:
    if not (isinstance(values, list) and len(values) == PALETTE_COLORS
            and all(isinstance(value, int) and 0 <= value < 0x40 for value in values)):
        raise ThemeError(f"a theme's {which} Ganon palette is three NES colors")
    return values[0], values[1], values[2]


def theme_from_object(data: dict[str, Any]) -> ThemeData:
    if data.get("format") != FILE_FORMAT or data.get("version") != FILE_VERSION:
        raise ThemeError(f"not a {FILE_FORMAT} file of version {FILE_VERSION}")
    tiles = []
    for block, entry in data["blocks"].items():
        if block not in BLOCK_OFFSETS:
            raise ThemeError(f"a theme names an unknown pattern block {block!r}")
        raw = base64.b64decode(entry["data"])
        if len(raw) != TILE_BYTES * len(entry["tiles"]):
            raise ThemeError(f"{block}: {len(raw)} bytes for {len(entry['tiles'])} tiles")
        kept = [tuple(run) for run in entry.get("fromGame", [])]
        for position, index in enumerate(entry["tiles"]):
            if not 0 <= index < BLOCK_TILES[block]:
                raise ThemeError(f"{block} has no tile {index}")
            if block == COMMON_BACKGROUND and index in RESERVED_BACKGROUND_TILES:
                raise ThemeError(f"a theme never writes {COMMON_BACKGROUND} tile ${index:02X}")
            start = position * TILE_BYTES
            runs = tuple((a - start, b - start) for a, b in kept if start <= a < start + TILE_BYTES)
            tiles.append(ThemeTile(block, index, raw[start:start + TILE_BYTES], runs))
    palettes = data["ganonPalettes"]
    return ThemeData(data["name"], data["author"], data["provenance"], tuple(tiles),
                     _palette(palettes["normal"], "normal"), _palette(palettes["second"], "second"))


@cache
def load_theme(theme: GraphicsTheme) -> ThemeData:
    """A shipped theme (package data)."""
    if theme is GraphicsTheme.OFF:
        raise ThemeError("Off is no theme")
    text = files(__package__).joinpath(THEMES_FOLDER, f"{theme.value}.json").read_text(encoding="utf-8")
    return theme_from_object(json.loads(text))


def _write_tile(image: bytearray, tile: ThemeTile) -> None:
    """A theme tile over an image in PRG0's layout (headered), its fromGame bytes left as they are."""
    kept = {offset for start, end in tile.from_game for offset in range(start, end)}
    for position, value in enumerate(tile.data):
        if position not in kept:
            image[tile.offset + position] = value


def themed_image(layout: bytes, theme: GraphicsTheme) -> bytes:
    """The working copy: the player's ROM in PRG0's layout with the theme's tiles."""
    image = bytearray(layout)
    for tile in load_theme(theme).tiles:
        _write_tile(image, tile)
    return bytes(image)


@lru_cache(maxsize=4)
def themed_player_rom(data: bytes, theme: GraphicsTheme) -> PlayerRom:
    """The player's ROM with a theme's working copy as the canvas generation parses and writes
    (PlayerRom.canvas); its identity and original-game reads stay the untouched ROM's. Off is the
    player's ROM as it is."""
    player = player_rom_of(data)
    if theme is GraphicsTheme.OFF:
        return player
    return player.with_canvas(theme.value, themed_image(player.layout, theme))


def theme_after_generation(image: bytearray, theme: GraphicsTheme) -> None:
    """write_player_settings' part, on the finished image in PRG0's layout: Ganon's palettes, and the
    fireball's tiles again (Item and Sprite Appearance may have drawn an item there; its fromGame bytes
    from the player's untouched ROM)."""
    if theme is GraphicsTheme.OFF:
        return
    data = load_theme(theme)
    for tile in data.fireball:
        image[tile.offset:tile.offset + TILE_BYTES] = original_bytes(tile.offset, TILE_BYTES)
        _write_tile(image, tile)
    for offset, colors in ((GANON_NORMAL_COLORS, data.ganon_normal), (GANON_BROWN_COLORS, data.ganon_second),
                           (GANON_BLUE_COLORS, data.ganon_normal)):
        image[offset:offset + PALETTE_COLORS] = bytes(colors)


def theme_offsets(theme: GraphicsTheme) -> set[int]:
    """Every file offset a theme may change in a finished ROM: any pattern tile (the generation
    carries the theme's art to wherever it copies a tile) and Ganon's palettes."""
    if theme is GraphicsTheme.OFF:
        return set()
    tiles = {NES_HEADER_SIZE + offset + position for _name, offset, length in GRAPHICS_BLOCKS
             for position in range(length)}
    palettes = {offset + color for offset in (GANON_NORMAL_COLORS, GANON_BROWN_COLORS, GANON_BLUE_COLORS)
                for color in range(PALETTE_COLORS)}
    return tiles | palettes
