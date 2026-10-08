"""Per-level dungeon statistics computed from a parsed GameWorld.

Used to characterize the corpus ("Consternation"/shapes output) and ZORA's own
generated dungeons (tasks 3, 5, 6 of the plan). Every statistic is derived from
data the spec says matters: sizes, footprints, staircases, dead ends, door
types, special rooms and items.

Deterministic: all iteration is over sorted room numbers / explicit lists.
"""
from dataclasses import dataclass, fields
from statistics import mean, median

from zora.model import room_grid
from zora.model.enums import BossSound, Destination, Enemy, Item, RoomAction, RoomType, Side, WallType
from zora.model.game_world import GameWorld
from zora.model.levels import LEVEL_BLOCK_ROOMS, Level, LevelBlock
from zora.model.overworld import ItemCave, OverworldItem
from zora.model.room_grid import neighbour
from zora.model.rooms import Room, StaircaseRoom

# Enemies with the is_boss flag that the spec treats as ordinary room monsters
# (SH-ENEMY-02) or as person-room NPCs (SH-ROOM-04/05) — excluded from boss
# counts computed from room data alone.
_NOT_A_BOSS: frozenset[Enemy] = frozenset({
    Enemy.RED_LANMOLA, Enemy.BLUE_LANMOLA, Enemy.MOLDORM,
    Enemy.RUPEE_BOSS, Enemy.HUNGRY_GORIYA, Enemy.THE_KIDNAPPED,
})

# Staircase budget per level number (SH-STAIR-02, item cellars included).
STAIR_BUDGET: dict[int, int] = {1: 1, 2: 0, 3: 1, 4: 1, 5: 2, 6: 2, 7: 2, 8: 3, 9: 8}

_PERSON_LAYOUT = RoomType.BLACK_ROOM          # $26
_TRIFORCE_LAYOUT = RoomType.TRIFORCE_ROOM     # $29
_ENTRANCE_LAYOUT = RoomType.ENTRANCE_ROOM     # $21

@dataclass(frozen=True)
class LevelStats:
    level_num: int
    rooms: int
    item_cellars: int
    transport_stairs: int
    stair_pieces: int                 # connected pieces before stairs (SH-GRID-07)
    pieces_final: int                 # after staircase joins (must be 1, SH-GRID-09)
    grid_width: int
    grid_height: int
    footprint: int                    # cells used = rooms + stair cells
    dead_end_rooms: int               # degree-1 rooms (excluding entrance)
    door_open: int
    door_closed_wall: int             # same-level neighbour pair, both sides solid
    door_walk: int
    door_bomb: int
    door_key: int
    door_shutter: int                 # shutter on both sides
    door_oneway_shutter: int          # shutter one side, open the other
    wall_crosslevel: int              # sides facing another level (counted per side)
    wall_edge: int                    # sides at grid edge (counted per side)
    person_rooms: int
    triforce_rooms: int
    entrance_rooms: int
    ganon_rooms: int
    zelda_rooms: int
    boss_rooms_any: int               # room holds a boss, any enemy count
    dark_rooms: int
    push_block_rooms: int
    boss_rooms: int
    heart_containers: int
    keys_dropped: int
    bombs_dropped: int
    rupees5_dropped: int
    nothing_rooms: int                # regular rooms whose item is NONE
    item_rooms: int                   # regular rooms with a non-NOTHING item
    nonpal2_rooms: int                # rooms not outer palette 2 (SH-DOOR-01)
    layout_turnstile_20: int          # layout $20 with or without push block (SH-BOSS-04)
    layouts_rare_0e_0f_12: int        # $0E/$0F/$12 (SH-ROOM-14)


@dataclass(frozen=True)
class RomStats:
    name: str
    levels: tuple[LevelStats, ...]


def _room_by_num(level: Level) -> dict[int, Room]:
    return {r.room_num: r for r in level.rooms}


