"""Item Shuffle (C06; PS-ITEM-01 to -08): the progression items, cave items and
dungeon hearts. Within each dungeon (C06 = 2; PS-ITW-01 to -04): the fifteen-place
deal without the hearts, then a re-deal inside each level."""

from dataclasses import dataclass, replace

from ...model.enums import Item, RoomType
from ...model.levels import Level, LevelBlock
from ...model.rooms import ITEM_MASK, NO_ITEM_CODE, ItemInfo, Room, StaircaseRoom
from ..rng import IntRng
from ..shapes.world import blocks_of
from .dungeon_quest import SET_LEVELS, SetSource, SetSources
from .item_shuffle_result import (
    ItemShuffleOptions,
    ItemShuffleResult,
    TrackedPlace,
    _level_rooms,
)

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
# PS-ITEM-08: in a second-quest-style block the scan records a heart room of
# level 2, 4 or 7 as level 3, 5 or 8, and the other way round
PAIRED_LEVELS = {2: 3, 3: 2, 4: 5, 5: 4, 7: 8, 8: 7}


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

    @property
    def level_num(self) -> int | None:
        """The level the place belongs to; None for a cave slot."""
        raise NotImplementedError


@dataclass
class _RoomPosition(_PoolPosition):
    room: Room
    level: Level
    # the level the heart scan records, when PS-ITEM-08 relabels it (not the owner)
    recorded_level_num: int | None = None

    def get(self) -> int:
        return self.room.item_byte

    def put(self, item_byte: int) -> None:
        self.room.item_info = ItemInfo.from_item_byte(item_byte)     # whole byte

    def tracked(self, value: int) -> TrackedPlace:
        return TrackedPlace(value & ITEM_MASK, level=self.level.level_num, room=self.room.room_num, item_byte=value)

    @property
    def level_num(self) -> int | None:
        return self.level.level_num if self.recorded_level_num is None else self.recorded_level_num


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
        return TrackedPlace(value & ITEM_MASK, level=self.level.level_num, cellar=self.cellar.room_num)

    @property
    def level_num(self) -> int | None:
        return None if self.level is None else self.level.level_num


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

    @property
    def level_num(self) -> int | None:
        return None


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


# PS-VAN-03: a vanilla set's progression-item places, the rooms of its block that hold those
# items in PRG0 (room cells or item cellars)
VANILLA_ITEM_ROOMS: dict[tuple[SetSource, int], tuple[int, ...]] = {
    (SetSource.FIRST_QUEST, 0): (0x04, 0x0F, 0x44, 0x4F, 0x60, 0x75, 0x7F),
    (SetSource.FIRST_QUEST, 1): (0x00, 0x0F, 0x4A, 0x4F, 0x6F),
    (SetSource.SECOND_QUEST, 0): (0x0B, 0x15, 0x46, 0x6A, 0x78, 0x7A, 0x7F),
    (SetSource.SECOND_QUEST, 1): (0x2B, 0x2C, 0x70, 0x76, 0x77),
}


def _progression_places(levels: list[Level], sources: SetSources) -> list[_PoolPosition]:
    """PS-ITEM-01's twelve progression-item places: where the shape stage planted each item, in
    pool order; with a vanilla set (PS-VAN-03), seven places from levels 1-6 and five from 7-9,
    a vanilla set's being its fixed rooms."""
    if not any(source.is_vanilla for source in sources):
        return [place for code in POOL_ORDER if (place := _find_item_place(levels, code)) is not None]
    places: list[_PoolPosition] = []
    for set_index, source in enumerate(sources):
        set_levels = [level for level in levels if level.level_num in SET_LEVELS[set_index]]
        if source.is_vanilla:
            places += [_place_at(set_levels[0].block, room_num) for room_num in VANILLA_ITEM_ROOMS[source, set_index]]
        else:
            places += [place for code in POOL_ORDER if (place := _find_item_place(set_levels, code)) is not None]
    return places


def _place_at(block: LevelBlock, room_num: int) -> _PoolPosition:
    """The pool place at one cell of a block: an item cellar, or a level's room."""
    cell = block.cells[room_num]
    if isinstance(cell, StaircaseRoom):
        owner = block.owner_of(cell.return_dest) if cell.return_dest is not None else None
        return _CellarPosition(cell, owner)
    level = block.owner_of(room_num)
    assert level is not None, f"PS-VAN-03: room ${room_num:02X} belongs to no level"
    return _RoomPosition(cell, level)


def heart_rooms(levels: list[Level], pooled: list[_PoolPosition]) -> list[_PoolPosition]:
    """PS-ITEM-02 and PS-ITW-02's heart scan: every room of a level, in block
    scan order, whose item byte's low five bits are $1A and that is not
    already a pool place. PS-ITEM-08: in a second-quest-style block (a level
    of a vanilla second-quest set) a heart room of level 2, 4 or 7 is
    recorded as level 3, 5 or 8, and the other way round; the recorded level
    is what the within-dungeon deal (C06 = 2) groups by. The room's owner and
    the scan's order are unchanged."""
    taken = {id(place.room) for place in pooled if isinstance(place, _RoomPosition)}
    hearts: list[_PoolPosition] = []
    for level_room in _level_rooms(levels):
        room, level = level_room.room, level_room.level
        if id(room) not in taken and room.item_info.item_code == Item.HEART_CONTAINER:
            recorded = PAIRED_LEVELS.get(level.level_num) if level.is_second_quest else None
            hearts.append(_RoomPosition(room, level, recorded))
    return hearts


