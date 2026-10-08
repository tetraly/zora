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
line onto land. Raft docks, the recorder, bombable walls and the boulders are not modelled:
they gate entrances, which the acceptance check's screen sets already handle.

Two screens join where one's edge and the other's opposite edge are walkable at the same
position. A region is a set of positions joined inside one screen.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field

from zora.rom.vanilla_overworld.layouts import read_layout, square_tiles
from zora.rom.vanilla_overworld.tables import ATTRIBUTE_TABLE_SIZE, LEVEL_BLOCK_OW, SCREEN_COUNT

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
    """One screen: its regions and, per side, the region at each edge position (None: wall)."""
    count: int
    edges: dict[str, dict[int, int | None]]


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
    return ScreenRegions(count, edges)


def neighbour(screen: int, side: str) -> int | None:
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
        return {screen for screen, _ in seen}


def screen_graph(rom: bytes, ladder: bool = False) -> ScreenGraph:
    """The overworld's screen graph for a headered ROM image (PRG0, or with layout edits)."""
    graph = ScreenGraph({screen: screen_regions(screen_tiles(rom, screen), ladder) for screen in range(SCREEN_COUNT)})
    for screen, regions in graph.screens.items():
        for side, (_, _, opposite) in SIDES.items():
            other = neighbour(screen, side)
            if other is None:
                continue
            across = graph.screens[other].edges[opposite]
            for position, region in regions.edges[side].items():
                arrival = across.get(position)
                if region is not None and arrival is not None:
                    graph.exits.setdefault((screen, region, side), set()).add((other, arrival))
    return graph
