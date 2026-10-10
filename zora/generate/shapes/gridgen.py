"""Shape step: grow blobs until the grid is tiled (SH-GRID-01..07).

Numbering + freeing for stairs is numbering.number_with_frees (runs next);
SH-GRID-08's "never the bottom two rows" protection also keeps entrance
candidates (bottom row) and the L9 entry-person room (row 6) intact.
"""
from ...model import room_grid
from ...model.enums import Side
from ...model.room_grid import neighbour
from ..rng import IntRng, Rng
from .options import ShapeOptions
from .world import GRID_COLS, GRID_ROWS, SetWorld

# In-grid neighbours of every cell, in N/E/S/W order (precomputed: growth
# reads them for every frontier push and weight).
_NEIGHBORS: tuple[tuple[int, ...], ...] = tuple(
    tuple(n for n in (neighbour(c, d) for d in Side) if n is not None)
    for c in range(GRID_COLS * GRID_ROWS)
)


def grow_set(world: SetWorld, rng: Rng, six_level: bool,
             opts: ShapeOptions | None = None) -> None:
    """SH-GRID-02..06/13 (917a41f): starts, one growth step per level (in-set
    order), the three extra seeds, 12 (six-level) / 17 (three-level) more
    rounds, then the fill until the frontier is empty. The frontier is a
    LIST of (cell, level) entries (SH-GRID-13): every placement appends one
    entry per on-grid neighbour inside the placing level's band; duplicates
    and entries for owned cells stay listed. Leftover cells stay unowned
    (no sweep); they join the stair pool (SH-GRID-08)."""
    opts = opts or ShapeOptions()
    frontier: list[tuple[int, int]] = []
    _place_starts(world, rng, six_level, frontier)
    order = list(range(world.blob_count))
    for blob in order:               # update 10: one step per level, 1, 2, 3...
        _grow_step(world, rng, blob, frontier)
    _place_seeds(world, rng, opts, frontier)
    rounds = 12 if six_level else 17
    for _ in range(rounds):          # same in-set order (QUESTIONS #44.1)
        for blob in order:
            _grow_step(world, rng, blob, frontier)
    _fill(world, rng, frontier)


def _place(world: SetWorld, cell: int, blob: int,
           frontier: list[tuple[int, int]]) -> None:
    world.assign(cell, blob)
    _push_neighbors(world, cell, blob, frontier)


def _push_neighbors(world: SetWorld, cell: int, blob: int,
                    frontier: list[tuple[int, int]]) -> None:
    lo, hi = world.bands[blob]
    frontier.extend((n, blob) for n in _NEIGHBORS[cell] if lo <= (n & 0x0F) <= hi)


_POW10 = (1, 10, 100, 1000, 10000)


def _weight(world: SetWorld, cell: int, blob: int) -> int:
    """SH-GRID-05/13: 10 ** (in-band neighbours that are free or owned by
    another level), evaluated at draw time; the first-grown level of the
    set (in-set blob 0) doubles it, so it is never weight 1."""
    lo, hi = world.bands[blob]
    owner_of = world.blob_of
    k = 0
    for m in _NEIGHBORS[cell]:
        if lo <= (m & 0x0F) <= hi and owner_of[m] != blob:
            k += 1
    w = _POW10[k]
    return w * 2 if blob == 0 else w


def _take(world: SetWorld, rng: Rng, frontier: list[tuple[int, int]],
          idxs: list[int]) -> tuple[int, int] | None:
    """One draw (SH-GRID-13): pick an entry among `idxs` by weight, REMOVE
    it, then: owned cell -> nothing placed; weight-1 entry -> the 1-in-5
    test (its own draw), dropped on failure. Returns (cell, blob) to place,
    or None when this draw placed nothing."""
    weights = [_weight(world, frontier[i][0], frontier[i][1]) for i in idxs]
    i = rng.weighted(idxs, weights)
    cell, blob = frontier.pop(i)
    if world.blob_of[cell] != -1:
        return None
    if _weight(world, cell, blob) == 1 and not rng.chance(1, 5):
        return None
    return cell, blob


def _grow_step(world: SetWorld, rng: Rng, blob: int,
               frontier: list[tuple[int, int]]) -> None:
    """A per-level round step: only this level's entries are weighted; a
    draw that places nothing draws again; with no free-cell entry left the
    level falls through to the in-band probe (5,000 misses widen the band
    one column, never past eight; at eight the step places nothing)."""
    while True:
        mine = [i for i, (c, b) in enumerate(frontier) if b == blob]
        if not any(world.blob_of[frontier[i][0]] == -1 for i in mine):
            break
        got = _take(world, rng, frontier, mine)
        if got is not None:
            _place(world, got[0], blob, frontier)
            return
    _probe(world, rng, blob, frontier)


