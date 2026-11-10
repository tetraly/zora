"""Item Counter (the ZORA flag item_counter; idea: Ultralavos): the ROM side of asm/flags2/item-counter.

The patch shows a chest and found/total on the status bar row under the rupees. Two blank tiles of
CommonBackgroundPatterns, $50 and $51 (blank in PRG0 and in every ZORA build: the boss expansion ends at
$4F), become the chest and the slash; the digits and A-F are the font's own tiles $00-$0F. The seed's table
(asm/rom_space.toml site "item-counter-table", bank 5 $BA40-$BABF) lists each area's places as the patch
reads them (asm/flags2/item-counter/bank_05.s); zora/generate/item_counter.py says which places count.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .layout import BOSS_SET_EXPANSION_SPRITES_ADDRESS

TABLE = 0x17A50                         # bank 5 $BA40
TABLE_SIZE = 0x80
AREAS = 10                              # 0 the overworld, 1-9 the levels
BLOCK_HEADER = 5                        # flags address (low, high), U, G, K
PLACE_LIMIT = 0x80                      # a room, cellar or screen number is below it
WARE_PLACE = 0x80                       # a shop ware: %100PPSSS
WARE_POSITION_SHIFT = 3
DISPLAY_LIMIT = 0x0F                    # the font's F: a count or total above it cannot be shown

# CommonBackgroundPatterns starts 768 bytes before the boss expansion that reuses it (model/sprites.py).
COMMON_BACKGROUND = BOSS_SET_EXPANSION_SPRITES_ADDRESS - 0x300
TILE_BYTES = 16
CHEST_TILE = 0x50
SLASH_TILE = 0x51

# The status bar's colors in the icons' column: 0 black, 1 white, 2 orange, 3 peach (as the rupee's).
COLORS = {".": 0, "W": 1, "O": 2, "P": 3}
CHEST = (
    "........",
    ".PPPPPP.",
    "POOOOOOP",
    "........",
    "POOWWOOP",
    "POOW.OOP",
    "PPPPPPPP",
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
    """One area's block: its room flags' address, the places that count one each (`unique`), and a group
    of which at most `cap` count (`group`: heart containers that only partly count)."""
    flags_address: int
    unique: tuple[int, ...] = ()
    group: tuple[int, ...] = ()
    cap: int = 0

    @property
    def total(self) -> int:
        return len(self.unique) + self.cap


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
        if area.total > DISPLAY_LIMIT or not 0 <= area.cap <= len(area.group):
            raise ValueError(f"an area of {area.total} places (cap {area.cap} of {len(area.group)})")
        if any(not 0 <= place < WARE_PLACE + (1 << (WARE_POSITION_SHIFT + 2)) for place in area.unique + area.group):
            raise ValueError(f"a place byte out of range: {area}")
        offsets.append(AREAS + len(blocks))
        blocks += bytes([area.flags_address & 0xFF, area.flags_address >> 8, len(area.unique), len(area.group),
                         area.cap])
        blocks += bytes(area.unique + area.group)
    table = bytes(offsets) + bytes(blocks)
    if len(table) > TABLE_SIZE:
        raise ValueError(f"the table takes {len(table)} bytes, more than its {TABLE_SIZE}")
    return table


def item_counter_writes(table: bytes) -> list[tuple[int, bytes]]:
    """The chest and slash tiles and the seed's table, as (file offset, bytes)."""
    return [(COMMON_BACKGROUND + CHEST_TILE * TILE_BYTES, tile_bytes(CHEST)),
            (COMMON_BACKGROUND + SLASH_TILE * TILE_BYTES, tile_bytes(SLASH)),
            (TABLE, table)]
