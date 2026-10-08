"""Extra items joining the major-item pool after the item shuffle (ZORA flags
Randomize Magical Sword and Randomize Letter; docs/zora-extras.md).

The item shuffle (PS-ITEM, shuffle_items.py) is left exactly as it is. An
extra joins afterwards, in one step: one draw picks uniformly among the
pool's places and the extra's own cave, and the extra exchanges items with
the place drawn (staying put when its own cave is drawn). That is the
"inside-out" Fisher-Yates step: added to a uniform shuffle of n places, it
gives a uniform shuffle of n + 1. The pool's forced cave slots keep their
items.

The pool's places are found by what they hold, since the item shuffle does
not hand its positions on: the three special-cave slots, every extra cave
already joined, and each level room or item cellar holding an item of the
pool (one of the tracked items, a heart container while the dungeon hearts
are pooled, or an extra already joined). Later passes move rooms' items with
their rooms, never out of the pool's set, so this finds the same places
whenever it runs.

An extra's cave sits outside the room blocks, so like B1's cave items it is
STAGED in ExtraPoolItems and written into the GameWorld only when the pass
ships (apply_extra_pool_items).
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace

from zora.generate.acceptance_check import DEFAULT_RULES, LogicRules
from zora.generate.rng import IntRng
from zora.generate.steps.cave_entries import CaveShuffle
from zora.generate.steps.item_shuffle_result import (
    EXTRA_SLOT_CAVES,
    LETTER_SLOT,
    MAGICAL_SWORD_SLOT,
    ItemShuffleOptions,
    ItemShuffleResult,
    TrackedPlace,
    shop_ware_slot,
)
from zora.generate.steps.shuffle_items import CAVE_SLOTS, FORCED_ITEM_OPTIONS, RANDOM_ITEM
from zora.model.enums import Item, RoomType
from zora.model.game_world import GameWorld
from zora.model.levels import Level
from zora.model.overworld import ItemCave, Overworld, Shop
from zora.model.rooms import ITEM_MASK, Room, StaircaseRoom

# The item each extra brings into the pool (its cave's vanilla item).
JOINED_ITEMS: dict[str, Item] = {MAGICAL_SWORD_SLOT: Item.MAGICAL_SWORD, LETTER_SLOT: Item.LETTER}


@dataclass
class ExtraPoolItems:
    """The extra caves that joined the pool this pass, each with the item it
    now offers (staged; the GameWorld is untouched until the pass ships), and
    the shop wares joined by Shop Items in the Item Pool (SI-JOIN-01: on the
    pass's staged overworld, which ships whole), with the item each brought."""
    caves: dict[str, Item] = field(default_factory=dict)
    shop_wares: list[ShopWarePlace] = field(default_factory=list)
    shop_items: list[Item] = field(default_factory=list)


def extra_cave(overworld: Overworld, slot: str) -> ItemCave:
    cave = overworld.get_cave(EXTRA_SLOT_CAVES[slot], ItemCave)
    assert cave is not None, slot
    return cave


def apply_extra_pool_items(gw: GameWorld, extras: ExtraPoolItems) -> None:
    """Write the staged extra caves' items into the shipped GameWorld."""
    for slot, item in extras.caves.items():
        extra_cave(gw.overworld, slot).item = item


# ---------------------------------------------------------------------------
# The pool's places
# ---------------------------------------------------------------------------

class PoolPlace:
    """A place of the pool: what it holds, and where, as VA-REJ-07 records it."""

    def get(self) -> Item:
        raise NotImplementedError

    def put(self, item: Item) -> None:
        raise NotImplementedError

    def tracked(self, item: Item) -> TrackedPlace:
        raise NotImplementedError


@dataclass
class LevelRoomPlace(PoolPlace):
    """A level room. Only the item moves: the room keeps its boss sound and
    darkness, since a cave has neither to trade."""
    level: Level
    room: Room

    def get(self) -> Item:
        return self.room.item

    def put(self, item: Item) -> None:
        self.room.item = item

    def tracked(self, item: Item) -> TrackedPlace:
        return TrackedPlace(item & ITEM_MASK, level=self.level.level_num)


@dataclass
class ItemCellarPlace(PoolPlace):
    level: Level
    cellar: StaircaseRoom

    def get(self) -> Item:
        assert self.cellar.item is not None
        return self.cellar.item

    def put(self, item: Item) -> None:
        self.cellar.item = item

    def tracked(self, item: Item) -> TrackedPlace:
        return TrackedPlace(item & ITEM_MASK, level=self.level.level_num)


@dataclass
class CaveSlotPlace(PoolPlace):
    """One of the item shuffle's three special-cave slots (armos, white
    sword, coast), staged in the ItemShuffleResult."""
    slot: str
    state: ItemShuffleResult

    def get(self) -> Item:
        return Item(self.state.caves[self.slot])

    def put(self, item: Item) -> None:
        self.state.caves[self.slot] = int(item)

    def tracked(self, item: Item) -> TrackedPlace:
        return TrackedPlace(item & ITEM_MASK, slot=self.slot)


@dataclass
class ExtraSlotPlace(PoolPlace):
    """An extra's cave, staged in ExtraPoolItems."""
    slot: str
    extras: ExtraPoolItems

    def get(self) -> Item:
        return self.extras.caves[self.slot]

    def put(self, item: Item) -> None:
        self.extras.caves[self.slot] = item

    def tracked(self, item: Item) -> TrackedPlace:
        return TrackedPlace(item & ITEM_MASK, slot=self.slot)


@dataclass
class ShopWarePlace(PoolPlace):
    """A shop ware (SI-JOIN-01): what it sells; its price is set apart (SI-PRICE-01)."""
    shop: Shop
    position: int

    def get(self) -> Item:
        return self.shop.items[self.position].item

    def put(self, item: Item) -> None:
        self.shop.items[self.position].item = item

    def tracked(self, item: Item) -> TrackedPlace:
        return TrackedPlace(item & ITEM_MASK, slot=shop_ware_slot(self.shop.destination, self.position))


def item_cellars(level: Level) -> Iterator[StaircaseRoom]:
    """The level's item cellars holding an item: those returning to one of
    its rooms (as dungeon_walk.item_cellar reads ownership)."""
    for stair in level.block.staircases:
        if (stair.room_type == RoomType.ITEM_STAIRCASE and stair.item is not None
                and stair.return_dest in level.room_nums):
            yield stair


def dungeon_places(levels: list[Level]) -> Iterator[LevelRoomPlace | ItemCellarPlace]:
    """Every level room and item cellar, levels in order, rooms in room order."""
    for level in sorted(levels, key=lambda level: level.level_num):
        for room in sorted(level.rooms, key=lambda room: room.room_num):
            yield LevelRoomPlace(level, room)
        for cellar in sorted(item_cellars(level), key=lambda cellar: cellar.room_num):
            yield ItemCellarPlace(level, cellar)


def pool_items(state: ItemShuffleResult, extras: ExtraPoolItems, opts: ItemShuffleOptions) -> frozenset[int]:
    """The item codes the pool holds: the tracked items (the progression
    items and the three special-cave items), heart containers while the
    dungeon hearts are pooled (PS-ITEM-02), and every extra joined so far."""
    codes = {place.item for place in state.tracked}
    if opts.dungeon_hearts:
        codes.add(Item.HEART_CONTAINER)
    codes |= {JOINED_ITEMS[slot] for slot in extras.caves}
    codes |= set(extras.shop_items)
    return frozenset(codes)


def _forced_slots(opts: ItemShuffleOptions) -> frozenset[str]:
    """The special-cave slots whose item the flags fix (PS-ITEM-03): they keep it."""
    choice = {"armos": opts.armos_item, "white_sword": opts.white_sword_item, "coast": opts.coast_item}
    return frozenset(slot for slot, index in choice.items() if FORCED_ITEM_OPTIONS[index] != RANDOM_ITEM)


def pool_places(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                opts: ItemShuffleOptions) -> list[PoolPlace]:
    """The pool's places an extra may exchange with, in a fixed order: the
    dungeon places holding a pool item, the special-cave slots (less the
    forced ones), the extras' caves in the order they joined, then the shop
    wares joined so far."""
    codes = pool_items(state, extras, opts)
    places: list[PoolPlace] = [place for place in dungeon_places(levels)
                               if int(place.get()) & ITEM_MASK in codes and place.get() != Item.NOTHING]
    forced = _forced_slots(opts)
    places += [CaveSlotPlace(slot, state) for slot in CAVE_SLOTS if slot not in forced]
    places += [ExtraSlotPlace(slot, extras) for slot in extras.caves]
    places += extras.shop_wares
    return places


# ---------------------------------------------------------------------------
# Joining
# ---------------------------------------------------------------------------

def _retrack(state: ItemShuffleResult, item: Item, before: TrackedPlace, after: TrackedPlace) -> None:
    """Move one tracked record of an item from where it was to where it is
    now (VA-REJ-07 judges item types by level or slot, so any one record of
    a duplicated item will do)."""
    for index, place in enumerate(state.tracked):
        if place == before:
            state.tracked[index] = after
            return


def join_pool(slot: str, levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
              overworld: Overworld, rng: IntRng, opts: ItemShuffleOptions | None = None) -> PoolPlace | None:
    """An extra's cave joins the pool: one draw among the pool's places and
    the cave itself, then the two exchange items. Returns the place drawn,
    or None when the extra stayed in its own cave.

    The extra itself is not a tracked item (it unlocks nothing VA-REJ-07's
    walk models); the item it displaces keeps its tracked record, moved to
    the extra's cave."""
    opts = opts or ItemShuffleOptions()
    assert slot not in extras.caves, f"{slot} joined twice"
    places = pool_places(levels, state, extras, opts)
    extras.caves[slot] = extra_cave(overworld, slot).item
    return exchange_with_drawn(ExtraSlotPlace(slot, extras), places, state, rng)


def exchange_with_drawn(own: PoolPlace, places: list[PoolPlace], state: ItemShuffleResult,
                        rng: IntRng) -> PoolPlace | None:
    """The join step: one draw among the places and the joining item's own place, then the
    two exchange items and their tracked records. Returns the place drawn, or None when the
    item stayed in its own place."""
    drawn = rng.below(len(places) + 1)
    if drawn == len(places):
        return None
    place = places[drawn]
    joining, displaced = own.get(), place.get()
    own.put(displaced)
    place.put(joining)
    _retrack(state, displaced, place.tracked(displaced), own.tracked(displaced))
    _retrack(state, joining, own.tracked(joining), place.tracked(joining))
    return place


# ---------------------------------------------------------------------------
# For the acceptance check (E1, VA-REJ-07)
# ---------------------------------------------------------------------------

def is_extra_slot_collected(slot: str, caves: CaveShuffle, held: frozenset[int],
                            rules: LogicRules = DEFAULT_RULES) -> bool:
    """VA-REJ-07's rule for an extra's cave, as for the white-sword slot:
    collected when the cave's screen needs are held; a cave the cave
    shuffle did not enrol is never collected, as for that slot. The
    magical-sword cave's heart requirement is judged apart, by
    randomize_magical_sword.has_enough_heart_containers."""
    screens = caves.movable_screens(EXTRA_SLOT_CAVES[slot])
    if not screens:
        return False
    return rules.needs(screens[0]) <= held


def with_tracked(state: ItemShuffleResult, tracked: list[TrackedPlace]) -> ItemShuffleResult:
    """A copy of the item shuffle's result with another tracked list."""
    return replace(state, tracked=list(tracked), caves=dict(state.caves))
