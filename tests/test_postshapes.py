"""Post-shapes batch B1 (post-shapes-b1.md): pass rules and the checkpoint
invariants on serialized output."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.game_config import GameConfig, HintMode
from zora.model.enums import (
    BossSound, BossSpriteSet, Direction, Enemy, EnemySpriteSet, Item, RoomAction, RoomType, TollOption,
    WallType,
)
from zora.model.rooms import EnemyInfo, ItemInfo, LayoutInfo, LifeOrMoneyToll, Room, StaircaseRoom, WallSet
from zora.model.levels import Level, LevelBlock
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions
from zora.generate.steps.item_shuffle_result import ItemShuffleOptions, ItemShuffleResult
from zora.generate.steps.add_money_or_life_rooms import add_money_or_life_rooms
from zora.generate.steps.shuffle_bomb_upgrade_men import shuffle_bomb_upgrade_men
from zora.generate.steps.shuffle_dungeon_drops import shuffle_dungeon_drops, snapshot_shapes
from zora.generate.steps.shuffle_items import shuffle_items
from zora.generate.steps.change_money_or_life_toll import change_money_or_life_toll
from zora_measure.statistics import b1_checkpoint


# Generated hint text is written as generated seeds write it (the extended bank), not into the
# vanilla bank, which ZORA's wording outgrows.
GENERATED_HINTS = GameConfig(hint_mode=HintMode.CONSTERNATION)


def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)


def test_checkpoint_invariants_on_output() -> None:
    rom = _vanilla_rom()
    for seed in range(4):
        gw = parse_rom(rom)
        res = generate_shapes(gw, Rng(900 + seed), ShapeOptions())
        out = serialize_to_rom(gw, rom, config=GENERATED_HINTS)
        cp = b1_checkpoint(parse_rom(out))
        assert cp.goriya == 1
        assert cp.ganon_8e == 1
        assert res.item_shuffle_result is not None
        assert cp.merchants == res.item_shuffle_result.merchants_added
        assert 1 <= cp.merchants <= 3
        assert cp.hearts_dungeon + cp.hearts_caves == 9


def _level(num: int, block: LevelBlock, room_nums: list[int]) -> Level:
    return Level(
        level_num=num, entrance_room=room_nums[0],
        entrance_direction=Direction.SOUTH, palette_raw=b"", fade_palette_raw=b"",
        staircase_room_pool=[], room_nums=room_nums, staircase_nums=[],
        block=block, boss_room=0xFF,
        enemy_sprite_set=EnemySpriteSet.A, boss_sprite_set=BossSpriteSet.A, start_y=0,
        item_position_table=[0] * 4, map_start=0, map_cursor_offset=0,
        map_data=b"", map_ppu_commands=b"", qty_table=[0, 2, 4, 8],
        stairway_data_raw=b"",
    )


def _toy_levels(owners: dict[int, list[int]] | None = None) -> list[Level]:
    """One block; owners: level -> its rooms (level 1 owns rooms 0-3 by
    default). Every room starts with no item."""
    block = LevelBlock.blank()
    levels = [_level(num, block, rooms) for num, rooms in (owners or {1: [0, 1, 2, 3]}).items()]
    for level in levels:
        for room in level.rooms:
            room.item_info = ItemInfo(Item.NOTHING)
    return levels


def _room(levels: list[Level], cell: int) -> Room:
    return levels[0].block.room(cell)


def _make_person(room: Room, code: int = 0x4D, count_index: int = 2) -> None:
    room.layout_info = LayoutInfo(RoomType.BLACK_ROOM)
    room.enemy_info = EnemyInfo(Enemy(code), count_index)
    room.room_action = RoomAction.ALL_DEAD


def test_item_shuffle_is_a_permutation_with_cave_masking() -> None:
    levels = _toy_levels()
    block = levels[0].block
    _room(levels, 0).item = Item(0x1D)        # wood boomerang room
    _room(levels, 1).item = Item(0x1A)        # heart room
    block[5] = StaircaseRoom(room_num=5, room_type=RoomType.ITEM_STAIRCASE, exit_x=6, exit_y=9,
                             item=Item(0x0A), return_dest=2)
    st = ItemShuffleResult(caves={"armos": 0x14, "white_sword": 0x02, "coast": 0x1A})
    # pool order: boomerang (room 0), bow (cellar), armos, white sword,
    # coast, heart (room 1)
    shuffle_items(levels, st, ScriptedRng([5, 0, 0, 2, 0, 0]), ItemShuffleOptions())
    cellar_item = block.staircase(5).item
    assert cellar_item is not None
    got = sorted([int(cellar_item), int(_room(levels, 0).item), int(_room(levels, 1).item)]
                 + list(st.caves.values()))
    assert got == sorted([0x0A, 0x1D, 0x1A, 0x14, 0x02, 0x1A])
    # destinations are exchanged (PS-ITEM-04): step 0 gives the boomerang
    # place 5 and the heart place 0; step 3 hands place 0 on to the white
    # sword item, whose position is dealt before position 5's
    assert _room(levels, 0).item == 0x02
    assert st.pool_size == 6
    # the tracked places in a room or the cellar are level 1's (the cellar returns to room 2)
    assert {place.level for place in st.tracked if place.slot is None} == {1}


def test_item_shuffle_refuses_to_drop_bits_into_a_cellar() -> None:
    """A pooled room's whole item byte moves (PS-ITEM-04). A cellar holds an
    item only, so a byte with the dark flag or a boss sound landing in one
    is an error, never a silent loss."""
    for item_info in (ItemInfo(Item(0x1D), is_dark=True),
                      ItemInfo(Item(0x1D), BossSound.ROAR_AQUAMENTUS_GLEEOK_GANON)):
        levels = _toy_levels()
        _room(levels, 0).item_info = item_info            # the wood boomerang's room
        levels[0].block[5] = StaircaseRoom(room_num=5, room_type=RoomType.ITEM_STAIRCASE,
                                           exit_x=6, exit_y=9, item=Item(0x0A), return_dest=2)
        state = ItemShuffleResult(caves={"armos": 0x14, "white_sword": 0x02, "coast": 0x1A})
        # position 0 (the boomerang room's byte) is dealt the cellar's place
        with pytest.raises(ValueError, match="item cellar"):
            shuffle_items(levels, state, ScriptedRng([1, 0, 0, 0, 0]), ItemShuffleOptions())


def test_drop_shuffle_uses_shape_stage_eligibility() -> None:
    levels = _toy_levels()
    for c, it in ((0, 0x19), (2, 0x00), (3, 0x0F)):
        _room(levels, c).item = Item(it)
    snap = snapshot_shapes(levels)
    _room(levels, 1).item = Item(0x05)        # gained an item since: stays out
    shuffle_dungeon_drops(levels, snap, ScriptedRng([2, 0, 0]))
    assert _room(levels, 1).item == 0x05
    assert [_room(levels, c).item for c in (0, 2, 3)] == [0x0F, 0x00, 0x19]


def test_merchant_write() -> None:
    levels = _toy_levels()
    room = _room(levels, 1)
    for person in (room, _room(levels, 2), _room(levels, 3)):
        _make_person(person)
    room.walls = WallSet(north=WallType(0), east=WallType(5), south=WallType(6), west=WallType(4))
    st = ItemShuffleResult()
    add_money_or_life_rooms(levels, st, ScriptedRng([0, 0, 0, 0]))
    assert (room.enemy, room.count_index, room.room_action) == (0x51, 0, 6)
    assert room.walls == WallSet(north=WallType(7), east=WallType(7), south=WallType(6), west=WallType(4))
    assert st.merchants_added == 1


def test_short_merchant_list_adds_no_merchant() -> None:
    # P23: fewer than three candidates ends the pass with no merchant
    levels = _toy_levels()
    room = _room(levels, 1)
    _make_person(room)
    st = ItemShuffleResult()
    add_money_or_life_rooms(levels, st, ScriptedRng([]))
    assert (room.enemy, room.room_action) == (0x4D, 1)
    assert st.merchants_added == 0


def test_merchants_dealt_by_partial_fisher_yates() -> None:
    # P13: three exchanges are always made, then the count; the first
    # `count` dealt candidates become merchants
    levels = _toy_levels()
    for c in range(4):
        _make_person(_room(levels, c))
    st = ItemShuffleResult()
    # i=0 picks 0+3, i=1 picks 1+0, i=2 picks 2+1; count 1+1 = 2
    add_money_or_life_rooms(levels, st, ScriptedRng([3, 0, 1, 1]))
    assert [_room(levels, c).enemy for c in range(4)] == [0x4D, 0x51, 0x4D, 0x51]
    assert st.merchants_added == 2


def test_bomb_upgrade_move() -> None:
    # PS-BOMB-01/02: the first two $0F persons of levels 5/7 are collected,
    # any other $0F person becomes $0E; each collected entry swaps its
    # monster byte with a uniform member of eligible + collected
    levels = _toy_levels({5: [0], 7: [1], 2: [2, 3]})
    for c, code in ((0, 0x4F), (1, 0x4F), (2, 0x4F), (3, 0x4D)):
        _make_person(_room(levels, c), code, count_index=0)
    st = ItemShuffleResult()
    # eligible = [2, 3] (collected rooms are not eligible, the stray is),
    # combined = [2, 3, 0, 1]; discards, then entry 2 (cell 0) swaps with
    # index 1 (cell 3) and entry 3 (cell 1) with itself; combined becomes
    # [2, 0, 3, 1], so the $0F cells in list order are 3 (L2), 1 (L7)
    shuffle_bomb_upgrade_men(levels, st, ScriptedRng([0, 0, 1, 3]))
    assert [_room(levels, c).enemy for c in range(4)] == [0x4D, 0x4F, 0x4E, 0x4F]
    assert st.bomb_levels == (2, 7)


def test_toll_draw_orders_the_pair() -> None:
    # two discards; first keys (2), second life (0): ordered life, keys;
    # key cost KEY_COSTS[1]
    st = ItemShuffleResult()
    change_money_or_life_toll(st, ScriptedRng([0, 0, 2, 0, 1]))
    assert st.toll == LifeOrMoneyToll(TollOption.LIFE, TollOption.KEYS, key_cost=3)
