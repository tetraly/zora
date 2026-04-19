"""
Unit tests for dungeon palette randomization.

The algorithm (in dungeon_randomizer.py) works as follows:
  1. Discard 3 RNG values.
  2. Read 8 dungeons' palettes into slots 0-7.
  3. Build slot 8: copy of slot 0 with low-nibble 0x0C → 0x04 remap.
  4. Build slots 9-22: one per PALETTE_OPTIONS template. Each starts from a
     copy of slot 0, writes template values to specific positions, then applies
     an exact-value remap (12→tpl[1], 28→tpl[2], 44→tpl[3]) over the whole
     palette. The exact-value remap runs after the template write, so it can
     overwrite positions that were just set by the template.
  5. Fisher-Yates shuffle all 23 slot indices.
  6. Write shuffled[1..9] into game_world.levels[0..8].

Key facts that drive the test design:
  - The PPU header (palette_raw[0:3]) and the end byte (palette_raw[35]) are
    always preserved unchanged.
  - palette_raw positions 0-7 and 16-27 come entirely from slot 0 (dungeon 1
    vanilla), possibly modified by the exact-value remap. They are NOT
    guaranteed to equal the pre-randomization values.
  - The nibble remap (0x0C→0x04) is only applied to slot 8; template slots
    (9-22) can produce fade_palette_raw bytes with low nibble 0x0C if the
    template or dungeon-0 data contains them.
"""
from flags.flags_generated import Flags, Tristate
from zora.dungeon_randomizer import (
    PALETTE1_END,
    PALETTE1_START,
    PALETTE2_LEN,
    PALETTE_OPTIONS,
    TOTAL_SLOTS,
    _exact_remap,
    randomize_dungeon_palettes,
)
from zora.game_config import GameConfig, resolve_game_config
from zora.parser import parse_game_world
from zora.rng import SeededRng


SEED = 12345


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config() -> GameConfig:
    flags = Flags(shuffle_major_shop_items=Tristate.ON, randomize_dungeon_palettes=Tristate.ON)
    return resolve_game_config(flags, SeededRng(SEED))

def _run(bins, seed=SEED):
    gw = parse_game_world(bins)
    config = _config()
    randomize_dungeon_palettes(gw, config, SeededRng(seed))
    return gw


def _palette1(lvl):
    """32 bytes of basic palette data (skipping the 3-byte PPU header)."""
    return lvl.palette_raw[PALETTE1_START:PALETTE1_END]


def _simulate_slot_assignment(seed):
    """
    Re-run only the RNG-consuming parts of the algorithm (discard 3, shuffle)
    to determine which slot index was assigned to each output level.
    Returns a list of 9 slot indices (for levels 1-9).
    """
    rng = SeededRng(seed)
    rng.random()
    rng.random()
    rng.random()

    indices = list(range(TOTAL_SLOTS))
    rng.shuffle(indices)
    return [indices[1 + i] for i in range(9)]


def _build_expected_p1(slot_idx, d0_p1):
    """
    Re-derive what palette1 should look like for a given slot, given the
    dungeon-0 palette1 data. Mirrors the algorithm in dungeon_randomizer.py.
    """
    if slot_idx < 8:
        # Vanilla dungeon slot: palette1 is just that dungeon's original data.
        # We don't have all 8 originals here, so return None to skip.
        return None
    if slot_idx == 8:
        from zora.dungeon_randomizer import _nibble_remap
        return [_nibble_remap(v) for v in d0_p1]
    # Template slot
    tpl = PALETTE_OPTIONS[slot_idx - 9]
    p1 = list(d0_p1)
    for i, v in enumerate(tpl):
        p1[8 + i] = v
    p1[28] = tpl[0]
    p1[29] = tpl[1]
    p1[30] = tpl[2]
    p1[31] = tpl[3]
    # Exact-value remap over the whole palette (runs after template write)
    for i in range(len(p1)):
        sub = _exact_remap(d0_p1[i], tpl)
        if sub is not None:
            p1[i] = sub
    return p1


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ppu_header_and_end_byte_preserved(bins):
    """palette_raw PPU header (bytes 0-2) and end byte (byte 35) must never change."""
    gw_before = parse_game_world(bins)
    gw_after  = _run(bins)
    for lvl_before, lvl_after in zip(
        sorted(gw_before.levels, key=lambda lvl: lvl.level_num),
        sorted(gw_after.levels,  key=lambda lvl: lvl.level_num),
        strict=True,
    ):
        assert lvl_after.palette_raw[:3] == lvl_before.palette_raw[:3], (
            f"level {lvl_before.level_num}: PPU header changed"
        )
        assert lvl_after.palette_raw[35] == lvl_before.palette_raw[35], (
            f"level {lvl_before.level_num}: end byte changed"
        )


def test_palette_raw_length_preserved(bins):
    """palette_raw must remain the same length for every level."""
    gw_before = parse_game_world(bins)
    gw_after  = _run(bins)
    for lvl_b, lvl_a in zip(
        sorted(gw_before.levels, key=lambda lvl: lvl.level_num),
        sorted(gw_after.levels,  key=lambda lvl: lvl.level_num),
        strict=True,
    ):
        assert len(lvl_a.palette_raw) == len(lvl_b.palette_raw), (
            f"level {lvl_b.level_num}: palette_raw length changed"
        )


