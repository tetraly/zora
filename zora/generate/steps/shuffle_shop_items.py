"""The shops: stock shuffle, price jitter, the six extra price bytes, the
two extra candles and the front-door guarantees (overworld-behavior.md
OW-SHOP-01..06), on a GameWorld's Overworld model.

The slot flags (the third ware of each shop carries $C0) belong to the
slot; the serializer writes them, so only (item, price) pairs move here.
"""
from zora.generate.rng import IntRng
from zora.generate.steps.cave_entries import (
    BRACELET_SCREENS,
    BURNABLE_SCREENS,
    LADDER_SCREENS,
    RAFT_SCREENS,
    RECORDER_SCREENS,
    CaveShuffle,
)
from zora.model.enums import Destination, Item
from zora.model.overworld import DoorRepairCave, ItemCave, Overworld, SecretCave, Shop, ShopItem, TakeAnyCave

SHOPS = (Destination.SHOP_1, Destination.SHOP_2, Destination.SHOP_3, Destination.SHOP_4)
WARES_PER_SHOP = 3
JITTER = 20                           # OW-SHOP-03: d uniform in [-20, +20]
PRICE_FLOOR, PRICE_CEILING = 0, 255   # a jitter landing on either is undone
# OW-SHOP-04: inclusive ranges of the six extra price bytes
POTION_PRICES = ((25, 55), (48, 88))  # 0x1866A, 0x1866C: code 26 wares 0 and 2
SECRET_AMOUNTS = ((Destination.MEDIUM_SECRET, (25, 40)),    # 0x18680, code 33
                  (Destination.LARGE_SECRET, (50, 150)),    # 0x18683, code 34
                  (Destination.SMALL_SECRET, (1, 20)))      # 0x18686, code 35
DOOR_REPAIR_CHARGE = (15, 25)         # 0x048A0, bank 1 $8890
TAKE_ANY_CANDLE_SLOT = 1              # OW-SHOP-05: cave index 1, ware 1
# OW-SHOP-06: screens the candle and arrow shops' front doors must avoid
CANDLE_DOOR_BARRED = RAFT_SCREENS | RECORDER_SCREENS | LADDER_SCREENS | BRACELET_SCREENS \
    | BURNABLE_SCREENS
ARROW_DOOR_BARRED = RAFT_SCREENS | RECORDER_SCREENS | LADDER_SCREENS | BRACELET_SCREENS


def _cave(overworld: Overworld, destination: Destination) -> object:
    cave = next((c for c in overworld.caves if c.destination == destination), None)
    assert cave is not None, destination
    return cave


def _shops(overworld: Overworld) -> list[Shop]:
    shops = []
    for destination in SHOPS:
        shop = _cave(overworld, destination)
        assert isinstance(shop, Shop) and len(shop.items) == WARES_PER_SHOP
        shops.append(shop)
    return shops


def _uniform(rng: IntRng, low: int, high: int) -> int:
    return low + rng.below(high - low + 1)


def _distinct_per_shop(pairs: list[ShopItem]) -> bool:
    return all(len({pair.item for pair in pairs[k:k + WARES_PER_SHOP]}) == WARES_PER_SHOP
               for k in range(0, len(pairs), WARES_PER_SHOP))


def shuffle_stock(pairs: list[ShopItem], rng: IntRng) -> None:
    """OW-SHOP-02: Fisher-Yates walks over the twelve pairs (j from i..11),
    each run on the current arrangement, until every shop's items are
    distinct."""
    while True:
        for i in range(len(pairs) - 1):
            j = i + rng.below(len(pairs) - i)
            pairs[i], pairs[j] = pairs[j], pairs[i]
        if _distinct_per_shop(pairs):
            return


def jitter_prices(pairs: list[ShopItem], rng: IntRng) -> None:
    """OW-SHOP-03: shift each price by d in [-20, +20], slot order; a shift
    landing at 0 or below, or 255 or above, is undone, not clamped."""
    for pair in pairs:
        price = pair.price + rng.below(2 * JITTER + 1) - JITTER
        if PRICE_FLOOR < price < PRICE_CEILING:
            pair.price = price


def redraw_extra_prices(overworld: Overworld, rng: IntRng) -> None:
    """OW-SHOP-04: six price bytes redrawn uniformly over their ranges, in
    the spec's order. Which purchase each prices is OW-K-04."""
    potion = _cave(overworld, Destination.POTION_SHOP)
    assert isinstance(potion, Shop)
    for ware, (low, high) in zip(potion.items, POTION_PRICES, strict=True):
        ware.price = _uniform(rng, low, high)
    for destination, (low, high) in SECRET_AMOUNTS:
        secret = _cave(overworld, destination)
        assert isinstance(secret, SecretCave)
        secret.rupee_value = _uniform(rng, low, high)
    repair = _cave(overworld, Destination.DOOR_REPAIR)
    assert isinstance(repair, DoorRepairCave)
    repair.cost = _uniform(rng, *DOOR_REPAIR_CHARGE)


def extra_candles(overworld: Overworld) -> None:
    """Extra Candles (B09; OW-SHOP-05): the blue candle in the wooden-sword cave's ware 0 and the
    code-17 cave's ware 1 (not shop stock)."""
    wood_sword = _cave(overworld, Destination.WOOD_SWORD_CAVE)
    take_any = _cave(overworld, Destination.TAKE_ANY)
    assert isinstance(wood_sword, ItemCave) and isinstance(take_any, TakeAnyCave)
    wood_sword.maybe_extra_candle = Item.BLUE_CANDLE
    take_any.items[TAKE_ANY_CANDLE_SLOT] = Item.BLUE_CANDLE


def shuffle_shop_items(overworld: Overworld, rng: IntRng) -> None:
    """Shuffle Shop Items (B08; OW-SHOP-02..04, in order)."""
    shops = _shops(overworld)
    pairs = [ShopItem(ware.item, ware.price) for shop in shops for ware in shop.items]
    shuffle_stock(pairs, rng)
    jitter_prices(pairs, rng)
    for k, shop in enumerate(shops):
        shop.items = pairs[k * WARES_PER_SHOP:(k + 1) * WARES_PER_SHOP]
    redraw_extra_prices(overworld, rng)


def _shop_selling(overworld: Overworld, item: Item) -> Destination:
    sellers = [shop.destination for shop in _shops(overworld)
               if any(ware.item == item for ware in shop.items)]
    assert len(sellers) == 1, f"{item.name} sold by {sellers}"
    return sellers[0]


def front_door_failure(overworld: Overworld, caves: CaveShuffle,
                       also_barred: frozenset[int] = frozenset()) -> str | None:
    """OW-SHOP-06: the candle shop (a) and the arrow shop (b) each need a
    movable entrance off their barred screen sets. Returns the guarantee
    that fails, or None. also_barred: the owner's 2.0 gated screens, barred too."""
    for label, item, barred in (("(a) candle", Item.BLUE_CANDLE, CANDLE_DOOR_BARRED | also_barred),
                                ("(b) arrow", Item.WOOD_ARROWS, ARROW_DOOR_BARRED | also_barred)):
        doors = caves.movable_screens(_shop_selling(overworld, item))
        if not any(screen not in barred for screen in doors):
            return label
    return None