PROBE_LIMIT = 5_000


def _probe(world: SetWorld, rng: Rng, blob: int,
           frontier: list[tuple[int, int]]) -> None:
    """Update 9 C / update 10: random in-band placement probes."""
    while True:
        lo, hi = world.bands[blob]
        for _ in range(PROBE_LIMIT):
            cell = room_grid.room_number(rng.below(GRID_ROWS), lo + rng.below(hi - lo + 1))
            if world.blob_of[cell] == -1:
                _place(world, cell, blob, frontier)
                return
        if hi - lo + 1 >= 8:
            return                    # capped: the level ends a room smaller
        side = _widen_side(world, blob, lo, hi, rng)
        blo, bhi = _band_bounds(world, blob)
        if side == 0 and lo - 1 >= blo:
            world.bands[blob] = [lo - 1, hi]
        elif side == 1 and hi + 1 <= bhi:
            world.bands[blob] = [lo, hi + 1]
        else:
            return


def _fill(world: SetWorld, rng: Rng, frontier: list[tuple[int, int]]) -> None:
    """SH-GRID-06/13 final fill: draws over ALL entries until the frontier
    is empty — no attempt cap, no skip counter, no leftover sweep."""
    while frontier:
        got = _take(world, rng, frontier, list(range(len(frontier))))
        if got is not None:
            _place(world, got[0], got[1], frontier)


def _band_for_start(start_col: int) -> list[int]:
    """SH-GRID-16 default: the eight columns starting at start-3, that start
    clamped to 0-11 and the band clipped at column 15."""
    lo = min(11, max(0, start_col - 3))
    return [lo, min(GRID_COLS - 1, lo + 7)]


# SH-GRID-03 (U21): the six-level set's sixth level draws its FIRST start
# column with these weights (out of 25); the capped formula below gives
# 12/13/14 1/5 each and 15 2/5 instead, and is used for its re-draws.
SIXTH_LEVEL_FIRST_START = ((12, 4), (13, 4), (14, 4), (15, 13))


