"""Backward compatibility module for DataTable.

This module provides backward compatibility for code that still uses DataTable.
New code should import from the rom module directly:

    from rom import RomInterface
    state = RomInterface.from_rom_file("game.nes")

For legacy code:

    from logic.data_table import DataTable
    data_table = DataTable(rom_bytes)  # Pass io.BytesIO directly
"""

import io
from typing import Dict, List

from .location import Location
from .patch import Patch
from .randomizer_constants import (
    CaveType, Direction, Enemy, Item, ItemPosition, LevelNum, Range, RoomNum, RoomType, WallType
)

from rom.rom_interface import RomInterface
from rom.rom_data import RomData, load_from_bytes
from rom.rom_config import RomLayout, NES_HEADER_SIZE


class DataTable(RomInterface):
    """Backward-compatible wrapper around RomInterface.

    This class maintains the old DataTable API while delegating to RomInterface.
    It accepts a BytesIO object for backward compatibility with existing code.

    New code should use RomInterface directly instead.
    """

    def __init__(self, rom_bytes: io.BytesIO) -> None:
        """Initialize DataTable from ROM bytes.

        Args:
            rom_bytes: A BytesIO object containing the ROM data
        """
        # Store rom_bytes for methods that need direct access
        self._rom_bytes_io = rom_bytes

        # Read the full ROM into bytes
        rom_bytes.seek(0)
        rom_data_bytes = rom_bytes.read()

        # Load RomData from bytes
        rom_data = load_from_bytes(rom_data_bytes)

        # Initialize parent RomInterface
        super().__init__(rom_data)

    def GetArmosItemScreen(self) -> int:
        """Get the screen number where the armos item is located.

        Returns:
            The overworld screen number (0-127) where the armos item statue is located
        """
        self._rom_bytes_io.seek(NES_HEADER_SIZE + RomLayout.ARMOS_SCREEN.cpu_address)
        return self._rom_bytes_io.read(1)[0]

    def FindHeartResetCodeOffset(self) -> int:
        """Find the heart reset code location in the ROM.

        Returns the offset where "AD 6F 06 29 F0 09 02 8D 6F 06" appears,
        or raises an exception if not found.
        """
        self._rom_bytes_io.seek(0)
        rom_data = self._rom_bytes_io.read()
        pattern = bytes.fromhex("AD 6F 06 29 F0 09 02 8D 6F 06")

        for addr in range(NES_HEADER_SIZE, len(rom_data) - len(pattern)):
            if rom_data[addr:addr+len(pattern)] == pattern:
                return addr

        raise Exception("Could not find heart reset code pattern in ROM!")

    def IsPrg0Rom(self) -> bool:
        """Detect if this is a PRG0 ROM based on heart reset code location.

        Returns True for PRG0, False for PRG1 or other versions.
        """
        try:
            offset = self.FindHeartResetCodeOffset()
            return offset == 0x14B7D  # PRG0 location
        except:
            return False
