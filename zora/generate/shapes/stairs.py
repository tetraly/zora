"""Staircase placement (SH-STAIR-01..10, T2).

Cells were already freed by number_with_frees (SH-GRID-08). This step
consumes a level's freed cells: item cellars first, then transports, joining
spatial pieces first so the level ends up connected (SH-GRID-07/09).
"""
from ...model.enums import Item, RoomAction
from ...model.rooms import DIAMOND_STAIRS_PUSH, LAYOUT_ID_MASK, SPIRAL_STAIRS_PUSH
from ..errors import GenerationFailure
from ..rng import Rng
from .numbering import spatial_pieces
from .options import ShapeOptions
from .t5_positions import item_slots_for
from .tables import (
    T2_FIRST_QUEST_WEIGHTS,
    T2_LAYOUTS,
    T2_SECOND_QUEST_WEIGHTS,
    cellar_items,
    stair_budget,
)
from .world import SetWorld, StairKind, StairPlan, StairRole

# SH-STAIR-08: the triggers a stair room with an item may trade for kill-for-item (0 and 1)
ITEM_TRIGGER_REPLACEABLE = (RoomAction.NONE, RoomAction.ALL_DEAD)


def _draw_stair_layout(rng: Rng, opts: ShapeOptions) -> int:
    layouts = list(T2_LAYOUTS)
    weights = list(T2_FIRST_QUEST_WEIGHTS)
    if opts.second_quest_rooms:
        for i, w in enumerate(T2_SECOND_QUEST_WEIGHTS):
            weights[i] += w
    return rng.weighted(layouts, weights)


def _is_push_block(layout: int) -> bool:
    return layout >= 0x40


def _assign_stair_room(world: SetWorld, rng: Rng, opts: ShapeOptions,
                       cell: int, role: StairRole) -> None:
    """(positions gated by T5 vs the level's standard position table)"""
    """Give a stair room its layout/trigger/key (SH-STAIR-05..08).

    SH-STAIR-06: push-block layouts get "push block reveals stairs" except
    $5A and $5C. SH-STAIR-07: the SECOND transport room's exception set is
    {$5A, $5C} and $5C instead gets "push block opens door"; the first room
    excludes only $5A, so a first-room $5C follows the base rule. For a
    cellar house $5C is excluded by the base rule → no push trigger.
    """
    layout = _draw_stair_layout(rng, opts)
    plan = world.plans[cell]
    plan.layout = layout & LAYOUT_ID_MASK
    plan.movable = _is_push_block(layout)
    # SH-STAIR-08: key + two-in-three kill-for-item trigger.
    # SPEC-GAP 3: "usable item position" list is missing from the spec;
    # all four standard positions are assumed usable, so stair rooms always
    # take a key.
    # SH-STAIR-08: the key only lands if the layout has a usable item
    # position — now judged properly via T5 against the level's standard
    # positions (SH-ROOM-11 model change).
    table = world.pos_tables.get(world.levels[blob_of_cell(world, cell)], [])
    slots = item_slots_for(layout, table, opts.universal_drops)
    # SH-ROOM-15: "when a stair room's key is placed, rooms whose number is
    # divisible by three never get a key" — measured at the shapes stage this
    # suppression is on STAIR rooms (key rate 8.9% vs 27% at cell%3==0),
    # while ordinary rooms show none (18.5% vs 18.3%) — the ban lives here,
    # not in the random-room item draw. Residual keys at %3 (~1/3 of the
    # un-suppressed rate) are measured but unexplained; see QUESTIONS #33.
    if slots and cell % 3 != 0:
        plan.item = Item.KEY
        plan.item_pos = slots[rng.below(len(slots))]
    if _is_push_block(layout):
        if layout == SPIRAL_STAIRS_PUSH and role is StairRole.SECOND_END:
            plan.action = RoomAction.BLOCK_DOOR
        elif (layout == DIAMOND_STAIRS_PUSH
              or (layout == SPIRAL_STAIRS_PUSH and role is StairRole.CELLAR_HOUSE)):
            plan.action = RoomAction.ALL_DEAD
        else:
            plan.action = RoomAction.BLOCK_STAIRS
    else:
        plan.action = RoomAction.ALL_DEAD
    # SH-STAIR-08: then any room with an item still on trigger 0 or 1 (the push-block layouts
    # $5A and $5C included) gets "kill all enemies for the item" two times in three.
    if plan.item is not None and plan.action in ITEM_TRIGGER_REPLACEABLE and rng.chance(2, 3):
        plan.action = RoomAction.ALL_DEAD_ITEM


