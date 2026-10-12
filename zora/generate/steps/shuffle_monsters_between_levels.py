"""Shuffle Monsters Between Levels (B36; PS-MONLV-01 to -06): enemy banks
and monster redraws."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ...model.enums import Enemy
from ...model.levels import GANON_LIST, ZELDA_LIST, Level, LevelBlock
from ...model.rooms import MONSTER_VALUE_BIT, RoomPlace
from ..rng import IntRng, discard
from ..shapes.enemies import monster_barred
from .dungeon_quest import SET_LEVELS, SetSource, vanilla_room_list
from .monster_lists import MonsterShuffleResult, RoomLists, _low_six, _room_at
from .shuffle_bosses import LEADING_DISCARDS

# --- PS-MONLV ------------------------------------------------------------------

# PS-MONLV-01: vanilla enemy-bank tiers; the deal's starting order for levels
# 1-9, with levels 6 and 7 redrawn (the spec's stream, non-normative).
VANILLA_ENEMY_TIER = {1: 0, 2: 0, 7: 0, 3: 1, 5: 1, 8: 1, 4: 2, 6: 2, 9: 2}
DEAL_START = (0, 0, 1, 1, 2, None, None, 0, 2)
TIER_COUNT = 3

# PS-MONLV-02: values never in a pool and never redrawn (whole-value tests).
POOL_EXCLUDED_BOSSES = frozenset(
    {0x3D, 0x31, 0x32, 0x33, 0x34, 0x39, 0x38, 0x3C}
    | {MONSTER_VALUE_BIT | low for low in (0x02, 0x03, 0x04, 0x05, 0x07, 0x08)}
)
POOL_EXCLUDED_SPECIAL = frozenset({GANON_LIST, ZELDA_LIST, Enemy.HUNGRY_GORIYA})
PEOPLE_AND_HINTS = range(0x10B, 0x121)   # flagged monster bytes 11-32

# PS-MONLV-06: the goriya's first sprite tile, by the level's NEW tier.
GORIYA_TILES_BY_TIER = ((0xA0, 0xA8, 0xAC, 0xB0), (0xA4, 0xB0), (0xB4,))


def deal_enemy_banks(state: MonsterShuffleResult, rng: IntRng) -> None:
    """PS-MONLV-01: the multiset {0,0,0,1,1,2,2,x,y} dealt uniformly over
    levels 1-9 by a Fisher-Yates walk (the "level 9 included" option is on
    under the preset)."""
    discard(rng, LEADING_DISCARDS)
    tiers = [tier if tier is not None else rng.below(TIER_COUNT) for tier in DEAL_START]
    levels = len(tiers)
    for position in range(levels):
        other = position + rng.below(levels - position)
        tiers[position], tiers[other] = tiers[other], tiers[position]
        state.enemy_tiers[position + 1] = tiers[position]


def pool_excluded(value: int) -> bool:
    """PS-MONLV-02's exclusions: empty rooms, bosses, Ganon, Zelda, the
    hungry goriya, people and hint codes. Quirk: whole-value tests, so a
    count-indexed boss would escape them (none exists at the shape stage)."""
    return (_low_six(value) == 0 or value in POOL_EXCLUDED_BOSSES
            or value in POOL_EXCLUDED_SPECIAL or value in PEOPLE_AND_HINTS)


def build_pools(lists: RoomLists, quests: LevelQuests | None = None, second_quest: bool = False) -> list[list[int]]:
    """PS-MONLV-02: pool t holds each distinct value (once) of the lists of
    the levels whose VANILLA tier is t, after the boss shuffle, in ascending
    order. The first-quest lists 1-9 and the second-quest lists 10-18 have
    pools of their own (PS-VAN-01): a level's list of the other quest than
    its own is PRG0's (`quests`)."""
    pools: list[set[int]] = [set() for _ in range(TIER_COUNT)]
    for level, places in lists.rooms.items():
        tier = VANILLA_ENEMY_TIER[level]
        if quests is None or quests.is_second_quest(level) == second_quest:
            values: Iterable[int] = (lists.values[place] for place in places)
        else:
            values = quests.other_quest_values[level]
        pools[tier].update(value for value in values if not pool_excluded(value))
    return [sorted(pool) for pool in pools]


def _goriya_level(blocks: list[LevelBlock], levels: list[Level]) -> int | None:
    """The level owning the hungry goriya's cell (after PS-GRUM-02's move):
    the first such room in block scan order."""
    for block in blocks:
        owned = sorted(((room.room_num, level.level_num, room) for level in levels
                        if level.block is block for room in level.rooms), key=lambda entry: entry[0])
        for _room_num, level_num, room in owned:
            if room.enemy == Enemy.HUNGRY_GORIYA:
                return level_num
    return None


