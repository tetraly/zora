"""Item cellars in the emulator (SH-STAIR-16): in a ZORA ROM, levels 1, 4
and 5's cellar items stand on the middle of the upper ledge (X $80, Y $90)
and Link takes them walking the cellar. Those three levels' position
tables put index 0 elsewhere; with the old $00 bits, level 5's item floats
a tile above the ledge and cannot be taken."""
from functools import cache

import pytest

from tests.emulator import (
    CUR_LEVEL, GAME_MODE, GAME_SUBMODE, ITEMS, OBJ_X, OBJ_Y, ROOM_ID, Button, Emulator, Mode,
)
from tests.test_feature_patches import vanilla
from zora.generate.generation_pass import generate_shapes
from zora.generate.rng import Rng
from zora.generate.shapes.options import ShapeOptions
from zora.model.enums import RoomType
from zora.model.game_world import GameWorld
from zora.model.rooms import StaircaseRoom
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

SEED = 0
LEVEL_BLOCK_ATTRS_F = 0x6AFE          # the current block's LevelBlockAttrsF in WRAM
CELLAR_SOURCE_ROOM = 0x527            # the room a cellar returns to
IS_UPDATING_MODE = 0x11
CELLAR_MODE = 0x09
ITEM_X, ITEM_Y = OBJ_X + 0x13, OBJ_Y + 0x13   # the room item's object slot
LEDGE_ITEM_PLACE = (0x80, 0x90)
RIGHT_LADDER_X = 0xB0
# Inventory bytes a cellar item changes when taken (not the rupees or the
# partial heart, which change on their own).
INVENTORY = [address for address in range(ITEMS, 0x680) if address not in (0x66D, 0x670)]
LEVEL_LOAD_FRAMES, SETTLE_FRAMES = 900, 40


@cache
def _finished() -> tuple[GameWorld, bytes]:
    world = parse_rom(vanilla())
    generate_shapes(world, Rng(SEED), ShapeOptions())
    return world, serialize_to_rom(world, vanilla(), config=GameConfig(features_b10=True))


def _cellar(world: GameWorld, level_num: int) -> StaircaseRoom:
    level = next(level for level in world.levels if level.level_num == level_num)
    return next(stair for stair in level.block.staircases
                if stair.room_type == RoomType.ITEM_STAIRCASE and stair.return_dest in level.room_nums)


def _walk_the_cellar(rom: bytes, level_num: int, stair: StaircaseRoom,
                     attrs_f: int | None = None) -> tuple[tuple[int, int], bool]:
    """Load the level, step down into its item cellar (as its staircase
    does), and walk the whole cellar: down the left ladder, to the right
    ladder, up it and along the upper ledge both ways. Returns where the
    item stands and whether Link took it. attrs_f overrides the cellar's
    LevelBlockAttrsF byte in WRAM."""
    emu = Emulator(rom)
    emu.new_game()
    emu[CUR_LEVEL] = level_num
    emu[GAME_MODE] = Mode.LOAD_LEVEL
    emu[GAME_SUBMODE] = 0
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[CUR_LEVEL] == level_num, limit=LEVEL_LOAD_FRAMES)
    emu.run(SETTLE_FRAMES)
    if attrs_f is not None:
        emu[LEVEL_BLOCK_ATTRS_F + stair.room_num] = attrs_f
    assert stair.return_dest is not None
    emu[CELLAR_SOURCE_ROOM] = stair.return_dest
    emu[ROOM_ID] = stair.room_num
    emu[GAME_MODE] = CELLAR_MODE
    emu[IS_UPDATING_MODE] = 0
    emu[GAME_SUBMODE] = 0
    emu.run_until(lambda: emu.mode == CELLAR_MODE and emu[IS_UPDATING_MODE] == 1)
    place = (emu[ITEM_X], emu[ITEM_Y])
    before = [emu[address] for address in INVENTORY]

    def taken() -> bool:
        return [emu[address] for address in INVENTORY] != before

    def hold(buttons: Button, frames: int) -> bool:
        for _ in range(frames):
            emu.run(1, buttons)
            if taken():
                return True
        return False

    def walk_to_right_ladder() -> bool:
        for _ in range(300):
            if emu[OBJ_X] == RIGHT_LADDER_X:
                return False
            emu.run(1, Button.RIGHT if emu[OBJ_X] < RIGHT_LADDER_X else Button.LEFT)
            if taken():
                return True
        return False

    took = (hold(Button.DOWN, 120) or walk_to_right_ladder() or hold(Button.UP, 120)
            or hold(Button.RIGHT, 80) or hold(Button.LEFT, 200) or hold(Button.RIGHT, 200))
    return place, took


@pytest.mark.parametrize("level_num", [1, 4, 5])
def test_link_takes_the_cellar_item(level_num: int) -> None:
    world, rom = _finished()
    assert _walk_the_cellar(rom, level_num, _cellar(world, level_num)) == (LEDGE_ITEM_PLACE, True)


def test_old_position_bits_leave_level_5s_item_in_the_air() -> None:
    """The bug this guards against: $00 bits put level 5's item at its first
    position ($87: X $80, Y $70), above the ledge, out of reach."""
    world, rom = _finished()
    assert _walk_the_cellar(rom, 5, _cellar(world, 5), attrs_f=0x00) == ((0x80, 0x70), False)
