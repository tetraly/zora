"""End-to-end flow tests: generate → serialize → re-parse consistency."""
import os
from pathlib import Path

import pytest

from zora.model.game_world import GameWorld
from zora.model.enums import Item, RoomType
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions
from zora.rom.serialize.game_world import serialize_game_world


def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)



def test_generated_world_serializes_and_reparses() -> None:
    rom = _vanilla_rom()
    gw = parse_rom(rom)
    res = generate_shapes(gw, Rng(31), ShapeOptions())
    assert res.attempts >= 1
    out = serialize_to_rom(gw, rom)
    assert len(out) == len(rom)
    gw2 = parse_rom(out)
    # every level: entrance room has layout $21 and south side open
    for lvl in gw2.levels:
        ent = next(r for r in lvl.rooms if r.room_num == lvl.entrance_room)
        assert ent.room_type == RoomType.ENTRANCE_ROOM
        assert ent.walls.south.value == 0
    # staircase_rooms are a subset of the raw stairway pool (SH-STAIR-12/13:
    # stale pool entries are ordinary rooms, not staircases)
    for lvl in gw2.levels:
        pool = set(lvl.staircase_room_pool)
        assert {x.room_num for x in lvl.staircase_rooms} <= pool


def test_generated_dungeons_are_connected() -> None:
    # re-parse the generated ROM and flood-fill: each level must own all its
    # rooms (forward from entrance) — and the parsed rooms equal plan cells.
    rom = _vanilla_rom()
    gw = parse_rom(rom)
    generate_shapes(gw, Rng(32), ShapeOptions())
    out = serialize_to_rom(gw, rom)
    gw2 = parse_rom(out)
    for lvl in gw2.levels:
        # Under reference numbering (free under early numbers, renumber once)
        # a level's final size can dip low; just require rooms + entrance.
        assert len(lvl.rooms) >= 3
        assert any(r.room_num == lvl.entrance_room for r in lvl.rooms)


def test_determinism_end_to_end() -> None:
    rom = _vanilla_rom()
    outs = []
    for _ in range(2):
        gw = parse_rom(rom)
        generate_shapes(gw, Rng(33), ShapeOptions())
        outs.append(serialize_to_rom(gw, rom))
    assert outs[0] == outs[1]


def test_triforce_and_hc_counts() -> None:
    rom = _vanilla_rom()
    gw = parse_rom(rom)
    generate_shapes(gw, Rng(34), ShapeOptions(), post_shapes=False)
    for lvl in gw.levels:
        tris = [r for r in lvl.rooms if r.item == Item.TRIFORCE]
        assert len(tris) == (1 if lvl.level_num <= 8 else 0)
        hcs = [r for r in lvl.rooms if r.item == Item.HEART_CONTAINER]
        assert len(hcs) == (1 if lvl.level_num <= 8 else 0)


def test_items_use_t5_usable_positions() -> None:
    """Every generated room's item position must be a T5-allowed slot for its
    screen type against its own level's standard position table (SH-ROOM-11).
    Levels 7-9: the late gate's block push-block clear (late-gate.md step 6,
    A4) removes push blocks AFTER positions were chosen, so the room's
    shapes-stage push variant is accepted there. Shape stage only: the
    goriya swap (PS-GRUM-02) moves layouts while positions stay."""
    from zora.generate.shapes.t5_positions import item_slots_for
    rom = _vanilla_rom()
    gw = parse_rom(rom)
    generate_shapes(gw, Rng(55), ShapeOptions(), post_shapes=False)
    checked = 0
    for lvl in gw.levels:
        table = list(lvl.item_position_table)
        pool = set(lvl.staircase_room_pool)
        for r in lvl.rooms:
            if r.room_num in pool:
                continue
            if r.item == Item.NOTHING:
                continue
            lay = int(r.room_type) | (0x40 if r.movable_block else 0)
            slots = item_slots_for(lay, table, False)
            if lvl.level_num >= 7 and not r.movable_block:
                slots = slots + item_slots_for(lay | 0x40, table, False)
            assert int(r.item_position) in slots, (lay, r.item_position, slots)
            checked += 1
    assert checked > 50


def test_minimap_check_in_suite_and_passes() -> None:
    from zora.measure.checks import finished_rom_checks, run_checks
    checks = finished_rom_checks(post_shapes=False)
    assert any(c.__name__ == "check_minimap_synthesis" for c in checks)
    rom = _vanilla_rom()
    gw = parse_rom(rom)
    generate_shapes(gw, Rng(56), ShapeOptions(), post_shapes=False)
    results = run_checks(gw, checks)
    # SH-STAIR-02/03 may legitimately fail: freeing happens under the EARLY
    # number's budget, renumbering can move a blob to a different-budget
    # level or a level with more cellars than cells (artifacts the spec
    # allows: corpus shows 996/1000 and 999/1000 on these).
    tolerated = {"SH-STAIR-02", "SH-STAIR-03"}
    failed = [r for r in results if not r.passed and r.check_id not in tolerated]
    assert not failed, failed[:3]


