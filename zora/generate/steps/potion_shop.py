"""The owner's 2.0 Shuffle Blue Potion (docs/design/zora-flags-2.0.md section 1; owner decisions
2026-10-07 and 2026-10-08).

Shuffle Blue Potion, merged with the progressive plan's "Potion Shop Item in the Pool" (Phase 2B,
docs/design/progressive-items-plan.md section 13): after the other joins, a blue potion joins the
major-item pool from the potion shop's MIDDLE ware (owner design change, 2026-10-08: empty in
PRG0, it becomes the place), with the extras' inside-out Fisher-Yates step, so that ware may sell
any pool item and the blue potion may land in any pool place (a dungeon room, a cave, another
joined shop ware). The potion shop's left blue potion and its red potion stay, sold again and
again as in PRG0.
  - The letter never lands in the potion shop, which opens only for a player who has shown the
    letter: a place holding it is left out of the draw.
  - The letter becomes a tracked item whenever the middle ware holds a tracked one (the ware
    is collected with its door reached and the letter held; acceptance_check). It works with
    Randomize Letter, which already put the letter in the pool.
  - Prices follow the existing price classes (SI-PRICE-01): the middle ware holding another
    item is priced by it; keeping its blue potion it costs what the left one does; a blue potion
    landing in another joined shop ware costs 25-55 rupees, the potion shop's own range.
  - The middle ware is sold once whatever it holds, the blue potion included (code_patches.
    one_time_wares; fp-prog-01's one-time wares, written with this flag on as well).
"""
from __future__ import annotations

from ...model.enums import Destination, Item
from ...model.levels import Level
from ...model.overworld import POTION_SHOP_MIDDLE, ItemCave, Overworld, Shop, ShopItem
from ..rng import IntRng
from .extra_pool_items import (
    ExtraPoolItems,
    PoolPlace,
    ShopWarePlace,
    exchange_with_drawn,
    pool_places,
)
from .item_shuffle_result import LETTER_SLOT, ItemShuffleOptions, ItemShuffleResult, TrackedPlace
from .shop_items_in_pool import PRICES_BY_ITEM

BLUE_POTION_WARE = 0                  # the potion shop's left ware: PRG0's blue potion, which stays
BLUE_POTION_PRICES = (25, 55)         # the potion shop's own range (OW-SHOP-04)


def potion_shop(overworld: Overworld) -> Shop:
    shop = overworld.get_cave(Destination.POTION_SHOP, Shop)
    assert isinstance(shop, Shop)
    return shop


def _uniform(rng: IntRng, prices: tuple[int, int]) -> int:
    low, high = prices
    return low + rng.below(high - low + 1)


def shuffle_blue_potion(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems, overworld: Overworld,
                        rng: IntRng, opts: ItemShuffleOptions | None = None) -> None:
    """A blue potion, priced as the left one, fills the potion shop's middle ware and joins the
    pool from there (one draw); the two wares it touched are priced, and the letter is tracked
    when the middle ware now holds a tracked item."""
    opts = opts or ItemShuffleOptions()
    shop = potion_shop(overworld)
    left = shop.ware(BLUE_POTION_WARE)
    assert left.item == Item.BLUE_POTION and shop.middle is None, (left, shop.middle)
    shop.middle = ShopItem(item=Item.BLUE_POTION, price=left.price)
    own = ShopWarePlace(shop, POTION_SHOP_MIDDLE)
    places = [place for place in pool_places(levels, state, extras, opts) if place.get() != Item.LETTER]
    drawn = exchange_with_drawn(own, places, state, rng)
    extras.shop_wares.append(own)
    extras.shop_items.append(Item.BLUE_POTION)
    extras.slot_prices.append(left.price)
    price_potion_wares(own, drawn, rng)
    if any(place.slot == own.tracked(Item.NOTHING).slot for place in state.tracked):
        track_the_letter(levels, state, extras, overworld, opts)


def price_potion_wares(own: ShopWarePlace, drawn: PoolPlace | None, rng: IntRng) -> None:
    """SI-PRICE-01's classes for the potion shop's middle ware; 25-55 for a blue potion in another shop."""
    item = own.get()
    if item != Item.BLUE_POTION and item in PRICES_BY_ITEM:
        own.shop.ware(own.position).price = _uniform(rng, PRICES_BY_ITEM[item])
    if isinstance(drawn, ShopWarePlace):
        drawn.shop.ware(drawn.position).price = _uniform(rng, BLUE_POTION_PRICES)


def track_the_letter(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems, overworld: Overworld,
                     opts: ItemShuffleOptions) -> None:
    """The letter as a tracked item, where it is: its own cave (Randomize Letter off), or the pool
    place Randomize Letter put it in."""
    holding = [place for place in pool_places(levels, state, extras, opts) if place.get() == Item.LETTER]
    if holding:
        state.tracked.append(holding[0].tracked(Item.LETTER))
        return
    letter_cave = overworld.get_cave(Destination.LETTER_CAVE, ItemCave)
    assert isinstance(letter_cave, ItemCave) and letter_cave.item == Item.LETTER
    state.tracked.append(TrackedPlace(Item.LETTER, slot=LETTER_SLOT))

