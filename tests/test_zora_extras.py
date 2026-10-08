"""The ZORA extras, unwired (docs/zora-extras.md): Randomize Magical Sword and
Randomize Letter join the major-item pool, and the magical sword's heart
logic. The model is PRG0's levels after the item shuffle (PS-ITEM) with a
fixed stream; a full generation with the flags on waits for the wiring."""
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import pytest

from tests.test_feature_patches import vanilla
from zora.generate.rng import Rng
from zora.generate.steps.extra_pool_items import (
    CaveSlotPlace, ExtraPoolItems, ExtraSlotPlace, ItemCellarPlace, LevelRoomPlace, PoolPlace,
    apply_extra_pool_items, extra_cave, pool_places,
)
from zora.generate.steps.item_shuffle_result import (
    LETTER_SLOT, MAGICAL_SWORD_SLOT, ItemShuffleOptions, ItemShuffleResult,
)
from zora.generate.steps.randomize_letter import randomize_letter
from zora.generate.steps.randomize_magical_sword import (
    count_reachable_heart_containers, has_enough_heart_containers, heart_container_places,
    randomize_magical_sword,
)
from zora.generate.steps.shuffle_items import shuffle_items
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave, OverworldItem, TakeAnyCave
from zora.rom.parse.rom_file import parse_rom

OPTIONS = ItemShuffleOptions()
T = TypeVar("T")


class FixedRng:
    """Draws a chosen value (counted from the top when negative)."""

    def __init__(self, value: int) -> None:
        self.value = value
        self.ranges: list[int] = []

    def below(self, n: int) -> int:
        self.ranges.append(n)
        return self.value % n

    def choice(self, seq: Sequence[T]) -> T:
        return seq[self.below(len(seq))]

    def shuffle(self, items: list[Any]) -> None:
        raise NotImplementedError


def shuffled_world(seed: int = 1) -> tuple[GameWorld, ItemShuffleResult]:
    """PRG0's world after the item shuffle (the item-shuffle step alone)."""
    world = parse_rom(vanilla())
    overworld = world.overworld
    armos = overworld.get_cave(Destination.ARMOS_ITEM, OverworldItem)
    coast = overworld.get_cave(Destination.COAST_ITEM, OverworldItem)
    white_sword = overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    assert armos and coast and white_sword
    state = ItemShuffleResult(caves={"armos": int(armos.item), "white_sword": int(white_sword.item),
                                     "coast": int(coast.item)})
    shuffle_items(world.levels, state, Rng(seed), OPTIONS)
    return world, state


def pool_contents(world: GameWorld, state: ItemShuffleResult, extras: ExtraPoolItems) -> Counter[Item]:
    return Counter(place.get() for place in pool_places(world.levels, state, extras, OPTIONS))


# --- the pool ------------------------------------------------------------------

def test_the_pool_is_the_item_shuffles() -> None:
    world, state = shuffled_world()
    places = pool_places(world.levels, state, ExtraPoolItems(), OPTIONS)
    assert len(places) == state.pool_size
    held = Counter(place.get() for place in places)
    assert held[Item.HEART_CONTAINER] == 9           # eight dungeon hearts and the coast's
    assert Item.MAGICAL_SWORD not in held and Item.LETTER not in held


def test_the_magical_sword_joins_the_pool() -> None:
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    before = pool_contents(world, state, extras)
    rng = FixedRng(5)
    place = randomize_magical_sword(world.levels, state, extras, world.overworld, rng)
    assert rng.ranges == [state.pool_size + 1]       # one draw: the places and the cave itself
    assert place is not None and place.get() == Item.MAGICAL_SWORD
    after = pool_contents(world, state, extras)
    # The pool now holds the sword too; the cave offers the item it displaced.
    assert after == before + Counter({Item.MAGICAL_SWORD: 1})
    assert extras.caves[MAGICAL_SWORD_SLOT] in before
    # The vanilla cave in the overworld is untouched until the pass ships.
    assert extra_cave(world.overworld, MAGICAL_SWORD_SLOT).item == Item.MAGICAL_SWORD


