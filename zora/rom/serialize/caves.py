"""Caves: the cave definitions, the money-making game's prizes and the bomb upgrade."""

from ...model.enums import Destination, Item
from ...model.overworld import (
    CaveDefinition,
    DoorRepairCave,
    HintShop,
    ItemCave,
    MoneyMakingGameCave,
    Overworld,
    OverworldItem,
    SecretCave,
    Shop,
    TakeAnyCave,
)
from ..layout import (
    ARMOS_ITEM_ADDRESS,
    BOMB_COST_OFFSET,
    BOMB_COUNT_OFFSET,
    BOMB_DISP_BASE,
    BOMB_DISPLAY_SPACE_TILE,
    CAVE_ITEM_DATA_ADDRESS,
    CAVE_NOTHING_CODE,
    CAVE_PRICE_DATA_ADDRESS,
    CAVE_QUOTES_DATA_ADDRESS,
    COAST_ITEM_ADDRESS,
    DOOR_REPAIR_CHARGE_ADDRESS,
    HINT_SHOP_QUOTES_ADDRESS,
    MAGICAL_SWORD_REQUIREMENT_ADDRESS,
    MMG_LOSE_LARGE_OFFSET,
    MMG_LOSE_SMALL_2_OFFSET,
    MMG_LOSE_SMALL_OFFSET,
    MMG_WIN_LARGE_OFFSET_A,
    MMG_WIN_LARGE_OFFSET_B,
    MMG_WIN_LARGE_OFFSET_C,
    MMG_WIN_SMALL_OFFSET_A,
    MMG_WIN_SMALL_OFFSET_B,
    MMG_WIN_SMALL_OFFSET_C,
    WHITE_SWORD_REQUIREMENT_ADDRESS,
)
from .patch import Patch

# ---------------------------------------------------------------------------
# Cave data serialization
# ---------------------------------------------------------------------------

# The cave ware tables: 20 caves (destination $10 + index) of three wares each.
CAVE_COUNT = 20
WARES_PER_CAVE = 3
# Flag bits of the three ware bytes, derived from the cave type, not stored in the model.
NEGATIVE_PRICES = 0x80       # byte 0
HEART_CONDITION = 0x40       # byte 0: the cave asks for hearts
RUPEES_CHANGE = 0x80         # byte 1: rupees received or lost
PAY_FOR_HINT = 0x40          # byte 1
PRICES_DISPLAYED = 0x80      # byte 2
ITEMS_DISPLAYED = 0x40       # byte 2
SLOT_SENTINEL = 0x18         # the item code of a ware slot that sells a hint or a bet
EXTERNAL_MARKER = 0x7F       # byte 2 of a cave whose item lives outside the table
_NOTHING = CAVE_NOTHING_CODE   # 0x3F = unused slot
CAVE_ITEM_CODE_MASK = 0x3F
# Each cave's index in the tables
WOOD_SWORD_INDEX, TAKE_ANY_INDEX, WHITE_SWORD_INDEX, MAGICAL_SWORD_INDEX = 0, 1, 2, 3
HINT_ONLY_INDEXES = (4, 5, 9)          # Any Road, Lost Hills hint, Dead Woods hint
MONEY_MAKING_GAME_INDEX, DOOR_REPAIR_INDEX, LETTER_CAVE_INDEX, POTION_SHOP_INDEX = 6, 7, 8, 10
HINT_SHOP_INDEXES = ((11, Destination.HINT_SHOP_1), (12, Destination.HINT_SHOP_2))
SHOP_INDEXES = ((13, Destination.SHOP_1), (14, Destination.SHOP_2), (15, Destination.SHOP_3),
                (16, Destination.SHOP_4))
SECRET_INDEXES = ((17, Destination.MEDIUM_SECRET), (18, Destination.LARGE_SECRET), (19, Destination.SMALL_SECRET))
# A sword cave's heart requirement byte: (hearts - 1) in the high nibble.
HEARTS_PER_REQUIREMENT_STEP = 16

