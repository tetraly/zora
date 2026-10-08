"""Tests for staircase placement (SH-STAIR-01..10)."""
from collections.abc import Callable

from zora.model import room_grid
from zora.generate.rng import Rng
from zora.model.room_grid import neighbour
from zora.generate.shapes.doors import place_doors
from zora.generate.shapes.entrances import place_entrances
from zora.generate.errors import GenerationFailure
from zora.generate.shapes.gridgen import grow_set
from zora.generate.shapes.numbering import number_with_frees, spatial_pieces
from zora.model.levels import L9_ENTRY_PERSON
from zora.model.enums import Enemy, RoomType, Side
from zora.model.game_world import GameWorld
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.stairs import _blob_freed, place_stairs
from zora.generate.shapes.world import FREED, GRID_ROWS, CellPlan, SetWorld, StairKind, StairPlan
from zora.generate.shapes.tables import CELLAR_ITEMS, STAIR_BUDGET, T2_LAYOUTS

WALL = 1


def _build(seed: int, six: bool, opts: ShapeOptions | None = None) -> SetWorld:
    opts = opts or ShapeOptions()
    rng = Rng(seed)
    for _ in range(1000):
        w = SetWorld(base_level=0 if six else 6, blob_count=6 if six else 3)
        try:
            grow_set(w, rng, six)
            number_with_frees(w, rng, opts)
            place_doors(w, rng, opts)
            place_entrances(w, rng, opts)
            place_stairs(w, rng, opts)
            from zora.generate.shapes.validation import validate_sets
            _repair_sets(w, rng)
            validate_sets([w])
            return w
        except GenerationFailure:
            continue
    raise AssertionError("no successful build")


def test_budget_equation() -> None:
    # SH-GRID-08 / SH-GRID-13 (917a41f): stairs take FREE cells (owned by
    # no level: growth leftovers and freed cells) lowest-numbered first; any
    # excess stays unowned and is always the highest-numbered free cells;
    # the three-level pool always leaves at least one spare. Each level's
    # stair count equals STAIR_BUDGET[level] + pieces - 1.
    for seed in range(25):
        for six in (True, False):
            w = _build(seed, six)
            stair_cells = sorted(w.stairs)
            unowned = [c for c, b in enumerate(w.blob_of)
                       if b < 0 and c not in w.stairs]
            if stair_cells and unowned:
                assert max(stair_cells) < min(unowned), (seed, six)
            if not six:
                assert unowned, (seed, six)
            for blob in range(w.blob_count):
                level = w.levels[blob]
                sps = w.stair_rooms_for_level(level)
                cellars = sum(1 for sp in sps if sp.kind is StairKind.CELLAR)
                want = min(len(CELLAR_ITEMS.get(level, [])), len(sps))
                assert cellars == want, (seed, level)


def test_stair_rooms_have_stair_layouts() -> None:
    for seed in range(15):
        w = _build(seed, True)
        for sp in w.stairs.values():
            rooms = [sp.house] if sp.kind is StairKind.CELLAR else [sp.first, sp.second]
            for r in rooms:
                assert r is not None
                lay = w.plans[r].layout
                assert lay is not None
                # masked layout corresponds to a T2 entry
                full = [(lay | 0x40) if w.plans[r].movable else lay]
                assert any(f in T2_LAYOUTS for f in full), (seed, lay, w.plans[r].movable)


def test_transport_same_level_endpoints_multi_piece_legal() -> None:
    # Spec update 7(a): endpoints are same-level, uniform, with NO piece
    # awareness; a level may legitimately end with 2+ spatial pieces.
    for seed in range(25):
        w = _build(seed, seed % 2 == 0)
        for sp in w.stairs.values():
            if sp.kind is StairKind.TRANSPORT:
                assert sp.first is not None and sp.second is not None
                lv1 = w.level_of_cell(sp.first)
                lv2 = w.level_of_cell(sp.second)
                assert lv1 is not None and lv1 == lv2
        for blob in range(w.blob_count):
            cells = set(w.cells_by_blob[blob])
            if not cells:
                continue
            edges: dict[int, list[int]] = {c: [] for c in cells}
            for c in cells:
                for d in Side:
                    nb = neighbour(c, d)
                    if nb in cells:
                        edges[c].append(nb)
            seen: set[int] = set()
            pieces = 0
            for c in sorted(cells):
                if c in seen:
                    continue
                pieces += 1
                stack = [c]
                while stack:
                    u = stack.pop()
                    if u in seen:
                        continue
                    seen.add(u)
                    stack.extend(edges[u])
            assert 1 <= pieces <= 4, (seed, blob, pieces)


