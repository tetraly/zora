from typing import List
import logging
from .randomizer_constants import Direction, Enemy, Item, Range, RoomAction, RoomNum, RoomType, WallType

log = logging.getLogger(__name__)


class Room():
  # According to http://www.bwass.org/romhack/zelda1/zelda1bank6.txt:
  # Bytes in table 0 represent:
  # xxx. ....	Type of Door on Top Wall
  # ...x xx..	Type of Door on Bottom Wall
  # .... ..xx	Code for Palette 0 (Outer Border)
  # Bytes in table 1 represent:
  # xxx. ....	Type of Door on Left Wall
  # ...x xx..	Type of Door on Right Wall
  # .... ..xx	Code for Palette 1 (Inner Section)
  WALL_TYPE_TABLE_NUMBERS_AND_OFFSETS = {
      Direction.WEST: (1, 5),  # Bits 5-8 of table 1
      Direction.NORTH: (0, 5),  # Bits 5-8 of table 0
      Direction.EAST: (1, 2),  # Bits 2-5 of table 1
      Direction.SOUTH: (0, 2)  # Bits 2-5 of table 0
  }

  def __init__(self, rom_data: List[int]) -> None:
    if rom_data[4] & 0x1F == 0x03:
      stuff_not_to_change = rom_data[4] & 0xE0
      new_value = stuff_not_to_change + 0x0E
      rom_data[4] = new_value
    self.rom_data = rom_data

    # -1 is used as a sentinal value indicating a lack of stairway room
    self.staircase_room_num = RoomNum(-1)

  def GetRomData(self) -> List[int]:
    return self.rom_data

  def GetWallType(self, direction: Direction) -> WallType:
    assert self.GetType() not in [RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE]
    (table_num, offset) = self.WALL_TYPE_TABLE_NUMBERS_AND_OFFSETS[direction]
    return WallType(self.rom_data[table_num] >> offset & 0x07)

  def SetWallType(self, direction: Direction, wall_type: WallType) -> None:
    """Sets the wall type for a given direction, preserving all other bits."""
    assert self.GetType() not in [RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE]
    (table_num, offset) = self.WALL_TYPE_TABLE_NUMBERS_AND_OFFSETS[direction]

    # Create a mask to clear only the 3 bits at the offset position
    # 0x07 is 0b00000111, shift it left by offset to align with the wall bits
    # Then negate to create a mask that preserves everything except those 3 bits
    clear_mask = ~(0x07 << offset) & 0xFF

    # Clear the 3 wall bits, then OR in the new wall_type value at the correct position
    self.rom_data[table_num] = (self.rom_data[table_num] & clear_mask) | (int(wall_type) << offset)

  ### Staircase room methods ###
  def GetLeftExit(self) -> RoomNum:
    return RoomNum(self.rom_data[0] & 0x7F)

  def GetRightExit(self) -> RoomNum:
    return RoomNum(self.rom_data[1] & 0x7F)

  def HasStaircase(self) -> bool:
    # -1 is used as a sentinal value indicating a lack of stairway room
    return self.staircase_room_num != RoomNum(-1)

  def GetStaircaseRoomNumber(self) -> RoomNum:
    return self.staircase_room_num

  def SetStaircaseRoomNumber(self, staircase_room_num: RoomNum) -> None:
    self.staircase_room_num = staircase_room_num

  ### Room type-related methods ###
  def GetType(self) -> RoomType:
    return RoomType(self.rom_data[3] & 0x3F)

  #def HasUnobstructedStaircase(self) -> bool:
  #  return self.GetType() in [RoomType.SPIRAL_STAIR_ROOM, RoomType.NARROW_STAIR_ROOM]

  def IsItemStaircase(self) -> bool:
    return self.GetType() == RoomType.ITEM_STAIRCASE

  def IsTransportStaircase(self) -> bool:
    return self.GetType() == RoomType.TRANSPORT_STAIRCASE

  ### Item-related methods ###
  def SetItem(self, item_num_param: Item) -> None:
    item_num = int(item_num_param)
    old_item_num = self.rom_data[4] & 0x1F
    assert old_item_num in Range.VALID_ITEM_NUMBERS
    assert item_num in Range.VALID_ITEM_NUMBERS

    part_that_shouldnt_be_modified = self.rom_data[4] & 0xE0

    new_value = part_that_shouldnt_be_modified + int(item_num)
    assert new_value & 0xE0 == part_that_shouldnt_be_modified
    assert new_value & 0x1F == item_num
    self.rom_data[4] = new_value
    log.debug("Changed item %x to %x" % (old_item_num, item_num))
    
  def SetItemPosition(self, position_num: int):
    part_that_shouldnt_be_modified = self.rom_data[5] & 0xCF
    new_value = part_that_shouldnt_be_modified + position_num * 0x10
    self.rom_data[5] = new_value

  def GetItem(self) -> Item:
    return Item(self.rom_data[4] & 0x1F)

  def HasDropBitSet(self) -> bool:
    assert self.rom_data[5] & 0x04 in [0, 4]
    assert self.rom_data[5] & 0x01 in [0, 1]
    return self.rom_data[5] & 0x04 > 0 and self.rom_data[5] & 0x01 > 0

  def HasMovableBlockBitSet(self) -> bool:
      return ((self.rom_data[3] >> 6) & 0x01) > 0
      
  def HasItem(self) -> bool:
    if self.GetItem() == Item.MAGICAL_SWORD and (self.HasStaircase() or not self.HasDropBitSet()):
      return False
    return True

  ### Room action methods ###
  def GetRoomAction(self) -> RoomAction:
    """Get the room action code (SecretTrigger) from the lowest 3 bits of table 5."""
    return RoomAction(self.rom_data[5] & 0x07)

  def SetRoomAction(self, room_action: RoomAction) -> None:
    """Set the room action code (SecretTrigger), preserving all other bits in table 5."""
    # Create a mask to clear only the lowest 3 bits (0x07 = 0b00000111)
    # Then negate to create a mask that preserves everything except those 3 bits
    clear_mask = ~0x07 & 0xFF

    # Clear the 3 action bits, then OR in the new room_action value
    self.rom_data[5] = (self.rom_data[5] & clear_mask) | int(room_action)

  ### Enemy-related methods ###
  def GetEnemy(self) -> Enemy:
    enemy_code = self.rom_data[2] & 0x3F
    if self.rom_data[3] & 0x80 > 0:
      enemy_code += 0x40
    return Enemy(enemy_code)

  def HasTheBeast(self) -> bool:
    return self.GetEnemy() == Enemy.THE_BEAST

  def HasDigdogger(self) -> bool:
    enemy = self.GetEnemy()
    return enemy in [Enemy.SINGLE_DIGDOGGER, Enemy.TRIPLE_DIGDOGGER]

  def HasGohma(self) -> bool:
    enemy = self.GetEnemy()
    return enemy in [Enemy.RED_GOHMA, Enemy.BLUE_GOHMA]

  def HasHungryGoriya(self) -> bool:
    return self.GetEnemy() == Enemy.HUNGRY_GORIYA

  def HasNoEnemiesToKill(self) -> bool:
    enemy = self.GetEnemy()
    return enemy in [
      Enemy.BUBBLE,
      Enemy.THREE_PAIRS_OF_TRAPS,
      Enemy.CORNER_TRAPS,
      Enemy.OLD_MAN,
      Enemy.THE_KIDNAPPED,
      Enemy.NOTHING
    ]
