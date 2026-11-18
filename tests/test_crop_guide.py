"""The crop guide on the file-select screen (asm/crop-guide): a white square in each corner cell and a
blue one a cell in diagonally, and nothing else on the screen changed. Checked in the emulator
(tests/emulator.py, cynes) with a registered file, so the death counts the guide's records follow are
drawn too. It is a player setting (PlayerSettings.crop_guide, the page's Cosmetic tab), on by default: off
puts the hook's two instructions back, and the corners are blank."""
from functools import cache

import numpy as np
import pytest

from tests.emulator import Emulator
from tests.test_feature_patches import vanilla
from tests.test_seed_code_icons import nes_palette
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import PRG1_ROM_PATH
from zora.rom.player_settings import PlayerSettings, apply_player_settings

SEED = 12345
NAMETABLE = 0x2000
NAMETABLE_TILES = 0x3C0                 # 30 rows of 32, then the attribute table
ROW_TILES = 32
TILE_PIXELS = 8
WHITE_TILE, BLUE_TILE = 0x25, 0x27
WHITE, BLUE = 0x30, 0x12                # background palette 0's colors 1 and 3 on this screen
WHITE_CELLS = ((0, 0), (0, 31), (29, 0), (29, 31))           # (row, column)
BLUE_CELLS = ((1, 1), (1, 30), (28, 1), (28, 30))
GUIDE = {**dict.fromkeys(WHITE_CELLS, WHITE_TILE), **dict.fromkeys(BLUE_CELLS, BLUE_TILE)}
# asm/crop-guide's hook: InitMode1_Sub6's LDA #$00 / STA $0A
HOOK_OFFSET, HOOK_LENGTH = 0x0A539, 4


@cache
def finished(base: bytes) -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base).rom


def file_select(rom: bytes) -> Emulator:
    emu = Emulator(rom)
    emu.boot_to_file_select()
    emu.register_file(b"\x0a\x0b")
    return emu


def screen_tiles(emu: Emulator) -> bytes:
    return emu.nametable(NAMETABLE, NAMETABLE_TILES)


def assert_guide_shown(emu: Emulator) -> None:
    tiles = screen_tiles(emu)
    palette = nes_palette()
    for (row, column), tile in GUIDE.items():
        assert tiles[row * ROW_TILES + column] == tile, (row, column)
        top, left = row * TILE_PIXELS, column * TILE_PIXELS
        cell = emu.last_frame[top:top + TILE_PIXELS, left:left + TILE_PIXELS]
        color = palette[WHITE if tile == WHITE_TILE else BLUE]
        assert (cell == np.array(color, dtype=np.uint8)).all(), (row, column)


def test_the_guide_is_drawn_in_white_and_blue() -> None:
    assert_guide_shown(file_select(finished(vanilla())))


def test_nothing_else_on_the_screen_changes() -> None:
    """The same ROM with the hook's two instructions put back draws the screen with blank corners
    and every other tile the same, the save file's name and death count included."""
    rom = finished(vanilla())
    without = bytearray(rom)
    without[HOOK_OFFSET:HOOK_OFFSET + HOOK_LENGTH] = vanilla()[HOOK_OFFSET:HOOK_OFFSET + HOOK_LENGTH]
    shown, plain = screen_tiles(file_select(rom)), screen_tiles(file_select(bytes(without)))
    differing = {(index // ROW_TILES, index % ROW_TILES) for index, (a, b) in enumerate(zip(shown, plain))
                 if a != b}
    assert differing == set(GUIDE)


def test_prg1_draws_the_guide() -> None:
    if not PRG1_ROM_PATH.exists():
        pytest.skip("needs the PRG1 ROM")
    assert_guide_shown(file_select(finished(PRG1_ROM_PATH.read_bytes())))


def without_guide(rom: bytes) -> bytes:
    """`rom` with the hook's two instructions put back, as the setting's Off writes it."""
    plain = bytearray(rom)
    plain[HOOK_OFFSET:HOOK_OFFSET + HOOK_LENGTH] = vanilla()[HOOK_OFFSET:HOOK_OFFSET + HOOK_LENGTH]
    return bytes(plain)


def test_the_setting_is_on_by_default_and_off_leaves_the_corners_blank() -> None:
    """Crop guide (Cosmetic tab): on by default, as before it was a setting; off writes only the hook back,
    so no guide tile is drawn; turning it on again on the finished ROM brings the guide back."""
    assert PlayerSettings().crop_guide
    rom = finished(vanilla())
    off = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, vanilla(), PlayerSettings(crop_guide=False)).rom
    assert off == without_guide(rom) == apply_player_settings(rom, PlayerSettings(crop_guide=False))
    tiles = screen_tiles(file_select(off))
    assert all(tiles[row * ROW_TILES + column] != tile for (row, column), tile in GUIDE.items())
    assert apply_player_settings(off, PlayerSettings()) == rom
