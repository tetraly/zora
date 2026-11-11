"""Wizzrobes Shoot Wallmasters (ZORA flag wizzrobes_shoot_wallmasters, version 21; asm/flags2/wizzrobe-hand/):
the flag, its conflict, Shuffle Enemy Groups forced on, the deal that puts the Wizzrobes in a dungeon group with
the Wallmasters, and finished ROMs whose every Wizzrobe level holds the Wallmaster's open-hand tiles where the
patch draws the hand from. tests/test_wizzrobe_hand_emulator.py plays it."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags import codec, zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import OopsAllEnemies, ZoraFlags
from zora.generate.pipeline import extra_options, generate_rom, plan
from zora.generate.rng import Rng
from zora.generate.steps.group_banks import OVERWORLD
from zora.generate.steps.shuffle_enemy_groups import ENEMY_BANK_FIRST_TILE, WIZZROBE_GROUP, deal_enemies
from zora.model.enums import Enemy, EnemySpriteSet
from zora.model.game_world import GameWorld
from zora.model.sprites import TILE_BYTES, PatternBlock
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.flags2_patch_data import PATCHES
from zora.rom.parse.rom_file import parse_rom

E = Enemy
ON = ZoraFlags(wizzrobes_shoot_wallmasters=ThreeState.ON)
WIZZROBES = {E.RED_WIZZROBE, E.BLUE_WIZZROBE}
BANKS = {EnemySpriteSet.A: PatternBlock.UWSP127, EnemySpriteSet.B: PatternBlock.UWSP358,
         EnemySpriteSet.C: PatternBlock.UWSP469}
OPEN_HAND = 0xAC                         # PRG0's open-hand frame: $AC and $AE, two 8x16 sprites
HAND_TILES = 4
WALLMASTER_FRAMES = 146                  # the Wallmaster's frames in ObjAnimFrameHeap
FIRST_LIST_CODE = 0x62                   # a room's monster code from $62 names a mixed list
LIST_LENGTH = 8
SEEDS = range(3)


def with_groups(shuffled: bool) -> str:
    """The baseline (Shuffle Enemy Groups on) or the baseline with B42 off (which the flag turns on)."""
    if shuffled:
        return MVP_BASELINE_LEVEL_ENCODING_OFF
    flags = codec.decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    return codec.encode(flags.updated(toggles={"B42": ThreeState.OFF}))


def test_the_field_is_version_21_and_off_by_default() -> None:
    field = next(field for field in zora_flags.FIELDS if field.name == zora_flags.WIZZROBE_HAND_FIELD)
    assert field.version == 21
    assert ZoraFlags().wizzrobes_shoot_wallmasters is ThreeState.OFF
    assert zora_flags.decode(zora_flags.encode(ON)).wizzrobes_shoot_wallmasters is ThreeState.ON


def test_it_reaches_the_generation() -> None:
    assert extra_options(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 7, zora_flags.encode(ON))).wizzrobes_shoot_wallmasters
    assert not extra_options(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 7)).wizzrobes_shoot_wallmasters


def test_it_turns_shuffle_enemy_groups_on() -> None:
    off = codec.decode(with_groups(False))
    assert zora_flags.forced_z1r_values(ON) == [
        (zora_flags.SHUFFLE_ENEMY_GROUPS.id, ThreeState.ON, zora_flags.WIZZROBE_HAND_FORCED_NOTE)]
    assert zora_flags.forced_z1r_values(ZoraFlags()) == []
    chosen = plan(with_groups(False), 7, zora_flags.encode(ON))
    assert chosen.steps.shuffle_enemy_groups
    assert not plan(with_groups(False), 7).steps.shuffle_enemy_groups
    assert off.toggle(zora_flags.SHUFFLE_ENEMY_GROUPS) is ThreeState.OFF


def test_oops_all_wizzrobes_conflicts() -> None:
    z1r = codec.decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    both = ZoraFlags(wizzrobes_shoot_wallmasters=ThreeState.POSSIBLE, oops_all_enemies=OopsAllEnemies.WIZZROBES)
    assert zora_flags.wizzrobe_hand_conflicts(both, z1r) == [
        (zora_flags.WIZZROBE_HAND_CONFLICT, (zora_flags.WIZZROBE_HAND_FIELD, "oops_all_enemies"))]
    assert zora_flags.WIZZROBE_HAND_CONFLICT in zora_flags.validate(both, z1r)
    keese = ZoraFlags(wizzrobes_shoot_wallmasters=ThreeState.ON, oops_all_enemies=OopsAllEnemies.KEESE)
    assert zora_flags.wizzrobe_hand_conflicts(keese, z1r) == []


@pytest.mark.parametrize("overworld_group", [True, False], ids=["b43-on", "b43-off"])
@pytest.mark.parametrize("level_9_group", [False, True], ids=["b35-on", "b35-off"])
def test_the_deal_keeps_the_wallmaster_with_the_blue_wizzrobe(overworld_group: bool, level_9_group: bool) -> None:
    for seed in range(60):
        deal = deal_enemies(Rng(seed), 1, overworld_group, level_9_group, wallmasters_with_wizzrobes=True)
        homes = {enemy: group for group, members in deal.groups.items() for enemy in members}
        assert homes[E.WALLMASTER] == homes[E.BLUE_WIZZROBE] != OVERWORLD
        assert E.RED_LANMOLA not in deal.groups[homes[E.WALLMASTER]]
        if level_9_group:
            assert homes[E.WALLMASTER] == WIZZROBE_GROUP


def test_the_patch_writes_the_wallmaster_damage_for_both_shots() -> None:
    damage = dict(PATCHES["wizzrobe-hand"])[0x07322]
    assert bytes(damage) == bytes([0x80, 0x80])        # ObjTypeToDamagePoints for $58 and $59


@cache
def finished(shuffled: bool, seed: int) -> tuple[bytes, GameWorld]:
    text = zora_flags.encode(ON)
    rom = generate_rom(with_groups(shuffled), seed, remember_repo_base_rom(), zora_flag_string=text).rom
    return rom, parse_rom(rom)


def level_enemies(world: GameWorld, level_num: int) -> set[Enemy]:
    level = next(level for level in world.levels if level.level_num == level_num)
    found: set[Enemy] = set()
    for room in level.rooms:
        code = int(room.enemy_info.enemy)
        if code >= FIRST_LIST_CODE:
            start = world.enemies.mixed_group_offsets[code]
            found |= {Enemy(value) for value in world.enemies.mixed_enemy_data[start:start + LIST_LENGTH]}
        else:
            found.add(Enemy(code))
    return found


@needs_base_rom
@pytest.mark.slow
@pytest.mark.parametrize("shuffled", [True, False], ids=["b42-on", "b42-off"])
def test_every_wizzrobe_level_holds_the_hand(shuffled: bool) -> None:
    """The hand is drawn from the tile ObjAnimFrameHeap's Wallmaster frame names: in each level with a
    Wizzrobe, the level's enemy bank holds PRG0's open hand there."""
    vanilla = parse_rom(remember_repo_base_rom())
    hand = vanilla.sprites.read_tiles(PatternBlock.UWSP127, (OPEN_HAND - ENEMY_BANK_FIRST_TILE) * TILE_BYTES,
                                      HAND_TILES)
    wizzrobe_levels = 0
    for seed in SEEDS:
        _rom, world = finished(shuffled, seed)
        tile = world.enemies.frame_bytes(WALLMASTER_FRAMES, 1)[0]
        assert tile == OPEN_HAND
        for level in world.levels:
            if level.level_num and level_enemies(world, level.level_num) & WIZZROBES:
                wizzrobe_levels += 1
                tiles = world.sprites.read_tiles(BANKS[level.enemy_sprite_set],
                                                 (tile - ENEMY_BANK_FIRST_TILE) * TILE_BYTES, HAND_TILES)
                assert tiles == hand, (seed, level.level_num)
    assert wizzrobe_levels >= len(SEEDS)
