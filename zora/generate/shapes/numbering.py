"""Level numbering + stair-cell freeing (SH-NUM-01/02, SH-GRID-08).

Parsed room counts are monotone in 1000/1000 corpus ROMs
(SH-NUM-01), so numbering must reflect sizes AFTER freeing. Freeing counts
depend on level numbers (per-level allowances), so we iterate to a fixed
point: number by current sizes → free/restore to match each level's allowance
→ repeat until stable. Cells are only restored before any content is placed,
so this is safe.

SH-GRID-08 constraints honored in the free step: rows 0-5 only (never the
bottom two rows), removal never splits the level. Restores happen LIFO by
cell order (deterministic).
"""
from ...model import room_grid
from ...model.enums import Side
from ...model.room_grid import neighbour
from ..errors import GenerationFailure
from ..rng import Rng
from .options import ShapeOptions
from .world import GRID_COLS, GRID_ROWS, SetWorld


def spatial_pieces(world: SetWorld, blob: int) -> list[list[int]]:
    return spatial_pieces_of(set(world.cells_by_blob[blob]))


def spatial_pieces_of(cells: set[int]) -> list[list[int]]:
    """The cells' grid-adjacent pieces, each sorted, in grid order."""
    seen: set[int] = set()
    out: list[list[int]] = []
    for start in sorted(cells):
        if start in seen:
            continue
        comp: list[int] = []
        stack = [start]
        seen.add(start)
        while stack:
            c = stack.pop()
            comp.append(c)
            for d in Side:
                nb = neighbour(c, d)
                if nb in cells and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        out.append(sorted(comp))
    return out


def _would_split(world: SetWorld, blob: int, cell: int,
                 current_pieces: int) -> bool:
    cells = set(world.cells_by_blob[blob])
    rest = cells - {cell}
    if not rest:
        return True
    seen: set[int] = set()
    count = 0
    for start in sorted(rest):
        if start in seen:
            continue
        count += 1
        stack = [start]
        seen.add(start)
        while stack:
            c = stack.pop()
            for d in Side:
                nb = neighbour(c, d)
                if nb in rest and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        if count > current_pieces:
            return True
    return False


def number_with_frees(world: SetWorld, rng: Rng, opts: ShapeOptions) -> None:
    """SH-GRID-08 (spec update 5, exact) + SH-NUM-01/02.

    1. In-set numbers assigned once, in grow order (blob index).
    2. THE POOL: demand = Σ(extra pieces per level) + Σ(cellar items per
       level under the in-set numbers) + constant (2 six-set / 9 three-set),
       counted once, after growth. Filled by an UNCAPPED SPIN: draw (row
       0-5, column 0-15); if the cell is owned and removing it does not
       split its level, clear it; repeat until the free cells meet the
       demand. The spin cannot legitimately fail (guard only catches bugs).
       This runs BEFORE renumbering; nothing reconciles after.
    3. ONE renumber by post-free room counts, ties broken by the in-set
       number (SH-NUM-01 monotone by construction). place_stairs then takes
       pool cells in cell order; the per-level budgets exactly consume the
       six-set pool and leave one spare cell in the three-set pool (the
       systematic extra unowned cell of the 7-9 grid, SH-GRID-01), plus
       one cell for each piece the spin removed.
    """
    base = world.base_level
    early: dict[int, int] = {}
    for blob in range(world.blob_count):
        early[blob] = base + 1 + blob
        world.levels[blob] = early[blob]

    from .tables import cellar_items
    cellars = sum(len(cellar_items(early[b], opts.level_2_sword_cellar))
                  for b in range(world.blob_count))
    const = 2 if world.blob_count == 6 else 9

    # SH-GRID-08: the generator counts the pieces and demands that many free
    # cells; the spin then re-checks only the free count. Quirk: freeing can
    # delete a level's single-cell piece (rows 0-5), which lowers the piece
    # count at stair time but not the demand, so stairs leave one more cell
    # unowned (shapes-answers update 9: extra pieces 0.363 per level after
    # growth, 0.359 at stair time; SH-GRID-13: "any excess", 29 of 1,000
    # finals with more than one unowned cell).
    demand = (sum(max(0, len(spatial_pieces(world, b)) - 1)
                  for b in range(world.blob_count))
              + cellars + const)

    def _free_cells() -> int:
        # SH-GRID-08: "any grid cell that no level owns" — growth leftovers
        # (SH-GRID-13: no sweep reclaims them) count as well as freed cells.
        return sum(1 for b in world.blob_of if b < 0)

    spins = 0
    while _free_cells() < demand:
        spins += 1
        if spins > 200_000:
            raise GenerationFailure("stair pool spin guard hit (bug?)")
        cell = rng.below(6) * 16 + rng.below(GRID_COLS)
        b = world.blob_of[cell]
        if b < 0:
            continue
        if _would_split(world, b, cell, len(spatial_pieces(world, b))):
            continue
        world.free_for_stair(cell)

    order = sorted(range(world.blob_count),
                   key=lambda b: (len(world.cells_by_blob[b]), early[b]))
    numbers = [base + i + 1 for i in range(world.blob_count)]
    if not opts.sort_shapes:
        rng.shuffle(numbers)  # SH-NUM-02 (separate per set)
    for i, blob in enumerate(order):
        world.levels[blob] = numbers[i]


def _free_one(world: SetWorld, rng: Rng, blob: int) -> None:
    pieces = len(spatial_pieces(world, blob))
    candidates = [c for c in sorted(world.cells_by_blob[blob])
                  if room_grid.row(c) <= GRID_ROWS - 3  # rows 0-5 (SH-GRID-08)
                  and not _would_split(world, blob, c, pieces)]
    if not candidates:
        raise GenerationFailure(f"blob {blob}: cannot free enough rooms")
    world.free_for_stair(candidates[rng.below(len(candidates))])
