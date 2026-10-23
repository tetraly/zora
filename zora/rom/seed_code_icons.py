"""The seed code's four icons as the file-select screen draws them (FP-HASH-01), for the web page to
show beside their names: the finished ROM's own tiles, frame tables and menu palette, so a player's
custom sprites (modified graphics), Pegasus Boots' boot and the tunic color setting show as they
will in the game. Aldonunez labels, at the pinned disassembly commit.

asm/fp-hash-01 draws each code item as a room item is drawn: DrawItemBySlot picks the sprite
attributes (the palette row) from the item's slot and value, and Anim_WriteSpecificItemSprites
picks the 8x16 sprite pair from the slot's first frame tile. The palette is the file-select
menu's (MenuPalettesTransferBuf), whose first three sprite rows take each save file's tunic color;
the icons show a new game's screen, with no save files, so all three take the green tunic's.

The menu's sprite rows 0-2 are the save files' Links (color 1 each file's ring color) and row 3 is
the cursor's ($0F $15 $27 $30, the in-play red row but for $15). asm/fp-hash-01 keeps an item drawn
in Link's row (0) there, the tunic color as in play, and moves every other item to row 3 (owner,
2026-10-22): the red and blue rows' items, and the Heart and Triforce, which flash in a room
(DrawItemBySlot alternates rows 1 and 2) and here show steady in row 3. So no icon takes a save
file's tunic color, nor goes blank under a black tunic (tests/test_seed_code_icons.py)."""
from __future__ import annotations

from dataclasses import dataclass

from .code_patches import seed_code, seed_code_values
from .inventory import ITEM_ID_TO_DESCRIPTOR, ITEM_ID_TO_SLOT
from .layout import NES_HEADER_SIZE
from .player_settings import TUNIC_FILE_SELECT_COPY
from .revision import GRAPHICS_BLOCKS, finished_in_prg0_layout
from .sword_states import DRAW_ITEM_SWORD_CMP

ICON_SIZE = 16                          # two 8x16 sprites side by side
SPRITE_WIDTH, SPRITE_HEIGHT = 8, 16
TILE_SIZE = 8
TILE_BYTES = 16                         # two bit planes of 8 bytes

# DrawItemBySlot (bank 7) and the tables it reads (bank 1), file offsets in PRG0's layout.
ITEM_SLOT_PALETTES = 0x06B6C            # ItemSlotToPaletteOffsetsOrValues: a row, or an offset to the value
FLASHING_SLOTS = frozenset({0x16, 0x19, 0x1A, 0x1B})        # rows 1 and 2 by turns
FLASH_FIRST_ROW = 1
LINK_ROW = 0                            # asm/fp-hash-01: an icon in Link's row keeps it
MENU_ITEM_ROW = 3                       # every other icon is drawn in the cursor's row
VALUE_OFFSET_SLOTS = frozenset({0x00, 0x02, 0x04, 0x07, 0x0B})   # row = table entry + the item's value
SWORD_SLOT = 0x00
MASTER_SWORD_IMAGE_SLOT = 0x20          # the sword slot's image when its row is DrawItemBySlot's CMP operand
DESCRIPTOR_FULL = 0x30                  # descriptor class 3: the value is $FF
DESCRIPTOR_VALUE_MASK = 0x0F
BYTE_MASK = 0xFF

# Anim_WriteSpecificItemSprites (bank 1): the slot's first frame tile, and the tile bounds that
# choose how the pair is drawn, read from its CMP operands (Pegasus Boots moves the narrow start).
ITEM_FRAME_OFFSETS = 0x07137            # Anim_ItemFrameOffsets, one per item slot
ITEM_FRAME_TILES = 0x0715C              # Anim_ItemFrameTiles
NARROW_TILE_OPERAND = 0x071CA           # CMP #$F3: also half-width
NARROW_FIRST_OPERAND = 0x071CE          # CMP #$20: half-width from here
NARROW_END_OPERAND = 0x071D2            # CMP #$62: up to here
SLIM_END_OPERAND = 0x071EB              # CMP #$6C: wide tiles below it overlap by a pixel
MIRRORED_END_OPERAND = 0x071EF          # CMP #$7C: from here the right half is the next tile pair
NARROW_X = 4                            # a half-width item is centered
SLIM_RIGHT_X = 7
WIDE_RIGHT_X = 8
RIGHT_TILE_STEP = 2

