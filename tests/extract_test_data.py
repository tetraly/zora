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
import yaml
from pathlib import Path


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

    # Load ROM region config
    try:
        rom_regions = load_rom_config()
    except FileNotFoundError:
        print("Error: rom_config.yaml not found")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing rom_config.yaml: {e}")
        sys.exit(1)

    # Read the ROM file
    with open(rom_path, 'rb') as f:
        rom_data = f.read()

    rom_size = len(rom_data)
    print(f"Reading ROM: {rom_path} ({rom_size} bytes)")
    print(f"Output directory: {output_dir}")
    print()

    # Extract each data region
    extracted_count = 0
    for region_name, region_info in rom_regions.items():
        # Skip regions without test data
        if region_info.get('test_data') is None:
            continue

        file_offset = region_info['file_offset']
        size = region_info['size']
        filename = region_info['test_data']
        output_path = output_dir / filename

        # Extract data from ROM
        data = rom_data[file_offset:file_offset + size]

        # Verify we got the expected amount of data
        if len(data) != size:
            print(f"Warning: Expected {size} bytes but got {len(data)} bytes for {region_name}")

        # Write to file
        with open(output_path, 'wb') as f:
            f.write(data)

        cpu_addr = region_info.get('cpu_address')
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
