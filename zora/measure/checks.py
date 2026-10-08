"""Spec invariants as executable checks (the "Check" lines of docs/spec/shapes-behavior.md).

Every function takes a parsed GameWorld and returns (passed, message). Checks
that the spec marks as generator-internal (SH-FLOW-03 attempt caps,
SH-GRID-04 band widening) can only be approximated from a ROM; see docstrings.
"""
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise

from zora.model.enums import Enemy, Item, RoomType, Side, WallType
from zora.model.game_world import GameWorld
from zora.model.levels import Level
from zora.model.room_grid import neighbour
from zora.model.rooms import Room, StaircaseRoom

STAIR_POOL_LAYOUTS = (RoomType.TRANSPORT_STAIRCASE, RoomType.ITEM_STAIRCASE)

BOSS_CODES = frozenset({
    0x31, 0x32, 0x33, 0x34, 0x36, 0x38, 0x39, 0x3C, 0x3D, 0x3E,
    0x42, 0x43, 0x44, 0x45, 0x47, 0x48,
})

CELLAR_COUNTS = {1: 1, 2: 0, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 2, 9: 2}
STAIR_BUDGET = {1: 1, 2: 0, 3: 1, 4: 1, 5: 2, 6: 2, 7: 2, 8: 3, 9: 8}


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    passed: bool
    message: str


Check = Callable[[GameWorld], CheckResult]


def _room_cells(level: Level) -> set[int]:
    return {r.room_num for r in level.rooms}


def _stairs(level: Level) -> set[int]:
    return {s.room_num for s in level.staircase_rooms}


def _linked_rooms(staircase: StaircaseRoom) -> set[int]:
    """The rooms a staircase joins: a transport's two exits, an item cellar's return room."""
    if staircase.room_type == RoomType.TRANSPORT_STAIRCASE:
        rooms = [staircase.left_exit, staircase.right_exit]
    else:
        rooms = [staircase.return_dest]
    return {room for room in rooms if room is not None}


def level_pieces(level: Level) -> list[set[int]]:
    """The level's pieces on the map (SH-GRID-07): its rooms grouped by grid adjacency,
    whatever the walls between them, largest first."""
    rooms = _room_cells(level)
    pieces: list[set[int]] = []
    for start in sorted(rooms):
        if any(start in piece for piece in pieces):
            continue
        piece = {start}
        stack = [start]
        while stack:
            room = stack.pop()
            for side in Side:
                other = neighbour(room, side)
                if other in rooms and other not in piece:
                    piece.add(other)
                    stack.append(other)
        pieces.append(piece)
    return sorted(pieces, key=len, reverse=True)


def own_staircases(level: Level) -> list[StaircaseRoom]:
    """The level's staircases, without a cell another level of its block also lists and whose
    staircase joins only that level's rooms. Quirk (SH-STAIR-09): a finished ROM can list such a
    cell twice, in level 9's stairway list as well as level 7's or 8's (cell $02 at the head of
    level 9's list); the staircase leads into the other level and is counted there."""
    rooms = set(level.room_nums)
    others = [other for other in level.block.levels if other is not level]
    return [staircase for staircase in level.staircase_rooms
            if _linked_rooms(staircase) & rooms
            or not any(staircase.room_num in other.staircase_nums
                       and _linked_rooms(staircase) & set(other.room_nums) for other in others)]


def _grid_of(level: Level) -> int:
    return 0 if level.level_num <= 6 else 1


def _by_grid(gw: GameWorld) -> tuple[dict[int, Level], dict[int, Level]]:
    g0: dict[int, Level] = {}
    g1: dict[int, Level] = {}
    for level in gw.levels:
        (g0 if _grid_of(level) == 0 else g1)[level.level_num] = level
    return g0, g1


