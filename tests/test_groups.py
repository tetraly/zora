"""B4 group passes and B5's repack (post-shapes-b4.md, -b5.md PS-SPR)."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.model.enums import Enemy
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng
from zora.generate.generation_pass import generate_shapes
from zora.generate.steps.randomize_boss_groups import (
    BLOCK_FREE_TILES, BOSSES, is_boss_pick_barred, deal_bosses,
)
from zora.generate.steps.shuffle_enemy_groups import (
    GROUP_START_TOTALS, GROUP_TILE_LIMIT, OVERWORLD_BARRED, SEED_GROUPS, counted_cost, deal_enemies,
    pack_enemies, redraw_excess_zols,
)
from zora.generate.steps.group_banks import OVERWORLD, Staged
from zora.generate.shapes.options import ShapeOptions

E = Enemy


def _vanilla() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)


def test_enemy_deal_invariants() -> None:
    for seed in range(40):
        deal = deal_enemies(Rng(seed), zol_hp=1)
        dealt = [e for g in deal.groups.values() for e in g if e != deal.seed]
        assert sorted(dealt) == sorted(e for e in deal.order if e != deal.seed)
        for g, members in deal.groups.items():
            total = GROUP_START_TOTALS[g] + sum(counted_cost(e) for e in members)
            assert total <= GROUP_TILE_LIMIT
            assert not {E.WALLMASTER, E.RED_LANMOLA} <= set(members)
            if g == OVERWORLD:
                assert not OVERWORLD_BARRED & set(members)
        assert all(deal.seed in deal.groups[g] for g in SEED_GROUPS)
        assert deal.seed not in deal.groups[0]


def test_boss_deal_fits_and_splits_the_big_two() -> None:
    for seed in range(40):
        deal = deal_bosses(Rng(seed))
        assert deal.blocks[OVERWORLD][0] == deal.special
        for block, bosses in deal.blocks.items():
            assert sum(BOSSES[b].cost for b in bosses) <= BLOCK_FREE_TILES[block]
        homes = {b: block for block, bosses in deal.blocks.items() for b in bosses}
        assert homes[E.TRIPLE_DODONGO] in (0, 1) and homes[E.GLEEOK_2] in (0, 1)
        assert homes[E.TRIPLE_DODONGO] != homes[E.GLEEOK_2]
        assert set(deal.blocks[2]) <= {E.SINGLE_DIGDOGGER, E.PATRA_1}


def test_boss_layout_bars() -> None:
    assert is_boss_pick_barred(E.GLEEOK_2, 0x02, has_push_block=True)
    assert is_boss_pick_barred(E.GLEEOK_4, 19, has_push_block=False)
    assert not is_boss_pick_barred(E.GLEEOK_3, 19, has_push_block=False)
    assert is_boss_pick_barred(E.RED_GOHMA, 14, has_push_block=False)
    assert not is_boss_pick_barred(E.AQUAMENTUS, 14, has_push_block=True)


def test_enemy_packing_fixed_slots() -> None:
    gw = parse_rom(_vanilla())
    deal = deal_enemies(Rng(7), zol_hp=1)
    placed = pack_enemies(gw, deal, Staged())
    for g in SEED_GROUPS:
        assert placed[g][deal.seed][-1] == 191
    for g, slots in placed.items():
        if E.WALLMASTER in slots:
            assert slots[E.WALLMASTER] == [172, 173, 174, 175]
        used = [t for tiles in slots.values() for t in tiles]
        assert len(used) == len(set(used))


def test_finished_rom_group_bytes() -> None:
    """PS-SPR-02's Gleeok bytes, Wallmaster's frames and the open-mouth
    operand on shipped output."""
    rom = _vanilla()
    for seed in range(3):
        gw = parse_rom(rom)
        generate_shapes(gw, Rng(500 + seed), ShapeOptions())
        out = parse_rom(serialize_to_rom(gw, rom))
        enemies = out.enemies
        assert (enemies.gleeok_head_sprite_ptr_a, enemies.gleeok_head_sprite_ptr_b,
                enemies.frame_bytes(199, 1)[0]) == (0xDA, 0xDC, 0xDE)
        assert enemies.frame_bytes(146, 2) == [0xAC, 0x9C]
        assert enemies.aquamentus_tile_layout_table is not None
        assert enemies.aquamentus_sprite_ptr == enemies.aquamentus_tile_layout_table[3] - 2


def test_zol_limit_counts_every_replaced_byte() -> None:
    """PS-EGRP-04 (S6): replaced bytes count 1, a Zol one more; only a
    count above 10 redraws the Zols, and never to a Zol."""
    zol, stalfos = E.ZOL.value, E.STALFOS.value
    five = bytearray([zol] * 5)
    redraw_excess_zols(five, 5, [E.STALFOS], Rng(1))
    assert five == bytearray([zol] * 5)                  # count 10 stands
    three_of_eight = bytearray([zol] * 3 + [stalfos] * 5)
    redraw_excess_zols(three_of_eight, 8, [E.GIBDO], Rng(1))
    assert zol not in three_of_eight                     # count 11: redrawn
    assert three_of_eight[:3] == bytearray([E.GIBDO.value] * 3)
