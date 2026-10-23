"""The underworld room layouts' floors, square by square, as the game draws them (aldonunez
`LayoutUWFloor`, bank 5): each of the 42 layouts is 12 column descriptors in `RoomLayoutsUW`, a
descriptor's high nibble picks one of the ten column heaps in `ColumnDirectoryUW` and its low
nibble the column there (the heap's columns each start with a byte whose bit 7 is set). A
column is 7 squares from the top: each square descriptor's low three bits pick one of the eight
`PrimarySquaresUW` tiles, and bits 6-4 repeat it that many more times. No ZORA patch writes any
of these bytes, and PRG1 has them at the same offsets.

Read by tests/test_item_spots.py, which keeps zora/generate/item_spots.py's table of the squares
equal to the player's ROM's."""
# File offsets (iNES header included) in PRG0 and PRG1
ROOM_LAYOUTS_UW = 0x160EE
COLUMN_DIRECTORY_UW = 0x16714
PRIMARY_SQUARES_UW = 0x16728
BANK_5_FILE = 0x14010            # bank 5's $8000
CPU_BANK_START = 0x8000

UW_LAYOUTS = 42                  # room types $00-$29
UW_COLUMNS = 12
UW_ROWS = 7
COLUMN_HEAPS = 10
PRIMARY_SQUARES = 8
SQUARE_INDEX_MASK = 0x07
SQUARE_REPEAT_MASK = 0x70
SQUARE_REPEAT_SHIFT = 4
COLUMN_START_BIT = 0x80
HEAP_NIBBLE_SHIFT = 4
COLUMN_NIBBLE_MASK = 0x0F

# A layout's floor: columns[column][row], each the square's tile ($74 floor, $B0 block, ...)
Floor = tuple[tuple[int, ...], ...]


def _heap_file_offset(rom: bytes, heap: int) -> int:
    at = COLUMN_DIRECTORY_UW + 2 * heap
    return (rom[at] | rom[at + 1] << 8) - CPU_BANK_START + BANK_5_FILE


def _column(rom: bytes, descriptor: int, squares: bytes) -> tuple[int, ...]:
    """One column's 7 square tiles from its descriptor."""
    at = _heap_file_offset(rom, descriptor >> HEAP_NIBBLE_SHIFT)
    starts_left = descriptor & COLUMN_NIBBLE_MASK
    while not (rom[at] & COLUMN_START_BIT and starts_left == 0):
        if rom[at] & COLUMN_START_BIT:
            starts_left -= 1
        at += 1
    tiles: list[int] = []
    repeated = 0
    while len(tiles) < UW_ROWS:
        square = rom[at]
        tiles.append(squares[square & SQUARE_INDEX_MASK])
        if (square & SQUARE_REPEAT_MASK) >> SQUARE_REPEAT_SHIFT == repeated:
            repeated = 0
            at += 1
        else:
            repeated += 1
    return tuple(tiles)


def underworld_floors(rom: bytes) -> dict[int, Floor]:
    """Every underworld layout's floor, by room type."""
    squares = rom[PRIMARY_SQUARES_UW:PRIMARY_SQUARES_UW + PRIMARY_SQUARES]
    return {layout: tuple(_column(rom, rom[ROOM_LAYOUTS_UW + layout * UW_COLUMNS + column], squares)
                          for column in range(UW_COLUMNS))
            for layout in range(UW_LAYOUTS)}