def shuffle_monsters_between_levels(blocks: list[LevelBlock], levels: list[Level], lists: RoomLists,
                                    state: MonsterShuffleResult, rng: IntRng,
                                    quests: LevelQuests | None = None) -> None:
    """PS-MONLV-01..06: deal the enemy banks, then redraw every ordinary monster room of levels
    1-9 from its new tier's pool. `quests`: with a vanilla set (PS-VAN-01), each level's quest,
    the second-quest pools and the mixed groups the bubble rule reads; None under the MVP
    baseline, where every list is first quest and no bubble exists."""
    deal_enemy_banks(state, rng)
    if quests is not None and quests.second_quest_level_2:
        state.enemy_tiers[2] = state.enemy_tiers[7]      # PS-VAN-04, before any room is redrawn
    pools = {False: build_pools(lists, quests, second_quest=False)}
    if quests is not None:
        pools[True] = build_pools(lists, quests, second_quest=True)
    goriya_level = _goriya_level(blocks, levels)
    for level in sorted(lists.rooms):
        tier = state.enemy_tiers[level]
        if level == goriya_level:
            tiles = GORIYA_TILES_BY_TIER[tier]
            state.goriya_tile = tiles[rng.below(len(tiles))]
        pool = pools[quests is not None and quests.is_second_quest(level)][tier]
        start = {place: lists.values[place] for place in lists.rooms[level]}
        while True:
            drawn = _redraw_level(blocks, lists, lists.rooms[level], pool, state, rng)
            if quests is None or not quests.red_without_blue(drawn):
                break
            lists.values.update(start)                   # PS-MONLV-05: the whole level again


def _redraw_level(blocks: list[LevelBlock], lists: RoomLists, places: list[RoomPlace], pool: list[int],
                  state: MonsterShuffleResult, rng: IntRng) -> list[int]:
    """PS-MONLV-03/04: one pass over a level's rooms; returns the values drawn."""
    drawn = []
    for place in places:
        if pool_excluded(lists.values[place]):
            continue
        if not pool:
            discard(rng)             # an empty pool still consumes a draw
            continue
        layout = _room_at(blocks, place).room_type
        while True:                  # no cap (PS-MONLV-04; SH-ENEMY-04's bars)
            value = pool[rng.below(len(pool))]
            if not monster_barred(value, layout):
                break
        lists.values[place] = value
        drawn.append(value)
        state.redrawn += 1
    return drawn


@dataclass(frozen=True)
class LevelQuests:
    """What the monster moves need of a seed with a vanilla set (PS-VAN-01): the second-quest
    levels, the other quest's lists of each level (PRG0's, PS-VAN-02: a level's first-quest and
    second-quest lists both join their quest's pools) and the mixed groups as the ROM stands
    when the step starts (PS-MONLV-05)."""
    second_quest_levels: frozenset[int]
    other_quest_values: dict[int, tuple[int, ...]]
    mixed_groups: dict[int, list[Enemy]]

    @property
    def second_quest_level_2(self) -> bool:
        return 2 in self.second_quest_levels

    def is_second_quest(self, level: int) -> bool:
        return level in self.second_quest_levels

    def _names(self, value: int, bubble: Enemy) -> bool:
        if not value & MONSTER_VALUE_BIT:
            return _low_six(value) == bubble
        code = MIXED_GROUP_BASE + _low_six(value)
        return _low_six(value) >= FIRST_MIXED_LOW_SIX and bubble in self.mixed_groups.get(code, [])

    def red_without_blue(self, drawn: list[int]) -> bool:
        """PS-MONLV-05: a drawn red bubble and no drawn blue one (count bits ignored)."""
        return (any(self._names(value, Enemy.RED_BUBBLE) for value in drawn)
                and not any(self._names(value, Enemy.BLUE_BUBBLE) for value in drawn))


# PS-MONLV-05: a flagged value names mixed group $40 + its low six bits ($62-$7F: low six $22 up)
MIXED_GROUP_BASE = 0x40
FIRST_MIXED_LOW_SIX = 0x22


def level_quests(levels: list[Level], second_quest_sets: set[int], base_levels: list[Level],
                 base_levels_2q: list[Level], mixed_groups: dict[int, list[Enemy]]) -> LevelQuests:
    """PS-VAN-01/02: each level's quest and its other quest's PRG0 list values."""
    second = frozenset(level.level_num for level in levels
                       if any(level.level_num in SET_LEVELS[s] for s in second_quest_sets))
    other: dict[int, tuple[int, ...]] = {}
    for level_num in range(1, 10):
        is_second = level_num in second
        base = (base_levels if is_second else base_levels_2q)[level_num - 1]
        source = SetSource.FIRST_QUEST if is_second else SetSource.SECOND_QUEST
        other[level_num] = tuple(base.block.room(room).monster_value for room in vanilla_room_list(base, source))
    return LevelQuests(second, other, mixed_groups)
