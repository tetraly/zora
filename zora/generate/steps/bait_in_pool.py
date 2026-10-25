"""Shop Items in the Item Pool's bait (docs/zora-extras.md section 10; owner decision 2026-10-17:
ZORA 1.0's definition of the option, which put the bait in the pool with the wooden arrows, blue
candle and blue ring), following docs/design/progressive-items-plan.md section 13's "Phase 2A: Bait
in the Item Pool".

After the option's other three joins, on the stock Shuffle Shop Items (B08) left, the shops'
baits are found by what they sell, shops 1-4 in order and each shop's wares left to right:
  - one bait joins the major-item pool for each hungry Goriya in the seed's levels (Shuffle Hungry
    Goriya, B28, moves the one first-quest Goriya; a second-quest set brings its own), each from
    its own shop ware with the extras' inside-out Fisher-Yates step, so its ware becomes a pool
    place. Each bait is a tracked item (the logic's bait rule, acceptance_check.LogicRules);
  - a bait left over (one Goriya: PRG0's second bait) becomes a fairy priced 20-40
    (FAIRY_PRICES, one draw), and stays a plain ware, never a pool place.
Prices follow Shop Items in the Item Pool's classes (SI-PRICE-01, steps/shop_prices.py): a bait
ware holding a displaced item is priced by that item, and a joined ware that now sells the bait
is priced as a required item, 60-80 (beta 9 price rules; it kept its own slot price before).
The ROM side, bait as a count, is zora/rom/bait_count.py.
"""
from __future__ import annotations

from ...model.enums import Enemy, Item
from ...model.levels import Level
from ...model.overworld import Overworld, Shop
from ..rng import IntRng
from .extra_pool_items import ExtraPoolItems, ShopWarePlace, exchange_with_drawn, pool_places
from .item_shuffle_result import ItemShuffleOptions, ItemShuffleResult
from .shop_items_in_pool import price_ware
from .shop_prices import FAIRY_PRICES
from .shuffle_shop_items import SHOPS


def hungry_goriyas(levels: list[Level]) -> int:
    """How many rooms of the seed's levels hold a hungry Goriya: one in a first-quest set
    (PS-GRUM-01's census), two with a second-quest set (each quest's own)."""
    return sum(room.enemy == Enemy.HUNGRY_GORIYA for level in levels for room in level.rooms)


def bait_wares(overworld: Overworld) -> list[ShopWarePlace]:
    """The shop wares selling bait, shops 1-4 in order, each shop's wares left to right."""
    return [ShopWarePlace(shop, position) for destination in SHOPS
            if isinstance(shop := overworld.get_cave(destination, Shop), Shop)
            for position, ware in enumerate(shop.items) if ware.item == Item.BAIT]


def bait_in_pool(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                             overworld: Overworld, rng: IntRng, opts: ItemShuffleOptions | None = None) -> None:
    """The fairy swap for the baits no Goriya needs, then each needed bait's join and prices."""
    opts = opts or ItemShuffleOptions()
    wares = bait_wares(overworld)
    needed = max(1, hungry_goriyas(levels))
    assert needed <= len(wares), f"{needed} hungry Goriyas, {len(wares)} baits in the shops"
    for spare in wares[needed:]:
        spare.put(Item.FAIRY)
        low, high = FAIRY_PRICES
        spare.shop.ware(spare.position).price = low + rng.below(high - low + 1)
    for own in wares[:needed]:
        join_bait(own, levels, state, extras, rng, opts)


def join_bait(own: ShopWarePlace, levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
              rng: IntRng, opts: ItemShuffleOptions) -> None:
    """SI-JOIN-01's step for one bait: one draw among the pool's places and its own ware, then
    the two exchange items; then SI-PRICE-01 for the wares it touched."""
    places = pool_places(levels, state, extras, opts)
    state.tracked.append(own.tracked(Item.BAIT))
    slot_price = own.shop.ware(own.position).price
    extras.shop_wares.append(own)
    extras.shop_items.append(Item.BAIT)
    extras.slot_prices.append(slot_price)
    drawn = exchange_with_drawn(own, places, state, rng)
    prices = opts.prices.prices
    displaced = own.get()
    if displaced != Item.BAIT and displaced in prices:
        low, high = prices[displaced]
        own.shop.ware(own.position).price = low + rng.below(high - low + 1)
    if isinstance(drawn, ShopWarePlace):
        # a joined ware now selling the bait: priced as a required item (beta 9 price rules; it
        # kept the slot's price, up to 254 in the blue ring's ware)
        price_ware(drawn, extras, rng, opts.prices)
