"""Entrance placement (SH-ENT-01..04).

Runs after doors so the entrance's south side can be forced open.
"""
from zora.generate.errors import GenerationFailure
from zora.generate.rng import Rng
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.world import GRID_ROWS, SetWorld
from zora.model import room_grid
from zora.model.enums import RoomAction, RoomType, Side
from zora.model.room_grid import neighbour
from zora.model.rooms import NO_ITEM_CODE

W_OPEN = 0
W_WALL = 1


def place_entrances(world: SetWorld, rng: Rng, opts: ShapeOptions) -> None:
    for blob in range(world.blob_count):
        level = world.levels[blob]
        cells = sorted(world.cells_by_blob[blob])
        candidates: list[int] = []
        for cell in cells:
            row = room_grid.row(cell)
            same_level_neighbors = any(
                world.blob_of[nb] == blob
                for nb in (neighbour(cell, d) for d in Side)
                if nb is not None
            )
            if not same_level_neighbors:
                continue
            if not opts.start_room_swap and row != GRID_ROWS - 1:
                continue  # bottom edge only (SH-ENT-01)
            if opts.start_room_swap and row != GRID_ROWS - 1:
                # Unless on the bottom row, the room below must be a
                # different level (SH-ENT-01).
                below = neighbour(cell, Side.SOUTH)
                if below is not None and world.blob_of[below] == blob:
                    continue
            candidates.append(cell)
        if level == 9:
            # SH-ENT-02: level 9's entrance is always bottom row with a
            # level 9 room above, even when entrances may be anywhere.
            candidates = [c for c in candidates
                          if room_grid.row(c) == GRID_ROWS - 1
                          and world.blob_of[c - 16] == blob]
        if not candidates:
            # SH-ENT-04: no qualifying room — restart generation.
            raise GenerationFailure(f"no entrance candidate for level {level}")
        # SH-ENT-02 note: start_room_swap is off by default; when it is on,
        # levels other than 9 keep the bottom-row rule unless swapped option.
        entrance = candidates[rng.below(len(candidates))]
        world.entrance[level] = entrance
        plan = world.plans[entrance]
        # SH-ENT-03: entrance layout $21, south side open, item none,
        # kill-all trigger. Other sides keep their placed door state.
        plan.layout = RoomType.ENTRANCE_ROOM
        plan.movable = False
        plan.walls[Side.SOUTH] = W_OPEN
        plan.item = NO_ITEM_CODE
        plan.item_pos = 0
        plan.action = RoomAction.ALL_DEAD
