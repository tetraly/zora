"""FP-START-03: the starting table a seed's start items and hearts make (fp-start-02's 40 bytes,
copied into Items, RAM $0657, by a new save file and the second-quest switch), and the items a
table holds."""
from collections.abc import Iterable

from ..model.enums import Item
from .code_patches import PRG0_START_ITEMS, START_ITEMS_SIZE
from .heart_values import heart_values

HEART_VALUES_INDEX = 0x18            # HeartValues, RAM $066F

# FP-START-03's table: each start item's slot in Items and its value. A slot keeps the larger of
# its value and the item's, so two swords keep the better one and two candles the red.
START_ITEM_SLOTS: dict[Item, tuple[int, int]] = {
    Item.WOOD_SWORD: (0, 1), Item.WHITE_SWORD: (0, 2), Item.MAGICAL_SWORD: (0, 3),
    Item.BOMBS: (1, 8),                                  # bombs in hand
    Item.WOOD_ARROWS: (2, 1), Item.SILVER_ARROWS: (2, 2),
    Item.BOW: (3, 1),
    Item.BLUE_CANDLE: (4, 1), Item.RED_CANDLE: (4, 2),
    Item.RECORDER: (5, 1),
    Item.BAIT: (6, 1),
    Item.WAND: (8, 1),
    Item.RAFT: (9, 1),
    Item.BOOK: (10, 1),
    Item.BLUE_RING: (11, 1), Item.RED_RING: (11, 2),
    Item.LADDER: (12, 1),
    Item.MAGICAL_KEY: (13, 1),
    Item.POWER_BRACELET: (14, 1),
    Item.LETTER: (15, 1),
    Item.WOOD_BOOMERANG: (29, 1),
    Item.MAGICAL_BOOMERANG: (30, 1),
    Item.MAGICAL_SHIELD: (31, 1),
}
ITEM_AT_SLOT_VALUE = {slot_value: item for item, slot_value in START_ITEM_SLOTS.items()}
ITEM_SLOTS = sorted({slot for slot, _ in START_ITEM_SLOTS.values()})


def start_table(items: Iterable[Item], heart_containers: int, full_hearts: int) -> bytes:
    """FP-START-03: FP-START-01's table with each item's slot raised to its value and the hearts
    byte from the start hearts (FL-ALT-02)."""
    table = bytearray(PRG0_START_ITEMS)
    for item in items:
        slot, value = START_ITEM_SLOTS[item]
        table[slot] = max(table[slot], value)
    table[HEART_VALUES_INDEX] = heart_values(heart_containers, full_hearts)
    return bytes(table)


def items_in_table(table: bytes) -> tuple[Item, ...]:
    """The start items a starting table holds, one per raised slot, in slot order (a slot holding
    the white sword reads back as the white sword alone, which writes the same table). A value no
    start item gives (another randomizer's table) is skipped."""
    if len(table) != START_ITEMS_SIZE:
        raise ValueError(f"a starting table is {START_ITEMS_SIZE} bytes, not {len(table)}")
    found = (ITEM_AT_SLOT_VALUE.get((slot, table[slot])) for slot in ITEM_SLOTS)
    return tuple(item for item in found if item is not None)
