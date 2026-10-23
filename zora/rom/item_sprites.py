"""Item and Sprite Appearance (C15 = 1 to 3; features-behavior.md FP-SPRITE-01): the 34 item
pictures replaced, the title story's item list, and the file-select screen's code shown as four
characters instead of icons. Written by the final steps after every other code patch, from the
pictures as the ROM image holds them then (the player's graphics), with their own stream
(pipeline.item_sprites_key; FL-SEED-01 leaves the draws' source open).

  C15 = 1 (fun percentage): one of twelve source pictures drawn, written to all 34, then four
           zeroed.
  C15 = 2 (sprite shuffle): each of the 34, in order, takes one of the 19 sources (their bytes
           before any write), drawn with repetition; the same four zeroed; then five groups made
           equal to their first member.

In an Archipelago ROM with the logo (GameConfig.foreign_logo) the magical shield's picture is the
logo, which stands for another player's item; it is no source then, so no other item takes the
logo's look, and no target, so other players' items keep it (owner decisions, 2026-10-22).
"""
from __future__ import annotations

from ..generate.rng import IntRng
from .base_rom import original_bytes

Writes = list[tuple[int, bytes]]

PATTERN_BYTES = 32                     # two tiles
# The 34 item pictures in file order: ten of the title story's (DemoSpritePatterns, bank 1) and 24
# of the common sprite patterns (CommonSpritePatterns, bank 2, tiles $20-$6E)
ITEM_PATTERNS = (0x4E24, 0x4E64, 0x4E84, 0x4EA4, 0x4EE4, 0x4F04, 0x4F24, 0x4F44, 0x4F64, 0x4F84,
                 0x828F, 0x82AF, 0x82CF, 0x82EF, 0x830F, 0x832F, 0x834F, 0x83CF, 0x83EF, 0x840F,
                 0x842F, 0x848F, 0x84AF, 0x84CF, 0x84EF, 0x850F, 0x852F, 0x854F, 0x856F, 0x85EF,
                 0x870F, 0x872F, 0x874F, 0x876F)
FUN_PERCENTAGE_SOURCES = (0x82AF, 0x82CF, 0x82EF, 0x834F, 0x83CF, 0x83EF, 0x848F, 0x84AF, 0x84EF, 0x854F,
                          0x856F, 0x85EF)
NEVER_SOURCES = frozenset({0x4E64, 0x4E84, 0x4EA4, 0x4EE4, 0x4F04, 0x4F24, 0x4F44, 0x4F64, 0x4F84, 0x840F,
                           0x842F, 0x870F, 0x872F, 0x874F, 0x876F})
SHUFFLE_SOURCES = tuple(offset for offset in ITEM_PATTERNS if offset not in NEVER_SOURCES)
ZEROED = (0x4E84, 0x4EE4, 0x4F24, 0x4F64)
# C15 = 2's five groups, each made equal to its first member
EQUAL_GROUPS = ((0x828F, 0x850F, 0x4F04), (0x4F44, 0x830F), (0x4E64, 0x4EA4), (0x4F84, 0x852F),
                (0x83EF, 0x840F, 0x842F))
FUN_PERCENTAGE, SPRITE_SHUFFLE = 1, 2
LOGO_PATTERN = 0x85EF                  # the magical shield's tiles $56/$57 (archipelago_logo)
assert LOGO_PATTERN in FUN_PERCENTAGE_SOURCES and LOGO_PATTERN in SHUFFLE_SOURCES
assert len(ITEM_PATTERNS) == 34 and len(SHUFFLE_SOURCES) == 19

# Under every C15 but 0: the title story's left item list (DemoLeftItemIds), its first 18 entries
DEMO_LEFT_ITEMS = 0x9250
DEMO_LEFT_ITEMS_CHANGED = 18
DEMO_ITEM = 0x34

