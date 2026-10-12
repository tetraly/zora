"""Dungeon quest (C02; shapes-behavior.md SH-SRC-01 to SH-SRC-10, post-shapes-b9.md PS-VAN):
which sets of levels are built by the shapes generator and which keep the first or second
quest's own dungeons, and what a vanilla set starts from before the later passes."""
import copy
from enum import Enum

from ...flags.fields import DungeonLayoutSource
from ...model.game_world import GameWorld
from ...model.levels import Level, LevelBlock
from ...model.rooms import ItemInfo
from ..rng import IntRng


class SetSource(Enum):
    """Where a set's levels come from (SH-SRC-01)."""
    FIRST_QUEST = "first quest"
    SECOND_QUEST = "second quest"
    SHAPES = "shapes"

    @property
    def is_vanilla(self) -> bool:
        return self is not SetSource.SHAPES


# The two sets: levels 1-6 and levels 7-9 (level 9 belongs to the second, SH-SRC-01)
SET_LEVELS = (range(1, 7), range(7, 10))
SetSources = tuple[SetSource, SetSource]
ALL_SHAPES: SetSources = (SetSource.SHAPES, SetSource.SHAPES)
# SH-SRC-01: C02 = 4 draws each set's source from these three until the two differ
MIXED_WITH_SHAPES_SOURCES = (SetSource.FIRST_QUEST, SetSource.SECOND_QUEST, SetSource.SHAPES)
# SH-SRC-09: Mixed Quest's coin; heads makes levels 1-6 second quest
MIXED_HEADS: SetSources = (SetSource.SECOND_QUEST, SetSource.FIRST_QUEST)
MIXED_TAILS: SetSources = (SetSource.FIRST_QUEST, SetSource.SECOND_QUEST)
FIXED_SOURCES: dict[DungeonLayoutSource, SetSources] = {
    DungeonLayoutSource.FIRST_QUEST: (SetSource.FIRST_QUEST, SetSource.FIRST_QUEST),
    DungeonLayoutSource.SECOND_QUEST: (SetSource.SECOND_QUEST, SetSource.SECOND_QUEST),
    DungeonLayoutSource.GENERATED_SHAPES: ALL_SHAPES,
}


def draw_seed_set_sources(dungeon_quest: DungeonLayoutSource, rng: IntRng) -> SetSources | None:
    """SH-SRC-01/07/08: the sources drawn once per seed; None for Mixed Quest (C02 = 2), whose
    coin is drawn per attempt (draw_attempt_set_sources). C02 = 5 and 6 arrive here already
    drawn (SH-SRC-10, FL-DEP-04)."""
    if dungeon_quest in FIXED_SOURCES:
        return FIXED_SOURCES[dungeon_quest]
    if dungeon_quest is DungeonLayoutSource.MIXED:
        return None
    if dungeon_quest is not DungeonLayoutSource.MIXED_WITH_SHAPES:
        raise ValueError(f"C02 = {dungeon_quest} is drawn before generation (SH-SRC-10)")
    while True:
        first, second = (MIXED_WITH_SHAPES_SOURCES[rng.below(3)] for _ in range(2))
        if first is not second:
            return first, second


def draw_attempt_set_sources(seed_sources: SetSources | None, rng: IntRng) -> SetSources:
    """SH-SRC-09: Mixed Quest's coin, drawn again on every generation attempt."""
    if seed_sources is not None:
        return seed_sources
    return MIXED_HEADS if rng.below(2) else MIXED_TAILS


def monsters_take_second_quest_path(dungeon_quest: DungeonLayoutSource, sources: SetSources) -> bool:
    """SH-SRC-05: a second-quest set sends every rope and Stalfos down the second-quest path,
    except under Mixed Quest (C02 = 2, SH-SRC-09's quirk: the branches keep $F0)."""
    return dungeon_quest is not DungeonLayoutSource.MIXED and SetSource.SECOND_QUEST in sources


# PS-VAN-02: a vanilla level's room list leaves out its person rooms and, in first-quest
# level 7, room $28 (40), the hungry goriya's
HUNGRY_GORIYA_ROOM_Q1_L7 = 0x28
# PS-VAN-02: the rooms listed last, in this order (quirk)
LISTED_LAST = {(SetSource.FIRST_QUEST, 7): (11, 58), (SetSource.FIRST_QUEST, 9): (49, 33, 53)}
# PS-VAN-02: the one stored value that differs from PRG0's (quirk): first-quest level 7's room
# $3A holds item $19 (PRG0 $39). Trigger bytes are not stored values (V25): every vanilla room
# keeps PRG0's, so level 9's $21 starts with $20 and no room ends with trigger 7 and no item.
STORED_ITEM_BYTES = {(SetSource.FIRST_QUEST, 58): 0x19}
STORED_VALUE_LEVELS = {(SetSource.FIRST_QUEST, 58): 7}


def vanilla_room_list(level: Level, source: SetSource) -> list[int]:
    """PS-VAN-02: the level's rooms (SH-SRC-04's list, which the parser's flood fill gives for
    PRG0) less its person rooms and the first-quest hungry goriya, in rising order but for the
    two first-quest levels whose last rooms are fixed."""
    rooms = [room.room_num for room in level.rooms if not room.is_person
             and not (source is SetSource.FIRST_QUEST and level.level_num == 7
                      and room.room_num == HUNGRY_GORIYA_ROOM_Q1_L7)]
    last = LISTED_LAST.get((source, level.level_num), ())
    return [room for room in rooms if room not in last] + [room for room in last if room in rooms]


def _apply_stored_values(levels: list[Level], source: SetSource) -> None:
    """PS-VAN-02's stored value that differs from PRG0's, written into the staged room so the
    passes that start from the lists start from it."""
    for level in levels:
        for room in level.rooms:
            key = (source, room.room_num)
            if STORED_VALUE_LEVELS.get(key) != level.level_num:
                continue
            if key in STORED_ITEM_BYTES:
                room.item_info = ItemInfo.from_item_byte(STORED_ITEM_BYTES[key])


def vanilla_set(gw: GameWorld, set_index: int, source: SetSource) -> tuple[LevelBlock, list[Level]]:
    """SH-SRC-02/03: a vanilla set starts as PRG0's block for its quest and set, with PRG0's
    level information for each level (the second quest's replacement bytes in a second-quest
    level); a copy, so the base GameWorld is untouched."""
    first_quest = source is SetSource.FIRST_QUEST
    base_block = (gw.blocks if first_quest else gw.blocks_2q)[set_index]
    base_levels = [(gw.levels if first_quest else gw.levels_2q)[level_num - 1] for level_num in SET_LEVELS[set_index]]
    block, levels = copy.deepcopy((base_block, base_levels))
    block.levels[:] = levels
    for level in levels:
        level.is_second_quest = not first_quest
    _apply_stored_values(levels, source)
    return block, levels

