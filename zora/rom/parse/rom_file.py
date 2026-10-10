"""The ROM-file entry points: load a ROM, parse it, slice its raw tables."""

from pathlib import Path

from ...model.game_world import GameWorld
from ..base_rom import remember_base_rom
from ..game_config import GameConfig
from ..layout import (
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_INFO_ADDRESS,
    NES_HEADER_SIZE,
    OVERWORLD_DATA_ADDRESS,
)
from .bin_files import load_bin_files_from_rom
from .game_world import parse_game_world

# ---------------------------------------------------------------------------
# ROM-level entry points
# ---------------------------------------------------------------------------

_NES_ROM_SIZE_CHECK = NES_HEADER_SIZE + 0x20000


def load_rom(path: Path) -> bytes:
    """Read a full .nes file and validate size + iNES magic."""
    rom = path.read_bytes()
    if len(rom) != _NES_ROM_SIZE_CHECK:
        raise ValueError(f"{path}: expected {_NES_ROM_SIZE_CHECK} bytes, got {len(rom)}")
    if rom[:4] != b"NES\x1a":
        raise ValueError(f"{path}: not an iNES file")
    return rom


def parse_rom(rom: bytes, config: GameConfig | None = None) -> GameWorld:
    """Parse a full .nes ROM image into a GameWorld (no randomizer magic check).

    Accepts vanilla and randomized ROMs alike; regions not present in a vanilla
    ROM (e.g. the boss expansion sprites block) are read from wherever the
    layout constants say they live. A PRG0 ROM is remembered as the player's ROM,
    the source of the original bytes the patches keep or move (base_rom.Original).
    """
    remember_base_rom(rom)
    return parse_game_world(load_bin_files_from_rom(rom), config=config,
                            rom_bytes=rom)


def parse_rom_file(path: Path,
                   config: GameConfig | None = None) -> tuple[GameWorld, bytes]:
    """Convenience: read file → (GameWorld, raw rom bytes)."""
    rom = load_rom(path)
    return parse_rom(rom, config=config), rom


def original_bins_from_rom(rom: bytes) -> dict[str, bytes]:
    """The dict of bin-name → bytes that serialize_game_world expects, sliced
    straight from a ROM image. Keys match the historical .bin filenames.

    NOTE: overworld_data is exactly 6 tables x 0x80 = 0x300 bytes; the old
    0x500 slices bled into the level grids and silently clobbered them on
    serialize (round-trips hid it because the bytes started identical)."""
    return {
        "level_1_6_data.bin": rom[LEVEL_1_6_DATA_ADDRESS: LEVEL_1_6_DATA_ADDRESS + 0x300],
        "level_7_9_data.bin": rom[LEVEL_7_9_DATA_ADDRESS: LEVEL_7_9_DATA_ADDRESS + 0x300],
        "level_info.bin":     rom[LEVEL_INFO_ADDRESS: LEVEL_INFO_ADDRESS + 0xA * 0xFC],
        "overworld_data.bin": rom[OVERWORLD_DATA_ADDRESS: OVERWORLD_DATA_ADDRESS + 0x300],
    }
