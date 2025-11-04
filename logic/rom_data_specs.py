"""ROM data specifications for generic read/write operations.

This module defines all ROM data regions that can be read from or written to
using generic GetRomData/SetRomData methods in DataTable. This allows adding
new ROM data without creating specific getter/setter methods for each one.

Address Convention:
    - cpu_address: NES CPU memory address (what code references, no iNES header)
    - file_offset: Byte offset in .nes file (includes 0x10 iNES header)
    - Relationship: file_offset = cpu_address + 0x10

Default values are read from vanilla Zelda 1 PRG1 ROM.
"""

from enum import Enum, auto
from typing import NamedTuple, List, Callable, Any


class RomDataType(Enum):
    """Enumeration of all ROM data types that can be accessed generically."""

    # Heart requirements
    WHITE_SWORD_HEART_REQUIREMENT = auto()
    MAGICAL_SWORD_HEART_REQUIREMENT = auto()

    # Overworld cave shuffling
    ANY_ROAD_SCREENS = auto()

    # Recorder warps
    RECORDER_WARP_DESTINATIONS = auto()
    RECORDER_WARP_Y_COORDINATES = auto()

    # Lost Woods / Dead Woods
    LOST_HILLS_DIRECTIONS = auto()
    DEAD_WOODS_DIRECTIONS = auto()

    # Dungeon item handling
    DUNGEON_NO_ITEM_CODE = auto()


class RomDataSpec(NamedTuple):
    """Specification for a ROM data region.

    Attributes:
        cpu_address: NES CPU memory address (without 0x10 header offset)
        file_offset: Byte offset in .nes file (cpu_address + 0x10)
        size: Size in bytes
        description: Human-readable description
        writable: Whether this data can be written
        readable: Whether this data can be read from ROM
        default_value: Vanilla ROM value (for write-only data or documentation)
        encoder: Optional function to encode data before writing to ROM
        decoder: Optional function to decode data after reading from ROM
    """
    cpu_address: int
    file_offset: int
    size: int
    description: str
    writable: bool = True
    readable: bool = True
    default_value: Any = None
    encoder: Callable[[Any], List[int]] | None = None
    decoder: Callable[[List[int]], Any] | None = None


# Encoder/decoder functions

def encode_heart_requirement(hearts: int) -> List[int]:
    """Encode heart requirement as (hearts - 1) * 16.

    Args:
        hearts: Number of hearts required (e.g., 5, 12)

    Returns:
        Single-element list with encoded byte (e.g., [0x40], [0xB0])
    """
    return [(hearts - 1) * 16]


def decode_heart_requirement(data: List[int]) -> int:
    """Decode heart requirement from ROM format.

    Args:
        data: Single-element list with encoded byte

    Returns:
        Number of hearts required
    """
    return int(data[0] / 16) + 1


# ROM Data Specifications
# Default values are from vanilla Zelda 1 PRG1 ROM
ROM_DATA_SPECS = {
    RomDataType.WHITE_SWORD_HEART_REQUIREMENT: RomDataSpec(
        cpu_address=0x48FD,
        file_offset=0x490D,
        size=1,
        description="White sword cave heart requirement",
        default_value=5,  # Decoded from 0x40
        encoder=encode_heart_requirement,
        decoder=decode_heart_requirement,
    ),

    RomDataType.MAGICAL_SWORD_HEART_REQUIREMENT: RomDataSpec(
        cpu_address=0x4906,
        file_offset=0x4916,
        size=1,
        description="Magical sword cave heart requirement",
        default_value=12,  # Decoded from 0xB0
        encoder=encode_heart_requirement,
        decoder=decode_heart_requirement,
    ),

    RomDataType.ANY_ROAD_SCREENS: RomDataSpec(
        cpu_address=0x19334,
        file_offset=0x19344,
        size=4,
        description="Four 'take any road' screen IDs",
        readable=True,
        writable=True,
        default_value=[0x1D, 0x23, 0x49, 0x79],
    ),

    RomDataType.RECORDER_WARP_DESTINATIONS: RomDataSpec(
        cpu_address=0x6010,
        file_offset=0x6020,
        size=8,
        description="Recorder warp destination screens for levels 1-8",
        readable=True,
        writable=True,
        default_value=[0x36, 0x3B, 0x73, 0x44, 0x0A, 0x21, 0x41, 0x6C],
    ),

    RomDataType.RECORDER_WARP_Y_COORDINATES: RomDataSpec(
        cpu_address=0x6119,
        file_offset=0x6129,
        size=8,
        description="Recorder warp Y coordinates for levels 1-8",
        readable=False,  # Write-only (randomizer calculates these)
        writable=True,
        default_value=[0x8D, 0xAD, 0x8D, 0x8D, 0xAD, 0x8D, 0xAD, 0x5D],
    ),

    RomDataType.LOST_HILLS_DIRECTIONS: RomDataSpec(
        cpu_address=0x6D9B,
        file_offset=0x6DAB,
        size=4,
        description="Lost Hills direction sequence (3 random + Up)",
        readable=False,  # Write-only (randomizer generates these)
        writable=True,
        default_value=[0x08, 0x08, 0x08, 0x08],  # Vanilla: Up, Up, Up, Up
    ),

    RomDataType.DEAD_WOODS_DIRECTIONS: RomDataSpec(
        cpu_address=0x6D97,
        file_offset=0x6DA7,
        size=4,
        description="Dead Woods direction sequence (3 random + South)",
        readable=False,  # Write-only (randomizer generates these)
        writable=True,
        default_value=[0x08, 0x02, 0x04, 0x02],  # Vanilla: Up, West, South, West
    ),

    RomDataType.DUNGEON_NO_ITEM_CODE: RomDataSpec(
        cpu_address=0x1784F,
        file_offset=0x1785F,
        size=1,
        description="Item code that represents 'no item' in dungeons (changed from 0x03 to 0x18 to allow MAGICAL_SWORD in dungeons)",
        readable=False,  # Write-only (always patch this)
        writable=True,
        default_value=0x18,  # RUPEE code (never used as room item)
    ),
}
