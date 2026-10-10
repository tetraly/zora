"""The seed format's item names (docs/seed-format/seed-format.schema.json, $defs/itemName), the one
name each item code has outside ZORA: the seed document (zora_export) writes them, and Archipelago's
interface (zora/archipelago.py) names its items by them. Codes the format names nowhere are written
"Unknown Item XX" by the seed document and are never Archipelago items."""
from .enums import Item

ITEM_NAMES: dict[Item, str] = {
    Item.BOMBS: "Bombs", Item.WOOD_SWORD: "Wood Sword", Item.WHITE_SWORD: "White Sword",
    Item.MAGICAL_SWORD: "Magical Sword", Item.BAIT: "Bait", Item.RECORDER: "Recorder",
    Item.BLUE_CANDLE: "Blue Candle", Item.RED_CANDLE: "Red Candle", Item.WOOD_ARROWS: "Wooden Arrow",
    Item.SILVER_ARROWS: "Silver Arrow", Item.BOW: "Bow", Item.MAGICAL_KEY: "Magical Key", Item.RAFT: "Raft",
    Item.LADDER: "Ladder", Item.TRIFORCE_OF_POWER: "Triforce of Power", Item.FIVE_RUPEES: "5 Rupees",
    Item.WAND: "Wand", Item.BOOK: "Book", Item.BLUE_RING: "Blue Ring", Item.RED_RING: "Red Ring",
    Item.POWER_BRACELET: "Power Bracelet", Item.LETTER: "Letter", Item.COMPASS: "Compass", Item.MAP: "Map",
    Item.ITEM_0x18: "Rupee", Item.KEY: "Key", Item.HEART_CONTAINER: "Heart Container", Item.TRIFORCE: "Triforce",
    Item.MAGICAL_SHIELD: "Shield", Item.WOOD_BOOMERANG: "Boomerang", Item.MAGICAL_BOOMERANG: "Magical Boomerang",
    Item.BLUE_POTION: "Blue Potion", Item.RED_POTION: "Red Potion", Item.ITEM_0x21: "Clock",
    Item.SINGLE_HEART: "Heart", Item.FAIRY: "Fairy",
}
ITEMS_BY_NAME: dict[str, Item] = {name: item for item, name in ITEM_NAMES.items()}
assert len(ITEMS_BY_NAME) == len(ITEM_NAMES), "item names must be unique"
