"""Shuffle Monsters Between Levels (B36; PS-MONLV-01 to -04, -06): enemy banks
and monster redraws."""

from ...model.enums import Enemy
from ...model.levels import GANON_LIST, ZELDA_LIST, Level, LevelBlock
from ...model.rooms import MONSTER_VALUE_BIT
from ..rng import IntRng, discard
from ..shapes.enemies import monster_barred
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


def build_pools(lists: RoomLists) -> list[list[int]]:
    """PS-MONLV-02: pool t holds each distinct value (once) of the lists of
    the levels whose VANILLA tier is t, after the boss shuffle, in ascending
    order."""
    pools: list[set[int]] = [set() for _ in range(TIER_COUNT)]
    for level, places in lists.rooms.items():
        tier = VANILLA_ENEMY_TIER[level]
        pools[tier].update(value for value in (lists.values[place] for place in places)
                           if not pool_excluded(value))
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
                                    state: MonsterShuffleResult, rng: IntRng) -> None:
    """PS-MONLV-01..04 and -06: deal the enemy banks, then redraw every
    ordinary monster room of levels 1-9 from its new tier's pool."""
    deal_enemy_banks(state, rng)
    pools = build_pools(lists)
    goriya_level = _goriya_level(blocks, levels)
    for level in sorted(lists.rooms):
        tier = state.enemy_tiers[level]
        if level == goriya_level:
            tiles = GORIYA_TILES_BY_TIER[tier]
            state.goriya_tile = tiles[rng.below(len(tiles))]
        pool = pools[tier]
        for place in lists.rooms[level]:
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
            state.redrawn += 1
