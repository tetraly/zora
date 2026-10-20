"""Dungeon quest's data layer (shapes-behavior.md SH-SRC-02, SH-SRC-03, SH-SRC-05): a set of
levels pointing at its second-quest room block, with the second-quest level information and
the quest-number branches, round-trips through serialize and parse."""
import copy
from functools import cache

import pytest

from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.layout import (
    LEVEL_1_6_DATA_ADDRESS_Q2,
    LEVEL_INFO_ADDRESS,
    LEVEL_INFO_SIZE,
    Q2_REPLACEMENT_SIZES_ADDRESS,
    QUEST_MONSTER_BRANCH_ADDRESSES,
    ROOM_BLOCK_ADDRESSES_Q1,
)
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

# SH-SRC-03: the second-quest replacement bytes start at level-information offset $29; n per
# level 1-9, read from PRG0's table at Q2_REPLACEMENT_SIZES_ADDRESS
REPLACEMENT_START = 0x29


@cache
def _base() -> bytes:
    return remember_repo_base_rom()


def _second_quest_levels_1_to_6() -> GameWorld:
    """PRG0 with levels 1 to 6 taken from the second quest, as SH-SRC-02/03 state."""
    world = copy.deepcopy(parse_rom(_base()))
    world.levels[:6] = world.levels_2q[:6]
    world.monsters_take_second_quest_path = True
    return world


def test_prg0_round_trips_unchanged() -> None:
    assert serialize_to_rom(parse_rom(_base()), _base()) == _base()


def test_a_second_quest_set_is_written_and_read_back() -> None:
    world = _second_quest_levels_1_to_6()
    rom = serialize_to_rom(world, _base())
    assert [rom[ROOM_BLOCK_ADDRESSES_Q1 + 2 * level + 1] for level in range(1, 10)] == [0x8D] * 6 + [0x8A] * 3
    assert [rom[address] for address in QUEST_MONSTER_BRANCH_ADDRESSES] == [0xD0] * 3
    assert rom[LEVEL_1_6_DATA_ADDRESS_Q2:LEVEL_1_6_DATA_ADDRESS_Q2 + 0x300] == \
        _base()[LEVEL_1_6_DATA_ADDRESS_Q2:LEVEL_1_6_DATA_ADDRESS_Q2 + 0x300]
    reread = parse_rom(rom)
    assert reread.monsters_take_second_quest_path
    for level, second_quest in zip(reread.levels[:6], world.levels_2q[:6], strict=True):
        assert level.block is reread.blocks_2q[0]
        assert level.room_nums == second_quest.room_nums
    for level in reread.levels[6:]:
        assert level.block is reread.blocks[1]
    assert serialize_to_rom(reread, rom) == rom


@pytest.mark.parametrize("level_num", range(1, 7))
def test_the_level_information_carries_the_n_replacement_bytes(level_num: int) -> None:
    """SH-SRC-03: n bytes from $29 are the second quest's; byte $29 + n keeps its first-quest
    value (the quirk: PRG0's loader copies one more)."""
    rom = serialize_to_rom(_second_quest_levels_1_to_6(), _base())
    count = _base()[Q2_REPLACEMENT_SIZES_ADDRESS + level_num - 1]
    start = LEVEL_INFO_ADDRESS + level_num * LEVEL_INFO_SIZE + REPLACEMENT_START
    first_quest = _base()[start:start + count + 1]
    written = rom[start:start + count + 1]
    assert written[count] == first_quest[count]
    second_quest = parse_rom(_base()).levels_2q[level_num - 1]
    assert written[:4] == bytes(second_quest.item_position_table)