def blob_of_cell(world: SetWorld, cell: int) -> int:
    for b, cs in enumerate(world.cells_by_blob):
        if cell in cs:
            return b
    return -1


def _blob_freed(world: SetWorld, blob: int) -> list[int]:
    return sorted(c for c, b in world.freed.items() if b == blob)


def place_stairs(world: SetWorld, rng: Rng, opts: ShapeOptions) -> None:
    protected: set[int] = set()
    if world.base_level == 6 and 9 in world.entrance:
        protected.add(world.entrance[9] - 16)  # SH-ROOM-05 / SH-STAIR-10

    # SH-GRID-08 (update 5): the freed pool is GLOBAL; levels take their
    # budget's worth of cells in cell order. Six-set budgets consume the pool
    # exactly; the three-set leaves its last pool cell spare (unowned — the
    # 7-9 grid's systematic extra corner).
    # SH-GRID-08: stairs take FREE cells (owned by no level: growth
    # leftovers and freed cells) in cell order; any excess stays unowned —
    # always the highest-numbered free cells (SH-GRID-13 Check).
    pool = [c for c in range(len(world.blob_of)) if world.blob_of[c] < 0]
    take_at = 0
    for level in sorted(world.levels.values()):
        blob = next(b for b in range(world.blob_count)
                    if world.levels[b] == level)
        pieces = len(spatial_pieces(world, blob))
        budget = stair_budget(level, opts.level_2_sword_cellar) + pieces - 1
        if budget > 9:
            # SH-STAIR-02: more than nine stairs restarts generation.
            raise GenerationFailure(
                f"level {level} would need {budget} stairs (>9)"
            )
        free_stair_cells = pool[take_at:take_at + budget]
        take_at += budget
        if len(free_stair_cells) != budget:
            raise GenerationFailure(
                f"level {level}: pool exhausted (budget {budget})"
            )
        cellars = cellar_items(level, opts.level_2_sword_cellar)
        if len(cellars) > budget:
            raise GenerationFailure(f"level {level}: cellars exceed budget")
        transports = budget - len(cellars)

        # --- item cellars placed first (SH-STAIR-02/03) ---
        for item in cellars:
            house = _pick_room_without_layout(world, rng, blob, protected)
            _assign_stair_room(world, rng, opts, house, role=StairRole.CELLAR_HOUSE)
            cell = free_stair_cells.pop(rng.below(len(free_stair_cells)))
            world.stairs[cell] = StairPlan(
                cell=cell, kind=StairKind.CELLAR, item=item, house=house
            )

        # --- transport staircases (SH-STAIR-15, spec update 7a) ---
        # Both endpoint rooms are drawn uniformly from the level's cells
        # that have no layout yet, with NO piece awareness: they may land in
        # the same piece, and a level may ship with unjoined pieces. The
        # budget itself still carries pieces-1 (update 5's pool arithmetic);
        # the endpoints simply do not aim at the extra pieces.
        for _k in range(transports):
            pool_rooms = _all_without_layout(world, blob, protected)
            if len(pool_rooms) < 2:
                raise GenerationFailure("not enough rooms for transports")
            x = pool_rooms[rng.below(len(pool_rooms))]
            b_pool = [c for c in pool_rooms if c != x]
            y = b_pool[rng.below(len(b_pool))]
            _assign_stair_room(world, rng, opts, x, role=StairRole.FIRST_END)
            _assign_stair_room(world, rng, opts, y, role=StairRole.SECOND_END)
            cell = free_stair_cells.pop(rng.below(len(free_stair_cells)))
            world.stairs[cell] = StairPlan(
                cell=cell, kind=StairKind.TRANSPORT, first=x, second=y
            )
        if free_stair_cells:
            raise GenerationFailure("freed cells not fully consumed")


def _all_without_layout(world: SetWorld, blob: int,
                        protected: set[int]) -> list[int]:
    return sorted(c for c in world.cells_by_blob[blob]
                  if world.plans[c].layout is None and c not in protected)


def _pick_room_without_layout(world: SetWorld, rng: Rng, blob: int,
                              protected: set[int]) -> int:
    pool = _all_without_layout(world, blob, protected)
    if not pool:
        raise GenerationFailure("no layout-free room in level")
    # SH-STAIR-15 (SPEC-GAP 20 closed): no piece-awareness
    # anywhere in staircase room choice — pure uniform draw.
    return pool[rng.below(len(pool))]