def test_the_displaced_item_keeps_its_tracked_record() -> None:
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    places = pool_places(world.levels, state, extras, OPTIONS)
    tracked_at = next(index for index, place in enumerate(places)
                      if place.get() != Item.HEART_CONTAINER and isinstance(place, LevelRoomPlace))
    displaced = places[tracked_at].get()
    randomize_magical_sword(world.levels, state, extras, world.overworld, FixedRng(tracked_at))
    assert extras.caves[MAGICAL_SWORD_SLOT] == displaced
    records = [place for place in state.tracked if place.item == displaced]
    assert [place.slot for place in records] == [MAGICAL_SWORD_SLOT]
    assert all(place.item != Item.MAGICAL_SWORD for place in state.tracked)


def test_drawing_its_own_cave_leaves_the_sword_there() -> None:
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    before = pool_contents(world, state, extras)
    assert randomize_magical_sword(world.levels, state, extras, world.overworld, FixedRng(-1)) is None
    assert extras.caves == {MAGICAL_SWORD_SLOT: Item.MAGICAL_SWORD}
    assert pool_contents(world, state, extras) == before + Counter({Item.MAGICAL_SWORD: 1})


def test_the_letter_joins_the_pool() -> None:
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    before = pool_contents(world, state, extras)
    place = randomize_letter(world.levels, state, extras, world.overworld, FixedRng(3))
    assert place is not None and place.get() == Item.LETTER
    assert pool_contents(world, state, extras) == before + Counter({Item.LETTER: 1})
    assert extras.caves[LETTER_SLOT] in before


def test_with_both_the_letter_may_take_the_swords_cave() -> None:
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    randomize_magical_sword(world.levels, state, extras, world.overworld, FixedRng(-1))
    places = pool_places(world.levels, state, extras, OPTIONS)
    assert isinstance(places[-1], ExtraSlotPlace) and places[-1].slot == MAGICAL_SWORD_SLOT
    rng = FixedRng(len(places) - 1)
    randomize_letter(world.levels, state, extras, world.overworld, rng)
    assert rng.ranges == [state.pool_size + 2]
    assert extras.caves == {MAGICAL_SWORD_SLOT: Item.LETTER, LETTER_SLOT: Item.MAGICAL_SWORD}


def test_a_forced_cave_slot_keeps_its_item() -> None:
    world, state = shuffled_world()
    forced = ItemShuffleOptions(white_sword_item=1)      # FORCED_ITEM_OPTIONS[1], the book
    places = pool_places(world.levels, state, ExtraPoolItems(), forced)
    assert not any(isinstance(place, CaveSlotPlace) and place.slot == "white_sword" for place in places)
    assert len(places) == state.pool_size - 1


def describe(place: PoolPlace | None) -> tuple[object, ...]:
    if isinstance(place, LevelRoomPlace):
        return ("room", place.level.level_num, place.room.room_num)
    if isinstance(place, ItemCellarPlace):
        return ("cellar", place.level.level_num, place.cellar.room_num)
    if isinstance(place, (CaveSlotPlace, ExtraSlotPlace)):
        return ("cave", place.slot)
    return ("stays",)


def test_draw_k_lands_on_the_kth_place() -> None:
    world, state = shuffled_world()
    expected = [describe(place) for place in pool_places(world.levels, state, ExtraPoolItems(), OPTIONS)]
    expected.append(describe(None))
    landed = []
    for drawn in range(len(expected)):
        world, state = shuffled_world()
        landed.append(describe(randomize_magical_sword(world.levels, state, ExtraPoolItems(), world.overworld,
                                                       FixedRng(drawn))))
    assert landed == expected and len(set(landed)) == len(landed)


def test_shipping_writes_the_caves() -> None:
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    randomize_magical_sword(world.levels, state, extras, world.overworld, FixedRng(0))
    randomize_letter(world.levels, state, extras, world.overworld, FixedRng(1))
    apply_extra_pool_items(world, extras)
    for slot, item in extras.caves.items():
        assert extra_cave(world.overworld, slot).item == item


# --- the heart logic -----------------------------------------------------------------

@dataclass
class ReachAll:
    """Every place reachable except the ones named."""
    unreachable: tuple[PoolPlace, ...] = ()

    def reaches(self, place: PoolPlace) -> bool:
        return place not in self.unreachable