# Cave quote ID table (20 bytes): the low 6 bits per slot are quote_id * 2;
# the top 2 bits are display flags owned by the ROM engine. These constants
# must contain ONLY the top-2-bit flags (& 0xC0), not the full vanilla byte,
# or old quote_id bits leak through the OR.
CAVE_QUOTE_DISPLAY_FLAGS = (
    0x40,  # 0  Wood Sword
    0x40,  # 1  Take Any
    0x40,  # 2  White Sword
    0x40,  # 3  Magical Sword
    0x00,  # 4  Any Road
    0x00,  # 5  Lost Hills Hint
    0x40,  # 6  MMG
    0x00,  # 7  Door Repair
    0x40,  # 8  Letter Cave
    0x00,  # 9  Dead Woods Hint
    0xC0,  # 10 Potion Shop
    0xC0,  # 11 Hint Shop 1
    0xC0,  # 12 Hint Shop 2
    0xC0,  # 13 Shop 1
    0xC0,  # 14 Shop 2
    0xC0,  # 15 Shop 3
    0xC0,  # 16 Shop 4
    0x40,  # 17 Medium Secret
    0x40,  # 18 Large Secret
    0x40,  # 19 Small Secret
)
QUOTE_ID_MASK = 0x3F
HINT_SHOP_QUOTE_SLOTS = 6


def _item_code(item: Item) -> int:
    """Encode an Item as a 6-bit cave item code. NOTHING → CAVE_NOTHING_CODE."""
    return CAVE_NOTHING_CODE if item == Item.NOTHING else (item.value & CAVE_ITEM_CODE_MASK)


def _quote_byte(flags: int, quote_id: int) -> int:
    return flags | ((quote_id * 2) & QUOTE_ID_MASK)


def _serialize_cave_data(overworld: Overworld, patch: "Patch") -> None:
    """
    Build 60-byte item and price buffers from scratch using the caves list,
    write the cave quote ID table, hint shop slot quote ID table, and
    door repair charge to patch.

    Flag bits in item bytes are fully determined by cave type — no raw bytes
    needed. Layout matches ROM table at CAVE_ITEM_DATA_ADDRESS.
    """
    cave_by_dest: dict[Destination, CaveDefinition] = {c.destination: c for c in overworld.caves}
    items, prices = cave_ware_tables(cave_by_dest)
    patch.add(CAVE_ITEM_DATA_ADDRESS,  bytes(items))
    patch.add(CAVE_PRICE_DATA_ADDRESS, bytes(prices))
    _serialize_cave_values(cave_by_dest, patch)
    patch.add(CAVE_QUOTES_DATA_ADDRESS, cave_quote_table(cave_by_dest))
    patch.add(HINT_SHOP_QUOTES_ADDRESS, hint_shop_quote_table(cave_by_dest))