# Sprite attributes
PALETTE_ROW_MASK = 0x03
FLIP_HORIZONTAL = 0x40
FLIP_VERTICAL = 0x80
PATTERN_TABLE_BIT = 0x01                # an 8x16 sprite's tile byte: bit 0 picks the pattern table

# What the PPU's sprite pattern table holds on the file-select screen: CommonSpritePatterns at $0000
# (TransferCommonPatterns), DemoSpritePatterns from $0700 at power-on (TransferDemoPatterns; a
# level's blocks start at $08E0) and CommonMiscPatterns at $1F20.
PATTERN_TABLE_SIZE = 0x1000
CHR_BLOCKS = (("CommonSpritePatterns", 0x0000), ("DemoSpritePatterns", 0x0700), ("CommonMiscPatterns", 0x1F20))
DEMO_BLOCK_END = 0x08E0                 # where a level's sprite blocks start

# MenuPalettesTransferBuf (bank 6): a transfer record (PPU address, length) of the 8 palette rows.
MENU_PALETTES = 0x19CE8
TRANSFER_HEADER = 3
COLORS_PER_ROW = 4
SPRITE_ROWS_START = 4 * COLORS_PER_ROW
TUNIC_ROWS = 3                          # one per save file
TUNIC_COLOR_INDEX = 1
NO_RING = 0


@dataclass(frozen=True)
class CodeIcon:
    """One code item: its name and the 16x16 icon as NES palette values, row by row."""
    name: str
    pixels: tuple[tuple[int, ...], ...]


def seed_code_icons(rom: bytes) -> list[CodeIcon]:
    """The finished ROM's seed code as the file-select screen draws it, in screen order."""
    image = finished_in_prg0_layout(rom)
    names = seed_code(rom)
    return [CodeIcon(name, draw_item(image, item)) for name, item in zip(names, seed_code_values(image), strict=True)]


def draw_item(image: bytes, item: int) -> tuple[tuple[int, ...], ...]:
    """FP-HASH-01: one code item as asm/fp-hash-01 draws it, on the menu's backdrop color."""
    slot = image[ITEM_ID_TO_SLOT + item]
    attributes, slot = item_attributes(image, slot, image[ITEM_ID_TO_DESCRIPTOR + item])
    if attributes & PALETTE_ROW_MASK != LINK_ROW:
        attributes |= MENU_ITEM_ROW
    palette = menu_sprite_palettes(image)[attributes & PALETTE_ROW_MASK]
    backdrop = image[MENU_PALETTES + TRANSFER_HEADER]
    canvas = [[backdrop] * ICON_SIZE for _ in range(ICON_SIZE)]
    # The left sprite has the lower OAM index, so it is drawn over the right where both show.
    for x, tile, sprite_attributes in reversed(sprite_pair(image, slot, attributes)):
        for row, line in enumerate(sprite_pixels(image, tile, sprite_attributes)):
            for column, color in enumerate(line):
                if color:
                    canvas[row][x + column] = palette[color]
    return tuple(tuple(row) for row in canvas)


def item_attributes(image: bytes, slot: int, descriptor: int) -> tuple[int, int]:
    """DrawItemBySlot: the sprite attributes for the item, and the slot whose image is drawn."""
    attributes = image[ITEM_SLOT_PALETTES + slot]
    if slot in FLASHING_SLOTS:
        attributes = FLASH_FIRST_ROW
    elif slot in VALUE_OFFSET_SLOTS:
        value = (BYTE_MASK if descriptor == DESCRIPTOR_FULL else descriptor) & DESCRIPTOR_VALUE_MASK
        attributes = (attributes + value) & BYTE_MASK
        if slot == SWORD_SLOT and attributes == image[DRAW_ITEM_SWORD_CMP]:
            slot = MASTER_SWORD_IMAGE_SLOT
    return attributes, slot


