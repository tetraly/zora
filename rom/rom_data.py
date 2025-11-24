"""ROM data container and loading functions.

This module provides:
- RomData: A pure data container for all ROM state
- Loading functions: load_from_file, load_from_bytes, load_from_test_data
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import zlib

from .rom_config import (
    NES_HEADER_SIZE,
    RomLayout,
    LEVEL_INFO_BLOCK_SIZE,
    LEVEL_INFO_PPU_PALETTE_SIZE,
    LEVEL_TABLE_SIZE,
    FIRST_MIXED_GROUP_CODE,
    MIXED_GROUP_POINTER_COUNT,
)
from logic.randomizer_constants import Enemy


@dataclass
class RomData:
    """Pure data container for all ROM state needed by the randomizer.

    This class holds the raw data extracted from a ROM file. It does not
    contain any business logic - that lives in RomState.

    All fields use List[int] for byte data to match existing code conventions.
    """

    # Main level data blocks (each 0x300 bytes = 128 rooms * 6 tables)
    level_1_to_6_block: List[int] = field(default_factory=lambda: [0] * 0x300)
    level_7_to_9_block: List[int] = field(default_factory=lambda: [0] * 0x300)
    overworld_block: List[int] = field(default_factory=lambda: [0] * 0x300)

    # Level metadata (10 levels, each with meaningful data after skipping PPU palette)
    # Each entry is the meaningful portion of the level info (0xFC - 0x24 = 0xD8 bytes)
    level_info: List[List[int]] = field(default_factory=list)

    # Raw level info for reset functionality
    level_info_raw: List[List[int]] = field(default_factory=list)

    # Individual overworld items
    armos_item: int = 0
    coast_item: int = 0

    # Mixed enemy group data
    mixed_enemy_groups: Dict[int, List[Enemy]] = field(default_factory=dict)

    # ROM metadata (for detection purposes, not used in game logic)
    is_z1r: bool = True  # Whether this is a Z1R (randomized) ROM

    # Level block pointers (for quest detection)
    overworld_pointer: int = 0
    level_1_to_6_pointer: int = 0
    level_7_to_9_pointer: int = 0

    # Recorder warp data (8 bytes each, one per level 1-8)
    recorder_warp_destinations: List[int] = field(default_factory=lambda: [0] * 8)
    recorder_warp_y_coordinates: List[int] = field(default_factory=lambda: [0] * 8)

    # Any Road screens (4 bytes)
    any_road_screens: List[int] = field(default_factory=lambda: [0] * 4)


def _read_word_little_endian(data: bytes, offset: int) -> int:
    """Read a 16-bit word in little-endian format."""
    return data[offset] | (data[offset + 1] << 8)


def _cpu_address_to_rom_offset(cpu_address: int) -> int:
    """Convert a CPU address in bank 5 to a ROM file offset.

    Bank 5 occupies CPU addresses $8000-$BFFF, which corresponds to
    ROM file addresses $14010-$17FFF (including 0x10 header).
    """
    BANK_5_CPU_START = 0x8000
    BANK_5_ROM_START = 0x14010  # file_offset (includes header)

    if cpu_address < BANK_5_CPU_START:
        raise ValueError(f"CPU address 0x{cpu_address:04X} is below bank 5 range")

    offset_in_bank = cpu_address - BANK_5_CPU_START
    rom_offset = BANK_5_ROM_START + offset_in_bank
    return rom_offset


def _read_mixed_enemy_groups(rom_bytes: bytes) -> Dict[int, List[Enemy]]:
    """Read all mixed enemy group data from ROM bytes.

    Mixed enemy groups are referenced by enemy codes 0x62-0x7F (98-127).
    These codes index into a pointer table that points to lists of enemy types.

    Returns:
        Dictionary mapping enemy codes to lists of Enemy enums
    """
    mixed_groups: Dict[int, List[Enemy]] = {}
    pointer_table_offset = RomLayout.MIXED_ENEMY_POINTER_TABLE.file_offset

    for i in range(MIXED_GROUP_POINTER_COUNT):
        enemy_code = FIRST_MIXED_GROUP_CODE + i

        # Read the pointer from the pointer table
        pointer_address = pointer_table_offset + (i * 2)
        cpu_address = _read_word_little_endian(rom_bytes, pointer_address)

        # Convert CPU address to ROM offset
        rom_offset = _cpu_address_to_rom_offset(cpu_address)

        # Read the enemy list (8 enemies per group)
        enemy_ids = list(rom_bytes[rom_offset:rom_offset + 8])

        # Convert enemy IDs to Enemy enums
        enemy_list: List[Enemy] = []
        for enemy_id in enemy_ids:
            try:
                enemy_list.append(Enemy(enemy_id))
            except ValueError:
                raise ValueError(
                    f"Unknown enemy ID 0x{enemy_id:02X} found in mixed enemy group 0x{enemy_code:02X}. "
                    f"This enemy type may need to be added to the Enemy enum in randomizer_constants.py"
                )

        mixed_groups[enemy_code] = enemy_list

    return mixed_groups


def _read_level_info(rom_bytes: bytes) -> tuple[List[List[int]], List[List[int]], bool]:
    """Read level info data from ROM bytes.

    Returns:
        Tuple of (level_info, level_info_raw, is_z1r)
    """
    level_info: List[List[int]] = []
    level_info_raw: List[List[int]] = []
    is_z1r = True

    base_offset = RomLayout.LEVEL_INFO.file_offset

    for level_num in range(10):
        start = base_offset + level_num * LEVEL_INFO_BLOCK_SIZE
        end = start + LEVEL_INFO_BLOCK_SIZE
        full_info = list(rom_bytes[start:end])

        # Skip the first 0x24 bytes (PPU palette data) to avoid cosmetic differences
        meaningful_data = full_info[LEVEL_INFO_PPU_PALETTE_SIZE:]
        info_copy = meaningful_data[:]

        level_info_raw.append(info_copy)
        level_info.append(info_copy[:])

        # Check for z1r detection using stairway list data
        # Read from original full data (offset 0x34 to 0x3E)
        vals = full_info[0x34:0x3E]
        if vals[-1] not in range(0, 5):
            is_z1r = False

    return level_info, level_info_raw, is_z1r


def load_from_bytes(rom_bytes: bytes) -> RomData:
    """Load ROM data from raw bytes.

    Args:
        rom_bytes: Complete ROM file contents (including NES header)

    Returns:
        RomData instance populated with data from the ROM
    """
    # Read level block pointers
    overworld_pointer = _read_word_little_endian(
        rom_bytes, RomLayout.OVERWORLD_POINTER.file_offset
    )
    level_1_to_6_pointer = _read_word_little_endian(
        rom_bytes, RomLayout.LEVEL_1_TO_6_POINTER.file_offset
    )
    level_7_to_9_pointer = _read_word_little_endian(
        rom_bytes, RomLayout.LEVEL_7_TO_9_POINTER.file_offset
    )

    # Determine which data blocks to read based on pointers
    # First quest uses 0x8700/0x8A00, second quest uses 0x8D00/0x9000
    if level_1_to_6_pointer == 0x8700:
        level_1_to_6_region = RomLayout.LEVEL_1_TO_6_FIRST_QUEST_DATA
    elif level_1_to_6_pointer == 0x8D00:
        level_1_to_6_region = RomLayout.LEVEL_1_TO_6_SECOND_QUEST_DATA
    else:
        level_1_to_6_region = RomLayout.LEVEL_1_TO_6_FIRST_QUEST_DATA

    if level_7_to_9_pointer == 0x8A00:
        level_7_to_9_region = RomLayout.LEVEL_7_TO_9_FIRST_QUEST_DATA
    elif level_7_to_9_pointer == 0x9000:
        level_7_to_9_region = RomLayout.LEVEL_7_TO_9_SECOND_QUEST_DATA
    else:
        level_7_to_9_region = RomLayout.LEVEL_7_TO_9_FIRST_QUEST_DATA

    # Read main data blocks
    level_1_to_6_block = list(rom_bytes[
        level_1_to_6_region.file_offset:level_1_to_6_region.end_offset
    ])
    level_7_to_9_block = list(rom_bytes[
        level_7_to_9_region.file_offset:level_7_to_9_region.end_offset
    ])
    overworld_block = list(rom_bytes[
        RomLayout.OVERWORLD_DATA.file_offset:RomLayout.OVERWORLD_DATA.end_offset
    ])

    # Read individual items
    armos_item = rom_bytes[RomLayout.ARMOS_ITEM.file_offset]
    coast_item = rom_bytes[RomLayout.COAST_ITEM.file_offset]

    # Read level info
    level_info, level_info_raw, is_z1r = _read_level_info(rom_bytes)

    # Read mixed enemy groups
    mixed_enemy_groups = _read_mixed_enemy_groups(rom_bytes)

    # Read recorder warp data
    recorder_warp_destinations = list(rom_bytes[
        RomLayout.RECORDER_WARP_DESTINATIONS.file_offset:
        RomLayout.RECORDER_WARP_DESTINATIONS.end_offset
    ])
    recorder_warp_y_coordinates = list(rom_bytes[
        RomLayout.RECORDER_WARP_Y_COORDINATES.file_offset:
        RomLayout.RECORDER_WARP_Y_COORDINATES.end_offset
    ])

    # Read any road screens
    any_road_screens = list(rom_bytes[
        RomLayout.ANY_ROAD_SCREENS.file_offset:
        RomLayout.ANY_ROAD_SCREENS.end_offset
    ])

    return RomData(
        level_1_to_6_block=level_1_to_6_block,
        level_7_to_9_block=level_7_to_9_block,
        overworld_block=overworld_block,
        level_info=level_info,
        level_info_raw=level_info_raw,
        armos_item=armos_item,
        coast_item=coast_item,
        mixed_enemy_groups=mixed_enemy_groups,
        is_z1r=is_z1r,
        overworld_pointer=overworld_pointer,
        level_1_to_6_pointer=level_1_to_6_pointer,
        level_7_to_9_pointer=level_7_to_9_pointer,
        recorder_warp_destinations=recorder_warp_destinations,
        recorder_warp_y_coordinates=recorder_warp_y_coordinates,
        any_road_screens=any_road_screens,
    )


def load_from_file(rom_path: str) -> RomData:
    """Load ROM data from a .nes file.

    Args:
        rom_path: Path to the ROM file

    Returns:
        RomData instance populated with data from the file
    """
    with open(rom_path, 'rb') as f:
        rom_bytes = f.read()
    return load_from_bytes(rom_bytes)


def load_from_test_data(data_dir: Optional[str] = None) -> RomData:
    """Load ROM data from extracted test data files.

    This function assembles a RomData from the individual .bin files
    created by extract_test_data.py, allowing tests to run without
    requiring the full ROM file.

    Args:
        data_dir: Path to test data directory (defaults to tests/data/)

    Returns:
        RomData instance populated with test data
    """
    if data_dir is None:
        # Default to tests/data/ relative to project root
        data_dir_path = Path(__file__).parent.parent / 'tests' / 'data'
    else:
        data_dir_path = Path(data_dir)

    def read_bin(filename: str) -> bytes:
        with open(data_dir_path / filename, 'rb') as f:
            return f.read()

    # Read the individual data files
    level_1_6_data = list(read_bin('level_1_6_data.bin'))
    level_7_9_data = list(read_bin('level_7_9_data.bin'))
    overworld_data = list(read_bin('overworld_data.bin'))
    level_info_bytes = read_bin('level_info.bin')
    armos_item = read_bin('armos_item.bin')[0]
    coast_item = read_bin('coast_item.bin')[0]
    level_pointers = read_bin('level_pointers.bin')

    # Parse level info into individual levels
    level_info: List[List[int]] = []
    level_info_raw: List[List[int]] = []
    is_z1r = True

    for level_num in range(10):
        start = level_num * LEVEL_INFO_BLOCK_SIZE
        end = start + LEVEL_INFO_BLOCK_SIZE
        full_info = list(level_info_bytes[start:end])

        # Skip PPU palette data
        meaningful_data = full_info[LEVEL_INFO_PPU_PALETTE_SIZE:]
        info_copy = meaningful_data[:]

        level_info_raw.append(info_copy)
        level_info.append(info_copy[:])

        # Check for z1r detection
        vals = full_info[0x34:0x3E]
        if vals[-1] not in range(0, 5):
            is_z1r = False

    # Parse level pointers
    overworld_pointer = _read_word_little_endian(level_pointers, 0)
    level_1_to_6_pointer = _read_word_little_endian(level_pointers, 2)
    level_7_to_9_pointer = _read_word_little_endian(level_pointers, 0xE)

    # Read mixed enemy data
    mixed_enemy_pointers = read_bin('mixed_enemy_pointers.bin')
    mixed_enemy_data = read_bin('mixed_enemy_data.bin')

    mixed_enemy_groups: Dict[int, List[Enemy]] = {}
    for i in range(MIXED_GROUP_POINTER_COUNT):
        enemy_code = FIRST_MIXED_GROUP_CODE + i
        cpu_address = _read_word_little_endian(mixed_enemy_pointers, i * 2)

        # Calculate offset into the mixed_enemy_data.bin file
        # The data starts at CPU address 0x8686 (based on first pointer)
        base_cpu_address = _read_word_little_endian(mixed_enemy_pointers, 0)
        offset = cpu_address - base_cpu_address

        if 0 <= offset < len(mixed_enemy_data) - 8:
            enemy_ids = list(mixed_enemy_data[offset:offset + 8])
            enemy_list: List[Enemy] = []
            for enemy_id in enemy_ids:
                try:
                    enemy_list.append(Enemy(enemy_id))
                except ValueError:
                    # Skip unknown enemy IDs in test data
                    pass
            mixed_enemy_groups[enemy_code] = enemy_list

    # For test data, use vanilla defaults for recorder warp and any road data
    # These aren't extracted by the test data extractor
    vanilla_recorder_destinations = [0x76, 0x3B, 0x74, 0x41, 0x04, 0x2B, 0x22, 0x6C]
    vanilla_recorder_y_coords = [0x8D, 0xAD, 0x8D, 0x8D, 0xAD, 0x8D, 0x8D, 0x5D]
    vanilla_any_road_screens = [0x22, 0x0A, 0x68, 0x3F]

    return RomData(
        level_1_to_6_block=level_1_6_data,
        level_7_to_9_block=level_7_9_data,
        overworld_block=overworld_data,
        level_info=level_info,
        level_info_raw=level_info_raw,
        armos_item=armos_item,
        coast_item=coast_item,
        mixed_enemy_groups=mixed_enemy_groups,
        is_z1r=is_z1r,
        overworld_pointer=overworld_pointer,
        level_1_to_6_pointer=level_1_to_6_pointer,
        level_7_to_9_pointer=level_7_to_9_pointer,
        recorder_warp_destinations=vanilla_recorder_destinations,
        recorder_warp_y_coordinates=vanilla_recorder_y_coords,
        any_road_screens=vanilla_any_road_screens,
    )
