#!/usr/bin/env python3
"""Extract minimal ROM data needed for validator tests.

This script extracts only the portions of the ROM that are actually read
by the DataTable and Validator classes, saving them as separate binary files
in the tests/data/ directory. This allows tests to run without checking in the
full ROM file.

Usage:
    python3 tests/extract_test_data.py roms/z1-prg1.nes
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rom.rom_config import RomLayout, NES_HEADER_SIZE


# Mapping of RomLayout regions to test data filenames
# Only regions listed here will be extracted
TEST_DATA_REGIONS = {
    'NES_HEADER': ('nes_header.bin', 0, NES_HEADER_SIZE),  # Special case: offset 0, not from RomLayout
    'ARMOS_ITEM': ('armos_item.bin', RomLayout.ARMOS_ITEM),
    'COAST_ITEM': ('coast_item.bin', RomLayout.COAST_ITEM),
    'MIXED_ENEMY_DATA': ('mixed_enemy_data.bin', 0x14686, 0xD0),  # Special: not in RomLayout yet
    'MIXED_ENEMY_POINTERS': ('mixed_enemy_pointers.bin', RomLayout.MIXED_ENEMY_POINTER_TABLE),
    'LEVEL_POINTERS': ('level_pointers.bin', 0x18010, 0x10),  # Combined pointer region
    'OVERWORLD_DATA': ('overworld_data.bin', RomLayout.OVERWORLD_DATA),
    'LEVEL_1_6_DATA': ('level_1_6_data.bin', RomLayout.LEVEL_1_TO_6_FIRST_QUEST_DATA),
    'LEVEL_7_9_DATA': ('level_7_9_data.bin', RomLayout.LEVEL_7_TO_9_FIRST_QUEST_DATA),
    'LEVEL_INFO': ('level_info.bin', RomLayout.LEVEL_INFO),
}


def extract_rom_data(rom_path: str, output_dir: str = 'data') -> None:
    """Extract required ROM data regions to separate binary files.

    Args:
        rom_path: Path to the source ROM file (z1-prg1.nes)
        output_dir: Directory to save extracted data files (relative to this script, default: data)
    """
    rom_path = Path(rom_path)
    # Resolve output_dir relative to this script's directory
    output_dir = Path(__file__).parent / output_dir

    if not rom_path.exists():
        print(f"Error: ROM file not found: {rom_path}")
        sys.exit(1)

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read the ROM file
    with open(rom_path, 'rb') as f:
        rom_data = f.read()

    rom_size = len(rom_data)
    print(f"Reading ROM: {rom_path} ({rom_size} bytes)")
    print(f"Output directory: {output_dir}")
    print()

    # Extract each data region
    extracted_count = 0
    for region_name, region_info in TEST_DATA_REGIONS.items():
        filename = region_info[0]

        # Handle different tuple formats
        if len(region_info) == 3:
            # Tuple: (filename, file_offset, size)
            file_offset = region_info[1]
            size = region_info[2]
            cpu_addr = None
        else:
            # Tuple: (filename, RomRegion)
            rom_region = region_info[1]
            file_offset = rom_region.file_offset
            size = rom_region.size
            cpu_addr = rom_region.cpu_address

        output_path = output_dir / filename

        # Extract data from ROM
        data = rom_data[file_offset:file_offset + size]

        # Verify we got the expected amount of data
        if len(data) != size:
            print(f"Warning: Expected {size} bytes but got {len(data)} bytes for {region_name}")

        # Write to file
        with open(output_path, 'wb') as f:
            f.write(data)

        if cpu_addr is not None:
            print(f"  ✓ {filename:30s} {size:4d} bytes  [file: 0x{file_offset:05X}, cpu: 0x{cpu_addr:05X}]")
        else:
            print(f"  ✓ {filename:30s} {size:4d} bytes  [file: 0x{file_offset:05X}]")
        extracted_count += 1

    print()
    print(f"Successfully extracted {extracted_count} data files to {output_dir}/")
    print("These files can now be used for testing without the full ROM.")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        print(f"Usage: {sys.argv[0]} <path_to_rom.nes>")
        sys.exit(1)

    rom_path = sys.argv[1]
    extract_rom_data(rom_path)


if __name__ == '__main__':
    main()
