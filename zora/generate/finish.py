"""FINISH with an assignment (Archipelago Phase 2, External mode; docs/archipelago.md): another
filler's item in each of a built world's places, then everything the ROM shows that depends on
which item sits where, done again for the new placement.

ZORA mode never comes here: pipeline.finish with no assignment serializes the built world as it
is. apply_assignment works on a copy of the built world, and draws only from its own stream
(finish_rng: the generation seed and "finish"), never BUILD's.
"""
from __future__ import annotations

import hashlib
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ..model.enums import Destination, Item
from ..model.overworld import Shop
from ..rom.game_config import DungeonNothingCode, GameConfig
from .places import Place, PlaceKind, major_pool, read_item, write_item
from .rng import IntRng, Rng
from .steps.item_shuffle_result import (
    LETTER_SLOT,
    MAGICAL_SWORD_SLOT,
    ItemShuffleResult,
    TrackedPlace,
    shop_ware_slot,
)
from .steps.potion_shop import BLUE_POTION_PRICES
from .steps.shop_items_in_pool import PRICES_BY_ITEM

if TYPE_CHECKING:
    from ..model.game_world import GameWorld
    from .pipeline import Built


class Foreign:
    """Another player's item (Archipelago): this player gets nothing from it."""

    def __repr__(self) -> str:
        return "FOREIGN"


FOREIGN = Foreign()
# Owner decision 4 (2026-10-08): another player's item shows as a rupee in v1, as Archipelago's
# TLoZ world does. Phase 4a may give it its own look.
FOREIGN_ITEM = Item.FIVE_RUPEES

Assignment = Mapping[str, Item | Foreign]

# The finish stream's key: the generation seed, and this label.
FINISH_STREAM = b"zora finish"
SEED_BYTES = 8


class AssignmentUnbeatable(ValueError):
    """The sanity check (R4) failed where it is a hard error: the walk with the received items
    granted (any game), or the strict walk in a solo game."""

    def __init__(self, sanity: Sanity) -> None:
        self.sanity = sanity
        super().__init__(f"assignment fails ZORA's acceptance walk: {sanity}")


class AssignmentRefused(ValueError):
    """An assignment FINISH cannot write, with every reason."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("assignment refused: " + "; ".join(reasons))


def finish_rng(generation_seed: int) -> Rng:
    """FINISH's own stream, keyed by the generation seed and "finish": the player's machine can
    repeat FINISH exactly, and BUILD's stream is never touched."""
    key = hashlib.blake2b(generation_seed.to_bytes(SEED_BYTES, "little"), digest_size=SEED_BYTES,
                          person=FINISH_STREAM).digest()
    return Rng(int.from_bytes(key, "little"))


def written_item(value: Item | Foreign) -> Item:
    """The item code the ROM gets for an assigned value."""
    return FOREIGN_ITEM if isinstance(value, Foreign) else value


def refusals(places: list[Place], assignment: Assignment, pool: frozenset[Item]) -> list[str]:
    """Why the assignment cannot be written: a name that is no place of this build, an item
    outside the build's major pool (FOREIGN aside), or an item the place forbids (R2)."""
    by_name = {place.name: place for place in places}
    reasons = [f"{name}: no such place in this seed" for name in assignment if name not in by_name]
    for name, value in assignment.items():
        place = by_name.get(name)
        if place is None or isinstance(value, Foreign):
            continue
        if value not in pool:
            reasons.append(f"{name}: {value.name} is not in this seed's major pool")
        elif value in place.forbids:
            reasons.append(f"{name}: {value.name} is forbidden there")
    return reasons


def one_time_places(places: list[Place]) -> tuple[tuple[int, int], ...]:
    """GameConfig.one_time_places: each ware place as (shop number, position)."""
    from ..rom.code_patches import SHOPS_BY_NUMBER
    pairs = []
    for place in places:
        if place.is_shop:
            assert place.destination is not None and place.position is not None
            pairs.append((SHOPS_BY_NUMBER.index(place.destination), place.position))
    return tuple(pairs)


def needs_remap(places: list[Place], assignment: Assignment) -> bool:
    """R2: a magical sword ($03) in a dungeon room or cellar reads as "no item" unless ZORA's
    remap is written, which makes $0E the "no item" code there instead."""
    return any(place.is_dungeon and assignment.get(place.name) == Item.MAGICAL_SWORD for place in places)


# --- the tracked items -----------------------------------------------------------------------

# The item shuffle's special-cave slots, by the place's destination (ItemShuffleResult.caves).
CAVE_SLOTS: dict[Destination, str] = {
    Destination.ARMOS_ITEM: "armos",
    Destination.WHITE_SWORD_CAVE: "white_sword",
    Destination.COAST_ITEM: "coast",
    Destination.MAGICAL_SWORD_CAVE: MAGICAL_SWORD_SLOT,
    Destination.LETTER_CAVE: LETTER_SLOT,
}


