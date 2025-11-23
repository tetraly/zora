"""Build minimal test ROMs from extracted data chunks.

This module reconstructs a minimal ROM file from the extracted binary chunks
in the tests/data/ directory. The ROM is padded with 0xFF bytes everywhere except
the regions that are actually read by the RomState and Validator.
"""

import io
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rom.rom_config import RomLayout, NES_HEADER_SIZE


# Standard NES ROM size (128 KB including 16-byte header)
NES_ROM_SIZE = 0x20010  # 131088 bytes


# Mapping of test data files to their ROM regions
# Format: filename -> RomRegion (or tuple of (file_offset, size) for special cases)
TEST_DATA_REGIONS = {
    'nes_header.bin': (0, NES_HEADER_SIZE),  # Special: NES header at offset 0
    'armos_item.bin': RomLayout.ARMOS_ITEM,
    'coast_item.bin': RomLayout.COAST_ITEM,
    'mixed_enemy_data.bin': (0x14686, 0xD0),  # Special: not in RomLayout yet
    'mixed_enemy_pointers.bin': RomLayout.MIXED_ENEMY_POINTER_TABLE,
    'level_pointers.bin': (0x18010, 0x10),  # Combined pointer region
    'overworld_data.bin': RomLayout.OVERWORLD_DATA,
    'level_1_6_data.bin': RomLayout.LEVEL_1_TO_6_FIRST_QUEST_DATA,
    'level_7_9_data.bin': RomLayout.LEVEL_7_TO_9_FIRST_QUEST_DATA,
    'level_info.bin': RomLayout.LEVEL_INFO,
}


def build_minimal_rom(testdata_dir: str = 'data') -> io.BytesIO:
    """Build a minimal ROM from extracted test data.

    Creates a ROM filled with 0xFF bytes, then overlays the actual data
    from the extracted binary files in the correct positions.

    Args:
        testdata_dir: Directory containing the extracted .bin files
                      (relative to this file's directory, defaults to 'data')

    Returns:
        BytesIO object containing the minimal ROM data

    Raises:
        FileNotFoundError: If testdata directory or required files don't exist
    """
    # Resolve testdata_dir relative to this file's directory
    testdata_path = Path(__file__).parent / testdata_dir

    if not testdata_path.exists():
        raise FileNotFoundError(
            f"Test data directory not found: {testdata_path}\n"
            f"Run 'python3 tests/extract_test_data.py roms/z1-prg1.nes' to generate it."
        )

    # Create a ROM filled with 0xFF
    rom_data = bytearray([0xFF] * NES_ROM_SIZE)

    # Overlay each data region from extracted test files
    for filename, region in TEST_DATA_REGIONS.items():
        filepath = testdata_path / filename

        if not filepath.exists():
            raise FileNotFoundError(
                f"Missing test data file: {filepath}\n"
                f"Run 'python3 tests/extract_test_data.py roms/z1-prg1.nes' to generate it."
            )

        with open(filepath, 'rb') as f:
            data = f.read()

        # Get file_offset from region (either RomRegion or tuple)
        if isinstance(region, tuple):
            file_offset = region[0]
        else:
            file_offset = region.file_offset

        rom_data[file_offset:file_offset + len(data)] = data

    return io.BytesIO(bytes(rom_data))


def verify_minimal_rom(rom: io.BytesIO) -> bool:
    """Verify that a minimal ROM has the expected structure.

    Args:
        rom: BytesIO object containing ROM data

    Returns:
        True if the ROM appears valid, False otherwise
    """
    rom.seek(0)
    data = rom.read()

    # Check ROM size
    if len(data) != NES_ROM_SIZE:
        print(f"Error: ROM size is {len(data)}, expected {NES_ROM_SIZE}")
        return False

    # Check NES header magic bytes (should be "NES" + 0x1A)
    rom.seek(0)
    header = rom.read(4)
    if header != b'NES\x1a':
        print(f"Error: Invalid NES header: {header}")
        return False

    # Check that level pointers are set correctly (using file_offset from config)
    rom.seek(0x18010)  # file_offset for overworld pointer
    overworld_ptr = rom.read(2)
    if overworld_ptr != b'\x00\x84':  # Little-endian 0x8400
        print(f"Error: Invalid overworld pointer: {overworld_ptr.hex()}")
        return False

    rom.seek(0x18012)  # file_offset + 2 for level 1-6 pointer
    level_1_6_ptr = rom.read(2)
    if level_1_6_ptr != b'\x00\x87':  # Little-endian 0x8700
        print(f"Error: Invalid level 1-6 pointer: {level_1_6_ptr.hex()}")
        return False

    rom.seek(0x1801E)  # file_offset + 0x0E for level 7-9 pointer
    level_7_9_ptr = rom.read(2)
    if level_7_9_ptr != b'\x00\x8a':  # Little-endian 0x8A00
        print(f"Error: Invalid level 7-9 pointer: {level_7_9_ptr.hex()}")
        return False

    return True
