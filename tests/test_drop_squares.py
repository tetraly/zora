"""Universal Drops v2.0' drop squares (zora/generate/drop_squares.py): the written table is the
model's, and the model says what the research measured (docs/reports/research-universal-drops-balance.md
sections 3.3, 5.2 and 5.3); the finished-world check rejects an item off its screen type's squares.

The model's inferences (door squares, the ladder, the push block) are checked in the emulator:
tests/test_drop_squares_emulator.py."""
from dataclasses import replace

import pytest

from scripts.make_drop_square_table import TABLE, table_source
from tests.needs import needs_base_rom
from zora.generate.drop_square_table import DROP_SQUARES
from zora.generate.drop_squares import (
    DROP_SQUARE_FAILURE,
    check_drop_squares,
    drop_squares,
    misplaced_drops,
    model_drop_squares,
    push_block_square,
)
from zora.generate.errors import GenerationFailure
from zora.generate.item_spots import FLOORS
from zora.generate.shapes.t5_positions import T5_BASE, T5_UNIVERSAL, t5_row
from zora.model.enums import Item, RoomType
from zora.model.rooms import PUSH_BLOCK_VARIANT
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

SCREEN_TYPES = sorted({*FLOORS, *(layout | PUSH_BLOCK_VARIANT for layout in FLOORS)})
CENTER = 0x89
CORNERS = {0x26, 0xD6, 0x2C, 0xDC}
ALL_SQUARES = 12 * 7


def test_the_table_is_the_models() -> None:
    assert TABLE.read_text() == table_source(), "rerun scripts/make_drop_square_table.py"
    for screen_type in SCREEN_TYPES:
        assert drop_squares(screen_type) == model_drop_squares(screen_type), f"${screen_type:02X}"
    assert set(DROP_SQUARES) <= set(SCREEN_TYPES)


def test_every_t5_square_is_a_drop_square() -> None:
    """Every square the spec's T5 lets a screen type hold, base or universal, is in the table."""
    for screen_type in set(T5_BASE) | set(T5_UNIVERSAL):
        assert set(t5_row(screen_type, True)) <= drop_squares(screen_type), f"${screen_type:02X}"


@pytest.mark.parametrize(("layout", "count"), [
    (RoomType.PLAIN_ROOM, ALL_SQUARES), (RoomType.CHEVY_ROOM, 80), (RoomType.CIRCLE_WALL, 44),
    (RoomType.NSU, 38), (RoomType.VERTICAL_CHUTE_ROOM, 14), (RoomType.HORIZONTAL_CHUTE_ROOM, 12),
    (RoomType.TURNSTILE_ROOM, 0)])
def test_the_measured_counts(layout: int, count: int) -> None:
    """The research's full-square table (section 5.3)."""
    assert len(drop_squares(layout)) == count


def test_water_holds_an_item_only_in_a_ladder_layout() -> None:
    # vertical moat (ladder): every square, the water column included; pointless moat (no ladder): none of its water
    assert len(drop_squares(RoomType.VERTICAL_MOAT_ROOM)) == ALL_SQUARES
    pointless = FLOORS[RoomType.POINTLESS_MOAT_ROOM]
    water = {(column + 2) << 4 | (row + 6) for row, line in enumerate(pointless)
             for column, kind in enumerate(line) if kind == "~"}
    assert water and not water & drop_squares(RoomType.POINTLESS_MOAT_ROOM)


def test_the_circle_wall_holds_items_outside_its_ring_only() -> None:
    squares = drop_squares(RoomType.CIRCLE_WALL)
    assert CORNERS <= squares and CENTER not in squares
    assert {0x76, 0x86, 0x29, 0xD9, 0x7C, 0x8C} <= squares       # the wall middles


def test_a_chute_holds_items_inside_it_only() -> None:
    # the vertical chute's floor between its block walls: columns X $7-$8
    assert {square >> 4 for square in drop_squares(RoomType.VERTICAL_CHUTE_ROOM)} == {0x7, 0x8}
    assert {square & 0xF for square in drop_squares(RoomType.HORIZONTAL_CHUTE_ROOM)} == {0x9}


def test_a_push_block_room_loses_its_blocks_square_and_where_it_slides() -> None:
    single = RoomType.SINGLE_BLOCK_ROOM
    block = push_block_square(single)
    assert block == 0x79                                         # one left of the center
    assert drop_squares(single | PUSH_BLOCK_VARIANT) == drop_squares(single) - {block, 0x69, 0x89, 0x78, 0x7A}
    # the diamond stair room's push block (two left of center, $69) can slide onto three of its squares:
    # three left of center ($59), two left one up ($68) and two left one down ($6A); the fourth, one left
    # of center ($79), is inside the diamond, which no door reaches
    diamond = RoomType.DIAMOND_STAIR_ROOM
    assert drop_squares(diamond) - drop_squares(diamond | PUSH_BLOCK_VARIANT) == {0x59, 0x68, 0x6A}
    assert push_block_square(RoomType.PLAIN_ROOM) == 0xD9        # no block in the middle row


def test_the_narrow_stair_and_zelda_rooms_keep_t5_rows() -> None:
    for layout in (RoomType.NARROW_STAIR_ROOM, RoomType.ZELDA_ROOM):
        assert drop_squares(layout) == set(t5_row(layout, True))


@needs_base_rom
def test_the_original_games_items() -> None:
    """Every first-quest item stands on a drop square; three second-quest items stand outside a
    chute, the case the community report described (level 3 room $2A at five left two up, $37;
    level 6 room $34 at four left, $49; level 9 room $55 at top row three right, $B6)."""
    world = parse_rom(remember_repo_base_rom())
    assert misplaced_drops(world.levels) == []
    outside = [(level.level_num, room_num) for level, room_num in misplaced_drops(world.levels_2q)]
    assert outside == [(3, 0x2A), (6, 0x34), (9, 0x55)]
    for level, room_num in misplaced_drops(world.levels_2q):
        assert level.block.room(room_num).layout_code in (RoomType.VERTICAL_CHUTE_ROOM,
                                                           RoomType.HORIZONTAL_CHUTE_ROOM)


@needs_base_rom
def test_the_check_rejects_an_item_off_its_squares() -> None:
    world = parse_rom(remember_repo_base_rom())
    check_drop_squares(world.levels)
    level = world.levels[0]
    room = next(room for room in level.rooms if room.item != Item.NOTHING)
    room.layout_info = replace(room.layout_info, room_type=RoomType.TURNSTILE_ROOM)   # no drop squares
    with pytest.raises(GenerationFailure, match=DROP_SQUARE_FAILURE):
        check_drop_squares(world.levels)
    room.item_info = replace(room.item_info, item=Item.NOTHING)  # an empty room is never checked
    check_drop_squares(world.levels)