def tracked_place(place: Place, item: Item) -> TrackedPlace:
    """VA-REJ-07's record of an item in a place: its level, or its slot."""
    if place.is_dungeon:
        return TrackedPlace(item, level=place.level)
    assert place.destination is not None
    if place.is_shop:
        assert place.position is not None
        return TrackedPlace(item, slot=shop_ware_slot(place.destination, place.position))
    return TrackedPlace(item, slot=CAVE_SLOTS[place.destination])


@dataclass
class Tracking:
    """The tracked items after an assignment: where each sits in this world (`tracked`), and the
    tracked items this world does not hold (`elsewhere`: in another player's world)."""
    tracked: list[TrackedPlace]
    elsewhere: list[Item]


def rebuild_tracking(world: GameWorld, built: Built) -> Tracking:
    """The item shuffle's tracked records (and the extras') for the assigned world: each tracked
    item as BUILD tracked them, found again among the places in place order (one place per
    record). With Shuffle Blue Potion, the letter is tracked, wherever it is, when a tracked record
    is the potion shop's ware (potion_shop.shuffle_blue_potion's rule)."""
    from .pipeline import extra_options
    assert built.result.item_shuffle_result is not None
    blue_potion = extra_options(built.plan).shuffle_blue_potion
    records = [record for record in built.result.item_shuffle_result.tracked
               if not (blue_potion and record.item == Item.LETTER)]
    holding = [(place, read_item(world, place)) for place in built.places]
    used: set[str] = set()
    tracking = Tracking([], [])

    def track(item: Item, record: TrackedPlace | None = None) -> None:
        """The item's place: the one BUILD's record names if it still holds the item (so an
        unchanged placement keeps BUILD's records), else the first holding it."""
        candidates = [place for place, held in holding if held == item and place.name not in used]
        place = next((place for place in candidates if tracked_place(place, item) == record), None)
        place = place or next(iter(candidates), None)
        if place is None:
            tracking.elsewhere.append(item)
            return
        used.add(place.name)
        tracking.tracked.append(tracked_place(place, item))

    for record in records:
        track(Item(record.item), replace(record, item=Item(record.item)))
    if blue_potion:
        potion = next(place for place in built.places if place.kind == PlaceKind.POTION_SHOP)
        potion_slot = tracked_place(potion, Item.LETTER).slot
        if any(record.slot == potion_slot for record in tracking.tracked):
            if any(held == Item.LETTER for _place, held in holding):
                track(Item.LETTER)
            elif not extra_options(built.plan).randomize_letter:
                tracking.tracked.append(TrackedPlace(Item.LETTER, slot=LETTER_SLOT))    # in its own cave
            else:
                tracking.elsewhere.append(Item.LETTER)
    return tracking


def with_tracking(state: ItemShuffleResult, tracking: Tracking, world: GameWorld,
                  places: list[Place]) -> ItemShuffleResult:
    """A copy of the item shuffle's result with the rebuilt records and the special caves' items."""
    caves = dict(state.caves)
    for place in places:
        if place.destination in CAVE_SLOTS and CAVE_SLOTS[place.destination] in caves:
            caves[CAVE_SLOTS[place.destination]] = int(read_item(world, place))
    return replace(state, tracked=list(tracking.tracked), caves=caves)


# --- prices (SI-PRICE-01, Shuffle Blue Potion) -------------------------------------------------

def _uniform(rng: IntRng, prices: tuple[int, int]) -> int:
    low, high = prices
    return low + rng.below(high - low + 1)


def reprice_wares(world: GameWorld, built: Built, rng: IntRng) -> None:
    """The joined wares' prices for what they now hold, in join order: SI-PRICE-01's classes; a
    blue potion in a ware other than its own costs 25-55 (potion_shop.price_potion_wares); a
    ware holding its own joined item or an unpriced one keeps its price from before SI-PRICE-01."""
    extras = built.result.extra_pool_items
    if extras is None:
        return
    for ware, own_item, slot_price in zip(extras.shop_wares, extras.shop_items, extras.slot_prices, strict=True):
        shop = world.overworld.get_cave(ware.shop.destination, Shop)
        assert shop is not None
        held = shop.ware(ware.position)
        if held.item == own_item or (held.item not in PRICES_BY_ITEM and held.item != Item.BLUE_POTION):
            held.price = slot_price
        elif held.item == Item.BLUE_POTION:
            held.price = _uniform(rng, BLUE_POTION_PRICES)
        else:
            held.price = _uniform(rng, PRICES_BY_ITEM[held.item])


# --- the hint text --------------------------------------------------------------------------

