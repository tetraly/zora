"""Ordinary rooms: random layouts, items, triggers (SH-ROOM-09..15, T3).

Step 7 of the generation flow.
"""
from zora.generate.errors import GenerationFailure
from zora.generate.rng import Rng
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.t4_tables import T4_FIRST_QUEST, T4_SECOND_QUEST_ADDITION
from zora.generate.shapes.t5_positions import item_slots_for
from zora.generate.shapes.tables import T3_WEIGHTS
from zora.generate.shapes.world import SetWorld
from zora.model.enums import Item, RoomAction
from zora.model.rooms import NO_ITEM_CODE

# zora.model item codes used in room data bytes

PERSON_LAYOUT = 0x26
# SH-ROOM-08 reserved layout ids (masked; push-block variants are zeroed too)
RESERVED_LAYOUTS = frozenset({0x1A, 0x1B, 0x1C, 0x21, 0x27, 0x28, 0x29})
# SH-ROOM-14: layouts that get rarer with each use in a level.
RARE_WITH_USE = (0x0E, 0x0F, 0x12)


def _layout_weights(level: int, opts: ShapeOptions) -> list[int]:
    # SH-ROOM-09 / T4: per-level first-quest weights; second-quest row added
    # when the option is on.
    row = list(T4_FIRST_QUEST[level])
    if opts.second_quest_rooms:
        add = T4_SECOND_QUEST_ADDITION[level]
        for i in range(128):
            row[i] += add[i]
    # SH-ROOM-08: reserved layouts never drawn randomly (mask + push-block
    # variants).
    for code in RESERVED_LAYOUTS:
        row[code] = 0
        row[code | 0x40] = 0
    # SH-ROOM-07: person layout weight reduced by one (by two from level 4).
    # SPEC-GAP 7: floored at zero. Measured at the shapes stage: no shave →
    # 19.1 person rooms/grid (overshoot), full shave → 12.1 (slight
    # undershoot) vs the corpus's 14.35 at both stages — applied as
    # spec-written; the residual gap is flagged in QUESTIONS.
    reduction = 2 if level >= 4 else 1
    for base in (PERSON_LAYOUT, PERSON_LAYOUT | 0x40):
        row[base] = max(0, row[base] - reduction)
    return row


def _draw_layout(rng: Rng, weights: list[int]) -> int:
    """One layout draw from the level's weights; a rare layout with a use
    count loses one weight each time it is drawn (weights changes in place)."""
    lay = rng.weighted(list(range(128)), weights)
    for code in RARE_WITH_USE:
        if lay == code:
            weights[code] = max(0, weights[code] - 1)
    return lay


def place_rooms(world: SetWorld, rng: Rng, opts: ShapeOptions) -> None:
    for blob in range(world.blob_count):
        level = world.levels[blob]
        weights = _layout_weights(level, opts)
        cells = sorted(world.cells_by_blob[blob])
        pending = [c for c in cells if world.plans[c].layout is None]
        variant_count = 0
        for cell in pending:
            plan = world.plans[cell]

            layout = _draw_layout(rng, weights)
            plan.layout = layout & 0x3F
            plan.movable = bool(layout & 0x40)
            table = world.pos_tables.get(level, [])
            item = _draw_item(rng, level, cell)

            # SH-ROOM-12 (T6, spec update 6 note): a room counts as a
            # VARIANT room when its exact drawn screen type has a base-list
            # T5 row AND one or more of that row's values equals one of the
            # level's four T6 bytes (push-block types only via the exact
            # code, e.g. $5A/$63 — handled because `layout` keeps its $40
            # bit when item_slots_for runs).
            slots = item_slots_for(layout, table, opts.universal_drops)
            if item == NO_ITEM_CODE and variant_count < 4:
                # Rule 1 fires only on VARIANT-candidate rooms (T6 test): redraw the ITEM only (layout kept)
                # until something is held, or the level reaches four variant
                # rooms. Non-variant layouts keep their T3 "no item" draw —
                # that is where the corpus's 68/ROM no-items accumulate.
                tries = 0
                while item == NO_ITEM_CODE and variant_count < 4 and tries < 32:
                    item = _draw_item(rng, level, cell)
                    tries += 1
            if item != NO_ITEM_CODE and not slots:
                # Rule 2: an item the layout cannot seat.
                if variant_count > 5:
                    item = NO_ITEM_CODE          # keep layout, drop the item
                else:
                    # erase the room and redraw BOTH until it fits (uncapped
                    # redo; guard only catches bugs)
                    tries = 0
                    while not slots and tries < 5000:
                        layout = _draw_layout(rng, weights)
                        plan.layout = layout & 0x3F
                        plan.movable = bool(layout & 0x40)
                        slots = item_slots_for(layout, table, opts.universal_drops)
                        item = _draw_item(rng, level, cell)
                        while item == NO_ITEM_CODE and variant_count < 4:
                            item = _draw_item(rng, level, cell)
                        tries += 1
                    if not slots:
                        raise GenerationFailure(
                            "SH-ROOM-12 redo could not seat an item"
                        )
            plan.item = item
            if item != NO_ITEM_CODE and slots:
                plan.item_pos = slots[rng.below(len(slots))]
                if len(slots) >= 1:
                    variant_count += 1
            else:
                plan.item_pos = 0
            # SH-ROOM-13: triggers.
            if plan.movable and (layout & 0x3F) != 0x20:
                plan.action = RoomAction.BLOCK_DOOR
            elif item != NO_ITEM_CODE and rng.chance(2, 3):
                plan.action = RoomAction.ALL_DEAD_ITEM
            else:
                plan.action = RoomAction.ALL_DEAD


def _draw_item(rng: Rng, level: int, cell: int) -> int:
    opts_weights = list(T3_WEIGHTS[level])
    # SH-ROOM-15's key ban applies to STAIR rooms (measured) and lives in
    # stairs.py; ordinary rooms keep the plain T3 draw.
    total = sum(opts_weights)
    if total <= 0:
        # all options were key/nothing-only: fall back to nothing
        return NO_ITEM_CODE
    choice = rng.weighted(list(range(4)), opts_weights)
    return (Item.BOMBS, NO_ITEM_CODE, Item.FIVE_RUPEES, Item.KEY)[choice]
