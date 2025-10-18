from typing import List
from .randomizer_constants import Item, Range


class Cave(object):
  def __init__(self, raw_data: List[int]) -> None:
    self.raw_data = raw_data

  def GetItemAtPosition(self, position_num: int) -> Item:
    return Item(self.raw_data[position_num - 1] & 0x3F)


#  def GetAllItems(self) -> List[Item]:
#    actual_items: List[Item] = []
#    for position in Range.VALID_CAVE_POSITION_NUMBERS:
#      maybe_item = self.GetItemAtPosition(position)
#      if maybe_item != Item.OVERWORLD_NO_ITEM:
#        actual_items.append(maybe_item)
#    return actual_items

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
