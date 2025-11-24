"""ROM memory layout configuration.

This module defines all ROM memory regions used by the randomizer.
All addresses use file_offset convention (includes 0x10 NES header).

Address Convention:
    file_offset: Byte offset in the .nes file (includes 0x10 iNES header)
    cpu_address: NES CPU memory address (what code references, no header)
    Relationship: file_offset = cpu_address + 0x10

When viewing a ROM in a hex editor, use file_offset addresses.
When reading NES technical documentation, use cpu_address.
"""

from dataclasses import dataclass
from typing import Optional


# The NES header is 0x10 bytes and must be accounted for when reading ROM files
NES_HEADER_SIZE = 0x10


@dataclass(frozen=True)
class RomRegion:
    """Definition of a ROM memory region.

    Attributes:
        file_offset: Offset in .nes file (includes 0x10 header)
        size: Size of the region in bytes
        cpu_address: NES CPU address (no header) - for documentation/verification
        description: Human-readable description
    """
    file_offset: int
    size: int
    cpu_address: Optional[int] = None
    description: str = ""

    def __post_init__(self):
        """Verify file_offset = cpu_address + 0x10 if both are provided."""
        if self.cpu_address is not None:
            expected = self.cpu_address + NES_HEADER_SIZE
            if self.file_offset != expected:
                raise ValueError(
                    f"Address mismatch for '{self.description}': "
                    f"file_offset 0x{self.file_offset:X} != cpu_address 0x{self.cpu_address:X} + 0x10 "
                    f"(expected 0x{expected:X})"
                )

    @property
    def end_offset(self) -> int:
        """Return the end offset (exclusive) for slicing."""
        return self.file_offset + self.size


class RomLayout:
    """ROM memory layout constants for Legend of Zelda.

    All addresses are file_offset (include 0x10 NES header).
    cpu_address is provided for documentation and verification.
    """

    # ==========================================================================
    # Level/Dungeon Data Blocks
    # ==========================================================================

    # Level block pointers (used to determine quest type)
    OVERWORLD_POINTER = RomRegion(
        file_offset=0x18010, cpu_address=0x18000, size=2,
        description="Overworld data block pointer"
    )
    LEVEL_1_TO_6_POINTER = RomRegion(
        file_offset=0x18012, cpu_address=0x18002, size=2,
        description="Level 1-6 data block pointer"
    )
    LEVEL_7_TO_9_POINTER = RomRegion(
        file_offset=0x1801E, cpu_address=0x1800E, size=2,
        description="Level 7-9 data block pointer"
    )

    # Main data blocks (each is 0x300 bytes = 128 rooms * 6 tables)
    OVERWORLD_DATA = RomRegion(
        file_offset=0x18410, cpu_address=0x18400, size=0x300,
        description="Overworld screen data"
    )
    LEVEL_1_TO_6_FIRST_QUEST_DATA = RomRegion(
        file_offset=0x18710, cpu_address=0x18700, size=0x300,
        description="Level 1-6 room data (first quest)"
    )
    LEVEL_7_TO_9_FIRST_QUEST_DATA = RomRegion(
        file_offset=0x18A10, cpu_address=0x18A00, size=0x300,
        description="Level 7-9 room data (first quest)"
    )
    LEVEL_1_TO_6_SECOND_QUEST_DATA = RomRegion(
        file_offset=0x18D10, cpu_address=0x18D00, size=0x300,
        description="Level 1-6 room data (second quest)"
    )
    LEVEL_7_TO_9_SECOND_QUEST_DATA = RomRegion(
        file_offset=0x19010, cpu_address=0x19000, size=0x300,
        description="Level 7-9 room data (second quest)"
    )

    # Level metadata (10 levels * 0xFC bytes each = 0x9D8 total)
    LEVEL_INFO = RomRegion(
        file_offset=0x19310, cpu_address=0x19300, size=0x9D8,
        description="Level metadata (start rooms, stairway lists, etc.)"
    )

    # ==========================================================================
    # Overworld Items
    # ==========================================================================

    ARMOS_ITEM = RomRegion(
        file_offset=0x10D05, cpu_address=0x10CF5, size=1,
        description="Item dropped by Armos statues"
    )
    ARMOS_SCREEN = RomRegion(
        file_offset=0x10CC2, cpu_address=0x10CB2, size=1,
        description="Screen number for Armos item"
    )
    COAST_ITEM = RomRegion(
        file_offset=0x1789A, cpu_address=0x1788A, size=1,
        description="Item at the coast (requires ladder)"
    )

    # ==========================================================================
    # Cave Data
    # ==========================================================================

    CAVE_ITEM_DATA = RomRegion(
        file_offset=0x18610, cpu_address=0x18600, size=0x3C,
        description="Cave item data (20 caves * 3 items)"
    )
    CAVE_PRICE_DATA = RomRegion(
        file_offset=0x1864C, cpu_address=0x1863C, size=0x3C,
        description="Cave price data (20 caves * 3 prices)"
    )

    # ==========================================================================
    # Game Requirements
    # ==========================================================================

    TRIFORCE_REQUIREMENT = RomRegion(
        file_offset=0x5F27, cpu_address=0x5F17, size=1,
        description="Triforce pieces required for level 9"
    )
    WHITE_SWORD_REQUIREMENT = RomRegion(
        file_offset=0x490D, cpu_address=0x48FD, size=1,
        description="Hearts required for white sword"
    )
    MAGICAL_SWORD_REQUIREMENT = RomRegion(
        file_offset=0x4916, cpu_address=0x4906, size=1,
        description="Hearts required for magical sword"
    )
    DOOR_REPAIR_CHARGE = RomRegion(
        file_offset=0x48A0, cpu_address=0x4890, size=1,
        description="Rupees charged for door repair"
    )

    # ==========================================================================
    # Warp/Travel Data
    # ==========================================================================

    ANY_ROAD_SCREENS = RomRegion(
        file_offset=0x19344, cpu_address=0x19334, size=4,
        description="Any road destination screens"
    )
    RECORDER_WARP_DESTINATIONS = RomRegion(
        file_offset=0x6020, cpu_address=0x6010, size=8,
        description="Recorder warp destination screens for levels 1-8"
    )
    RECORDER_WARP_Y_COORDINATES = RomRegion(
        file_offset=0x6129, cpu_address=0x6119, size=8,
        description="Recorder warp Y coordinates for levels 1-8"
    )

    # ==========================================================================
    # Mixed Enemy Groups
    # ==========================================================================

    MIXED_ENEMY_POINTER_TABLE = RomRegion(
        file_offset=0x1474F, cpu_address=0x1473F, size=0x3C,
        description="Pointer table for mixed enemy groups (30 pointers)"
    )

    # Bank 5 mapping (for CPU address conversion)
    BANK_5_ROM_START = 0x14010  # file_offset (0x14000 + 0x10)
    BANK_5_CPU_START = 0x8000

    # ==========================================================================
    # Text Data
    # ==========================================================================

    QUOTE_POINTER_TABLE = RomRegion(
        file_offset=0x4010, cpu_address=0x4000, size=0x4C,
        description="Quote text pointer table (38 quotes * 2 bytes)"
    )
    RECORDER_TEXT = RomRegion(
        file_offset=0xB010, cpu_address=0xB000, size=0x40,
        description="Recorder/flute text data"
    )


