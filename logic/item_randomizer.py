from typing import DefaultDict, List, Tuple, Iterable
from collections import defaultdict
from random import randint, shuffle
import logging as log

from .randomizer_constants import Direction, Item, LevelNum, Range, RoomNum, RoomType, WallType
from .data_table import DataTable
from .location import Location
from .flags import Flags


class ItemRandomizer():
  def __init__(self, data_table: DataTable, flags: Flags) -> None:
    self.data_table = data_table
    self.flags = flags
    self.item_shuffler = ItemShuffler(flags)

  def _GetProgressiveReplacementItemIfNeeded(self, item: Item):
    # Individual progressive flags are temporarily disabled
    progressive_candles = False
    progressive_rings = False
    progressive_arrows = False
    progressive_swords = False
    progressive_boomerangs = False

    if (self.flags.progressive_items or progressive_candles) and item == Item.RED_CANDLE:
      return Item.BLUE_CANDLE
    if (self.flags.progressive_items or progressive_rings) and item == Item.RED_RING:
      return Item.BLUE_RING
    if (self.flags.progressive_items or progressive_arrows) and item == Item.SILVER_ARROWS:
      return Item.WOOD_ARROWS
    if (self.flags.progressive_items or progressive_swords) and item in [Item.WHITE_SWORD,  Item.MAGICAL_SWORD]:
      return Item.WOOD_SWORD
    if progressive_boomerangs and item == Item.MAGICAL_BOOMERANG:
      return Item.WOOD_BOOMERANG
    return item 

  def ReplaceProgressiveItemsWithUpgrades(self):
    for cave_num in [0, 2, 3, 8, 0x0D, 0x0E, 0x0F, 0x10, 20, 21]:
      for position_num in [1, 2, 3]:
        location = Location.CavePosition(cave_num, position_num)
        current_item = self.data_table.GetCaveItem(location)
        replacement_item = self._GetProgressiveReplacementItemIfNeeded(current_item)
        if current_item != replacement_item:
          self.data_table.SetCaveItem(location, replacement_item)        
        
  def _GetOverworldItemLocation(self, item: Item, skip_first=False):
    log.debug("_GetOverworldItemLocation for %s" % item)
    for cave_num in [0x0D, 0x0E, 0x0F, 0x10]:
      for position_num in Range.VALID_CAVE_POSITION_NUMBERS:
        maybe_location = Location(cave_num=cave_num, position_num=position_num)
        if self.data_table.GetCaveItem(maybe_location) == item:
          if skip_first:
              skip_first = False
              continue
          log.debug("_GetOverworldItemLocation Found it at cave %d pos %d" %
                      (maybe_location.GetCaveNum(),maybe_location.GetPositionNum()))
          return maybe_location
    raise Exception(f"_GetOverworldItemLocation: Couldn't find item {item} in overworld caves")

  WOOD_SWORD_LOCATION = Location.CavePosition(0, 2)
  WHITE_SWORD_LOCATION = Location.CavePosition(2, 2)
  MAGICAL_SWORD_LOCATION = Location.CavePosition(3, 2)
  LETTER_LOCATION = Location.CavePosition(8, 2)
  ARMOS_ITEM_LOCATION = Location.CavePosition(20, 2)
  COAST_ITEM_LOCATION = Location.CavePosition(21, 2)
  LEFT_POTION_SHOP_LOCATION = Location.CavePosition(10, 1)
  MIDDLE_POTION_SHOP_LOCATION = Location.CavePosition(10, 2)
  RIGHT_POTION_SHOP_LOCATION = Location.CavePosition(10, 3)
  
  def _GetOverworldItemsToShuffle(self) -> List[Location]:
    items: List[Location] = []
    if self.flags.shuffle_wood_sword_cave_item:
      items.append(self.WOOD_SWORD_LOCATION)
    if self.flags.shuffle_white_sword_cave_item:
      items.append(self.WHITE_SWORD_LOCATION)
    # When Progressive Items are enabled but not shuffling the magical sword item, change mags to a sword upgrade
    # Individual progressive flags are temporarily disabled
    progressive_swords = False
    if self.flags.shuffle_magical_sword_cave_item:
      items.append(self.MAGICAL_SWORD_LOCATION)
    elif self.flags.progressive_items or progressive_swords:
      self.data_table.SetCaveItem(self.MAGICAL_SWORD_LOCATION, Item.WOOD_SWORD)
    if self.flags.shuffle_coast_item:
      items.append(self.COAST_ITEM_LOCATION)
    if self.flags.shuffle_armos_item:
      items.append(self.ARMOS_ITEM_LOCATION)
    if self.flags.shuffle_letter_cave_item:
      items.append(self.LETTER_LOCATION)
    if self.flags.shuffle_shop_arrows:
      items.append(self._GetOverworldItemLocation(Item.WOOD_ARROWS))
    if self.flags.shuffle_shop_candle:
      items.append(self._GetOverworldItemLocation(Item.BLUE_CANDLE))
    if self.flags.shuffle_shop_ring:
      ring_location = self._GetOverworldItemLocation(Item.BLUE_RING)
      items.append(ring_location)
      # Lower the price of the ring shop slot to 150 ± 25 rupees
      import random
      new_price = random.randint(125, 175)
      cave_num = ring_location.GetCaveNum()
      position_num = ring_location.GetPositionNum()
      self.data_table.overworld_caves[cave_num].SetPriceAtPosition(new_price, position_num)
    if self.flags.shuffle_shop_book:
      try:
        book_location = self._GetOverworldItemLocation(Item.BOOK)
        items.append(book_location)
      except Exception:
        # If book is not found, flag has no effect
        pass
    if self.flags.shuffle_shop_bait:
      items.append(self._GetOverworldItemLocation(Item.BAIT))
      second_bait_location = self._GetOverworldItemLocation(Item.BAIT, skip_first=True)
      self.data_table.SetCaveItem(second_bait_location, Item.FAIRY)
      cave_num = second_bait_location.GetCaveNum()
      position_num = second_bait_location.GetPositionNum()
      self.data_table.overworld_caves[cave_num].SetPriceAtPosition(randint(20, 40), position_num)
    return items

  def ResetState(self):
    self.item_shuffler.ResetState()

  def ReadItemsAndLocationsFromTable(self) -> None:
    for level_num in Range.VALID_LEVEL_NUMBERS:
      self._ReadItemsAndLocationsForUndergroundLevel(level_num)
    for location in self._GetOverworldItemsToShuffle():
      item_num = self.data_table.GetCaveItem(location)
      self.item_shuffler.AddLocationAndItem(location, item_num)
    if self.flags.shuffle_potion_shop_items:
      self.item_shuffler.AddLocationAndItem(self.LEFT_POTION_SHOP_LOCATION, Item.BLUE_POTION)
      self.item_shuffler.AddLocationAndItem(self.RIGHT_POTION_SHOP_LOCATION, Item.BLUE_POTION)

  def _ReadItemsAndLocationsForUndergroundLevel(self, level_num: LevelNum) -> None:
    log.debug("Reading staircase room data for level %d " % level_num)
    for staircase_room_num in self.data_table.GetLevelStaircaseRoomNumberList(level_num):
      self._ParseStaircaseRoom(level_num, staircase_room_num)
    level_start_room_num = self.data_table.GetLevelStartRoomNumber(level_num)
    entrance_direction = self.data_table.GetLevelEntranceDirection(level_num)
    log.debug("Traversing level %d.  Start room is %x. " % (level_num, level_start_room_num))
    self._ReadItemsAndLocationsRecursively(level_num, level_start_room_num, entrance_direction)

  def _ParseStaircaseRoom(self, level_num: LevelNum, staircase_room_num: RoomNum) -> None:
    staircase_room = self.data_table.GetRoom(level_num, staircase_room_num)

    if staircase_room.GetType() == RoomType.ITEM_STAIRCASE:
      log.debug("  Found item staircase %x in L%d " % (staircase_room_num, level_num))
      assert staircase_room.GetLeftExit() == staircase_room.GetRightExit()
      self.data_table.GetRoom(
          level_num, staircase_room.GetLeftExit()).SetStaircaseRoomNumber(staircase_room_num)
    elif staircase_room.GetType() == RoomType.TRANSPORT_STAIRCASE:
      log.debug("  Found transport staircase %x in L%d " % (staircase_room_num, level_num))
      assert staircase_room.GetLeftExit() != staircase_room.GetRightExit()
      for associated_room_num in [staircase_room.GetLeftExit(), staircase_room.GetRightExit()]:
        self.data_table.GetRoom(level_num,
                                associated_room_num).SetStaircaseRoomNumber(staircase_room_num)
    else:
      log.fatal("Room in staircase room number list (%x) didn't have staircase type (%x)." %
                    (staircase_room_num, staircase_room.GetType()))

  def _ReadItemsAndLocationsRecursively(self, level_num: LevelNum, room_num: RoomNum, from_dir: Direction) -> None:
    if room_num not in Range.VALID_ROOM_NUMBERS:
      return  # No escaping back into the overworld! :)
    log.debug("Visiting level %d room %0x" % (level_num, room_num))
    room = self.data_table.GetRoom(level_num, room_num)
    if room.IsMarkedAsVisited():
      return
    room.MarkAsVisited()

    item = room.GetItem()
    if item not in [Item.NO_ITEM, Item.TRIFORCE_OF_POWER]:
        if not item.IsMinorDungeonItem() or self.flags.shuffle_minor_dungeon_items:
          self.item_shuffler.AddLocationAndItem(Location.LevelRoom(level_num, room_num), item)
 
    # Staircase cases (bad pun intended)
    if room.GetType() == RoomType.ITEM_STAIRCASE:
      return  # Dead end, no need to traverse further.
    elif room.GetType() == RoomType.TRANSPORT_STAIRCASE:
      for upstairs_room in [room.GetLeftExit(), room.GetRightExit()]:
        self._ReadItemsAndLocationsRecursively(level_num, upstairs_room, Direction.STAIRCASE)
      return
    # Regular (non-staircase) room case.  Check all four cardinal directions, plus "down".
    for direction in (Direction.WEST, Direction.NORTH, Direction.EAST, Direction.SOUTH):
      if direction == from_dir:
        continue
      if room.GetWallType(direction) != WallType.SOLID_WALL:
        self._ReadItemsAndLocationsRecursively(level_num, RoomNum(room_num + direction), direction.inverse())
    if room.HasStaircase():
      self._ReadItemsAndLocationsRecursively(level_num, room.GetStaircaseRoomNumber(), Direction.STAIRCASE)

  def ShuffleItems(self) -> None:
    self.item_shuffler.ShuffleItems()

  def HasValidItemConfiguration(self) -> bool:
    return self.item_shuffler.HasValidItemConfiguration()

  def WriteItemsAndLocationsToTable(self) -> None:
    for (location, item_num) in self.item_shuffler.GetAllLocationAndItemData():
      if location.IsLevelRoom():
        self.data_table.SetRoomItem(location, item_num)
        if item_num == Item.TRIFORCE:
          self.data_table.UpdateTriforceLocation(location)
      elif location.IsCavePosition():
        self.data_table.SetCaveItem(location, item_num)
    # Individual progressive flags are temporarily disabled
    progressive_swords = False
    if (self.flags.progressive_items or progressive_swords) and self.flags.add_l4_sword:
      level_nine_start_room_num = self.data_table.GetLevelStartRoomNumber(9)
      triforce_check_room_num = level_nine_start_room_num - 0x10
      self.data_table.SetRoomItem(Location.LevelRoom(9, triforce_check_room_num), Item.WOOD_SWORD)
      self.data_table.SetItemPosition(Location.LevelRoom(9, triforce_check_room_num), 2) 
      


