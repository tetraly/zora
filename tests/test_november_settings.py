"""The November tournament's settings (the 2026-10-17 export): "Most" Enemy HP (C09) and Boss HP
(C10) at every value (post-shapes-b8.md PS-HP-01, PS-HP-02, PS-HP-04, PS-HP-05), Set Ganon HP to 0
(B41, PS-HP-06), Permanent Sword Beam (B52, features-behavior.md FP-BEAM-01) and OHKO (B53,
FP-OHKO-01). The steps' rules on scripted draws, the group pass's Zol rule (PS-EGRP-01), the
values in generated seeds, the patches' bytes against PRG0, the seed's code left alone while they
are off, and in the emulator a beam fired short of full health, a death on the first hit and
Ganon's hit points when he appears; then the November string itself generates."""
from dataclasses import replace
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, ITEMS, OBJ_STATE, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID, Button, Emulator, Mode
from tests.test_assignment_emulator import ENTER_ROOM_MODE, IS_UPDATING_MODE, MONSTER_SLOTS
from zora.flags import codec
from zora.flags.fields import HitPointChange, ThreeState
from zora.flags.form import metadata
from zora.flags.support import Support, support
from zora.generate.generation_pass import STEPS
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.rng import ScriptedRng
from zora.generate.steps.change_enemy_hp import (
    BOSS_HP_TYPES,
    BOSS_MIRRORS,
    ENEMY_HP_TYPES,
    GANON,
    GANON_RETURN_HP,
    HP_SEED_DRAWS,
    HP_UP_BIT,
    EnemyHpResult,
    _step,
    change_boss_hp,
    change_most_enemy_hp,
    visiting_order,
    zero_ganon_hp,
)
from zora.generate.steps.shuffle_enemy_groups import COVERAGE, VIRE_COVERS_AT_ZOL_HP, _is_covered
from zora.model.canonical import canonical_bytes
from zora.model.enums import Enemy
from zora.rom import sword_and_harm as patches
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.game_config import GameConfig
from zora.rom.layout import GANON_HP_ADDRESS
from zora.rom.parse.rom_file import parse_rom

DEFAULT_SETTINGS = codec.decode(metadata()["defaultFlags"])      # CP-5
NOVEMBER = "oIbnRjuQKp1DXiYCys9LwvSpzqZbXk1pRmZzr"
SEEDS = (1, 2, 3)
ENEMY_TYPES = [Enemy(t) for t in ENEMY_HP_TYPES]
BOSS_TYPES = [Enemy(t) for t in BOSS_HP_TYPES]
PRG0_GANON_BYTE = 0xF0
ROPE_PRG0 = (1, 4)
# RAM (aldonunez Variables.inc)
OBJ_HP = 0x485
OBJ_INVINCIBILITY_TIMER = 0x4F0
HEART_VALUES = 0x66F                  # high nibble heart containers - 1, low nibble full hearts
HEART_PARTIAL = 0x670
INV_SWORD = ITEMS                     # 1 the wooden sword
SWORD_SHOT_SLOT = 0x0E
FULL_HEARTS_MASK = 0x0F
THREE_CONTAINERS_NONE_FULL = 0x20     # three containers, no full heart: short of full health
THREE_FULL_HEARTS = 0x22
HALF_FULL = 0x80
FULL_PARTIAL = 0xFF
INV_CLOCK = 0x66C
SETTLE_FRAMES = 10
GANON_SETTLE_FRAMES = 60              # Ganon's ObjHP is filled a few frames after he appears
CONTACT_MONSTERS = (Enemy.STALFOS, Enemy.GIBDO)
STROKE_FRAMES = 30
HIT_FRAMES = 300


def flags(options: dict[str, int] | None = None, toggles: dict[str, ThreeState] | None = None) -> str:
    return codec.encode(DEFAULT_SETTINGS.updated(options=options or {}, toggles=toggles or {}))


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


@cache
def _built(flag_string: str, seed: int) -> Built:
    return build(plan(flag_string, seed), remember_repo_base_rom())


@cache
def _rom(flag_string: str, seed: int) -> bytes:
    return finish(_built(flag_string, seed), remember_repo_base_rom())


def prg0_hp() -> dict[Enemy, int]:
    return parse_rom(remember_repo_base_rom()).enemies.hp


# --- the support matrix ---------------------------------------------------------------------------

