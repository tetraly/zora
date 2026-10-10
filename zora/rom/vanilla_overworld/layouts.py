"""Overworld screen layouts: RoomLayoutsOW's column descriptors decoded
into squares through ColumnDirectoryOW and the column heaps (read-only).

LayoutRoomOrCaveOW, per column descriptor:
  - bits 4-7 pick a column heap (ColumnHeapOW0-F, via ColumnDirectoryOW);
    bits 0-3 pick the column within it: the heap is scanned for bytes with
    bit 7 set, each of which starts a column;
  - from there, each square descriptor gives a square index (bits 0-5);
    bit 6 means the square fills two rows; a column is $B rows tall.
A square index below $10 draws the four tiles listed in SecondarySquaresOW;
from $10 up it draws its PrimarySquaresOW tile and the next three tiles.

These are the stored layouts. The game changes some squares while drawing,
which this reader does not: once a room's secret is found, a tree ($E7)
or armos ($EA) square becomes stairs and a rock wall ($E6) a cave entrance;
CheckTileObject turns tile-object squares into their objects.
"""
from .tables import (
    CAVE_LAYOUT_COUNT,
    COLUMN_DIRECTORY_OW,
    COLUMN_HEAP_BANK,
    INES_HEADER_SIZE,
    LAYOUT_COLUMNS,
    OW_LAYOUT_COUNT,
    PRIMARY_SQUARES_OW,
    ROOM_LAYOUTS_OW,
    ROOM_LAYOUTS_OW_CAVE,
    SECONDARY_SQUARES_OW,
    cpu_to_prg,
)

SQUARE_ROWS = 0x0B
HEAP_SHIFT = 4
COLUMN_INDEX_MASK = 0x0F
COLUMN_START_BIT = 0x80
REPEAT_BIT = 0x40
SQUARE_INDEX_MASK = 0x3F
FIRST_PRIMARY_SQUARE = 0x10       # below: secondary (four listed tiles)
TILES_PER_SQUARE = 4

# Primary squares LayoutRoomOrCaveOW rewrites once the room's secret is found.
SECRET_TREE = 0xE7
SECRET_ROCK_WALL = 0xE6
SECRET_ARMOS = 0xEA

Layout = list[list[int]]          # [column][row] square indices, 16 x 11


def _heap_starts(rom: bytes) -> list[int]:
    """Each column heap's file offset, from ColumnDirectoryOW's pointers."""
    directory = COLUMN_DIRECTORY_OW.read(rom)
    pointers = [directory[i] | directory[i + 1] << 8 for i in range(0, len(directory), 2)]
    return [cpu_to_prg(COLUMN_HEAP_BANK, pointer) + INES_HEADER_SIZE for pointer in pointers]


def _column(rom: bytes, heap_start: int, column_index: int) -> list[int]:
    """One column's 11 square indices (LayoutRoomOrCaveOW's two loops)."""
    position = heap_start - 1
    for _ in range(column_index + 1):              # the (index+1)-th column start
        position += 1
        while not rom[position] & COLUMN_START_BIT:
            position += 1
    squares: list[int] = []
    repeating = False
    while len(squares) < SQUARE_ROWS:
        descriptor = rom[position]
        squares.append(descriptor & SQUARE_INDEX_MASK)
        if descriptor & REPEAT_BIT:
            repeating = not repeating
            if repeating:
                continue                           # the same descriptor fills the next row
        position += 1
    return squares


def _decode(rom: bytes, descriptors: bytes) -> Layout:
    heaps = _heap_starts(rom)
    return [_column(rom, heaps[d >> HEAP_SHIFT], d & COLUMN_INDEX_MASK) for d in descriptors]


def read_layout(rom: bytes, layout: int) -> Layout:
    """Screen layout 0-120 as 16 columns of 11 square indices."""
    assert 0 <= layout < OW_LAYOUT_COUNT
    table = ROOM_LAYOUTS_OW.read(rom)
    return _decode(rom, table[layout * LAYOUT_COLUMNS:(layout + 1) * LAYOUT_COLUMNS])


def read_cave_layout(rom: bytes, cave_layout: int) -> Layout:
    """RoomLayoutOWCave0-2 decoded the same way."""
    assert 0 <= cave_layout < CAVE_LAYOUT_COUNT
    table = ROOM_LAYOUTS_OW_CAVE.read(rom)
    return _decode(rom, table[cave_layout * LAYOUT_COLUMNS:(cave_layout + 1) * LAYOUT_COLUMNS])


def primary_squares(rom: bytes) -> bytes:
    """Square index -> its primary tile (PrimarySquaresOW)."""
    return PRIMARY_SQUARES_OW.read(rom)


def square_tiles(rom: bytes, square_index: int) -> tuple[int, int, int, int]:
    """WriteSquareOW's four tiles: (top left, bottom left, top right,
    bottom right)."""
    if square_index < FIRST_PRIMARY_SQUARE:
        secondary = SECONDARY_SQUARES_OW.read(rom)
        start = square_index * TILES_PER_SQUARE
        a, b, c, d = secondary[start:start + TILES_PER_SQUARE]
        return a, b, c, d
    primary = primary_squares(rom)[square_index]
    return primary, primary + 1, primary + 2, primary + 3
