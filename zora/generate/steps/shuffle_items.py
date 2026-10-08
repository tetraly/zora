"""Item Shuffle (C06; PS-ITEM-01 to -08): the progression items, cave items and
dungeon hearts."""

from dataclasses import dataclass

from zora.generate.rng import IntRng
from zora.generate.shapes.world import blocks_of
from zora.generate.steps.item_shuffle_result import (
    ItemShuffleOptions,
    ItemShuffleResult,
    TrackedPlace,
    _level_rooms,
)
from zora.model.enums import Item, RoomType
from zora.model.levels import Level
from zora.model.rooms import ITEM_MASK, NO_ITEM_CODE, ItemInfo, Room, StaircaseRoom

# --- PS-ITEM ---------------------------------------------------------------

# Appendix "The twelve progression-item rooms, in pool order".
POOL_ORDER = (0x05, 0x0C, 0x1D, 0x1E, 0x0D, 0x10, 0x0A, 0x13, 0x0B, 0x07,
              0x09, 0x11)
CAVE_SLOTS = ("armos", "white_sword", "coast")   # PS-ITEM-04's walk order
ITEM_SHUFFLE_BUDGET = 10_000
# Appendix option table: index -> item byte, or one of the two choices that
# are not an item (random, Non-Heart).
RANDOM_ITEM = 0
NON_HEART = -2
FORCED_ITEM_OPTIONS = (RANDOM_ITEM, Item.BOOK, Item.WOOD_BOOMERANG, Item.BOW, Item.HEART_CONTAINER, Item.LADDER,
                       Item.MAGICAL_BOOMERANG, Item.MAGICAL_KEY, Item.POWER_BRACELET, Item.RAFT, Item.RECORDER,
                       Item.RED_CANDLE, Item.RED_RING, Item.SILVER_ARROWS, Item.WAND, Item.WHITE_SWORD, NON_HEART)
# PS-ITEM-05: the white-sword test reads the partner's LOW SIX bits
KEY_TEST_MASK = 0x3F


class _PoolPosition:
    """One pool position (PS-ITEM-04): a level room, an item cellar or a cave
    slot. The pool's values are whole item bytes as the spec reads them: a
    room's carries its boss sound and dark flag."""

    def get(self) -> int:
        raise NotImplementedError

    def put(self, item_byte: int) -> None:
        raise NotImplementedError

    def tracked(self, value: int) -> TrackedPlace:
        raise NotImplementedError


@dataclass
class _RoomPosition(_PoolPosition):
    room: Room
    level: Level

    def get(self) -> int:
        return self.room.item_byte

    def put(self, item_byte: int) -> None:
        self.room.item_info = ItemInfo.from_item_byte(item_byte)     # whole byte

    def tracked(self, value: int) -> TrackedPlace:
        return TrackedPlace(value & ITEM_MASK, level=self.level.level_num)


@dataclass
class _CellarPosition(_PoolPosition):
    cellar: StaircaseRoom
    level: Level | None

    def get(self) -> int:
        item = self.cellar.item
        return NO_ITEM_CODE if item is None or item == Item.NOTHING else int(item)

    def put(self, item_byte: int) -> None:
        # A cellar holds an item only: the whole byte cannot land here with
        # boss-sound or dark bits, and they are never dropped silently (none
        # has been seen: ItemShuffleResult.pool_high_bits counts them).
        if item_byte & ~ITEM_MASK:
            raise ValueError(f"item cellar ${self.cellar.room_num:02X}: the pool byte ${item_byte:02X} "
                             "carries boss-sound or dark bits, which a cellar cannot hold")
        self.cellar.item = ItemInfo.from_item_byte(item_byte).item

    def tracked(self, value: int) -> TrackedPlace:
        assert self.level is not None
        return TrackedPlace(value & ITEM_MASK, level=self.level.level_num)


@dataclass
class _CavePosition(_PoolPosition):
    slot: str
    state: ItemShuffleResult

    def get(self) -> int:
        return self.state.caves[self.slot]

    def put(self, item_byte: int) -> None:
        self.state.caves[self.slot] = item_byte & ITEM_MASK      # PS-ITEM-06

    def tracked(self, value: int) -> TrackedPlace:
        return TrackedPlace(value & ITEM_MASK, slot=self.slot)