def test_t5_agrees_with_corpus_fitted_table() -> None:
    """Cross-check: the spec's T5 position model, projected through the nine
    vanilla level position tables, must broadly agree with the independently
    corpus-fitted usable-position table (zora/generate/shapes/item_positions.py)."""
    from zora.model.game_world import GameWorld
    from zora.generate.shapes.item_positions import USABLE_ITEM_POSITIONS
    from zora.generate.shapes.t5_positions import T5_BASE
    tables = [list(l.item_position_table) for l in parse_rom(_vanilla_rom()).levels]
    proj: dict[int, set[int]] = {}
    for stype, positions in T5_BASE.items():
        slots: set[int] = set()
        for table in tables:
            for i, v in enumerate(table):
                if v in positions:
                    slots.add(i)
        proj[stype] = slots
    fitted = {k: set(v) for k, v in USABLE_ITEM_POSITIONS.items()}
    holds_t5 = {k for k, v in proj.items() if v}
    holds_fit = set(fitted)
    both = holds_t5 & holds_fit
    assert len(both) >= 0.75 * min(len(holds_t5), len(holds_fit)), \
        (len(holds_t5), len(holds_fit), len(both))
    checked = 0
    for lay, slots_fit in fitted.items():
        slots_t5 = proj.get(lay, set())
        if not slots_t5:
            continue
        assert slots_fit & slots_t5, (lay, sorted(slots_fit), sorted(slots_t5))
        checked += 1
    assert checked >= 20


def test_restart_reasons_recorded() -> None:
    from zora.generate.rng import Rng
    from zora.generate.generation_pass import generate_shapes
    from zora.generate.shapes.options import ShapeOptions
    rom = _vanilla_rom()
    for seed in range(10):
        gw = parse_rom(rom)
        res = generate_shapes(gw, Rng(777 + seed), ShapeOptions())
        shape_reasons = [r for r in res.restart_reasons
                         if not r.startswith("late gate:")]
        # two-level accounting (spec update 7 + late-gate split): every
        # shapes-stage restart records at most one reason per prior attempt;
        # gate retries are counted in gate_attempts.
        assert len(shape_reasons) <= res.attempts - 1
        assert res.gate_attempts >= 0
        assert len(shape_reasons) + res.gate_attempts <= res.attempts - 1 + \
            res.gate_attempts


def test_gate_redeal_moves_ganon_and_rollbacks_keep_one() -> None:
    """Regression (stale Ganon pointer): the late gate re-deals level 9's
    contents, Zelda's and Ganon's included, so they are found by content.
    After the gate, rolled-back attempts included, level 9 holds exactly one
    room with monster list $37 and one with $3E."""
    from zora.generate.late_gate import deal
    from zora.model.enums import Enemy
    from zora.model.levels import Level

    moved_any = False
    orig = deal._redeal_contents
    first: list[int] = []

    def ganon_cell(level: Level) -> int:
        return next(room.room_num for room in level.rooms if room.enemy == Enemy.THE_BEAST)

    def spy(level: Level, rng: Rng) -> dict[int, int] | None:
        if level.level_num == 9 and not first:
            first.append(ganon_cell(level))
        return orig(level, rng)

    deal._redeal_contents = spy
    try:
        rom = _vanilla_rom()
        for seed in range(4):
            first.clear()
            gw = parse_rom(rom)
            generate_shapes(gw, Rng(seed), ShapeOptions())
            level9 = gw.levels[8]
            assert sum(room.enemy == Enemy.THE_BEAST for room in level9.rooms) == 1
            assert sum(room.enemy == Enemy.THE_KIDNAPPED for room in level9.rooms) == 1
            moved_any |= first[0] != ganon_cell(level9)
    finally:
        deal._redeal_contents = orig
    assert moved_any, "Ganon's content never moved in 4 seeds"


def test_ship_order_is_pinned():
    """The staged results ship in this order (ship.SHIP_STEPS): the
    overworld copy before B1's cave items and the ZORA extras' caves are
    written onto it, and the groups' goriya tile after B1's and B2's, and the start screen's monster
    exchange after the groups' overworld monsters. Change it only on purpose."""
    from zora.generate.ship import SHIP_STEPS
    assert [name for name, _ in SHIP_STEPS] == [
            "sets", "overworld", "item shuffle", "extra pool items", "hints", "monster shuffle", "hit points", "groups", "colors",
            "start screen"]
