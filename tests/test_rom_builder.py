"""Build minimal test ROMs from extracted data chunks.

This module reconstructs a minimal ROM file from the extracted binary chunks
in the tests/data/ directory. The ROM is padded with 0xFF bytes everywhere except
the regions that are actually read by the DataTable and Validator.
"""

import io
import yaml
from pathlib import Path


# Standard NES ROM size (128 KB including 16-byte header)
NES_ROM_SIZE = 0x20010  # 131088 bytes


def load_rom_config(config_path: str = None) -> dict:
    """Load ROM region definitions from config file.

    Args:
        config_path: Path to the YAML config file (defaults to ../rom_config.yaml)

    Returns:
        Dictionary of ROM regions
    """
    if config_path is None:
        # Default to rom_config.yaml in parent directory (project root)
        config_path = Path(__file__).parent.parent / 'rom_config.yaml'
    else:
        config_path = Path(config_path)

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config['rom_regions']


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

    # Load ROM region config
    try:
        rom_regions = load_rom_config()
    except FileNotFoundError:
        raise FileNotFoundError(
            "rom_config.yaml not found. Ensure it's in the project root directory."
        )

    # Create a ROM filled with 0xFF
    rom_data = bytearray([0xFF] * NES_ROM_SIZE)

    # Overlay each data region
    for region_name, region_info in rom_regions.items():
        # Skip regions without test data
        if region_info.get('test_data') is None:
            continue

        filename = region_info['test_data']
        filepath = testdata_path / filename

        if not filepath.exists():
            raise FileNotFoundError(
                f"Missing test data file: {filepath}\n"
                f"Run 'python3 tests/extract_test_data.py roms/z1-prg1.nes' to generate it."
            )

        with open(filepath, 'rb') as f:
            data = f.read()

        # Use file_offset directly (already includes 0x10 header offset)
        file_offset = region_info['file_offset']
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
