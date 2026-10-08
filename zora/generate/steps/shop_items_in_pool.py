"""Shop Items in the Item Pool (ZORA flag; docs/design/progressive-items-plan.md section 6,
docs/zora-extras.md section 10): the wooden arrows, the blue candle and the blue ring join the
major-item pool, and a shop may sell the pool item that takes their place.

SI-JOIN-01: after the magical sword and letter joins, each item joins once, in that order, with
the extras' inside-out Fisher-Yates step: one draw among the pool's places and the item's own
shop ware (found by what it sells, after B08's stock shuffle), then the two exchange items. The
arrows and the candle unlock things, so they become tracked items (PI-LOGIC-06); the ring
unlocks nothing and joins untracked, like the letter.

SI-PRICE-01 (owner revision, 6 Oct 2026): then each joined shop ware that holds a displaced item
is priced by what it holds, drawn uniformly: progression items 60-80, items not needed to beat
the game 200-240, heart containers and the letter 20-40 (the letter: owner decision, 6 Oct
2026); any other item keeps the slot's price (B08's jitter included when B08 is on).
"""
from __future__ import annotations

from zora.generate.rng import IntRng
from zora.generate.steps.extra_pool_items import (
    ExtraPoolItems,
    ShopWarePlace,
    exchange_with_drawn,
    pool_places,
)
from zora.generate.steps.item_shuffle_result import ItemShuffleOptions, ItemShuffleResult
from zora.generate.steps.shuffle_shop_items import SHOPS
from zora.model.enums import Item
from zora.model.levels import Level
from zora.model.overworld import Overworld, Shop

# SI-JOIN-01: the joining items, in join order.
JOINED_SHOP_ITEMS = (Item.WOOD_ARROWS, Item.BLUE_CANDLE, Item.BLUE_RING)
# PI-LOGIC-06: the joined items that unlock something are tracked.
TRACKED_SHOP_ITEMS = frozenset({Item.WOOD_ARROWS, Item.BLUE_CANDLE})
# SI-PRICE-01 (owner revision, 6 Oct 2026): what a shop ware holding a displaced item costs, by
# that item (inclusive ranges).
PROGRESSION_PRICES = (60, 80)
NOT_NEEDED_PRICES = (200, 240)
HEART_CONTAINER_PRICES = (20, 40)
# Priced like heart containers: cheap. The letter reaches a shop ware only with Randomize Letter on
# (owner decision, 6 Oct 2026).
CHEAP_ITEMS = frozenset({Item.HEART_CONTAINER, Item.LETTER})
# Needed to beat the game: the four overworld progression items, the bow, and every candle-line
# and arrow-line item (a candle burns the bushes, two arrow upgrades beat Ganon).
PROGRESSION_ITEMS = frozenset({Item.LADDER, Item.RAFT, Item.POWER_BRACELET, Item.RECORDER, Item.BOW,
                               Item.BLUE_CANDLE, Item.RED_CANDLE, Item.WOOD_ARROWS, Item.SILVER_ARROWS})
# Not needed to beat the game: the sword, ring and boomerang lines, the wand, the book, the
# magical key.
NOT_NEEDED_ITEMS = frozenset({Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.BLUE_RING,
                              Item.RED_RING, Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG, Item.WAND,
                              Item.BOOK, Item.MAGICAL_KEY})
PRICES_BY_ITEM: dict[Item, tuple[int, int]] = {
    **dict.fromkeys(PROGRESSION_ITEMS, PROGRESSION_PRICES),
    **dict.fromkeys(NOT_NEEDED_ITEMS, NOT_NEEDED_PRICES),
    **dict.fromkeys(CHEAP_ITEMS, HEART_CONTAINER_PRICES),
}


def own_shop_ware(overworld: Overworld, item: Item) -> ShopWarePlace:
    """The shop ware selling the item: the one shop of A-D whose stock holds it (OW-SHOP-06
    finds the candle and arrow shops the same way)."""
    wares = [ShopWarePlace(shop, position) for destination in SHOPS
             if isinstance(shop := overworld.get_cave(destination, Shop), Shop)
             for position, ware in enumerate(shop.items) if ware.item == item]
    assert len(wares) == 1, f"{item.name} sold by {len(wares)} wares"
    return wares[0]


def shop_items_in_pool(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                       overworld: Overworld, rng: IntRng, opts: ItemShuffleOptions | None = None) -> None:
    """SI-JOIN-01, then SI-PRICE-01."""
    opts = opts or ItemShuffleOptions()
    for item in JOINED_SHOP_ITEMS:
        own = own_shop_ware(overworld, item)
        places = pool_places(levels, state, extras, opts)
        if item in TRACKED_SHOP_ITEMS:
            state.tracked.append(own.tracked(item))
        extras.shop_wares.append(own)
        extras.shop_items.append(item)
        exchange_with_drawn(own, places, state, rng)
    price_displaced_wares(extras, rng)


def price_displaced_wares(extras: ExtraPoolItems, rng: IntRng) -> None:
    """SI-PRICE-01: each joined shop ware, in join order, holding an item other than its own
    joined item is priced by that item, uniformly over its range; an item without a range
    keeps the slot's price."""
    for ware, own_item in zip(extras.shop_wares, extras.shop_items, strict=True):
        item = ware.get()
        if item == own_item or item not in PRICES_BY_ITEM:
            continue
        low, high = PRICES_BY_ITEM[item]
        ware.shop.items[ware.position].price = low + rng.below(high - low + 1)
