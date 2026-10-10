"""The level block's room grid (SH-GRID-01): 16 columns by 8 rows, row 7
at the bottom; a room's number is row * 16 + column."""
from .enums import ROOMS_PER_ROW, Side

COLUMNS = ROOMS_PER_ROW
ROWS = 8
ROOMS = COLUMNS * ROWS


def row(room_number: int) -> int:
    return room_number // COLUMNS


def column(room_number: int) -> int:
    return room_number % COLUMNS


def room_number(row: int, column: int) -> int:
    return row * COLUMNS + column


def _neighbour_on_grid(room_number: int, side: Side) -> int | None:
    """The room next to this one on the side, or None past the grid's edge."""
    grid_row, grid_column = row(room_number), column(room_number)
    if side == Side.NORTH and grid_row == 0:
        return None
    if side == Side.SOUTH and grid_row == ROWS - 1:
        return None
    if side == Side.WEST and grid_column == 0:
        return None
    if side == Side.EAST and grid_column == COLUMNS - 1:
        return None
    return room_number + side.delta


# neighbour() is called ~30M times per 200 seeds: the block's rooms are
# served from a precomputed table (the same values as _neighbour_on_grid).
_NEIGHBOURS: tuple[tuple[int | None, ...], ...] = tuple(
    tuple(_neighbour_on_grid(number, side) for side in Side) for number in range(ROOMS)
)


def neighbour(room_number: int, side: Side) -> int | None:
    """The room next to this one on the side, or None at the grid's edge."""
    if 0 <= room_number < ROOMS:
        return _NEIGHBOURS[room_number][side]
    return _neighbour_on_grid(room_number, side)


def step(room_number: int, side: Side) -> int | None:
    """Quirk (A26): one room-number step to the side with no row check, so
    east of room 15 is room 16; None only off the top or bottom of the
    block."""
    stepped = room_number + side.delta
    return stepped if 0 <= stepped < ROOMS else None