def _adjacency(gw: GameWorld) -> dict[tuple[int, int], list[int]]:
    """Directed edges (u → v): u's side toward v is non-solid and v exists in
    the same grid. Stair links are undirected pairs added on top."""
    edges: dict[tuple[int, int], list[int]] = {}
    for level in gw.levels:
        grid = _grid_of(level)
        by_num = {r.room_num: r for r in level.rooms}
        for c, room in by_num.items():
            for side in Side:
                nb = c + side.delta
                if nb < 0 or nb > 0x7F:
                    continue
                if room.walls[side] == WallType.SOLID_WALL:
                    continue
                if level.block.owner_of(nb) is not None:
                    edges.setdefault((grid, c), []).append(nb)
        # stair links
        for s in level.staircase_rooms:
            if s.room_type == RoomType.TRANSPORT_STAIRCASE:
                for a, b in ((s.left_exit, s.right_exit),):
                    for x, y in ((s.room_num, a), (s.room_num, b), (a, b), (b, a),
                                 (a, s.room_num), (b, s.room_num)):
                        if x is not None and y is not None:
                            edges.setdefault((grid, x), []).append(y)
            else:
                if s.return_dest is not None:
                    edges.setdefault((grid, s.room_num), []).append(s.return_dest)
                    edges.setdefault((grid, s.return_dest), []).append(s.room_num)
    return edges


def _reach(edges: dict[tuple[int, int], list[int]], grid: int, start: int) -> set[int]:
    seen = {start}
    stack = [start]
    while stack:
        u = stack.pop()
        for v in edges.get((grid, u), []):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------

def check_grid_tiled(gw: GameWorld) -> CheckResult:
    """SH-GRID-01/08: the grid is tiled except for cells growth never reaches, which the
    spec does not bound ("no longer a strict invariant"); the levels 7-9 grid always keeps
    at least one cell no level owns (SH-GRID-08's spare cell). The count's rate is compared,
    not checked (compare rows SH-GRID-16/17). Quirk: a level whose band ends inside another
    level's can seal that level off from the columns only it may grow into (SH-GRID-16), so
    a whole edge strip stays unowned: up to 18 cells in ZORA's 2,000 baseline seeds (2 ROMs
    over six), up to 6 in the 1,000 final corpus ROMs."""
    stairs: set[tuple[int, int]] = set()
    for level in gw.levels:
        for c in _stairs(level):
            stairs.add((_grid_of(level), c))
    missing = [(grid, c) for grid in (0, 1) for c in range(0x80)
               if gw.blocks[grid].owner_of(c) is None and (grid, c) not in stairs]
    spare = [c for grid, c in missing if grid == 1]
    return CheckResult("SH-GRID-01", bool(spare),
                       f"{len(missing)} unowned cells, {len(spare)} on levels 7-9's grid (first 5: {missing[:5]})")


def check_grid_connectivity(gw: GameWorld) -> CheckResult:
    """SH-GRID-09: every room mutually reachable with its level's entrance
    (directed engine rule: each side traversed by its own room's door state;
    stair links count)."""
    edges = _adjacency(gw)
    bad = []
    for level in gw.levels:
        grid = _grid_of(level)
        rooms = _room_cells(level)
        if level.entrance_room not in rooms:
            continue  # entrance check covers this
        fwd = _reach(edges, grid, level.entrance_room)
        # reverse edges
        rev_edges: dict[tuple[int, int], list[int]] = {}
        for (g, u), vs in edges.items():
            for v in vs:
                rev_edges.setdefault((g, v), []).append(u)
        rev = _reach(rev_edges, grid, level.entrance_room)
        miss_f = rooms - fwd
        miss_r = rooms - rev
        if miss_f or miss_r:
            bad.append((level.level_num, len(miss_f), len(miss_r)))
    return CheckResult("SH-GRID-09", not bad,
                       f"levels failing fwd/rev reach: {bad[:6]}")


def _ganon_rooms(level9: Level) -> list[Room]:
    """Ganon's room is identified by its monster, in any layout: later passes
    move it off layout $28 (in 842 of 1,000 finished corpus ROMs)."""
    return [room for room in level9.rooms if room.enemy == Enemy.THE_BEAST]


