"""Tests for the shape step (SH-GRID-01..07)."""
from collections import Counter

from zora.model import room_grid
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.shapes.gridgen import _six_level_start, _sixth_level_first_start, grow_set
from zora.generate.shapes.world import GRID_COLS, GRID_ROWS, SetWorld


def _grow(seed: int, six: bool) -> SetWorld:
    w = SetWorld(base_level=0 if six else 6, blob_count=6 if six else 3)
    grow_set(w, Rng(seed), six)
    return w




def test_growth_steps_floor_level_sizes() -> None:
    # SH-GRID-06/14: every level gets its start plus 13 (six-level) / 18
    # (three-level) single-room growth steps before the fill, each placing
    # one cell unless its band is capped at eight columns and every probe
    # misses; nothing reclaims leftovers after the fill (SH-GRID-13).
    for seed in range(12):
        for six in (True, False):
            w = _grow(seed, six)
            floor = 14 if six else 19
            assert min(len(c) for c in w.cells_by_blob) >= floor, (seed, six)


def test_starts_on_bottom_row() -> None:
    # Every blob's earliest-assigned cell... simpler invariant: every blob
    # touches the bottom row (its start).
    for seed in range(8):
        for six in (True, False):
            w = _grow(seed, six)
            for blob in range(w.blob_count):
                assert any(room_grid.row(c) == GRID_ROWS - 1 for c in w.cells_by_blob[blob])


def test_six_level_starts_clamped() -> None:
    # SH-GRID-04 clamps apply to the START cell; bands may widen later
    # during fill, so full-blob span isn't asserted.
    for seed in (3, 7, 11):
        w = _grow(seed, True)
        assert room_grid.column(w.cells_by_blob[0][0]) <= 7
        assert room_grid.column(w.cells_by_blob[5][0]) >= 8


def test_bands_roughly_eight_columns() -> None:
    # SH-GRID-04: footprints fit the 8-column band for the overwhelming
    # majority of blobs; widening during final fill is the documented escape.
    total = 0
    wide = 0
    for seed in range(30):
        w = _grow(seed, True)
        for blob in range(w.blob_count):
            cols = [room_grid.column(c) for c in w.cells_by_blob[blob]]
            total += 1
            if max(cols) - min(cols) + 1 > 8:
                wide += 1
    assert wide * 10 < total  # <10% of footprints exceed the band width


def test_deterministic() -> None:
    a = _grow(77, True)
    b = _grow(77, True)
    assert a.blob_of == b.blob_of
    c = _grow(78, True)
    assert c.blob_of != a.blob_of


def test_three_level_first_blob_top_cell_taken() -> None:
    w = _grow(2, False)
    # SH-GRID-03: first level takes the cell above its start too.
    bottom = [c for c in w.cells_by_blob[0] if room_grid.row(c) == GRID_ROWS - 1]
    assert bottom
    start_col = room_grid.column(bottom[0])
    assert room_grid.room_number(GRID_ROWS - 2, start_col) in w.cells_by_blob[0]


def test_band_rules_sh_grid_16() -> None:
    # SH-GRID-16: six-level first band starts at 0 and last ends at 15;
    # three-level third band is the right half (8-15), or 10-15 when the
    # first band was re-drawn (minimum 3-6, eight wide). Widening only
    # ever adds columns to a band narrower than eight.
    redrawn = 0
    for seed in range(40):
        w = _grow(seed, True)
        assert w.bands[0][0] == 0 and w.bands[0][1] <= 7
        assert w.bands[5][1] == 15 and w.bands[5][0] >= 8
        t = _grow(seed, False)
        if t.bands[0][0] > 0:
            redrawn += 1
            assert 3 <= t.bands[0][0] <= 6 and t.bands[0][1] == t.bands[0][0] + 7
            assert t.bands[2][0] >= 8 and t.bands[2][1] == 15
        else:
            assert t.bands[0] == [0, 7] and t.bands[2] == [8, 15]
    assert 0 < redrawn < 40


def test_six_level_start_columns() -> None:
    """SH-GRID-03/16 (U20/U21): level 6's first draw gives 12/13/14 at 4/25
    and 15 at 13/25; its re-draws 12/13/14 at 1/5 and 15 at 2/5."""
    first = Counter(_sixth_level_first_start(ScriptedRng([r])) for r in range(25))
    assert first == {12: 4, 13: 4, 14: 4, 15: 13}
    redraw = Counter(_six_level_start(5, ScriptedRng([r])) for r in range(5))
    assert redraw == {12: 1, 13: 1, 14: 1, 15: 2}
    assert [_six_level_start(1, ScriptedRng([r])) for r in range(5)] == [2, 3, 4, 5, 6]