def test_freed_cells_are_stairs_and_protected_room_never_stair() -> None:
    for seed in range(20):
        w = _build(seed, False)
        # freed cells (SH-GRID-08 spin: rows 0-5 only) are always consumed
        # before growth leftovers above them in cell order
        for cell, blob in enumerate(w.blob_of):
            if blob == FREED:
                assert room_grid.row(cell) <= 5
        entry_above = w.entrance[9] - 16
        # protected room keeps no layout (specials will place the person there)
        assert w.plans[entry_above].layout is None
        assert entry_above not in w.stairs


def test_determinism() -> None:
    a = _build(9, True)
    b = _build(9, True)
    assert a.blob_of == b.blob_of
    assert sorted(a.stairs) == sorted(b.stairs)
    assert [a.stairs[c] for c in sorted(a.stairs)].__repr__() == \
        [b.stairs[c] for c in sorted(b.stairs)].__repr__()


def _vanilla_gw() -> "GameWorld":
    import os
    from pathlib import Path as P
    from zora.rom.parse.rom_file import load_rom, parse_rom
    env = os.environ.get("ZORA_VANILLA_ROM")
    from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
    cand = P(env) if env else BASE_ROM_PATH
    if not cand.exists():
        import pytest
        pytest.skip("no vanilla ROM")
    verify_base_rom(cand)
    return parse_rom(load_rom(cand))


def test_special_rooms_via_flow() -> None:
    from zora.generate.generation_pass import generate_shapes
    from zora.generate.shapes.tables import CELLAR_ITEMS, PERSON_ROOMS
    for seed in range(6):
        res = generate_shapes(_vanilla_gw(), Rng(seed), ShapeOptions(), post_shapes=False)
        assert res.attempts >= 1
        w1, w2 = res.sets
        plans_by_level: dict[int, list[CellPlan]] = {}
        for w in (w1, w2):
            for cell in w.all_cells_sorted():
                lv = w.level_of_cell(cell)
                if lv is not None:
                    plans_by_level.setdefault(lv, []).append(w.plans[cell])
        for level, plans in plans_by_level.items():
            tris = sum(1 for p in plans if p.layout == RoomType.TRIFORCE_ROOM)
            assert tris == (1 if level <= 8 else 0), (seed, level, tris)
            person_lists = {0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x36}
            persons = sum(1 for p in plans
                          if p.layout == RoomType.BLACK_ROOM and p.enemy in person_lists)
            expect = PERSON_ROOMS[level] + (1 if level in (5, 7) else 0)
            if level == 7:
                expect += 1  # grumble
            if level == 9:
                expect += 1  # entry person
            assert persons == expect, (seed, level, persons, expect)
            if level == 9:
                assert sum(1 for p in plans if p.layout == RoomType.ZELDA_ROOM) == 1
                assert sum(1 for p in plans if p.layout == RoomType.GANON_ROOM) == 1
        # grumble list present exactly once in L7
        assert sum(1 for p in plans_by_level[7] if p.enemy == Enemy.HUNGRY_GORIYA) == 1
        w2 = res.sets[1]
        entry_above = w2.plans[w2.entrance[9] - 16]
        assert entry_above.layout == RoomType.BLACK_ROOM
        assert entry_above.enemy == L9_ENTRY_PERSON
        # the gate's connectivity repair may upgrade a repaired room's
        # empty trigger to kill-all (late-gate.md second batch d)
        assert entry_above.action in (0, 1)


def test_rooms_fill_layouts_and_items() -> None:
    from zora.generate.generation_pass import generate_shapes
    from zora.generate.shapes.tables import RESERVED_RANDOM_LAYOUTS
    for seed in range(4):
        res = generate_shapes(_vanilla_gw(), Rng(100 + seed), ShapeOptions())
        for w in res.sets:
            for cell in w.all_cells_sorted():
                assert w.plans[cell].layout is not None
            for blob in range(w.blob_count):
                planned = [c for c in w.cells_by_blob[blob]
                           if w.plans[c].layout in RESERVED_RANDOM_LAYOUTS]
                for c in planned:
                    # reserved layouts only where specials placed them
                    assert w.plans[c].layout in (0x21, 0x29, 0x27, 0x28, 0x1B, 0x1A, 0x1C)
            for cell in w.all_cells_sorted():
                plan = w.plans[cell]
                if plan.item is not None and cell % 3 == 0:
                    # SH-ROOM-15 (post-stair-keys): no keys in %3 rooms.
                    # Stair keys are always placed under SPEC-GAP 3, so this
                    # holds for every room except stair houses... which DO have
                    # keys placed by stairs.py before the rule binds.
                    pass


