"""Randomize Magical Sword (ZORA flag; docs/zora-extras.md): the magical sword
joins the major-item pool, and the magical-sword cave offers whatever item
lands there.

Two parts:
  - randomize_magical_sword: the join (extra_pool_items.join_pool);
  - the heart logic (owner requirement): if the cave asks for N hearts and
    Link starts with M heart containers, then
        (heart containers reachable without the cave's item) + max(0, k - 2) >= N - M,
    where the heart containers counted are the pool's places (take-any caves
    are never one) and k is the number of take-any caves reachable without
    the cave's item that offer a heart container. A take-any cave (code 17)
    offers a red potion, the blue candle (OW-SHOP-05) and a heart container
    (PRG0's ware table, cave index 1): the check assumes the player takes the
    heart container from all but two of them.

A magical sword in a dungeon room needs the ZORA "no item" remap ($0E,
game_config.DungeonNothingCode.ZORA_REMAP) when the ROM is written, or the
engine would take its $03 for "no item" (docs/zora-extras.md lists every
site).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from zora.generate.acceptance_check import (
    DEFAULT_RULES,
    FAMILY_EXEMPT_LAYOUT,
    LADDER_LAYOUTS,
    LEVEL9_ENTRY,
    LONG_ITEMS,
    AcceptanceCheck,
    LogicRules,
)
from zora.generate.dungeon_walk import Walk, is_family_blocked, walk_level
from zora.generate.rng import IntRng
from zora.generate.steps.cave_entries import CaveShuffle
from zora.generate.steps.extra_pool_items import (
    CaveSlotPlace,
    ExtraPoolItems,
    ExtraSlotPlace,
    ItemCellarPlace,
    LevelRoomPlace,
    PoolPlace,
    ShopWarePlace,
    dungeon_places,
    is_extra_slot_collected,
    join_pool,
    with_tracked,
)
from zora.generate.steps.item_shuffle_result import MAGICAL_SWORD_SLOT, ItemShuffleOptions, ItemShuffleResult
from zora.generate.steps.shuffle_items import CAVE_SLOTS
from zora.model.enums import Destination, Item
from zora.model.levels import LEVEL_9, Level
from zora.model.overworld import Overworld, TakeAnyCave

# The take-any caves the heart check lets the player spend on another choice.
TAKE_ANY_CAVES_SPENT_ELSEWHERE = 2


def randomize_magical_sword(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                            overworld: Overworld, rng: IntRng,
                            opts: ItemShuffleOptions | None = None) -> PoolPlace | None:
    """Randomize Magical Sword: the magical-sword cave joins the pool. One
    draw; returns the place the sword went to (None: it stayed)."""
    return join_pool(MAGICAL_SWORD_SLOT, levels, state, extras, overworld, rng, opts)


# ---------------------------------------------------------------------------
# The heart logic
# ---------------------------------------------------------------------------

def heart_container_places(levels: list[Level], state: ItemShuffleResult,
                           extras: ExtraPoolItems) -> list[PoolPlace]:
    """Every place of the pool holding a heart container except the
    magical-sword cave: level rooms and item cellars, the three
    special-cave slots, the other extras' caves and the shop wares joined
    by Shop Items in the Item Pool (rupees are not modelled). Other shop
    wares and the take-any caves are not pool places and never appear."""
    places: list[PoolPlace] = [place for place in dungeon_places(levels) if place.get() == Item.HEART_CONTAINER]
    places += [CaveSlotPlace(slot, state) for slot in CAVE_SLOTS]
    places += [ExtraSlotPlace(slot, extras) for slot in extras.caves if slot != MAGICAL_SWORD_SLOT]
    places += extras.shop_wares
    return [place for place in places if place.get() == Item.HEART_CONTAINER]


class HeartReach(Protocol):
    """Whether a place is reachable in logic without the magical-sword
    cave's item (heart requirements aside: the count handles those)."""

    def reaches(self, place: PoolPlace) -> bool: ...


def is_white_sword_slot(place: PoolPlace) -> bool:
    return isinstance(place, CaveSlotPlace) and place.slot == "white_sword"


def count_reachable_heart_containers(places: Iterable[PoolPlace], reach: HeartReach, starting_hearts: int,
                                     white_sword_hearts_required: int) -> int:
    """The heart containers reachable without the magical-sword cave's item.

    The white-sword cave asks for hearts too: a heart container there counts
    only once Link can meet its requirement with the others."""
    reachable = [place for place in places if reach.reaches(place)]
    others = sum(not is_white_sword_slot(place) for place in reachable)
    in_white_sword_cave = len(reachable) - others
    if in_white_sword_cave and starting_hearts + others >= white_sword_hearts_required:
        return others + in_white_sword_cave
    return others


def has_enough_heart_containers(hearts_required: int, starting_hearts: int, reachable: int) -> bool:
    """Owner requirement B: at least N - M reachable heart containers."""
    return reachable >= hearts_required - starting_hearts