def test_every_value_is_supported() -> None:
    """FL-SUP-02 and FL-SUP-03 (2026-10-17 export): C09 and C10 at all five values, B41, B52 and
    B53 off, on and "?"."""
    for field_id in ("C09", "C10"):
        for change in HitPointChange:
            assert support(DEFAULT_SETTINGS.updated(options={field_id: change}))[field_id] is Support.SUPPORTED
    for field_id in ("B41", "B52", "B53"):
        for state in ThreeState:
            assert support(DEFAULT_SETTINGS.updated(toggles={field_id: state}))[field_id] is Support.SUPPORTED


# --- the steps on scripted draws ------------------------------------------------------------------

def test_a_walk_of_up_to_four() -> None:
    """PS-HP-01 under C09 = 2: change |r mod 5|, so 4 is a move, up with bit 5."""
    assert _step(5, 4, ScriptedRng([HP_UP_BIT | 0x02])) == 9         # $22 = 34, mod 5 = 4, up
    assert _step(5, 4, ScriptedRng([0x09])) == 1                    # 9 mod 5 = 4, down
    assert _step(5, 4, ScriptedRng([HP_UP_BIT | 0x03])) == 5         # $23 = 35, mod 5 = 0: a spent draw
    assert _step(14, 4, ScriptedRng([HP_UP_BIT | 0x01])) == 15       # $21 = 33, up 3, clamped at 15


def test_the_gleeok_head_under_a_walk_of_four() -> None:
    """PS-HP-02 under C10 = 2: the head operand is ((s mod 9) - 4 + 6), 2..10."""
    for draw, head in ((0, 2), (8, 10), (9, 2), (4, 6)):
        state = EnemyHpResult.unchanged(parse_rom(remember_repo_base_rom()).enemies)
        before_head = visiting_order(BOSS_HP_TYPES).index(Enemy.GLEEOK_2) + 1
        still = HP_UP_BIT | 0x03                                     # $23 = 35, mod 5 = 0: no move
        rng = ScriptedRng([0] * HP_SEED_DRAWS + [still] * before_head + [draw]
                          + [still] * (len(BOSS_HP_TYPES) - before_head))
        change_boss_hp(state, HitPointChange.UP_TO_4, rng)
        assert state.gleeok_head == head


def test_enemy_values_all_zero(base: bytes) -> None:
    """PS-HP-04: every enemy value and both Rope operands 0; the boss values untouched."""
    state = EnemyHpResult.unchanged(parse_rom(base).enemies)
    change_most_enemy_hp(state, HitPointChange.ALL_ZERO, ScriptedRng([0] * HP_SEED_DRAWS))
    assert all(state.hp[enemy] == 0 for enemy in ENEMY_TYPES) and state.rope == (0, 0)
    assert all(state.hp[enemy] == prg0_hp()[enemy] for enemy in BOSS_TYPES)


def test_boss_values_all_zero_but_ganon(base: bytes) -> None:
    """PS-HP-05: every boss value but Ganon's 0, and the operands Ganon's aside; no draw but the
    pass's seed and discards."""
    state = EnemyHpResult.unchanged(parse_rom(base).enemies)
    change_boss_hp(state, HitPointChange.ALL_ZERO, ScriptedRng([0] * HP_SEED_DRAWS))
    assert all(state.hp[enemy] == 0 for enemy in BOSS_TYPES if enemy != GANON)
    assert state.hp[GANON] == prg0_hp()[GANON] == PRG0_GANON_BYTE >> 4
    assert state.mirrors == {name: 0 for enemy, name in BOSS_MIRRORS.items() if enemy != GANON}
    assert state.gleeok_head == 0


@pytest.mark.parametrize("change", [HitPointChange.NORMAL, HitPointChange.UP_TO_2, HitPointChange.ALL_ZERO])
def test_ganon_zero_after_any_boss_pass(base: bytes, change: HitPointChange) -> None:
    """PS-HP-06: after the boss pass, whatever C10 holds (C10 = 0 runs no boss pass), Ganon's
    value is 0 and the value he returns to $41."""
    state = EnemyHpResult.unchanged(parse_rom(base).enemies)
    if change is not HitPointChange.NORMAL:
        change_boss_hp(state, change, ScriptedRng([0] * (HP_SEED_DRAWS + len(BOSS_HP_TYPES) + 1)))
    zero_ganon_hp(state)
    assert state.hp[GANON] == 0 and state.ganon_return == GANON_RETURN_HP


