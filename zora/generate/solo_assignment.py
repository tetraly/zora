"""The two level-item switches in a single-player seed (docs/design/archipelago-items.md piece 7): BUILD places
the Triforces, maps and compasses in their levels as it always has; then each new item, in a drawn order, swaps
places with the item at a place drawn from its partner set, which Item Shuffle's reach decides, and FINISH writes
the result as Archipelago's games are written (finish.apply_assignment), its sanity check a solo game's.

The partner sets, by Item Shuffle as resolved (piece 7's table):
- Dungeon items only (C06 = 1): the tracked places and the new items' places, in any level or cave.
- Within each dungeon (C06 = 2): the dungeon places of the new item's own level (Place.level) that are tracked
  places, heart rooms or new items' places.
- Full (C06 = 3): every place of the seed.
A place a pin fixed (Armos Item, White Sword Item, Coast Item, Level 9 Item 1 and 2) is never a partner, so the pins
and their hints stay true. A swap that breaks a place's `forbids` (a piece on a side ware, the Triforce of Power in a
room) is drawn again; an assignment the strict walk refuses is drawn again whole, from where the stream stands.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import TYPE_CHECKING

from ..flags.fields import ItemShuffleScope
from ..model.enums import Destination, Item
from .finish import SEED_BYTES, Assignment, AssignmentUnbeatable, refusals, tracked_place
from .places import Place, item_pool, own_item, read_item
from .rng import Rng
from .steps.item_shuffle_result import TrackedPlace

if TYPE_CHECKING:
    from .pipeline import Built

SOLO_STREAM = b"zora solo items"          # 16 bytes at most (BLAKE2b's person)
SWAP_DRAWS = 100                           # draws for one new item before it stays where it is
# whole assignments drawn before the seed is refused: the 2026-11-21 scan's 900 seeds needed at most 39 (one seed;
# every other at most 12), and a draw costs a FINISH without serialization
ASSIGNMENT_ATTEMPTS = 200
NO_PIN = 0                                 # a cave pin's "Random" (FORCED_ITEM_OPTIONS[0])
ITEM_SHUFFLE_FIELD = "C06"


class SoloAssignmentFailed(RuntimeError):
    """No drawn assignment passed the strict walk within ASSIGNMENT_ATTEMPTS."""


def solo_rng(generation_seed: int) -> Rng:
    """The swaps' own stream, keyed by the generation seed as finish_rng is: BUILD's and FINISH's are untouched."""
    key = hashlib.blake2b(generation_seed.to_bytes(SEED_BYTES, "little"), digest_size=SEED_BYTES,
                          person=SOLO_STREAM).digest()
    return Rng(int.from_bytes(key, "little"))


def item_shuffle_scope(built: Built) -> ItemShuffleScope:
    """Item Shuffle as this seed resolved it."""
    return ItemShuffleScope(built.plan.settings.option(ITEM_SHUFFLE_FIELD))


def acts(built: Built) -> bool:
    """A switch resolved On under any Item Shuffle but None (decision 21)."""
    from .pipeline import extra_options
    return extra_options(built.plan).per_level_items and item_shuffle_scope(built) is not ItemShuffleScope.NONE


def identity(built: Built) -> dict[str, Item]:
    """BUILD's placement as an assignment: each place's item as the pool names it."""
    from .pipeline import extra_options
    extras = extra_options(built.plan)
    return {place.name: own_item(place, read_item(built.world, place), extras) for place in built.places}


def tracked_places(built: Built) -> set[str]:
    """The places of the item shuffle's tracked records: for each record the first unused place holding its item
    in its level or slot (a record's room may be stale: the late gate moves rooms with their items)."""
    state = built.result.item_shuffle_result
    assert state is not None
    used: set[str] = set()
    for record in state.tracked:
        item = Item(record.item)
        wanted = TrackedPlace(item, level=record.level, slot=record.slot)
        found = next((place for place in built.places if place.name not in used
                      and read_item(built.world, place) == item
                      and tracked_place(place, item) == wanted), None)
        if found is not None:
            used.add(found.name)
    return used


