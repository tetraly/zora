"""Item Counter (the ZORA flag item_counter; idea: Ultralavos): the ROM side of asm/flags2/item-counter.

The patch shows chest, found, slash, total on the status bar row under the rupees: an orange chest, then a white
slash in the numbers' colors. CommonBackgroundPatterns tiles $52 and $53 become the chest and the slash: blank in
PRG0, drawn by no screen, and in the row kept for tiles loaded everywhere (owner decision 2026-11-14: $50/$51
Pegasus Boots' blank priority sprites, $5C-$5F the Archipelago logo; Change Hidden OW Tiles shares $30-$3F with
the boss expansion, zora/rom/hidden_tiles.py step 4); graphics_theme.RESERVED_BACKGROUND_TILES keeps themes off
them. Before then the chest was tile $60, drawn twice (the second in the numbers' gray). The digits and A-F are
the font's own tiles $00-$0F. The seed's table (asm/rom_space.toml site "item-counter-table", bank 5
$BE60-$BEDF, clear of the code lozft puts at $BA40-$BAB9 on a music ROM) lists each area's places as the patch
reads them (asm/flags2/item-counter/bank_05.s); zora/generate/item_counter.py says which places count.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .layout import BOSS_SET_EXPANSION_SPRITES_ADDRESS

TABLE = 0x17E70                         # bank 5 $BE60
TABLE_SIZE = 0x80
AREAS = 10                              # 0 the overworld, 1-9 the levels
BLOCK_HEADER = 3                        # flags address (low, high), the number of places
PLACE_LIMIT = 0x80                      # a room, cellar or screen number is below it
WARE_PLACE = 0x80                       # a shop ware: %100PPSSS
WARE_POSITION_SHIFT = 3
DISPLAY_LIMIT = 0x0F                    # the font's F: a count or total above it cannot be shown

# CommonBackgroundPatterns starts 768 bytes before the boss expansion that reuses it (model/sprites.py).
COMMON_BACKGROUND = BOSS_SET_EXPANSION_SPRITES_ADDRESS - 0x300
TILE_BYTES = 16
CHEST_TILE = 0x52
SLASH_TILE = 0x53

# The status bar's colors: 0 black, then 1-3 as the 2x2-tile block's palette has them. The chest sits in the icons'
# column (1 red, 2 orange, 3 peach): an orange chest with a red lock. The slash sits among the numbers (1 white,
# 2 gray, 3 blue), white like the font's digits.
COLORS = {".": 0, "W": 1, "O": 2, "P": 3}
CHEST = (
    "........",
    ".OOOOOO.",
    "OOOOOOOO",
    "........",
    "OOOWWOOO",
    "OOOW.OOO",
    "OOOOOOOO",
    "........",
)
SLASH = (
    "......WW",
    ".....WW.",
    "....WW..",
    "...WW...",
    "..WW....",
    ".WW.....",
    "WW......",
    "........",
)


def tile_bytes(rows: Sequence[str]) -> bytes:
    """An 8x8 tile's 16 pattern bytes: the eight low-bit planes, then the eight high."""
    low = bytearray(8)
    high = bytearray(8)
    for y, row in enumerate(rows):
        for x, pixel in enumerate(row):
            color = COLORS[pixel]
            low[y] |= (color & 1) << (7 - x)
            high[y] |= (color >> 1) << (7 - x)
    return bytes(low + high)


@dataclass(frozen=True)
class CounterArea:
    """One area's block: its room flags' address and its places, each counting one once taken."""
    flags_address: int
    places: tuple[int, ...] = ()

    @property
    def total(self) -> int:
        return len(self.places)


def ware_place(position: int, shop_number: int) -> int:
    """A shop ware's place byte: ShopBoughtFlags + position, bit 1 << shop number."""
    return WARE_PLACE | position << WARE_POSITION_SHIFT | shop_number


def table_bytes(areas: Sequence[CounterArea]) -> bytes:
    """The seed's table: an offset per area, then each area's block."""
    if len(areas) != AREAS:
        raise ValueError(f"the table holds {AREAS} areas, not {len(areas)}")
    blocks = bytearray()
    offsets = []
    for area in areas:
        if area.total > DISPLAY_LIMIT:
            raise ValueError(f"an area of {area.total} places")
        if any(not 0 <= place < WARE_PLACE + (1 << (WARE_POSITION_SHIFT + 2)) for place in area.places):
            raise ValueError(f"a place byte out of range: {area}")
        offsets.append(AREAS + len(blocks))
        blocks += bytes([area.flags_address & 0xFF, area.flags_address >> 8, len(area.places)])
        blocks += bytes(area.places)
    table = bytes(offsets) + bytes(blocks)
    if len(table) > TABLE_SIZE:
        raise ValueError(f"the table takes {len(table)} bytes, more than its {TABLE_SIZE}")
    return table


def item_counter_writes(table: bytes) -> list[tuple[int, bytes]]:
    """The chest and slash tiles and the seed's table, as (file offset, bytes)."""
    return [(COMMON_BACKGROUND + CHEST_TILE * TILE_BYTES, tile_bytes(CHEST)),
            (COMMON_BACKGROUND + SLASH_TILE * TILE_BYTES, tile_bytes(SLASH)), (TABLE, table)]