def test_n_minus_m_arithmetic() -> None:
    assert has_enough_heart_containers(12, 3, 9)
    assert not has_enough_heart_containers(12, 3, 8)
    assert has_enough_heart_containers(10, 3, 7)
    assert has_enough_heart_containers(3, 5, 0)


def test_the_check_passes_with_every_heart_reachable() -> None:
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    randomize_magical_sword(world.levels, state, extras, world.overworld, FixedRng(-1))
    places = heart_container_places(world.levels, state, extras)
    reachable = count_reachable_heart_containers(places, ReachAll(), 3, 6)
    assert reachable == 9
    assert has_enough_heart_containers(12, 3, reachable)


def test_the_check_fails_with_one_heart_out_of_reach() -> None:
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    randomize_magical_sword(world.levels, state, extras, world.overworld, FixedRng(-1))
    places = heart_container_places(world.levels, state, extras)
    reachable = count_reachable_heart_containers(places, ReachAll((places[0],)), 3, 6)
    assert not has_enough_heart_containers(12, 3, reachable)
    assert has_enough_heart_containers(11, 3, reachable)


def test_a_heart_in_the_sword_cave_does_not_count() -> None:
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    places = pool_places(world.levels, state, extras, OPTIONS)
    heart = next(index for index, place in enumerate(places) if place.get() == Item.HEART_CONTAINER)
    randomize_magical_sword(world.levels, state, extras, world.overworld, FixedRng(heart))
    assert extras.caves[MAGICAL_SWORD_SLOT] == Item.HEART_CONTAINER
    hearts = heart_container_places(world.levels, state, extras)
    assert len(hearts) == 8
    assert not has_enough_heart_containers(12, 3, count_reachable_heart_containers(hearts, ReachAll(), 3, 6))


def test_take_any_hearts_are_not_pool_places() -> None:
    world, state = shuffled_world()
    take_any = [cave for cave in world.overworld.caves if isinstance(cave, TakeAnyCave)]
    assert take_any and all(Item.HEART_CONTAINER in cave.items for cave in take_any)
    extras = ExtraPoolItems()
    randomize_magical_sword(world.levels, state, extras, world.overworld, FixedRng(-1))
    hearts = heart_container_places(world.levels, state, extras)
    assert all(not isinstance(place, ExtraSlotPlace) or place.slot != MAGICAL_SWORD_SLOT for place in hearts)
    # Two dungeon hearts out of reach: the take-any caves' hearts are not pool places;
    # they count only through the heart check's take-any allowance (tests/test_zora_extras_wired.py).
    reachable = count_reachable_heart_containers(hearts, ReachAll(tuple(hearts[:2])), 3, 6)
    assert reachable == 7
    assert not has_enough_heart_containers(12, 3, reachable)


def test_a_white_sword_cave_heart_counts_once_its_requirement_is_met() -> None:
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    places = pool_places(world.levels, state, extras, OPTIONS)
    heart = next(place for place in places if place.get() == Item.HEART_CONTAINER)
    white_sword = next(place for place in places if isinstance(place, CaveSlotPlace) and place.slot == "white_sword")
    item = white_sword.get()
    white_sword.put(Item.HEART_CONTAINER)
    heart.put(item)
    hearts = heart_container_places(world.levels, state, extras)
    assert white_sword in hearts and len(hearts) == 9
    # 3 + 8 others meet a 6-heart white sword; 1 + 2 others do not meet it.
    assert count_reachable_heart_containers(hearts, ReachAll(), 3, 6) == 9
    few = tuple(place for place in hearts if place is not white_sword)[2:]
    assert count_reachable_heart_containers(hearts, ReachAll(few), 1, 6) == 2


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_pool_is_found_again_after_other_seeds(seed: int) -> None:
    world, state = shuffled_world(seed)
    assert len(pool_places(world.levels, state, ExtraPoolItems(), OPTIONS)) == state.pool_size


# --- Shop Items in the Item Pool (SI-JOIN-01, SI-PRICE-01) ---------------------------------------

