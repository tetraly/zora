from pathlib import Path

from zora.data_model import RoomType, WallType
from zora.dungeon.shuffle_dungeon_rooms import shuffle_dungeon_rooms, _is_level_connected
from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng

TEST_DATA = Path(__file__).parent.parent / "rom_data"

SEED = 3233987923


def _parse():
    return parse_game_world(load_bin_files(TEST_DATA))


def _rooms_with_stairway(level):
    result = []
    for room in level.rooms:
        if room.room_type.has_open_staircase():
            result.append(room.room_num)
        elif room.room_type.can_have_push_block() and room.movable_block:
            result.append(room.room_num)
    return set(result)


def test_staircase_refs_point_to_stairway_rooms():
    """After shuffling, every staircase return_dest/left_exit/right_exit
    must point to a room that actually has a stairway (open staircase or
    push block).  This is the regression that caused unreachable items."""
    gw = _parse()
    rng = SeededRng(SEED)
    assert shuffle_dungeon_rooms(gw, rng)

    for level in gw.levels:
        stairway_rooms = _rooms_with_stairway(level)
        for sr in level.staircase_rooms:
            if sr.room_type == RoomType.ITEM_STAIRCASE:
                assert sr.return_dest in stairway_rooms, (
                    f"L{level.level_num} ITEM_STAIRCASE {sr.room_num:#04x}: "
                    f"return_dest {sr.return_dest:#04x} has no stairway. "
                    f"Stairway rooms: {[hex(r) for r in sorted(stairway_rooms)]}"
                )
            else:
                assert sr.left_exit in stairway_rooms, (
                    f"L{level.level_num} TRANSPORT {sr.room_num:#04x}: "
                    f"left_exit {sr.left_exit:#04x} has no stairway. "
                    f"Stairway rooms: {[hex(r) for r in sorted(stairway_rooms)]}"
                )
                assert sr.right_exit in stairway_rooms, (
                    f"L{level.level_num} TRANSPORT {sr.room_num:#04x}: "
                    f"right_exit {sr.right_exit:#04x} has no stairway. "
                    f"Stairway rooms: {[hex(r) for r in sorted(stairway_rooms)]}"
                )


def test_staircase_refs_valid_across_seeds():
    """Staircase refs must remain valid across multiple seeds."""
    for seed in range(100):
        gw = _parse()
        rng = SeededRng(seed)
        assert shuffle_dungeon_rooms(gw, rng), f"shuffle failed for seed {seed}"

        for level in gw.levels:
            stairway_rooms = _rooms_with_stairway(level)
            for sr in level.staircase_rooms:
                if sr.room_type == RoomType.ITEM_STAIRCASE:
                    assert sr.return_dest in stairway_rooms, (
                        f"seed {seed} L{level.level_num}: "
                        f"return_dest {sr.return_dest:#04x} not in stairway rooms"
                    )
                else:
                    assert sr.left_exit in stairway_rooms, (
                        f"seed {seed} L{level.level_num}: "
                        f"left_exit {sr.left_exit:#04x} not in stairway rooms"
                    )
                    assert sr.right_exit in stairway_rooms, (
                        f"seed {seed} L{level.level_num}: "
                        f"right_exit {sr.right_exit:#04x} not in stairway rooms"
                    )


def test_all_levels_connected():
    """After shuffling, every room in each level must be reachable from
    the entrance via non-solid walls and transport staircases."""
    for seed in range(100):
        gw = _parse()
        rng = SeededRng(seed)
        assert shuffle_dungeon_rooms(gw, rng), f"shuffle failed for seed {seed}"

        for level in gw.levels:
            assert _is_level_connected(level), (
                f"seed {seed} L{level.level_num}: level is not fully connected"
            )


def test_staircase_refs_unchanged_without_shuffle():
    """Without shuffling, staircase refs should match vanilla positions."""
    gw = _parse()
    for level in gw.levels:
        stairway_rooms = _rooms_with_stairway(level)
        for sr in level.staircase_rooms:
            if sr.room_type == RoomType.ITEM_STAIRCASE:
                assert sr.return_dest in stairway_rooms, (
                    f"Vanilla L{level.level_num}: return_dest {sr.return_dest:#04x} "
                    f"not in stairway rooms (parser bug?)"
                )
            else:
                assert sr.left_exit in stairway_rooms, (
                    f"Vanilla L{level.level_num}: left_exit {sr.left_exit:#04x} "
                    f"not in stairway rooms (parser bug?)"
                )
                assert sr.right_exit in stairway_rooms, (
                    f"Vanilla L{level.level_num}: right_exit {sr.right_exit:#04x} "
                    f"not in stairway rooms (parser bug?)"
                )
