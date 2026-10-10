"""Shuffle Bomb Upgrade Men (B29; PS-BOMB-01 to -03)."""

from ...model.levels import LEVEL_9, Level
from ...model.rooms import PERSON_LISTS, EnemyInfo, Room
from ..rng import IntRng, discard
from .item_shuffle_result import ItemShuffleResult, LevelRoom, _level_rooms

LEADING_DISCARDS = 2           # the bomb-upgrade move and PS-MERCH-04 each start with two discarded draws

BOMB_UPGRADE_CODE = 0x0F
BOMB_UPGRADE_LEVELS = (5, 7)     # PS-BOMB-01: the levels whose $0F persons are collected
STRAY_BOMB_UPGRADE_CODE = 0x0E   # PS-BOMB-01: an uncollected $0F becomes $0E


def shuffle_bomb_upgrade_men(levels: list[Level], state: ItemShuffleResult,
                             rng: IntRng) -> None:
    """PS-BOMB-01..03: collect the first two $0F person rooms of levels 5/7,
    rewrite every other $0F person to $0E, swap each collected room's
    monster byte with a uniform member of eligible + collected, and record
    the levels of the first two whole-$0F person cells in list order."""
    bombs: list[LevelRoom] = []
    eligible: list[LevelRoom] = []
    stray: list[Room] = []
    for level_room in _level_rooms(levels):
        room = level_room.room
        if not room.has_monster_bit:
            continue
        monster_list = room.monster_list
        level_num = level_room.level.level_num
        # A collected room goes to the bomb list ONLY; every other person
        # of levels 1-8, strays of $0F included, is eligible (QUESTIONS
        # #48.2: the reading that reproduces the corpus's operand levels).
        if monster_list == BOMB_UPGRADE_CODE and level_num in BOMB_UPGRADE_LEVELS and len(bombs) < 2:
            bombs.append(level_room)
            continue
        if monster_list == BOMB_UPGRADE_CODE:
            stray.append(room)
        if monster_list in PERSON_LISTS and level_num != LEVEL_9:
            eligible.append(level_room)
    for room in stray:                     # the whole monster byte -> $0E
        room.enemy_info = EnemyInfo(room.enemy_info.with_monster_list(STRAY_BOMB_UPGRADE_CODE).enemy)
    combined = eligible + bombs
    discard(rng, LEADING_DISCARDS)
    for position in range(len(eligible), len(combined)):
        pick = rng.below(len(combined))
        first, second = combined[position].room, combined[pick].room
        # the whole monster byte: list bits 0-5 and count bits 6-7; the
        # person flag is the layout byte's and stays with its cell
        first_byte, second_byte = first.enemy_info, second.enemy_info
        first.enemy_info = EnemyInfo(first_byte.with_monster_list(second_byte.monster_list).enemy,
                                     second_byte.count_index)
        second.enemy_info = EnemyInfo(second_byte.with_monster_list(first_byte.monster_list).enemy,
                                      first_byte.count_index)
        combined[position], combined[pick] = combined[pick], combined[position]
    # the first two such cells (a cell is listed once; dedupe is a guard)
    bomb_rooms = list({level_room.key: level_room for level_room in combined
                  if level_room.room.has_monster_bit
                  and level_room.room.monster_byte == BOMB_UPGRADE_CODE}.values())
    found = [level_room.level.level_num for level_room in bomb_rooms]
    if len(found) >= 2:
        state.bomb_levels = (found[0], found[1])
    elif found:
        state.bomb_levels = (found[0], found[0])   # QUESTIONS #48.2
