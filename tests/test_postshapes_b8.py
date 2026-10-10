"""B8 (post-shapes-b8.md): the overworld monster re-deal, the hit points and
level 9's records; and B4.1's overworld fills (post-shapes-b4.md S7)."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.game_config import GameConfig, HintMode
from zora_measure.checkpoints.overworld_monsters_and_hp import (
    boss_hp_walk, enemy_hp_walk, level9_records_match, owm_no_barred_placement, owm_non_candidates_kept,
)
from zora.model.enums import Enemy
from zora.model.game_world import GameWorld
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions
from zora.generate.steps.change_enemy_hp import (
    BOSS_HP_TYPES, BOSS_MIRRORS, ENEMY_HP_TYPES, HP_UP_BIT, EnemyHpResult, _step, visiting_order, change_boss_hp,
)

# Generated hint text is written as generated seeds write it (the extended bank), not into the
# vanilla bank, which ZORA's wording outgrows.
GENERATED_HINTS = GameConfig(hint_mode=HintMode.CONSTERNATION)


def _vanilla() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    path = Path(env) if env else BASE_ROM_PATH
    if not path.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(path)
    return load_rom(path)


@pytest.fixture(scope="module")
def finished() -> list[GameWorld]:
    rom = _vanilla()
    worlds = []
    for seed in range(4):
        gw = parse_rom(rom)
        generate_shapes(gw, Rng(seed), ShapeOptions())
        worlds.append(parse_rom(serialize_to_rom(gw, rom, config=GENERATED_HINTS)))
    return worlds


def test_hp_step_rule() -> None:
    """PS-HP-01: change |r mod 3|, up when bit 5 is set, clamped 0..15."""
    assert _step(5, ScriptedRng([HP_UP_BIT | 0x02])) == 6     # $22 mod 3 = 1, up
    assert _step(5, ScriptedRng([HP_UP_BIT | 0x01])) == 5     # $21 mod 3 = 0: a spent draw
    assert _step(1, ScriptedRng([0x02])) == 0                 # down 2, clamped at 0
    assert _step(15, ScriptedRng([HP_UP_BIT | 0x05])) == 15   # up 1, clamped at 15


def test_finished_output(finished: list[GameWorld]) -> None:
    for gw in finished:
        assert owm_non_candidates_kept(gw)
        assert owm_no_barred_placement(gw)
        assert enemy_hp_walk(gw)["within 2"]
        assert all(boss_hp_walk(gw).values())
        records = level9_records_match(gw)
        assert records["records"] and records["L1-8 boss records vanilla"]


def test_hp_visiting_order() -> None:
    """PS-HP-01/02: each odd object type, then the even type sharing its byte."""
    assert [t.value for t in visiting_order(ENEMY_HP_TYPES)][:4] == [1, 0, 3, 2]
    assert [t.value for t in visiting_order(ENEMY_HP_TYPES)][-2:] == [49, 48]
    assert [t.value for t in visiting_order(BOSS_HP_TYPES)][:2] == [51, 50]
    assert [t.value for t in visiting_order(BOSS_HP_TYPES)][-2:] == [73, 72]


def test_hp_mirror_pairing_in_prg0() -> None:
    """PS-HP-02: in PRG0 the four mirrored operands equal their object
    types' values times 16, which fixes the pairing of type to nibble."""
    enemies = parse_rom(_vanilla()).enemies
    assert {enemy.value: getattr(enemies, name) for enemy, name in BOSS_MIRRORS.items()} == \
        {enemy.value: enemies.hp[enemy] for enemy in BOSS_MIRRORS}
    assert [getattr(enemies, name) * 16 for name in BOSS_MIRRORS.values()] == [0xA0, 0xF0, 0x20, 0x20]


def test_gleeok_head_draw_position() -> None:
    """PS-HP-02: the head draw comes after type $43's write, before $42's."""
    enemies = parse_rom(_vanilla()).enemies
    state = EnemyHpResult.unchanged(enemies)
    seed = [0, 0, 0]
    unchanged = HP_UP_BIT | 0x01            # $21 mod 3 = 0: no move
    before_head = visiting_order(BOSS_HP_TYPES).index(Enemy.GLEEOK_2) + 1
    rng = ScriptedRng(seed + [unchanged] * before_head + [4]
                      + [unchanged] * (len(BOSS_HP_TYPES) - before_head))
    change_boss_hp(state, rng)
    # misplaced, the 4 would move a value down by 1 ($04 mod 3 = 1, bit 5 clear)
    assert state.gleeok_head == 4 + 4 and state.hp == enemies.hp


def test_hp_untouched_beyond_type_49(finished: list[GameWorld]) -> None:
    """PS-HP-02: types $4A and up (byte 37, 0x1FB83) keep PRG0's values."""
    base = parse_rom(_vanilla()).enemies.hp
    for gw in finished:
        assert all(gw.enemies.hp[e] == base[e] for e in base if e.value >= BOSS_HP_TYPES.stop)