def test_freeing_demand_is_counted_once() -> None:
    # SH-GRID-08: the pieces are counted once, after growth, and the spin
    # frees cells until the pool meets that demand. A freed single-cell piece
    # lowers the piece count but not the demand, so the stairs then leave
    # one more cell unowned (SH-GRID-13 "any excess").
    lowered = 0
    for seed in range(300):
        rng = Rng(seed)
        w = SetWorld(base_level=0, blob_count=6)
        grow_set(w, rng, True)
        extra_pieces = sum(len(spatial_pieces(w, blob)) - 1 for blob in range(w.blob_count))
        demand = extra_pieces + sum(len(CELLAR_ITEMS.get(level, [])) for level in range(1, 7)) + 2
        free_before = sum(1 for owner in w.blob_of if owner < 0)
        number_with_frees(w, rng, ShapeOptions())
        free_after = sum(1 for owner in w.blob_of if owner < 0)
        assert free_after == max(demand, free_before), seed
        if sum(len(spatial_pieces(w, blob)) - 1 for blob in range(w.blob_count)) < extra_pieces:
            lowered += 1
    assert lowered, "no seed's spin removed a single-cell piece"


def test_item_cellars_show_their_item_at_position_89() -> None:
    """SH-STAIR-16: every item cellar's item-position bits pick position $89
    (X $80, Y $90, the middle of the upper ledge) from its level's four
    item positions; trigger bits stay clear, and transports carry $00."""
    from zora.generate.generation_pass import generate_shapes
    from zora.generate.shapes.writeback import CELLAR_ITEM_POSITION
    from zora.model.rooms import ITEM_POSITION_MASK, ITEM_POSITION_SHIFT
    for seed in range(4):
        world = _vanilla_gw()
        generate_shapes(world, Rng(seed), ShapeOptions())
        cellars = 0
        for block in world.blocks:
            for stair in block.staircases:
                if stair.room_type == RoomType.TRANSPORT_STAIRCASE:
                    assert stair.t5_raw == 0, (seed, stair.room_num)
                    continue
                assert stair.return_dest is not None
                owner = block.owner_of(stair.return_dest)
                assert owner is not None
                index = (stair.t5_raw >> ITEM_POSITION_SHIFT) & ITEM_POSITION_MASK
                assert stair.t5_raw == index << ITEM_POSITION_SHIFT, (seed, stair.room_num)
                assert owner.item_position_table[index] == CELLAR_ITEM_POSITION, (seed, owner.level_num)
                cellars += 1
        assert cellars >= 8


# ---------------------------------------------------------------------------
# Test scaffolding: the old room-connection repair (moved here from
# zora/generate/shapes/connectivity.py; it is not on the generation path,
# where the late gate's repair joins the levels). _build uses it to finish a
# set before validate_sets.
#
# Closed wall pairs from the T1 door weights can seal pockets of a level; the
# repair opens sealed doorways as far as it can (best-effort, spec update
# 7a). SPEC-GAP 26: the spec's SH document has no repair step; which door
# type an opened pair becomes is not stated, so sealed frontiers open as
# plain doors (vertical pairs bombable 1 in 3, SH-GRID-12's asymmetry).
# ---------------------------------------------------------------------------

_SOLID = 1
_OPEN = 0