def _zelda_room(level9: Level) -> Room | None:
    """Zelda's room: the last level-9 room holding her monster list, in any
    layout (VA-REJ-01.3); only 13 of 1,000 finished corpus ROMs keep $27."""
    zelda = [room for room in level9.rooms if room.enemy == Enemy.THE_KIDNAPPED]
    return zelda[-1] if zelda else None


def check_ganon_reachable(gw: GameWorld) -> CheckResult:
    """SH-GRID-10: L9's Ganon room is reachable from L9's entrance."""
    l9 = next((level for level in gw.levels if level.level_num == 9), None)
    if l9 is None:
        return CheckResult("SH-GRID-10", False, "no level 9")
    ganon = [room.room_num for room in _ganon_rooms(l9)]
    if not ganon:
        return CheckResult("SH-GRID-10", False, "no Ganon room in L9")
    reach = _reach(_adjacency(gw), 1, l9.entrance_room)
    ok = all(g in reach for g in ganon)
    return CheckResult("SH-GRID-10", ok, f"ganon rooms {ganon}, reached={sorted(g in reach for g in ganon)}")


def check_zelda_not_dark(gw: GameWorld) -> CheckResult:
    """SH-GRID-11 (approximated): Zelda's room is not dark."""
    l9 = next((level for level in gw.levels if level.level_num == 9), None)
    if l9 is None:
        return CheckResult("SH-GRID-11", False, "no level 9")
    zelda = _zelda_room(l9)
    if zelda is None:
        return CheckResult("SH-GRID-11", False, "no Zelda room in L9")
    return CheckResult("SH-GRID-11", not zelda.is_dark, f"zelda room {zelda.room_num:02X}")


def check_numbering_sorted(gw: GameWorld) -> CheckResult:
    """SH-NUM-01 (with sorted shapes on): room counts non-decreasing within
    each set. The corpus option state is assumed sorted."""
    g0, g1 = _by_grid(gw)
    s0 = [len(g0[n].rooms) for n in sorted(g0)]
    s1 = [len(g1[n].rooms) for n in sorted(g1)]
    ok = all(a <= b for a, b in pairwise(s0)) and \
         all(a <= b for a, b in pairwise(s1))
    return CheckResult("SH-NUM-01", ok, f"counts {s0} / {s1}")


def check_door_sync(gw: GameWorld) -> CheckResult:
    """SH-DOOR-03: across every doorway between same-level rooms, both sides
    match or form an open/shutter one-way."""
    bad: list[str] = []
    for level in gw.levels:
        by_num = {r.room_num: r for r in level.rooms}
        for c, room in sorted(by_num.items()):
            for side in (Side.EAST, Side.SOUTH):
                nb = c + side.delta
                if nb > 0x7F or level.block.owner_of(nb) is not level:
                    continue
                nroom = by_num.get(nb)
                if nroom is None:
                    continue
                a, b = room.walls[side], nroom.walls[side.opposite]
                if a == b:
                    continue
                if {int(a), int(b)} == {int(WallType.OPEN_DOOR), int(WallType.SHUTTER_DOOR)}:
                    continue
                bad.append(f"L{level.level_num} {c:02X}/{nb:02X} {int(a)}|{int(b)}")
    return CheckResult("SH-DOOR-03", not bad,
                       f"{len(bad)} mismatched doorways (first 5: {bad[:5]})")


def check_entrances(gw: GameWorld) -> CheckResult:
    """SH-ENT-01/03: start rooms south open, own-level neighbour, layout $21,
    item none."""
    bad = []
    for level in gw.levels:
        ent = level.entrance_room
        room = next((r for r in level.rooms if r.room_num == ent), None)
        if room is None:
            bad.append((level.level_num, "no entrance room"))
            continue
        if room.walls.south != WallType.OPEN_DOOR:
            bad.append((level.level_num, "south not open"))
        if room.room_type != RoomType.ENTRANCE_ROOM:
            bad.append((level.level_num, "layout not $21"))
        if room.item != Item.NOTHING:
            bad.append((level.level_num, "item not none"))
        if not any(level.block.owner_of(n) is level
                   for n in (ent - 16, ent + 16, ent - 1, ent + 1) if 0 <= n <= 0x7F):
            bad.append((level.level_num, "no same-level neighbour"))
    return CheckResult("SH-ENT-01/03", not bad, f"problems: {bad[:6]}")