def shuffle_items(levels: list[Level], state: ItemShuffleResult, rng: IntRng,
                  opts: ItemShuffleOptions) -> None:
    """PS-ITEM-01..08: one uniform Fisher-Yates walk over the pool with the
    forced-slot, Non-Heart and white-sword-key rejections and one
    10,000-iteration budget for the whole walk."""
    _deal_pool(levels, state, rng, opts)


def _deal_pool(levels: list[Level], state: ItemShuffleResult, rng: IntRng,
               opts: ItemShuffleOptions) -> list[tuple[_PoolPosition, int]]:
    """PS-ITEM-01..08's deal; returns the fifteen tracked items' final places
    with their item bytes, in pool order."""
    places = _progression_places(levels, opts.set_sources)
    cave_position: dict[str, int] = {}
    for slot in CAVE_SLOTS:
        cave_position[slot] = len(places)
        places.append(_CavePosition(slot, state))
    if opts.dungeon_hearts:
        # PS-ITEM-02: low five bits $1A, a room of a level, not yet pooled.
        places += heart_rooms(levels, places)
    # Minor items (bombs, rupees, keys) join only in minor-items mode: off
    # for the preset and not modeled.

    count = len(places)
    pool_items = [place.get() for place in places]
    if any(source.is_vanilla for source in opts.set_sources):
        # PS-VAN-03: the values dealt are the twelve progression items, one each, whatever the
        # rooms held (levels 1-6 first quest and 7-9 second hold the wand twice and no Book)
        assert cave_position[CAVE_SLOTS[0]] == len(POOL_ORDER), "PS-VAN-03: 7 + 5 progression places"
        pool_items[:len(POOL_ORDER)] = POOL_ORDER
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
    dealt = [(places[destination[position]], pool_items[position])
             for position in range(cave_position[CAVE_SLOTS[-1]] + 1)]
    state.tracked = [place.tracked(item_byte) for place, item_byte in dealt]
    return dealt


def shuffle_items_within_levels(levels: list[Level], state: ItemShuffleResult, rng: IntRng,
                                opts: ItemShuffleOptions) -> None:
    """PS-ITW-01: under C06 = 2 the item shuffle is two deals. The first is
    PS-ITEM-01 over the fifteen places without the heart rooms (PS-ITEM-02
    applies only to C06 = 3); then one number is drawn and discarded (the
    original randomizer's unused pass seed), and the second deal re-deals each level's
    tracked items and heart rooms inside that level (PS-ITW-02 to -04)."""
    state.items_within_levels = True
    dealt = _deal_pool(levels, state, rng, replace(opts, dungeon_hearts=False))
    rng.below(ITEM_SHUFFLE_BUDGET)       # PS-ITW-01 step 2: drawn and discarded
    deal_within_levels(levels, state, rng, dealt)


def within_levels_pool(levels: list[Level], dealt: list[tuple[_PoolPosition, int]]) -> list[_PoolPosition]:
    """PS-ITW-02: the fifteen tracked places in pool order (a cave slot among
    them never moves), then every heart room of a level ($1A in the item
    byte's low five bits) not already a pool place, in block scan order."""
    places = [place for place, _item_byte in dealt]
    return places + heart_rooms(levels, places)


def deal_within_levels(levels: list[Level], state: ItemShuffleResult, rng: IntRng,
                       dealt: list[tuple[_PoolPosition, int]]) -> None:
    """PS-ITW-03 and PS-ITW-04: a Fisher-Yates over the pool positions in
    order that skips a cave slot (no draw) and redraws a partner from
    another level, with its own 10,000-iteration budget counted as in
    PS-ITEM-07 (every skip and every rejected draw counts). No pins,
    Non-Heart test, white-sword key test or level-9 rule. Moved bytes are
    written whole; the fifteen records keep their items and take the items'
    final places (the heart rooms that joined are not recorded)."""
    places = within_levels_pool(levels, dealt)
    levels_of = [place.level_num for place in places]
    count = len(places)
    pool_items = [place.get() for place in places]
    destination = list(range(count))
    position = iterations = 0
    while position < count:
        iterations += 1
        if iterations >= ITEM_SHUFFLE_BUDGET:   # the 10,000th is not run
            break
        if levels_of[position] is None:         # a special-cave slot: skipped, no draw
            position += 1
            continue
        other = position + rng.below(count - position)
        if levels_of[other] != levels_of[position]:
            continue                            # another level: redraw for this position
        destination[position], destination[other] = destination[other], destination[position]
        position += 1
    state.within_levels_iterations = iterations
    for position, item_byte in enumerate(pool_items):
        if destination[position] != position:
            places[destination[position]].put(item_byte)
    state.tracked = [places[destination[position]].tracked(item_byte)
                     for position, (_place, item_byte) in enumerate(dealt)]
