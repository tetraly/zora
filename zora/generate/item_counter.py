"""Item Counter (the ZORA flag item_counter; idea: Ultralavos): which places of a finished world count, per area.

An area is the overworld (0) or a level (1-9). It counts places, not items (rule of 2026-11-26, replacing the
2026-11-11 ruling that every level counts its item places under every shuffle):
- every place of the big item shuffle pool in it (places.all_item_places, read from the finished world, where the
  items really are; never Shuffle Minor Dungeon Drops' minor places);
- each level's Triforce piece spot whenever the pieces are not in that pool, Triforce Shuffle Off or Between levels
  (places.triforce_spot_rooms: the room holding the piece, or its item cellar). With Anywhere the spots are pool
  places already, so a piece counts wherever it lands, the overworld included.
Maps and compasses count only with Map & Compass Shuffle: Anywhere, the one value that puts them in the big pool;
Between levels is a shuffle of its own and leaves them out. So the first quest's levels read 4-3-3-3-3-3-3-4-2
with Map & Compass Shuffle Off or Between levels and 6-5-5-5-5-5-5-6-4 with Anywhere (level 9's map and compass
included); the second quest's follow its layout the same way. Each place counts once its item is taken, by the bit
the game sets (archipelago.pickup_check's: a room's or cellar's item bit, a cave's screen bit, a once-only ware's
ShopBoughtFlags bit). The table is indexed by CurLevel, the level the game has loaded, whatever number it shows.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

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


def counter_areas(places: Sequence[Place], mirrored: bool = False,
                  piece_spots: Mapping[int, int] | None = None) -> list[CounterArea]:
    """The ten areas' places: `places`, then each level's Triforce spot in `piece_spots` (data level -> room or
    item cellar), given when the pieces are not pool places."""
    piece_spots = piece_spots or {}
    overworld = tuple(_overworld_place(place, mirrored) for place in places if place.level is None)
    areas = [CounterArea(inventory.room_flags(OVERWORLD), overworld)]
    for level in range(1, AREAS):
        rooms = tuple(place.room_num for place in places if place.level == level)
        assert all(room is not None for room in rooms)
        spot = (piece_spots[level],) if level in piece_spots else ()
        areas.append(CounterArea(inventory.room_flags(level),
                                 tuple(room for room in rooms if room is not None) + spot))
    return areas


def counter_table(places: Sequence[Place], mirrored: bool = False,
                  piece_spots: Mapping[int, int] | None = None) -> bytes:
    """The seed's table for asm/flags2/item-counter (zora/rom/item_counter.py)."""
    return table_bytes(counter_areas(places, mirrored, piece_spots))