def _six_level_start(blob: int, rng: IntRng) -> int:
    """SH-GRID-03/16: level n (blob n-1) starts at the whole part of
    2.5*(n-1) plus a uniform 0-4, capped at column 15."""
    return min(GRID_COLS - 1, (5 * blob) // 2 + rng.below(5))


def _sixth_level_first_start(rng: IntRng) -> int:
    """SH-GRID-03 (U21): level 6's first draw, 12/13/14 at 4/25, 15 at 13/25."""
    roll = rng.below(sum(weight for _, weight in SIXTH_LEVEL_FIRST_START))
    for col, weight in SIXTH_LEVEL_FIRST_START:
        if roll < weight:
            return col
        roll -= weight
    raise AssertionError("weights cover the roll")


def _start_is_free(world: SetWorld, col: int) -> bool:
    return world.blob_of[room_grid.room_number(GRID_ROWS - 1, col)] == -1


def _place_starts(world: SetWorld, rng: Rng, six_level: bool,
                  frontier: list[tuple[int, int]]) -> None:
    """SH-GRID-03/16: draw every start and fix every band, THEN list the
    start cells' neighbours under the final bands (SH-GRID-16 *Order*)."""
    starts: list[tuple[int, int]] = []           # (cell, blob), placement order
    if six_level:
        for blob in range(world.blob_count):
            # SH-GRID-16 start-cell re-draws: the row never changes; the
            # column is re-drawn until the cell is free.
            if blob == world.blob_count - 1:
                col = _sixth_level_first_start(rng)
            else:
                col = _six_level_start(blob, rng)
            while not _start_is_free(world, col):
                col = _six_level_start(blob, rng)
            # SH-GRID-16: the default band from the final column, then the
            # first level's minimum forced to 0 and maximum to at most 7;
            # the sixth level's maximum forced to 15, minimum at least 8.
            band = _band_for_start(col)
            if blob == 0:
                band = [0, min(band[1], 7)]
            elif blob == world.blob_count - 1:
                band = [max(band[0], 8), GRID_COLS - 1]
            world.bands[blob] = band
            starts.append((room_grid.room_number(GRID_ROWS - 1, col), blob))
            world.assign(starts[-1][0], blob)
    else:
        # SH-GRID-03: three-level set. First starts at column 6 and takes the
        # cell above it; second in cols 0-11; third in cols 8-15.
        # SH-GRID-16: first band replaced outright with columns 0-7.
        world.bands[0] = [0, 7]
        for cell in (room_grid.room_number(GRID_ROWS - 1, 6), room_grid.room_number(GRID_ROWS - 2, 6)):
            starts.append((cell, 0))
            world.assign(cell, 0)
        # Second level: drawn from 0-11; a re-draw after landing on a taken
        # cell uses 4-11; the band uses the final column.
        col_second = rng.below(12)
        while not _start_is_free(world, col_second):
            col_second = 4 + rng.below(8)
        redrawn = col_second < 7
        if redrawn:
            # Started left of column 7: its band becomes columns 0 to at most
            # 6, and the first level's band is re-drawn: eight wide, minimum
            # 3-6 uniformly.
            world.bands[1] = [0, min(_band_for_start(col_second)[1], 6)]
            lo = 3 + rng.below(4)
            world.bands[0] = [lo, lo + 7]
        else:
            world.bands[1] = _band_for_start(col_second)
        starts.append((room_grid.room_number(GRID_ROWS - 1, col_second), 1))
        world.assign(starts[-1][0], 1)
        # Third level: its band is the whole right half, or 10-15 when the
        # first level's band was re-drawn. Its start is drawn from 8-15 and
        # re-drawn from the same range while taken (SH-GRID-16).
        world.bands[2] = [10, 15] if redrawn else [8, 15]
        col_third = 8 + rng.below(8)
        while not _start_is_free(world, col_third):
            col_third = 8 + rng.below(8)
        starts.append((room_grid.room_number(GRID_ROWS - 1, col_third), 2))
        world.assign(starts[-1][0], 2)
    for cell, blob in starts:
        _push_neighbors(world, cell, blob, frontier)


def _band_bounds(world: SetWorld, blob: int) -> tuple[int, int]:
    """SH-GRID-04 edge clamps as widening bounds: the first level of a set
    is held to columns 0-7, the last to columns 8-15 (both sets); middle
    levels may reach the whole grid."""
    if blob == 0:
        return (0, 7)
    if blob == world.blob_count - 1:
        return (8, GRID_COLS - 1)
    return (0, GRID_COLS - 1)



def _widen_side(world: SetWorld, blob: int, lo: int, hi: int,
                rng: Rng) -> int:
    """Update 9 C: widen one column toward the OPEN side — the side where
    the blob borders free space it cannot claim — or a random side when
    both are open. Edge-clamp bounds (SH-GRID-04) constrain movement.
    Returns -1 when no side can move."""
    blo, bhi = _band_bounds(world, blob)
    left_open, right_open = lo > blo, hi < bhi
    if not (left_open or right_open):
        return -1
    pressure_l = pressure_r = False
    for c in world.cells_by_blob[blob]:
        col = room_grid.column(c)
        if col == lo:
            nb = room_grid.room_number(room_grid.row(c), col - 1) if col > 0 else None
            if nb is not None and world.blob_of[nb] == -1:
                pressure_l = True
        elif col == hi:
            nb = room_grid.room_number(room_grid.row(c), col + 1) if col < GRID_COLS - 1 else None
            if nb is not None and world.blob_of[nb] == -1:
                pressure_r = True
    if left_open and not right_open:
        return 0
    if right_open and not left_open:
        return 1
    if pressure_l and not pressure_r:
        return 0
    if pressure_r and not pressure_l:
        return 1
    return rng.below(2)


def _place_seeds(world: SetWorld, rng: Rng, opts: ShapeOptions,
                 frontier: list[tuple[int, int]]) -> None:
    """SH-GRID-06 seeds: three draws per set — a level uniformly, a row
    uniformly from all eight, a column uniformly inside that level's band.
    A free cell becomes the level's; either way the picked cell's in-band
    neighbours join that level's frontier."""
    for _ in range(3):
        blob = rng.below(world.blob_count)
        row = rng.below(GRID_ROWS)
        lo, hi = world.bands[blob]
        cell = room_grid.room_number(row, lo + rng.below(hi - lo + 1))
        if world.blob_of[cell] == -1:
            _place(world, cell, blob, frontier)
        else:
            _push_neighbors(world, cell, blob, frontier)
