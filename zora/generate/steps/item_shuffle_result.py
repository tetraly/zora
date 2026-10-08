"""What the item passes decide outside the room blocks (ItemShuffleResult), and
the level rooms they walk."""

from dataclasses import dataclass, field

from zora.generate.shapes.world import blocks_of
from zora.model.enums import Destination
from zora.model.levels import Level
from zora.model.rooms import LifeOrMoneyToll, Room, RoomPlace


@dataclass
class ItemShuffleOptions:
    """Preset values (Consternation): dungeon hearts on, minor items off,
    all "which item goes here" choices random (index 0)."""
    dungeon_hearts: bool = True
    armos_item: int = 0          # FORCED_ITEM_OPTIONS index
    white_sword_item: int = 0
    coast_item: int = 0


@dataclass(frozen=True)
class TrackedPlace:
    """One of acceptance.md VA-REJ-07's fifteen tracked items and where the
    item shuffle put it: a level (a room or item cellar of it) or a cave
    slot."""
    item: int
    level: int | None = None         # a progression place's level
    slot: str | None = None          # "armos", "white_sword" or "coast", or an extra's cave below


# The ZORA extras' cave slots (docs/zora-extras.md): an item an extra displaces
# keeps its tracked record, moved to the extra's cave.
MAGICAL_SWORD_SLOT = "magical_sword"
LETTER_SLOT = "letter"
EXTRA_SLOT_CAVES: dict[str, Destination] = {
    MAGICAL_SWORD_SLOT: Destination.MAGICAL_SWORD_CAVE,
    LETTER_SLOT: Destination.LETTER_CAVE,
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
    # VA-REJ-07's fifteen tracked items, which are also PS-BOSS-05's planted-item records
    tracked: list[TrackedPlace] = field(default_factory=list)


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