def test_fade_palette_raw_length_preserved(bins):
    """fade_palette_raw must remain 96 bytes for every level."""
    gw = _run(bins)
    for lvl in gw.levels:
        assert len(lvl.fade_palette_raw) == PALETTE2_LEN, (
            f"level {lvl.level_num}: fade_palette_raw length = {len(lvl.fade_palette_raw)}, expected {PALETTE2_LEN}"
        )


def test_template_slot_palette1_matches_algorithm(bins):
    """For levels assigned a template slot, palette1 must exactly match the
    values produced by the algorithm: template write followed by exact-value remap."""
    gw_orig = parse_game_world(bins)
    d0_p1 = list(_palette1(gw_orig.levels[0]))

    gw = _run(bins)
    slot_assignments = _simulate_slot_assignment(SEED)

    for out_level_idx, slot_idx in enumerate(slot_assignments):
        if slot_idx < 9:
            continue  # vanilla or nibble-remap slots tested separately
        level_num = out_level_idx + 1
        lvl = next(lv for lv in gw.levels if lv.level_num == level_num)
        expected = _build_expected_p1(slot_idx, d0_p1)
        got = list(_palette1(lvl))
        assert got == expected, (
            f"level {level_num} (slot {slot_idx}, template {slot_idx - 9}): "
            f"palette1 mismatch.\n  got:      {got}\n  expected: {expected}"
        )


def test_nibble_remap_slot_palette1_matches_algorithm(bins):
    """For levels assigned slot 8 (nibble-remap of dungeon 0), palette1 must
    have every 0x0C low-nibble replaced with 0x04."""
    from zora.dungeon_randomizer import _nibble_remap
    gw_orig = parse_game_world(bins)
    d0_p1 = list(_palette1(gw_orig.levels[0]))

    gw = _run(bins)
    slot_assignments = _simulate_slot_assignment(SEED)

    for out_level_idx, slot_idx in enumerate(slot_assignments):
        if slot_idx != 8:
            continue
        level_num = out_level_idx + 1
        lvl = next(lv for lv in gw.levels if lv.level_num == level_num)
        expected = [_nibble_remap(v) for v in d0_p1]
        got = list(_palette1(lvl))
        assert got == expected, (
            f"level {level_num} (slot 8, nibble-remap): "
            f"palette1 mismatch.\n  got:      {got}\n  expected: {expected}"
        )


def test_nibble_remap_slot_no_0c_low_nibble_in_palette1(bins):
    """For levels assigned slot 8, no byte in palette1 may have low nibble 0x0C."""
    gw = _run(bins)
    slot_assignments = _simulate_slot_assignment(SEED)
    for out_level_idx, slot_idx in enumerate(slot_assignments):
        if slot_idx != 8:
            continue
        level_num = out_level_idx + 1
        lvl = next(lv for lv in gw.levels if lv.level_num == level_num)
        for i, b in enumerate(_palette1(lvl)):
            assert (b & 0x0F) != 0x0C, (
                f"level {level_num} (slot 8): palette1[{i}] = {b:#04x} still has low nibble 0x0C"
            )


def test_all_levels_palettes_changed(bins):
    """Every level's palette_raw must differ from the original after randomization
    (the shuffle always picks a different slot for each output level)."""
    gw_before = parse_game_world(bins)
    gw_after  = _run(bins)
    orig = {lvl.level_num: lvl.palette_raw for lvl in gw_before.levels}
    for lvl in gw_after.levels:
        assert lvl.palette_raw != orig[lvl.level_num], (
            f"level {lvl.level_num}: palette_raw unchanged after randomization"
        )


def test_randomize_dungeon_palettes_deterministic(bins):
    """Same seed must produce identical palette_raw and fade_palette_raw for all levels."""
    gw1 = _run(bins, SEED)
    gw2 = _run(bins, SEED)
    for l1, l2 in zip(
        sorted(gw1.levels, key=lambda lvl: lvl.level_num),
        sorted(gw2.levels, key=lambda lvl: lvl.level_num),
        strict=True,
    ):
        assert l1.palette_raw == l2.palette_raw, (
            f"level {l1.level_num}: palette_raw not deterministic"
        )
        assert l1.fade_palette_raw == l2.fade_palette_raw, (
            f"level {l1.level_num}: fade_palette_raw not deterministic"
        )


def test_different_seeds_produce_different_palettes(bins):
    """Two different seeds must not produce identical palettes for all levels."""
    gw1 = _run(bins, SEED)
    gw2 = _run(bins, SEED + 1)
    levels1 = sorted(gw1.levels, key=lambda lvl: lvl.level_num)
    levels2 = sorted(gw2.levels, key=lambda lvl: lvl.level_num)
    all_same = all(l1.palette_raw == l2.palette_raw for l1, l2 in zip(levels1, levels2, strict=True))
    assert not all_same, "Different seeds produced identical palettes for all levels"


def test_nine_levels_written(bins):
    """Exactly 9 levels must exist and all must have been written."""
    gw = _run(bins)
    assert len(gw.levels) == 9
    level_nums = sorted(lvl.level_num for lvl in gw.levels)
    assert level_nums == list(range(1, 10))
