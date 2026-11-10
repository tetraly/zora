"""Item Counter (the ZORA flag item_counter; idea: Ultralavos): which places of a finished world count, per area.

An area is the overworld (0) or a level (1-9). Its places are the item places (places.all_item_places): the
places of the major pool, read from the finished world, where the items really are. Each counts once its item
is taken, by the bit the game sets (archipelago.pickup_check's: a room's or cellar's item bit, a cave's screen
bit, a once-only ware's ShopBoughtFlags bit).

Only what the item shuffle deals counts (owner rulings, 2026-11-10). Under Full (C06 = 3) that is every heart
container too. Under Item Only, Within Each Dungeon and None the bosses' heart containers are not dealt: a level's
heart container places then count only as many as the deal's own heart container records there (the coast's,
when it landed in the level), as a group of which that many count (heart containers are all alike, so whichever
the player takes first counts).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from ..flags.fields import ItemShuffleScope
from ..model.enums import Item
from ..model.game_world import GameWorld
from ..rom import inventory
from ..rom.code_patches import SHOPS_BY_NUMBER
from ..rom.item_counter import AREAS, CounterArea, table_bytes, ware_place
from ..rom.mirror_overworld import mirror_screen
from .places import Place, read_item
from .steps.item_shuffle_result import ItemShuffleResult

OVERWORLD = 0


def _overworld_place(place: Place, mirrored: bool) -> int:
    if place.is_shop:
        assert place.destination is not None and place.position is not None
        return ware_place(place.position, SHOPS_BY_NUMBER.index(place.destination))
    screen = place.screens[0] if place.screens else inventory.COAST_SCREEN
    return mirror_screen(screen) if mirrored else screen


def dealt_hearts(state: ItemShuffleResult) -> Counter[int]:
    """Each level's heart containers the deal itself placed there (its tracked records)."""
    return Counter(place.level for place in state.tracked
                   if place.item == Item.HEART_CONTAINER and place.level is not None)


def counter_areas(world: GameWorld, places: Sequence[Place], scope: ItemShuffleScope, hearts: Counter[int],
                  mirrored: bool = False) -> list[CounterArea]:
    """The ten areas' places. `scope` is the item shuffle's, resolved; `hearts`, dealt_hearts."""
    overworld = tuple(_overworld_place(place, mirrored) for place in places if place.level is None)
    areas = [CounterArea(inventory.room_flags(OVERWORLD), overworld)]
    for level in range(1, AREAS):
        own = [place for place in places if place.level == level]
        rooms = [place.room_num for place in own]
        assert all(room is not None for room in rooms)
        if scope is ItemShuffleScope.FULL:
            areas.append(CounterArea(inventory.room_flags(level), tuple(room for room in rooms if room is not None)))
            continue
        heart_rooms = tuple(place.room_num for place in own if place.room_num is not None
                            and read_item(world, place) == Item.HEART_CONTAINER)
        unique = tuple(place.room_num for place in own if place.room_num is not None
                       and read_item(world, place) != Item.HEART_CONTAINER)
        cap = min(hearts[level], len(heart_rooms))
        if cap == len(heart_rooms):
            unique, heart_rooms, cap = unique + heart_rooms, (), 0
        elif cap == 0:
            heart_rooms = ()
        areas.append(CounterArea(inventory.room_flags(level), unique, heart_rooms, cap))
    return areas


def counter_table(world: GameWorld, places: Sequence[Place], scope: ItemShuffleScope, state: ItemShuffleResult,
                  mirrored: bool = False) -> bytes:
    """The seed's table for asm/flags2/item-counter (zora/rom/item_counter.py)."""
    return table_bytes(counter_areas(world, places, scope, dealt_hearts(state), mirrored))
