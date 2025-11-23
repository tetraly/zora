"""Backward compatibility module for DataTable.

This module provides backward compatibility for code that still uses DataTable.
New code should import from the rom module directly:

    from rom import RomState
    state = RomState.from_rom_file("game.nes")

For legacy code using RomReader:

    from logic.data_table import DataTable
    from logic.rom_reader import RomReader
    data_table = DataTable(rom_reader)  # Still works

This module will be deprecated in a future release.
"""

import io
from typing import Dict, List

from .rom_reader import RomReader
from .location import Location
from .patch import Patch
from .randomizer_constants import (
    CaveType, Direction, Enemy, Item, ItemPosition, LevelNum, Range, RoomNum, RoomType, WallType
)

# Re-export RomState as DataTable for backward compatibility
from rom.rom_state import RomState
from rom.rom_data import RomData, load_from_bytes

from rom.rom_config import RomLayout


class DataTable(RomState):
    """Backward-compatible wrapper around RomState that accepts RomReader.

    This class maintains the old DataTable API while delegating to RomState.
    It accepts a RomReader for backward compatibility with existing code.

    New code should use RomState directly instead.
    """

    def __init__(self, rom_reader: RomReader) -> None:
        """Initialize DataTable from a RomReader.

        Args:
            rom_reader: A RomReader instance wrapping the ROM data
        """
        # Store rom_reader for methods that need direct access
        self.rom_reader = rom_reader

        # Read the full ROM into bytes
        rom_reader.rom.seek(0)
        rom_bytes = rom_reader.rom.read()

        # Load RomData from bytes
        rom_data = load_from_bytes(rom_bytes)

        # Initialize parent RomState
        super().__init__(rom_data)

    def GetArmosItemScreen(self) -> int:
        """Get the screen number where the armos item is located.

        Returns:
            The overworld screen number (0-127) where the armos item statue is located
        """
        return self.rom_reader._ReadMemory(RomLayout.ARMOS_SCREEN.cpu_address, 1)[0]

    def FindHeartResetCodeOffset(self) -> int:
        """Find the heart reset code location in the ROM.

        Returns the offset where "AD 6F 06 29 F0 09 02 8D 6F 06" appears,
        or raises an exception if not found.
        """
        self.rom_reader.rom.seek(0)
        rom_data = self.rom_reader.rom.read()
        pattern = bytes.fromhex("AD 6F 06 29 F0 09 02 8D 6F 06")

        for addr in range(0x10, len(rom_data) - len(pattern)):
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
