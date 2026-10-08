"""The emulator harness (tests/emulator.py) on PRG0: the file-select screen,
registering a file, the start of the game and walking."""
import os
from pathlib import Path

import pytest

from tests.emulator import (
    CHR_RAM_SIZE, CUR_LEVEL, FRAME_COUNTER, OBJ_DIR, OBJ_X, OBJ_Y, ROOM_ID, Button, Direction, Emulator, Mode,
)
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.layout import NES_HEADER_SIZE
from zora.rom.text_encoding import CHAR_TO_BYTE

START_SCREEN = 0x77
START_X, START_Y = 0x78, 0x8D
# "REGISTER" on the file-select menu (Mode1TileTransferBuf), at PPU $22A6.
REGISTER_TEXT_ADDRESS = 0x22A6
# CommonSpritePatterns and CommonBackgroundPatterns (offsets from src/bins.xml)
COMMON_SPRITE_PATTERNS = NES_HEADER_SIZE + 32895
COMMON_BACKGROUND_PATTERNS = NES_HEADER_SIZE + 34687
REGISTER_TEXT = bytes(CHAR_TO_BYTE[letter] for letter in "REGISTER")      # its tiles


def _vanilla() -> Path:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    return verify_base_rom(cand)


def test_boots_to_file_select_and_reads_the_nametable() -> None:
    emu = Emulator(_vanilla())
    emu.boot_to_file_select()
    assert emu.mode == Mode.FILE_SELECT
    assert emu.nametable(REGISTER_TEXT_ADDRESS, len(REGISTER_TEXT)) == REGISTER_TEXT


def test_reads_the_pattern_tables() -> None:
    """PRG0 loads its common sprite and background patterns at CHR $0000
    and $1000 (PatternBlockPpuAddrs)."""
    emu = Emulator(_vanilla())
    emu.new_game()
    rom = _vanilla().read_bytes()
    patterns = emu.pattern_tables()
    assert len(patterns) == CHR_RAM_SIZE
    for chr_address, file_offset in ((0x0000, COMMON_SPRITE_PATTERNS), (0x1000, COMMON_BACKGROUND_PATTERNS)):
        assert patterns[chr_address:chr_address + 256] == rom[file_offset:file_offset + 256]


def test_registers_starts_and_walks() -> None:
    emu = Emulator(_vanilla())
    emu.new_game()
    assert emu.mode == Mode.PLAY
    assert (emu[CUR_LEVEL], emu[ROOM_ID]) == (0, START_SCREEN)
    assert (emu[OBJ_X], emu[OBJ_Y], emu[OBJ_DIR]) == (START_X, START_Y, Direction.UP)

    counter = emu[FRAME_COUNTER]
    frames = emu.frames
    emu.run(24, Button.LEFT)
    assert emu.frames == frames + 24
    assert emu[FRAME_COUNTER] == (counter + 24) % 256
    assert emu[OBJ_X] < START_X and emu[OBJ_DIR] == Direction.LEFT
    emu.run(24, Button.UP)
    assert emu[OBJ_Y] < START_Y and emu[OBJ_DIR] == Direction.UP
    assert emu[ROOM_ID] == START_SCREEN
