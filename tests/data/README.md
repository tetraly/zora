# Test Data Directory

This directory contains extracted binary data from the Zelda 1 ROM needed for validator tests.

## Contents

The test data consists of 10 binary files totaling ~5.0 KB (vs 128 KB for the full ROM):

- `nes_header.bin` (16 bytes) - iNES ROM header
- `armos_item.bin` (1 byte) - Item at the Armos location
- `coast_item.bin` (1 byte) - Item at the coast location
- `level_pointers.bin` (16 bytes) - Pointers to overworld and dungeon data blocks
- `overworld_data.bin` (768 bytes) - All overworld screen/cave data
- `level_1_6_data.bin` (768 bytes) - Dungeon room data for levels 1-6
- `level_7_9_data.bin` (768 bytes) - Dungeon room data for levels 7-9
- `level_info.bin` (2520 bytes) - Level metadata (start rooms, stairways, etc.)
- `mixed_enemy_pointers.bin` (60 bytes) - Pointers to mixed enemy group data
- `mixed_enemy_data.bin` (208 bytes) - Mixed enemy group definitions

All regions and addresses are defined in `rom_config.yaml` in the project root.

## Generating Test Data

To generate these files from your ROM:

```bash
python3 tests/extract_test_data.py roms/z1-prg1.nes
```

This will extract only the portions of the ROM that are actually read by the DataTable and Validator classes.

## Verifying Test Data

To verify all test data files are present and valid:

```bash
python3 tests/verify_test_data.py
```

## How It Works

The test fixture in `tests/test_validator.py` uses `test_rom_builder.build_minimal_rom()` to construct a 128 KB ROM filled with 0xFF bytes, then overlays the extracted data chunks in the correct file offsets. This creates a minimal ROM that works for testing without needing the full ROM file in the repository.

## Address Convention

All addresses in `rom_config.yaml` follow this convention:
- **file_offset**: Byte offset in the .nes file (includes 0x10 iNES header)
- **cpu_address**: NES CPU memory address (no header offset)
- Relationship: `file_offset = cpu_address + 0x10`

When viewing a ROM in a hex editor, use the file_offset addresses. This prevents off-by-0x10 errors.

## Why Not Check In the Full ROM?

- **Copyright**: ROMs are copyrighted and shouldn't be distributed
- **Size**: The full ROM is 128 KB, but we only need ~5.0 KB of data
- **Clarity**: This approach documents exactly what data the validator needs
- **Single source of truth**: ROM regions are defined once in `rom_config.yaml`