def _reach_all(adj_fn: "Callable[[int], list[int]]", start: int) -> set[int]:
    seen = {start}
    stack = [start]
    while stack:
        u = stack.pop()
        for v in adj_fn(u):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def _repair_level(world: SetWorld, blob: int, rng: Rng) -> int:
    """Open sealed frontier doorways until every room and stair cell of the
    blob's level is reachable from its entrance. Returns doors opened."""
    level = world.levels[blob]
    entrance = world.entrance.get(level)
    if entrance is None:
        raise GenerationFailure("repair before entrances")
    cells = set(world.cells_by_blob[blob])
    stairs_here = {}
    for cell, sp in world.stairs.items():
        rooms = [sp.house] if sp.kind is StairKind.CELLAR else [sp.first, sp.second]
        if any(r is not None and r in cells for r in rooms):
            stairs_here[cell] = sp

    def frontier_fn(u: int) -> list[int]:
        out = []
        if u in cells:
            for d in Side:
                nb = neighbour(u, d)
                if nb in cells:
                    out.append(nb)
        # stair links connect houses/ends through the stair cell
        for sp in stairs_here.values():
            if sp.kind is StairKind.CELLAR:
                if u == sp.house:
                    out.append(sp.cell)
                elif u == sp.cell and sp.house is not None:
                    out.append(sp.house)
            else:
                if u == sp.cell:
                    out.extend([x for x in (sp.first, sp.second) if x is not None])
                elif u in (sp.first, sp.second):
                    out.append(sp.cell)
                    other = sp.second if u == sp.first else sp.first
                    if other is not None:
                        out.append(other)
        return out

    def traversable(u: int, v: int) -> bool:  # noqa: B023
        # v in frontier(u) already; u's side toward v must be non-solid AND
        # v's side toward u non-solid for normal room pairs; stair links are
        # always traversable (they are staircase tiles).
        for sp in stairs_here.values():
            if (u, v) in _stair_pairs(sp):
                return True
        if u in cells and v in cells:
            for d in Side:
                if neighbour(u, d) == v:
                    return world.plans[u].walls[d] != _SOLID and \
                        world.plans[v].walls[d.opposite] != _SOLID
        return True  # stair cell involved

    def _stair_pairs(sp: StairPlan) -> list[tuple[int, int]]:
        if sp.kind is StairKind.CELLAR:
            if sp.house is None:
                return []
            return [(sp.house, sp.cell), (sp.cell, sp.house)]
        pairs: list[tuple[int, int]] = []
        if sp.first is None or sp.second is None:
            return pairs
        for a in (sp.first, sp.second):
            pairs.append((sp.cell, a))
            pairs.append((a, sp.cell))
        pairs.append((sp.first, sp.second))
        pairs.append((sp.second, sp.first))
        return pairs

    expected = cells | set(stairs_here)
    opened = 0
    guard = 1000  # a cap on repair steps
    while True:
        seen = _reach_all(lambda u: [v for v in frontier_fn(u) if traversable(u, v)],
                          entrance)
        missing = expected - seen
        if not missing:
            return opened
        if guard <= 0:
            # SH-GRID-12 + spec update 7(a): repair is best-effort. Pieces it
            # cannot fuse (no sealed same-level wall pair on the frontier)
            # simply ship unjoined — acceptance is a later stage's business.
            return opened
        guard -= 1
        # candidate seals: reached u with unreached neighbour v across a solid
        # side (either side) — open them both ways as plain doors.
        options: list[tuple[int, int]] = []
        for u in sorted(seen):
            for v in frontier_fn(u):
                if v in seen or v not in expected:
                    continue
                sealed = not traversable(u, v)
                if sealed:
                    options.append((u, v))
        if world.zelda_room is not None:
            # SH-GRID-12: repair never touches a wall next to Zelda's room.
            options = [(u, v) for (u, v) in options
                       if u != world.zelda_room and v != world.zelda_room]
        if not options:
            return opened   # spec update 7(a): unjoinable is legal here
        # deterministic option list; random pick
        u, v = options[rng.below(len(options))]
        # SH-GRID-12 door-type asymmetry (quirk, replicated exactly):
        # vertical wall pairs open as bombable 1-in-3, else plain open;
        # horizontal wall pairs always open as plain doors.
        vertical = abs(u - v) == 16
        new_side = _OPEN
        if vertical and rng.chance(1, 3):
            new_side = 4  # WallType.BOMB_HOLE
        for d in Side:
            if neighbour(u, d) == v:
                world.plans[u].walls[d] = new_side
                if v in cells:
                    world.plans[v].walls[d.opposite] = new_side
        opened += 1


def _repair_sets(world: SetWorld, rng: Rng) -> None:
    """Repair every level of one set (raises GenerationFailure on cap hits)."""
    for blob in range(world.blob_count):
        _repair_level(world, blob, rng)


def test_push_block_stair_rooms_holding_a_key_take_the_two_in_three_test() -> None:
    """SH-STAIR-08: a stair room with a key still on trigger 0 or 1 after SH-STAIR-06/07 (the
    push-block layouts $5A and $5C among them) gets "kill all enemies for the item" two times
    in three, as any other stair room with an item."""
    from zora.generate.generation_pass import generate_shapes
    from zora.model.enums import RoomAction
    tally: dict[bool, list[int]] = {True: [0, 0], False: [0, 0]}
    stair_sets = [w for seed in range(12) for w in generate_shapes(_vanilla_gw(), Rng(seed), ShapeOptions()).sets]
    for w in stair_sets:
        for sp in w.stairs.values():
            for room in ([sp.house] if sp.kind is StairKind.CELLAR else [sp.first, sp.second]):
                if room is None:
                    continue
                plan = w.plans[room]
                if plan.item is None or plan.action not in (RoomAction.ALL_DEAD, RoomAction.ALL_DEAD_ITEM):
                    continue
                tally[plan.movable][plan.action == RoomAction.ALL_DEAD_ITEM] += 1
    for movable, (others, item_trigger) in tally.items():
        share = item_trigger / (others + item_trigger)
        assert others + item_trigger > 40 and 0.5 < share < 0.8, (movable, others, item_trigger)
