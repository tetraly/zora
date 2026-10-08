"""The level block's room grid (zora/model/room_grid.py)."""
from zora.model import room_grid
from zora.model.enums import Side
from zora.model.room_grid import neighbour


def test_rows_columns_and_room_numbers() -> None:
    assert (room_grid.row(0x7A), room_grid.column(0x7A)) == (7, 0x0A)
    assert room_grid.room_number(7, 0x0A) == 0x7A


def test_neighbour_stops_at_the_grid_edge() -> None:
    assert neighbour(0x00, Side.NORTH) is None
    assert neighbour(0x7F, Side.SOUTH) is None
    assert neighbour(0x70, Side.WEST) is None
    assert neighbour(0x0F, Side.EAST) is None
    assert neighbour(0x70, Side.NORTH) == 0x60
    for number in range(room_grid.ROOMS):
        for side in Side:
            other = neighbour(number, side)
            assert other is None or neighbour(other, side.opposite) == number


def test_step_crosses_rows_but_not_the_block_edge() -> None:
    """Quirk (A26): east of room 15 is room 16."""
    assert room_grid.step(0x0F, Side.EAST) == 0x10
    assert room_grid.step(0x10, Side.WEST) == 0x0F
    assert room_grid.step(0x05, Side.NORTH) is None
    assert room_grid.step(0x7F, Side.EAST) is None