def _components(nodes: list[int], adjacency: dict[int, list[int]]) -> int:
    seen: set[int] = set()
    count = 0
    for start in nodes:
        if start in seen:
            continue
        count += 1
        stack = [start]
        seen.add(start)
        while stack:
            node = stack.pop()
            for nxt in adjacency.get(node, []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
    return count


def _pair_class(wa: WallType, wb: WallType) -> str:
    """Classify a doorway given the two facing side types."""
    solid_a, solid_b = wa == WallType.SOLID_WALL, wb == WallType.SOLID_WALL
    if solid_a and solid_b:
        return "closed_wall"
    if solid_a or solid_b:
        # one side solid, other open-ish: malformed doorway; count by the open side
        wa_or_wb = wb if solid_a else wa
        return _pair_class(wa_or_wb, wa_or_wb)
    if wa == WallType.SHUTTER_DOOR and wb == WallType.SHUTTER_DOOR:
        return "shutter"
    if (wa == WallType.SHUTTER_DOOR) != (wb == WallType.SHUTTER_DOOR):
        other = wb if wa == WallType.SHUTTER_DOOR else wa
        if other == WallType.OPEN_DOOR:
            return "oneway_shutter"
        return "shutter"  # shutter paired with key/bomb/walk: treat as shutter
    if wa == WallType.BOMB_HOLE or wb == WallType.BOMB_HOLE:
        return "bomb"
    if wa in (WallType.LOCKED_DOOR_1, WallType.LOCKED_DOOR_2) or \
       wb in (WallType.LOCKED_DOOR_1, WallType.LOCKED_DOOR_2):
        return "key"
    if wa in (WallType.WALK_THROUGH_WALL_1, WallType.WALK_THROUGH_WALL_2) or \
       wb in (WallType.WALK_THROUGH_WALL_1, WallType.WALK_THROUGH_WALL_2):
        return "walk"
    return "open"


def _door_open(w: WallType) -> bool:
    return w != WallType.SOLID_WALL


# Layouts the statistics count by their low six bits.
LAYOUT_ID_MASK = 0x3F
RARE_LAYOUTS = (0x0E, 0x0F, 0x12)        # SH-ROOM-14
DOOR_CLASSES = ("open", "closed_wall", "walk", "bomb", "key", "shutter", "oneway_shutter")
STANDARD_OUTER_PALETTE = 2               # SH-DOOR-01


@dataclass
class DoorCensus:
    """A level's doorways between its own rooms, and the sides that face no room of it."""
    doors: dict[str, int]                # pair class -> count
    wall_crosslevel: int                 # sides facing another level's cell
    wall_edge: int                       # sides at the grid edge
    adjacency: dict[int, list[int]]      # room -> rooms reached through a doorway
    open_degree: dict[int, int]          # room -> doorways


@dataclass
class RoomCensus:
    """Counts of a level's rooms by their layout, monsters and item."""
    person: int = 0
    triforce: int = 0
    entrance: int = 0
    ganon: int = 0
    zelda: int = 0
    dark: int = 0
    push_block: int = 0
    bosses: int = 0
    bosses_any: int = 0
    hearts: int = 0
    keys: int = 0
    bombs: int = 0
    rupees: int = 0
    nothing: int = 0
    has_item: int = 0
    nonpal: int = 0
    turnstile: int = 0
    rare: int = 0


def door_census(rooms: dict[int, Room], cells: list[int], stair_slots: set[int]) -> DoorCensus:
    """Classify every side of every room. The cell's owner level is unavailable
    at this scope: a side facing an on-grid cell not owned by this level is a
    cross-level wall, a side facing off-grid is an edge wall."""
    cellset = set(cells)
    census = DoorCensus(doors=dict.fromkeys(DOOR_CLASSES, 0), wall_crosslevel=0, wall_edge=0,
                        adjacency={rn: [] for rn in cells}, open_degree=dict.fromkeys(rooms, 0))
    for rn in cells:
        if rn in stair_slots:
            continue
        room = rooms[rn]
        for side in Side:
            nb = neighbour(rn, side)
            if nb is None:
                census.wall_edge += 1
                continue
            if nb not in cellset:
                census.wall_crosslevel += 1
                continue
            if nb in stair_slots:
                # Stair cell touching a room: not a doorway (stairs repurpose
                # the byte), just ignore for door counts.
                continue
            if rn < nb:
                cls = _pair_class(room.walls[side], rooms[nb].walls[side.opposite])
                census.doors[cls] += 1
                if cls != "closed_wall":
                    census.adjacency.setdefault(rn, []).append(nb)
                    census.adjacency.setdefault(nb, []).append(rn)
                    census.open_degree[rn] += 1
                    census.open_degree[nb] += 1
    return census


def staircase_adjacency(level: Level, cells: list[int], adjacency: dict[int, list[int]]) -> dict[int, list[int]]:
    """The doorway adjacency with the staircases' joins added."""
    cellset = set(cells)
    join_adj: dict[int, list[int]] = {rn: list(adjacency.get(rn, [])) for rn in cells}
    for sr in level.staircase_rooms:
        if sr.room_type == RoomType.TRANSPORT_STAIRCASE:
            ends = [x for x in (sr.left_exit, sr.right_exit) if x is not None]
        else:
            ends = [sr.return_dest] if sr.return_dest is not None else []
        for e in ends:
            if e in cellset:
                join_adj.setdefault(sr.room_num, []).append(e)
                join_adj.setdefault(e, []).append(sr.room_num)
    return join_adj


def room_census(level: Level) -> RoomCensus:
    census = RoomCensus()
    for room in level.rooms:
        rt = room.room_type
        census.person += rt == _PERSON_LAYOUT
        census.triforce += rt == _TRIFORCE_LAYOUT
        census.entrance += rt == _ENTRANCE_LAYOUT
        census.ganon += rt == RoomType.GANON_ROOM
        census.zelda += rt == RoomType.ZELDA_ROOM
        census.dark += bool(room.is_dark)
        census.push_block += bool(room.movable_block)
        if room.enemy.is_boss and room.enemy not in _NOT_A_BOSS:
            census.bosses_any += 1
            census.bosses += level.enemy_quantity(room) == 0
        census.hearts += room.item == Item.HEART_CONTAINER
        if room.item == Item.KEY:
            census.keys += 1
        elif room.item == Item.BOMBS:
            census.bombs += 1
        elif room.item == Item.FIVE_RUPEES:
            census.rupees += 1
        elif room.item == Item.NOTHING:
            census.nothing += 1
        census.has_item += room.item != Item.NOTHING
        census.nonpal += room.palette_0 != STANDARD_OUTER_PALETTE
        census.turnstile += (rt & LAYOUT_ID_MASK) == RoomType.TURNSTILE_ROOM
        census.rare += (rt & LAYOUT_ID_MASK) in RARE_LAYOUTS
    return census


def level_stats(level: Level) -> LevelStats:
    rooms = _room_by_num(level)
    stair_slots = {s.room_num for s in level.staircase_rooms}
    cells = sorted(set(rooms) | stair_slots)
    doors = door_census(rooms, cells, stair_slots)
    join_adj = staircase_adjacency(level, cells, doors.adjacency)
    # door pieces are counted over room cells only: staircase cells are freed
    # rooms (SH-GRID-08), not part of the growing blobs (SH-GRID-07).
    stair_pieces = _components(sorted(rooms), doors.adjacency)
    pieces_final = _components(cells, join_adj)
    dead_ends = sum(1 for rn, deg in doors.open_degree.items() if deg == 1 and rn != level.entrance_room)
    rows = [room_grid.row(rn) for rn in cells]
    cols = [room_grid.column(rn) for rn in cells]
    counts = room_census(level)
    return LevelStats(
        level_num=level.level_num,
        rooms=len(rooms),
        item_cellars=sum(1 for s in level.staircase_rooms if s.room_type == RoomType.ITEM_STAIRCASE),
        transport_stairs=sum(1 for s in level.staircase_rooms if s.room_type == RoomType.TRANSPORT_STAIRCASE),
        stair_pieces=stair_pieces,
        pieces_final=pieces_final,
        grid_width=max(cols) - min(cols) + 1 if cells else 0,
        grid_height=max(rows) - min(rows) + 1 if cells else 0,
        footprint=len(cells),
        dead_end_rooms=dead_ends,
        door_open=doors.doors["open"],
        door_closed_wall=doors.doors["closed_wall"],
        door_walk=doors.doors["walk"],
        door_bomb=doors.doors["bomb"],
        door_key=doors.doors["key"],
        door_shutter=doors.doors["shutter"],
        door_oneway_shutter=doors.doors["oneway_shutter"],
        wall_crosslevel=doors.wall_crosslevel,
        wall_edge=doors.wall_edge,
        person_rooms=counts.person,
        triforce_rooms=counts.triforce,
        entrance_rooms=counts.entrance,
        ganon_rooms=counts.ganon,
        zelda_rooms=counts.zelda,
        dark_rooms=counts.dark,
        push_block_rooms=counts.push_block,
        boss_rooms=counts.bosses,
        boss_rooms_any=counts.bosses_any,
        heart_containers=counts.hearts,
        keys_dropped=counts.keys,
        bombs_dropped=counts.bombs,
        rupees5_dropped=counts.rupees,
        nothing_rooms=counts.nothing,
        item_rooms=counts.has_item,
        nonpal2_rooms=counts.nonpal,
        layout_turnstile_20=counts.turnstile,
        layouts_rare_0e_0f_12=counts.rare,
    )


def rom_stats(name: str, levels: list[Level]) -> RomStats:
    return RomStats(name=name, levels=tuple(level_stats(level) for level in sorted(
        levels, key=lambda level: level.level_num
    )))


STAT_NAMES: list[str] = [f.name for f in fields(LevelStats) if f.name != "level_num"]


def _fmt(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}"


def summarize(stats: list[RomStats]) -> str:
    """Markdown summary: mean / median / min / max per statistic.

    Each ROM contributes 9 level rows; the aggregate is per level across the
    pool (vanilla alone, or corpus ROMs alone).
    """
    rows: list[list[float]] = []
    for rs in stats:
        for ls in rs.levels:
            vals: list[float] = []
            for name in STAT_NAMES:
                v = getattr(ls, name)
                vals.append(float(v))
            rows.append(vals)
    if not rows:
        return "(no data)"
    lines = ["| statistic | mean | median | min | max |", "|---|---|---|---|---|"]
    for i, name in enumerate(STAT_NAMES):
        col = [r[i] for r in rows]
        lines.append(
            f"| {name} | {_fmt(mean(col))} | {_fmt(median(col))} | "
            f"{_fmt(min(col))} | {_fmt(max(col))} |"
        )
    return "\n".join(lines) + "\n"


def csv_header() -> str:
    return "rom,level," + ",".join(STAT_NAMES)


def csv_rows(rs: RomStats) -> list[str]:
    out = []
    for ls in rs.levels:
        vals = ",".join(str(getattr(ls, name)) for name in STAT_NAMES)
        out.append(f"{rs.name},{ls.level_num},{vals}")
    return out


# ---------------------------------------------------------------------------
# Grid-level statistics (membership-free)
#
# Censuses over every room of a level block, independent of which level owns
# a room: the comparison basis for corpus vs generated output (task 6).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GridStats:
    grid: str                       # "1-6" or "7-9"
    sides_open: int
    sides_wall: int
    sides_walk: int
    sides_bomb: int
    sides_key: int
    sides_shutter: int
    pairs_synced: int
    pairs_oneway_connector: int     # one side solid, other non-solid
    pairs_shutter_oneway: int       # open|shutter (SH-DOOR-03)
    pairs_other_mismatch: int
    cells_total: int                # always 128
    layout_entrance_21: int
    layout_triforce_29: int
    layout_person_26: int
    layout_zelda_27: int
    layout_ganon_28: int
    layout_cellar_3f: int
    layout_transport_3e: int
    item_none: int
    item_key: int
    item_bombs: int
    item_rupees5: int
    item_triforce: int
    item_heart: int
    item_other: int
    trigger_none: int                 # action $0: nothing opens shutters
    trigger_kill_all: int             # action $1 (the spec's "kill all enemies")
    trigger_kill_for_item: int        # action $7
    trigger_push_door: int            # action $4
    trigger_push_stairs: int          # action $5
    trigger_other: int                # actions $2/$3/$6


_SIDE_KIND: dict[WallType, str] = {
    WallType.OPEN_DOOR: "open", WallType.SOLID_WALL: "wall",
    WallType.WALK_THROUGH_WALL_1: "walk", WallType.WALK_THROUGH_WALL_2: "walk",
    WallType.BOMB_HOLE: "bomb",
    WallType.LOCKED_DOOR_1: "key", WallType.LOCKED_DOOR_2: "key",
    WallType.SHUTTER_DOOR: "shutter",
}
_LAYOUT_KEY: dict[RoomType, str] = {
    RoomType.ENTRANCE_ROOM: "e21", RoomType.TRIFORCE_ROOM: "t29",
    RoomType.BLACK_ROOM: "p26", RoomType.ZELDA_ROOM: "z27",
    RoomType.GANON_ROOM: "g28", RoomType.ITEM_STAIRCASE: "c3f",
    RoomType.TRANSPORT_STAIRCASE: "s3e",
}
_ITEM_KEY: dict[Item, str] = {
    Item.NOTHING: "none", Item.KEY: "key", Item.BOMBS: "bomb",
    Item.FIVE_RUPEES: "r5", Item.TRIFORCE: "tri", Item.HEART_CONTAINER: "heart",
}
_TRIGGER_KEY: dict[RoomAction, str] = {
    RoomAction.NONE: "none",
    RoomAction.ALL_DEAD: "kill",
    RoomAction.ALL_DEAD_ITEM: "kill_item",
    RoomAction.BLOCK_DOOR: "push_door",
    RoomAction.BLOCK_STAIRS: "push_stairs",
}


def _cell_item(cell: Room | StaircaseRoom) -> Item:
    """The item a cell holds: a room's or a cellar's; a transport holds none."""
    if isinstance(cell, Room):
        return cell.item
    return cell.item if cell.item is not None else Item.NOTHING


def _cell_trigger(cell: Room | StaircaseRoom) -> RoomAction:
    """A room's trigger; staircases have none."""
    return cell.room_action if isinstance(cell, Room) else RoomAction.NONE


def grid_stats(grid_name: str, block: LevelBlock) -> GridStats:
    """Census of one 128-room block: door sides and facing pairs over its
    ordinary rooms (a staircase has no doors), and layouts, items and
    triggers over every cell."""
    sides = {"open": 0, "wall": 0, "walk": 0, "bomb": 0, "key": 0, "shutter": 0}
    pairs = {"synced": 0, "oneway": 0, "shutter_1way": 0, "mismatch": 0}
    for room in block.rooms:
        for side in Side:
            sides[_SIDE_KIND[room.walls[side]]] += 1
        # each facing pair once: from its west and its north room
        for side in (Side.EAST, Side.SOUTH):
            other = neighbour(room.room_num, side)
            if other is not None and isinstance(block[other], Room):
                _tally_pair(pairs, room.walls[side], block.room(other).walls[side.opposite])

    layouts = dict.fromkeys(_LAYOUT_KEY.values(), 0)
    items = dict.fromkeys([*_ITEM_KEY.values(), "other"], 0)
    trig = dict.fromkeys([*_TRIGGER_KEY.values(), "other"], 0)
    for cell in block.cells:
        if cell.room_type in _LAYOUT_KEY:
            layouts[_LAYOUT_KEY[cell.room_type]] += 1
        items[_ITEM_KEY.get(_cell_item(cell), "other")] += 1
        trig[_TRIGGER_KEY.get(_cell_trigger(cell), "other")] += 1

    return GridStats(
        grid=grid_name,
        sides_open=sides["open"], sides_wall=sides["wall"], sides_walk=sides["walk"],
        sides_bomb=sides["bomb"], sides_key=sides["key"], sides_shutter=sides["shutter"],
        pairs_synced=pairs["synced"], pairs_oneway_connector=pairs["oneway"],
        pairs_shutter_oneway=pairs["shutter_1way"], pairs_other_mismatch=pairs["mismatch"],
        cells_total=LEVEL_BLOCK_ROOMS,
        layout_entrance_21=layouts["e21"], layout_triforce_29=layouts["t29"],
        layout_person_26=layouts["p26"], layout_zelda_27=layouts["z27"],
        layout_ganon_28=layouts["g28"], layout_cellar_3f=layouts["c3f"],
        layout_transport_3e=layouts["s3e"],
        item_none=items["none"], item_key=items["key"], item_bombs=items["bomb"],
        item_rupees5=items["r5"], item_triforce=items["tri"], item_heart=items["heart"],
        item_other=items["other"],
        trigger_none=trig["none"], trigger_kill_all=trig["kill"],
        trigger_kill_for_item=trig["kill_item"],
        trigger_push_door=trig["push_door"], trigger_push_stairs=trig["push_stairs"],
        trigger_other=trig["other"],
    )


def block_stats(gw: GameWorld) -> list[GridStats]:
    """grid_stats for both quest-1 blocks ("1-6", "7-9")."""
    return [grid_stats(name, block) for name, block in zip(("1-6", "7-9"), gw.blocks, strict=True)]


def _tally_pair(pairs: dict[str, int], a: WallType, b: WallType) -> None:
    solid_a, solid_b = a == WallType.SOLID_WALL, b == WallType.SOLID_WALL
    if a == b:
        pairs["synced"] += 1
    elif {a, b} == {WallType.OPEN_DOOR, WallType.SHUTTER_DOOR}:
        pairs["shutter_1way"] += 1
    elif solid_a != solid_b:
        pairs["oneway"] += 1
    else:
        pairs["mismatch"] += 1


GRID_STAT_NAMES: list[str] = [f.name for f in fields(GridStats) if f.name != "grid"]


def grid_csv_header() -> str:
    return "rom,grid," + ",".join(GRID_STAT_NAMES)


def grid_csv_rows(name: str, gs: list[GridStats]) -> list[str]:
    return [f"{name},{g.grid}," + ",".join(str(getattr(g, n)) for n in GRID_STAT_NAMES)
            for g in gs]


def summarize_grids(rows: list[GridStats]) -> str:
    if not rows:
        return "(no data)\n"
    out = ["| statistic | mean | median | min | max |", "|---|---|---|---|---|"]
    for name in GRID_STAT_NAMES:
        col = [float(getattr(g, name)) for g in rows]
        out.append(f"| {name} | {_fmt(mean(col))} | {_fmt(median(col))} | "
                   f"{_fmt(min(col))} | {_fmt(max(col))} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# B1 checkpoint (post-shapes-b1.md "Checkpoint (B1)")
# ---------------------------------------------------------------------------

@dataclass
class B1Checkpoint:
    goriya: int          # the hungry goriya: monster $36 without the person flag
    ganon_8e: int        # item byte exactly $8E: dark room + triforce of power
    merchants: int       # life-or-money person ($11 + flag, count 0) with trigger 6
    hearts_dungeon: int  # heart containers in both blocks' rooms and cellars
    hearts_caves: int    # heart containers in the three special-cave slots


def special_cave_items(gw: GameWorld) -> list[Item]:
    """The items of the three special-cave slots: the Armos item, the
    white-sword cave and the coast item (PS-ITEM-01's cave places)."""
    ow = gw.overworld
    caves = [ow.get_cave(Destination.ARMOS_ITEM, OverworldItem),
             ow.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave),
             ow.get_cave(Destination.COAST_ITEM, OverworldItem)]
    return [c.item for c in caves if c is not None]


def _is_ganon_item_byte(room: Room) -> bool:
    """The Ganon room's item byte $8E: dark, no boss sound, triforce of power."""
    return (room.is_dark and room.boss_sound == BossSound.NONE
            and room.item == Item.TRIFORCE_OF_POWER)


def b1_checkpoint(gw: GameWorld) -> B1Checkpoint:
    """post-shapes-b1.md "Checkpoint (B1)": the four censuses over the two
    quest-1 blocks (every room, owned or not) and the special-cave slots."""
    rooms = [room for block in gw.blocks for room in block.rooms]
    cellar_items = [c.item for block in gw.blocks for c in block.staircases]
    return B1Checkpoint(
        goriya=sum(r.enemy == Enemy.HUNGRY_GORIYA for r in rooms),
        ganon_8e=sum(_is_ganon_item_byte(r) for r in rooms),
        merchants=sum(r.enemy == Enemy.MUGGER and r.count_index == 0
                      and r.room_action == RoomAction.MONEY_OR_LIFE
                      for r in rooms),
        hearts_dungeon=(sum(r.item == Item.HEART_CONTAINER for r in rooms)
                        + sum(item == Item.HEART_CONTAINER for item in cellar_items)),
        hearts_caves=sum(item == Item.HEART_CONTAINER for item in special_cave_items(gw)),
    )
