"""Add L4 Sword = Level 2 (All Swords No Boards, docs/design/asnb.md section 4): the shapes give
level 2 one item cellar (shapes.tables.cellar_items), holding one sword upgrade (item $01); after
the other ZORA extras' joins, that sword joins the major-item pool with the same inside-out
Fisher-Yates step (extra_pool_items.exchange_with_drawn): one draw among the pool's places and the
cellar itself, and the two exchange items. So the sword may land anywhere in the pool, and the
cellar holds whatever it displaced (a pool item, so a place, Archipelago's "... Cellar" too).

With Level 9 Entrance = Level 4 sword the sword is a tracked item (level 9 needs it, like the
letter for the potion shop): its record joins the item shuffle's tracked list before the draw and
moves with it. Otherwise it is untracked, as Add L4 Sword's level-9 sword is.
"""
from __future__ import annotations

from ...model.enums import Item
from ...model.levels import Level
from ..rng import IntRng
from ..shapes.tables import LEVEL_2_SWORD_ITEM, LEVEL_2_SWORD_LEVEL
from .extra_pool_items import ExtraPoolItems, ItemCellarPlace, exchange_with_drawn, item_cellars, pool_places
from .item_shuffle_result import ItemShuffleOptions, ItemShuffleResult

LEVEL_2_SWORD = Item(LEVEL_2_SWORD_ITEM)


def level_2_sword_cellar(levels: list[Level]) -> ItemCellarPlace:
    """Level 2's one item cellar, holding the sword before the join."""
    level2 = next(level for level in levels if level.level_num == LEVEL_2_SWORD_LEVEL)
    cellars = list(item_cellars(level2))
    assert len(cellars) == 1 and cellars[0].item == LEVEL_2_SWORD, cellars
    return ItemCellarPlace(level2, cellars[0])


def join_level_2_sword(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems, rng: IntRng,
                       tracked: bool, opts: ItemShuffleOptions | None = None) -> None:
    """The level-2 sword joins the pool (one draw); `tracked`: Level 9 Entrance = Level 4 sword."""
    opts = opts or ItemShuffleOptions()
    own = level_2_sword_cellar(levels)
    places = pool_places(levels, state, extras, opts)
    if tracked:
        state.tracked.append(own.tracked(LEVEL_2_SWORD))
    exchange_with_drawn(own, places, state, rng)
