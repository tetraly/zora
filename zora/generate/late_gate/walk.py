"""The late gate's walks (late-gate.md VA-REJ-01.2 and VA-REJ-01.3).

The walk moves between (room, side) states; sides are N, E, S, W and St
(the room's staircase).
- Leaving a room through a side needs the room's OWN side to be passable:
  not a wall, and not a closed shutter. The neighbor's facing side is
  never consulted, so edges are one-sided. Only same-level neighbors
  count. East and west sides connect across row edges (room 15 to 16)
  with no wrap guard (A26). Rooms off the level join only as stair links.
- Open, walk-through, locked and bombable sides are passable. Keys and bombs
  are not counted here.
- Shutters are open for triggers 1, 7, 3, 4 and 6. In quest 1's level 9,
  the room one row north of the entrance has all its shutter sides open.
- Inside a room, moves between sides follow the table in `_moves`. Rows
  match the layout byte with the monster bit ignored; the person row
  matches exactly $A6 (A25).
- A $1B or $9B room's east side is never an exit.
- Staircases link their exit rooms' St sides. The link is one-way from a
  usable end; both ends usable make it two-way. Item cellars ($3F) link
  their two exit rooms (the A and B bytes, normally both the cellar's room)
  the same way, so a usable stair room over a cellar has its St side as an
  exit the walk must reach; the reverse walk has no reverse for a link into
  an item cellar (A38).
- Entering a room through a side puts the walker at that door, so the
  entry side counts as reached and can be left through again. This is
  ZORA's own design (W10).

Pass condition: in both directions, from the start state, every room is
reached and every exit side of every room is reached.

The level-9 Ganon walk (VA-REJ-01.3) is a different walk. The last boss is
assumed alive, so trigger-3 shutters are closed. Cellars are dead ends, so
its graph has no cellar links. Row wraps are blocked. Only
entry into Ganon's room is needed. Everything else is the connectivity
walk's rulebook (stated since 23d15d0).
"""
from dataclasses import dataclass, field
from typing import cast

from ...model import room_grid
from ...model.enums import RoomAction, RoomType, Side
from ...model.levels import L9_ENTRY_PERSON, LEVEL_9, MERCHANT_LIST, Level
from ...model.rooms import DIAMOND_STAIRS_PUSH, PERSON_LAYOUT_BYTE, PUSH_BLOCK_VARIANT, Room, StaircaseRoom
from ..shapes.world import D_SHUTTER, D_WALL, GRID_COLS, side_of, sides_of

STAIR_SIDE = 4
ALL_SIDES = (Side.NORTH, Side.EAST, Side.SOUTH, Side.WEST, STAIR_SIDE)

_SHUTTER_OPEN_TRIGGERS = frozenset({RoomAction.ALL_DEAD, RoomAction.ALL_DEAD_ITEM, RoomAction.LAST_BOSS,
                                    RoomAction.BLOCK_DOOR, RoomAction.MONEY_OR_LIFE})
_STAIR_LAYOUTS = frozenset({RoomType.NARROW_STAIR_ROOM, RoomType.SPIRAL_STAIR_ROOM})
# The person row: the layout byte EXACTLY $A6 (the Black room + the flag).
# VA-1: a person room whose monster byte exceeds 32 does not restrict
# (a nonzero count index on a person code).
PERSON_MONSTER_BYTE_LIMIT = 32

State = tuple[int, int]


def _group(sides: tuple[int, ...]) -> dict[int, set[int]]:
    return {side: {other for other in sides if other != side} for side in sides}


