"""Generate the physical layout of dungeon rooms on the 8x16 level grid.

Determines which grid cells belong to which dungeon level by growing
level territories outward from random starting positions using a
weighted frontier expansion algorithm. Earlier levels are biased toward
the left side of the grid, later levels toward the right.

After expansion, excess rooms are trimmed to ensure each level has
enough empty adjacent cells for staircase placement.

The output is purely the grid assignment (which cells belong to which
level). No room contents, enemies, walls, or items are set here.

Ported from RegenerateLevelMap.cs (regenerateLevelMap, Module.cs:18911).
Sub-functions addRoom (Module.cs:18195), addStairSpots (Module.cs:18681),
noBreak (Module.cs:18500).

Uses MT19937-64 RNG internally to match the original's integer
arithmetic patterns. Seeded from the caller's Rng for determinism.
"""

from collections import deque

from zora.level_gen.mt64 import MersenneTwister64
from zora.rng import Rng

GRID_ROWS = 8
GRID_COLS = 16

_MAX_PLACEMENT_ATTEMPTS = 10_000
_MAX_ADD_ROOM_RETRIES = 5_000
_MAX_FRONTIER_DRAIN = 10_000
_MAX_STAIR_SPOT_ITERATIONS = 50

_DIR_ROW = (1, 0, -1, 0)
_DIR_COL = (0, 1, 0, -1)


