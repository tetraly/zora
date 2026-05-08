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

import logging

from zora.data_model import (
    Direction,
    Enemy,
    GameWorld,
    Item,
    Level,
    Room,
    RoomAction,
    RoomType,
    StaircaseRoom,
    WallType,
)
from zora.game_config import GameConfig
from zora.item_randomizer import MAJOR_ITEMS
from zora.rng import Rng

logger = logging.getLogger(__name__)

# Items that must go in ITEM_STAIRCASE rooms (the "major" staircase constraint).
# Heart containers are included as dungeon-significant rewards.
_DUNGEON_MAJOR_ITEMS: frozenset[Item] = frozenset(MAJOR_ITEMS) | {Item.HEART_CONTAINER}

# Items that are never shuffled regardless of flags. NOTHING is intentionally
# NOT in this set — empty rooms are eligible to receive minor items via Pool 2,
# subject to the entrance-room and black-room-NPC exclusions below.
_FIXED_ITEMS: frozenset[Item] = frozenset({Item.TRIFORCE_OF_POWER})

# Rooms with these enemies must stay empty — the NPC interaction occupies the
# room and any item there interferes with or hides behind the NPC.
_BLACK_ROOM_NPC_ENEMIES: frozenset[Enemy] = frozenset({
    Enemy.OLD_MAN, Enemy.OLD_MAN_2, Enemy.OLD_MAN_3, Enemy.OLD_MAN_4,
    Enemy.OLD_MAN_5, Enemy.OLD_MAN_6,
    Enemy.BOMB_UPGRADER, Enemy.MUGGER,
    Enemy.HUNGRY_GORIYA,
})

# Walls that can be traversed without bombs. BOMB_HOLE and SOLID_WALL are excluded.
_NO_BOMB_PASSABLE: frozenset[WallType] = frozenset({
    WallType.OPEN_DOOR,
    WallType.WALK_THROUGH_WALL_1,
    WallType.WALK_THROUGH_WALL_2,
    WallType.LOCKED_DOOR_1,
    WallType.LOCKED_DOOR_2,
    WallType.SHUTTER_DOOR,
})

_DIR_OFFSETS: list[tuple[Direction, int]] = [
    (Direction.NORTH, -0x10),
    (Direction.SOUTH, +0x10),
    (Direction.EAST, +1),
    (Direction.WEST, -1),
]
_OPPOSITE: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
}

_MAP_PLACEMENT_MAX_RETRIES = 50


def _rooms_reachable_without_bombs(level: Level) -> set[int]:
    """Flood-fill from level.entrance_room, traversing only walls that don't
    require bombs — with one exception: BOMB_HOLE walls of the entrance room
    itself are treated as passable. The simulated player has bombs on entry
    (cave bombs are easy to obtain) and can bomb their way out of the entry
    room, but cannot bomb deeper rooms because they may not have found the
    map / item drops yet.

    Returns the set of reachable room_nums (regular rooms + transport-
    staircase exit rooms reached via triggered staircases)."""
    room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}
    reachable: set[int] = set()
    if level.entrance_room not in room_by_num:
        return reachable

    def _wall_passable(room: Room, direction: Direction) -> bool:
        wall = room.walls[direction]
        if wall in _NO_BOMB_PASSABLE:
            return True
        # Entrance room only: bombing through a BOMB_HOLE is allowed.
        if room.room_num == level.entrance_room and wall == WallType.BOMB_HOLE:
            return True
        return False

    def _expand(stack: list[int]) -> None:
        while stack:
            rn = stack.pop()
            if rn in reachable:
                continue
            reachable.add(rn)
            room = room_by_num.get(rn)
            if room is None:
                continue
            row, col = rn >> 4, rn & 0xF
            for direction, offset in _DIR_OFFSETS:
                if direction == Direction.NORTH and row == 0:
                    continue
                if direction == Direction.SOUTH and row == 7:
                    continue
                if direction == Direction.WEST and col == 0:
                    continue
                if direction == Direction.EAST and col == 15:
                    continue
                if not _wall_passable(room, direction):
                    continue
                neighbor = rn + offset
                if neighbor not in room_by_num:
                    continue
                neighbor_room = room_by_num[neighbor]
                if not _wall_passable(neighbor_room, _OPPOSITE[direction]):
                    continue
                stack.append(neighbor)

    _expand([level.entrance_room])

    # Follow transport staircases — both exits become reachable when the
    # trigger room is reachable. Iterate until no new staircase fires.
    changed = True
    while changed:
        changed = False
        for sr in level.staircase_rooms:
            if sr.room_type != RoomType.TRANSPORT_STAIRCASE:
                continue
            if sr.left_exit is None or sr.right_exit is None:
                continue
            if sr.left_exit in reachable or sr.right_exit in reachable:
                fresh: list[int] = []
                for exit_rn in (sr.left_exit, sr.right_exit):
                    if exit_rn not in reachable:
                        fresh.append(exit_rn)
                        changed = True
                if fresh:
                    _expand(fresh)

    return reachable