def sprite_pair(image: bytes, slot: int, attributes: int) -> list[tuple[int, int, int]]:
    """Anim_WriteSpecificItemSprites: the slot's first frame as (x, tile, attributes) per sprite,
    left first: a half-width item one centered sprite, a wide one its tile beside its mirror image
    (a pixel closer below the slim bound), and from MIRRORED_END on the tile beside the next."""
    tile = image[ITEM_FRAME_TILES + image[ITEM_FRAME_OFFSETS + slot]]
    if tile == image[NARROW_TILE_OPERAND] or image[NARROW_FIRST_OPERAND] <= tile < image[NARROW_END_OPERAND]:
        return [(NARROW_X, tile, attributes)]
    if tile >= image[MIRRORED_END_OPERAND]:
        return [(0, tile, attributes), (WIDE_RIGHT_X, tile + RIGHT_TILE_STEP, attributes)]
    right_x = SLIM_RIGHT_X if tile < image[SLIM_END_OPERAND] else WIDE_RIGHT_X
    return [(0, tile, attributes), (right_x, tile, attributes ^ FLIP_HORIZONTAL)]


def sprite_pixels(image: bytes, tile: int, attributes: int) -> list[list[int]]:
    """An 8x16 sprite's 16 rows of color indexes (0 transparent), flipped as its attributes say."""
    table = (tile & PATTERN_TABLE_BIT) * PATTERN_TABLE_SIZE
    first = tile & ~PATTERN_TABLE_BIT
    rows = [row for half in (first, first + 1) for row in tile_rows(pattern(image, table + half * TILE_BYTES))]
    if attributes & FLIP_HORIZONTAL:
        rows = [row[::-1] for row in rows]
    if attributes & FLIP_VERTICAL:
        rows.reverse()
    return rows


def tile_rows(data: bytes) -> list[list[int]]:
    """A tile's 8 rows of 2-bit color indexes: plane 0 the low bit, plane 1 the high."""
    return [[((low >> bit) & 1) | (((high >> bit) & 1) << 1) for bit in range(TILE_SIZE - 1, -1, -1)]
            for low, high in zip(data[:TILE_SIZE], data[TILE_SIZE:], strict=True)]


def pattern(image: bytes, ppu_address: int) -> bytes:
    """The 16 bytes of the tile at a sprite pattern table address on the file-select screen."""
    blocks = {name: (start, size) for name, start, size in GRAPHICS_BLOCKS}
    for name, destination in CHR_BLOCKS:
        start, size = blocks[name]
        end = min(destination + size, DEMO_BLOCK_END) if name == "DemoSpritePatterns" else destination + size
        if destination <= ppu_address and ppu_address + TILE_BYTES <= end:
            offset = NES_HEADER_SIZE + start + ppu_address - destination
            return bytes(image[offset:offset + TILE_BYTES])
    raise ValueError(f"no pattern block is loaded at PPU ${ppu_address:04X} on the file-select screen")


def menu_sprite_palettes(image: bytes) -> list[tuple[int, ...]]:
    """The file-select menu's four sprite palette rows, as InitMode1_Sub1 sends them with no save
    files: each save file's row takes the tunic color of no ring (LinkColors)."""
    colors = image[MENU_PALETTES + TRANSFER_HEADER + SPRITE_ROWS_START:][:4 * COLORS_PER_ROW]
    rows = [list(colors[row * COLORS_PER_ROW:(row + 1) * COLORS_PER_ROW]) for row in range(4)]
    for row in rows[:TUNIC_ROWS]:
        row[TUNIC_COLOR_INDEX] = image[TUNIC_FILE_SELECT_COPY + NO_RING]
    return [tuple(row) for row in rows]

