"""Shuffle Bosses (B34; PS-BOSS-01 to -04): boss tiers and boss sprite banks."""

from collections.abc import Mapping

from ...model.enums import Enemy, Item
from ...model.levels import LevelBlock
from ..rng import IntRng, discard
from ..shapes.bosses import boss_barred
from .item_shuffle_result import TrackedPlace
from .monster_lists import (
    MonsterShuffleResult,
    RoomLists,
    _boss_code,
    _boss_value,
    _room_at,
)

# --- PS-BOSS -------------------------------------------------------------------

# PS-BOSS-02: the three tiers in pick order; boss codes with $40 = monster bit.
BOSS_TIERS = (
    (0x3D, 0x31, 0x32, 0x39, 0x38),          # Aquamentus, Dodongos, Digdoggers
    (0x33, 0x34, 0x3C, 0x43, 0x44, 0x45),    # Gohmas, Manhandla, Gleeok 2-4 heads
    (0x47, 0x48),                            # Patras
)
VANILLA_BOSS_TIER = {1: 0, 2: 0, 5: 0, 7: 0, 3: 1, 4: 1, 6: 1, 8: 1}
# PS-BOSS-01's w per level: tiers 0 and 1 each w/(2w+1), tier 2 1/(2w+1).
BOSS_TIER_WEIGHT = {1: 4, 2: 4, 3: 8, 4: 8, 5: 9, 6: 9, 7: 27, 8: 27}
LEADING_DISCARDS = 3


def draw_boss_tier(level: int, rng: IntRng) -> int:
    """PS-BOSS-01: tier = (r mod (2w+1)) div w."""
    weight = BOSS_TIER_WEIGHT[level]
    return rng.below(2 * weight + 1) // weight


# PS-BOSS-05: each item and the bosses it beats (any Gleeok, one head included).
BOSSES_BEATEN_BY = {
    Item.RECORDER: (Enemy.SINGLE_DIGDOGGER, Enemy.TRIPLE_DIGDOGGER),
    Item.BOW: (Enemy.BLUE_GOHMA, Enemy.RED_GOHMA),
    Item.WAND: (Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4),
}
ITEM_BEATS_BOSS_LEVELS = (1, 2)

# PS-BOSS-07 (B79): each listed room first takes a coin that comes up one time in EXTRA_BOSS_ODDS
EXTRA_BOSS_ODDS = 4
MONSTER_BIT_VALUE = 0x100                       # the nine-bit value's monster bit (PS-MONLV-02)
MONSTER_LIST_MASK = 0x3F
# The monster values an extra boss never replaces: Zelda, Ganon and the hungry goriya, and (with the
# monster bit) the person codes 12 to 18; an empty room (value 0 without the monster bit) neither
NEVER_EXTRA_BOSS = frozenset({Enemy.THE_KIDNAPPED, Enemy.THE_BEAST, Enemy.HUNGRY_GORIYA})
PERSON_CODES = range(0x0C, 0x13)


def bosses_beaten_by_planted_items(records: list[TrackedPlace]) -> dict[int, frozenset[int]]:
    """PS-BOSS-05: in levels 1 and 2, the bosses a pick may not be because the
    item that beats them is the level's FIRST or LAST planted-item record.

    The records (owner ruling, 2026-10-04) are fifteen, one per ITEM, in this
    fixed order: recorder, raft, wood boomerang, magical boomerang, ladder,
    wand, bow, red ring, magical key, red candle, silver arrow, book, then the
    items the bracelet, white-sword and coast caves held before the shuffle
    (ItemShuffleResult.tracked, in pool order). Each lies in the level its item
    ends up in; a level's first and last are the earliest and latest listed
    items that ended up there (one may be both; those in between are ignored).
    Heart containers added to the pool have no records."""
    barred: dict[int, frozenset[int]] = {}
    for level in ITEM_BEATS_BOSS_LEVELS:
        in_level = [record for record in records if record.level == level]
        ends = {in_level[0].item, in_level[-1].item} if in_level else set()
        barred[level] = frozenset(int(boss) for item in ends for boss in BOSSES_BEATEN_BY.get(Item(item), ()))
    return barred


def may_take_an_extra_boss(value: int) -> bool:
    """PS-BOSS-07: a room an extra boss may replace: not empty, Zelda, Ganon, the hungry goriya or a
    person."""
    if value & ~MONSTER_BIT_VALUE == 0 or value in NEVER_EXTRA_BOSS:
        return False
    return not (value & MONSTER_BIT_VALUE and value & MONSTER_LIST_MASK in PERSON_CODES)


def shuffle_bosses(blocks: list[LevelBlock], lists: RoomLists, state: MonsterShuffleResult,
                   rng: IntRng, beaten_by_planted_items: Mapping[int, frozenset[int]] | None = None,
                   extra_bosses: bool = False) -> None:
    """PS-BOSS-01..04: levels 1-8 in order draw a tier (the level's boss
    bank); a room whose boss is on the level's VANILLA tier (PS-BOSS-03)
    gets a boss drawn uniformly from the new tier, redrawn while its layout
    bars it (PS-BOSS-04), or, given beaten_by_planted_items, while the item
    that beats it is planted at an end of the level (PS-BOSS-05). Level 9
    is never touched (PS-BOSS-06). The lists walked are each level's own: a
    second-quest level's (C02 = 1, 2, 4), whose redraws are its bosses
    (PS-BOSS-06's MUST); the item rule bars by level number, so it applies to a
    second-quest level 1 or 2 too (PS-BOSS-05's MAY; owner ruling 2026-10-27).

    With extra_bosses (B79, PS-BOSS-07) every listed room first takes a coin; when it comes up, a
    room that may take an extra boss is re-bossed as a boss room is. Quirk: a pick the bars reject
    starts the room again with a new coin, so an ordinary room whose coin then fails keeps its
    monster; a vanilla-tier boss room is re-bossed whatever its coins say."""
    beaten_by_planted_items = beaten_by_planted_items or {}
    discard(rng, LEADING_DISCARDS)
    for level, vanilla_tier in sorted(VANILLA_BOSS_TIER.items()):
        tier = draw_boss_tier(level, rng)
        state.boss_tiers[level] = tier
        planted_bars = beaten_by_planted_items.get(level, frozenset())
        for place in lists.rooms.get(level, []):
            value = lists.values[place]
            vanilla_boss = _boss_code(value) in BOSS_TIERS[vanilla_tier]
            room = _room_at(blocks, place)
            bosses = BOSS_TIERS[tier]
            while True:                  # no cap: every tier has an unbarred boss
                extra = extra_bosses and rng.below(EXTRA_BOSS_ODDS) == 0 and may_take_an_extra_boss(value)
                if not (vanilla_boss or extra):
                    break
                boss = bosses[rng.below(len(bosses))]
                if not boss_barred(room.room_type, room.movable_block, boss) and boss not in planted_bars:
                    lists.values[place] = _boss_value(boss)
                    state.rebossed += 1
                    break
