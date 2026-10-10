"""Caves: the cave definitions (items, prices, quotes) of each destination."""

from ...model.enums import Destination, Item, ShopType
from ...model.overworld import (
    CaveDefinition,
    DoorRepairCave,
    HintCave,
    HintShop,
    HintShopItem,
    ItemCave,
    MoneyMakingGameCave,
    OverworldItem,
    SecretCave,
    Shop,
    ShopItem,
    TakeAnyCave,
)
from ..layout import CAVE_NOTHING_CODE
from .bin_files import RawBinFiles

# ---------------------------------------------------------------------------
# Cave data parsing
# ---------------------------------------------------------------------------

WARES_PER_CAVE = 3
CAVE_ITEM_CODE_MASK = 0x3F       # a ware byte's item code (top two bits: flags)
QUOTE_ID_MASK = 0x3F             # a quote byte's low six bits hold quote_id * 2
SLOT_FLAGS_MASK = 0xC0           # a hint-shop quote byte's display flags
# A sword cave's heart requirement byte: (hearts - 1) in the high nibble.
HEART_REQUIREMENT_SHIFT = 4
# Each cave's index in the tables (destination $10 + index)
WOOD_SWORD_INDEX, TAKE_ANY_INDEX, WHITE_SWORD_INDEX, MAGICAL_SWORD_INDEX = 0, 1, 2, 3
ANY_ROAD_INDEX, LOST_HILLS_HINT_INDEX, MONEY_MAKING_GAME_INDEX, DOOR_REPAIR_INDEX = 4, 5, 6, 7
LETTER_CAVE_INDEX, DEAD_WOODS_HINT_INDEX, POTION_SHOP_INDEX = 8, 9, 10
HINT_SHOP_INDEXES = (11, 12)
SHOP_INDEXES = ((13, ShopType.SHOP_A), (14, ShopType.SHOP_B), (15, ShopType.SHOP_C), (16, ShopType.SHOP_D))
SECRET_INDEXES = ((17, Destination.MEDIUM_SECRET), (18, Destination.LARGE_SECRET), (19, Destination.SMALL_SECRET))


def _cave_item(raw: int) -> Item:
    """Extract item from a cave data byte (low 6 bits; 0x3F = nothing)."""
    code = raw & CAVE_ITEM_CODE_MASK
    if code == CAVE_NOTHING_CODE:
        return Item.NOTHING
    return Item(code)


def _extra_candle(raw: int) -> Item:
    """Parse optional extra candle item from byte 0 low 6 bits (0x3F = none)."""
    code = raw & CAVE_ITEM_CODE_MASK
    return Item.OVERWORLD_NO_ITEM if code == CAVE_NOTHING_CODE else Item(code)


def _quote_id(quote_byte: int) -> int:
    """The ROM stores quote_id * 2 in the low 6 bits; divide by 2 to get the logical quote index."""
    return (quote_byte & QUOTE_ID_MASK) // 2


def _cave_qid(cave_quotes: bytes, cave_index: int) -> int:
    """Extract quote_id from the cave quotes table (low 6 bits of each byte)."""
    return _quote_id(cave_quotes[cave_index])


def _heart_requirement(requirement: bytes) -> int:
    return (requirement[0] >> HEART_REQUIREMENT_SHIFT) + 1


class _CaveTables:
    """The cave tables as the parser reads them: three ware bytes and three
    prices per cave, the 20-byte cave quote table."""

    def __init__(self, bins: RawBinFiles) -> None:
        self.bins = bins

    def wares(self, index: int) -> tuple[int, int, int]:
        items = self.bins.cave_item_data
        return items[index * 3], items[index * 3 + 1], items[index * 3 + 2]

    def prices(self, index: int) -> tuple[int, int, int]:
        prices = self.bins.cave_price_data
        return prices[index * 3], prices[index * 3 + 1], prices[index * 3 + 2]

    def quote_id(self, index: int) -> int:
        return _cave_qid(self.bins.cave_quotes_data, index)

    def item_cave(self, index: int, heart_requirement: int = 0) -> ItemCave:
        """A cave with an optional extra item in byte 0, its main item in byte 1, nothing in byte 2."""
        extra, main, _ = self.wares(index)
        return ItemCave(destination=_destination(index), item=_cave_item(main), maybe_extra_candle=_extra_candle(extra),
                        quote_id=self.quote_id(index), heart_requirement=heart_requirement)

    def hint_cave(self, index: int) -> HintCave:
        return HintCave(destination=_destination(index), quote_id=self.quote_id(index))

    def hint_shop(self, index: int, slot_quotes: bytes) -> HintShop:
        """Slot quote IDs and flags from the hint-shop quote table's three bytes for this shop."""
        return HintShop(destination=_destination(index), quote_id=self.quote_id(index), hints=[
            HintShopItem(quote_id=_quote_id(quote_byte), price=price, slot_flags=quote_byte & SLOT_FLAGS_MASK)
            for quote_byte, price in zip(slot_quotes, self.prices(index), strict=True)
        ])

    def shop(self, index: int, shop_type: ShopType) -> Shop:
        """Shops A-D: all three items and prices."""
        return Shop(destination=_destination(index), quote_id=self.quote_id(index), shop_type=shop_type,
                    letter_requirement=False,
                    items=[ShopItem(item=_cave_item(ware), price=price)
                           for ware, price in zip(self.wares(index), self.prices(index), strict=True)])


