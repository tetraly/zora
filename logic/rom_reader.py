"""Legacy ROM reader for backward compatibility.

This module is deprecated. New code should use:
    from rom import RomState
    state = RomState.from_rom_file("game.nes")

This module is kept for backward compatibility with code that uses
DataTable(RomReader(rom)).
"""

import io
from typing import List

# Constants still used by randomizer.py
NES_HEADER_OFFSET = 0x10


class RomReader:
    """Legacy ROM reader class.

    This class provides low-level ROM reading functionality needed by
    the backward-compatible DataTable class. New code should use RomState
    instead.
    """

    def __init__(self, rom: io.BytesIO) -> None:
        self.rom = rom

    def _ReadMemory(self, address: int, num_bytes: int = 1) -> List[int]:
        """Read bytes from ROM at a CPU address.

        Args:
            address: CPU address (NES_HEADER_OFFSET will be added)
            num_bytes: Number of bytes to read

        Returns:
            List of byte values
        """
        assert num_bytes > 0, "num_bytes shouldn't be negative"
        self.rom.seek(NES_HEADER_OFFSET + address)
        data: List[int] = []
        for raw_byte in self.rom.read(num_bytes):
            data.append(int(raw_byte))
        return data