def test_the_group_pass_reads_zol_after_the_hit_point_passes() -> None:
    """PS-EGRP-01: Vire covers a group only while Zol's value, as the hit-point pass left it, is 4
    or less; so the group pass runs after both hit-point passes and B41."""
    only_vire = {group: [Enemy.VIRE] for group in range(4)}
    assert _is_covered(only_vire, VIRE_COVERS_AT_ZOL_HP)
    assert not _is_covered(only_vire, VIRE_COVERS_AT_ZOL_HP + 1)
    assert Enemy.VIRE not in COVERAGE
    names = [step.name for step in STEPS]
    assert (names.index("change_most_enemy_hp") < names.index("change_boss_hp") < names.index("zero_ganon_hp")
            < names.index("shuffle_enemy_groups"))


# --- generated seeds ------------------------------------------------------------------------------

def test_enemy_walk_of_four_in_seeds(base: bytes) -> None:
    """PS-HP-01's C09 = 2 Check: all 50 values within PRG0's +-4, clamped; the Rope operands
    within their bases +-4; some move above 2; Zol's value is what the group pass read."""
    prg0, moves = prg0_hp(), set()
    for seed in SEEDS:
        built = _built(flags({"C09": HitPointChange.UP_TO_4}), seed)
        enemies = built.world.enemies
        for enemy in ENEMY_TYPES:
            assert max(0, prg0[enemy] - 4) <= enemies.hp[enemy] <= min(15, prg0[enemy] + 4), (seed, enemy)
            moves.add(abs(enemies.hp[enemy] - prg0[enemy]))
        assert enemies.rope_hp is not None
        assert all(max(0, rope - 4) <= value <= rope + 4 for value, rope in zip(enemies.rope_hp, ROPE_PRG0, strict=True))
    assert max(moves) > 2


def test_enemy_values_zero_in_seeds(base: bytes) -> None:
    for seed in SEEDS:
        rom = _rom(flags({"C09": HitPointChange.ALL_ZERO}), seed)
        enemies = parse_rom(rom).enemies
        assert all(enemies.hp[enemy] == 0 for enemy in ENEMY_TYPES) and enemies.rope_hp == (0, 0)


def test_boss_walk_of_four_in_seeds(base: bytes) -> None:
    """PS-HP-02's C10 = 2 Check: within PRG0's +-4, the mirrored operands their type's value, the
    head operand 2..10, types $4A and up untouched."""
    prg0 = prg0_hp()
    for seed in SEEDS:
        enemies = parse_rom(_rom(flags({"C10": HitPointChange.UP_TO_4}), seed)).enemies
        for enemy in BOSS_TYPES:
            assert max(0, prg0[enemy] - 4) <= enemies.hp[enemy] <= min(15, prg0[enemy] + 4), (seed, enemy)
        assert all(getattr(enemies, name) == enemies.hp[enemy] for enemy, name in BOSS_MIRRORS.items())
        assert 2 <= enemies.gleeok_head_hp <= 10
        assert all(enemies.hp[enemy] == prg0[enemy] for enemy in prg0 if enemy.value >= BOSS_HP_TYPES.stop)


def test_boss_values_zero_in_seeds(base: bytes) -> None:
    for seed in SEEDS:
        rom = _rom(flags({"C10": HitPointChange.ALL_ZERO}), seed)
        enemies = parse_rom(rom).enemies
        assert all(enemies.hp[enemy] == 0 for enemy in BOSS_TYPES if enemy != GANON)
        assert enemies.hp[GANON] == PRG0_GANON_BYTE >> 4 and rom[GANON_HP_ADDRESS] == PRG0_GANON_BYTE


@pytest.mark.parametrize("change", [HitPointChange.UP_TO_2, HitPointChange.ALL_ZERO])
def test_ganon_zero_in_seeds(base: bytes, change: HitPointChange) -> None:
    """PS-HP-06's Checks: with B41, Ganon's value 0 and his byte $41, with C10 = 1 and 3."""
    for seed in SEEDS:
        rom = _rom(flags({"C10": change}, {"B41": ThreeState.ON}), seed)
        enemies = parse_rom(rom).enemies
        assert enemies.hp[GANON] == 0 and rom[GANON_HP_ADDRESS] == GANON_RETURN_HP
        assert enemies.ganon_return_hp == GANON_RETURN_HP           # the round trip keeps it


@pytest.mark.parametrize("field_id", ["C09", "C10"])
def test_random_values_generate(base: bytes, field_id: str) -> None:
    for seed in SEEDS:
        assert _rom(flags({field_id: HitPointChange.RANDOM}), seed)


