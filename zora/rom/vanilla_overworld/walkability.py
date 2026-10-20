"""Where Link can walk on the overworld: each screen's walkable regions and how the screens'
edges join them (read-only; the owner's 2.0 maze gates are derived from it, zora/generate/
steps/overworld_gates.py).

A screen is its layout's squares (layouts.py) as 22 rows of 32 tiles. The engine's tile test
(aldonunez Z_07 @FetchTile and its callers): a tile is walkable below
ObjectFirstUnwalkableTile, $89 on the overworld, or when it is one of WalkableTiles; water
($8F-$98) is not. Link stands on two tiles side by side (his feet): a step up or down needs
both, a step sideways only the tile he moves onto. The engine's one special case is screen
$1F's false wall (at X = $80 going up), which opens its top.

With the ladder, Link also steps over exactly one square of water (two tiles) in a straight
line onto land. Raft docks, the recorder, bombable walls and the boulders are not modeled:
they gate entrances, which the acceptance check's screen sets already handle.

Two screens join where one's edge and the other's opposite edge are walkable at the same
position. A region is a set of positions joined inside one screen. Link arriving on an edge
position he could not stand on still walks on: the engine tests the square ahead of a moving Link,
never the one he stands in (aldonunez GetCollidableTile), so he reaches the first position inward
whose way there is open (features-behavior.md FP-WOODS-01: room $51's west edge into room $50,
whose own east edge is rock). Such a join is one-way: that edge never leads back out.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field

from .layouts import read_layout, square_tiles
from .tables import ATTRIBUTE_TABLE_SIZE, LEVEL_BLOCK_OW, SCREEN_COUNT

FIRST_UNWALKABLE_TILE = 0x89          # ObjectFirstUnwalkableTile on the overworld
WALKABLE_TILES = frozenset({0x8D, 0x91, 0x9C, 0xAC, 0xAD, 0xCC, 0xD2, 0xD5, 0xDF})   # WalkableTiles
WATER_TILES = frozenset(range(0x8F, 0x99))
OPEN_TILE = 0x26                      # the engine's stand-in for a walkable tile
ROWS, COLUMNS = 22, 32
POSITIONS = COLUMNS - 1               # Link's left foot column
GRID_COLUMNS = 16                     # screens per overworld row
SCREEN_ROWS = SCREEN_COUNT // GRID_COLUMNS
LAYOUT_TABLE = 3                      # LevelBlockAttrsD: bits 6-0 are the screen's layout
LAYOUT_MASK = 0x7F
# Screen $1F's false wall: Link at X = $80 going up passes (aldonunez @FetchTile).
FALSE_WALL_SCREEN = 0x1F
FALSE_WALL_COLUMNS = (16, 17)         # X = $80
FALSE_WALL_ROWS = range(6)            # Y < $56, the top of the play area

SIDES = {"N": (-1, 0, "S"), "S": (1, 0, "N"), "W": (0, -1, "E"), "E": (0, 1, "W")}

Tiles = list[list[int]]               # [row][column]
Node = tuple[int, int]                # (screen, region)


def is_walkable(tile: int) -> bool:
    return tile < FIRST_UNWALKABLE_TILE or tile in WALKABLE_TILES


def screen_tiles(rom: bytes, screen: int) -> Tiles:
    """A screen's play area as tiles, from its layout's squares."""
    layout = read_layout(rom, LEVEL_BLOCK_OW.read(rom)[LAYOUT_TABLE * ATTRIBUTE_TABLE_SIZE + screen] & LAYOUT_MASK)
    tiles = [[0] * COLUMNS for _ in range(ROWS)]
    for column, squares in enumerate(layout):
        for row, square in enumerate(squares):
            top_left, bottom_left, top_right, bottom_right = square_tiles(rom, square)
            tiles[2 * row][2 * column], tiles[2 * row + 1][2 * column] = top_left, bottom_left
            tiles[2 * row][2 * column + 1], tiles[2 * row + 1][2 * column + 1] = top_right, bottom_right
    if screen == FALSE_WALL_SCREEN:
        for row in FALSE_WALL_ROWS:
            for column in FALSE_WALL_COLUMNS:
                tiles[row][column] = OPEN_TILE
    return tiles


@dataclass
class ScreenRegions:
    """One screen: its regions, per side the region at each edge position (None: wall), and the
    region of every position Link can stand on."""
    count: int
    edges: dict[str, dict[int, int | None]]
    positions: dict[tuple[int, int], int] = field(default_factory=dict)
    # Per side, the region Link reaches arriving at an edge position he cannot stand on (one-way)
    entries: dict[str, dict[int, int]] = field(default_factory=dict)

    def arrival(self, side: str, position: int) -> int | None:
        """The region Link reaches arriving at a side's edge position."""
        region = self.edges[side][position]
        return region if region is not None else self.entries.get(side, {}).get(position)

    def regions_in_columns(self, columns: range) -> set[int]:
        """The regions with a position whose left foot is in one of the columns (a cave entrance's
        square: the screen's split regions tell which side of a wall its cave is on)."""
        return {region for (_, column), region in self.positions.items() if column in columns}


def _stands(tiles: Tiles, row: int, column: int) -> bool:
    return (0 <= row < ROWS and 0 <= column < POSITIONS
            and is_walkable(tiles[row][column]) and is_walkable(tiles[row][column + 1]))