def _destination(index: int) -> Destination:
    return Destination(Destination.WOOD_SWORD_CAVE + index)


def _parse_cave_data(bins: RawBinFiles) -> list[CaveDefinition]:
    """Parse all cave/shop definitions into a list of CaveDefinition instances, in table order."""
    tables = _CaveTables(bins)
    hint_shop_quotes = bins.hint_shop_quotes      # 6 bytes: three slots per hint shop
    left, middle, right = tables.wares(TAKE_ANY_INDEX)
    bet_low, bet_mid, bet_high = tables.prices(MONEY_MAKING_GAME_INDEX)
    potion_left, potion_middle, potion_right = tables.wares(POTION_SHOP_INDEX)
    potion_left_price, potion_middle_price, potion_right_price = tables.prices(POTION_SHOP_INDEX)
    caves: list[CaveDefinition] = [
        tables.item_cave(WOOD_SWORD_INDEX),
        TakeAnyCave(destination=_destination(TAKE_ANY_INDEX), quote_id=tables.quote_id(TAKE_ANY_INDEX),
                    items=[_cave_item(left), _cave_item(middle), _cave_item(right)]),
        tables.item_cave(WHITE_SWORD_INDEX, _heart_requirement(bins.white_sword_requirement)),
        tables.item_cave(MAGICAL_SWORD_INDEX, _heart_requirement(bins.magical_sword_requirement)),
        tables.hint_cave(ANY_ROAD_INDEX),
        tables.hint_cave(LOST_HILLS_HINT_INDEX),
        # bet amounts from the price bytes; win/lose from their own ROM locations
        MoneyMakingGameCave(
            destination=_destination(MONEY_MAKING_GAME_INDEX), quote_id=tables.quote_id(MONEY_MAKING_GAME_INDEX),
            bet_low=bet_low, bet_mid=bet_mid, bet_high=bet_high,
            lose_small=bins.mmg_lose_small[0], lose_small_2=bins.mmg_lose_small_2[0],
            lose_large=bins.mmg_lose_large[0], win_small=bins.mmg_win_small[0], win_large=bins.mmg_win_large[0]
        ),
        DoorRepairCave(destination=_destination(DOOR_REPAIR_INDEX), quote_id=tables.quote_id(DOOR_REPAIR_INDEX),
                       cost=bins.door_repair_charge[0]),
        tables.item_cave(LETTER_CAVE_INDEX),
        tables.hint_cave(DEAD_WOODS_HINT_INDEX),
        # Potion Shop (SHOP_E): items in bytes 0 and 2 only (2-item shop); letter required
        Shop(destination=_destination(POTION_SHOP_INDEX), quote_id=tables.quote_id(POTION_SHOP_INDEX),
             shop_type=ShopType.SHOP_E, letter_requirement=True,
             items=[ShopItem(item=_cave_item(potion_left), price=potion_left_price),
                    ShopItem(item=_cave_item(potion_right), price=potion_right_price)],
             middle=(None if _cave_item(potion_middle) == Item.NOTHING
                     else ShopItem(item=_cave_item(potion_middle), price=potion_middle_price))),
    ]
    for shop_number, index in enumerate(HINT_SHOP_INDEXES):
        start = shop_number * WARES_PER_CAVE
        caves.append(tables.hint_shop(index, hint_shop_quotes[start:start + WARES_PER_CAVE]))
    caves += [tables.shop(index, shop_type) for index, shop_type in SHOP_INDEXES]
    # Secret caves: rupee value in price byte 1
    caves += [SecretCave(destination=destination, quote_id=tables.quote_id(index), rupee_value=tables.prices(index)[1])
              for index, destination in SECRET_INDEXES]
    # Overworld items: no cave table entry, no quote
    caves.append(OverworldItem(destination=Destination.ARMOS_ITEM, item=Item(bins.armos_item[0])))
    caves.append(OverworldItem(destination=Destination.COAST_ITEM, item=Item(bins.coast_item[0]),
                               ladder_requirement=True))
    return caves
