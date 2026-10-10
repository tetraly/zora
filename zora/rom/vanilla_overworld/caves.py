"""Cave and shop contents: the 20 cave dwellers' wares, prices and flags
(read-only).

InitCave / InitCaveContinue (Z_01.asm), for cave index i (object type
$6A + i, the screen's cave value minus $10):
  - three ware bytes at LevelBlockAttrsE + 3i: item id in bits 0-5 ($3F:
    nothing), two cave flags in bits 6-7;
  - three prices at LevelBlockAttrsE + 60 + 3i;
  - OverworldPersonTextSelectors[i]: text selector in bits 0-5, two more
    cave flags in bits 6-7.
In the overworld, LevelBlockAttrsE is LevelBlockOW's fifth table, so the
wares sit at LevelBlockOW + $200 and the prices at + $23C.

The eight flags combine into CaveFlags:
  bit 0 choose / pick up    <- text selector bit 6
  bit 1 pay                 <- text selector bit 7
  bit 2 show items          <- ware 2 bit 6
  bit 3 show prices         <- ware 2 bit 7
  bit 4 hint                <- ware 1 bit 6
  bit 5 money game          <- ware 1 bit 7
  bit 6 heart requirement   <- ware 0 bit 6
  bit 7 negative amounts    <- ware 0 bit 7
Prices are single bytes (FormatDecimalByte); 0 draws no price. Object types
$6E-$7A, other than $71 and $72, forget their state (InitCave's
@TakeType test); the others remember whether their item was taken.
"""
from dataclasses import dataclass
from enum import IntFlag

from .tables import (
    ATTRIBUTE_TABLE_SIZE,
    CAVE_COUNT,
    LEVEL_BLOCK_OW,
    OVERWORLD_PERSON_TEXT_SELECTORS,
    WARES_PER_CAVE,
)

WARES_TABLE = 4                   # LevelBlockAttrsE
PRICES_OFFSET = 60                # LevelBlockAttrsE + 60
ITEM_ID_MASK = 0x3F
NO_ITEM = 0x3F
WARE_FLAGS_MASK = 0xC0
TEXT_SELECTOR_MASK = 0x3F
CAVE_DWELLER_BASE = 0x6A
# InitCave's @TakeType test: these dwellers keep no taken state
FORGETFUL_TYPES = frozenset(range(0x6E, 0x7B)) - {0x71, 0x72}


class CaveFlags(IntFlag):
    CHOOSE = 0x01
    PAY = 0x02
    SHOW_ITEMS = 0x04
    SHOW_PRICES = 0x08
    HINT = 0x10
    MONEY_GAME = 0x20
    HEART_REQUIREMENT = 0x40
    NEGATIVE_AMOUNTS = 0x80


def _cave_flags(ware_bytes: bytes, text_selector_byte: int) -> CaveFlags:
    """InitCaveContinue's combination of the four two-bit fields."""
    selector_bits = (text_selector_byte & WARE_FLAGS_MASK) >> 6
    ware0, ware1, ware2 = (ware & WARE_FLAGS_MASK for ware in ware_bytes)
    return CaveFlags(ware0 | ware1 >> 2 | ware2 >> 4 | selector_bits)


@dataclass(frozen=True)
class Cave:
    index: int                       # 0-19
    ware_bytes: bytes                # as stored, flags included
    prices: tuple[int, int, int]
    text_selector_byte: int

    @property
    def object_type(self) -> int:
        return CAVE_DWELLER_BASE + self.index

    @property
    def remembers_taken(self) -> bool:
        """Whether the dweller vanishes once its item is taken (InitCave)."""
        return self.object_type not in FORGETFUL_TYPES

    @property
    def item_ids(self) -> tuple[int, int, int]:
        """The three item ids; NO_ITEM ($3F) is an empty slot."""
        a, b, c = (ware & ITEM_ID_MASK for ware in self.ware_bytes)
        return a, b, c

    @property
    def text_selector(self) -> int:
        return self.text_selector_byte & TEXT_SELECTOR_MASK

    @property
    def flags(self) -> CaveFlags:
        return _cave_flags(self.ware_bytes, self.text_selector_byte)


def read_caves(rom: bytes) -> list[Cave]:
    block = LEVEL_BLOCK_OW.read(rom)
    table_e = block[WARES_TABLE * ATTRIBUTE_TABLE_SIZE:(WARES_TABLE + 1) * ATTRIBUTE_TABLE_SIZE]
    selectors = OVERWORLD_PERSON_TEXT_SELECTORS.read(rom)
    caves = []
    for index in range(CAVE_COUNT):
        start = index * WARES_PER_CAVE
        a, b, c = table_e[PRICES_OFFSET + start:PRICES_OFFSET + start + WARES_PER_CAVE]
        caves.append(Cave(index, bytes(table_e[start:start + WARES_PER_CAVE]), (a, b, c),
                          selectors[index]))
    return caves