def test_the_patches_against_prg0(base: bytes) -> None:
    """FP-BEAM-01 and FP-OHKO-01: PRG0's bytes where the patches go (the off value keeps them),
    the patched bytes with each on, and B53's next byte $F9 either way."""
    assert base[patches.BEAM_HEALTH_TEST:patches.BEAM_HEALTH_TEST + 3] == patches.BEAM_PRG0
    assert patches.is_prg0_ring_halving(base[patches.RING_HALVING:patches.KEPT_OPERAND])
    plain, both = _rom(flags(), 1), _rom(flags(toggles={"B52": ThreeState.ON, "B53": ThreeState.ON}), 1)
    assert plain[patches.BEAM_HEALTH_TEST:patches.BEAM_HEALTH_TEST + 3] == patches.BEAM_PRG0
    assert patches.is_prg0_ring_halving(plain[patches.RING_HALVING:patches.KEPT_OPERAND])
    assert both[patches.BEAM_HEALTH_TEST:patches.BEAM_HEALTH_TEST + 3] == patches.BEAM_PATCH
    assert both[patches.RING_HALVING:patches.KEPT_OPERAND] == patches.ONE_HIT_PATCH
    assert plain[patches.KEPT_OPERAND] == both[patches.KEPT_OPERAND] == patches.KEPT_OPERAND_PRG0


def test_the_seed_code_is_unchanged_while_they_are_off() -> None:
    """The two new GameConfig fields write nothing while off (model/canonical.py), so seeds
    without them keep their codes; on, each changes the configuration's bytes."""
    plain = canonical_bytes(GameConfig())
    assert b"permanent_sword_beam" not in plain and b"one_hit_knock_out" not in plain
    assert canonical_bytes(replace(GameConfig(), permanent_sword_beam=True)) != plain
    assert canonical_bytes(replace(GameConfig(), one_hit_knock_out=True)) != plain


def test_the_steps_take_no_draw_off(base: bytes) -> None:
    """B52 and B53 take no draw, so the world is the same with them on as off."""
    plain = _built(flags(), 1).world
    patched = _built(flags(toggles={"B52": ThreeState.ON, "B53": ThreeState.ON}), 1).world
    assert canonical_bytes(plain) == canonical_bytes(patched)


# --- the emulator ---------------------------------------------------------------------------------

def _wait_for_play(emu: Emulator) -> None:
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)


def _start_mode(emu: Emulator, mode: int) -> None:
    emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = mode, 0, 0


def _enter_room(emu: Emulator, level: int, room: int) -> None:
    emu[CUR_LEVEL] = level
    _start_mode(emu, Mode.LOAD_LEVEL)
    _wait_for_play(emu)
    emu[ROOM_ID] = room
    _start_mode(emu, ENTER_ROOM_MODE)
    _wait_for_play(emu)


def fires_a_beam(flag_string: str, hearts: int) -> bool:
    """In a contact-monster room, the monsters frozen by the clock, a wooden-sword stroke at these
    HeartValues (the partial heart full): does a beam fly? (Link stands still first, as the
    flags2 beam test does; on the overworld right after the start, the stroke is not taken.)"""
    built = _built(flag_string, 1)
    level, room, _monster = _contact_room(built)
    emu = Emulator(finish(built, remember_repo_base_rom()))
    emu.new_game()
    _enter_room(emu, level, room)
    emu[INV_CLOCK], emu[INV_SWORD] = 1, 1
    emu[HEART_VALUES], emu[HEART_PARTIAL] = hearts, FULL_PARTIAL
    emu.run(SETTLE_FRAMES, Button.UP)
    emu.run(SETTLE_FRAMES)
    emu.press(Button.A, after=0)
    for _ in range(STROKE_FRAMES):
        emu.run(1)
        if emu[OBJ_STATE + SWORD_SHOT_SLOT]:
            return True
    return False


@pytest.mark.parametrize("beam", [False, True])
def test_beam_short_of_full_health(base: bytes, beam: bool) -> None:
    """FP-BEAM-01 in play: with B52 a stroke fires a beam short of full health; without it, not."""
    flag_string = flags(toggles={"B52": ThreeState.ON} if beam else {})
    assert fires_a_beam(flag_string, THREE_FULL_HEARTS)               # at full health, always
    assert fires_a_beam(flag_string, THREE_CONTAINERS_NONE_FULL) == beam


