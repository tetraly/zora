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
  - Staircase-eligible: must land in ITEM_STAIRCASE rooms.
    By default: only major items (from MAJOR_ITEMS) and heart containers.
    When triforces_in_stairways is on: Item.TRIFORCE is also eligible.
  - Non-staircase: compasses, maps, triforces (flag off), hearts (flag off).
    These permute freely among regular room slots.

TRIFORCE_OF_POWER (Ganon, level 9) is never shuffled — it stays fixed.
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

    The shuffle proceeds in two steps:

    1. Triforce swap (only when triforces_in_stairways is on): each dungeon's
       triforce room is randomly swapped with one of the item staircase rooms,
       so the triforce may end up in a staircase room and the displaced major
       item moves to the triforce room.

    2. Regular-room shuffle: all regular rooms that hold a non-fixed item
       (compass, map, heart container, triforce, keys, bombs, rupees, etc.)
       are permuted among themselves. Staircase rooms are only touched in
       step 1 — the shuffler never permutes items between staircase rooms.
    """
    item_staircase_rooms: list[StaircaseRoom] = [
        sr for sr in level.staircase_rooms if _is_item_staircase(sr) and sr.item is not None
    ]
    regular_rooms: list[Room] = [
        room for room in level.rooms
        if room.item not in _FIXED_ITEMS
    ]

    if not regular_rooms:
        return

    # Step 1: optionally swap the triforce into a staircase room.
    if triforces_in_stairways and item_staircase_rooms:
        triforce_rooms = [r for r in regular_rooms if r.item == Item.TRIFORCE]
        for triforce_room in triforce_rooms:
            # Pick a random staircase room to swap with.
            sr = rng.choice(item_staircase_rooms)
            assert sr.item is not None
            triforce_room.item, sr.item = sr.item, triforce_room.item

    # Step 2: shuffle all regular rooms among themselves freely.
    items = [room.item for room in regular_rooms]
    assert len(items) == len(regular_rooms), (
        f"L{level.level_num}: item pool size {len(items)} != location pool size {len(regular_rooms)}"
    )
    assert all(item not in _FIXED_ITEMS for item in items), (
        f"L{level.level_num}: fixed item found in shuffle pool: {[i.name for i in items if i in _FIXED_ITEMS]}"
    )

    rng.shuffle(items)
    for room, item in zip(regular_rooms, items, strict=True):
        room.item = item

    # Verify pool is fully consumed — every slot filled, none left over.
    remaining = [room for room in regular_rooms if room.item in _FIXED_ITEMS]
    assert len(remaining) == 0, (
        f"L{level.level_num}: {len(remaining)} room(s) not filled after shuffle: "
        f"{[hex(r.room_num) for r in remaining]}"
    )
