"""Shuffle Dungeon Start Room (B26; post-shapes-b9.md PS-START-01 to PS-START-03): each level's
start room moves to a room on the level's edge, whose door on that edge opens; Link enters through
it (FP-ENTR-01's arrival codes 1-4) and leaves the level by it (FP-ENTR-02's exit room)."""
from dataclasses import dataclass

from ...model import room_grid
from ...model.enums import Enemy, Side, WallType
from ...model.levels import Level, LevelBlock
from ...model.rooms import Room, RoomPlace, StaircaseRoom
from ..rng import IntRng
from .monster_lists import RoomLists

LEVEL_9 = 9
# PS-START-01: the sides in the order each room lists its edges, with PS-START-03's arrival
# code for each (FP-ENTR-01: 1 from above, 2 from below, 3 from the left, 4 from the right)
EDGE_SIDES = (Side.NORTH, Side.SOUTH, Side.WEST, Side.EAST)
ARRIVAL_CODES = {Side.NORTH: 1, Side.SOUTH: 2, Side.WEST: 3, Side.EAST: 4}
# PS-START-02: a room moved out of (or into) a room list loses its B palette bits; the new start
# room's are 2 (bit 1 set)
LISTLESS_START_PALETTE = 0b10


@dataclass(frozen=True)
class Edge:
    """A room of the level and a side where the next room is off the grid or another level's."""
    room: int
    side: Side


def level_edges(level: Level) -> list[Edge]:
    """PS-START-01: the level's edges in room order and, within a room, up, down, left, right.
    An edge to a room of no level or of the same level is not one. Level 9 lists only downward
    edges, and only below a room of level 9."""
    block = level.block
    edges = []
    for room in sorted(level.room_nums):
        for side in EDGE_SIDES:
            if level.level_num == LEVEL_9 and not (side == Side.SOUTH and _above_is_level_9(level, room)):
                continue
            next_room = room_grid.neighbor(room, side)
            owner = None if next_room is None else block.owner_of(next_room)
            if next_room is None or (owner is not None and owner is not level):
                edges.append(Edge(room, side))
    return edges


def _above_is_level_9(level: Level, room: int) -> bool:
    above = room_grid.neighbor(room, Side.NORTH)
    return above is not None and level.block.owner_of(above) is level


def _transport_staircases(block: LevelBlock) -> list[StaircaseRoom]:
    """PS-START-02: the block's staircases (layout byte $3E or $3F), in room order."""
    return [cell for cell in block.cells if isinstance(cell, StaircaseRoom)]


def _redirect_staircase(staircases: list[StaircaseRoom], old: int, new: int) -> None:
    """PS-START-02's staircase fix: in the first staircase with an exit naming `old`, each exit
    naming it names `new`. A transport's exits are its left and right ones (tables A and B), an
    item cellar's its return room (A, and B when it differs)."""
    for stair in staircases:
        exits = ("left_exit", "right_exit") if stair.return_dest is None else ("return_dest", "return_dest_b")
        named = [attr for attr in exits if getattr(stair, attr) == old]
        if named:
            for attr in named:
                setattr(stair, attr, new)
            return


def _exchange_contents(first: Room, second: Room) -> None:
    """PS-START-02: the monster, layout, item and trigger bytes (tables C to F) change rooms;
    the door bytes (A, B) stay with the cell.

    ZORA's deviation (2026-10-29; docs/deviations.md): when either room holds the hungry Goriya, the
    inner palette selectors (table B bits 0-1) change rooms too, so the Goriya keeps its black floor
    (inner 0, SH-DOOR-01) and the other room its own look. As the spec has it, a Goriya moved into the
    old start room took that room's palette (14 of 300 seeds of a beta 10 player's flags)."""
    for attr in ("enemy_info", "layout_info", "item_info", "secret_info"):
        first_value, second_value = getattr(first, attr), getattr(second, attr)
        setattr(first, attr, second_value)
        setattr(second, attr, first_value)
    if Enemy.HUNGRY_GORIYA in (first.enemy, second.enemy):
        first.palette_1, second.palette_1 = second.palette_1, first.palette_1