def _find_item_place(levels: list[Level], code: int) -> _PoolPosition | None:
    """The room holding a planted progression item: its item cellar, or
    (boomerangs, SH-ITEM-02) the level room it was dropped in."""
    for block in blocks_of(levels):
        for stair in block.staircases:
            if (stair.room_type == RoomType.ITEM_STAIRCASE and stair.item is not None
                    and stair.item == code):
                owner = block.owner_of(stair.return_dest) if stair.return_dest is not None else None
                return _CellarPosition(stair, owner)
    for level_room in _level_rooms(levels):
        if level_room.room.item_info.item_code == code:
            return _RoomPosition(level_room.room, level_room.level)
    return None


def shuffle_items(levels: list[Level], state: ItemShuffleResult, rng: IntRng,
                  opts: ItemShuffleOptions) -> None:
    """PS-ITEM-01..08: one uniform Fisher-Yates walk over the pool with the
    forced-slot, Non-Heart and white-sword-key rejections and one
    10,000-iteration budget for the whole walk."""
    places: list[_PoolPosition] = []
    for code in POOL_ORDER:
        place = _find_item_place(levels, code)
        if place is not None:
            places.append(place)
    cave_position: dict[str, int] = {}
    for slot in CAVE_SLOTS:
        cave_position[slot] = len(places)
        places.append(_CavePosition(slot, state))
    if opts.dungeon_hearts:
        # PS-ITEM-02: low five bits $1A, a room of a level, not yet pooled.
        # PS-ITEM-08's paired-level relabel changes only a pooled room's
        # recorded level in second-quest-style blocks; the quest-1 blocks
        # are in use and no level is recorded per position here.
        taken = {id(place.room) for place in places if isinstance(place, _RoomPosition)}
        for level_room in _level_rooms(levels):
            room = level_room.room
            if id(room) not in taken and room.item_info.item_code == Item.HEART_CONTAINER:
                places.append(_RoomPosition(room, level_room.level))
    # Minor items (bombs, rupees, keys) join only in minor-items mode: off
    # for the preset and not modelled.

    count = len(places)
    pool_items = [place.get() for place in places]
    state.pool_size = count
    state.pool_high_bits = sum(1 for item_byte in pool_items if item_byte & ~ITEM_MASK)
    choice = {"armos": opts.armos_item, "white_sword": opts.white_sword_item,
              "coast": opts.coast_item}
    forced: dict[int, int] = {}
    non_heart: set[int] = set()
    for slot, option_index in choice.items():
        code = FORCED_ITEM_OPTIONS[option_index]
        if code == NON_HEART:
            non_heart.add(cave_position[slot])
        elif code != RANDOM_ITEM:
            forced[cave_position[slot]] = code
    white_sword_position = cave_position["white_sword"]

    # PS-ITEM-04 (P11): positions carry items and exchange DESTINATIONS;
    # forced slots, "Non-Heart" and the white-sword test are properties of a
    # destination. destination[p] is the place position p's item ends in.
    destination = list(range(count))
    position = iterations = 0
    while position < count:
        iterations += 1
        if iterations >= ITEM_SHUFFLE_BUDGET:   # the 10,000th is not run
            break
        target = destination[position]
        if target in forced:
            code = forced[target]
            match = next((match for match in range(count) if pool_items[match] == code), None)
            if match is None or match == position:
                position += 1                   # no exchange, no draw
                continue
            destination[position], destination[match] = destination[match], destination[position]
            continue                            # examine this position again
        other = position + rng.below(count - position)
        if destination[other] in forced:
            continue
        if target in non_heart and pool_items[other] == Item.HEART_CONTAINER:
            continue
        if target == white_sword_position and pool_items[other] & KEY_TEST_MASK == Item.KEY:
            continue
        destination[position], destination[other] = destination[other], destination[position]
        position += 1
    state.item_shuffle_iterations = iterations
    for position, item_byte in enumerate(pool_items):
        places[destination[position]].put(item_byte)
    # VA-REJ-07's fifteen tracked items: the pool's first fifteen contents
    # (the progression items found, then the three cave items), each where
    # the shuffle put it - a heart-container place included (QUESTIONS #62.2).
    # They are also PS-BOSS-05's planted-item records (one per item, in this
    # order; added heart containers have none).
    state.tracked = [places[destination[position]].tracked(pool_items[position])
                     for position in range(cave_position[CAVE_SLOTS[-1]] + 1)]