# FP-HASH-01 under C15 = 1 to 3: no icons (the file-select set-up keeps PRG0's code), and the heading
# row's eighth to eleventh tiles show four characters, a digit 1 to 9 or a letter A to Z
FILE_SELECT_SETUP = 0x0A4CD
FILE_SELECT_SETUP_LENGTH = 7
HEADING_TILES = 0x1A129
CODE_CHARACTERS = HEADING_TILES + 7
CODE_CHARACTER_TILES = range(0x01, 0x24)          # 1 to 9, then A to Z
CODE_TEXT = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
assert len(CODE_TEXT) == len(CODE_CHARACTER_TILES)


def _pattern(image: bytes | bytearray, offset: int) -> bytes:
    return bytes(image[offset:offset + PATTERN_BYTES])


def _sources(offsets: tuple[int, ...], logo: bool) -> tuple[int, ...]:
    return tuple(offset for offset in offsets if offset != LOGO_PATTERN) if logo else offsets


def item_sprite_writes(image: bytes | bytearray, appearance: int, rng: IntRng, logo: bool = False) -> Writes:
    """FP-SPRITE-01's pattern writes and the title story's list, from the pictures in `image`;
    with `logo` (the Archipelago logo in the shield's tiles) the shield's picture is neither a
    source nor written (its draw is still made, so the other pictures keep theirs)."""
    patterns: dict[int, bytes]
    if appearance == FUN_PERCENTAGE:
        offsets = _sources(FUN_PERCENTAGE_SOURCES, logo)
        source = _pattern(image, offsets[rng.below(len(offsets))])
        patterns = dict.fromkeys(ITEM_PATTERNS, source)
    elif appearance == SPRITE_SHUFFLE:
        sources = [_pattern(image, offset) for offset in _sources(SHUFFLE_SOURCES, logo)]
        patterns = {offset: sources[rng.below(len(sources))] for offset in ITEM_PATTERNS}
    else:
        raise ValueError(f"C15 = {appearance} writes nothing")
    patterns.update(dict.fromkeys(ZEROED, bytes(PATTERN_BYTES)))
    if appearance == SPRITE_SHUFFLE:
        for first, *others in EQUAL_GROUPS:
            patterns.update(dict.fromkeys(others, patterns[first]))
    if logo:
        del patterns[LOGO_PATTERN]
    return [*patterns.items(), (DEMO_LEFT_ITEMS, bytes([DEMO_ITEM]) * DEMO_LEFT_ITEMS_CHANGED)]


def code_characters(code_items: bytes) -> bytes:
    """The four characters for a seed's code: each item's place among the 28 code items, as a tile
    from 1 to 9 and A to Z (a function of the same values as the icons; FP-SPRITE-01 lets a rebuild
    choose them)."""
    from .code_patches import SEED_CODE_ITEMS
    return bytes(CODE_CHARACTER_TILES[SEED_CODE_ITEMS.index(item)] for item in code_items)


def file_select_code_writes(code_items: bytes) -> Writes:
    """Under C15 = 1 to 3: the set-up's PRG0 code (no icons) and the four characters."""
    return [(FILE_SELECT_SETUP, original_bytes(FILE_SELECT_SETUP, FILE_SELECT_SETUP_LENGTH)),
            (CODE_CHARACTERS, code_characters(code_items))]


def code_text(rom: bytes | bytearray) -> str | None:
    """The four characters a finished ROM's file-select screen shows instead of icons (C15 = 1 to
    3), or None when it shows icons."""
    if bytes(rom[FILE_SELECT_SETUP:FILE_SELECT_SETUP + FILE_SELECT_SETUP_LENGTH]) != original_bytes(
            FILE_SELECT_SETUP, FILE_SELECT_SETUP_LENGTH):
        return None
    tiles = rom[CODE_CHARACTERS:CODE_CHARACTERS + 4]
    if not all(tile in CODE_CHARACTER_TILES for tile in tiles):
        return None
    return "".join(CODE_TEXT[tile - CODE_CHARACTER_TILES.start] for tile in tiles)
