"""Shop Items in the Item Pool (ZORA flag; docs/design/progressive-items-plan.md section 6,
docs/zora-extras.md section 10): the wooden arrows, the blue candle and the blue ring join the
major-item pool, and a shop may sell the pool item that takes their place.

SI-JOIN-01: after the magical sword and letter joins, each item joins once, in that order, with
the extras' inside-out Fisher-Yates step: one draw among the pool's places and the item's own
shop ware (found by what it sells, after B08's stock shuffle), then the two exchange items. The
arrows and the candle unlock things, so they become tracked items (PI-LOGIC-06); the ring
unlocks nothing and joins untracked, like the letter.

SI-PRICE-01 (owner revision, 6 Oct 2026; the beta 9 rules, 2026-10-24): then each joined shop
ware that holds a displaced item is priced by what it holds (steps/shop_prices.py: an item that can
be required 60-80, the boomerangs 75-125, optional items 200-240, heart containers and the letter
20-40); any other item keeps the slot's price (B08's jitter included when B08 is on).
"""
from __future__ import annotations

from ...model.enums import Item
from ...model.levels import Level
from ...model.overworld import Overworld, Shop
from ..rng import IntRng
from .extra_pool_items import (
    ExtraPoolItems,
    ShopWarePlace,
    exchange_with_drawn,
    pool_places,
)
from .item_shuffle_result import ItemShuffleOptions, ItemShuffleResult
from .shop_prices import DEFAULT_PRICE_RULES, PriceRules
from .shuffle_shop_items import SHOPS

# SI-JOIN-01: the joining items, in join order.
JOINED_SHOP_ITEMS = (Item.WOOD_ARROWS, Item.BLUE_CANDLE, Item.BLUE_RING)
# PI-LOGIC-06: the joined items that unlock something are tracked.
TRACKED_SHOP_ITEMS = frozenset({Item.WOOD_ARROWS, Item.BLUE_CANDLE})
# Defense Item Pacing counts the rings a player holds, so the blue ring unlocks levels and is tracked too
# (docs/zora-extras.md section 22): untracked, only the red ring counted and Earlier's two rings at level 9
# could never be held, so every attempt was rejected (E1) until the generation limit.
PACED_SHOP_ITEMS = TRACKED_SHOP_ITEMS | {Item.BLUE_RING}


def own_shop_ware(overworld: Overworld, item: Item) -> ShopWarePlace:
    """The shop ware selling the item: the one shop of A-D whose stock holds it (OW-SHOP-06
    finds the candle and arrow shops the same way)."""
    wares = [ShopWarePlace(shop, position) for destination in SHOPS
             if isinstance(shop := overworld.get_cave(destination, Shop), Shop)
             for position, ware in enumerate(shop.items) if ware.item == item]
    assert len(wares) == 1, f"{item.name} sold by {len(wares)} wares"
    return wares[0]


def shop_items_in_pool(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                       overworld: Overworld, rng: IntRng, opts: ItemShuffleOptions | None = None,
                       tracked: frozenset[Item] = TRACKED_SHOP_ITEMS) -> None:
    """SI-JOIN-01, then SI-PRICE-01. tracked: the joined items that unlock something (PI-LOGIC-06)."""
    opts = opts or ItemShuffleOptions()
    for item in JOINED_SHOP_ITEMS:
        own = own_shop_ware(overworld, item)
        places = pool_places(levels, state, extras, opts)
        if item in tracked:
            state.tracked.append(own.tracked(item))
        extras.shop_wares.append(own)
        extras.shop_items.append(item)
        extras.slot_prices.append(own.shop.ware(own.position).price)
        exchange_with_drawn(own, places, state, rng)
    price_displaced_wares(extras, rng, opts.prices)


def price_displaced_wares(extras: ExtraPoolItems, rng: IntRng, rules: PriceRules = DEFAULT_PRICE_RULES) -> None:
    """SI-PRICE-01: each joined shop ware, in join order, holding an item other than its own
    joined item is priced by that item, uniformly over its range; an item without a range
    keeps the slot's price."""
    prices = rules.prices
    for ware, own_item in zip(extras.shop_wares, extras.shop_items, strict=True):
        item = ware.get()
        if item == own_item or item not in prices:
            continue
        low, high = prices[item]
        ware.shop.ware(ware.position).price = low + rng.below(high - low + 1)


def price_ware(ware: ShopWarePlace, extras: ExtraPoolItems, rng: IntRng,
               rules: PriceRules = DEFAULT_PRICE_RULES) -> None:
    """SI-PRICE-01 for a joined ware a later step put a new item in: by the item's class, else its
    slot price."""
    prices = rules.prices
    item = ware.get()
    if item in prices:
        low, high = prices[item]
        ware.shop.ware(ware.position).price = low + rng.below(high - low + 1)
    else:
        joined = next(index for index, joined_ware in enumerate(extras.shop_wares)
                      if joined_ware.shop is ware.shop and joined_ware.position == ware.position)
        ware.shop.ware(ware.position).price = extras.slot_prices[joined]