_FREE_MOVES = _group(ALL_SIDES)
# Rows keyed on the layout byte with the monster high bit ignored (A25):
# $8E/$CE restrict like $0E, $92 like $12, and so on; push variants of $12,
# $27 and $0B do not restrict. The person row is matched separately on the
# layout byte EXACTLY $A6.
_VERTICAL_CHUTE: dict[int, set[int]] = {
    Side.NORTH: {Side.SOUTH}, Side.SOUTH: {Side.NORTH}, STAIR_SIDE: {Side.EAST}
}
_HORIZONTAL_CHUTE: dict[int, set[int]] = {
    Side.WEST: {Side.EAST}, Side.EAST: {Side.WEST}, STAIR_SIDE: {Side.NORTH}
}
_MOVES: dict[int, dict[int, set[int]]] = {
    RoomType.VERTICAL_CHUTE_ROOM: _VERTICAL_CHUTE,
    RoomType.VERTICAL_CHUTE_ROOM | PUSH_BLOCK_VARIANT: _VERTICAL_CHUTE,
    RoomType.HORIZONTAL_CHUTE_ROOM: _HORIZONTAL_CHUTE,
    RoomType.HORIZONTAL_CHUTE_ROOM | PUSH_BLOCK_VARIANT: _HORIZONTAL_CHUTE,
    RoomType.T_ROOM: _group((Side.NORTH, Side.WEST, Side.EAST, STAIR_SIDE)),
    RoomType.ZELDA_ROOM:
        {Side.NORTH: {Side.SOUTH}, Side.WEST: {Side.SOUTH}, Side.EAST: {Side.SOUTH}, STAIR_SIDE: {Side.SOUTH}},
    RoomType.LAVA_MOAT:
        {Side.NORTH: {Side.EAST}, Side.EAST: {Side.NORTH}, Side.SOUTH: {Side.WEST}, Side.WEST: {Side.SOUTH}},
    RoomType.TURNSTILE_ROOM | PUSH_BLOCK_VARIANT:
        {Side.NORTH: {Side.WEST}, Side.WEST: {Side.NORTH}, Side.SOUTH: {Side.EAST}, Side.EAST: {Side.SOUTH}},
}
_PERSON_MOVES = _group((Side.SOUTH, Side.WEST, Side.EAST, STAIR_SIDE))


def level9_entry_room(level: Level) -> int | None:
    """VA-WALK-08: level 9's Triforce gate room, one row north of the entrance, whose shutters count
    as open (its person opens them when Link holds the pieces, InitUnderworldPersonC).
    Deviation (docs/deviations.md): in every quest. VA-WALK-08 keeps a second-quest level 9's cell
    at $64, PRG0's gate room, even when its start room moves (B26), where the walks would then find
    the real gate room's shutters closed and level 9 shut."""
    if level.level_num != LEVEL_9:
        return None
    if level.entrance_room < GRID_COLS:
        return None
    return level.entrance_room - GRID_COLS


def _moves(room: Room, level9_entry: int | None) -> dict[int, set[int]]:
    """The room's row of the in-room move table."""
    if room.layout_byte == PERSON_LAYOUT_BYTE:
        if (room.monster_byte == MERCHANT_LIST
                or (room.room_num == level9_entry and room.enemy == L9_ENTRY_PERSON)
                or room.monster_byte > PERSON_MONSTER_BYTE_LIMIT):
            return _FREE_MOVES
        return _PERSON_MOVES
    return _MOVES.get(room.layout_code, _FREE_MOVES)


def are_shutters_open(room: Room, level9_entry: int | None, boss_alive: bool = False) -> bool:
    if room.room_num == level9_entry:
        return True
    trigger = room.room_action
    if boss_alive and trigger == RoomAction.LAST_BOSS:
        return False
    return trigger in _SHUTTER_OPEN_TRIGGERS


def is_side_passable(room: Room, side: Side, level9_entry: int | None, boss_alive: bool = False) -> bool:
    side_type = side_of(room, side)
    if side_type == D_WALL:
        return False
    if side_type == D_SHUTTER and not are_shutters_open(room, level9_entry, boss_alive):
        return False
    return True


def is_stair_usable(room: Room) -> bool:
    """Layout bits 0-5 are $1B/$1C, or trigger 5, or the layout byte
    without the monster bit is $5A (the $1A family's $5A / $DA)."""
    return (room.room_type in _STAIR_LAYOUTS or room.room_action == RoomAction.BLOCK_STAIRS
            or room.layout_code == DIAMOND_STAIRS_PUSH)


@dataclass
class Graph:
    room_numbers: set[int]
    start: State | None
    edges: dict[State, list[State]]
    exit_states: list[State]         # (room, side) sides that are exits
    # A38: the reverse walk uses the same graph with every link reversed;
    # a St side is an exit there when a REVERSED stair link leaves it.
    reverse_exit_states: list[State]
    # The item-cellar links among `edges`: a link into an item cellar has no
    # reverse (A38), so the reverse walk leaves each of these out once.
    cellar_links: list[tuple[State, State]] = field(default_factory=list)