class ItemShuffler():
  def __init__(self, flags) -> None:
    self.flags = flags
    self.item_num_list: List[Item] = []
    self.per_level_item_location_lists: DefaultDict[LevelNum, List[Location]] = defaultdict(list)
    self.per_level_item_lists: DefaultDict[LevelNum, List[Item]] = defaultdict(list)
    self.heart_container_count = 0
    self.temp_location_count = 0
    self.temp_dung_item_count = 0

  def ResetState(self):
    self.item_num_list.clear()
    self.per_level_item_location_lists.clear()
    self.per_level_item_lists.clear()
    self.heart_container_count = 0
    self.temp_location_count = 0
    self.temp_dung_item_count = 0

  def AddLocationAndItem(self, location: Location, item_num: Item) -> None:
    if item_num == Item.TRIFORCE_OF_POWER:
      return
    level_num = location.GetLevelNum() if location.IsLevelRoom() else 10
    self.per_level_item_location_lists[level_num].append(location)
    log.debug("Location %d:  %s" %
              (len(self.per_level_item_location_lists[level_num]),location.ToString()))
              
    self.temp_location_count += 1
    log.debug("L%d Adding Location %s" % (self.temp_location_count, location.ToString()))
    if (item_num == Item.HEART_CONTAINER and self.heart_container_count < 8) or item_num in [Item.MAP, Item.COMPASS, Item.TRIFORCE]:
      if item_num == Item.HEART_CONTAINER:
        self.heart_container_count += 1            
      self.temp_dung_item_count += 1
      log.debug("T%d Found a thing" % self.temp_dung_item_count)
      log.debug("%d == %d + %d" % (self.temp_location_count , self.temp_dung_item_count, len(self.item_num_list)))
      assert (self.temp_location_count == self.temp_dung_item_count + len(self.item_num_list))
      return
    # Incorporate the logic from _GetProgressiveReplacementItemIfNeeded
    # Individual progressive flags are temporarily disabled
    progressive_candles = False
    progressive_rings = False
    progressive_arrows = False
    progressive_swords = False
    progressive_boomerangs = False

    if self.flags.progressive_items or progressive_candles:
      if item_num == Item.RED_CANDLE:
        item_num = Item.BLUE_CANDLE
    if self.flags.progressive_items or progressive_rings:
      if item_num == Item.RED_RING:
        item_num = Item.BLUE_RING
    if self.flags.progressive_items or progressive_arrows:
      if item_num == Item.SILVER_ARROWS:
        item_num = Item.WOOD_ARROWS
    if self.flags.progressive_items or progressive_swords:
      if item_num == Item.WHITE_SWORD:
        item_num = Item.WOOD_SWORD
      if item_num == Item.MAGICAL_SWORD:
        item_num = Item.WOOD_SWORD
    if progressive_boomerangs:
      if item_num == Item.MAGICAL_BOOMERANG:
        item_num = Item.WOOD_BOOMERANG

    self.item_num_list.append(item_num)
    log.debug("I%d:  %s. From %s" % (len(self.item_num_list), Item(item_num), location.ToString()))
    log.debug("%d == %d + %d" % (self.temp_location_count , self.temp_dung_item_count, len(self.item_num_list)))
    assert (self.temp_location_count == self.temp_dung_item_count + len(self.item_num_list))

  def ShuffleItems(self) -> None:
    shuffle(self.item_num_list)

    for level_num in Range.VALID_LEVEL_AND_CAVE_NUMBERS:
      log.debug("We're in level %d" % level_num)
      log.debug("There are a total of %d items left" % len(self.item_num_list))
      # Levels 1-8 get a tringle, map, and compass.  Level 9 only gets a map and compass.
      if level_num in Range.VALID_LEVEL_NUMBERS and self.flags.shuffle_minor_dungeon_items:
        self.per_level_item_lists[level_num] = [Item.MAP, Item.COMPASS]
      if level_num in range(1, 9):
        self.per_level_item_lists[level_num].append(Item.TRIFORCE)
        self.per_level_item_lists[level_num].append(Item.HEART_CONTAINER)

      num_locations_needing_an_item = len(self.per_level_item_location_lists[level_num]) - len(
          self.per_level_item_lists[level_num])
      log.debug("In this level, %d locations need an item" % num_locations_needing_an_item)

      while num_locations_needing_an_item > 0:
        self.per_level_item_lists[level_num].append(self.item_num_list.pop())
        num_locations_needing_an_item = num_locations_needing_an_item - 1

      if level_num in range(1, 10):  # Technically this could be for OW and caves too
        shuffle(self.per_level_item_lists[level_num])

    if self.item_num_list:
      print(f"\n!!! WARNING: Items remaining after shuffle !!!")
      print(f"Remaining items: {self.item_num_list}")
      print(f"Number of remaining items: {len(self.item_num_list)}")
      print("!!!\n")

    assert not self.item_num_list

  def HasValidItemConfiguration(self):
    found_ring_in_level_nine: bool = False
    found_wand_in_level_nine: bool = False
    found_arrow_in_level_nine: bool = False
    heart_container_count_in_level_nine: int = 0
    found_heart_container_at_armos: bool = False
    found_heart_container_at_coast: bool = False
    for level_num in range(0, 11):
      for location, item in zip(self.per_level_item_location_lists[level_num],
                                    self.per_level_item_lists[level_num]):
        if location.IsShopPosition():
            # Individual progressive flags are temporarily disabled
            progressive_arrows = False
            progressive_candles = False
            progressive_rings = False
            progressive_swords = False
            progressive_boomerangs = False

            if (self.flags.progressive_items or progressive_arrows) and item == Item.WOOD_ARROWS:
              return False
            if (self.flags.progressive_items or progressive_candles) and item == Item.BLUE_CANDLE:
              return False
            if (self.flags.progressive_items or progressive_rings) and item == Item.BLUE_RING:
              return False
            if (self.flags.progressive_items or progressive_swords) and item == Item.WOOD_SWORD:
              return False
            if progressive_boomerangs and item == Item.WOOD_BOOMERANG:
              return False
        if (self.flags.progressive_items and location.IsShopPosition() and
            item.IsProgressiveUpgradeItem()):
            return False
        if location.IsShopPosition() and item == Item.HEART_CONTAINER:
            return False
        if location.IsCavePosition() and location.GetCaveNum() == 0x25 and item == Item.LADDER:
            return False
        # Track heart containers at armos and coast locations
        if location.IsCavePosition() and location.GetCaveNum() == 20 and location.GetPositionNum() == 2:
            if item == Item.HEART_CONTAINER:
                found_heart_container_at_armos = True
        if location.IsCavePosition() and location.GetCaveNum() == 21 and location.GetPositionNum() == 2:
            if item == Item.HEART_CONTAINER:
                found_heart_container_at_coast = True
        if location in [Location.CavePosition(10, 1),  Location.CavePosition(10, 2),  Location.CavePosition(10, 3)]:
            if item == Item.LETTER:
                return False 
        # TODO: Remove this constraint once we fix the NO_ITEM vs MAGICAL_SWORD ambiguity
        # The game uses code 0x03 for both MAGICAL_SWORD and NO_ITEM in dungeons, so we cannot
        # safely place Magical Swords in dungeon rooms. This limitation is documented in
        # ui/known_issues.py. The fix will be to change the NO_ITEM code to a different value.
        if location.IsLevelRoom() and item == Item.MAGICAL_SWORD:
            return False
        if location.IsLevelRoom() and location.GetLevelNum() == 9:
          # By default, prevent important items in level 9 unless flag is enabled
          if not self.flags.allow_important_items_in_level_nine:
            if item in [Item.RAFT, Item.POWER_BRACELET, Item.RECORDER, Item.BOW, Item.LADDER]:
              return False
          if item in [Item.WOOD_ARROWS, Item.SILVER_ARROWS]:
            found_arrow_in_level_nine = True
          if item in [Item.BLUE_RING, Item.RED_RING]:
            found_ring_in_level_nine = True
          if item == Item.WAND:
            found_wand_in_level_nine = True
          if item == Item.HEART_CONTAINER:
            heart_container_count_in_level_nine += 1
    if self.flags.force_arrow_to_level_nine and not found_arrow_in_level_nine:
      return False
    if self.flags.force_ring_to_level_nine and not found_ring_in_level_nine:
      return False
    if self.flags.force_wand_to_level_nine and not found_wand_in_level_nine:
      return False
    if self.flags.force_heart_container_to_level_nine and heart_container_count_in_level_nine < 1:
      return False
    if self.flags.force_two_heart_containers_to_level_nine and heart_container_count_in_level_nine < 2:
      return False
    if self.flags.force_heart_container_to_armos and not found_heart_container_at_armos:
      return False
    if self.flags.force_heart_container_to_coast and not found_heart_container_at_coast:
      return False
    return True   

  def GetAllLocationAndItemData(self) -> Iterable[Tuple[Location, Item]]:
    tbr = []
    for level_num in range(0, 11):
      for location, item_num in zip(self.per_level_item_location_lists[level_num],
                                    self.per_level_item_lists[level_num]):
        tbr.append((location, item_num))
    return tbr
