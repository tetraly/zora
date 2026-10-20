"""Shuffle Wood Sword (a ZORA 1.0 flag recreated as a ZORA extra, owner design 2026-10-17;
docs/zora-extras.md section 13). Not Shuffle Wood Sword Cave (B02), which moves the cave: this
moves the sword.

After every other join (the last of them is Add L4 Sword = Level 2's, whose cellar sword has the
wood sword's item code, so it must join first):
  - the wood sword joins the major-item pool from its cave (the extras' join step), so the cave
    becomes a pool place; it is a tracked item, which the logic no longer counts as held from the
    start (LogicRules.wood_sword_in_pool);
  - the sword-or-wand guarantee (owner's choice: only with this flag on, never with Randomize
    Letter alone): one weapon is put in a cave the player can walk into at the start, the wood
    sword cave if its entrance is open, else the letter cave if Randomize Letter put it in the
    pool and its entrance is open. The weapon is drawn evenly from the swords in the pool and the
    wand; it exchanges places with the cave's item (a shop ware that takes the cave's item is
    priced again by SI-PRICE-01's classes), and the cave is pinned. With no open cave the
    attempt restarts, as for any restart.
An entrance is open when its screen is one the wood-sword cave may start on (OW-APP-A3, the
screens the player walks into from the start) and the logic asks nothing for it (the owner's
overworld gates).
"""
from __future__ import annotations

from ...model.enums import Destination, Item
from ...model.levels import Level
from ...model.overworld import POTION_SHOP_MIDDLE, Overworld
from ..acceptance_check import LogicRules
from ..errors import GenerationFailure
from ..rng import IntRng
from .cave_entries import WOOD_SWORD_SCREENS, CaveShuffle
from .extra_pool_items import ExtraPoolItems, ExtraSlotPlace, ShopWarePlace, exchange, join_pool, pool_places
from .item_shuffle_result import LETTER_SLOT, WOOD_SWORD_SLOT, ItemShuffleOptions, ItemShuffleResult
from .shop_items_in_pool import PRICES_BY_ITEM

# The weapons the guarantee draws from, those of them in the pool: the swords and the wand.
WEAPONS = (Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.WAND)
NO_OPEN_CAVE = "no open cave for the starting weapon"
# The caves the guarantee may fill, in the order it tries them.
WEAPON_CAVES = ((WOOD_SWORD_SLOT, Destination.WOOD_SWORD_CAVE), (LETTER_SLOT, Destination.LETTER_CAVE))


def is_open(screen: int, rules: LogicRules) -> bool:
    """A cave entrance the player walks into from the start: an OW-APP-A3 screen that needs
    nothing (no overworld gate)."""
    return screen in WOOD_SWORD_SCREENS and not rules.needs(screen)


def shuffle_wood_sword(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems, overworld: Overworld,
                       caves: CaveShuffle, rules: LogicRules, rng: IntRng,
                       opts: ItemShuffleOptions | None = None) -> None:
    """The join, then the guarantee."""
    opts = opts or ItemShuffleOptions()
    join_pool(WOOD_SWORD_SLOT, levels, state, extras, overworld, rng, opts, tracked=True)
    place_starting_weapon(levels, state, extras, caves, rules, rng, opts)


def place_starting_weapon(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                          caves: CaveShuffle, rules: LogicRules, rng: IntRng, opts: ItemShuffleOptions) -> None:
    """The sword-or-wand guarantee: the first open weapon cave of the pool, a weapon drawn
    evenly from those in the pool, the two exchanged, the cave pinned."""
    target = next((ExtraSlotPlace(slot, extras) for slot, cave in WEAPON_CAVES
                   if slot in extras.caves and (screens := caves.movable_screens(cave))
                   and is_open(screens[0], rules)), None)
    if target is None:
        raise GenerationFailure(NO_OPEN_CAVE)
    # the potion shop opens only with the letter, so it never takes the letter cave's letter
    letter_held = target.get() == Item.LETTER
    places = [place for place in pool_places(levels, state, extras, opts) if place.get() in WEAPONS
              and not (letter_held and isinstance(place, ShopWarePlace) and place.position == POTION_SHOP_MIDDLE
                       and place.shop.destination == Destination.POTION_SHOP)]
    weapons = [weapon for weapon in WEAPONS if any(place.get() == weapon for place in places)]
    weapon = weapons[rng.below(len(weapons))]
    holder = next(place for place in places if place.get() == weapon)
    if not (isinstance(holder, ExtraSlotPlace) and holder.slot == target.slot):
        exchange(target, holder, state)
        if isinstance(holder, ShopWarePlace):
            price_ware(holder, extras, rng)
    extras.pinned.add(target.slot)


def price_ware(ware: ShopWarePlace, extras: ExtraPoolItems, rng: IntRng) -> None:
    """SI-PRICE-01 for a joined ware that took a new item: by the item's class, else its slot price."""
    item = ware.get()
    if item in PRICES_BY_ITEM:
        low, high = PRICES_BY_ITEM[item]
        ware.shop.ware(ware.position).price = low + rng.below(high - low + 1)
    else:
        joined = next(index for index, joined_ware in enumerate(extras.shop_wares)
                      if joined_ware.shop is ware.shop and joined_ware.position == ware.position)
        ware.shop.ware(ware.position).price = extras.slot_prices[joined]