def check_level9_entrance(gw: GameWorld) -> CheckResult:
    """SH-ENT-02: L9 entrance on bottom row, room above is L9."""
    l9 = next((level for level in gw.levels if level.level_num == 9), None)
    if l9 is None:
        return CheckResult("SH-ENT-02", False, "no level 9")
    ent = l9.entrance_room
    above_ok = ent >= 0x70 and any(r.room_num == ent - 16 for r in l9.rooms)
    return CheckResult("SH-ENT-02", above_ok, f"entrance {ent:02X}")


def check_cellar_counts(gw: GameWorld) -> CheckResult:
    """SH-STAIR-03: item cellar counts 1,0,1,1,1,1,1,2,2."""
    got = {}
    for level in gw.levels:
        got[level.level_num] = sum(1 for s in own_staircases(level)
                                   if s.room_type == RoomType.ITEM_STAIRCASE)
    bad = [(n, got.get(n), want) for n, want in sorted(CELLAR_COUNTS.items())
           if got.get(n) != want]
    return CheckResult("SH-STAIR-03", not bad, f"mismatches: {bad[:6]}")


def check_stair_budget(gw: GameWorld) -> CheckResult:
    """SH-STAIR-02: cellars + transports = budget + pieces - 1; with SH-STAIR-03's
    cellar counts, transports = the budget's transports + pieces - 1 (level 9: six,
    seven when it is in two pieces).

    Pieces are counted as SPATIAL regions of the level's rooms (grid
    adjacency regardless of door type) — the basis under which the corpus
    passes this check 1000/1000 and under which ZORA generates (SH-GRID-07
    extra pieces come from band limits and seed cells, not from closed wall
    door pairs; see SPEC-GAP 21). Staircases are the level's own
    (own_staircases)."""
    bad = []
    for level in gw.levels:
        pieces = len(level_pieces(level))
        total = len(own_staircases(level))
        want = STAIR_BUDGET[level.level_num] + max(0, pieces - 1)
        if total != want:
            bad.append((level.level_num, total, want, pieces))
    return CheckResult("SH-STAIR-02", not bad,
                       f"(level, actual, expected, pieces) mismatches: {bad[:6]}")


def check_transport_same_level(gw: GameWorld) -> CheckResult:
    """SH-STAIR-09/13 (revised check wording): every transport staircase's far
    room is reachable, by ordinary doors or by the staircase itself, from its
    level's own entrance."""
    edges = _adjacency(gw)
    bad = []
    for level in gw.levels:
        grid = _grid_of(level)
        reach = _reach(edges, grid, level.entrance_room) if level.rooms else set()
        for s in own_staircases(level):
            if s.room_type != RoomType.TRANSPORT_STAIRCASE:
                continue
            if s.room_num not in reach:
                bad.append(f"L{level.level_num} stair {s.room_num:02X} unreachable")
                continue
            bad.extend(f"L{level.level_num} stair {s.room_num:02X} end {e:02X} unreachable"
                       for e in (s.left_exit, s.right_exit) if e is not None and e not in reach)
    return CheckResult("SH-STAIR-09", not bad,
                       f"unreachable transport parts: {len(bad)} (first 5 {bad[:5]})")


def check_triforce_rooms(gw: GameWorld) -> CheckResult:
    """SH-ROOM-01: each of levels 1-8 has exactly one room with item $1B and
    layout $29."""
    bad = []
    for level in gw.levels:
        if level.level_num == 9:
            continue
        tris = [r for r in level.rooms if int(r.item) == 0x1B]
        lay = [r for r in tris if r.room_type == RoomType.TRIFORCE_ROOM]
        if len(tris) != 1 or len(lay) != 1:
            bad.append((level.level_num, len(tris), len(lay)))
    return CheckResult("SH-ROOM-01", not bad, f"mismatches: {bad[:6]}")


