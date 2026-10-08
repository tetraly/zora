"""Tests for boss and enemy placement (SH-BOSS, SH-ENEMY)."""
import os
from pathlib import Path

import pytest

from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.generate.rng import Rng
from zora.generate.shapes.bosses import boss_barred
from zora.generate.errors import GenerationFailure
from zora.generate.context import GenerationResult
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.tables import BOSS_COUNTS, LEVEL_BOSS_POOL, POOL_EXCLUSIONS


def _vanilla_gw() -> GameWorld:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("no vanilla ROM")
    verify_base_rom(cand)
    return parse_rom(load_rom(cand))



def _gen(seed: int) -> GenerationResult:
    return generate_shapes(_vanilla_gw(), Rng(seed), ShapeOptions(), post_shapes=False)


def test_boss_counts() -> None:
    res = _gen(1)
    counts: dict[int, int] = {}
    for w in res.sets:
        for cell in w.all_cells_sorted():
            lv = w.level_of_cell(cell)
            enemy = w.plans[cell].enemy
            if lv is not None and enemy is not None:
                if enemy in set(sum(LEVEL_BOSS_POOL.values(), ())):
                    counts[lv] = counts.get(lv, 0) + 1
    for level, want in BOSS_COUNTS.items():
        assert counts.get(level, 0) == want, (level, counts.get(level), want)


def test_first_boss_has_heart_container_levels_1_8() -> None:
    res = _gen(2)
    w = res.sets[0]
    for level, cell in sorted(w.boss_room.items()):
        assert level <= 6
        assert w.plans[cell].item == 0x1A


def test_boss_layout_bans() -> None:
    assert boss_barred(0x0E, False, 0x31)      # dodongo hates chute $0E
    assert boss_barred(0x08, True, 0x45)       # gleeok hates push blocks
    assert boss_barred(0x17, False, 0x45)      # 4-head gleeok hates $17
    assert not boss_barred(0x17, False, 0x44)  # 3-head ok there
    assert not boss_barred(0x02, False, 0x3D)  # aqua anywhere ok


def test_enemy_pools_exclude_bosses_and_people() -> None:
    res = _gen(3)
    assert res.pools is not None
    for bank, pool in sorted(res.pools.pools.items()):
        assert pool
        for value in pool:
            code = (value & 0x3F) | (0x40 if value & 0x100 else 0)
            assert code not in POOL_EXCLUSIONS, (bank, hex(value))


def test_every_room_has_enemy_except_exempt() -> None:
    res = _gen(4)
    for w in res.sets:
        for cell in w.all_cells_sorted():
            plan = w.plans[cell]
            if plan.layout in (0x21, 0x29, 0x20):
                continue
            if cell == w.entrance.get(w.level_of_cell(cell) or -1):
                continue
            assert plan.enemy is not None, hex(cell)


def test_determinism() -> None:
    a = _gen(8)
    b = _gen(8)
    assert [( [x for x in w.blob_of] ) for w in a.sets] == \
           [([x for x in w.blob_of]) for w in b.sets]
    for wa, wb in zip(a.sets, b.sets):
        for cell in range(128):
            assert wa.plans[cell].enemy == wb.plans[cell].enemy
            assert wa.plans[cell].layout == wb.plans[cell].layout