def _map_placement_ok(level: Level, eligible_room_nums: frozenset[int]) -> bool:
    """Return True if the MAP sits in a room reachable from the entrance
    without going through any BOMB_HOLE wall. Only checks maps in
    eligible_room_nums (rooms the shuffler can actually move items between);
    a map pinned outside that pool is treated as ok because re-shuffling
    can't relocate it."""
    map_rooms = [
        r for r in level.rooms
        if r.item == Item.MAP and r.room_num in eligible_room_nums
    ]
    if not map_rooms:
        return True
    reachable = _rooms_reachable_without_bombs(level)
    return all(r.room_num in reachable for r in map_rooms)


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

    2. Non-major-regular pool: remaining regular rooms — minor-item rooms
       (compasses, maps, keys, bombs, rupees, hearts when flag off, triforces
       when flag off) AND empty (NOTHING) rooms. Including empty rooms gives
       the shuffle more bomb-free slots, which the map-placement retry below
       relies on.

    Excluded from both pools: entrance rooms, black-room NPC rooms (old men,
    bomb upgrader, mugger, hungry goriya), and TRIFORCE_OF_POWER rooms.
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
        if room.enemy_spec.enemy in _BLACK_ROOM_NPC_ENEMIES:
            # NPC rooms must stay empty — any current NOTHING item is fixed.
            continue
        if room.room_action == RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM:
            # The room's item is dropped after killing all enemies — moving it
            # would break the drop puzzle, and NOTHING here causes a phantom
            # Magical Sword drop. Keep the slot fixed.
            continue
        if room.item in major_pool_items:
            major_regular_rooms.append(room)
        else:
            # Includes NOTHING-rooms: empty slots become eligible to receive
            # minor items, expanding the pool of safe placements.
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

    # Pool 2: non-major regular rooms — permute among themselves. Retry until
    # the MAP lands in a room reachable from the entrance without going through
    # any BOMB_HOLE. Falls back to the last attempt if no valid placement is
    # found in _MAP_PLACEMENT_MAX_RETRIES — non-fatal, downstream validation
    # will catch fully unreachable layouts.
    if len(other_regular_rooms) >= 2:
        other_items = [room.item for room in other_regular_rooms]
        eligible_nums = frozenset(r.room_num for r in other_regular_rooms)
        for attempt in range(_MAP_PLACEMENT_MAX_RETRIES):
            rng.shuffle(other_items)
            for room, item in zip(other_regular_rooms, other_items, strict=True):
                room.item = item
            if _map_placement_ok(level, eligible_nums):
                break
        else:
            logger.warning(
                "L%d: map placement exhausted %d retries — accepting "
                "potentially bomb-gated map",
                level.level_num, _MAP_PLACEMENT_MAX_RETRIES,
            )