def recompose_hint_text(world: GameWorld, built: Built, item_shuffle_result: ItemShuffleResult, rng: Rng,
                        foreign: bool = False) -> None:
    """The hint text again on the assigned world: the hint text step (compose_hint_text), B19's
    pointer exchange when it ran, and ship_hint_text. foreign: the assignment holds another
    player's item; a hint naming a place that holds one says it is an item for another player
    (owner decision, 2026-10-08), never what the ROM shows there, and never which item it is."""
    from .generation_pass import compose_hint_text
    from .pipeline import extra_options
    from .ship import ship_hint_text
    from .steps.shuffle_dungeon_text import shuffle_dungeon_text
    result = built.result
    if result.hint_assignment is None:          # no hint text step ran (the shape stage only)
        return
    chosen = built.plan
    hint_text = compose_hint_text(world, item_shuffle_result, result.hint_assignment, rng, extra_options(chosen),
                                  chosen.alternatives, result.maze_offers, FOREIGN_ITEM if foreign else None)
    if chosen.steps.shuffle_dungeon_text:
        hint_text = shuffle_dungeon_text(hint_text, rng)
    ship_hint_text(world, hint_text)


# --- the sanity check (R4) --------------------------------------------------------------------

@dataclass(frozen=True)
class Sanity:
    """ZORA's acceptance check (E1, E3, E4, E5) on the assigned world, two ways (owner decision
    2026-10-08). Places holding FOREIGN give this player nothing.
      strict:  this player's items placed in other worlds are unavailable; a hard error only in a
               solo game (no FOREIGN place, nothing received), a diagnostic otherwise, since a
               multiworld player's own world is often meant to be unbeatable alone;
      granted: the items this player receives from other worlds are held from the start; a hard
               error in every game: a failure means ZORA's walk and the logic disagree, or an
               own-world item sits behind something it unlocks.
    Each is the first failing check's label (E1, E3, E4, E5), or None when it passes."""
    solo: bool
    strict: str | None
    granted: str | None

    @property
    def hard_failure(self) -> bool:
        return self.granted is not None or (self.solo and self.strict is not None)


def sanity_check(world: GameWorld, built: Built, tracking: Tracking, solo: bool,
                 received: Collection[Item]) -> Sanity:
    """R4's two walks on the assigned world (Sanity)."""
    from .acceptance_check import acceptance_check
    from .pipeline import extra_options
    state = built.result.item_shuffle_result
    caves = built.result.overworld
    assert state is not None and caves is not None
    rules = extra_options(built.plan).logic_rules
    # strict: an item elsewhere is still to be collected, and no place holds it
    strict_state = replace(state, tracked=[*tracking.tracked, *(TrackedPlace(item) for item in tracking.elsewhere)])
    strict = acceptance_check(world.levels, strict_state, world.overworld, caves, rules)
    granted_state = replace(state, tracked=list(tracking.tracked))
    granted = acceptance_check(world.levels, granted_state, world.overworld, caves, rules,
                               granted=frozenset(int(item) for item in received))
    return Sanity(solo, strict, granted)


# --- applying an assignment -------------------------------------------------------------------

@dataclass
class Finished:
    """What apply_assignment hands to serialization: the configuration (the remap); and the
    tracked items as the assigned world holds them, and the sanity check's result (R4), for the
    caller."""
    config: GameConfig
    tracking: Tracking
    sanity: Sanity | None = None


def apply_assignment(world: GameWorld, built: Built, assignment: Assignment, rng: Rng, recompute: bool = True,
                     received: Collection[Item] = (), check: bool = True) -> Finished:
    """Write the assignment into `world` (a copy of the built world), refusing it whole if any
    part breaks a rule (AssignmentRefused); then redo every output that depends on which item
    sits where (docs/archipelago.md, R3): the tracked items, the joined wares' prices and the hint
    text, drawing from `rng` in that order. The one-time wares and the seed's code follow at
    serialization. recompute=False writes the items and the remap only (tests 2 and 3).

    received: this player's items that other worlds hold (Archipelago gives them). check: run
    the sanity check (R4, Sanity), raising AssignmentUnbeatable on a hard failure; off for tests
    that write arbitrary permutations."""
    from .pipeline import extra_options
    places = built.places
    reasons = refusals(places, assignment, major_pool(extra_options(built.plan)))
    if reasons:
        raise AssignmentRefused(reasons)
    for place in places:
        if place.name in assignment:
            write_item(world, place, written_item(assignment[place.name]))
    # every ware place is sold once, whatever it holds, so that buying it is a location check
    config = replace(built.plan.config, one_time_places=one_time_places(places))
    if needs_remap(places, assignment):
        config = replace(config, dungeon_nothing_code=DungeonNothingCode.ZORA_REMAP)
    tracking = rebuild_tracking(world, built)
    if recompute:
        assert built.result.item_shuffle_result is not None
        item_shuffle_result = with_tracking(built.result.item_shuffle_result, tracking, world, places)
        reprice_wares(world, built, rng)
        recompose_hint_text(world, built, item_shuffle_result, rng,
                            foreign=any(isinstance(value, Foreign) for value in assignment.values()))
    finished = Finished(config, tracking)
    if check:
        solo = not received and not any(isinstance(value, Foreign) for value in assignment.values())
        finished.sanity = sanity_check(world, built, tracking, solo, received)
        if finished.sanity.hard_failure:
            raise AssignmentUnbeatable(finished.sanity)
    return finished
