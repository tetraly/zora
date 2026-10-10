"""Door placement (SH-DOOR-01..05, T1).

Runs after numbering so weights can key off the level number.
"""
from ...model import room_grid
from ...model.enums import Side
from ...model.room_grid import neighbour
from ..rng import Rng
from .options import ShapeOptions
from .tables import T1_FIRST_QUEST, T1_SECOND_QUEST
from .world import DOOR_PASS_SELECTOR, GRID_COLS, GRID_ROWS, SetWorld

# WallType values (zora.model.enums.WallType): open, wall, walk1, walk2, bomb,
# key1, key2, shutter — same order as T1 columns.
W_OPEN, W_WALL, W_WALK1, W_WALK2, W_BOMB, W_KEY1, W_KEY2, W_SHUTTER = range(8)


def _weights_for_level(level: int, opts: ShapeOptions) -> list[int]:
    row = list(T1_FIRST_QUEST[level])
    if opts.second_quest_doors:
        if T1_SECOND_QUEST is None:
            # SPEC-GAP 2 (SH-DOOR-02): second-quest door weights are not in
            # the spec. ShapeOptions rejects the option at construction;
            # this guard is not a GenerationFailure, so it cannot be retried.
            raise NotImplementedError("second_quest_doors: waits on QUESTIONS #2")
        for i, w in enumerate(T1_SECOND_QUEST[level]):
            row[i] += w
    return row


def write_palette_selectors(world: SetWorld) -> None:
    """SH-DOOR-01: the door pass's first touch of each level cell writes the
    outer selector 2 (at write-back: every level cell's is 2) and ORs 2
    into the cell's inner selector, so the inner is the base ROM's bits
    there ORed with 2. The special-room placements replace it later."""
    for cell, blob in enumerate(world.blob_of):
        if blob >= 0:
            world.plans[cell].inner_palette = (world.base_inner_palettes[cell]
                                               | DOOR_PASS_SELECTOR)


def place_doors(world: SetWorld, rng: Rng, opts: ShapeOptions) -> None:
    write_palette_selectors(world)
    for cell in range(len(world.blob_of)):
        plan = world.plans[cell]
        for d in Side:
            if plan.walls[d] == -1:
                plan.walls[d] = W_WALL

    # SH-DOOR-02/03: same-level pairs get a drawn door type on both sides.
    for cell in range(len(world.blob_of)):
        blob = world.blob_of[cell]
        if blob < 0:
            continue
        level = world.levels[blob]
        row, col = room_grid.row(cell), room_grid.column(cell)
        for d in (Side.EAST, Side.SOUTH):
            nb = cell + (1 if d == Side.EAST else 16)
            if d == Side.EAST and col == GRID_COLS - 1:
                continue
            if d == Side.SOUTH and row == GRID_ROWS - 1:
                continue
            if world.blob_of[nb] != blob:
                continue  # SH-DOOR-04: cross-level / edge handled below
            if (cell, nb) in _l9_fixed_pairs(world):
                continue  # SH-DOOR-03: fixed L9 doorways consume no randomness
            kind_idx = rng.weighted(list(range(8)), _weights_for_level(level, opts))
            # SH-DOOR-03: when the draw is open, one in five makes the NEAR
            # side a shutter; otherwise one in five makes the FAR side one.
            if kind_idx == W_OPEN and rng.chance(1, 5):
                world.plans[cell].walls[d] = W_SHUTTER
                world.plans[nb].walls[d.opposite] = W_OPEN
            elif kind_idx == W_OPEN and rng.chance(1, 5):
                world.plans[cell].walls[d] = W_OPEN
                world.plans[nb].walls[d.opposite] = W_SHUTTER
            else:
                world.plans[cell].walls[d] = kind_idx
                world.plans[nb].walls[d.opposite] = kind_idx

    # SH-DOOR-04: sides toward another level, the grid edge, or a freed stair
    # cell are solid walls. The "opposite edge write" quirk resolves to a
    # no-op under the spec's own description (it writes into a cell that is at
    # an edge and already solid); see SPEC-GAP 19 — implemented as no-op.
    for cell in range(len(world.blob_of)):
        blob = world.blob_of[cell]
        if blob < 0:
            continue
        row, col = room_grid.row(cell), room_grid.column(cell)
        for d in Side:
            adj = neighbour(cell, d)
            if adj is None or world.blob_of[adj] != blob:
                world.plans[cell].walls[d] = W_WALL

    _fixed_level9_doors(world, rng)


def _l9_fixed_pairs(world: SetWorld) -> set[tuple[int, int]]:
    """Cell pairs whose doors are fixed by SH-DOOR-05 (both rooms level 9).
    Computed up front so the T1 draw can skip them without consuming RNG."""
    pairs: set[tuple[int, int]] = set()
    def l9(c: int) -> bool:
        b = world.blob_of[c]
        return b >= 0 and world.levels.get(b) == 9
    for a, b in ((5 * 16 + 6, 6 * 16 + 6), (6 * 16 + 6, 7 * 16 + 6),
                 (6 * 16 + 5, 6 * 16 + 6), (6 * 16 + 6, 6 * 16 + 7),
                 (7 * 16 + 5, 7 * 16 + 6), (7 * 16 + 6, 7 * 16 + 7)):
        if l9(a) and l9(b):
            pairs.add((min(a, b), max(a, b)))
    return pairs


def _fixed_level9_doors(world: SetWorld, rng: Rng) -> None:
    """SH-DOOR-05: fixed doorways near the middle of level 9's bottom edge.
    Applies only where both rooms of a pair are level 9; stair-freed cells
    break the pair (no door is written through them)."""
    l9 = 9
    def lvl(c: int) -> int | None:
        blob = world.blob_of[c]
        return world.levels[blob] if blob >= 0 else None

    # Vertical doorways in column 6 between rows 5/6 and 6/7: shutters.
    for (a, b) in ((5 * 16 + 6, 6 * 16 + 6), (6 * 16 + 6, 7 * 16 + 6)):
        if lvl(a) == l9 and lvl(b) == l9:
            world.plans[a].walls[Side.SOUTH] = W_SHUTTER
            world.plans[b].walls[Side.NORTH] = W_SHUTTER
    # Horizontal doorways in row 6 between columns 5-6 and 6-7: shutters.
    for (a, b) in ((6 * 16 + 5, 6 * 16 + 6), (6 * 16 + 6, 6 * 16 + 7)):
        if lvl(a) == l9 and lvl(b) == l9:
            world.plans[a].walls[Side.EAST] = W_SHUTTER
            world.plans[b].walls[Side.WEST] = W_SHUTTER
    # Horizontal doorways in row 7 between columns 5-6 and 6-7: walls.
    for (a, b) in ((7 * 16 + 5, 7 * 16 + 6), (7 * 16 + 6, 7 * 16 + 7)):
        if lvl(a) == l9 and lvl(b) == l9:
            world.plans[a].walls[Side.EAST] = W_WALL
            world.plans[b].walls[Side.WEST] = W_WALL