from zora.generate.rng import ScriptedRng  # noqa: E402
from zora.generate.steps.extra_pool_items import ShopWarePlace  # noqa: E402
from zora.generate.steps.item_shuffle_result import shop_of_slot, shop_ware_slot  # noqa: E402
from zora.generate.steps.shop_items_in_pool import (  # noqa: E402
    CHEAP_ITEMS, HEART_CONTAINER_PRICES, JOINED_SHOP_ITEMS, NOT_NEEDED_ITEMS, NOT_NEEDED_PRICES, PRICES_BY_ITEM,
    PROGRESSION_ITEMS, PROGRESSION_PRICES, own_shop_ware, price_displaced_wares, shop_items_in_pool,
)
from zora.model.overworld import Shop  # noqa: E402


def _ware_prices(world: GameWorld) -> dict[tuple[Destination, int], tuple[Item, int]]:
    return {(cave.destination, position): (ware.item, ware.price) for cave in world.overworld.caves
            if isinstance(cave, Shop) for position, ware in enumerate(cave.items)}


def test_each_shop_item_is_found_by_what_its_shop_sells() -> None:
    """After B08's stock shuffle the item's ware is wherever the stock put it."""
    world, _ = shuffled_world()
    for item in JOINED_SHOP_ITEMS:
        ware = own_shop_ware(world.overworld, item)
        assert ware.get() == item
    first, second = (cave for cave in world.overworld.caves
                     if isinstance(cave, Shop) and cave.destination in (Destination.SHOP_1, Destination.SHOP_4))
    first.items, second.items = second.items, first.items
    moved = own_shop_ware(world.overworld, Item.BLUE_RING)
    assert moved.get() == Item.BLUE_RING and moved.shop.items is not None


def test_the_three_join_in_order_and_staying_home_keeps_the_prices() -> None:
    """One draw each, among the pool's places, the shop wares joined so far and the item's own
    ware (n + 1, n + 2, n + 3); every draw on the item's own ware leaves the stock and its
    prices as they were. The arrows and the candle are tracked at their wares, the ring not."""
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    before = _ware_prices(world)
    n = state.pool_size
    shop_items_in_pool(world.levels, state, extras, world.overworld, ScriptedRng([n, n + 1, n + 2]))
    assert extras.shop_items == list(JOINED_SHOP_ITEMS)
    assert [ware.get() for ware in extras.shop_wares] == list(JOINED_SHOP_ITEMS)
    assert _ware_prices(world) == before
    shop_records = {place.item: shop_of_slot(place.slot) for place in state.tracked if shop_of_slot(place.slot)}
    assert set(shop_records) == {Item.WOOD_ARROWS, Item.BLUE_CANDLE}
    assert shop_records[Item.WOOD_ARROWS] == own_shop_ware(world.overworld, Item.WOOD_ARROWS).shop.destination
    assert pool_contents(world, state, extras) == pool_contents(world, state, ExtraPoolItems()) + Counter(
        dict.fromkeys(JOINED_SHOP_ITEMS, 1))


def test_draw_k_lands_the_arrows_on_the_kth_place_and_prices_the_displaced_item() -> None:
    """The arrows' draw k exchanges with the pool's k-th place (an inside-out Fisher-Yates step);
    the ware then sells the displaced item at SI-PRICE-01's price, the arrows' record moves to
    the place and the displaced item's record to the ware."""
    world, state = shuffled_world()
    places = pool_places(world.levels, state, ExtraPoolItems(), OPTIONS)
    n = len(places)
    seen = set()
    for drawn in range(n):
        world, state = shuffled_world()
        extras = ExtraPoolItems()
        displaced = pool_places(world.levels, state, extras, OPTIONS)[drawn].get()
        draws = [drawn, n + 1, n + 2, 0]     # the arrows land on place k; the others stay; the price draw
        shop_items_in_pool(world.levels, state, extras, world.overworld, ScriptedRng(draws[:4]))
        ware = extras.shop_wares[0]
        assert ware.get() == displaced
        seen.add(describe(next(place for place in pool_places(world.levels, state, extras, OPTIONS)
                               if place.get() == Item.WOOD_ARROWS)))
        price = ware.shop.items[ware.position].price
        if displaced in PRICES_BY_ITEM:
            assert price == PRICES_BY_ITEM[displaced][0]     # the scripted 0 is the range's low end
        if displaced != Item.HEART_CONTAINER:
            slot = shop_ware_slot(ware.shop.destination, ware.position)
            assert any(place.item == displaced & 0x1F and place.slot == slot for place in state.tracked)
    assert len(seen) == n                        # every place reachable by its own draw


