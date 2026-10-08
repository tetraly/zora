"""Late gate (docs/spec/late-gate.md @ 641f51a): unit rules and shipped
invariants."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.model.enums import (
    BossSound, BossSpriteSet, Direction, Enemy, EnemySpriteSet, RoomAction, RoomType, Side,
)
from zora.model.rooms import EnemyInfo, LayoutInfo, Room, StaircaseRoom, WallSet
from zora.model.game_world import GameWorld
from zora.model.levels import Level, LevelBlock
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.generate.rng import Rng
from zora.generate.late_gate.blocks import GateBlock
from zora.generate.late_gate.deal import _is_safe_seat, _redeal_contents
from zora.generate.late_gate.fixes import _clear_exit_bits, _tail
from zora.generate.late_gate import walk
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.world import D_OPEN, D_SHUTTER, D_WALL, set_side, side_of


def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)


def _level(num: int, block: LevelBlock, room_nums: list[int], entrance: int,
           stair_nums: tuple[int, ...] = ()) -> Level:
    return Level(
        level_num=num, entrance_room=entrance,
        entrance_direction=Direction.SOUTH, palette_raw=b"", fade_palette_raw=b"",
        staircase_room_pool=list(stair_nums), room_nums=sorted(room_nums),
        staircase_nums=list(stair_nums), block=block, boss_room=0xFF,
        enemy_sprite_set=EnemySpriteSet.A, boss_sprite_set=BossSpriteSet.A, start_y=0,
        item_position_table=[0] * 4, map_start=0, map_cursor_offset=0,
        map_data=b"", map_ppu_commands=b"", qty_table=[0, 2, 4, 8],
        stairway_data_raw=b"",
    )


def _row_level(cells: list[int], layouts: dict[int, int], num: int = 1,
               block: LevelBlock | None = None) -> Level:
    """A level of walled-in rooms, each holding monster list $01 and trigger 1."""
    block = block or LevelBlock.blank()
    for c in cells:
        room = block.room(c)
        room.layout_info = LayoutInfo(RoomType(layouts.get(c, 0x00)))
        room.enemy_info = EnemyInfo(Enemy(0x01))
        room.room_action = RoomAction.ALL_DEAD
    return _level(num, block, cells, entrance=max(cells))


def test_swap_safety_rejects_after_1000_draws() -> None:
    # a $0E content has no legal home in a single row ending at column 15:
    # every other home lacks a left or right same-level neighbour.
    level = _row_level([0x70, 0x71], {0x70: 0x21, 0x71: 0x0E})
    assert _redeal_contents(level, Rng(1)) is None


def test_seat_rules_whole_byte() -> None:
    cells = {0x10, 0x20, 0x21, 0x22}
    assert _is_safe_seat(0x0E, 0x21, cells)
    assert not _is_safe_seat(0x0E, 0x20, cells)
    assert _is_safe_seat(0x4E, 0x20, cells)      # push variant unconstrained
    assert _is_safe_seat(0x27, 0x10, cells)      # cell below in the level
    assert not _is_safe_seat(0x27, 0x21, cells)
    assert _is_safe_seat(0x0F, 0x20, cells)      # cell above in the level


def test_walk_move_table_and_one_way_stairs() -> None:
    # entrance (0x71) -> north through a $0F room (0x61) to 0x51: $0F joins
    # only W<->E, so the room above is never reached; unrestricted passes.
    level = _row_level([0x51, 0x61, 0x71], {0x71: 0x21, 0x61: 0x0F})
    for c, ds in ((0x71, (Side.SOUTH, Side.NORTH)), (0x61, (Side.SOUTH, Side.NORTH)), (0x51, (Side.SOUTH,))):
        for d in ds:
            set_side(level.block.room(c), d, D_OPEN)
    assert walk.connectivity_walk(level).passed is False
    level.block.room(0x61).room_type = RoomType.PLAIN_ROOM
    assert walk.connectivity_walk(level).passed is True
    # one-way stair: only the usable end ($1B) leads to the other
    level = _row_level([0x50, 0x71], {0x71: 0x1B, 0x50: 0x00})
    level.block.room(0x71).walls.south = D_OPEN
    level.block[0x7F] = StaircaseRoom(room_num=0x7F, room_type=RoomType.TRANSPORT_STAIRCASE,
                                      exit_x=6, exit_y=9, left_exit=0x71, right_exit=0x50)
    level.staircase_nums = level.staircase_room_pool = [0x7F]
    res = walk.connectivity_walk(level)
    assert res.forward_passed and not res.reverse_passed


def _level9(gw: GameWorld) -> Level:
    return gw.levels[8]


def test_shipped_gate_invariants() -> None:
    """Read on the shape stage straight into the gate (b1=False): the map
    move after it only trades item bytes."""
    rom = _vanilla_rom()
    for seed in range(3):
        gw = parse_rom(rom)
        generate_shapes(gw, Rng(seed), ShapeOptions())
        level9 = _level9(gw)
        block = level9.block
        cells9 = set(level9.room_nums)
        entrance = block.room(level9.entrance_room)
        # L9 entrance: E/W walls, north open (pins + step-5 forcing)
        assert entrance.walls.east == D_WALL
        assert entrance.walls.west == D_WALL
        assert entrance.walls.north == D_OPEN
        # boss sound index 1, only in level 9: the gate marks Ganon's
        # neighbours, and the later map move (SH-MAP-06) can carry a mark
        # to another level-9 room with the item byte
        assert any(room.enemy == Enemy.THE_BEAST for room in level9.rooms)
        for room in block.rooms:
            if room.boss_sound != BossSound.NONE:
                assert room.boss_sound == BossSound.ROAR_AQUAMENTUS_GLEEOK_GANON
                assert room.room_num in cells9
        # levels 7-9: push blocks only where trigger 4/5 or byte $5A/$60
        # (monster bit ignored, A29)
        for level in gw.levels[6:]:
            for room in level.rooms:
                if room.movable_block:
                    assert room.room_action in (4, 5) or room.layout_code in (0x5A, 0x60)
        # $27 rooms: N/E/W pairs wall/wall where the neighbour is same-level.
        # The pin follows the layout; B2's re-deal moves Zelda off it and
        # B3's exchange moves the layout between levels (level 9 may hold
        # none).
        assert any(room.enemy == Enemy.THE_KIDNAPPED for room in level9.rooms)
        for room in level9.rooms:
            if room.layout_code != RoomType.ZELDA_ROOM:
                continue
            z = room.room_num
            for d, od, nb in ((Side.NORTH, Side.SOUTH, z - 16), (Side.EAST, Side.WEST, z + 1),
                              (Side.WEST, Side.EAST, z - 1)):
                same_row = d == Side.NORTH or nb // 16 == z // 16
                if nb in cells9 and same_row:
                    assert side_of(room, d) == D_WALL
                    assert side_of(block.room(nb), od) == D_WALL


def _person_room_at_row_end(block: LevelBlock) -> Room:
    """A $4B person room at column 15 whose east side is a shutter."""
    person = block.room(0x1F)
    person.layout_info = LayoutInfo(RoomType.BLACK_ROOM)
    person.enemy_info = EnemyInfo(Enemy(0x4B))
    person.room_action = RoomAction.NONE
    person.walls = WallSet(north=D_WALL, east=D_SHUTTER, south=D_OPEN, west=D_WALL)
    return person


def test_tail_person_rule_wraps_without_level_guard() -> None:
    """A42: the $0B person room's east write at column 15 lands on the next
    row's column 0, whatever level holds it."""
    block = LevelBlock.blank()
    _person_room_at_row_end(block)
    block.room(0x20).walls = WallSet(north=D_WALL, east=D_WALL, south=D_WALL, west=D_SHUTTER)
    levels = [_level(8, block, [0x20], entrance=0x20), _level(9, block, [0x1F], entrance=0x1F)]
    _tail(GateBlock(block, levels))
    assert block.room(0x20).walls.west == D_OPEN


