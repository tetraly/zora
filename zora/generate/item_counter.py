"""Item Counter (the ZORA flag item_counter; idea: Ultralavos): which places of a finished world count, per area.

An area is the overworld (0) or a level (1-9). Its places are the item places (places.all_item_places): the
places of the major pool, read from the finished world, where the items really are. Each counts once its item
is taken, by the bit the game sets (archipelago.pickup_check's: a room's or cellar's item bit, a cave's screen
bit, a once-only ware's ShopBoughtFlags bit).

Every level counts all its item places, heart containers included, under every item shuffle (owner ruling,
2026-11-11): a level's total follows its dungeon layout alone (the first quest's 3-2-2-2-2-2-2-3-2, the second
quest's 2-2-2-3-2-2-2-3-2 by the level numbers the game shows), never the shuffle, so a seed whose shuffle was
rolled at random does not show which one it rolled, and a heart container counts the moment it is taken wherever
the deal put it. The table is indexed by CurLevel, the level the game has loaded, whatever number it shows.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..rom import inventory
from ..rom.code_patches import SHOPS_BY_NUMBER
from ..rom.item_counter import AREAS, CounterArea, table_bytes, ware_place
from ..rom.mirror_overworld import mirror_screen
from .places import Place

OVERWORLD = 0


def _overworld_place(place: Place, mirrored: bool) -> int:
    if place.is_shop:
        assert place.destination is not None and place.position is not None
        return ware_place(place.position, SHOPS_BY_NUMBER.index(place.destination))
    screen = place.screens[0] if place.screens else inventory.COAST_SCREEN
    return mirror_screen(screen) if mirrored else screen


def counter_areas(places: Sequence[Place], mirrored: bool = False) -> list[CounterArea]:
    """The ten areas' places."""
    overworld = tuple(_overworld_place(place, mirrored) for place in places if place.level is None)
    areas = [CounterArea(inventory.room_flags(OVERWORLD), overworld)]
    for level in range(1, AREAS):
        rooms = tuple(place.room_num for place in places if place.level == level)
        assert all(room is not None for room in rooms)
        areas.append(CounterArea(inventory.room_flags(level), tuple(room for room in rooms if room is not None)))
    return areas


def counter_table(places: Sequence[Place], mirrored: bool = False) -> bytes:
    """The seed's table for asm/flags2/item-counter (zora/rom/item_counter.py)."""
    return table_bytes(counter_areas(places, mirrored))
