"""Transport cellars hold no item (post-shapes-b1.md PS-DROP-01: a transport's item byte is the
"no item" code). Under Randomize Magical Sword "no item" is $0E (docs/zora-extras.md section 6), so
a transport written with $03 showed a magical sword that Link could take."""
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.emulator import (
    CUR_LEVEL,
    GAME_MODE,
    GAME_SUBMODE,
    ITEMS,
    OBJ_STATE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    ROOM_ITEM_SLOT,
    Emulator,
    Mode,
)
from zora.generate.pipeline import generate_rom, plan
from zora.model.enums import RoomType
from zora.model.game_world import GameWorld
from zora.model.rooms import StaircaseRoom
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.game_config import DungeonNothingCode, GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.levels import encode_level_block

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

MAGICAL_SWORD_CASE = "magical sword and letter"
SEED = 1
ITEM_TABLE = 4                        # LevelBlockAttrsE: the room item byte
ITEM_CODE_MASK = 0x1F
CELLAR_SOURCE_ROOM = 0x527            # the room a cellar returns to
IS_UPDATING_MODE = 0x11
CELLAR_MODE = 0x09
NO_OBJECT = 0xFF                      # the room item slot's state when the room has no item
SWORD = ITEMS                         # the sword byte of the inventory
LEVEL_LOAD_FRAMES, SETTLE_FRAMES, TAKE_FRAMES = 900, 40, 120


def _transports(world: GameWorld) -> list[tuple[int, StaircaseRoom]]:
    return [(level.level_num, stair) for level in world.levels for stair in level.staircase_rooms
            if stair.room_type == RoomType.TRANSPORT_STAIRCASE]


@pytest.mark.parametrize("nothing_code", list(DungeonNothingCode))
def test_a_transport_holds_the_roms_no_item_code(nothing_code: DungeonNothingCode) -> None:
    world = parse_rom(remember_repo_base_rom())
    for _, stair in _transports(world):
        block = next(level.block for level in world.levels if stair in level.staircase_rooms)
        item_table = encode_level_block(block, nothing_code)[ITEM_TABLE * 0x80:(ITEM_TABLE + 1) * 0x80]
        assert item_table[stair.room_num] & ITEM_CODE_MASK == nothing_code


@cache
def _magical_sword_rom() -> tuple[GameWorld, bytes]:
    flags, zora_flags = FLAG_CASES[MAGICAL_SWORD_CASE]
    config = plan(flags, SEED, zora_flags).config
    assert config.dungeon_nothing_code == DungeonNothingCode.ZORA_REMAP
    rom = generate_rom(flags, SEED, remember_repo_base_rom(), zora_flag_string=zora_flags).rom
    return parse_rom(rom, GameConfig(dungeon_nothing_code=config.dungeon_nothing_code,
                                      hint_mode=config.hint_mode)), rom


def test_a_transport_cellar_shows_and_gives_nothing_with_randomize_magical_sword() -> None:
    """In the emulator: Link stepped down into a transport cellar finds no room item, and standing
    where a cellar item would stand gives him nothing (9f03ca3 gave him a sword there)."""
    world, rom = _magical_sword_rom()
    level_num, stair = _transports(world)[0]
    emu = Emulator(rom)
    emu.new_game()
    emu[CUR_LEVEL] = level_num
    emu[GAME_MODE] = Mode.LOAD_LEVEL
    emu[GAME_SUBMODE] = 0
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[CUR_LEVEL] == level_num, limit=LEVEL_LOAD_FRAMES)
    emu.run(SETTLE_FRAMES)
    assert stair.left_exit is not None
    emu[CELLAR_SOURCE_ROOM] = stair.left_exit
    emu[ROOM_ID] = stair.room_num
    emu[GAME_MODE] = CELLAR_MODE
    emu[IS_UPDATING_MODE] = 0
    emu[GAME_SUBMODE] = 0
    emu.run_until(lambda: emu.mode == CELLAR_MODE and emu[IS_UPDATING_MODE] == 1)
    assert emu[OBJ_STATE + ROOM_ITEM_SLOT] == NO_OBJECT
    sword = emu[SWORD]
    emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + ROOM_ITEM_SLOT], emu[OBJ_Y + ROOM_ITEM_SLOT]
    emu.run(TAKE_FRAMES)
    assert emu[SWORD] == sword