def _steps(tiles: Tiles, row: int, column: int, ladder: bool) -> Iterator[tuple[int, int]]:
    """The positions one step from (row, column)."""
    for step in (1, -1):
        if _stands(tiles, row + step, column):
            yield row + step, column
        if ladder and _stands(tiles, row + 3 * step, column) and all(
                tiles[row + k * step][column + side] in WATER_TILES for k in (1, 2) for side in (0, 1)):
            yield row + 3 * step, column
        ahead = column + 2 if step > 0 else column - 1
        if 0 <= column + step < POSITIONS and 0 <= ahead < COLUMNS and is_walkable(tiles[row][ahead]):
            yield row, column + step
        water = (column + 2, column + 3) if step > 0 else (column - 1, column - 2)
        if ladder and _stands(tiles, row, column + 4 * step) and all(
                0 <= tile < COLUMNS and tiles[row][tile] in WATER_TILES for tile in water):
            yield row, column + 4 * step


def screen_regions(tiles: Tiles, ladder: bool) -> ScreenRegions:
    """Flood each region from every position Link can stand on."""
    region: dict[tuple[int, int], int] = {}
    count = 0
    for row in range(ROWS):
        for column in range(POSITIONS):
            if (row, column) in region or not _stands(tiles, row, column):
                continue
            region[(row, column)] = count
            queue = deque([(row, column)])
            while queue:
                for position in _steps(tiles, *queue.popleft(), ladder):
                    if position not in region:
                        region[position] = count
                        queue.append(position)
            count += 1
    edges = {"N": {c: region.get((0, c)) for c in range(POSITIONS)},
             "S": {c: region.get((ROWS - 1, c)) for c in range(POSITIONS)},
             "W": {r: region.get((r, 0)) for r in range(ROWS)},
             "E": {r: region.get((r, POSITIONS - 1)) for r in range(ROWS)}}
    entries: dict[str, dict[int, int]] = {side: {} for side in SIDES}
    for side, at_edge in edges.items():
        for edge_position, edge_region in at_edge.items():
            if edge_region is None:
                inward = _walk_in(tiles, side, edge_position, region)
                if inward is not None:
                    entries[side][edge_position] = inward
    return ScreenRegions(count, edges, region, entries)


def _walk_in(tiles: Tiles, side: str, position: int, region: dict[tuple[int, int], int]) -> int | None:
    """The region Link reaches from an edge position he arrives on but cannot stand on, moving on
    away from that edge: each step tests only what lies ahead (_steps), up to the first position he
    can stand on."""
    if side in "NS":
        row = 1 if side == "N" else ROWS - 2
        return region.get((row, position)) if _stands(tiles, row, position) else None
    column, step = (POSITIONS - 1, -1) if side == "E" else (0, 1)
    while 0 <= column + step < POSITIONS:
        ahead = column - 1 if step < 0 else column + 2
        if not is_walkable(tiles[position][ahead]):
            return None
        column += step
        if (position, column) in region:
            return region[(position, column)]
    return None


def neighbor(screen: int, side: str) -> int | None:
    row, column = divmod(screen, GRID_COLUMNS)
    step_row, step_column, _ = SIDES[side]
    if 0 <= row + step_row < SCREEN_ROWS and 0 <= column + step_column < GRID_COLUMNS:
        return (row + step_row) * GRID_COLUMNS + column + step_column
    return None


@dataclass
class ScreenGraph:
    """Every screen's regions, and where leaving a region by a side arrives."""
    screens: dict[int, ScreenRegions]
    exits: dict[tuple[int, int, str], set[Node]] = field(default_factory=dict)

    def reach(self, start: int, closed: frozenset[tuple[int, str]] = frozenset()) -> set[int]:
        """The screens reached from any region of `start`, never leaving a screen by a closed
        (screen, side): a maze screen's sides that repeat it."""
        return {screen for screen, _ in self.reach_regions(start, closed)}

    def reach_regions(self, start: int, closed: frozenset[tuple[int, str]] = frozenset()) -> set[Node]:
        """The regions reached from any region of `start`, as reach."""
        seen = {(start, region) for region in range(self.screens[start].count)}
        queue = deque(seen)
        while queue:
            screen, region = queue.popleft()
            for side in SIDES:
                if (screen, side) in closed:
                    continue
                for arrival in self.exits.get((screen, region, side), ()):
                    if arrival not in seen:
                        seen.add(arrival)
                        queue.append(arrival)
        return seen


def screen_graph(rom: bytes, ladder: bool = False) -> ScreenGraph:
    """The overworld's screen graph for a headered ROM image (PRG0, or with layout edits)."""
    graph = ScreenGraph({screen: screen_regions(screen_tiles(rom, screen), ladder) for screen in range(SCREEN_COUNT)})
    for screen, regions in graph.screens.items():
        for side, (_, _, opposite) in SIDES.items():
            other = neighbor(screen, side)
            if other is None:
                continue
            across = graph.screens[other]
            for position, region in regions.edges[side].items():
                arrival = across.arrival(opposite, position)
                if region is not None and arrival is not None:
                    graph.exits.setdefault((screen, region, side), set()).add((other, arrival))
    return graph