def cave_ware_tables(cave_by_dest: dict[Destination, CaveDefinition]) -> tuple[bytearray, bytearray]:
    """The 60-byte item and price tables, cave by cave in table order."""
    items = bytearray(CAVE_COUNT * WARES_PER_CAVE)
    prices = bytearray(CAVE_COUNT * WARES_PER_CAVE)
    get = cave_by_dest.get

    # Wood Sword — byte 0 = optional extra item, byte 1 = main item, byte 2 = nothing
    if c := get(Destination.WOOD_SWORD_CAVE):
        assert isinstance(c, ItemCave)
        _write_item_cave(items, WOOD_SWORD_INDEX, c, heart_flag=0)
    # Take Any — byte 0 = left item, byte 1 = middle item, byte 2 = right item
    if c := get(Destination.TAKE_ANY):
        assert isinstance(c, TakeAnyCave)
        _write_wares(items, TAKE_ANY_INDEX, _item_code(c.items[0]), _item_code(c.items[1]),
                     ITEMS_DISPLAYED | _item_code(c.items[2]))
    # White and Magical Sword — byte 0 = heart flag | optional extra item, byte 1 = main item
    for index, destination in ((WHITE_SWORD_INDEX, Destination.WHITE_SWORD_CAVE),
                               (MAGICAL_SWORD_INDEX, Destination.MAGICAL_SWORD_CAVE)):
        if c := get(destination):
            assert isinstance(c, ItemCave)
            _write_item_cave(items, index, c, heart_flag=HEART_CONDITION if c.heart_requirement > 0 else 0)
    # Any Road, Lost Hills hint, Door Repair, Dead Woods hint — all nothing
    # (the door repair's price lives at its own address)
    for index in (*HINT_ONLY_INDEXES, DOOR_REPAIR_INDEX):
        _write_wares(items, index, _NOTHING, _NOTHING, _NOTHING)
    # Money Making Game — all nothing in items; prices = bet amounts
    if c := get(Destination.MONEY_MAKING_GAME):
        assert isinstance(c, MoneyMakingGameCave)
        _write_wares(items, MONEY_MAKING_GAME_INDEX, NEGATIVE_PRICES | SLOT_SENTINEL, RUPEES_CHANGE | SLOT_SENTINEL,
                     PRICES_DISPLAYED | ITEMS_DISPLAYED | SLOT_SENTINEL)
        _write_wares(prices, MONEY_MAKING_GAME_INDEX, c.bet_low, c.bet_mid, c.bet_high)
    # Letter Cave — slot 1 = item
    if c := get(Destination.LETTER_CAVE):
        assert isinstance(c, ItemCave)
        _write_wares(items, LETTER_CAVE_INDEX, _NOTHING, _item_code(c.item), ITEMS_DISPLAYED | EXTERNAL_MARKER)
    # Potion Shop (SHOP_E) — slots 0,2 = items; slot 1 empty unless Shuffle Blue Potion fills it;
    # letter required
    if c := get(Destination.POTION_SHOP):
        assert isinstance(c, Shop)
        middle_item = _NOTHING if c.middle is None else _item_code(c.middle.item)
        middle_price = 0x00 if c.middle is None else c.middle.price
        _write_wares(items, POTION_SHOP_INDEX, _item_code(c.items[0].item), middle_item,
                     PRICES_DISPLAYED | ITEMS_DISPLAYED | _item_code(c.items[1].item))
        _write_wares(prices, POTION_SHOP_INDEX, c.items[0].price, middle_price, c.items[1].price)
    # Hint Shops — prices only; item bytes use the slot sentinel
    for index, destination in HINT_SHOP_INDEXES:
        if c := get(destination):
            assert isinstance(c, HintShop)
            _write_wares(items, index, NEGATIVE_PRICES | SLOT_SENTINEL, PAY_FOR_HINT | SLOT_SENTINEL,
                         PRICES_DISPLAYED | ITEMS_DISPLAYED | SLOT_SENTINEL)
            _write_wares(prices, index, c.hints[0].price, c.hints[1].price, c.hints[2].price)
    # Shops A-D — all 3 item slots used
    for index, destination in SHOP_INDEXES:
        if c := get(destination):
            assert isinstance(c, Shop)
            _write_wares(items, index, _item_code(c.items[0].item), _item_code(c.items[1].item),
                         PRICES_DISPLAYED | ITEMS_DISPLAYED | _item_code(c.items[2].item))
            _write_wares(prices, index, c.items[0].price, c.items[1].price, c.items[2].price)
    # Secrets — rupee value in price byte 1; item bytes carry the rupees flag
    for index, destination in SECRET_INDEXES:
        if c := get(destination):
            assert isinstance(c, SecretCave)
            _write_wares(items, index, _NOTHING, RUPEES_CHANGE | SLOT_SENTINEL, ITEMS_DISPLAYED | EXTERNAL_MARKER)
            prices[index * WARES_PER_CAVE + 1] = c.rupee_value
    return items, prices


def _write_wares(table: bytearray, cave_index: int, first: int, second: int, third: int) -> None:
    start = cave_index * WARES_PER_CAVE
    table[start:start + WARES_PER_CAVE] = bytes((first, second, third))


def _write_item_cave(items: bytearray, cave_index: int, cave: ItemCave, heart_flag: int) -> None:
    """A cave with one main item (and an optional extra candle): byte 2 marks the item as external."""
    _write_wares(items, cave_index, heart_flag | _item_code(cave.maybe_extra_candle), _item_code(cave.item),
                 ITEMS_DISPLAYED | EXTERNAL_MARKER)