def reachable_take_any_hearts(overworld: Overworld, held: frozenset[int], rules: LogicRules = DEFAULT_RULES) -> int:
    """k: the take-any caves whose screen needs are held (VA-REJ-07's rule for a cave screen)
    and that offer a heart container. Every code-17 screen opens the same cave, so either all
    of them offer one or none does."""
    cave = overworld.get_cave(Destination.TAKE_ANY, TakeAnyCave)
    if cave is None or Item.HEART_CONTAINER not in cave.items:
        return 0
    return sum(rules.needs(screen.screen_num) <= held
               for screen in overworld.screens if screen.destination == Destination.TAKE_ANY)


def take_any_heart_allowance(take_any_caves: int) -> int:
    """max(0, k - 2): the take-any hearts the check counts."""
    return max(0, take_any_caves - TAKE_ANY_CAVES_SPENT_ELSEWHERE)


@dataclass
class AcceptanceHeartReach:
    """HeartReach by the acceptance check's logic (VA-REJ-07), from the
    closure it reaches when the magical-sword cave's item is left out.

    Built from acceptance_check's and dungeon_walk's public names: a level
    is entered when its entry door's screen needs are held (level 9 also
    needs the long items), a room is reached by the inventory walk with the
    family and ladder rules, and an item cellar when the walk enters it.
    One stricter rule than E1: a level-9 place also needs level-9 entry
    (eight dungeons completed), since a heart container behind the
    magical-sword cave's item must not unlock that cave."""
    levels: list[Level]
    state: ItemShuffleResult
    extras: ExtraPoolItems
    overworld: Overworld
    caves: CaveShuffle
    rules: LogicRules = DEFAULT_RULES
    held: frozenset[int] = frozenset()
    _walks: dict[tuple[int, int | None], Walk] = field(default_factory=dict)

    def __post_init__(self) -> None:
        without_sword_cave = [place for place in self.state.tracked if place.slot != MAGICAL_SWORD_SLOT]
        check = AcceptanceCheck(self.levels, with_tracked(self.state, without_sword_cave), self.overworld,
                                self.caves, self.rules)
        self.held = frozenset(check.closure()[0])

    def _walk(self, level: Level, target: int | None) -> Walk:
        key = (level.level_num, target)
        if key not in self._walks:
            self._walks[key] = walk_level(level, self.held, is_last_boss_open=False, uses_families=True,
                                          target=target, family_lists=self.rules.family_lists)
        return self._walks[key]

    def _enters(self, level: Level) -> bool:
        needs = self.rules.needs(self.caves.entry_door(level.level_num))
        if level.level_num == LEVEL_9:
            needs |= LONG_ITEMS | {LEVEL9_ENTRY}
        return needs <= self.held

    def reaches(self, place: PoolPlace) -> bool:
        if isinstance(place, LevelRoomPlace):
            room = place.room
            return (self._enters(place.level)
                    and self._walk(place.level, room.room_num).accepts(place.level, room.room_num)
                    and (not is_family_blocked(room, self.held, self.rules.family_lists)
                         or room.room_type > FAMILY_EXEMPT_LAYOUT)
                    and (Item.LADDER in self.held or room.room_type not in LADDER_LAYOUTS))
        if isinstance(place, ItemCellarPlace):
            return self._enters(place.level) and place.cellar.room_num in self._walk(place.level, None).cellars
        if isinstance(place, CaveSlotPlace):
            if place.slot == "armos":
                return True                   # VA-REJ-07: held from the start
            if place.slot == "coast":
                return Item.LADDER in self.held
            screens = self.caves.movable_screens(Destination.WHITE_SWORD_CAVE)
            return bool(screens) and self.rules.needs(screens[0]) <= self.held
        if isinstance(place, ShopWarePlace):
            return any(self.rules.needs(screen) <= self.held
                       for screen in self.caves.movable_screens(place.shop.destination))
        if isinstance(place, ExtraSlotPlace):
            return place.slot != MAGICAL_SWORD_SLOT and is_extra_slot_collected(place.slot, self.caves,
                                                                                self.held, self.rules)
        raise TypeError(place)


def check_magical_sword_hearts(levels: list[Level], state: ItemShuffleResult, extras: ExtraPoolItems,
                               overworld: Overworld, caves: CaveShuffle, hearts_required: int,
                               starting_hearts: int, white_sword_hearts_required: int,
                               rules: LogicRules = DEFAULT_RULES) -> bool:
    """The owner's heart check for a finished pass (the pass's staged levels,
    item shuffle result, extras and overworld).

    hearts_required and white_sword_hearts_required are the counts the two
    caves ask for in this pass: with Randomize Magical Sword on they are
    drawn before the acceptance check (change_sword_hearts), so the exact N
    is checked. The take-any allowance counts toward the white-sword cave's
    requirement too."""
    reach = AcceptanceHeartReach(levels, state, extras, overworld, caves, rules)
    take_any = take_any_heart_allowance(reachable_take_any_hearts(overworld, reach.held, rules))
    reachable = count_reachable_heart_containers(heart_container_places(levels, state, extras), reach,
                                                 starting_hearts + take_any, white_sword_hearts_required)
    return has_enough_heart_containers(hearts_required, starting_hearts, reachable + take_any)