def check_grumble(gw: GameWorld) -> CheckResult:
    """SH-ROOM-04: exactly one L7 room with monster list $36."""
    l7 = next((level for level in gw.levels if level.level_num == 7), None)
    if l7 is None:
        return CheckResult("SH-ROOM-04", False, "no level 7")
    n = sum(1 for r in l7.rooms if r.enemy == Enemy.HUNGRY_GORIYA)
    return CheckResult("SH-ROOM-04", n == 1, f"{n} grumble rooms")


def check_heart_containers(gw: GameWorld) -> CheckResult:
    """SH-BOSS-06: each of levels 1-8 has exactly one heart container ($1A),
    in a room with a boss."""
    bad = []
    for level in gw.levels:
        if level.level_num == 9:
            continue
        hcs = [r for r in level.rooms if int(r.item) == 0x1A]
        if len(hcs) != 1:
            bad.append((level.level_num, f"{len(hcs)} HCs"))
            continue
        if hcs[0].enemy.value not in BOSS_CODES:
            bad.append((level.level_num, "HC not on boss"))
    return CheckResult("SH-BOSS-06", not bad, f"problems: {bad[:6]}")


def check_compass_map(gw: GameWorld) -> CheckResult:
    """SH-ITEM-01: exactly one compass ($16) and one map ($17) per level."""
    bad = []
    for level in gw.levels:
        comp = sum(1 for r in level.rooms if int(r.item) == 0x16)
        mapn = sum(1 for r in level.rooms if int(r.item) == 0x17)
        if comp != 1 or mapn != 1:
            bad.append((level.level_num, comp, mapn))
    return CheckResult("SH-ITEM-01", not bad, f"mismatches: {bad[:6]}")


def check_palette_selectors(gw: GameWorld) -> CheckResult:
    """SH-DOOR-01 (U23), as finished ROMs keep it: every level room's outer
    selector is 2 and every person room's inner selector 0. (Zelda's inner
    2 is a shape-stage rule: B2 moves her monster and layout bytes but not
    the selector, and she ships on inner 3 in 301 of 1,000 final ROMs.)"""
    rooms = [r for level in gw.levels for r in level.rooms]
    bad_outer = sum(r.palette_0 != 2 for r in rooms)
    bad_person = sum(r.palette_1 != 0 for r in rooms if r.is_person)
    return CheckResult("SH-DOOR-01", not (bad_outer or bad_person),
                       f"outer not 2: {bad_outer}/{len(rooms)}; person inner not 0: {bad_person}")


def check_minimap_synthesis(gw: GameWorld) -> CheckResult:
    """SH-MAP-01: the minimap (bitmap, drawing commands through their
    terminator, start, cursor) must equal the full synthesis from the level's
    shape. Bytes past the terminator are never read and keep older values."""
    from zora.generate.shapes.minimap import drawn_commands, synthesize_minimap
    bad = []
    for level in gw.levels:
        cells = {r.room_num for r in level.rooms}
        data, cmds, start, cursor = synthesize_minimap(cells)
        if (data, cmds, start, cursor) != (level.map_data, drawn_commands(level.map_ppu_commands),
                                           level.map_start, level.map_cursor_offset):
            bad.append(level.level_num)
    return CheckResult("SH-MAP-01", not bad,
                       f"minimap mismatch levels: {bad[:9]}")


BLOCK_NAMES = ("1-6", "7-9")


