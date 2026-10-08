"""Hint assignment, B2.5 (post-shapes-b25.md PS-HINT-01..06)."""
from zora.model.enums import BossSpriteSet, Direction, Enemy, EnemySpriteSet, RoomType, UnderworldPersonInit
from zora.model.rooms import EnemyInfo, LayoutInfo
from zora.model.levels import Level, LevelBlock
from zora.generate.steps.assign_hints_for_hint_type import (
    HintAssignmentResult, assign_hints_for_hint_type, balance_levels, move_helpful_markers,
)

PERSON = 0x40                    # the person flag in an enemy code


def _level(num: int, block: LevelBlock, room_nums: list[int]) -> Level:
    return Level(
        level_num=num, entrance_room=room_nums[0] if room_nums else 0,
        entrance_direction=Direction.SOUTH, palette_raw=b"", fade_palette_raw=b"",
        staircase_room_pool=[], room_nums=room_nums, staircase_nums=[],
        block=block, boss_room=0xFF,
        enemy_sprite_set=EnemySpriteSet.A, boss_sprite_set=BossSpriteSet.A, start_y=0,
        item_position_table=[0] * 4, map_start=0, map_cursor_offset=0,
        map_data=b"", map_ppu_commands=b"", qty_table=[0, 2, 4, 8],
        stairway_data_raw=b"",
    )


def _levels(persons: dict[int, list[int]]) -> list[Level]:
    """Nine levels in one block; persons: level -> monster lists, one
    flagged Black room each (count index 2), placed in scan order."""
    block = LevelBlock.blank()
    owned: dict[int, list[int]] = {level: [] for level in range(1, 10)}
    cell = 0
    for level in sorted(persons):
        for code in persons[level]:
            room = block.room(cell)
            room.layout_info = LayoutInfo(RoomType.BLACK_ROOM)
            room.enemy_info = EnemyInfo(Enemy(PERSON | code), count_index=2)
            owned[level].append(cell)
            cell += 1
    return [_level(level, block, cells) for level, cells in owned.items()]


def test_marker_moves_within_its_half_and_skips_the_previous_entry() -> None:
    state = HintAssignmentResult(helpful={3, 4, 6, 8}, old_man_levels=[3, 8])
    move_helpful_markers(state)
    # 3 moves its marker to 1; 8 scans from 5: 5 is free (not 8, not 3)
    assert state.helpful == {1, 4, 5, 6}
    state = HintAssignmentResult(helpful={3, 4, 6, 8}, old_man_levels=[5, 6])
    move_helpful_markers(state)
    # 5 is unhelpful already; 6 scans from 5 but 5 is the previous entry
    assert state.helpful == {3, 4, 7, 8}


def test_repeated_old_man_level_moves_once() -> None:
    state = HintAssignmentResult(helpful={3, 4, 6, 8}, old_man_levels=[4, 4])
    move_helpful_markers(state)
    assert state.helpful == {1, 3, 6, 8}


def test_balance_flips_toward_five_or_six() -> None:
    counts = {level: 1 for level in range(1, 9)}
    counts[5] = 3
    state = HintAssignmentResult(helpful={3, 4, 6, 8})
    balance_levels(state, counts)                   # 1+1+3+1 = 6 already
    assert state.helpful == {3, 4, 6, 8}
    counts[7] = 3                                   # 8: flip the lowest unhelpfuls
    state = HintAssignmentResult(helpful={3, 4, 6, 8})
    balance_levels(state, counts)
    assert state.helpful == {1, 2, 3, 4, 6, 8}     # 8 -> 7 -> 6
    counts = {level: 1 for level in range(1, 9)}    # 4: flip level 2..8's first helpful
    state = HintAssignmentResult(helpful={3, 4, 6, 8})
    balance_levels(state, counts)
    assert state.helpful == {4, 6, 8}


def test_counters_skip_their_reserved_values() -> None:
    # levels 3/4/6/8 helpful: seven helpful rooms, six unhelpful (1,2,5,7)
    levels = _levels({3: [0x0D] * 4, 4: [0x0D] * 3, 1: [0x0D] * 2, 2: [0x0D] * 2,
                      5: [0x0D], 7: [0x0D]})
    state = assign_hints_for_hint_type(levels, None)
    by_level = {level.level_num: [room.monster_byte for room in level.rooms] for level in levels}
    assert by_level[3] + by_level[4] == [0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x12]
    assert by_level[1] + by_level[2] + by_level[5] + by_level[7] == [0x0B, 0x0C, 0x0D, 0x0E, 0x10, 0x12]
    assert all(room.has_monster_bit for level in levels for room in level.rooms)
    assert state.person_inits()[2] == UnderworldPersonInit.B


def test_merchants_level9_and_kept_bomb_rooms_are_untouched() -> None:
    levels = _levels({1: [0x11], 5: [0x0F], 9: [0x0C]})
    state = assign_hints_for_hint_type(levels, (5, 5))
    codes = [levels[0].block.room(cell).monster_list for cell in range(3)]
    assert codes == [0x11, 0x0F, 0x0C]
    assert state.old_man_levels == [5]
    assert state.listed == 0
