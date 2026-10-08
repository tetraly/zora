"""The Room model's four byte groups (EnemyInfo, LayoutInfo, ItemInfo,
SecretInfo): together they name every bit the spec's byte rules touch, and
they agree with the serializer and with the generator's CellPlan."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.model.rooms import (
    COUNT_INDEX_MASK, ITEM_MASK, ITEM_POSITION_MASK, ITEM_POSITION_SHIFT, LAYOUT_ID_MASK, MONSTER_BIT_CODE,
    MONSTER_LIST_BITS, MONSTER_VALUE_BIT, PUSH_BLOCK_VARIANT, TRIGGER_MASK, EnemyInfo, ItemInfo, LayoutInfo,
    Room, SecretInfo,
)
from zora.model.enums import BossSound, Enemy, Item, ItemPosition, RoomAction, RoomType, WallType
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.generate.rng import Rng
from zora.rom.serialize.levels import _room_bytes
from zora.generate.generation_pass import generate_shapes
from zora.generate.ship import build_sets
from zora.generate.shapes.options import ShapeOptions

WALL_FIELD_VALUES = 8
BOSS_SOUND_VALUES = 4
BYTE_VALUES = 256
# LevelBlockAttrsF's named bits in a dungeon room: the trigger and the item position
DUNGEON_TRIGGER_BYTE_BITS = TRIGGER_MASK | (ITEM_POSITION_MASK << ITEM_POSITION_SHIFT)
PINNED_SEEDS = (3, 31)


def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)


@pytest.mark.parametrize("enum, values", [
    (Item, ITEM_MASK + 1), (RoomType, LAYOUT_ID_MASK + 1),
    (Enemy, (MONSTER_BIT_CODE | MONSTER_LIST_BITS) + 1), (RoomAction, TRIGGER_MASK + 1),
    (ItemPosition, ITEM_POSITION_MASK + 1), (BossSound, BOSS_SOUND_VALUES),
    (WallType, WALL_FIELD_VALUES),
])
def test_every_value_of_a_bit_field_has_an_enum_member(enum: type, values: int) -> None:
    """A pass may write any bit pattern mid-run; each must have a member."""
    for value in range(values):
        enum(value)


def test_item_info_names_every_bit_of_the_item_byte() -> None:
    for item_byte in range(BYTE_VALUES):
        assert ItemInfo.from_item_byte(item_byte).item_byte == item_byte


def test_secret_info_names_the_dungeon_bits_of_the_trigger_byte() -> None:
    for trigger_byte in range(BYTE_VALUES):
        assert (SecretInfo.from_trigger_byte(trigger_byte).trigger_byte
                == trigger_byte & DUNGEON_TRIGGER_BYTE_BITS)


def test_enemy_info_names_every_bit_of_the_monster_value() -> None:
    for monster_value in range(MONSTER_VALUE_BIT << 1):
        assert EnemyInfo.from_monster_value(monster_value).monster_value == monster_value


def test_enemy_info_replaces_the_list_keeping_flag_and_count() -> None:
    person = EnemyInfo.from_monster_value(MONSTER_VALUE_BIT | (2 << 6) | 0x0B)
    moved = person.with_monster_list(0x0F)
    assert (moved.monster_list, moved.has_monster_bit, moved.count_index) == (0x0F, True, 2)
    assert moved.is_person and not EnemyInfo(Enemy(0x0F)).is_person


def test_layout_info_names_every_bit_of_the_layout_code() -> None:
    for layout_code in range(PUSH_BLOCK_VARIANT << 1):
        assert LayoutInfo.from_layout_code(layout_code).layout_code == layout_code


def test_single_field_writes_go_through_the_groups() -> None:
    room = Room.blank(0x10)
    room.item, room.is_dark, room.boss_sound = Item.KEY, True, BossSound.ROAR_DODONGO_GOHMA
    room.room_action, room.item_position = RoomAction.ALL_DEAD_ITEM, ItemPosition.POSITION_C
    room.room_type, room.movable_block = RoomType.T_ROOM, True
    room.enemy, room.count_index = Enemy.HUNGRY_GORIYA, COUNT_INDEX_MASK
    assert room.item_info == ItemInfo(Item.KEY, BossSound.ROAR_DODONGO_GOHMA, True)
    assert room.secret_info == SecretInfo(RoomAction.ALL_DEAD_ITEM, ItemPosition.POSITION_C)
    assert room.layout_info == LayoutInfo(RoomType.T_ROOM, True)
    assert room.enemy_info == EnemyInfo(Enemy.HUNGRY_GORIYA, COUNT_INDEX_MASK)


def _assert_views_match_the_serializer(room: Room) -> None:
    _, _, monster, layout, item, trigger = _room_bytes(room)
    assert (room.monster_byte, room.layout_byte, room.item_byte, room.trigger_byte) \
        == (monster, layout, item, trigger), f"room {room.room_num:02X}"


def test_byte_views_are_the_serializers_bytes_on_the_base_rom() -> None:
    world = parse_rom(_vanilla_rom())
    for block in world.blocks + world.blocks_2q:
        for room in block.rooms:
            _assert_views_match_the_serializer(room)


@pytest.mark.parametrize("seed", PINNED_SEEDS)
def test_built_rooms_read_as_their_plans_did(seed: int) -> None:
    """build_sets is the only place a CellPlan becomes a Room; while both
    models exist, every byte view must agree across it."""
    rom = _vanilla_rom()
    result = generate_shapes(parse_rom(rom), Rng(seed), ShapeOptions())
    built = build_sets(parse_rom(rom), result.sets)
    for block, set_world in zip(built.blocks, result.sets, strict=True):
        for cell in set_world.all_cells_sorted():
            plan, room = set_world.plans[cell], block.room(cell)
            _assert_views_match_the_serializer(room)
            assert (room.monster_value, room.layout_byte, room.item_byte, room.is_person) \
                == (plan.monster_value, plan.layout_byte, plan.item_byte, plan.is_person), f"room {cell:02X}"
            assert (room.room_action, room.item_position) == (plan.trigger, plan.item_pos or 0), f"room {cell:02X}"