def check_triforce_of_power(gw: GameWorld) -> CheckResult:
    """Room-item hiding (QUESTIONS #39; aldonunez CreateRoomObjects /
    CheckUnderworldSecrets / Ganon_ActivateRoomItem). Reads EVERY room of
    both quest-1 blocks, not only the rooms a level reaches: this is a data
    rule, and pre-gate snapshots (the shapes-stage corpus) have
    reachability-partial levels. The GameWorld's own "no item" encoding
    applies (the config it was parsed with):
      1. exactly one triforce of power, in a Ganon (monster $3E) room —
         under the vanilla encoding every $0E is one; under the ZORA remap
         only $0E + $3E is;
      2. no no-item room with trigger 7 — the engine would re-activate the
         hidden object and show item $03 (magical sword) or, under the
         remap, a second triforce of power."""
    tfop: list[tuple[str, Room]] = []
    bad7: list[str] = []
    for name, block in zip(BLOCK_NAMES, gw.blocks, strict=True):
        for room in block.rooms:
            if room.item == Item.TRIFORCE_OF_POWER:
                tfop.append((name, room))
            elif room.item == Item.NOTHING and room.item_appears_on_clear:
                bad7.append(f"{name}:{room.room_num:02X}")
    ok = (len(tfop) == 1 and tfop[0][1].enemy == Enemy.THE_BEAST
          and not bad7)
    where = [f"{name}:{room.room_num:02X}/enemy {room.enemy.value:02X}"
             for name, room in tfop[:4]]
    return CheckResult("TFOP-ROOM", ok,
                       f"tfop cells {where}; no-item+trigger7 {bad7[:8]}")


# --- which checks hold where ----------------------------------------------------
#
# Judged on the final corpus (1,000 ROMs) and ZORA (1,000 seeds, B1 on and
# off); temp/check_survey.py. The shapes-stage corpus cannot decide the level
# checks: its levels are not joined yet, so a parse finds only the rooms
# reachable from each entrance.

# Hold on every finished ROM. SH-STAIR-02, -03 and -09 count a level's own
# staircases (own_staircases): counting a cell two levels list against both
# failed them in 4 of 1,000 final corpus ROMs.
# check_triforce_of_power reads every room of both blocks, owned or not.
FINISHED_CHECKS = (
    check_grid_tiled, check_grid_connectivity, check_ganon_reachable,
    check_zelda_not_dark, check_entrances, check_level9_entrance,
    check_cellar_counts, check_stair_budget, check_transport_same_level,
    check_compass_map, check_minimap_synthesis, check_triforce_of_power,
    check_palette_selectors,
)

# SH-NUM-01 describes sorted numbering; sort_shapes=False maps the size
# order through a shuffled list (SH-NUM-02).
SORTED_SHAPES_CHECKS = (check_numbering_sorted,)

# Shape-stage rules that B1 moves: heart containers (PS-ITEM-02), the
# triforce room's layout and the grumble room (PS-GRUM). Finished ROMs keep
# them only without B1 (the final corpus fails them in 1,000, 1,000 and 817
# of 1,000 ROMs).
POST_SHAPES_MOVED_CHECKS = (check_triforce_rooms, check_grumble, check_heart_containers)

# SH-DOOR-03 describes the doors as the shape stage leaves them: the late
# gate re-deals door units, forces special-room sides and repairs with
# shutters, so finished output breaks it (reference: 16.8% mismatched pairs).
# The shapes-stage corpus passes it 1,000/1,000.
SHAPES_STAGE_CHECKS = (check_door_sync,)

# Stated rules the corpus contradicts, pending a spec answer (none open:
# SH-DOOR-01, QUESTIONS #56, was corrected by U23).
DISPUTED_CHECKS: tuple[Check, ...] = ()


def finished_rom_checks(sort_shapes: bool = True, post_shapes: bool = True) -> tuple[Check, ...]:
    """The checks a finished ROM generated with these options must pass."""
    checks: tuple[Check, ...] = FINISHED_CHECKS
    if sort_shapes:
        checks += SORTED_SHAPES_CHECKS
    if not post_shapes:
        checks += POST_SHAPES_MOVED_CHECKS
    return checks


def run_checks(gw: GameWorld, checks: tuple[Check, ...] | None = None) -> list[CheckResult]:
    """Run the checks (default: a finished ROM under the default options);
    a check that raises is reported as failed."""
    out = []
    for fn in finished_rom_checks() if checks is None else checks:
        try:
            out.append(fn(gw))
        except Exception as exc:  # a broken check must not crash the sweep
            out.append(CheckResult("EXC:" + fn.__name__, False, repr(exc)[:120]))
    return out