def _serialize_cave_values(cave_by_dest: dict[Destination, CaveDefinition], patch: Patch) -> None:
    """The cave values at their own ROM addresses: the door repair charge, the
    Armos and coast items and the sword caves' heart requirements."""
    if c := cave_by_dest.get(Destination.DOOR_REPAIR):
        assert isinstance(c, DoorRepairCave)
        patch.add(DOOR_REPAIR_CHARGE_ADDRESS, bytes([c.cost]))
    for destination, address in ((Destination.ARMOS_ITEM, ARMOS_ITEM_ADDRESS),
                                 (Destination.COAST_ITEM, COAST_ITEM_ADDRESS)):
        if c := cave_by_dest.get(destination):
            assert isinstance(c, OverworldItem)
            patch.add(address, bytes([c.item.value]))
    for destination, address in ((Destination.WHITE_SWORD_CAVE, WHITE_SWORD_REQUIREMENT_ADDRESS),
                                 (Destination.MAGICAL_SWORD_CAVE, MAGICAL_SWORD_REQUIREMENT_ADDRESS)):
        if c := cave_by_dest.get(destination):
            assert isinstance(c, ItemCave)
            patch.add(address, bytes([(c.heart_requirement - 1) * HEARTS_PER_REQUIREMENT_STEP]))


def cave_quote_table(cave_by_dest: dict[Destination, CaveDefinition]) -> bytes:
    """The cave quote ID table: each cave's display flags and quote."""
    quote_table = bytearray(CAVE_COUNT)
    for cave_idx in range(CAVE_COUNT):
        c = cave_by_dest.get(Destination(Destination.WOOD_SWORD_CAVE + cave_idx))
        qid = getattr(c, "quote_id", 0) if c is not None else 0
        quote_table[cave_idx] = _quote_byte(CAVE_QUOTE_DISPLAY_FLAGS[cave_idx], qid)
    return bytes(quote_table)


def hint_shop_quote_table(cave_by_dest: dict[Destination, CaveDefinition]) -> bytes:
    """The hint shops' slot quote ID table (6 bytes): three slots per shop."""
    hint_shop_quotes = bytearray(HINT_SHOP_QUOTE_SLOTS)
    for shop_number, (_index, destination) in enumerate(HINT_SHOP_INDEXES):
        shop = cave_by_dest.get(destination)
        if shop is not None:
            assert isinstance(shop, HintShop)
            for slot, hint in enumerate(shop.hints[:WARES_PER_CAVE]):
                hint_shop_quotes[shop_number * WARES_PER_CAVE + slot] = _quote_byte(hint.slot_flags, hint.quote_id)
    return bytes(hint_shop_quotes)


# ---------------------------------------------------------------------------
# MMG prize serialization
# ---------------------------------------------------------------------------

def _serialize_mmg_prizes(overworld: Overworld, patch: Patch) -> None:
    """Write MMG win/lose amounts to all 9 patch locations."""
    cave_by_dest = {c.destination: c for c in overworld.caves}
    c = cave_by_dest.get(Destination.MONEY_MAKING_GAME)
    if c is None:
        return
    assert isinstance(c, MoneyMakingGameCave)
    patch.add(MMG_LOSE_SMALL_OFFSET,   bytes([c.lose_small]))
    patch.add(MMG_LOSE_SMALL_2_OFFSET, bytes([c.lose_small_2]))
    patch.add(MMG_LOSE_LARGE_OFFSET,   bytes([c.lose_large]))
    patch.add(MMG_WIN_SMALL_OFFSET_A,  bytes([c.win_small]))
    patch.add(MMG_WIN_SMALL_OFFSET_B,  bytes([c.win_small]))
    patch.add(MMG_WIN_SMALL_OFFSET_C,  bytes([c.win_small]))
    patch.add(MMG_WIN_LARGE_OFFSET_A,  bytes([c.win_large]))
    patch.add(MMG_WIN_LARGE_OFFSET_B,  bytes([c.win_large]))
    patch.add(MMG_WIN_LARGE_OFFSET_C,  bytes([c.win_large]))


# ---------------------------------------------------------------------------
# Bomb upgrade serialization
# ---------------------------------------------------------------------------

def _serialize_bomb_upgrade(overworld: Overworld, patch: Patch) -> None:
    """Write bomb upgrade cost, count, and display tiles to patch."""
    bu = overworld.bomb_upgrade
    hundreds = bu.cost // 100
    tens     = (bu.cost % 100) // 10
    ones     = bu.cost % 10
    hundreds_tile = BOMB_DISPLAY_SPACE_TILE if hundreds == 0 else hundreds
    patch.add(BOMB_COST_OFFSET,  bytes([bu.cost]))
    patch.add(BOMB_COUNT_OFFSET, bytes([bu.count]))
    patch.add(BOMB_DISP_BASE,    bytes([hundreds_tile, tens, ones]))
