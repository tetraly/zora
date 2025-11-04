from typing import List, Set, Tuple

from .randomizer_constants import CaveType, Direction, Item, LevelNum, RoomNum

import logging as log

class Inventory(object):
  def __init__(self) -> None:
    self.items: Set[Item]
    self.item_locations: Set[int]
    self.locations_where_keys_were_used: Set[Tuple[LevelNum, RoomNum, Direction]]
    self.num_heart_containers: int
    self.num_keys: int
    self.levels_with_triforce_obtained: List[int]
    self.still_making_progress_bit: bool
    self.Reset()

  def Reset(self) -> None:
    self.items = set()
    self.item_locations = set()
    self.locations_where_keys_were_used = set()
    self.num_heart_containers = 3
    self.num_keys = 0
    self.levels_with_triforce_obtained = []
    self.still_making_progress_bit = False

  def _IsLevelLocation(self, location_type: int) -> bool:
    """Check if location_type represents a level (1-9)."""
    return location_type in range(1, 10)

  def _IsCaveLocation(self, location_type: int) -> bool:
    """Check if location_type represents a cave (0x10-0x25)."""
    return location_type in range(0x10, 0x26)

  def ToString(self) -> str:
    return ", ".join(item.name for item in self.items)

  def SetStillMakingProgressBit(self) -> None:
    self.still_making_progress_bit = True

  def ClearMakingProgressBit(self) -> None:
    self.still_making_progress_bit = False

  def StillMakingProgress(self) -> bool:
    return self.still_making_progress_bit

  def AddItem(self, item: Item, location_type: int, sub_location: int) -> None:
    """Add an item to the inventory.

    Args:
        item: The item to add
        location_type: Either a level number (1-9) or CaveType (0x10-0x25)
        sub_location: Either room_num (for levels) or position_num (for caves)
    """
    if item in [
        Item.OVERWORLD_NO_ITEM, Item.MAP, Item.COMPASS, Item.MAGICAL_SHIELD, Item.BOMBS,
        Item.FIVE_RUPEES, Item.NO_ITEM, Item.SINGLE_HEART, Item.TRIFORCE_OF_POWER
    ]:
      return
    #if (item == Item.TRIFORCE_OF_POWER
    #    and not (location_type == 9 and sub_location == 0x42)):
    #  return
    assert (item in range(0, 0x24) or
            item in [Item.BEAST_DEFEATED_VIRTUAL_ITEM, Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM,
                     Item.LOST_HILLS_HINT_VIRTUAL_ITEM, Item.DEAD_WOODS_HINT_VIRTUAL_ITEM])

    # Compute unique identifier for this location
    unique_id = 1000 * location_type + sub_location

    if unique_id in self.item_locations and item != Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM:
      return
    self.item_locations.add(unique_id)

    self.SetStillMakingProgressBit()

    if item == Item.HEART_CONTAINER:
      # Ignore Take Any Heart Containers (CaveType.TAKE_ANY = 0x11)
      if self._IsCaveLocation(location_type) and location_type == CaveType.TAKE_ANY:
        return
      self.num_heart_containers += 1
      if self._IsLevelLocation(location_type):
        log.debug("Found Heart Container in level %d. Now have %d HCs" %
                  (location_type, self.num_heart_containers))
      else:
        log.debug("Found Heart Container in cave 0x%x. Now have %d HCs" %
                  (location_type, self.num_heart_containers))
      assert self.num_heart_containers <= 16
      return
    elif item == Item.TRIFORCE:
      if location_type not in self.levels_with_triforce_obtained:
        self.levels_with_triforce_obtained.append(location_type)
        log.debug("Found triforce in level %d. Now have %d tringles" %
                  (location_type, len(self.levels_with_triforce_obtained)))
      return
    elif item == Item.KEY:
      self.num_keys += 1
      return

    log.debug("Found %s" % item)

    if item == Item.WOOD_SWORD and Item.WOOD_SWORD in self.items:
      self.items.add(Item.WHITE_SWORD)
    elif item == Item.WOOD_SWORD and Item.WHITE_SWORD in self.items:
      self.items.add(Item.MAGICAL_SWORD)
    elif item == Item.BLUE_RING and Item.BLUE_RING in self.items:
      self.items.add(Item.RED_RING)
    elif item == Item.BLUE_CANDLE and Item.BLUE_CANDLE in self.items:
      self.items.add(Item.RED_CANDLE)
    elif item == Item.WOOD_ARROWS and Item.WOOD_ARROWS in self.items:
      self.items.add(Item.SILVER_ARROWS)
    else:
      self.items.add(item)

  def GetHeartCount(self) -> int:
    return self.num_heart_containers

  def GetTriforceCount(self) -> int:
    log.debug("Triforce check. Currently have: %s" % self.levels_with_triforce_obtained)
    return len(self.levels_with_triforce_obtained)

  def HasKey(self) -> bool:
    return self.Has(Item.MAGICAL_KEY) or self.num_keys > 0

  def UseKey(self, level_num: LevelNum, room_num: RoomNum, exit_direction: Direction) -> None:
    assert self.HasKey()
    if self.Has(Item.MAGICAL_KEY):
      return
    if (level_num, room_num) in self.locations_where_keys_were_used:
      return
    self.num_keys -= 1
    self.locations_where_keys_were_used.add((level_num, room_num, exit_direction))

  # Methods to check what's in the inventory
  def Has(self, item: Item) -> bool:
    return item in self.items

  # TODO: Make this work correctly with the Magical sword as well.
  def HasSword(self) -> bool:
    return Item.WOOD_SWORD in self.items or Item.WHITE_SWORD in self.items

  def HasSwordOrWand(self) -> bool:
    return self.HasSword() or Item.WAND in self.items

  def HasReusableWeapon(self) -> bool:
    return self.HasSwordOrWand() or Item.RED_CANDLE in self.items

  def HasReusableWeaponOrBoomerang(self) -> bool:
    return self.HasReusableWeapon() or self.HasBoomerang()

  def HasRecorderAndReusableWeapon(self) -> bool:
    return Item.RECORDER in self.items and self.HasReusableWeapon()

  def HasBowAndArrows(self) -> bool:
    return (Item.BOW in self.items
            and (Item.WOOD_ARROWS in self.items or Item.SILVER_ARROWS in self.items))

  def HasBowSilverArrowsAndSword(self) -> bool:
    return self.HasSword() and Item.BOW in self.items and Item.SILVER_ARROWS in self.items

  def HasCandle(self) -> bool:
    return Item.BLUE_CANDLE in self.items or Item.RED_CANDLE in self.items

  def HasBoomerang(self) -> bool:
    return Item.WOOD_BOOMERANG in self.items or Item.MAGICAL_BOOMERANG in self.items

  def HasRing(self) -> bool:
    return Item.BLUE_RING in self.items or Item.RED_RING in self.items
