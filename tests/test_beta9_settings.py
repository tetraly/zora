"""The beta 9 export's small settings, on finished ROMs from the spec's own Check strings (CP-5 with the
field set), each against its entry's Check:

  - Maximum Enemy Health (B45; PS-HP-08): the 25 enemy bytes $FF and both Rope operands $F0, whatever
    "Most" Enemy HP (C09) holds; under Swordless the wooden-sword cave sells the red candle. The
    level-9 Vire cap (tetraly/zora#14) still lowers Vires that are level 9's only bomb droppers.
  - Increase Bomb Capacity Upgrade (B90; FP-BOMB-01): the capacity operand is the drawn one plus 2
    (4 to 8); with Change Bomb Upgrades (B12) off, 6 and PRG0's price.
  - "?" values resolve both ways; ROMs without the fields keep their bytes."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.steps.change_enemy_hp import BOMB_DROPPERS, VIRE_MOST_HP, cap_level_9_vire_hp, level_monsters
from zora.model.enums import Enemy
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.player_settings import DEFAULT_PLAYER_SETTINGS

pytestmark = needs_base_rom
CP5 = MVP_BASELINE_LEVEL_ENCODING_OFF
# The Checks' strings
B45_ON, B45_SWORDLESS, B45_ZERO_WALK, B45_POSSIBLE = (
    "8hrpCUwkY2YtIAS7u5WXvCc5qHUJ3A", "8hrpCUwkY2YtIAS7u5WXvCc5qHYbxq", "8hrpCUwkY2YtIAS7u5WXvCc5qMxJ0V",
    "8htZDLRSmYJdR9bCninGM0D8mQUJ3A")
B90_ON, B90_WITHOUT_B12, B12_OFF, B90_POSSIBLE = (
    "1K8u1yQ0wMsbzcHHN!CQfC1ZhJCP54uelbE!UJ3A", "1K8u1yQ0wMsbzcHHN!CQf77AzR1PZgQsCjK8UJ3A",
    "8hq4BeR1JXo3EnbApTkP!cSAzHUJ3A", "2eHn3vq1rjbW89MvKy5JWFuy4ZPKvLKuW8arUJ3A")
ENEMY_VALUES, ENEMY_VALUE_BYTES = 0x1FB5E, 25
ROPE_OPERANDS = (0x112D3, 0x112DF)
WOOD_SWORD_CAVE_WARE_1 = 0x18611
BLUE_CANDLE, RED_CANDLE = 0x06, 0x07
BOMB_CAPACITY, BOMB_PRICE_TILES = 0x4B9B, 0x1A2B2
PRG0_PRICE_TILES = bytes([0x01, 0x00, 0x00])            # "100"
SEEDS = (1, 2, 3)


@cache
def built(flag_string: str, seed: int) -> Built:
    return build(plan(flag_string, seed), remember_repo_base_rom())


@cache
def rom(flag_string: str, seed: int) -> bytes:
    base = remember_repo_base_rom()
    return finish(built(flag_string, seed), base, player_settings=DEFAULT_PLAYER_SETTINGS)


def maximum_enemy_health(data: bytes) -> bool:
    return (data[ENEMY_VALUES:ENEMY_VALUES + ENEMY_VALUE_BYTES] == b"\xff" * ENEMY_VALUE_BYTES
            and all(data[operand] == 0xF0 for operand in ROPE_OPERANDS))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("flag_string", [B45_ON, B45_ZERO_WALK])
def test_maximum_enemy_health(flag_string: str, seed: int) -> None:
    assert maximum_enemy_health(rom(flag_string, seed))
    assert rom(flag_string, seed)[WOOD_SWORD_CAVE_WARE_1] != RED_CANDLE
    assert not maximum_enemy_health(rom(CP5, seed))


@pytest.mark.parametrize("seed", SEEDS)
def test_maximum_enemy_health_swordless_sells_the_red_candle(seed: int) -> None:
    data = rom(B45_SWORDLESS, seed)
    assert maximum_enemy_health(data) and data[WOOD_SWORD_CAVE_WARE_1] == RED_CANDLE


def test_maximum_enemy_health_possible_resolves_both_ways() -> None:
    assert {maximum_enemy_health(rom(B45_POSSIBLE, seed)) for seed in range(1, 9)} == {False, True}


def test_the_level_9_vire_cap_still_lowers_maximum_health_vires() -> None:
    """Under B45 Vires hold 15; made level 9's only bomb droppers, the cap leaves them at 4."""
    world = built(B45_ON, 1).world
    level_9 = next(level for level in world.levels if level.level_num == 9)
    assert world.enemies.hp[Enemy.VIRE] == 15
    lists, starts = world.enemies.mixed_enemy_data, world.enemies.mixed_group_offsets
    for room in level_9.rooms:
        if room.enemy in starts:                        # a mixed list's members (level_monsters)
            start = starts[room.enemy]
            for place in range(start, start + level_9.enemy_quantity(room)):
                if lists[place] in BOMB_DROPPERS:
                    lists[place] = Enemy.VIRE
        elif room.enemy in BOMB_DROPPERS:
            room.enemy = Enemy.VIRE
    assert level_monsters(world, level_9) & BOMB_DROPPERS == {Enemy.VIRE}
    assert cap_level_9_vire_hp(world) and world.enemies.hp[Enemy.VIRE] == VIRE_MOST_HP


@pytest.mark.parametrize("seed", SEEDS)
def test_increase_bomb_capacity_upgrade(seed: int) -> None:
    drawn = rom(CP5, seed)[BOMB_CAPACITY]
    assert 2 <= drawn <= 6
    assert rom(B90_ON, seed)[BOMB_CAPACITY] in range(4, 9)
    assert rom(B90_WITHOUT_B12, seed)[BOMB_CAPACITY] == 6
    assert rom(B12_OFF, seed)[BOMB_CAPACITY] == 4
    for flag_string in (B90_WITHOUT_B12, B12_OFF):
        assert rom(flag_string, seed)[BOMB_PRICE_TILES:BOMB_PRICE_TILES + 3] == PRG0_PRICE_TILES


def test_increase_bomb_capacity_upgrade_possible_resolves_both_ways() -> None:
    capacities = {rom(B90_POSSIBLE, seed)[BOMB_CAPACITY] for seed in range(1, 13)}
    assert capacities & {2, 3} and capacities & {7, 8}