# ==========================================================================
# Level Info Internal Offsets (within each 0xFC byte level info block)
# ==========================================================================

# The first 0x24 bytes of each level info block are PPU palette data
# which should be skipped for meaningful game data
LEVEL_INFO_PPU_PALETTE_SIZE = 0x24

# Offsets within the meaningful data portion (after skipping PPU data)
# Original ROM offsets: ITEM_POSITIONS=0x29, START_ROOM=0x2F, STAIRWAY_LIST=0x34
# After skipping 0x24 bytes: subtract 0x24 from each
LEVEL_INFO_ITEM_POSITIONS_OFFSET = 0x05  # 0x29 - 0x24
LEVEL_INFO_START_ROOM_OFFSET = 0x0B  # 0x2F - 0x24
LEVEL_INFO_STAIRWAY_LIST_OFFSET = 0x10  # 0x34 - 0x24
LEVEL_INFO_COMPASS_OFFSET = 0x0C  # 0x30 - 0x24

# Per-level info block size
LEVEL_INFO_BLOCK_SIZE = 0xFC


# ==========================================================================
# Room/Cave Data Constants
# ==========================================================================

LEVEL_TABLE_SIZE = 0x80  # 128 rooms per level
NUM_BYTES_OF_DATA_PER_ROOM = 6  # 6 tables of data per room

# Special cave numbers (used internally, external API should use CaveType)
CAVE_NUMBER_ARMOS_ITEM = 0x14
CAVE_NUMBER_COAST_ITEM = 0x15


# ==========================================================================
# Mixed Enemy Group Constants
# ==========================================================================

FIRST_MIXED_GROUP_CODE = 0x62  # Enemy codes >= 0x62 are mixed groups
MIXED_GROUP_POINTER_COUNT = 0x1E  # 30 pointers total (0x62-0x7F)
