"""End-of-generation validation: SH-GRID-09 / SH-GRID-10.

Every room of a level (ordinary + its stair cells) must be mutually
reachable with the entrance using same-level non-solid sides (each side is
traversed by its own room's door state — the engine's directional rule) plus
staircase links. Level 9's Ganon room must be reachable (SH-GRID-10).

Spec update 7: connectivity is NOT a restart site at this stage (the five
sites are entrances with no candidate, stair budget >9 / endpoint tries
exhausted, variant-position search exhausted, boss search exhausted, major
item placement). Levels with unreachable rooms are counted in
world.unreachable_levels for reporting.
"""
from zora.generate.shapes.world import SetWorld, StairKind, StairPlan
from zora.model.enums import Side
from zora.model.room_grid import neighbour


def _blob_stairs(world: SetWorld, blob: int) -> dict[int, StairPlan]:
    """Stairs whose rooms belong to this blob (a stair cell is shared by the
    whole set, so filter by room ownership)."""
    cells = set(world.cells_by_blob[blob])
    out = {}
    for cell, sp in world.stairs.items():
        rooms = [sp.house] if sp.kind is StairKind.CELLAR else [sp.first, sp.second]
        if any(r is not None and r in cells for r in rooms):
            out[cell] = sp
    return out


def _forward_edges(world: SetWorld, blob: int) -> dict[int, list[int]]:
    cells = set(world.cells_by_blob[blob])
    stairs = _blob_stairs(world, blob)
    stair_cells = set(stairs)
    adj: dict[int, list[int]] = {c: [] for c in cells | stair_cells}
    for c in sorted(cells):
        for d in Side:
            nb = neighbour(c, d)
            if nb in cells and world.plans[c].walls[d] != 1:
                adj[c].append(nb)
    for sp in sorted(stairs.values(), key=lambda s: s.cell):
        if sp.kind is StairKind.CELLAR:
            if sp.house is not None:
                adj[sp.cell].append(sp.house)
                adj[sp.house].append(sp.cell)
        else:
            if sp.first is not None and sp.second is not None:
                adj[sp.cell].append(sp.first)
                adj[sp.first].append(sp.cell)
                adj[sp.cell].append(sp.second)
                adj[sp.second].append(sp.cell)
    return adj


def _reverse_edges(world: SetWorld, blob: int) -> dict[int, list[int]]:
    cells = set(world.cells_by_blob[blob])
    stairs = _blob_stairs(world, blob)
    stair_cells = set(stairs)
    adj: dict[int, list[int]] = {c: [] for c in cells | stair_cells}
    for c in sorted(cells):
        for d in Side:
            nb = neighbour(c, d)
            if nb in cells and world.plans[nb].walls[d.opposite] != 1:
                # nb -> c is traversable; record reverse-reach edge c <- nb
                adj[c].append(nb)
    # staircase links are undirected
    for sp in sorted(stairs.values(), key=lambda s: s.cell):
        if sp.kind is StairKind.CELLAR and sp.house is not None:
            adj[sp.cell].append(sp.house)
            adj[sp.house].append(sp.cell)
        elif sp.first is not None and sp.second is not None:
            for r in (sp.first, sp.second):
                adj[sp.cell].append(r)
                adj[r].append(sp.cell)
    return adj


def _reach(adj: dict[int, list[int]], start: int) -> set[int]:
    seen = {start}
    stack = [start]
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def validate_sets(worlds: list[SetWorld]) -> None:
    """Post-build invariant guard for the shapes stage.

    Update 9 removed its only real job (width rejection lived here once;
    nothing rejects on width now, and connectivity moved into the late
    room-deal gate). Kept as a bug guard so callers/tests have a place to
    assert structural sanity."""
    for w in worlds:
        for blob in range(w.blob_count):
            level = w.levels[blob]
            if w.cells_by_blob[blob] and level not in w.entrance:
                raise AssertionError(f"L{level}: built without an entrance")