def start_room(level: Level, level9_entry: int | None = None, boss_alive: bool = False) -> int | None:
    """The highest-numbered room (grid order) whose south side is passable."""
    block_rooms = cast("list[Room]", level.block.cells)
    for room_num in reversed(level.room_nums):
        if is_side_passable(block_rooms[room_num], Side.SOUTH, level9_entry, boss_alive):
            return room_num
    return None


def build_graph(level: Level, boss_alive: bool = False, transports: bool = True) -> Graph:
    """The connectivity walk's graph; boss_alive=True builds the level-9
    Ganon test's graph (trigger-3 shutters closed, row wraps blocked).
    Rooms off the level join only through stair links, so they never appear
    as states: a transport staircase ($3E) and, in the connectivity walk, an
    item cellar ($3F) each join their two exit rooms' St sides (late-gate.md
    "Rooms not on this level"); a cellar's link has no reverse. transports=False
    (Do Not Segment Dungeons) leaves the transport staircases out: doors alone must join the level.

    Fast-pathed: the late gate builds this once or more per attempt
    (thousands of times a seed), so the loop reads each room's four sides
    once and keeps to plain tuples and dicts."""
    # A26: the open walk steps across rows
    neighbor_of = room_grid.neighbor if boss_alive else room_grid.step
    room_numbers = set(level.room_nums)
    # an owned room number always holds a Room (see gate._room_table)
    block_rooms = cast("list[Room]", level.block.cells)
    level9_entry = level9_entry_room(level)
    edges: dict[State, list[State]] = {}
    exits: list[State] = []
    reverse_stair_exits: list[State] = []
    for room_number in level.room_nums:
        room = block_rooms[room_number]
        for from_side, targets in _moves(room, level9_entry).items():
            edges[(room_number, from_side)] = [(room_number, to_side) for to_side in targets]
        is_east_cut = room.layout_code == RoomType.NARROW_STAIR_ROOM   # $1B and $9B (A25)
        walls = sides_of(room)
        can_pass_shutters: bool | None = None
        for side in Side:
            if is_east_cut and side == Side.EAST:
                continue
            neighbor = neighbor_of(room_number, side)
            if neighbor is None or neighbor not in room_numbers:
                continue
            side_type = walls[side]
            if side_type == D_WALL:
                continue
            if side_type == D_SHUTTER:
                if can_pass_shutters is None:
                    can_pass_shutters = are_shutters_open(room, level9_entry, boss_alive)
                if not can_pass_shutters:
                    continue
            key = (room_number, side)
            links = edges.get(key)
            if links is None:
                edges[key] = [(neighbor, side.opposite)]
            else:
                links.append((neighbor, side.opposite))
            exits.append(key)
    cellar_links: list[tuple[State, State]] = []
    for stair in level.staircase_rooms:
        is_cellar = stair.room_type == RoomType.ITEM_STAIRCASE
        if is_cellar:
            # The Ganon test's cellars are dead ends (VA-REJ-01.3)
            if boss_alive:
                continue
            exit_rooms = _cellar_exit_rooms(stair)
        elif stair.room_type == RoomType.TRANSPORT_STAIRCASE and transports:
            exit_rooms = (stair.left_exit, stair.right_exit)
        else:
            continue
        left_room, right_room = exit_rooms
        if (left_room is None or right_room is None
                or left_room not in room_numbers or right_room not in room_numbers):
            continue
        directions = ((left_room, right_room),) if left_room == right_room else \
            ((left_room, right_room), (right_room, left_room))   # a cellar's room twice: one link
        for from_room, to_room in directions:
            if is_stair_usable(level.block.room(from_room)):
                link =((from_room, STAIR_SIDE), (to_room, STAIR_SIDE))
                edges.setdefault(link[0], []).append(link[1])
                exits.append(link[0])
                if is_cellar:
                    cellar_links.append(link)
                else:
                    reverse_stair_exits.append(link[1])
    start = start_room(level, level9_entry, boss_alive)
    reverse_exits = [state for state in exits if state[1] != STAIR_SIDE] + reverse_stair_exits
    return Graph(room_numbers, None if start is None else (start, Side.SOUTH), edges, exits,
                 reverse_exits, cellar_links)


