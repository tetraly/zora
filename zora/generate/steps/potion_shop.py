"""The owner's 2.0 Shuffle Blue Potion (docs/design/zora-flags-2.0.md section 1; owner decisions
2026-10-07).

Shuffle Blue Potion, merged with the progressive plan's "Potion Shop Item in the Pool" (Phase 2B,
docs/design/progressive-items-plan.md section 13): after the other joins, the potion shop's blue
potion (ware 0) joins the major-item pool with the extras' inside-out Fisher-Yates step, so the
potion shop may sell any pool item and the blue potion may land in any pool place (a dungeon
room, a cave, another joined shop ware). The red potion stays.
  - The letter never lands in the potion shop, which opens only for a player who has shown the
    letter: a place holding it is left out of the draw.
  - The letter becomes a tracked item whenever the potion shop holds a tracked one (the shop's
    ware is collected with its door reached and the letter held; acceptance_check). It works
    with Randomize Letter, which already put the letter in the pool.
  - Prices follow the existing price classes (SI-PRICE-01): the potion shop's ware holding
    another item is priced by it; a blue potion landing in another joined shop ware costs
    25-55 rupees, the potion shop's own range.
  - The ware is sold once like any non-consumable ware (fp-prog-01's one-time wares, written
    with this flag on as well).
"""
from __future__ import annotations

from zora.generate.rng import IntRng
from zora.generate.steps.extra_pool_items import (
    ExtraPoolItems,
    PoolPlace,
    ShopWarePlace,
    exchange_with_drawn,
    pool_places,
)
from zora.generate.steps.item_shuffle_result import LETTER_SLOT, ItemShuffleOptions, ItemShuffleResult, TrackedPlace
from zora.generate.steps.shop_items_in_pool import PRICES_BY_ITEM
from zora.model.enums import Destination, Item
from zora.model.levels import Level
from zora.model.overworld import ItemCave, Overworld, Shop

BLUE_POTION_WARE = 0                  # the potion shop's left ware (PRG0: the blue potion)
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
    """The blue potion joins the pool (one draw), the two wares it touched are priced, and the
    letter is tracked when the potion shop now holds a tracked item."""
    opts = opts or ItemShuffleOptions()
    own = ShopWarePlace(potion_shop(overworld), BLUE_POTION_WARE)
    assert own.get() == Item.BLUE_POTION, own.get()
    places = [place for place in pool_places(levels, state, extras, opts) if place.get() != Item.LETTER]
    drawn = exchange_with_drawn(own, places, state, rng)
    extras.shop_wares.append(own)
    extras.shop_items.append(Item.BLUE_POTION)
    price_potion_wares(own, drawn, rng)
    if any(place.slot == own.tracked(Item.NOTHING).slot for place in state.tracked):
        track_the_letter(levels, state, extras, overworld, opts)


def price_potion_wares(own: ShopWarePlace, drawn: PoolPlace | None, rng: IntRng) -> None:
    """SI-PRICE-01's classes for the potion shop's ware; 25-55 for a blue potion in another shop."""
    item = own.get()
    if item != Item.BLUE_POTION and item in PRICES_BY_ITEM:
        own.shop.items[own.position].price = _uniform(rng, PRICES_BY_ITEM[item])
    if isinstance(drawn, ShopWarePlace):
        drawn.shop.items[drawn.position].price = _uniform(rng, BLUE_POTION_PRICES)


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