def test_tail_write_on_a_staircase_clears_bits_only_when_serialized() -> None:
    """A43: the same write landing on a staircase clears the facing side's
    door-field bits of its exit byte (the west side is the B byte's bits
    7-5). The staircase keeps the rooms it leads to, so the map move, the
    acceptance walk and the hint probes still follow the link; the cleared
    bits appear in the bytes written to the ROM."""
    from zora.rom.serialize.levels import _staircase_bytes
    from zora.generate.dungeon_walk import stair_partners
    block = LevelBlock.blank()
    person = _person_room_at_row_end(block)
    block.room(0x6E).layout_info = LayoutInfo.from_layout_code(0x4E)
    stair = StaircaseRoom(room_num=0x20, room_type=RoomType.TRANSPORT_STAIRCASE,
                          exit_x=6, exit_y=9, left_exit=0x1F, right_exit=0x6E)
    block[0x20] = stair
    level9 = _level(9, block, [0x1F, 0x6E], entrance=0x1F, stair_nums=(0x20,))
    _tail(GateBlock(block, [level9]))
    assert (stair.left_exit, stair.right_exit) == (0x1F, 0x6E)            # the link is kept
    assert stair_partners(level9, person.room_num, block.staircases) == [0x6E]
    assert (stair.exit_x, stair.exit_y) == (0xB, 0x8)      # read from $6E's layout $4E
    assert _staircase_bytes(stair)[:2] == (0x1F, 0x6E & ~0xE0)            # the B byte as written


def test_cleared_exit_bits_of_a_cellar_split_its_two_bytes() -> None:
    """A43 on an item cellar: its A and B bytes both hold the return room;
    a write that clears bits of one makes them differ in the ROM only."""
    from zora.rom.serialize.levels import _staircase_bytes
    cellar = StaircaseRoom(room_num=0x21, room_type=RoomType.ITEM_STAIRCASE, exit_x=6, exit_y=9,
                           return_dest=0x6E)
    _clear_exit_bits(cellar, 1, 0xE0)
    assert (cellar.return_dest, cellar.return_dest_b) == (0x6E, None)
    assert _staircase_bytes(cellar)[:2] == (0x6E, 0x0E)
    _clear_exit_bits(cellar, 0, 0xE0)
    assert _staircase_bytes(cellar)[:2] == (0x0E, 0x0E)