def pinned_places(built: Built) -> set[str]:
    """The places a pin fixed: level 9's pinned places (PS-ITEM-12) and the pinned caves."""
    state = built.result.item_shuffle_result
    assert state is not None
    alternatives = built.plan.alternatives
    caves = {Destination.ARMOS_ITEM: alternatives.armos_pin, Destination.WHITE_SWORD_CAVE: alternatives.white_sword_pin,
             Destination.COAST_ITEM: alternatives.coast_pin}
    found = set()
    for place in built.places:
        if place.is_dungeon and (place.level, place.room_num) in state.pinned_level_places:
            found.add(place.name)
        elif place.destination in caves and not place.is_shop and caves[place.destination] != NO_PIN:
            found.add(place.name)
    return found


def partner_sets(built: Built, new_places: list[Place]) -> dict[str, list[Place]]:
    """Each new item's place (by name) and the places its item may swap with, the place itself among them."""
    scope = item_shuffle_scope(built)
    pinned = pinned_places(built)
    tracked = tracked_places(built)
    new_names = {place.name for place in new_places}
    heart_rooms = {place.name for place in built.places
                   if place.is_dungeon and read_item(built.world, place) == Item.HEART_CONTAINER}
    sets = {}
    for new_place in new_places:
        if scope is ItemShuffleScope.FULL:
            partners = list(built.places)
        elif scope is ItemShuffleScope.DUNGEON_ITEMS_ONLY:
            partners = [place for place in built.places if place.name in tracked | new_names]
        else:
            partners = [place for place in built.places if place.is_dungeon and place.level == new_place.level
                        and place.name in tracked | heart_rooms | new_names]
        sets[new_place.name] = [place for place in partners if place.name not in pinned or place is new_place]
    return sets


def draw_assignment(built: Built, rng: Rng) -> dict[str, Item]:
    """One drawn assignment: BUILD's placement with each new item, in a drawn order, swapped with the item at a
    place drawn uniformly from its partner set (it may draw its own place and stay)."""
    from .pipeline import extra_options
    assignment = identity(built)
    pool = item_pool(extra_options(built.plan))
    new_items = level_items_moved(built)
    new_places = [place for place in built.places if assignment[place.name] in new_items]
    partners = partner_sets(built, new_places)
    order = list(new_places)
    rng.shuffle(order)
    where = {assignment[place.name]: place.name for place in new_places}
    for start in order:
        item = assignment[start.name]
        current = where[item]
        choices = partners[start.name]
        for _ in range(SWAP_DRAWS):
            other = choices[rng.below(len(choices))].name
            trial = dict(assignment)
            trial[current], trial[other] = trial[other], trial[current]
            if not refusals(built.places, trial, pool):
                if assignment[other] in where:
                    where[assignment[other]] = current
                where[item] = other
                assignment = trial
                break
    return assignment


def level_items_moved(built: Built) -> frozenset[Item]:
    """The new items: the pieces with Add Triforces, the maps and compasses with Add Maps/Compasses (the generic
    codes are level 8's piece and level 9's map and compass)."""
    from .pipeline import extra_options
    from .places import level_item_pool
    return level_item_pool(extra_options(built.plan))


def attempts(built: Built) -> Iterator[dict[str, Item]]:
    """The drawn assignments, in order, from the swaps' own stream."""
    rng = solo_rng(built.plan.generation_seed)
    for _ in range(ASSIGNMENT_ATTEMPTS):
        yield draw_assignment(built, rng)


def solo_assignment(built: Built) -> Assignment:
    """The first drawn assignment FINISH's strict walk accepts (a solo game: its failure is hard)."""
    from .pipeline import finish_world
    for assignment in attempts(built):
        try:
            finish_world(built, assignment)
        except AssignmentUnbeatable:
            continue
        return assignment
    raise SoloAssignmentFailed(f"no assignment of the level items passed the walk in {ASSIGNMENT_ATTEMPTS} draws")

