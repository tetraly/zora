"""Move each level's map near its entrance (SH-MAP-03..06).

Runs on the pass's staged levels, after the late gate. Cost of a traversal =
1 for bombable or walk-through sides, 0 otherwise (SH-MAP-03); stair links
cost 0. Among rooms holding bombs/5-rupees/a key/compass/map, the minimum
cost from the entrance defines the candidate pool. A room found by several
minimum routes counts several times (SH-MAP-04); each instance is weighted
by its grid distance (rows plus columns) from the entrance, with the
documented off-by-one: first instance weight +1, last instance weight -1
(floored at zero). The chosen room swaps its whole item byte (item, boss
sound and dark flag, SH-MAP-05/06) with the map room. Four times in five, the map's new
room gets the kill-for-item trigger if it had none or plain kill-all; the test draws a number
whatever the trigger.
"""
from collections import deque

from ...model import room_grid
from ...model.enums import Item, RoomAction, RoomType, Side, WallType
from ...model.levels import Level
from ..rng import Rng
from ..shapes.tables import (
    MAP_MOVE_TRIGGER_CODES,
    MAP_MOVE_TRIGGER_PROB_DEN,
    MAP_MOVE_TRIGGER_PROB_NUM,
    T3_REPLACEABLE,
)

BOMBABLE_OR_WALK = frozenset({WallType.WALK_THROUGH_WALL_1, WallType.WALK_THROUGH_WALL_2,
                              WallType.BOMB_HOLE})
# SH-MAP-03: the rooms a map may move to hold bombs, five rupees, a key, the
# compass or the map
CANDIDATE_ITEMS = frozenset(Item(code) for code in T3_REPLACEABLE | MAP_MOVE_TRIGGER_CODES)
# SH-MAP-05: the triggers the map's new room may trade for kill-for-item
REPLACEABLE_TRIGGERS = (RoomAction.NONE, RoomAction.ALL_DEAD)


def _cost(wall: WallType) -> int:
    return 1 if wall in BOMBABLE_OR_WALK else 0


def _room_graph(level: Level) -> dict[int, list[tuple[int, int]]]:
    """Each of the level's rooms with the rooms it leads to and the cost of
    the step (SH-MAP-03)."""
    room_numbers = set(level.room_nums)
    links: dict[int, list[tuple[int, int]]] = {room_number: [] for room_number in room_numbers}
    for room in level.rooms:
        for side in Side:
            neighbour = room_grid.neighbour(room.room_num, side)
            if neighbour is None or neighbour not in room_numbers:
                continue
            wall = room.walls[side]
            if wall == WallType.SOLID_WALL:       # solid: no traversal
                continue
            links[room.room_num].append((neighbour, _cost(wall)))
    for stair in level.block.staircases:
        first, second = stair.left_exit, stair.right_exit
        if (stair.room_type == RoomType.TRANSPORT_STAIRCASE and first is not None
                and second is not None and first in links and second in links):
            links[first].append((second, 0))
            links[second].append((first, 0))
        # item cellars only ever loop back to their own house: no new reach.
    return links


def _dijkstra(links: dict[int, list[tuple[int, int]]], start: int
              ) -> tuple[dict[int, int], dict[int, int]]:
    distance = {start: 0}
    count = {start: 1}
    queue: deque[int] = deque([start])
    while queue:
        room_number = queue.popleft()
        for next_room, cost in links[room_number]:
            new_distance = distance[room_number] + cost
            if next_room not in distance or new_distance < distance[next_room]:
                distance[next_room] = new_distance
                count[next_room] = count[room_number]
                if cost == 0:
                    queue.appendleft(next_room)
                else:
                    queue.append(next_room)
            elif new_distance == distance[next_room]:
                count[next_room] += count[room_number]
    return distance, count


def move_map_near_entrance(level: Level, rng: Rng) -> None:
    """Move the level's map room toward the entrance (SH-MAP-03..07).

    SH-MAP-07: a level with no candidate, or whose candidates all weigh
    zero, keeps its map and draws nothing (both skips are unreached; the
    spec lets a rebuild omit them).
    """
    entrance = level.entrance_room
    links = _room_graph(level)
    distance, count = _dijkstra(links, entrance)
    block = level.block
    entries: list[tuple[int, int]] = []      # (room number, weight)
    for room_number in sorted(links):
        if room_number not in distance or block.room(room_number).item not in CANDIDATE_ITEMS:
            continue
        grid_distance = (abs(room_grid.row(room_number) - room_grid.row(entrance))
                         + abs(room_grid.column(room_number) - room_grid.column(entrance)))
        entries.extend([(room_number, grid_distance)] * max(1, count[room_number]))
    if not entries:
        return                         # SH-MAP-07: no candidate, no draw
    min_cost = min(distance[room_number] for room_number, _weight in entries)
    entries = [(room_number, weight) for room_number, weight in entries if distance[room_number] == min_cost]
    options = [room_number for room_number, _weight in entries]
    weights = [weight for _room, weight in entries]
    # SH-MAP-04 off-by-one (quirk, reproduced): first +1, last -1 (floor 0).
    weights[0] += 1
    weights[-1] = max(0, weights[-1] - 1)
    if all(weight == 0 for weight in weights):
        return                         # SH-MAP-07: zero total weight, no draw
    # SH-MAP-07: the draw comes first, then the map's room is located.
    chosen = block.room(rng.weighted(options, weights))
    map_room = next(room for room in level.rooms if room.item == Item.MAP)
    # Quirk (SH-MAP-05/06): the whole item byte is swapped, so the dark flag
    # and the boss sound (which the late gate has set by now) move with the
    # items.
    map_room.item_info, chosen.item_info = chosen.item_info, map_room.item_info
    # SH-MAP-05: the four-in-five test draws one number whatever the trigger; only trigger 0 or
    # 1 changes. A last-boss room (trigger 3, VA-REJ-20) keeps its trigger and the map with it.
    gets_item_trigger = rng.chance(MAP_MOVE_TRIGGER_PROB_NUM, MAP_MOVE_TRIGGER_PROB_DEN)
    if gets_item_trigger and chosen.room_action in REPLACEABLE_TRIGGERS:
        chosen.room_action = RoomAction.ALL_DEAD_ITEM
