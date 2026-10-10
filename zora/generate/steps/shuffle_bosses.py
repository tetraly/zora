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


def shuffle_bosses(blocks: list[LevelBlock], lists: RoomLists, state: MonsterShuffleResult,
                   rng: IntRng, beaten_by_planted_items: Mapping[int, frozenset[int]] | None = None) -> None:
    """PS-BOSS-01..04: levels 1-8 in order draw a tier (the level's boss
    bank); a room whose boss is on the level's VANILLA tier (PS-BOSS-03)
    gets a boss drawn uniformly from the new tier, redrawn while its layout
    bars it (PS-BOSS-04), or, given beaten_by_planted_items, while the item
    that beats it is planted at an end of the level (PS-BOSS-05). Level 9
    is never touched (PS-BOSS-06)."""
    beaten_by_planted_items = beaten_by_planted_items or {}
    discard(rng, LEADING_DISCARDS)
    for level, vanilla_tier in sorted(VANILLA_BOSS_TIER.items()):
        tier = draw_boss_tier(level, rng)
        state.boss_tiers[level] = tier
        planted_bars = beaten_by_planted_items.get(level, frozenset())
        for place in lists.rooms.get(level, []):
            if _boss_code(lists.values[place]) not in BOSS_TIERS[vanilla_tier]:
                continue
            room = _room_at(blocks, place)
            bosses = BOSS_TIERS[tier]
            while True:                  # no cap: every tier has an unbarred boss
                boss = bosses[rng.below(len(bosses))]
                if not boss_barred(room.room_type, room.movable_block, boss) and boss not in planted_bars:
                    break
            lists.values[place] = _boss_value(boss)
            state.rebossed += 1
