"""The overworld: screens, caves, shops and the quotes they show."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TypeVar

from zora.model.enums import Destination, EnemySpriteSet, Item, OverworldDirection, QuestVisibility, ShopType
from zora.model.rooms import EnemySpec

T = TypeVar("T")

class EntranceType(Enum):
    NONE                    = auto()
    OPEN                    = auto()
    BOMB                    = auto()
    LADDER                  = auto()
    LADDER_AND_BOMB         = auto()
    RAFT                    = auto()
    RAFT_AND_BOMB           = auto()
    CANDLE                  = auto()
    RECORDER                = auto()
    POWER_BRACELET          = auto()
    POWER_BRACELET_AND_BOMB = auto()
    LOST_HILLS_HINT         = auto()
    DEAD_WOODS_HINT         = auto()


# Lookup from overworld screen number → EntranceType.
# Screens not in this dict have no entrance (open field, water, etc.) → NONE.
# Lookup from overworld screen number → EntranceType.
SCREEN_ENTRANCE_TYPES: dict[int, "EntranceType"] = {}  # populated after EntranceType defined


def _build_screen_entrance_types() -> dict[int, "EntranceType"]:
    str_to_entrance = {
        "Open":           EntranceType.OPEN,
        "Bomb":           EntranceType.BOMB,
        "Ladder":         EntranceType.LADDER,
        "Ladder+Bomb":    EntranceType.LADDER_AND_BOMB,
        "Raft":           EntranceType.RAFT,
        "Candle":         EntranceType.CANDLE,
        "Recorder":       EntranceType.RECORDER,
        "Power Bracelet": EntranceType.POWER_BRACELET,
    }
    raw = {
        0x00: "Bomb",  0x01: "Bomb",  0x02: "Bomb",  0x03: "Bomb",
        0x04: "Open",  0x05: "Bomb",  0x06: "Recorder", 0x07: "Bomb",
        0x09: "Power Bracelet", 0x0A: "Open", 0x0B: "Open", 0x0C: "Open",
        0x0D: "Bomb",  0x0E: "Open",  0x0F: "Open",  0x10: "Bomb",
        0x11: "Power Bracelet", 0x12: "Bomb", 0x13: "Bomb", 0x14: "Bomb",
        0x15: "Bomb",  0x16: "Bomb",  0x18: "Ladder+Bomb", 0x19: "Ladder+Bomb",
        0x1A: "Open",  0x1B: "Power Bracelet", 0x1C: "Open", 0x1D: "Power Bracelet",
        0x1E: "Bomb",  0x1F: "Open",  0x20: "Open",  0x21: "Open",
        0x22: "Open",  0x23: "Power Bracelet", 0x24: "Open", 0x25: "Open",
        0x26: "Bomb",  0x27: "Bomb",  0x28: "Candle", 0x29: "Recorder",
        0x2B: "Recorder", 0x2C: "Bomb", 0x2D: "Bomb", 0x2F: "Raft",
        0x30: "Recorder", 0x33: "Bomb", 0x34: "Open", 0x37: "Open",
        0x3A: "Recorder", 0x3C: "Recorder", 0x3D: "Open", 0x42: "Recorder",
        0x44: "Open",  0x45: "Raft",  0x46: "Candle", 0x47: "Candle",
        0x48: "Candle", 0x49: "Power Bracelet", 0x4A: "Open", 0x4B: "Candle",
        0x4D: "Candle", 0x4E: "Open", 0x51: "Candle", 0x53: "Candle",
        0x56: "Candle", 0x58: "Recorder", 0x5B: "Candle", 0x5E: "Open",
        0x5F: "Ladder", 0x60: "Recorder", 0x62: "Candle", 0x63: "Candle",
        0x64: "Open",  0x66: "Open",  0x67: "Bomb",  0x68: "Candle",
        0x6A: "Candle", 0x6B: "Candle", 0x6C: "Candle", 0x6D: "Candle",
        0x6E: "Recorder", 0x6F: "Open", 0x70: "Open", 0x71: "Bomb",
        0x72: "Recorder", 0x74: "Open", 0x75: "Open", 0x76: "Bomb",
        0x77: "Open",  0x78: "Candle", 0x79: "Power Bracelet", 0x7B: "Bomb",
        0x7C: "Bomb",  0x7D: "Bomb",
    }
    return {screen: str_to_entrance[label] for screen, label in raw.items()}


SCREEN_ENTRANCE_TYPES = _build_screen_entrance_types()



# --- Cave component types ---

@dataclass
class Quote:
    quote_id: int
    text: str

@dataclass
class ShopItem:
    item: Item
    price: int

@dataclass
class HintShopItem:
    quote_id: int
    price: int
    # Top 2 bits of the slot's quote-ID byte in ROM (display flags; identity
    # unknown, preserved for round-trip fidelity).
    slot_flags: int = 0

# --- Cave definitions ---

@dataclass
class OverworldItem:
    """Item obtainable directly on the overworld, no cave entrance (Armos, Coast)."""
    destination: Destination
    item: Item
    ladder_requirement: bool = False

@dataclass
class ItemCave:
    """Single-item cave with a quote and optional heart requirement (sword caves, letter cave)."""
    destination: Destination
    item: Item
    quote_id: int
    maybe_extra_candle: Item = Item.OVERWORLD_NO_ITEM
    heart_requirement: int = 0

@dataclass
class SecretCave:
    """Rupee secret (under a bush, rock, etc.); positive = reward, negative = penalty."""
    destination: Destination
    quote_id: int
    rupee_value: int

@dataclass
class DoorRepairCave:
    """Cave that charges rupees for a broken door."""
    destination: Destination
    quote_id: int
    cost: int  # vanilla = 20, randomizable; stored positive, applied as a penalty

@dataclass
class HintCave:
    """Cave containing only a hint; no item."""
    destination: Destination
    quote_id: int  # hint variant is derivable from quote_id

@dataclass
class TakeAnyCave:
    """Cave offering a choice of items."""
    destination: Destination
    quote_id: int
    items: list[Item] = field(default_factory=lambda: [Item.RED_POTION, Item.OVERWORLD_NO_ITEM, Item.HEART_CONTAINER])

@dataclass
class Shop:
    """Shop with 2 or 3 priced items; may require letter."""
    destination: Destination
    quote_id: int
    shop_type: ShopType
    letter_requirement: bool
    items: list[ShopItem]  # 2 or 3 items (potion shop has 2)
    # The potion shop's middle ware, empty in PRG0 (None): Add L4 Sword sells the fourth sword
    # there (the owner's 2.0 flags).
    middle: ShopItem | None = None

@dataclass
class HintShop:
    """Shop selling hints at a price, with an entry quote."""
    destination: Destination
    quote_id: int
    hints: list[HintShopItem]  # exactly 3

@dataclass
class MoneyMakingGameCave:
    """The money-making game cave with bet amounts and prize/penalty outcomes."""
    destination: Destination
    quote_id: int
    bet_low: int
    bet_mid: int
    bet_high: int
    lose_small: int    # vanilla = -10
    lose_small_2: int  # vanilla = -10 (second losing bucket)
    lose_large: int    # vanilla = -40
    win_small: int     # vanilla = +20
    win_large: int     # vanilla = +50


@dataclass
class BombUpgrade:
    cost: int    # rupees charged for the upgrade (vanilla = 100)
    count: int   # bombs added to MaxBombs (vanilla = 4)


@dataclass
class Screen:
    screen_num: int
    destination: Destination
    entrance_type: EntranceType
    enemy_spec: EnemySpec
    enemy_quantity: int
    exit_x_position: int
    exit_y_position: int
    has_zola: bool
    has_ocean_sound: bool
    enemies_from_sides: bool
    stairs_position_code: int
    quest_visibility: QuestVisibility  # table 5 bits 7-6
    outer_palette: int   # table 0 bits 1-0: code for outer border palette
    inner_palette: int   # table 1 bits 1-0: code for inner section palette
    screen_code: int     # table 3 bits 6-0: visual map screen code

# --- Union type ---

CaveDefinition = (
    OverworldItem
    | ItemCave
    | SecretCave
    | DoorRepairCave
    | HintCave
    | TakeAnyCave
    | Shop
    | HintShop
    | MoneyMakingGameCave
)

@dataclass
class Overworld:
    screens: list[Screen]
    enemy_sprite_set: EnemySpriteSet
    caves: list[CaveDefinition]
    qty_table: list[int]   # 4-entry quantity lookup (level_info block 0 bytes 0x24-0x27)

    # Direction sequences for the Lost Hills and Dead Woods maze puzzles.
    # Each is a list of 4 OverworldDirection values stored at ROM 0x6DA7-0x6DAE.
    # Dead Woods: 0x6DA7-0x6DAA. Lost Hills: 0x6DAB-0x6DAE.
    dead_woods_directions: list[OverworldDirection]
    lost_hills_directions: list[OverworldDirection]
    # Armos statue lookup tables (ROM 0x10CB2, bank 4): 7 screen IDs and 7 sprite
    # X-positions. The game engine reads armos_screen_ids[0] to find which overworld
    # screen holds the active armos item, and armos_positions[0] for the sprite position.
    armos_screen_ids: list[int]   # 7 entries
    armos_positions:  list[int]   # 7 entries
    bomb_upgrade: BombUpgrade
    any_road_screens: list[int]
    recorder_warp_destinations: list[int]
    recorder_warp_y_coordinates: list[int]
    start_screen: int
    start_position_y: int  # ROM offset 0x19328+header; calculated as screen_widths[start_screen] * 16 + 13

    # Raw cave data preserved for round-trip serialization
    #cave_item_data_raw: bytes = b''
    #cave_price_data_raw: bytes = b''

    def get_cave(self, destination: Destination, cave_type: type[T]) -> T | None:
        """Return the cave at the given destination if it matches cave_type, else None.

        Usage:
            mmg = ow.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
            # mmg is MoneyMakingGameCave | None — no isinstance needed at call site
        """
        for c in self.caves:
            if c.destination == destination and isinstance(c, cave_type):
                return c
        return None