def _cellar_exit_rooms(stair: StaircaseRoom) -> tuple[int | None, int | None]:
    """An item cellar's two exit rooms, its A and B bytes (SH-STAIR-14): the return room, and the
    B byte where it differs (A43)."""
    return stair.return_dest, stair.return_dest if stair.return_dest_b is None else stair.return_dest_b


def _closure(start: State, edges: dict[State, list[State]]) -> set[State]:
    seen = {start}
    stack = [start]
    while stack:
        state = stack.pop()
        for next_state in edges.get(state, ()):
            if next_state not in seen:
                seen.add(next_state)
                stack.append(next_state)
    return seen


class WalkResult:
    """Forward result computed eagerly; the reverse walk only when read."""

    def __init__(self, forward_rooms: set[int], forward_passed: bool,
                 graph: "Graph | None" = None,
                 reverse: "tuple[set[int], bool] | None" = None) -> None:
        self.forward_rooms = forward_rooms
        self.forward_passed = forward_passed
        self._graph = graph
        self._reverse_result = reverse

    def _reverse(self) -> tuple[set[int], bool]:
        if self._reverse_result is None:
            graph = self._graph
            assert graph is not None and graph.start is not None
            reverse_edges: dict[State, list[State]] = {}
            for state, next_states in graph.edges.items():
                for next_state in next_states:
                    sources = reverse_edges.get(next_state)
                    if sources is None:
                        reverse_edges[next_state] = [state]
                    else:
                        sources.append(state)
            for from_state, to_state in graph.cellar_links:   # no reverse (A38)
                reverse_edges[to_state].remove(from_state)
            reached = _closure(graph.start, reverse_edges)
            rooms = {room_number for room_number, _side in reached}
            passed = (rooms >= graph.room_numbers
                      and all(state in reached for state in graph.reverse_exit_states))
            self._reverse_result = (rooms, passed)
        return self._reverse_result

    @property
    def reverse_rooms(self) -> set[int]:
        return self._reverse()[0]

    @property
    def reverse_passed(self) -> bool:
        return self._reverse()[1]

    @property
    def passed(self) -> bool:
        return self.forward_passed and self.reverse_passed

    def verdict(self) -> str | None:
        if self.passed:
            return None
        if not self.forward_passed and not self.reverse_passed:
            return "both"
        return "forward" if not self.forward_passed else "reverse"

    def repair_reached(self) -> set[int]:
        """The repair's "reached": the forward result, except when the
        forward walk passed and the reverse failed."""
        return self.reverse_rooms if (self.forward_passed and not self.reverse_passed) \
            else self.forward_rooms


def connectivity_walk(level: Level, transports: bool = True) -> WalkResult:
    graph = build_graph(level, transports=transports)
    if not graph.room_numbers:
        return WalkResult(set(), True, reverse=(set(), True))
    if graph.start is None:
        return WalkResult(set(), False, reverse=(set(), False))
    forward = _closure(graph.start, graph.edges)
    forward_rooms = {room_number for room_number, _side in forward}
    forward_passed = (forward_rooms >= graph.room_numbers
                      and all(state in forward for state in graph.exit_states))
    return WalkResult(forward_rooms, forward_passed, graph=graph)


def gate_walk(level: Level, transports: bool = True) -> str | None:
    """None when the level passes; else 'forward' / 'reverse' / 'both'."""
    return connectivity_walk(level, transports).verdict()


def is_ganon_reachable(level: Level, ganon_room: int | None, transports: bool = True) -> bool:
    """VA-REJ-01.3's distinct walk: entry into Ganon's room from level 9's
    start room, with the last boss alive (trigger-3 shutters closed); without
    transport staircases under Do Not Segment Dungeons."""
    if ganon_room is None:
        return False
    graph = build_graph(level, boss_alive=True, transports=transports)
    if graph.start is None:
        return False
    reached = _closure(graph.start, graph.edges)
    return any(room_number == ganon_room for room_number, _side in reached)