def regenerate_level_map(
    rng: Rng,
    levels_to_place: int,
    start_anywhere: bool,
) -> list[list[int]]:
    """Generate a fresh level grid.

    Args:
        rng: Random number generator (used only to seed the internal MT64).
        levels_to_place: Number of dungeon levels to lay out (3 or 6).
        start_anywhere: If True, starting row is random; otherwise row 7.

    Returns:
        An 8x16 grid where each cell contains a level number (1-N) or 0
        for empty.
    """
    seed = int(rng.random() * (1 << 63))
    mt = MersenneTwister64(seed)

    # Advance twice (Module.cs:18992-18993)
    mt.next()
    mt.next()

    grid = _empty_grid()
    frontier: list[tuple[int, int, int]] = []  # (row, col, level)
    min_col = [-1] * 7
    max_col = [-1] * 7
    rooms_remaining = [64] * 10

    # --- Step 7: Place starting positions (Module.cs:19009-19214) ---
    for level in range(1, levels_to_place + 1):
        start_row = 7
        if start_anywhere:
            start_row = int(mt.next() & 7)

        start_col = _pick_start_col(mt, level, levels_to_place)
        if levels_to_place == 3 and level == 1:
            start_row = 7

        start_col = _clamp(start_col, 0, 15)

        # Retry if cell occupied (Module.cs:19074-19107)
        attempts = 0
        while grid[start_row][start_col] != 0:
            if attempts >= _MAX_PLACEMENT_ATTEMPTS:
                break
            attempts += 1
            if levels_to_place == 6:
                rv = mt.next()
                bias = float(level - 1) * 2.5
                raw = int(float(rv - rv // 5 * 5) + bias)
                c = min(15.0, float(raw)) if 15.0 >= float(raw) else 15.0
                start_col = max(int(c), 0)
            elif level == 1:
                start_col = 6
            elif level == 2:
                start_col = int(mt.next() & 7) + 4
            else:
                start_col = int(mt.next() & 7) + 8

        grid[start_row][start_col] = level

        # Level 1 + 3-level mode: also place in row above (Module.cs:19110-19112)
        if level == 1 and levels_to_place == 3:
            grid[start_row - 1][start_col] = 1

        _set_column_bounds(mt, level, levels_to_place, start_col,
                           min_col, max_col)

    # --- Step 8: Build frontier from occupied cells (Module.cs:19216-19267) ---
    _build_initial_frontier(grid, frontier, min_col, max_col)

    # --- Step 9: addRoom per level (Module.cs:19268-19277) ---
    for level in range(1, levels_to_place + 1):
        _add_room(mt, grid, frontier, min_col, max_col, rooms_remaining, level)

    # --- Step 10: Add 3 random rooms (Module.cs:19278-19314) ---
    _add_random_rooms(mt, grid, frontier, min_col, max_col, levels_to_place)

    # --- Step 11: Iterated addRoom (Module.cs:19315-19334) ---
    iter_count = 12 if levels_to_place == 6 else 17
    for _ in range(iter_count):
        for level in range(1, levels_to_place + 1):
            _add_room(mt, grid, frontier, min_col, max_col,
                      rooms_remaining, level)

    # --- Step 12: Drain frontier (Module.cs:19335-19345) ---
    drain_count = 0
    while frontier and drain_count < _MAX_FRONTIER_DRAIN:
        _add_room(mt, grid, frontier, min_col, max_col, rooms_remaining, -1)
        drain_count += 1

    # --- Step 13: addStairSpots (Module.cs:19346-19348) ---
    stair_count = 0
    while _add_stair_spots(mt, grid, levels_to_place):
        stair_count += 1
        if stair_count >= _MAX_STAIR_SPOT_ITERATIONS:
            break

    return grid


# ---------------------------------------------------------------------------
# Starting column selection (Module.cs:19020-19069)
# ---------------------------------------------------------------------------

def _pick_start_col(mt: MersenneTwister64, level: int,
                    levels_to_place: int) -> int:
    if levels_to_place == 6:
        return _biased_column_branching(mt, level)

    if level == 1:
        return 6
    if level == 2:
        rv = mt.next()
        return int(rv - rv // 12 * 12)

    return int(mt.next() & 7) + 8


def _biased_column_branching(mt: MersenneTwister64, level: int) -> int:
    """Match the exact C# branching MT consumption pattern.

    The MSVC-inlined std::clamp causes 2-4 MT calls depending on values.
    (Module.cs:19022-19055, RegenerateLevelMap.cs:248-282)
    """
    bias = float(level - 1) * 2.5

    num7 = mt.next()  # MT call 1
    raw1 = int(float(num7 - num7 // 5 * 5) + bias)

    if 15 >= raw1:
        num10 = mt.next()  # MT call 2
        raw2 = int(float(num10 - num10 // 5 * 5) + bias)
        if 0 > raw2:
            return 0

    # Fall through
    num7 = mt.next()  # MT call 3 (or 2 if first branch skipped)
    raw3 = int(float(num7 - num7 // 5 * 5) + bias)

    if 15 < raw3:
        result = 15
    else:
        num15 = mt.next()  # MT call 4 (or 3)
        result = int(float(num15 - num15 // 5 * 5) + bias)

    return result


# ---------------------------------------------------------------------------
# Column bounds (Module.cs:19114-19187)
# ---------------------------------------------------------------------------

def _set_column_bounds(
    mt: MersenneTwister64,
    level: int,
    levels_to_place: int,
    start_col: int,
    min_col: list[int],
    max_col: list[int],
) -> None:
    base_min = start_col - 3
    if 11 >= base_min and 0 > base_min:
        base_min = 0
    else:
        base_min = min(11, base_min)

    min_col[level] = base_min

    base_max = min(15, base_min + 7)
    col_plus_4 = min(15, start_col + 4)
    if base_max > col_plus_4:
        max_col[level] = base_max
    else:
        max_col[level] = col_plus_4

    if levels_to_place == 6:
        if level == 1:
            min_col[1] = 0
            max_col[1] = min(7, max_col[1])
        elif level == 6:
            max_col[6] = 15
            min_col[6] = max(8, min_col[6])
    else:
        if level == 1:
            min_col[1] = 0
            max_col[1] = 7
        elif level == 2:
            if start_col < 7:
                min_col[2] = 0
                max_col[2] = min(6, max_col[2])
                min_col[1] = int(mt.next() & 3) + 3
                max_col[1] = min_col[1] + 7
        else:
            if min_col[1] != 0:
                min_col[level] = 10
                max_col[level] = 15
            else:
                min_col[level] = 8
                max_col[level] = 15


# ---------------------------------------------------------------------------
# Frontier building (Module.cs:19216-19267)
# ---------------------------------------------------------------------------

def _build_initial_frontier(
    grid: list[list[int]],
    frontier: list[tuple[int, int, int]],
    min_col: list[int],
    max_col: list[int],
) -> None:
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cell_level = grid[row][col]
            if cell_level != 0:
                _add_neighbors_to_frontier(
                    frontier, row, col, cell_level, min_col, max_col,
                )


def _add_neighbors_to_frontier(
    frontier: list[tuple[int, int, int]],
    row: int,
    col: int,
    level: int,
    min_col: list[int],
    max_col: list[int],
) -> None:
    for d in range(4):
        nr = row + _DIR_ROW[d]
        nc = col + _DIR_COL[d]
        if 0 <= nr <= 7 and min_col[level] <= nc <= max_col[level]:
            frontier.append((nr, nc, level))


# ---------------------------------------------------------------------------
# addRoom (Module.cs:18195-18498)
# ---------------------------------------------------------------------------

def _add_room(
    mt: MersenneTwister64,
    grid: list[list[int]],
    frontier: list[tuple[int, int, int]],
    min_col: list[int],
    max_col: list[int],
    rooms_remaining: list[int],
    level: int,
) -> None:
    if level != -1:
        has_empty = False
        for r, c, lv in frontier:
            if lv == level and grid[r][c] == 0:
                has_empty = True
                break
        if not has_empty:
            _place_random_room(mt, grid, frontier, min_col, max_col,
                               rooms_remaining, level)
            return

    _place_from_frontier(mt, grid, frontier, min_col, max_col,
                         rooms_remaining, level)


def _place_random_room(
    mt: MersenneTwister64,
    grid: list[list[int]],
    frontier: list[tuple[int, int, int]],
    min_col: list[int],
    max_col: list[int],
    rooms_remaining: list[int],
    level: int,
) -> None:
    """No-frontier path: pick random empty cell. (Module.cs:18227-18292)"""
    attempts = 0
    while True:
        row = int(mt.next() & 7)
        col_min = min_col[level]
        col_max = max_col[level]
        col_range = col_max - col_min + 1
        if col_range <= 0:
            return
        rv = mt.next()
        col = int(rv % col_range) + col_min

        attempts += 1
        if attempts > _MAX_ADD_ROOM_RETRIES:
            if col_max - col_min == 7:
                return
            if col_min == 0:
                max_col[level] += 1
            elif col_max == 15:
                min_col[level] -= 1
            elif int(mt.next() & 1) == 0:
                min_col[level] -= 1
            else:
                max_col[level] += 1
            attempts = 0

        if grid[row][col] == 0:
            grid[row][col] = level
            rooms_remaining[level] -= 1
            _add_neighbors_to_frontier(frontier, row, col, level,
                                       min_col, max_col)
            return


def _place_from_frontier(
    mt: MersenneTwister64,
    grid: list[list[int]],
    frontier: list[tuple[int, int, int]],
    min_col: list[int],
    max_col: list[int],
    rooms_remaining: list[int],
    level: int,
) -> None:
    """Weighted frontier selection. (Module.cs:18294-18498)"""
    while True:
        if not frontier:
            return

        weights = [0] * len(frontier)
        total_weight = 0

        for i, (fr, fc, fl) in enumerate(frontier):
            if level != -1 and fl != level:
                continue
            w = 1
            for d in range(4):
                nr = fr + _DIR_ROW[d]
                nc = fc + _DIR_COL[d]
                if 0 <= nr <= 7 and min_col[fl] <= nc <= max_col[fl]:
                    if grid[nr][nc] != fl and (level == -1 or fl == level):
                        w *= 10
            if fl == 1:
                w *= 2
            weights[i] = w
            total_weight += w

        if total_weight == 0:
            return

        pick = int(mt.next() % total_weight)
        chosen_idx = -1
        for i, w in enumerate(weights):
            pick -= w
            if pick < 0:
                chosen_idx = i
                break

        if chosen_idx == -1:
            return

        fr, fc, fl = frontier[chosen_idx]

        if level != -1 and fl != level:
            continue

        del frontier[chosen_idx]

        if weights[chosen_idx] == 1:
            rv = mt.next()
            if rv - rv // 5 * 5 != 0:
                _add_room(mt, grid, frontier, min_col, max_col,
                          rooms_remaining, level)
                return

        if grid[fr][fc] != 0:
            _add_room(mt, grid, frontier, min_col, max_col,
                      rooms_remaining, level)
            return

        grid[fr][fc] = fl
        _add_neighbors_to_frontier(frontier, fr, fc, fl, min_col, max_col)
        return


# ---------------------------------------------------------------------------
# Random filler rooms (Module.cs:19278-19314)
# ---------------------------------------------------------------------------

def _add_random_rooms(
    mt: MersenneTwister64,
    grid: list[list[int]],
    frontier: list[tuple[int, int, int]],
    min_col: list[int],
    max_col: list[int],
    levels_to_place: int,
) -> None:
    for _ in range(3):
        rand_level = int(mt.next() % levels_to_place) + 1
        rand_row = int(mt.next() & 7)
        rv = mt.next()
        col_min = min_col[rand_level]
        col_max = max_col[rand_level]
        col_range = col_max - col_min + 1
        if col_range <= 0:
            continue
        rand_col = int(rv % col_range) + col_min

        if grid[rand_row][rand_col] == 0:
            grid[rand_row][rand_col] = rand_level

        _add_neighbors_to_frontier(frontier, rand_row, rand_col,
                                   rand_level, min_col, max_col)


# ---------------------------------------------------------------------------
# addStairSpots (Module.cs:18681-18908)
# ---------------------------------------------------------------------------

def _add_stair_spots(
    mt: MersenneTwister64,
    grid: list[list[int]],
    levels_to_place: int,
) -> bool:
    component_counts = _count_level_components(grid, levels_to_place)

    if levels_to_place == 6:
        for lv in range(1, 7):
            component_counts[lv] += 1
        component_counts[2] -= 1
    else:
        component_counts[1] += 1
        component_counts[2] += 2
        component_counts[3] += 2

    needed_empty = sum(
        component_counts[lv] - 1
        for lv in range(1, levels_to_place + 1)
    )
    if levels_to_place == 6:
        needed_empty += 2
    else:
        needed_empty += 9

    empty_count = sum(
        1 for r in range(GRID_ROWS) for c in range(GRID_COLS)
        if grid[r][c] == 0
    )

    if empty_count >= needed_empty:
        return False

    to_remove = needed_empty - empty_count
    removed = 0
    while removed < to_remove:
        row = int(mt.next() % 6)
        col = int(mt.next() & 15)
        if grid[row][col] != 0 and _no_break(grid, row, col):
            grid[row][col] = 0
            removed += 1

    return True


# ---------------------------------------------------------------------------
# Component counting (Module.cs:18737-18833)
# ---------------------------------------------------------------------------

def _count_level_components(
    grid: list[list[int]],
    levels_to_place: int,
) -> list[int]:
    visited = [[False] * GRID_COLS for _ in range(GRID_ROWS)]
    counts = [0] * (levels_to_place + 1)

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            level = grid[row][col]
            if level != 0 and not visited[row][col]:
                _bfs_flood(grid, visited, row, col, level)
                counts[level] += 1

    return counts


def _bfs_flood(
    grid: list[list[int]],
    visited: list[list[bool]],
    start_row: int,
    start_col: int,
    level: int,
) -> None:
    queue = deque([(start_row, start_col)])
    visited[start_row][start_col] = True
    while queue:
        r, c = queue.popleft()
        for d in range(4):
            nr = r + _DIR_ROW[d]
            nc = c + _DIR_COL[d]
            if (0 <= nr < GRID_ROWS and 0 <= nc < GRID_COLS
                    and not visited[nr][nc] and grid[nr][nc] == level):
                visited[nr][nc] = True
                queue.append((nr, nc))


# ---------------------------------------------------------------------------
# noBreak (Module.cs:18500-18664)
# ---------------------------------------------------------------------------

def _no_break(grid: list[list[int]], row: int, col: int) -> bool:
    """Check if removing grid[row][col] would NOT disconnect its level."""
    level = grid[row][col]
    if level == 0:
        return True

    grid[row][col] = 0

    # Find first same-level neighbor
    first_neighbor = None
    for d in range(4):
        nr = row + _DIR_ROW[d]
        nc = col + _DIR_COL[d]
        if 0 <= nr <= 7 and 0 <= nc <= 15:
            if grid[nr][nc] == level:
                first_neighbor = (nr, nc)
                break

    if first_neighbor is None:
        grid[row][col] = level
        return True

    # BFS from first neighbor through same-level cells
    visited_grid = [[0] * GRID_COLS for _ in range(GRID_ROWS)]
    queue = deque([first_neighbor])
    visited_grid[first_neighbor[0]][first_neighbor[1]] = level
    while queue:
        r, c = queue.popleft()
        for d in range(4):
            nr = r + _DIR_ROW[d]
            nc = c + _DIR_COL[d]
            if (0 <= nr <= 7 and 0 <= nc <= 15
                    and visited_grid[nr][nc] == 0
                    and grid[nr][nc] == level):
                visited_grid[nr][nc] = level
                queue.append((nr, nc))

    grid[row][col] = level

    # Check: for every original neighbor of (row, col) that has same level,
    # is there a visited_grid neighbor that is UNVISITED? If so, disconnected.
    for d in range(4):
        nr = row + _DIR_ROW[d]
        nc = col + _DIR_COL[d]
        if 0 <= nr <= 7 and 0 <= nc <= 15:
            if grid[nr][nc] == level:
                if visited_grid[nr][nc] == 0:
                    return False

    return True


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


def _empty_grid() -> list[list[int]]:
    return [[0] * GRID_COLS for _ in range(GRID_ROWS)]
