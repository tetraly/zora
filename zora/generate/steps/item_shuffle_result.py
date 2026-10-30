"""What the item passes decide outside the room blocks (ItemShuffleResult), and
the level rooms they walk."""

from dataclasses import dataclass, field

from ...model.enums import Destination
from ...model.levels import Level
from ...model.rooms import LifeOrMoneyToll, Room, RoomPlace
from ..shapes.world import blocks_of
from .dungeon_quest import ALL_SHAPES, SetSources
from .shop_prices import DEFAULT_PRICE_RULES, PriceRules


@dataclass
class ItemShuffleOptions:
    """Preset values (Consternation): dungeon hearts on, minor items off,
    all "which item goes here" choices random (index 0)."""
    dungeon_hearts: bool = True
    # PS-ITEM-14 (B17): the level rooms holding bombs, five rupees or a key join the deal
    minor_items: bool = False
    armos_item: int = 0          # FORCED_ITEM_OPTIONS index
    white_sword_item: int = 0
    coast_item: int = 0
    # PS-ITEM-12 (C26, C27): FORCED_ITEM_OPTIONS indices for the first and the second pool place, in
    # PS-ITEM-04's walk order, that lies in level 9 when the deal starts
    level_9_items: tuple[int, int] = (0, 0)
    # SH-SRC: each set's source; a vanilla set gives PS-VAN-03's fixed item rooms
    set_sources: SetSources = ALL_SHAPES
    # The shop price classes (shop_prices.py): what a joined shop ware costs, by the item it holds
    prices: PriceRules = DEFAULT_PRICE_RULES


@dataclass(frozen=True)
class TrackedPlace:
    """One of acceptance.md VA-REJ-07's fifteen tracked items and where the
    item shuffle put it: a level (a room or item cellar of it) or a cave
    slot."""
    item: int
    level: int | None = None         # a progression place's level
    slot: str | None = None          # "armos", "white_sword" or "coast", or an extra's cave below
    # Where in the level, for HT-HINT-01's tested room: the room and the whole item byte written
    # there, or the item cellar. Not part of equality: a record names an item's level or slot
    # (VA-REJ-07), and finish.rebuild_tracking finds records again by those.
    room: int | None = field(default=None, compare=False)
    item_byte: int | None = field(default=None, compare=False)
    cellar: int | None = field(default=None, compare=False)


# The ZORA extras' cave slots (docs/zora-extras.md): an item an extra displaces
# keeps its tracked record, moved to the extra's cave.
MAGICAL_SWORD_SLOT = "magical_sword"
LETTER_SLOT = "letter"
WOOD_SWORD_SLOT = "wood_sword"           # Shuffle Wood Sword (docs/zora-extras.md section 13)
EXTRA_SLOT_CAVES: dict[str, Destination] = {
    MAGICAL_SWORD_SLOT: Destination.MAGICAL_SWORD_CAVE,
    LETTER_SLOT: Destination.LETTER_CAVE,
    WOOD_SWORD_SLOT: Destination.WOOD_SWORD_CAVE,
}

SHOP_WARE_SLOT_PREFIX = "shop "


def shop_ware_slot(destination: Destination, position: int) -> str:
    """A shop ware's slot name in a TrackedPlace (SI-JOIN-01)."""
    return f"{SHOP_WARE_SLOT_PREFIX}{destination.name} {position}"


def shop_of_slot(slot: str | None) -> Destination | None:
    """The shop a tracked shop-ware slot names, or None for any other slot."""
    if slot is None or not slot.startswith(SHOP_WARE_SLOT_PREFIX):
        return None
    return Destination[slot.split()[1]]


@dataclass
class ItemShuffleResult:
    """What the passes decided outside the two room blocks."""
    caves: dict[str, int] = field(default_factory=dict)   # slot -> item byte
    goriya_tile: int | None = None       # new ObjAnimFrameHeap+171 value
    goriya_swapped: bool = False
    # PS-GRUM-02's stored level: the goriya's new level when it swapped, else
    # the preset value 7 (read by PS-EGRP-06).
    goriya_level: int = 7
    merchants_added: int = 0
    bomb_levels: tuple[int, int] | None = None   # PS-BOMB-03's two levels
    toll: LifeOrMoneyToll | None = None          # PS-MERCH-04
    pool_size: int = 0
    pool_high_bits: int = 0              # pool bytes with bits 5-7 (diagnostic)
    item_shuffle_iterations: int = 0
    # Within each dungeon (C06 = 2): the second deal's iterations (PS-ITW-03), and whether this
    # scope was dealt; the hints then name heart containers in requirement texts (PS-ITW-05)
    within_levels_iterations: int = 0
    items_within_levels: bool = False
    # Whether PS-ITEM-02's heart rooms joined the pool (full scope, C06 = 3). Under every other scope
    # the hints may name a heart container in a requirement text (HT-HINT-01, PS-ITEM-09, PS-ITW-05)
    heart_rooms_pooled: bool = True
    # VA-REJ-07's fifteen tracked items, which are also PS-BOSS-05's planted-item records
    tracked: list[TrackedPlace] = field(default_factory=list)
    # PS-ITEM-12: the level places the deal pinned (an item forced there, or Non-Heart), as
    # (level, room or cellar number), which the ZORA extras' later exchanges leave alone
    pinned_level_places: frozenset[tuple[int, int]] = frozenset()
    # Allow Triforces in Stairways (steps/place_triforces.py): each Triforce's trade before the
    # shuffle, (set index, the spot's cell) -> the old Triforce room
    triforce_origins: dict[tuple[int, int], int] = field(default_factory=dict)


@dataclass(frozen=True)
class LevelRoom:
    """A level's room with where it sits: the block's index (0 for levels
    1-6, 1 for levels 7-9) and the level that owns it."""
    block_index: int
    room: Room
    level: Level

    @property
    def key(self) -> RoomPlace:
        return RoomPlace(self.block_index, self.room.room_num)


def _level_rooms(levels: list[Level]) -> list[LevelRoom]:
    """Rooms 0-127 of the level-1-6 block, then the level-7-9 block, that
    belong to a level."""
    scan: list[LevelRoom] = []
    for block_index, block in enumerate(blocks_of(levels)):
        owned = [LevelRoom(block_index, room, level) for level in levels if level.block is block
                 for room in level.rooms]
        scan.extend(sorted(owned, key=lambda level_room: level_room.room.room_num))
    return scan
