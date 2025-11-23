"""ROM utility functions for reading and validating Zelda ROMs."""

import os
import re
import sys
import zlib


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.constants import CODE_ITEMS
from rom.rom_config import RomLayout, NES_HEADER_SIZE

# ============================================================================
# ROM UTILITIES
# ============================================================================


def extract_code_from_bytes(code_bytes: bytes) -> str:
    """Extract the code from ROM code bytes.

    Args:
        code_bytes: 4 bytes from ROM addresses 0xAFD0-0xAFD3

    Returns:
        str: Comma-separated item names

    Raises:
        ValueError: If code bytes are invalid
    """
    # Look up in CODE_ITEMS and join (reverse byte order)
    items = [
        CODE_ITEMS.get(code_bytes[3]),
        CODE_ITEMS.get(code_bytes[2]),
        CODE_ITEMS.get(code_bytes[1]),
        CODE_ITEMS.get(code_bytes[0])]

    # Check if any items are None (invalid code bytes)
    if None in items:
        raise ValueError("Unable to determine ROM code - invalid code bytes")

    # Filter out None values for type checker (already verified no None above)
    valid_items: list[str] = [item for item in items if item is not None]
    return ", ".join(valid_items)


def extract_base_rom_code(filename: str) -> str:
    """Extract the code from a ROM file.

    Reads bytes at ROM addresses 0xAFD0-0xAFD3 (file offset 0xAFE0-0xAFE3)
    and returns the item names as a comma-separated string.

    Raises:
        Exception: If the file cannot be read or code items cannot be determined
    """
    with open(filename, 'rb') as f:
        # Seek to 0xAFD4 (0xAFD0 + 4 to read backwards)
        f.seek(0xAFD4)
        code_bytes = f.read(4)

    return extract_code_from_bytes(code_bytes)


def extract_code_from_rom_data(rom_data: bytes, offset: int = 0xAFD4) -> str:
    """Extract the code from ROM data bytes.

    Args:
        rom_data: The ROM data bytes
        offset: Offset to code bytes (default 0xAFD4)

    Returns:
        str: Comma-separated item names, or "Unknown" if extraction fails
    """
    try:
        code_bytes = rom_data[offset:offset + 4]
        return extract_code_from_bytes(code_bytes)
    except Exception:
        return "Unknown"


def is_vanilla_rom(filename: str) -> bool:
    try:
        with open(filename, 'rb') as f:
            f.seek(0xAFD4)
            return f.read(4) == b'\xff\xff\xff\xff'
    except Exception:
        return False


def is_vanilla_rom_data(rom_data: bytes) -> bool:
    """Check if ROM data is from a vanilla ROM by checking for 0xFF bytes at code location."""
    try:
        return rom_data[0xAFD4:0xAFD4 + 4] == b'\xff\xff\xff\xff'
    except Exception:
        return False


def parse_filename_for_flag_and_seed(filename: str) -> tuple[str, str]:
    """Extract flagstring and seed from ROM filename.

    Expects pattern: [basename]_[seed]_[flagstring].nes

    Returns:
        tuple: (flagstring, seed)

    Raises:
        ValueError: If the filename doesn't match the expected pattern
    """
    # Match pattern: _[digits]_[flagstring].nes
    # Flagstring can contain uppercase, lowercase, digits, and "!"
    match = re.search(r'_(\d+)_([A-Za-z0-9!]{23,36})\.nes$', filename)

    if match:
        seed = match.group(1)
        flagstring = match.group(2)
        return flagstring, seed

    # If pattern doesn't match, raise an error
    raise ValueError(f"Invalid ROM filename format.\n\n"
                     f"Expected pattern: [basename]_[seed]_[flagstring].nes\n\n"
                     f"Your filename: {os.path.basename(filename)}")


# ============================================================================
# ROM VALIDATION (moved from logic/rom_reader.py)
# ============================================================================

def _read_word_little_endian(rom_bytes: bytes, offset: int) -> int:
    """Read a 16-bit word in little-endian format."""
    return rom_bytes[offset] | (rom_bytes[offset + 1] << 8)


def is_race_rom(rom_bytes: bytes) -> bool:
    """Check if this ROM is a Race ROM by verifying level block pointers.

    Race ROMs have modified memory layouts with different pointer values,
    which prevents the randomizer from reading level data correctly.

    Args:
        rom_bytes: Complete ROM file contents (including NES header)

    Returns:
        True if this appears to be a Race ROM (unsupported), False otherwise
    """
    try:
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

        # Check if pointers match expected values for vanilla/randomized ROMs
        valid_overworld = (overworld_pointer == 0x8400)
        valid_level_1_to_6 = (level_1_to_6_pointer in [0x8700, 0x8D00])
        valid_level_7_to_9 = (level_7_to_9_pointer in [0x8A00, 0x9000])

        # If any pointer is invalid, this is likely a Race ROM
        return not (valid_overworld and valid_level_1_to_6 and valid_level_7_to_9)
    except Exception:
        # If we can't read the pointers, assume it's not a valid ROM
        return True


def get_rom_version(rom_bytes: bytes) -> str:
    """Determine the ROM version (PRG0 or PRG1) using CRC32 checksum.

    Args:
        rom_bytes: Complete ROM file contents (including NES header)

    Returns:
        "PRG0", "PRG1", or "Unknown"
    """
    try:
        # Calculate CRC32 checksum of ROM data (after header)
        rom_data = rom_bytes[NES_HEADER_SIZE:]
        crc32 = zlib.crc32(rom_data) & 0xFFFFFFFF

        # Known CRC32 values for Legend of Zelda (without header)
        # PRG0: 0x3FE272FB
        # PRG1: 0xEAF7ED72
        if crc32 == 0x3FE272FB:
            return "PRG0"
        elif crc32 == 0xEAF7ED72:
            return "PRG1"
        else:
            return "Unknown"
    except Exception:
        return "Unknown"


def is_race_rom_file(filename: str) -> bool:
    """Check if a ROM file is a Race ROM.

    Args:
        filename: Path to the ROM file

    Returns:
        True if this appears to be a Race ROM (unsupported), False otherwise
    """
    with open(filename, 'rb') as f:
        rom_bytes = f.read()
    return is_race_rom(rom_bytes)


def get_rom_version_from_file(filename: str) -> str:
    """Get the ROM version from a file.

    Args:
        filename: Path to the ROM file

    Returns:
        "PRG0", "PRG1", or "Unknown"
    """
    with open(filename, 'rb') as f:
        rom_bytes = f.read()
    return get_rom_version(rom_bytes)
