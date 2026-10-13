"""Remove Most Open Stairs (B30; post-shapes-b9.md PS-OSTAIR-01 and PS-OSTAIR-02): which rooms
change, the drawn push-block layout and trigger 5, and finished ROMs at the b30 corpus's string."""
import copy
from functools import cache

import pytest

from zora.generate.pipeline import generate_rom, plan
from zora.generate.rng import ScriptedRng
from zora.generate.steps.remove_most_open_stairs import remove_most_open_stairs
from zora.model.enums import Enemy, ItemPosition, RoomAction, RoomType, WallType
from zora.model.game_world import GameWorld
from zora.model.levels import LevelBlock
from zora.model.rooms import EnemyInfo, LayoutInfo, Room
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.open_stairs import OPEN_STAIRS_FLAGS, open_stairs_rooms, push_stairs_rooms

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

LEVEL_1_ROOM = 0x22          # a level-1 room of PRG0 ($5A, the Diamond stair room with its block)
NO_LEVEL_ROOM = 0x00
# Level 1's item positions in PRG0: $C9 $AC $89 $87
POSITION_89 = ItemPosition(2)
POSITION_C9 = ItemPosition(0)
# The draw's order: $4A, $62, $48; the redraw's: $4A, $62
DRAW_4A, DRAW_62, DRAW_48 = 0, 1, 2
REVERSE_C_PUSH = LayoutInfo(RoomType.REVERSE_C, movable_block=True)
DOUBLE_BLOCK_PUSH = LayoutInfo(RoomType.DOUBLE_BLOCK, movable_block=True)
SINGLE_BLOCK_PUSH = LayoutInfo(RoomType.SINGLE_BLOCK_ROOM, movable_block=True)
SEEDS = range(4)


@cache
def _prg0() -> GameWorld:
    return parse_rom(remember_repo_base_rom())


def _block_with_open_stairs(position: ItemPosition = POSITION_89, enemy: Enemy = Enemy.BLUE_GORIYA,
                            count_index: int = 0) -> tuple[LevelBlock, Room]:
    """PRG0's levels-1-6 block (a copy, its levels with it) with level 1's room $22 an open-stairs
    room on trigger 1."""
    world = copy.deepcopy(_prg0())
    block = world.blocks[0]
    room = block.room(LEVEL_1_ROOM)
    room.layout_info = LayoutInfo(RoomType.NARROW_STAIR_ROOM)
    room.room_action = RoomAction.ALL_DEAD
    room.item_position = position
    room.enemy_info = EnemyInfo(enemy, count_index)
    for side in ("north", "east", "south", "west"):
        if getattr(room.walls, side) == WallType.SHUTTER_DOOR:
            setattr(room.walls, side, WallType.OPEN_DOOR)
    return block, room


def _only(room: Room) -> LevelBlock:
    """A block whose one open-stairs room is `room` (the others leave the layout)."""
    block = LevelBlock.blank()
    block[room.room_num] = room
    return block


def _isolate(block: LevelBlock, room: Room) -> None:
    """Every other room of the block a Plain room, so the pass draws for `room` alone."""
    for other in block.rooms:
        if other is not room:
            other.layout_info = LayoutInfo(RoomType.PLAIN_ROOM)


def test_an_open_stairs_room_takes_the_drawn_layout_and_trigger_5() -> None:
    """PS-OSTAIR-02: $48 is kept at level 1's position $89; the monster and item position stay."""
    block, room = _block_with_open_stairs()
    _isolate(block, room)
    remove_most_open_stairs([block], ScriptedRng([DRAW_48]))
    assert room.layout_info == REVERSE_C_PUSH and room.room_action == RoomAction.BLOCK_STAIRS
    assert room.item_position == POSITION_89 and room.enemy == Enemy.BLUE_GORIYA


def test_a_drawn_48_needs_item_position_89_or_d6() -> None:
    """PS-OSTAIR-02: level 1's position $C9 draws again from $4A and $62."""
    block, room = _block_with_open_stairs(position=POSITION_C9)
    _isolate(block, room)
    remove_most_open_stairs([block], ScriptedRng([DRAW_48, DRAW_62]))
    assert room.layout_info == SINGLE_BLOCK_PUSH


def test_a_trap_room_that_drew_48_draws_again() -> None:
    """PS-OSTAIR-02: the monster bit with $09 ($49, three pairs of traps) never keeps $48."""
    block, room = _block_with_open_stairs(enemy=Enemy.THREE_PAIRS_OF_TRAPS)
    _isolate(block, room)
    remove_most_open_stairs([block], ScriptedRng([DRAW_48, DRAW_4A]))
    assert room.layout_info == DOUBLE_BLOCK_PUSH and room.has_monster_bit


def test_a_room_of_no_level_never_keeps_48() -> None:
    """PS-OSTAIR-02 (quirk): a room of no level reads the overworld's positions, none $89 or $D6."""
    room = Room.blank(NO_LEVEL_ROOM)
    room.layout_info = LayoutInfo(RoomType.SPIRAL_STAIR_ROOM)
    remove_most_open_stairs([_only(room)], ScriptedRng([DRAW_48, DRAW_62]))
    assert room.layout_info == SINGLE_BLOCK_PUSH and room.room_action == RoomAction.BLOCK_STAIRS


@pytest.mark.parametrize("exemption", ["push-block door", "shutter", "Gleeok"])
def test_exempt_rooms_keep_their_open_stairs(exemption: str) -> None:
    """PS-OSTAIR-01: trigger 4, a shutter or a Gleeok keeps the room as it is, with no draw."""
    _block, room = _block_with_open_stairs(enemy=Enemy.GLEEOK_1 if exemption == "Gleeok" else Enemy.BLUE_GORIYA)
    if exemption == "push-block door":
        room.room_action = RoomAction.BLOCK_DOOR
    if exemption == "shutter":
        room.walls.south = WallType.SHUTTER_DOOR
    before = copy.deepcopy(room)
    remove_most_open_stairs([_only(room)], ScriptedRng([]))
    assert room == before


def test_a_gleeok_on_an_odd_count_index_changes() -> None:
    """PS-OSTAIR-01 (quirk): the Gleeok test reads the monster byte's low seven bits, which take in
    the count index's low bit."""
    _block, room = _block_with_open_stairs(enemy=Enemy.GLEEOK_1, count_index=1)
    remove_most_open_stairs([_only(room)], ScriptedRng([DRAW_62, DRAW_62]))
    assert room.layout_info == SINGLE_BLOCK_PUSH


@cache
def _finished(seed: int) -> GameWorld:
    config = plan(OPEN_STAIRS_FLAGS, seed).config
    rom = generate_rom(OPEN_STAIRS_FLAGS, seed, remember_repo_base_rom()).rom
    return parse_rom(rom, GameConfig(dungeon_nothing_code=config.dungeon_nothing_code, hint_mode=config.hint_mode))


@pytest.mark.parametrize("seed", SEEDS)
def test_finished_roms_keep_only_exempt_open_stairs(seed: int) -> None:
    """PS-OSTAIR-01's and -02's Checks on finished ROMs at the b30 corpus's string."""
    world = _finished(seed)
    assert open_stairs_rooms(world)["left"] == 0
    assert sum(count for key, count in push_stairs_rooms(world).items() if key.endswith("t5")) > 0
