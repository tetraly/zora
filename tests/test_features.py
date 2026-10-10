"""Finished-ROM tests for B10 DATA items (docs/spec/features-behavior.md)."""
import pytest

from zora.rom.base_rom import verify_base_rom
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.generate.rng import Rng
from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave, MoneyMakingGameCave
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions


@pytest.fixture
def base_rom():
    return load_rom(verify_base_rom())


def _generated_world(base_rom: bytes, seed: int = 12345) -> "GameWorld":
    gw = parse_rom(base_rom)
    generate_shapes(gw, Rng(seed), ShapeOptions(), feature_data=True, seed=seed)
    return gw


def test_fp_lock_02_credits_pointers_differ_from_vanilla(base_rom):
    gw = _generated_world(base_rom)
    assert gw.credits_pointers[:3] != (0xAD33, 0xAD4D, 0xAD59)
    # Line 15 still points to PRG0's copyright record (docs/reports/ending-text.md).
    assert gw.credits_pointers[3] == 0xAD72


def test_fp_mmg_01_amounts_in_ranges(base_rom):
    gw = _generated_world(base_rom)
    mmg = gw.overworld.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
    assert mmg is not None
    assert 1 <= mmg.lose_small <= 20
    assert 30 <= mmg.lose_large <= 50
    assert 1 <= mmg.lose_small_2 <= 20
    assert 10 <= mmg.win_small <= 30
    assert 25 <= mmg.win_large <= 75


def test_fp_sword_01_heart_requirements_in_ranges(base_rom):
    gw = _generated_world(base_rom)
    ws = gw.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    ms = gw.overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    assert ws is not None and ms is not None
    assert 4 <= ws.heart_requirement <= 6
    assert 10 <= ms.heart_requirement <= 14


def test_fp_bomb_01_price_and_capacity_in_ranges(base_rom):
    gw = _generated_world(base_rom)
    bu = gw.overworld.bomb_upgrade
    assert 75 <= bu.cost <= 125
    assert 2 <= bu.count <= 6


def test_fp_trif_01_refusal_text_states_eight(base_rom):
    gw = _generated_world(base_rom)
    assert "EIGHT" in gw.level9_refusal_text


def test_fp_title_01_seed_number_on_title(base_rom):
    gw = _generated_world(base_rom, seed=999)
    assert gw.title_seed_number == 999
    assert gw.title_version_line


def test_fp_level_01_dash_tile(base_rom):
    gw = _generated_world(base_rom)
    assert gw.level_dash_tile == 0x2F


def test_fp_person_01_cave_animations_in_range(base_rom):
    gw = _generated_world(base_rom)
    assert len(gw.cave_person_animations) == 17
    assert all(0x58 <= b <= 0x5B for b in gw.cave_person_animations)


def test_fp_constants(base_rom):
    gw = _generated_world(base_rom)
    assert gw.reset_controller1 == 0xFA   # FP-RESET-01
    assert gw.text_speed_value == 0x02    # FP-TEXT-01
    assert gw.low_health_beep_value == 0x00  # FP-BEEP-01
    assert gw.dmc_level_value == 0x40     # FP-FIX-01
    assert gw.q2_room_trigger_value == 0x01  # FP-Q2R-01


def test_fp_start_01_starting_vector(base_rom):
    gw = _generated_world(base_rom)
    vector = bytes(24) + bytes([0x22, 0xFF]) + bytes(11) + bytes([0x08]) + bytes(2)
    assert gw.starting_items_new_file == vector
    assert gw.starting_items_second_quest == vector
    assert gw.continue_hearts_operand == 0x02