def test_the_candle_may_take_the_arrows_ware() -> None:
    """A joined ware is a pool place for the joins after it."""
    world, state = shuffled_world()
    extras = ExtraPoolItems()
    n = state.pool_size
    arrows_price = own_shop_ware(world.overworld, Item.WOOD_ARROWS)
    kept = arrows_price.shop.items[arrows_price.position].price
    shop_items_in_pool(world.levels, state, extras, world.overworld, ScriptedRng([n, n, n + 2, 3, 7]))
    arrows, candle, ring = extras.shop_wares
    assert (arrows.get(), candle.get(), ring.get()) == (Item.BLUE_CANDLE, Item.WOOD_ARROWS, Item.BLUE_RING)
    assert isinstance(arrows, ShopWarePlace)
    # both are candle-line or arrow-line items, priced 60-80 in join order; the ring stays home
    # and keeps its slot's price
    assert arrows.shop.items[arrows.position].price == PROGRESSION_PRICES[0] + 3 != kept
    assert candle.shop.items[candle.position].price == PROGRESSION_PRICES[0] + 7


# --- SI-PRICE-01, owner revision 6 Oct 2026: the price classes on constructed cases ---------------

def _priced(own: Item, holds: Item, price: int, draws: list[int]) -> int:
    """Price one joined ware whose own item is `own` and which now holds `holds`; the scripted
    RNG raises if the pricing takes more draws than given."""
    world, _ = shuffled_world()
    ware = own_shop_ware(world.overworld, own)
    ware.shop.items[ware.position].price = price
    ware.put(holds)
    extras = ExtraPoolItems(shop_wares=[ware], shop_items=[own])
    price_displaced_wares(extras, ScriptedRng(draws))
    return ware.shop.items[ware.position].price


@pytest.mark.parametrize("item", sorted(PROGRESSION_ITEMS - {Item.WOOD_ARROWS}))
def test_a_progression_item_costs_60_to_80(item: Item) -> None:
    assert _priced(Item.WOOD_ARROWS, item, 10, [0]) == 60
    assert _priced(Item.WOOD_ARROWS, item, 10, [20]) == 80


@pytest.mark.parametrize("item", sorted(NOT_NEEDED_ITEMS - {Item.BLUE_RING}))
def test_an_item_not_needed_to_win_costs_200_to_240(item: Item) -> None:
    assert _priced(Item.BLUE_RING, item, 10, [0]) == 200
    assert _priced(Item.BLUE_RING, item, 10, [40]) == 240


@pytest.mark.parametrize("item", [Item.HEART_CONTAINER, Item.LETTER])
def test_a_heart_container_or_the_letter_costs_20_to_40(item: Item) -> None:
    """The letter is priced like a heart container (owner decision, 6 Oct 2026)."""
    assert _priced(Item.BLUE_CANDLE, item, 10, [0]) == 20
    assert _priced(Item.BLUE_CANDLE, item, 10, [20]) == 40
    assert _priced(Item.BLUE_RING, item, 250, [7]) == 27


@pytest.mark.parametrize("item", [Item.BOMBS, Item.MAGICAL_SHIELD])
def test_anything_else_keeps_the_slots_price_without_a_draw(item: Item) -> None:
    assert _priced(Item.BLUE_CANDLE, item, 37, []) == 37


def test_an_item_at_home_keeps_its_price_without_a_draw() -> None:
    assert _priced(Item.BLUE_RING, Item.BLUE_RING, 37, []) == 37


def test_the_classes_are_disjoint_and_match_the_owner_list() -> None:
    assert not PROGRESSION_ITEMS & NOT_NEEDED_ITEMS and not CHEAP_ITEMS & (PROGRESSION_ITEMS | NOT_NEEDED_ITEMS)
    assert CHEAP_ITEMS == {Item.HEART_CONTAINER, Item.LETTER}
    assert PROGRESSION_PRICES == (60, 80) and NOT_NEEDED_PRICES == (200, 240) and HEART_CONTAINER_PRICES == (20, 40)
