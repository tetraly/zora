"""Post-shapes batch B2 (post-shapes-b2.md): the swap rules' quirks, the
bank draws, and the batch's invariants on serialized output."""
import os
from collections import Counter
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.model.levels import GANON_LIST, ZELDA_LIST
from zora.model.enums import BossSpriteSet
from zora.model.game_world import GameWorld
from zora.model.rooms import RoomPlace
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.shapes.enemies import monster_barred
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions
from zora.generate.steps.shuffle_bosses import BOSS_TIER_WEIGHT, draw_boss_tier
from zora.generate.steps.shuffle_dungeon_monsters import (
    GANON_BAD_LAYOUTS, ZELDA_BAD_LAYOUTS, _Room, is_swap_allowed,
)
from zora.generate.steps.monster_lists import MonsterShuffleResult
from zora.generate.steps.shuffle_monsters_between_levels import deal_enemy_banks
from zora.generate.shapes.tables import GLEEOK4_EXTRA_BAD, GLEEOK_BAD_LAYOUTS



def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)


def _room(layout: int, push: bool = False, cellar_exit: bool = False) -> _Room:
    return _Room(RoomPlace(0, layout), layout, push, cellar_exit)


# --- rule quirks -------------------------------------------------------------------

def test_either_side_rule_checks_both_rooms() -> None:
    """PS-MONRD-02: if either value is X, BOTH rooms must be safe for X,
    even the room X is leaving."""
    plain = 0x05
    ganon_barred = min(GANON_BAD_LAYOUTS)
    assert is_swap_allowed(GANON_LIST, plain, _room(0x28), _room(0x02))
    assert not is_swap_allowed(GANON_LIST, plain, _room(ganon_barred), _room(0x02))
    assert not is_swap_allowed(plain, GANON_LIST, _room(ganon_barred), _room(0x28))


def test_zelda_rules() -> None:
    """Zelda: barred layouts, the push bit, and no arrival in a cellar exit
    (her own position included)."""
    plain = 0x05
    assert is_swap_allowed(ZELDA_LIST, plain, _room(0x27), _room(0x02))
    assert not is_swap_allowed(ZELDA_LIST, plain, _room(0x27), _room(min(ZELDA_BAD_LAYOUTS)))
    assert not is_swap_allowed(ZELDA_LIST, plain, _room(0x27), _room(0x02, push=True))
    assert not is_swap_allowed(ZELDA_LIST, plain, _room(0x27), _room(0x02, cellar_exit=True))
    assert is_swap_allowed(ZELDA_LIST, plain, _room(0x27, cellar_exit=True), _room(0x02))
    exit_room = _room(0x02, cellar_exit=True)
    assert not is_swap_allowed(ZELDA_LIST, ZELDA_LIST, exit_room, exit_room)


def test_lanmola_rule_ignores_the_monster_bit_but_not_count_bits() -> None:
    """PS-MONRD-02: the Lanmola rule tests the whole monster byte (58/59),
    so a flagged count-zero $3A is caught and a count-indexed Lanmola is
    not."""
    barred = 0x01                               # a Lanmola-barred layout
    assert not is_swap_allowed(0x3A, 0x05, _room(0x02), _room(barred))
    assert not is_swap_allowed(0x13A, 0x05, _room(0x02), _room(barred))
    assert is_swap_allowed(0x7A, 0x05, _room(0x02), _room(barred))


def test_gleeok_rooms_checked_against_arriving_value() -> None:
    """The four-head list applies to a room whenever the value arriving in
    it has low six bits 5 (QUESTIONS #58.2)."""
    two_heads, four_heads = 0x103, 0x105
    extra_only = min(GLEEOK4_EXTRA_BAD - GLEEOK_BAD_LAYOUTS)
    assert is_swap_allowed(two_heads, 0x06, _room(0x02), _room(extra_only))
    assert not is_swap_allowed(four_heads, 0x06, _room(0x02), _room(extra_only))
    # a non-Gleeok partner with low six bits 5 arrives in the Gleeok's room
    assert not is_swap_allowed(two_heads, 0x05, _room(extra_only), _room(0x02))


def test_boss_tier_draw_weights() -> None:
    """PS-BOSS-01: tiers 0 and 1 each w/(2w+1), tier 2 1/(2w+1)."""
    for level, weight in BOSS_TIER_WEIGHT.items():
        tiers = Counter(draw_boss_tier(level, ScriptedRng([r])) for r in range(2 * weight + 1))
        assert tiers == {0: weight, 1: weight, 2: 1}


def test_enemy_bank_deal_keeps_the_multiset() -> None:
    """PS-MONLV-01: {0,0,0,1,1,2,2,x,y} dealt over levels 1-9."""
    for script in ([0] * 3 + [2, 1] + [0] * 9, [0] * 3 + [0, 0] + [8, 7, 6, 5, 4, 3, 2, 1, 0]):
        state = MonsterShuffleResult()
        deal_enemy_banks(state, ScriptedRng(script))
        counts = Counter(state.enemy_tiers.values())
        assert sorted(state.enemy_tiers) == list(range(1, 10))
        assert counts[0] >= 3 and counts[1] >= 2 and counts[2] >= 2


# --- finished-ROM invariants -----------------------------------------------------

def _finished(rom: bytes, seed: int) -> GameWorld:
    gw = parse_rom(rom)
    generate_shapes(gw, Rng(seed), ShapeOptions())
    return parse_rom(serialize_to_rom(gw, rom))


def test_b2_invariants_on_output() -> None:
    """What survives to the finished ROM. The bosses' identities and the
    pools' values do not: B4's group passes redraw both (post-shapes-b4.md
    PS-EGRP-03, PS-BGRP-03)."""
    rom = _vanilla_rom()
    for seed in range(3):
        gw = _finished(rom, 700 + seed)
        assert gw.levels[8].boss_sprite_set == BossSpriteSet.C       # PS-BOSS-06
        for level in gw.levels:
            for room in level.rooms:
                value = room.monster_value
                layout = room.layout_code & 0x3F
                assert not monster_barred(value, layout), (seed, hex(value), hex(layout))
                if value in (0x102, 0x103, 0x104, 0x105):          # Gleeok
                    assert layout not in GLEEOK_BAD_LAYOUTS and not room.movable_block
                if value == GANON_LIST:
                    assert layout not in GANON_BAD_LAYOUTS
                    assert room.item.value == 0x0E and room.is_dark        # $8E
                if value == ZELDA_LIST:
                    assert layout not in ZELDA_BAD_LAYOUTS and not room.movable_block
