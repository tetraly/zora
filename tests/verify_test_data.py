#!/usr/bin/env python3
"""Verify that test data files are present and valid.

This script checks that all required test data files exist and that they
can be used to build a valid minimal ROM for testing.

Usage:
    python3 tests/verify_test_data.py
"""

import sys
from pathlib import Path
from test_rom_builder import build_minimal_rom, verify_minimal_rom, load_rom_config


def main():
    testdata_dir = Path(__file__).parent / 'data'

    print("Checking test data files...")
    print("=" * 70)

    # Check if directory exists
    if not testdata_dir.exists():
        print(f"❌ Test data directory not found: {testdata_dir}")
        print("\nTo generate test data, run:")
        print("    python3 tests/extract_test_data.py roms/z1-prg1.nes")
        sys.exit(1)

    # Load config
    try:
        rom_regions = load_rom_config()
    except FileNotFoundError:
        print("❌ rom_config.yaml not found")
        sys.exit(1)

    # Check each required file
    all_files_present = True
    total_size = 0

    for region_name, region_info in rom_regions.items():
        # Skip regions without test data
        if region_info.get('test_data') is None:
            continue

        filename = region_info['test_data']
        filepath = testdata_dir / filename

        if filepath.exists():
            size = filepath.stat().st_size
            total_size += size
            file_offset = region_info['file_offset']
            cpu_addr = region_info.get('cpu_address')
            if cpu_addr is not None:
                print(f"✓ {filename:30s} {size:4d} bytes  [0x{file_offset:05X} / 0x{cpu_addr:05X}]")
            else:
                print(f"✓ {filename:30s} {size:4d} bytes  [0x{file_offset:05X}]")
        else:
            print(f"❌ {filename:30s} MISSING")
            all_files_present = False

    print("=" * 70)
    print(f"Total size: {total_size} bytes (~{total_size / 1024:.1f} KB)")

    if not all_files_present:
        print("\n❌ Some test data files are missing!")
        print("\nTo generate test data, run:")
        print("    python3 tests/extract_test_data.py roms/z1-prg1.nes")
        sys.exit(1)

    # Try to build and verify the ROM
    print("\nBuilding minimal ROM from test data...")
    try:
        rom = build_minimal_rom('data')
        print("✓ Successfully built minimal ROM")
    except Exception as e:
        print(f"❌ Failed to build ROM: {e}")
        sys.exit(1)

    print("\nVerifying ROM structure...")
    if verify_minimal_rom(rom):
        print("✓ ROM structure is valid")
    else:
        print("❌ ROM structure verification failed")
        sys.exit(1)

    # Get ROM info
    rom.seek(0)
    data = rom.read()
    non_ff_bytes = sum(1 for b in data if b != 0xFF)

    print("\nROM Statistics:")
    print(f"  Total size:     {len(data):6d} bytes ({len(data) // 1024} KB)")
    print(f"  Data bytes:     {non_ff_bytes:6d} bytes")
    print(f"  Padding (0xFF): {len(data) - non_ff_bytes:6d} bytes")
    print(f"  Efficiency:     {(1 - non_ff_bytes / len(data)) * 100:.1f}% padding")

    print("\n✓ All checks passed! Test data is ready for use.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
