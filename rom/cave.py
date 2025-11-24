"""Cave data representation (internal implementation detail).

This module is internal to the rom package. External code should use
RomInterface methods instead of accessing Cave directly.
"""

from typing import List

from logic.randomizer_constants import Item, Range


class Cave(object):
    """Represents a single cave's data.

    This class encapsulates the 6 bytes of ROM data that define a cave's
    items and prices (3 items + 3 prices).

    Internal use only - external code should use RomInterface methods.
    """

    def __init__(self, raw_data: List[int]) -> None:
        self.raw_data = raw_data

    def GetItemAtPosition(self, position_num: int) -> Item:
        return Item(self.raw_data[position_num - 1] & 0x3F)

    def SetItemAtPosition(self, item: Item, position_num: int) -> None:
        part_not_to_change = self.raw_data[position_num - 1] & 0xC0  # The two highest bits
        self.raw_data[position_num - 1] = part_not_to_change + int(item)

    def GetItemData(self) -> List[int]:
        assert len(self.raw_data[0:3]) == 3
        return self.raw_data[0:3]

    def GetPriceData(self) -> List[int]:
        assert len(self.raw_data[3:6]) == 3
        if self.raw_data[3:6] == [0x00, 0x0A, 0x00]:
            return [0x00, 0x1E, 0x00]
        return self.raw_data[3:6]

    def SetPriceAtPosition(self, price: int, position_num: int) -> None:
        """Set the price at a given position (1-3). Price should be in rupees."""
        assert position_num in Range.VALID_CAVE_POSITION_NUMBERS
        # Price is stored 3 positions after the item: position_num - 1 (item index) + 3 (offset to price)
        self.raw_data[position_num - 1 + 3] = price