def _contact_room(built: Built) -> tuple[int, int, Enemy]:
    """A level room whose monsters harm Link by touch, a Stalfos room first: a Gibdo's touch takes two
    full hearts, more than the test's three full hearts can show a no-OHKO hit by (seed 1's first
    contact room has held a Gibdo since 114f280)."""
    return next((level.level_num, room_num, monster) for monster in CONTACT_MONSTERS for level in built.world.levels
                for room_num in level.room_nums if level.block.room(room_num).enemy == monster)


def hearts_after_the_first_hit(flag_string: str) -> tuple[int, int]:
    """Three full hearts, then a monster put onto Link until a hit lands: his full hearts and
    partial heart afterwards."""
    built = _built(flag_string, 1)
    level, room, monster = _contact_room(built)
    emu = Emulator(finish(built, remember_repo_base_rom()))
    emu.new_game()
    emu[HEART_VALUES], emu[HEART_PARTIAL] = THREE_FULL_HEARTS, HALF_FULL
    _enter_room(emu, level, room)
    slot = next(slot for slot in MONSTER_SLOTS if emu[OBJ_TYPE + slot] == monster)

    def hit() -> bool:
        emu[OBJ_X + slot], emu[OBJ_Y + slot] = emu[OBJ_X], emu[OBJ_Y]
        return emu[OBJ_INVINCIBILITY_TIMER] != 0 or emu[HEART_VALUES] & FULL_HEARTS_MASK != THREE_FULL_HEARTS & FULL_HEARTS_MASK

    assert emu.run_until(hit, limit=HIT_FRAMES) < HIT_FRAMES, "no hit landed"
    emu.run(2)
    return emu[HEART_VALUES] & FULL_HEARTS_MASK, emu[HEART_PARTIAL]


def test_one_hit_knock_out(base: bytes) -> None:
    """FP-OHKO-01 in play: from three full hearts, the first hit leaves nothing with B53 (Link
    dies) and at least two full hearts without it."""
    assert hearts_after_the_first_hit(flags(toggles={"B53": ThreeState.ON})) == (0, 0)
    full, _partial = hearts_after_the_first_hit(flags())
    assert full >= 2


def ganons_hit_points(flag_string: str) -> int:
    """Ganon's ObjHP once he is in his room."""
    built = _built(flag_string, 1)
    level_9 = built.world.levels[-1]
    room = level_9.boss_room
    assert level_9.block.room(room).enemy == GANON
    emu = Emulator(finish(built, remember_repo_base_rom()))
    emu.new_game()
    _enter_room(emu, level_9.level_num, room)
    emu.run_until(lambda: any(emu[OBJ_TYPE + slot] == GANON for slot in MONSTER_SLOTS), limit=HIT_FRAMES)
    emu.run(GANON_SETTLE_FRAMES)
    slot = next(slot for slot in MONSTER_SLOTS if emu[OBJ_TYPE + slot] == GANON)
    return emu[OBJ_HP + slot]


def test_ganons_hit_points_in_play(base: bytes) -> None:
    """PS-HP-06 in play: Ganon appears with 0 hit points under B41, PRG0's $F0 without (C10 = 0,
    so no walk moves him)."""
    assert ganons_hit_points(flags({"C10": HitPointChange.NORMAL}, {"B41": ThreeState.ON})) == 0
    assert ganons_hit_points(flags({"C10": HitPointChange.NORMAL})) == PRG0_GANON_BYTE


# --- the November string --------------------------------------------------------------------------

def test_the_november_string_generates(base: bytes) -> None:
    """The tournament string (B82 on, so it needs the private level encoder): its settings are all
    produced, and its seeds carry each of them (FP-BEAM-01 and FP-OHKO-01's Checks)."""
    from zora.rom import level_encoding
    if not level_encoding.is_available():
        pytest.skip("needs the private level encoder")
    for seed in SEEDS:
        built = _built(NOVEMBER, seed)
        rom = finish(built, base)
        enemies = built.world.enemies
        assert all(enemies.hp[enemy] == 0 for enemy in ENEMY_TYPES + BOSS_TYPES)
        assert rom[GANON_HP_ADDRESS] == GANON_RETURN_HP
        assert rom[patches.BEAM_HEALTH_TEST:patches.BEAM_HEALTH_TEST + 3] == patches.BEAM_PATCH
        assert rom[patches.RING_HALVING:patches.KEPT_OPERAND] == patches.ONE_HIT_PATCH
