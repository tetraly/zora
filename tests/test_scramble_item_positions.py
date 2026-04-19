"""Regression test: scrambled dungeon rooms must not place items on walls.

After scramble_dungeon_rooms runs, every room's item_position must resolve
to coordinates that the game_validator considers valid for that room type.
This catches the bug where T_ROOM was assigned POSITION_C (X=0xC, Y=0x9),
which lands outside the T-room's walkable zones.
"""
from collections.abc import Callable

from zora.data_model import GameWorld, ItemPosition, RoomType
from zora.dungeon.scramble_dungeon_rooms import (
    _STANDARD_ITEM_POSITION_TABLE,
    _VALID_ITEM_POSITIONS,
    _assign_valid_item_positions,
    scramble_dungeon_rooms,
)
from zora.dungeon.shuffle_dungeon_rooms import shuffle_dungeon_rooms
from zora.parser import parse_game_world
from zora.rng import SeededRng


def _unpack(pos: ItemPosition) -> tuple[int, int]:
    packed = _STANDARD_ITEM_POSITION_TABLE[pos]
    return (packed >> 4) & 0x0F, packed & 0x0F


# -- Static check: every position in _VALID_ITEM_POSITIONS must land in a
#    zone that the validator recognises for that room type. --

_ZONE_CHECKS: dict[RoomType, Callable[[int, int], bool]] = {
    RoomType.HORIZONTAL_CHUTE_ROOM: lambda x, y: (
        y in (0x6, 0x7) or y == 0x9 or y in (0xB, 0xC)
    ),
    RoomType.VERTICAL_CHUTE_ROOM: lambda x, y: (
        0x2 <= x <= 0x5 or x in (0x7, 0x8) or 0xA <= x <= 0xD
    ),
    RoomType.T_ROOM: lambda x, y: (
        x == 0x2 or x == 0xD or y == 0x6
        or (0x5 <= x <= 0xA and 0x8 <= y <= 0xC)
    ),
}


def test_valid_positions_table_matches_validator_zones():
    """Every position listed in _VALID_ITEM_POSITIONS must resolve to
    coordinates inside a zone the validator accepts for that room type."""
    for rt, zone_check in _ZONE_CHECKS.items():
        valid = _VALID_ITEM_POSITIONS.get(rt, [])
        for pos in valid:
            x, y = _unpack(pos)
            assert zone_check(x, y), (
                f"{rt.name} allows {pos.name} (X={x:#x}, Y={y:#x}) "
                f"which is not in any valid zone"
            )


def test_t_room_excludes_position_c():
    """POSITION_C (X=0xC, Y=0x9) must not be allowed for T_ROOM."""
    valid = _VALID_ITEM_POSITIONS[RoomType.T_ROOM]
    assert ItemPosition.POSITION_C not in valid


def _standardize_and_reassign(gw: GameWorld, rng: SeededRng) -> None:
    """Replicate the orchestrator's post-shuffle/scramble step."""
    for level in gw.levels:
        level.item_position_table = list(_STANDARD_ITEM_POSITION_TABLE)
    all_rooms = [room for level in gw.levels for room in level.rooms]
    _assign_valid_item_positions(all_rooms, rng)


def test_scramble_produces_valid_item_positions(bins):
    """After scrambling + standardization, every room's item_position must
    be in the valid set for its room type."""
    for seed in range(50):
        gw = parse_game_world(bins)
        rng = SeededRng(seed)
        scramble_dungeon_rooms(gw, rng, shuffle_gannon_and_zelda=False, shuffle_drops=True)
        _standardize_and_reassign(gw, rng)

        for level in gw.levels:
            for room in level.rooms:
                valid = _VALID_ITEM_POSITIONS.get(room.room_type)
                if valid is None:
                    continue
                assert room.item_position in valid, (
                    f"Seed {seed}, L{level.level_num} room {room.room_num:#04x} "
                    f"({room.room_type.name}): {room.item_position.name} not in "
                    f"valid set {[p.name for p in valid]}"
                )


def test_shuffle_produces_valid_item_positions(bins):
    """After shuffle + standardization, every room's item_position must
    be in the valid set for its room type."""
    for seed in range(50):
        gw = parse_game_world(bins)
        rng = SeededRng(seed)
        shuffle_dungeon_rooms(gw, rng)
        _standardize_and_reassign(gw, rng)

        for level in gw.levels:
            for room in level.rooms:
                valid = _VALID_ITEM_POSITIONS.get(room.room_type)
                if valid is None:
                    continue
                assert room.item_position in valid, (
                    f"Seed {seed}, L{level.level_num} room {room.room_num:#04x} "
                    f"({room.room_type.name}): {room.item_position.name} not in "
                    f"valid set {[p.name for p in valid]}"
                )
