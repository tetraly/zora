"""Post-shapes batch B3 (post-shapes-b3.md): the room exchange's pool, its
swap rules and quirks, the position renumbering, the second drop shuffle,
and the pass's invariants on serialized output."""
import os
from collections import Counter
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.game_config import GameConfig, HintMode
from zora.model.enums import (
    BossSound, BossSpriteSet, Direction, Enemy, EnemySpriteSet, Item, ItemPosition, RoomAction, RoomType,
)
from zora.model.rooms import EnemyInfo, ItemInfo, LayoutInfo, Room
from zora.model.levels import Level, LevelBlock
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng, ScriptedRng
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions
from zora.generate.steps.dungeon_room_shuffle import (
    PROGRESSION_ITEMS, Contents, exchange_pool, exchange_rooms, is_stair_type, monster_refuses, put_contents,
    second_drop_shuffle, takes_part,
)

NO_ITEM = 0x03
POSITIONS = {1: [0x10, 0x20, 0x30, 0x40], 2: [0x40, 0x50, 0x60, 0x10]}


# Generated hint text is written as generated seeds write it (the extended bank), not into the
# vanilla bank, which ZORA's wording outgrows.
GENERATED_HINTS = GameConfig(hint_mode=HintMode.CONSTERNATION)


def _contents(layout: int, movable: bool = False, item: int = NO_ITEM,
              action: int = 0, position_value: int = 0x10) -> Contents:
    return Contents(LayoutInfo(RoomType(layout), movable), ItemInfo.from_item_byte(item),
                    RoomAction(action), position_value)


def _level(num: int, block: LevelBlock, room_nums: list[int]) -> Level:
    return Level(
        level_num=num, entrance_room=room_nums[0],
        entrance_direction=Direction.SOUTH, palette_raw=b"", fade_palette_raw=b"",
        staircase_room_pool=[], room_nums=room_nums, staircase_nums=[],
        block=block, boss_room=0xFF,
        enemy_sprite_set=EnemySpriteSet.A, boss_sprite_set=BossSpriteSet.A, start_y=0,
        item_position_table=list(POSITIONS[num]), map_start=0, map_cursor_offset=0,
        map_data=b"", map_ppu_commands=b"", qty_table=[0, 2, 4, 8],
        stairway_data_raw=b"",
    )


def _toy_levels(rooms: int = 4) -> list[Level]:
    """One block: level 1 owns cells 0..rooms-1, level 2 cells 16..16+rooms-1.
    Every room holds layout $02, monster list $05, no item and trigger 0."""
    block = LevelBlock.blank()
    levels = [_level(1, block, list(range(rooms))), _level(2, block, list(range(16, 16 + rooms)))]
    for level in levels:
        for room in level.rooms:
            room.layout_info = LayoutInfo(RoomType(0x02))
            room.enemy_info = EnemyInfo(Enemy(0x05))
            room.item_info = ItemInfo(Item.NOTHING)
            room.room_action = RoomAction.NONE
    return levels


def _room(levels: list[Level], cell: int) -> Room:
    return levels[0].block.room(cell)


# --- PS-XCHG-01 ----------------------------------------------------------------

def test_pool_skip_rules() -> None:
    levels = _toy_levels()
    room = _room(levels, 0)
    assert takes_part(room)
    pooled = {pooled_room.room_num for _level_of, pooled_room in exchange_pool(levels)}
    assert 0 in pooled and 5 not in pooled             # room 5: no level
    for layout, movable, joins in ((0x21, False, False), (0x20, True, False),
                                   (0x21, True, True), (0x3E, False, False)):
        room.layout_info = LayoutInfo(RoomType(layout), movable)
        assert takes_part(room) is joins, hex(layout)
    room.layout_info = LayoutInfo(RoomType(0x02))
    room.enemy = Enemy(0x40 | 0x0D)                    # a person
    assert not takes_part(room)
    room.enemy = Enemy(0x36)                           # the hungry goriya
    assert not takes_part(room)
    room.enemy = Enemy(0x40 | 0x36)                    # a flagged trap takes part
    assert takes_part(room)
    for item in (*PROGRESSION_ITEMS, 0x14, 0x02, 0x1C, 0x16, 0x17, 0x1A, 0x1B, 0x0E):
        room.item = Item(item)
        assert not takes_part(room), hex(item)


# --- PS-XCHG-03/04 ---------------------------------------------------------------

def test_stair_type() -> None:
    assert is_stair_type(_contents(0x1A, movable=True))       # $5A
    assert not is_stair_type(_contents(0x1B, movable=True))   # $5B is not
    assert not is_stair_type(_contents(0x1A))
    assert is_stair_type(_contents(0x02, action=5))


