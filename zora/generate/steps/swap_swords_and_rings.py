"""Swap Swords and Rings (features-behavior.md FP-SWAP-01 to FP-SWAP-05; BogieSmalls', used with
his permission, 2026-10-29; docs/zora-extras.md section 23): the White Sword and the Blue Ring exchange
places, and so do the Magical Sword and the Red Ring.

After every pass that places an item or stocks a shop (the ZORA extras' joins included), and before the
acceptance walk and the hints, every placed item is exchanged by its code wherever it lies: a level room, an
item cellar, the Armos, coast and white-sword slots, an extra's cave, any other one-item cave and every shop
ware. Only the item changes (FP-SWAP-05): a room keeps its dark and sound bits (Room.item is the low five
bits), a shop ware its price and slot flags, a cave its flags, text and heart requirement (FP-SWAP-02). The
pins were placed before (FP-SWAP-04) and are not rewritten.

The tracked records (VA-REJ-07) follow the items, so the walk and the hints see what is actually where: a
record of the White Sword moves to the place that now holds it, a shop ware's record named by its slot
(item_shuffle_result.shop_ware_slot), which the walk collects once a door of the shop is reached.

A pair either of whose items is a starting item (FP-SWAP-01: B69, B70 or any other) is not swapped; nor,
defensively, a pair one of whose items is placed nowhere, which would leave the other item without a place.
The take-any cave's fixed stock (a potion, a candle and a heart container) never holds these items and is
left out.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ...model.enums import Destination, Item
from ...model.levels import Level
from ...model.overworld import POTION_SHOP_MIDDLE, POTION_SHOP_WARES, ItemCave, Overworld, Shop
from .extra_pool_items import (
    CaveSlotPlace,
    ExtraPoolItems,
    ExtraSlotPlace,
    PoolPlace,
    ShopWarePlace,
    dungeon_places,
)
from .item_shuffle_result import EXTRA_SLOT_CAVES, ItemShuffleResult, TrackedPlace
from .shuffle_items import CAVE_SLOTS

# FP-SWAP-01's two pairs
SWAPPED_PAIRS: tuple[tuple[Item, Item], ...] = ((Item.WHITE_SWORD, Item.BLUE_RING),
                                                (Item.MAGICAL_SWORD, Item.RED_RING))
SLOT_OF_CAVE = {destination: slot for slot, destination in EXTRA_SLOT_CAVES.items()}


@dataclass
class OneItemCavePlace(PoolPlace):
    """A one-item cave no pass stages apart (the magical-sword cave without Randomize Magical Sword, the letter
    cave without Randomize Letter, the wooden-sword cave): its item, on the pass's staged overworld, which
    ships whole. Its record is its extra's slot, which the walk collects as it does that extra's cave."""
    cave: ItemCave

    def get(self) -> Item:
        return self.cave.item

    def put(self, item: Item) -> None:
        self.cave.item = item

    def tracked(self, item: Item) -> TrackedPlace:
        return TrackedPlace(item, slot=SLOT_OF_CAVE[self.cave.destination])


def shop_ware_positions(shop: Shop) -> Iterable[int]:
    """The ware positions a shop sells: 0 to 2, or the potion shop's two and its middle ware when set."""
    if shop.destination != Destination.POTION_SHOP:
        return range(len(shop.items))
    return (*POTION_SHOP_WARES, *((POTION_SHOP_MIDDLE,) if shop.middle is not None else ()))


def item_holders(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                 overworld: Overworld) -> list[PoolPlace]:
    """Every place that holds an item before the attempt ships, each once, in a fixed order: the dungeon
    places, the special-cave slots (staged in the item shuffle's result), the extras' caves (staged in
    ExtraPoolItems), the other one-item caves and every shop ware (on the staged overworld)."""
    holders: list[PoolPlace] = list(dungeon_places(levels))
    holders += [CaveSlotPlace(slot, state) for slot in CAVE_SLOTS]
    holders += [ExtraSlotPlace(slot, extras) for slot in extras.caves]
    staged = {EXTRA_SLOT_CAVES[slot] for slot in extras.caves} | {Destination.WHITE_SWORD_CAVE}
    for cave in overworld.caves:
        if isinstance(cave, ItemCave) and cave.destination in SLOT_OF_CAVE and cave.destination not in staged:
            holders.append(OneItemCavePlace(cave))
        elif isinstance(cave, Shop):
            holders += [ShopWarePlace(cave, position) for position in shop_ware_positions(cave)]
    return holders


def swapped_pairs(start_items: Iterable[Item], holders: list[PoolPlace]) -> list[tuple[Item, Item]]:
    """FP-SWAP-01: the pairs that are swapped: neither item a starting item, and both placed somewhere."""
    starting = set(start_items)
    placed = {holder.get() for holder in holders}
    return [pair for pair in SWAPPED_PAIRS if not starting & set(pair) and set(pair) <= placed]


def swap_swords_and_rings(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                          overworld: Overworld, start_items: Iterable[Item]) -> list[tuple[Item, Item]]:
    """FP-SWAP-01: exchange the pairs' items by code in every place, and move each of their tracked records to
    the place that now holds its item. Returns the pairs swapped."""
    holders = item_holders(levels, state, extras, overworld)
    pairs = swapped_pairs(start_items, holders)
    other = {first: second for pair in pairs for first, second in (pair, pair[::-1])}
    # where each code lies before the swap, in holder order
    lying = {code: [holder for holder in holders if holder.get() == code] for code in other}
    for index, record in enumerate(state.tracked):
        item = Item(record.item)
        if item not in other:
            continue
        found = next((place for place, holder in enumerate(lying[item]) if holder.tracked(item) == record), 0)
        # the item now lies where its partner lay (the same position among the partner's places)
        partner_places = lying[other[item]]
        state.tracked[index] = partner_places[found % len(partner_places)].tracked(item)
    for code, places in lying.items():
        for holder in places:
            holder.put(other[code])
    return pairs
