"""
Intra-dungeon item shuffler for Zelda 1.

Shuffles items within each dungeon independently before the cross-dungeon
assumed fill runs. The two passes are strictly ordered:
  - shuffle_dungeon_items (this module): permutes items within each dungeon,
    establishing which room slots hold which dungeon-local items.
  - assumed_fill (item_randomizer.py): places major items across all locations
    using full reachability analysis on the already-shuffled world.

Running intra-dungeon shuffle first means assumed fill sees the final room
topology and can make correct reachability decisions — major items placed by
assumed fill are never moved afterward.

Within each dungeon the shuffle partitions items into two buckets:
  - Major-item slots: regular rooms whose vanilla item is a dungeon-major
    item (MAJOR_ITEMS ∪ HEART_CONTAINER) or TRIFORCE (when triforces_in_stairways
    is on), plus all ITEM_STAIRCASE rooms.
  - Non-major regular rooms: compasses, maps, keys, bombs, rupees, hearts
    (flag off), triforces (flag off). Shuffled among themselves only.

When triforces_in_stairways is on, the triforce participates in the major-item
slot pool — so it can land in any major-item slot (regular or staircase) with
uniform probability, instead of being forced into a staircase.

TRIFORCE_OF_POWER (Ganon, level 9) is never shuffled — it stays fixed. The
entrance room is never shuffled — items there are unreachable on entry.
"""

from zora.data_model import GameWorld, Item, Level, Room, RoomType, StaircaseRoom
from zora.game_config import GameConfig
from zora.item_randomizer import MAJOR_ITEMS
from zora.rng import Rng

# Items that must go in ITEM_STAIRCASE rooms (the "major" staircase constraint).
# Heart containers are included as dungeon-significant rewards.
_DUNGEON_MAJOR_ITEMS: frozenset[Item] = frozenset(MAJOR_ITEMS) | {Item.HEART_CONTAINER}

# Items that are never shuffled regardless of flags.
_FIXED_ITEMS: frozenset[Item] = frozenset({Item.TRIFORCE_OF_POWER, Item.NOTHING})


def _is_item_staircase(sr: StaircaseRoom) -> bool:
    return sr.room_type == RoomType.ITEM_STAIRCASE



def shuffle_dungeon_items(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Shuffle items within each dungeon independently. Mutates game_world in place.

    Must be called BEFORE assumed_fill so that major item placement sees the
    final room topology. Only runs when config.shuffle_within_dungeons is True.
    """
    if not config.shuffle_within_dungeons:
        return

    for level in game_world.levels:
        _shuffle_level(level, config.triforces_in_stairways, rng)


def _shuffle_level(level: Level, triforces_in_stairways: bool, rng: Rng) -> None:
    """Shuffle items within a single level. Mutates level in place.

    Two independent uniform shuffles run on disjoint pools:

    1. Major-item pool: regular rooms whose vanilla item is in
       _DUNGEON_MAJOR_ITEMS, plus (when triforces_in_stairways is on) the
       triforce room, plus all ITEM_STAIRCASE rooms. Items in this pool are
       permuted uniformly across all of these slots — triforce, when in the
       pool, lands in any slot with equal probability rather than being
       forced into a staircase.

    2. Non-major-regular pool: remaining regular rooms holding non-fixed
       items (compasses, maps, keys, bombs, rupees, hearts when flag off,
       triforces when flag off). Permuted among themselves only.

    Excluded from both pools: entrance rooms, fixed-item rooms
    (TRIFORCE_OF_POWER, NOTHING).
    """
    major_pool_items: frozenset[Item] = (
        _DUNGEON_MAJOR_ITEMS | {Item.TRIFORCE} if triforces_in_stairways
        else _DUNGEON_MAJOR_ITEMS
    )

    major_regular_rooms: list[Room] = []
    other_regular_rooms: list[Room] = []
    for room in level.rooms:
        if room.item in _FIXED_ITEMS:
            continue
        if room.room_num == level.entrance_room:
            continue
        if room.item in major_pool_items:
            major_regular_rooms.append(room)
        else:
            other_regular_rooms.append(room)

    item_staircase_rooms: list[StaircaseRoom] = [
        sr for sr in level.staircase_rooms if _is_item_staircase(sr) and sr.item is not None
    ]

    # Pool 1: major-item slots — regular major rooms + item-staircase rooms.
    major_slots: list[Room | StaircaseRoom] = list(major_regular_rooms) + list(item_staircase_rooms)
    if len(major_slots) >= 2:
        major_items: list[Item] = []
        for slot in major_slots:
            assert slot.item is not None
            major_items.append(slot.item)
        rng.shuffle(major_items)
        for slot, item in zip(major_slots, major_items, strict=True):
            slot.item = item

    # Pool 2: non-major regular rooms — permute among themselves.
    if len(other_regular_rooms) >= 2:
        other_items = [room.item for room in other_regular_rooms]
        rng.shuffle(other_items)
        for room, item in zip(other_regular_rooms, other_items, strict=True):
            room.item = item
