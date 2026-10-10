"""Special rooms: triforce, people, Grumble, L9 entry person, Zelda/Ganon
(SH-ROOM-01..06). SH-ROOM-07/08 affect the random tables and live in rooms.py.
"""
from ...model import room_grid
from ...model.enums import Enemy, Item, RoomAction, RoomType
from ...model.levels import GANON_LIST, L9_ENTRY_PERSON, LEVEL_9, ZELDA_LIST
from ...model.rooms import NO_ITEM_CODE
from ..errors import GenerationFailure
from ..rng import Rng
from .options import ShapeOptions
from .t5_positions import item_slots_for
from .tables import EXTRA_PERSON_5_7, L9_PERSON_LISTS, PERSON_LIST_DEFAULT, PERSON_ROOMS
from .world import GRID_COLS, GRID_ROWS, PERSON_ROOM_INNER, ZELDA_ROOM_INNER, CellPlan, SetWorld


def _pick(world: SetWorld, rng: Rng, blob: int, *, not_bottom: bool = False,
          extra_excl: set[int] | None = None) -> int:
    excl = extra_excl or set()
    pool = [c for c in sorted(world.cells_by_blob[blob])
            if world.plans[c].layout is None and c not in excl
            and not (not_bottom and room_grid.row(c) == GRID_ROWS - 1)]
    if not pool:
        raise GenerationFailure("no layout-free room for special room")
    return pool[rng.below(len(pool))]


# Levels 5 and 7 get one more person room, with list $4F (SH-ROOM-03).
EXTRA_PERSON_LEVELS = (5, 7)
HUNGRY_GORIYA_LEVEL = 7          # SH-ROOM-04
LAST_TRIFORCE_LEVEL = 8          # SH-ROOM-01: levels 1-8 have a triforce room


def place_special_rooms(world: SetWorld, rng: Rng, opts: ShapeOptions) -> None:
    for blob in range(world.blob_count):
        level = world.levels[blob]
        if level <= LAST_TRIFORCE_LEVEL:
            _place_triforce_room(world, rng, blob, level, opts)
        _place_person_rooms(world, rng, blob, level)
        if level == LEVEL_9:
            _place_level9_rooms(world, rng, blob)


def _place_triforce_room(world: SetWorld, rng: Rng, blob: int, level: int, opts: ShapeOptions) -> None:
    """SH-ROOM-01: one triforce room per level 1-8."""
    plan = world.plans[_pick(world, rng, blob)]
    plan.layout = RoomType.TRIFORCE_ROOM
    plan.item = Item.TRIFORCE
    # SH-ROOM-11/T5 (SPEC-GAP 22 closed): layout $29 allows exactly
    # the screen position $89; the slot is wherever $89 sits in THIS
    # level's fixed table (slot 0 for six levels, 2 for one, 3 for
    # two — which is why position 0 dominates in the corpus).
    triforce_slots = item_slots_for(RoomType.TRIFORCE_ROOM, world.pos_tables.get(level, []),
                                    opts.universal_drops)
    if len(triforce_slots) != 1:
        raise GenerationFailure(
            f"level {level}: $89 triforce position in {len(triforce_slots)} slots"
        )
    plan.item_pos = triforce_slots[0]
    plan.action = RoomAction.ALL_DEAD


def _make_person_room(plan: CellPlan, enemy_list: int, action: RoomAction = RoomAction.ALL_DEAD) -> None:
    plan.layout = RoomType.BLACK_ROOM
    plan.item = NO_ITEM_CODE
    plan.enemy = enemy_list
    plan.action = action
    plan.item_pos = 0
    plan.inner_palette = PERSON_ROOM_INNER     # SH-DOOR-01


def _place_person_rooms(world: SetWorld, rng: Rng, blob: int, level: int) -> None:
    """SH-ROOM-02: fixed person-room counts, never on the bottom row (level 9's
    are placed with its entry person, _place_level9_rooms); SH-ROOM-03: levels
    5 and 7 get one more with list $4F; SH-ROOM-04: level 7's hungry goriya."""
    lists = [PERSON_LIST_DEFAULT] * PERSON_ROOMS[level] if level != LEVEL_9 else []
    if level in EXTRA_PERSON_LEVELS:
        lists.append(EXTRA_PERSON_5_7)
    if level == HUNGRY_GORIYA_LEVEL:
        lists.append(Enemy.HUNGRY_GORIYA)
    for enemy_list in lists:
        _make_person_room(world.plans[_pick(world, rng, blob, not_bottom=True)], enemy_list)


def _place_level9_rooms(world: SetWorld, rng: Rng, blob: int) -> None:
    """SH-ROOM-05: level 9's room above the entrance is a person room, placed
    FIRST so the random picks after it cannot consume it; then its other
    person rooms, and SH-ROOM-06's Zelda and Ganon rooms."""
    entry_room = world.entrance[LEVEL_9] - GRID_COLS
    plan = world.plans[entry_room]
    assert plan.layout is None, "entry person room lost its layout slot"
    _make_person_room(plan, L9_ENTRY_PERSON, RoomAction.NONE)   # "no item and no trigger"
    for enemy_list in L9_PERSON_LISTS:
        _make_person_room(world.plans[_pick(world, rng, blob, not_bottom=True)], enemy_list)

    # SH-ROOM-06: Zelda's and Ganon's rooms; random rooms, not
    # required to be adjacent (SH-ROOM-06 as written).
    zelda = _pick(world, rng, blob)
    plan = world.plans[zelda]
    plan.layout = RoomType.ZELDA_ROOM
    plan.enemy = ZELDA_LIST
    plan.item = NO_ITEM_CODE
    plan.action = RoomAction.ALL_DEAD
    plan.item_pos = 0
    world.zelda_room = zelda
    # SH-DOOR-01: Zelda's inner selector is exactly 2 (clear, then OR 2)
    plan.inner_palette = ZELDA_ROOM_INNER
    # SPEC-GAP 13 / SH-GRID-11: Zelda's room must not combine a
    # darkened-room layout with "one specific screen-display setting";
    # the setting is unnamed and the layout is fixed at $27 anyway, so
    # ensuring the room is not dark is the conservative reading.
    plan.dark = False

    ganon = _pick(world, rng, blob)
    plan = world.plans[ganon]
    plan.layout = RoomType.GANON_ROOM
    plan.enemy = GANON_LIST
    plan.item = Item.TRIFORCE_OF_POWER
    plan.action = RoomAction.ALL_DEAD
    plan.item_pos = 0
    plan.dark = True
    world.ganon_room = ganon
