"""The owner's level-9 Vire cap (tetraly/zora#14): when Vires are the only bomb droppers in level 9,
their hit points are at most 4, so a hit of the magical sword or a bomb kills one outright and it
can drop bombs (one harmed but not killed splits into red Keese, which drop nothing).

The spec's seed: CP-5 with "Most" Enemy HP at up to 4 (C09 = 2), seed 16, whose level 9 holds no
bomb dropper but Vires and whose walk left them at 6."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.steps.change_enemy_hp import BOMB_DROPPERS, VIRE_MOST_HP, cap_level_9_vire_hp, level_monsters
from zora.model.enums import Enemy
from zora.model.game_world import GameWorld
from zora.model.levels import Level
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = needs_base_rom
WIDER_WALK = encode(decode("8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A").updated(options={"C09": 2}))
ONLY_VIRES_SEED = 16
WALKED_HP = 6


@cache
def built(seed: int) -> Built:
    return build(plan(WIDER_WALK, seed), remember_repo_base_rom())


def level_9(world: GameWorld) -> Level:
    return next(level for level in world.levels if level.level_num == 9)


def test_only_vires_in_level_9_are_capped_in_the_finished_rom() -> None:
    seed_built = built(ONLY_VIRES_SEED)
    shipped = parse_rom(finish(seed_built, remember_repo_base_rom()))
    assert level_monsters(shipped, level_9(shipped)) & BOMB_DROPPERS == {Enemy.VIRE}
    assert shipped.enemies.hp[Enemy.VIRE] == VIRE_MOST_HP


def test_the_cap_lowers_only_a_vire_above_4() -> None:
    world = built(ONLY_VIRES_SEED).world
    hp = world.enemies.hp
    assert hp[Enemy.VIRE] == VIRE_MOST_HP and not cap_level_9_vire_hp(world)
    hp[Enemy.VIRE] = WALKED_HP
    others = {enemy: value for enemy, value in hp.items() if enemy != Enemy.VIRE}
    assert cap_level_9_vire_hp(world) and hp[Enemy.VIRE] == VIRE_MOST_HP
    assert {enemy: value for enemy, value in hp.items() if enemy != Enemy.VIRE} == others


@pytest.mark.parametrize("dropper", [Enemy.BLUE_DARKNUT, Enemy.GIBDO])
def test_another_bomb_dropper_in_level_9_leaves_the_vires_alone(dropper: Enemy) -> None:
    world = parse_rom(finish(built(ONLY_VIRES_SEED), remember_repo_base_rom()))
    vires = level_monsters(world, level_9(world))
    other = next(room for room in level_9(world).rooms if Enemy.NOTHING < room.enemy < Enemy.SINGLE_DODONGO
                 and room.enemy != Enemy.VIRE)
    other.enemy = dropper
    assert Enemy.VIRE in level_monsters(world, level_9(world)) and Enemy.VIRE in vires
    world.enemies.hp[Enemy.VIRE] = WALKED_HP
    assert not cap_level_9_vire_hp(world) and world.enemies.hp[Enemy.VIRE] == WALKED_HP
