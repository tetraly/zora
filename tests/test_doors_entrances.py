"""Tests for doors (SH-DOOR) and entrances (SH-ENT)."""
from zora.model import room_grid
from zora.generate.rng import Rng
from zora.model.room_grid import neighbour
from zora.generate.shapes.doors import place_doors
from zora.generate.shapes.entrances import place_entrances
from zora.generate.shapes.gridgen import grow_set
from zora.generate.shapes.numbering import number_with_frees
from zora.generate.shapes.options import ShapeOptions
from zora.generate.errors import GenerationFailure
from zora.generate.shapes.world import GRID_ROWS, SetWorld
from zora.model.enums import Side



def _build(seed: int, six: bool) -> SetWorld:
    """Build one set, restarting on GenerationFailure like the flow layer."""
    opts = ShapeOptions()
    rng = Rng(seed)
    for _ in range(500):
        w = SetWorld(base_level=0 if six else 6, blob_count=6 if six else 3)
        try:
            grow_set(w, rng, six)
            number_with_frees(w, rng, opts)
            place_doors(w, rng, opts)
            place_entrances(w, rng, opts)
            return w
        except GenerationFailure:
            continue
    raise AssertionError("no successful build in 500 attempts")


def test_pairs_synced_or_oneway_shutter() -> None:
    for seed in range(20):
        for six in (True, False):
            w = _build(seed, six)
            for cell in range(128):
                blob = w.blob_of[cell]
                if blob < 0:
                    continue
                for d in (Side.EAST, Side.SOUTH):
                    nb = neighbour(cell, d)
                    if nb is None or w.blob_of[nb] != blob:
                        continue
                    a, b = w.plans[cell].walls[d], w.plans[nb].walls[d.opposite]
                    assert a == b or {a, b} == {0, 7}, (seed, cell, d, a, b)


def test_crosslevel_and_edge_sides_solid() -> None:
    for seed in range(20):
        w = _build(seed, True)
        entrance_cells = set(w.entrance.values())
        for cell in range(128):
            blob = w.blob_of[cell]
            if blob < 0:
                continue
            for d in Side:
                nb = neighbour(cell, d)
                if nb is None or w.blob_of[nb] != blob:
                    if cell in entrance_cells and d == Side.SOUTH:
                        assert w.plans[cell].walls[d] == 0  # SH-ENT-03
                        continue
                    assert w.plans[cell].walls[d] == 1, (seed, cell, d)


def test_entrances() -> None:
    for seed in range(20):
        w = _build(seed, True)
        assert len(w.entrance) == 6
        for level, cell in sorted(w.entrance.items()):
            assert room_grid.row(cell) == GRID_ROWS - 1
            assert w.plans[cell].walls[Side.SOUTH] == 0
            assert w.plans[cell].layout == 0x21
            assert w.plans[cell].item == 0x03
            assert w.plans[cell].action == 1
        # exactly blob_count entrance cells with layout $21
        n21 = sum(1 for c in range(128)
                  if w.blob_of[c] >= 0 and w.plans[c].layout == 0x21)
        assert n21 == 6


def test_level9_entrance_shape() -> None:
    for seed in range(20):
        w = _build(seed, False)
        e = w.entrance[9]
        assert room_grid.row(e) == GRID_ROWS - 1
        assert w.blob_of[e - 16] == next(b for b in range(3)
                                        if w.levels[b] == 9)


def test_numbering_smallest_first() -> None:
    # SH-NUM-01 with sort on (default): level order matches size order.
    for seed in range(15):
        w = _build(seed, True)
        by_level = sorted(w.levels.items(), key=lambda kv: kv[1])
        sizes = [len(w.cells_by_blob[b]) for b, _lv in by_level]
        assert sizes == sorted(sizes)


def test_determinism() -> None:
    a = _build(42, True)
    b = _build(42, True)
    assert a.blob_of == b.blob_of
    assert [(l, e) for l, e in sorted(a.entrance.items())] == \
           [(l, e) for l, e in sorted(b.entrance.items())]


def test_door_pass_palette_selectors():
    """SH-DOOR-01 (U23): each level cell's inner selector is the base
    ROM's bits there ORed with 2; unowned cells are left undecided."""
    from zora.generate.shapes.doors import write_palette_selectors
    w = SetWorld(base_level=0, blob_count=6)
    grow_set(w, Rng(3), True)
    w.base_inner_palettes = [cell % 4 for cell in range(len(w.blob_of))]
    write_palette_selectors(w)
    for cell, blob in enumerate(w.blob_of):
        expected = (cell % 4) | 2 if blob >= 0 else None
        assert w.plans[cell].inner_palette == expected, cell