def _exchange_in_list(room_lists: RoomLists, level: Level, block_index: int, old: int, new: int) -> bool:
    """PS-START-02: the level's room list exchanges the two rooms, with their stored values (a
    value follows its room's contents). False when either room is not in the list."""
    places = room_lists.rooms.get(level.level_num, [])
    old_place, new_place = RoomPlace(block_index, old), RoomPlace(block_index, new)
    in_list = old_place in places and new_place in places
    swapped = {old_place: new_place, new_place: old_place}
    room_lists.rooms[level.level_num] = [swapped.get(place, place) for place in places]
    old_value, new_value = room_lists.values.pop(old_place, None), room_lists.values.pop(new_place, None)
    if old_value is not None:
        room_lists.values[new_place] = old_value
    if new_value is not None:
        room_lists.values[old_place] = new_value
    return in_list


def exit_room(level: Level, start: int, side: Side) -> int:
    """PS-START-03's room through the open side: the start room's number plus the side's step,
    without wrapping the column; past either end of the block, the first room, in room order,
    of another level."""
    exit_number = start + side.delta
    if 0 <= exit_number < len(level.block.cells):
        return exit_number
    return next(room for room in range(len(level.block.cells))
                if (owner := level.block.owner_of(room)) is not None and owner is not level)


def swap_start_room(level: Level, block_index: int, edge: Edge, staircases: list[StaircaseRoom],
                    room_lists: RoomLists) -> None:
    """PS-START-02 and PS-START-03 for one level and its drawn edge."""
    block = level.block
    old, new = level.entrance_room, edge.room
    _redirect_staircase(staircases, new, old)
    _exchange_contents(block.room(old), block.room(new))
    block.room(old).walls.south = WallType.SOLID_WALL
    block.room(new).walls[edge.side] = WallType.OPEN_DOOR
    if not _exchange_in_list(room_lists, level, block_index, old, new):
        block.room(old).palette_1 = 0
        block.room(new).palette_1 = LISTLESS_START_PALETTE
    if level.level_num == LEVEL_9:
        _move_level_9_person_room(level, block_index, old, new, staircases, room_lists)
    level.entrance_room = new
    level.arrival_code = ARRIVAL_CODES[edge.side]
    level.exit_room = exit_room(level, new, edge.side)


def _move_level_9_person_room(level: Level, block_index: int, old: int, new: int,
                              staircases: list[StaircaseRoom], room_lists: RoomLists) -> None:
    """PS-START-02 for level 9: the rooms above the two start rooms (SH-ROOM-05's person room)
    exchange their contents too; the room above the new start room is the person room later
    passes use, and the list names the room above the old one instead of it."""
    block = level.block
    old_above, new_above = old + Side.NORTH.delta, new + Side.NORTH.delta
    _redirect_staircase(staircases, new_above, old_above)
    _exchange_contents(block.room(old_above), block.room(new_above))
    block.room(new_above).palette_1 = 0
    places = room_lists.rooms.get(level.level_num, [])
    new_place, old_place = RoomPlace(block_index, new_above), RoomPlace(block_index, old_above)
    if new_place in places:
        room_lists.rooms[level.level_num] = [old_place if place == new_place else place for place in places]
        if new_place in room_lists.values:
            room_lists.values[old_place] = room_lists.values.pop(new_place)
        block.room(old_above).palette_1 = 0


def swap_start_rooms(blocks: list[LevelBlock], levels: list[Level], room_lists: RoomLists, rng: IntRng) -> None:
    """PS-START-01 to PS-START-03: every block's staircases are listed first; then, for levels
    1 to 9 by the number the block labels them with (a second-quest pair's player number,
    SH-NUM-03), one edge is drawn uniformly and the start room moves to it. A level with no edge
    keeps its start room."""
    staircases = {id(block): _transport_staircases(block) for block in blocks}
    block_index = {id(block): index for index, block in enumerate(blocks)}
    for level in sorted(levels, key=lambda level: level.rom_level_num):
        edges = level_edges(level)
        if not edges:
            continue
        edge = edges[rng.below(len(edges))]
        swap_start_room(level, block_index[id(level.block)], edge, staircases[id(level.block)], room_lists)