def test_rule_masks() -> None:
    """Low six bits for Ganon's list; low seven for Zelda's ($5A live, the
    push bit alone not banned) and for Gleeok (push bit always bars)."""
    assert monster_refuses(0x3E, _contents(0x01, movable=True), True)
    assert monster_refuses(0x37, _contents(0x1A, movable=True), True)
    assert not monster_refuses(0x37, _contents(0x02, movable=True), True)
    assert not monster_refuses(0x37, _contents(0x1B), True)   # no $1B ban here
    assert monster_refuses(0x82, _contents(0x02, movable=True), True)
    assert monster_refuses(0x85, _contents(0x13), True)
    assert not monster_refuses(0x84, _contents(0x13), True)


def test_dodongo_tested_in_the_first_cell_only() -> None:
    barred = _contents(0x09)
    assert monster_refuses(0x31, barred, dodongo_checked=True)
    assert not monster_refuses(0x31, barred, dodongo_checked=False)


def test_rule_failure_skips_without_redraw() -> None:
    """A refused swap moves the walk on; a stair mismatch re-draws."""
    levels = _toy_levels(rooms=1)
    _room(levels, 0).enemy = Enemy(0x3E)               # Ganon in level 1
    _room(levels, 16).room_type = RoomType(0x01)       # barred for Ganon
    # two discards, i=0 draws j=1 (refused, skipped), i=1 draws itself
    stats = exchange_rooms(levels, ScriptedRng([0, 0, 1, 0]))
    assert (stats.swaps, stats.skipped) == (1, 1)      # the self-pair counts
    assert _room(levels, 0).room_type == 0x02 and _room(levels, 16).room_type == 0x01
    levels = _toy_levels(rooms=1)
    _room(levels, 16).layout_info = LayoutInfo(RoomType(0x1A), True)   # stair-type
    stats = exchange_rooms(levels, ScriptedRng([0, 0, 1, 0, 0]))
    assert stats.stair_redraws == 1
    assert _room(levels, 16).layout_code == 0x5A


def test_contents_move_and_monsters_stay() -> None:
    levels = _toy_levels(rooms=1)
    first, second = _room(levels, 0), _room(levels, 16)
    first.room_type, first.item = RoomType(0x0C), Item.KEY
    first.item_position = ItemPosition.POSITION_D      # value $40
    second.enemy = Enemy(0x40 | 0x06)                  # flagged
    exchange_rooms(levels, ScriptedRng([0, 0, 1, 0]))
    assert (second.room_type, second.item) == (0x0C, Item.KEY)
    assert second.enemy == 0x46 and first.enemy == 0x05
    assert second.item_position == 0                   # first index holding $40
    assert first.item_position == 0                    # no item: index 0


def test_item_needs_its_position_value_in_the_receiving_level() -> None:
    levels = _toy_levels(rooms=1)
    first = _room(levels, 0)
    first.item, first.item_position = Item.KEY, ItemPosition.POSITION_B   # value $20: not in level 2
    stats = exchange_rooms(levels, ScriptedRng([0, 0, 1, 0]))
    assert stats.skipped == 1 and first.item == Item.KEY


def test_position_renumbering_falls_back_to_zero() -> None:
    levels = _toy_levels(rooms=1)
    put_contents(levels[1], _room(levels, 16), _contents(0x02, item=0x19, position_value=0x99))
    assert _room(levels, 16).item_position == 0


# --- PS-XCHG-05 ----------------------------------------------------------------

def test_second_drop_shuffle_keeps_each_levels_item_set() -> None:
    levels = _toy_levels()
    for cell, item in ((0, 0x19), (1, 0x0F), (2, 0x0E), (3, 0x16), (16, 0x18)):
        _room(levels, cell).item = Item(item)
    _room(levels, 0).is_dark = True
    before = [Counter(room.item for room in level.rooms) for level in levels]
    second_drop_shuffle(levels, ScriptedRng([2, 0, 0, 0]))
    after = [Counter(room.item for room in level.rooms) for level in levels]
    assert before == after
    assert _room(levels, 2).item == 0x0E               # the Triforce of Power stays
    assert _room(levels, 0).item_info == ItemInfo(Item.COMPASS, BossSound.NONE, False)
    assert _room(levels, 3).item_info == ItemInfo(Item.KEY, BossSound.NONE, True)   # the dark bit rides


# --- finished-ROM invariants -----------------------------------------------------

def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)


def test_b3_invariants_on_output() -> None:
    """No progression item in a level-9 room: the pool never moves guarded
    items (B3 checkpoint)."""
    rom = _vanilla_rom()
    for seed in range(3):
        gw = parse_rom(rom)
        generate_shapes(gw, Rng(900 + seed), ShapeOptions())
        finished = parse_rom(serialize_to_rom(gw, rom, config=GENERATED_HINTS))
        level9 = finished.levels[8]
        for room in level9.rooms:
            assert room.item.value & 0x1F not in PROGRESSION_ITEMS, (seed, room.room_num)


def test_exchange_is_deterministic_on_a_copy() -> None:
    layouts = []
    for _ in range(2):
        levels = _toy_levels()
        for cell in range(4):
            _room(levels, cell).room_type = RoomType(0x02 + cell)
        exchange_rooms(levels, Rng(5))
        layouts.append([room.room_type for room in levels[0].block.rooms])
    assert layouts[0] == layouts[1]
