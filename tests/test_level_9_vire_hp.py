"""The owner's level-9 Vire cap (tetraly/zora#14): when Vires are the only bomb droppers a player
reaches in level 9 without bombs, their hit points are at most 4, so a hit of the magical sword or a
bomb kills one outright and it can drop bombs (one harmed but not killed splits into red Keese,
which drop nothing).

The spec's seed: CP-5 with "Most" Enemy HP at up to 4 (C09 = 2), seed 16, whose level 9 holds no
bomb dropper but Vires and whose walk left them at 6."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.steps.change_enemy_hp import (
    VIRE_MOST_HP,
    MixedLists,
    bomb_droppers,
    cap_level_9_vire_hp,
    level_9_bomb_droppers_without_bombs,
    level_monsters,
    rooms_reached_without_bombs,
)
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
    world = seed_built.world
    assert level_9_bomb_droppers_without_bombs(world.levels, MixedLists.of(world), world.enemy_drop_classes) \
        == {Enemy.VIRE}
    shipped = parse_rom(finish(seed_built, remember_repo_base_rom()))
    assert shipped.enemies.hp[Enemy.VIRE] == VIRE_MOST_HP


def test_the_cap_lowers_only_a_vire_above_4() -> None:
    world = built(ONLY_VIRES_SEED).world
    hp = world.enemies.hp
    assert hp[Enemy.VIRE] == VIRE_MOST_HP and not cap_level_9_vire_hp(world)
    hp[Enemy.VIRE] = WALKED_HP
    others = {enemy: value for enemy, value in hp.items() if enemy != Enemy.VIRE}
    assert cap_level_9_vire_hp(world) and hp[Enemy.VIRE] == VIRE_MOST_HP
    assert {enemy: value for enemy, value in hp.items() if enemy != Enemy.VIRE} == others


@pytest.mark.parametrize("dropper", [Enemy.RED_DARKNUT, Enemy.GIBDO])
def test_another_bomb_dropper_in_level_9_leaves_the_vires_alone(dropper: Enemy) -> None:
    world = parse_rom(finish(built(ONLY_VIRES_SEED), remember_repo_base_rom()))
    vires = level_monsters(world, level_9(world))
    other = next(room for room in rooms_reached_without_bombs(level_9(world))
                 if Enemy.NOTHING < room.enemy < Enemy.SINGLE_DODONGO and room.enemy != Enemy.VIRE)
    other.enemy = dropper
    assert Enemy.VIRE in level_monsters(world, level_9(world)) and Enemy.VIRE in vires
    world.enemies.hp[Enemy.VIRE] = WALKED_HP
    assert not cap_level_9_vire_hp(world) and world.enemies.hp[Enemy.VIRE] == WALKED_HP


@pytest.mark.parametrize("dropper", [Enemy.RED_DARKNUT, Enemy.GIBDO])
def test_a_bomb_dropper_behind_a_bomb_wall_does_not_spare_the_vires(dropper: Enemy) -> None:
    """Only droppers a player reaches without bombs count: one behind a bomb wall still caps the Vires."""
    world = parse_rom(finish(built(ONLY_VIRES_SEED), remember_repo_base_rom()))
    reached = {room.room_num for room in rooms_reached_without_bombs(level_9(world))}
    behind = next((room for room in level_9(world).rooms if room.room_num not in reached
                   and Enemy.NOTHING < room.enemy < Enemy.SINGLE_DODONGO), None)
    if behind is None:
        pytest.skip("every room of this level 9 is reached without bombs")
    behind.enemy = dropper
    world.enemies.hp[Enemy.VIRE] = WALKED_HP
    assert cap_level_9_vire_hp(world) and world.enemies.hp[Enemy.VIRE] == VIRE_MOST_HP


def test_the_bomb_droppers_are_the_drop_row_with_bombs() -> None:
    """PRG0's class C (DropItemMonsterTypes2): the Lynel, Moblin and Octoroks of type $01, $03, $09
    and $0A, the Goriya $06, the Darknut $0B, the Vire, the Wizzrobe $24 and the Gibdo; never the
    Red Lynel, Blue Goriya or Blue Darknut, whose drops come from the row without bombs."""
    assert bomb_droppers(None) == {0x01, 0x03, 0x06, 0x09, 0x0A, 0x0B, Enemy.VIRE, 0x24, Enemy.GIBDO}
