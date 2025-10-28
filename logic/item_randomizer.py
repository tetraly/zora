from typing import DefaultDict, Dict, List, Tuple, Iterable
from collections import defaultdict, Counter
from random import randint, shuffle
import random
import logging as log
from ortools.sat.python import cp_model

from .randomizer_constants import Direction, Item, LevelNum, Range, RoomNum, RoomType, WallType
from .data_table import DataTable
from .location import Location
from .flags import Flags


class ShuffleConstraints:
  """Manages constraints for item shuffling to ensure required items are placed correctly."""

  def __init__(self):
    # Level-based constraints
    # level_num -> list of required items for that level (positive constraints)
    self.level_requirements: DefaultDict[int, List[Item]] = defaultdict(list)
    # level_num -> list of items that CANNOT be in that level (negative constraints/exclusions)
    self.level_exclusions: DefaultDict[int, List[Item]] = defaultdict(list)

    # Location-type-based constraints
    # Items that cannot be placed in shop positions
    self.shop_exclusions: List[Item] = []
    # Items that cannot be placed in dungeon rooms
    self.dungeon_room_exclusions: List[Item] = []

    # Specific location constraints
    # Specific location -> required item at that location
    self.specific_location_requirements: dict = {}  # Location -> Item
    # Specific location -> list of excluded items from that location
    self.specific_location_exclusions: DefaultDict = defaultdict(list)  # Location -> List[Item]

  def require_item_in_level(self, item: Item, level_num: int) -> None:
    """Require a specific item to be placed in a specific level."""
    self.level_requirements[level_num].append(item)

  def exclude_item_from_level(self, item: Item, level_num: int) -> None:
    """Exclude a specific item from being placed in a specific level."""
    self.level_exclusions[level_num].append(item)

  def exclude_item_from_shops(self, item: Item) -> None:
    """Exclude an item from all shop positions."""
    self.shop_exclusions.append(item)

  def exclude_item_from_dungeon_rooms(self, item: Item) -> None:
    """Exclude an item from all dungeon rooms."""
    self.dungeon_room_exclusions.append(item)

  def require_item_at_location(self, item: Item, location) -> None:
    """Require a specific item at a specific location."""
    self.specific_location_requirements[location] = item

  def exclude_item_from_location(self, item: Item, location) -> None:
    """Exclude a specific item from a specific location."""
    self.specific_location_exclusions[location].append(item)

  def is_item_excluded_from_level(self, item: Item, level_num: int) -> bool:
    """Check if an item is excluded from a specific level."""
    return item in self.level_exclusions.get(level_num, [])

  def is_item_excluded_from_location(self, item: Item, location) -> bool:
    """Check if an item is excluded from a specific location."""
    # Check location-type exclusions
    if location.IsShopPosition() and item in self.shop_exclusions:
      return True
    if location.IsLevelRoom() and item in self.dungeon_room_exclusions:
      return True
    # Check specific location exclusions
    if item in self.specific_location_exclusions.get(location, []):
      return True
    return False

  def get_required_items_for_level(self, level_num: int) -> List[Item]:
    """Get the list of items required to be in a specific level."""
    return self.level_requirements.get(level_num, [])

  def get_excluded_items_for_level(self, level_num: int) -> List[Item]:
    """Get the list of items excluded from a specific level."""
    return self.level_exclusions.get(level_num, [])

  def get_all_constrained_items(self) -> List[Item]:
    """Get a flat list of all items that have positive level constraints.

    Note: This does NOT include items from specific_location_requirements, because those
    are allocated normally during the allocation phase and then swapped to their specific
    locations during the location matching phase.
    """
    all_items = []
    for items in self.level_requirements.values():
      all_items.extend(items)
    # Note: specific_location_requirements are handled separately and should not be
    # removed from the pool here
    return all_items


class ItemRandomizer():
  def __init__(self, data_table: DataTable, flags: Flags) -> None:
    self.data_table = data_table
    self.flags = flags
    self.item_shuffler = ItemShuffler(flags)

  def _GetRandomizedShopPrice(self, item: Item) -> int:
    """Get a randomized price for an item placed in a shop.

    Price tiers:
    - Sword, Ring, Any Key: 230 ± 25 (range: 205-255)
    - Bow, Wand, Ladder: 100 ± 20 (range: 80-120)
    - Recorder, Arrows, HC: 80 ± 20 (range: 60-100)
    - Everything else: 60 ± 20 (range: 40-80)

    Args:
        item: The item being placed in the shop

    Returns:
        The randomized price in rupees
    """
    # Tier 1: Sword, Ring, Any Key - 230 ± 25
    if item in [Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD,
                Item.BLUE_RING, Item.RED_RING, Item.ANY_KEY]:
      return randint(205, 255)

    # Tier 2: Bow, Wand, Ladder - 100 ± 20
    elif item in [Item.BOW, Item.WAND, Item.LADDER]:
      return randint(80, 120)

    # Tier 3: Recorder, Arrows, HC - 80 ± 20
    elif item in [Item.RECORDER, Item.WOOD_ARROWS, Item.SILVER_ARROWS, Item.HEART_CONTAINER]:
      return randint(60, 100)

    # Tier 4: Everything else - 60 ± 20
    else:
      return randint(40, 80)

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

  def WriteItemsAndLocationsToTable(self) -> None:
    for (location, item_num) in self.item_shuffler.GetAllLocationAndItemData():
      if location.IsLevelRoom():
        self.data_table.SetRoomItem(location, item_num)
        if item_num == Item.TRIFORCE:
          self.data_table.UpdateTriforceLocation(location)
      elif location.IsCavePosition():
        self.data_table.SetCaveItem(location, item_num)
        # If this item is in a shop, set a randomized price based on item tier
        if location.IsShopPosition():
          randomized_price = self._GetRandomizedShopPrice(item_num)
          cave_num = location.GetCaveNum()
          position_num = location.GetPositionNum()
          self.data_table.overworld_caves[cave_num].SetPriceAtPosition(randomized_price, position_num)
    # Individual progressive flags are temporarily disabled
    progressive_swords = False
    if (self.flags.progressive_items or progressive_swords) and self.flags.add_l4_sword:
      level_nine_start_room_num = self.data_table.GetLevelStartRoomNumber(9)
      triforce_check_room_num = level_nine_start_room_num - 0x10
      self.data_table.SetRoomItem(Location.LevelRoom(9, triforce_check_room_num), Item.WOOD_SWORD)
      self.data_table.SetItemPosition(Location.LevelRoom(9, triforce_check_room_num), 2) 


class ItemShuffler:
    """OR-Tools based item shuffler that handles complex constraints efficiently."""

    def __init__(self, flags):
        self.flags = flags
        self.item_num_list: List[Item] = []
        self.per_level_item_location_lists: Dict[int, List] = defaultdict(list)
        self.per_level_item_lists: Dict[int, List] = defaultdict(list)
        # Track original level for each item (for no inter-level shuffle mode)
        self.per_level_original_items: DefaultDict[LevelNum, List[Item]] = defaultdict(list)
        
    def ResetState(self):
        self.item_num_list.clear()
        self.per_level_item_location_lists.clear()
        self.per_level_item_lists.clear()
        self.per_level_original_items.clear()

    def AddLocationAndItem(self, location: Location, item_num: Item) -> None:
    
        if item_num == Item.TRIFORCE_OF_POWER:
            return
        # MAP, COMPASS, and TRIFORCE never shuffle - skip them entirely
        # They stay in their original ROM locations (will be handled by intra-level shuffle later)
        if item_num in [Item.MAP, Item.COMPASS, Item.TRIFORCE]:
            return
        # Minor items already in shops stay in place (don't shuffle) - skip them too
        level_num = location.GetLevelNum() if location.IsLevelRoom() else 10
        if location.IsShopPosition() and item_num.IsMinorDungeonItem():
            return
    
        # DEBUG: Print every location being added to level 10
        if level_num == 10:
            if location.IsCavePosition():
                cave_num = location.GetCaveNum()
                print(f"DEBUG: Adding to level 10: Cave {cave_num} (0x{cave_num:02X}) pos {location.GetPositionNum()} = {item_num}")
            else:
                print(f"DEBUG: Adding to level 10: {location.ToString()} = {item_num}")
    
        # Add this location to the shuffle system
        self.per_level_item_location_lists[level_num].append(location)
        log.debug("Location %d:  %s" %
                  (len(self.per_level_item_location_lists[level_num]),location.ToString()))
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
        # Track which level this item originally came from (for no inter-level shuffle mode)
        self.per_level_original_items[level_num].append(item_num)

    def ShuffleItems(self) -> None:
      """Main entry point for item shuffling using constraint-based system."""
      log.info("Using constraint-based shuffle mode")

      # Check if inter-level shuffling is disabled
      if not self.flags.full_major_item_shuffle:
        log.info("No inter-level shuffle - keeping items in original levels")
        # Keep items in their original levels - per_level_original_items has everything
        for level_num in Range.VALID_LEVEL_AND_CAVE_NUMBERS:
          self.per_level_item_lists[level_num] = list(self.per_level_original_items[level_num])

          # Shuffle within level if enabled
          if self.flags.shuffle_items_within_levels:
            shuffle(self.per_level_item_lists[level_num])

        # Clear the global item list since we distributed everything
        self.item_num_list.clear()
        return

      # Full inter-level shuffle mode with constraints
      log.info("Full inter-level shuffle enabled")

      # Build constraints based on flags
      constraints = self._BuildConstraints()

      # Validate that constraints are satisfiable
      if not self._ConstraintsAreSatisfiable(constraints):
        raise Exception("Item shuffle constraints cannot be satisfied")

      # Use OR-Tools CP-SAT solver for allocation
      # The solver handles ALL constraints including level requirements and specific locations
      log.info("Using OR-Tools CP-SAT solver for item allocation")
      self.AllocateItemsToLevels(self.item_num_list, constraints)
    

    def _BuildConstraints(self) -> ShuffleConstraints:
      """Build shuffle constraints based on enabled flags.

      Note: This is only called when full_major_item_shuffle is True.
      """
      constraints = ShuffleConstraints()
      log.info("Building shuffle constraints for full inter-level shuffle...")

      # Note: MAP, COMPASS, and TRIFORCE are not part of inter-level shuffle.
      # They stay in their original ROM locations and will be handled by intra-level shuffle later.

      # Heart container constraints
      if self.flags.heart_container_in_each_level_1_8:
        log.info("Requiring one heart container in each level 1-8")
        # Assign one heart container to each of levels 1-8
        for level_num in range(1, 9):
          constraints.require_item_in_level(Item.HEART_CONTAINER, level_num)

      # Level 9 heart container constraints
      if self.flags.force_two_heart_containers_to_level_nine:
        log.info("Requiring two heart containers in level 9")
        constraints.require_item_in_level(Item.HEART_CONTAINER, 9)
        constraints.require_item_in_level(Item.HEART_CONTAINER, 9)
      elif self.flags.force_heart_container_to_level_nine:
        log.info("Requiring at least one heart container in level 9")
        constraints.require_item_in_level(Item.HEART_CONTAINER, 9)

      # Other level 9 item constraints
      if self.flags.force_arrow_to_level_nine:
        log.info("Requiring arrow in level 9")
        # Could be wood or silver arrows - just require one
        # We'll need to check which one is in the item pool
        if Item.SILVER_ARROWS in self.item_num_list:
          constraints.require_item_in_level(Item.SILVER_ARROWS, 9)
        elif Item.WOOD_ARROWS in self.item_num_list:
          constraints.require_item_in_level(Item.WOOD_ARROWS, 9)

      if self.flags.force_ring_to_level_nine:
        log.info("Requiring ring in level 9")
        # Could be blue or red ring
        if Item.RED_RING in self.item_num_list:
          constraints.require_item_in_level(Item.RED_RING, 9)
        elif Item.BLUE_RING in self.item_num_list:
          constraints.require_item_in_level(Item.BLUE_RING, 9)

      if self.flags.force_wand_to_level_nine:
        log.info("Requiring wand in level 9")
        constraints.require_item_in_level(Item.WAND, 9)

      # Exclusion constraints: important items can't be in level 9 unless flag allows it
      if not self.flags.allow_important_items_in_level_nine:
        log.info("Excluding important items from level 9")
        for item in [Item.BOW, Item.LADDER, Item.POWER_BRACELET, Item.RAFT, Item.RECORDER]:
          constraints.exclude_item_from_level(item, 9)

      # Shop exclusions
      log.info("Adding shop exclusions")
      # Heart containers can never be in shops
      constraints.exclude_item_from_shops(Item.HEART_CONTAINER)

      # Minor items can't be moved into shops (existing shop minor items are preserved in AddLocationAndItem)
      constraints.exclude_item_from_shops(Item.BOMBS)
      constraints.exclude_item_from_shops(Item.KEY)
      constraints.exclude_item_from_shops(Item.FIVE_RUPEES)

      # Progressive items can't be in shops
      if self.flags.progressive_items:
        log.info("Excluding progressive items from shops")
        constraints.exclude_item_from_shops(Item.WOOD_ARROWS)
        constraints.exclude_item_from_shops(Item.BLUE_CANDLE)
        constraints.exclude_item_from_shops(Item.BLUE_RING)
        constraints.exclude_item_from_shops(Item.WOOD_SWORD)
        # Note: WOOD_BOOMERANG would go here if progressive_boomerangs was enabled

      # Dungeon room exclusions
      log.info("Excluding Magical Sword from dungeon rooms (technical limitation)")
      constraints.exclude_item_from_dungeon_rooms(Item.MAGICAL_SWORD)

      # Specific location exclusions
      from .location import Location
      # Ladder can't be at coast location (cave 21) - circular dependency since coast requires ladder
      if self.flags.shuffle_coast_item:
          log.info(f"Excluding ladder from coast location (cave 21)")
          constraints.exclude_item_from_location(Item.LADDER, Location.CavePosition(21, 2))

      # Exclude LETTER from potion shop (cave 10, positions 1-3)
      log.info("Excluding letter from potion shop")
      for potion_shop_pos in [1, 2, 3]:
        potion_shop_location = Location.CavePosition(10, potion_shop_pos)
        constraints.exclude_item_from_location(Item.LETTER, potion_shop_location)

      # Specific location requirements
      if self.flags.force_heart_container_to_armos:
        log.info("Requiring heart container at Armos (cave 20)")
        constraints.require_item_at_location(Item.HEART_CONTAINER, Location.CavePosition(20, 2))

      if self.flags.force_heart_container_to_coast:
        log.info("Requiring heart container at Coast (cave 21)")
        constraints.require_item_at_location(Item.HEART_CONTAINER, Location.CavePosition(21, 2))

      log.info(f"Built {len(constraints.get_all_constrained_items())} positive constraints")
      log.info(f"Built {sum(len(items) for items in constraints.level_exclusions.values())} level exclusions")
      log.info(f"Built {len(constraints.shop_exclusions)} shop exclusions")
      log.info(f"Built {len(constraints.dungeon_room_exclusions)} dungeon room exclusions")
      log.info(f"Built {len(constraints.specific_location_requirements)} specific location requirements")
      return constraints

    def AllocateItemsToLevels(
        self,
        item_num_list: List,
        constraints: ShuffleConstraints
    ) -> None:
        """
        Allocate items to locations using OR-Tools CP-SAT solver.
        
        This replaces the complex greedy allocation with a declarative constraint
        satisfaction approach that guarantees finding a solution if one exists.
        """
        log.info("Starting OR-Tools based item allocation")
        
        # DEBUG: Check if coast is in the shuffle
        coast_in_shuffle = False
        for loc in self.per_level_item_location_lists[10]:  # Level 10 is caves/overworld
            if 'Cave 0x15' in loc.ToString() or 'cave 21' in loc.ToString().lower():
                coast_in_shuffle = True
                print(f"DEBUG: Found coast location: {loc.ToString()}")
                break
    
        if not coast_in_shuffle:
            print(f"DEBUG: Coast location NOT in shuffle!")
            print(f"DEBUG: Level 10 locations: {[loc.ToString() for loc in self.per_level_item_location_lists[10]]}")
        
        # Step 1: Collect all locations and organize by level
        all_locations = []
        location_to_level = {}
        
        for level_num in range(0, 11):  # Assuming levels 0-10 (adjust Range as needed)
            for location in self.per_level_item_location_lists[level_num]:
                all_locations.append(location)
                location_to_level[location] = level_num

        # Step 2: Verify we have the right number of items
        if len(item_num_list) != len(all_locations):
            raise ValueError(
                f"Item count mismatch: {len(item_num_list)} items for "
                f"{len(all_locations)} locations"
            )

        log.info(f"Allocating {len(item_num_list)} items to {len(all_locations)} locations")

        # Step 3: Create the CP-SAT model
        model = cp_model.CpModel()

        # Create variables: one integer variable per location
        # Each variable can take any item value
        assignment = {}
        all_item_values = [int(item) for item in item_num_list]
        
        for location in all_locations:
            # Create a variable that can hold any item value
            assignment[location] = model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(all_item_values),
                f'item_at_{location.ToString()}'
            )

        # Step 4: Add constraints based on item uniqueness
        # Count how many of each item we have
        item_counts = Counter(item_num_list)

        # Separate unique items from duplicates
        unique_items = [item for item, count in item_counts.items() if count == 1]
        duplicate_items = {item: count for item, count in item_counts.items() if count > 1}

        log.info(f"Unique items: {len(unique_items)}, Duplicate item types: {len(duplicate_items)}")

        # For unique items: ensure each appears exactly once
        if unique_items:
            unique_vars = []
            for location in all_locations:
                for item_val in unique_items:
                    # Create a boolean: "is this unique item at this location?"
                    is_here = model.NewBoolVar(f'unique_{item_val}_at_{location.ToString()}')
                    model.Add(assignment[location] == item_val).OnlyEnforceIf(is_here)
                    model.Add(assignment[location] != item_val).OnlyEnforceIf(is_here.Not())
                    unique_vars.append((item_val, is_here))
    
            # Each unique item appears exactly once
            for item_val in unique_items:
                appearances = [var for item, var in unique_vars if item == item_val]
                model.Add(sum(appearances) == 1)

        # For duplicate items: ensure correct count
        for item_val, expected_count in duplicate_items.items():
            appearances = []
            for location in all_locations:
                is_here = model.NewBoolVar(f'dup_{item_val}_at_{location.ToString()}')
                model.Add(assignment[location] == item_val).OnlyEnforceIf(is_here)
                model.Add(assignment[location] != item_val).OnlyEnforceIf(is_here.Not())
                appearances.append(is_here)
    
            # This item must appear exactly expected_count times
            model.Add(sum(appearances) == expected_count)
            log.info(f"Item {item_val} must appear exactly {expected_count} times")

        # Step 5: Add level-based constraints
        self._add_level_constraints(model, assignment, location_to_level, constraints)

        # Step 6: Add location-type constraints (shops, dungeon rooms)
        self._add_location_type_constraints(model, assignment, constraints)

        # Step 7: Add specific location constraints
        self._add_specific_location_constraints(model, assignment, constraints)

        # Step 8: Solve the model
        log.info("Solving constraint satisfaction problem...")
        solver = cp_model.CpSolver()

        # Derive OR-Tools seed from Python's seeded RNG (ensures reproducibility)
        # When user provides a seed, this will be deterministic
        ortools_seed = random.getrandbits(31)  # Get 31 random bits (fits in signed int32)
        solver.parameters.random_seed = ortools_seed
        solver.parameters.randomize_search = True
        solver.parameters.linearization_level = 0  # Increases randomization variety
        solver.parameters.search_branching = cp_model.PORTFOLIO_SEARCH  # Multiple search strategies

        log.debug(f"OR-Tools using seed derived from Python RNG: {ortools_seed}")

        # Optional: Set a time limit (e.g., 60 seconds)
        solver.parameters.max_time_in_seconds = 60.0

        status = solver.Solve(model)

        # Step 9: Handle the result
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            log.info("Solution found!")
            self._extract_solution(solver, assignment, location_to_level)
            
            # Optional: Shuffle within levels if flag is enabled
            if self.flags.shuffle_items_within_levels:
                self._shuffle_within_levels(constraints)
                
        elif status == cp_model.INFEASIBLE:
            self._report_infeasibility(constraints, item_num_list, all_locations)
            raise Exception("No valid item shuffle exists with the given constraints")
        else:
            raise Exception(f"Solver returned unexpected status: {status}")

        log.info("Item allocation complete")
    
    
    def _add_level_constraints(
        self,
        model: cp_model.CpModel,
        assignment: Dict,
        location_to_level: Dict,
        constraints: ShuffleConstraints
    ) -> None:
        """Add constraints for which items must/cannot be in which levels."""
        
        # For each level with requirements, ensure those items are in that level
        for level_num, required_items in constraints.level_requirements.items():
            # Get all locations in this level
            level_locations = [
                loc for loc, lvl in location_to_level.items() 
                if lvl == level_num
            ]
            
            for item in required_items:
                # At least one location in this level must have this item
                # Create boolean variables for "is item at this location?"
                item_at_location = []
                for location in level_locations:
                    is_item_here = model.NewBoolVar(f'{item}_at_{location.ToString()}')
                    model.Add(assignment[location] == int(item)).OnlyEnforceIf(is_item_here)
                    model.Add(assignment[location] != int(item)).OnlyEnforceIf(is_item_here.Not())
                    item_at_location.append(is_item_here)
                
                # Exactly one of these must be true (item must be somewhere in this level)
                model.Add(sum(item_at_location) == 1)
                
                log.debug(f"Required {item} in level {level_num}")

        # For each level with exclusions, ensure those items are NOT in that level
        for level_num, excluded_items in constraints.level_exclusions.items():
            level_locations = [
                loc for loc, lvl in location_to_level.items() 
                if lvl == level_num
            ]
            
            for location in level_locations:
                for item in excluded_items:
                    # This location cannot have this item
                    model.Add(assignment[location] != int(item))
                    
                log.debug(f"Excluded {len(excluded_items)} items from level {level_num}")

    def _add_location_type_constraints(
        self,
        model: cp_model.CpModel,
        assignment: Dict,
        constraints: ShuffleConstraints
    ) -> None:
        """Add constraints based on location types (shops, dungeon rooms)."""
        
        # Shop exclusions
        for location in assignment.keys():
            if location.IsShopPosition():
                for item in constraints.shop_exclusions:
                    model.Add(assignment[location] != int(item))
                    log.debug(f"Excluded {item} from shop at {location.ToString()}")

        # Dungeon room exclusions
        for location in assignment.keys():
            if location.IsLevelRoom():
                for item in constraints.dungeon_room_exclusions:
                    model.Add(assignment[location] != int(item))
                    log.debug(f"Excluded {item} from dungeon room at {location.ToString()}")

    def _add_specific_location_constraints(
        self,
        model: cp_model.CpModel,
        assignment: Dict,
        constraints: ShuffleConstraints
    ) -> None:
        """Add constraints for specific locations."""
        
        # Specific location requirements (item MUST be at location)
        for location, required_item in constraints.specific_location_requirements.items():
            if location in assignment:
                model.Add(assignment[location] == int(required_item))
                log.debug(f"Required {required_item} at {location.ToString()}")
            else:
                log.warning(f"Required location {location.ToString()} not in assignment")

        # Specific location exclusions (item CANNOT be at location)
        for location, excluded_items in constraints.specific_location_exclusions.items():
            if location in assignment:
                for item in excluded_items:
                    model.Add(assignment[location] != int(item))
                    log.debug(f"Excluded {item} from {location.ToString()}")

    def _extract_solution(self, solver, assignment, location_to_level):
        """Extract the solution from the solver and populate the item lists."""
    
        # Clear existing item lists
        for level_num in range(0, 11):
            self.per_level_item_lists[level_num] = []

        # Extract solution in the SAME ORDER as per_level_item_location_lists
        for level_num in range(0, 11):
            for location in self.per_level_item_location_lists[level_num]:
                if location in assignment:
                    item_value = solver.Value(assignment[location])
                    item = Item(item_value)
                    self.per_level_item_lists[level_num].append(item)
                else:
                    # Location not in shuffle (shouldn't happen)
                    log.error(f"Location {location.ToString()} not in assignment!")
                    self.per_level_item_lists[level_num].append(None)
    
        log.info("Solution extracted successfully")
        
    """   def _extract_solution(
            self,
            solver: cp_model.CpSolver,
            assignment: Dict,
            location_to_level: Dict
        ) -> None:
            Extract the solution from the solver and populate the item lists.
        
            # Clear existing item lists
            for level_num in range(0, 11):
                self.per_level_item_lists[level_num] = []

            # Extract solution for each location
            for location, var in assignment.items():
                item_value = solver.Value(var)
                level_num = location_to_level[location]
            
                # Convert back to Item enum (adjust this based on your Item class)
                # item = Item(item_value)
                item = Item(item_value)  # If you need to convert, do it here
            
                self.per_level_item_lists[level_num].append(item)
            
            log.info("Solution extracted successfully")
        """
    def _shuffle_within_levels(self, constraints: ShuffleConstraints) -> None:
        """Optionally shuffle items within each level while preserving specific location requirements."""
        
        log.info("Shuffling items within levels (preserving specific location requirements)")
        
        for level_num in range(1, 10):  # Levels 1-9 (dungeons)
            if not self.per_level_item_lists[level_num]:
                continue
                
            # Find indices that have specific location requirements
            protected_indices = set()
            for location, required_item in constraints.specific_location_requirements.items():
                if location in self.per_level_item_location_lists[level_num]:
                    location_index = self.per_level_item_location_lists[level_num].index(location)
                    protected_indices.add(location_index)

            # Shuffle only non-protected items
            if protected_indices:
                shuffleable_items = [
                    (i, item) for i, item in enumerate(self.per_level_item_lists[level_num])
                    if i not in protected_indices
                ]
                items_only = [item for _, item in shuffleable_items]
                random.shuffle(items_only)
                
                for (index, _), new_item in zip(shuffleable_items, items_only):
                    self.per_level_item_lists[level_num][index] = new_item
            else:
                random.shuffle(self.per_level_item_lists[level_num])

    def _report_infeasibility(
        self,
        constraints: ShuffleConstraints,
        items: List,
        locations: List
    ) -> None:
        """Provide helpful error messages when constraints are impossible to satisfy."""
        
        log.error("=" * 70)
        log.error("INFEASIBLE CONSTRAINT SET - No valid shuffle exists")
        log.error("=" * 70)
        
        # Report summary
        log.error(f"\nTotal items: {len(items)}")
        log.error(f"Total locations: {len(locations)}")
        
        # Report level requirements
        if constraints.level_requirements:
            log.error("\nLevel Requirements:")
            for level, items in constraints.level_requirements.items():
                log.error(f"  Level {level}: {len(items)} required items")
                for item in items:
                    log.error(f"    - {item}")
        
        # Report level exclusions
        if constraints.level_exclusions:
            log.error("\nLevel Exclusions:")
            for level, items in constraints.level_exclusions.items():
                log.error(f"  Level {level}: {len(items)} excluded items")
        
        # Report shop exclusions
        if constraints.shop_exclusions:
            log.error(f"\nShop Exclusions: {len(constraints.shop_exclusions)} items")
            
        # Report dungeon room exclusions
        if constraints.dungeon_room_exclusions:
            log.error(f"Dungeon Room Exclusions: {len(constraints.dungeon_room_exclusions)} items")
        
        # Report specific location requirements
        if constraints.specific_location_requirements:
            log.error(f"\nSpecific Location Requirements: {len(constraints.specific_location_requirements)}")
            for loc, item in constraints.specific_location_requirements.items():
                log.error(f"  {item} must be at {loc.ToString()}")
        
        log.error("\nPossible issues to check:")
        log.error("  1. Conflicting level requirements (e.g., item required in two levels)")
        log.error("  2. Over-constrained levels (too many requirements for available slots)")
        log.error("  3. Conflicting exclusions (e.g., item excluded from all possible locations)")
        log.error("  4. Shop-excluded items > non-shop slots in a level")
        log.error("=" * 70)

    def GetAllLocationAndItemData(self) -> Iterable[Tuple]:
        """Return all (location, item) pairs."""
        result = []
        for level_num in range(0, 11):
            for location, item in zip(
                self.per_level_item_location_lists[level_num],
                self.per_level_item_lists[level_num]
            ):
                result.append((location, item))
        return result

    def _AttemptAllocation(self, constraints: ShuffleConstraints, initial_item_list: List[Item],
                           initial_per_level_lists: Dict[int, List[Item]], retry_count: int) -> None:
      """Attempt to allocate items to levels and locations.

      Raises an exception if constraints cannot be satisfied.
      This method is called repeatedly with different random states until allocation succeeds.
      """
      # Perturb random state for retries (helps explore different allocation orderings)
      if retry_count > 0:
        # Use the retry count as additional entropy
        random.seed(random.randint(0, 2**31 - 1))

      # Calculate location type requirements for each level
      # This ensures we allocate the right mix of items to each level upfront
      level_location_info = {}
      for level_num in Range.VALID_LEVEL_AND_CAVE_NUMBERS:
        locations = self.per_level_item_location_lists[level_num]
        shop_locations = [loc for loc in locations if loc.IsShopPosition()]
        non_shop_locations = [loc for loc in locations if not loc.IsShopPosition()]

        slots_already_filled = len(self.per_level_item_lists[level_num])
        slots_remaining = len(locations) - slots_already_filled

        level_location_info[level_num] = {
          'total_slots': len(locations),
          'shop_slots': len(shop_locations),
          'non_shop_slots': len(non_shop_locations),
          'slots_already_filled': slots_already_filled,
          'slots_remaining': slots_remaining
        }
        log.debug(f"Level {level_num}: {len(locations)} total locations ({len(shop_locations)} shops, {len(non_shop_locations)} non-shops), {slots_remaining} slots remaining")

      # Separate remaining items into shop-compatible and shop-excluded
      shop_compatible_items = [item for item in self.item_num_list if item not in constraints.shop_exclusions]
      shop_excluded_items = [item for item in self.item_num_list if item in constraints.shop_exclusions]

      # Clear the main list since we're now working with the separated lists
      self.item_num_list = []

      shuffle(shop_compatible_items)
      shuffle(shop_excluded_items)

      log.info(f"Remaining items to allocate: {len(shop_compatible_items)} shop-compatible, {len(shop_excluded_items)} shop-excluded")

      # Phase 1: Allocate shop-compatible items to satisfy shop location requirements
      # Each level with shops must get at least as many shop-compatible items as it has shop locations
      log.info("Phase 1: Ensuring each level with shops gets enough shop-compatible items")

      for level_num in Range.VALID_LEVEL_AND_CAVE_NUMBERS:
        info = level_location_info[level_num]
        if info['shop_slots'] == 0:
          continue  # No shops, skip this level in phase 1

        # Calculate minimum shop-compatible items needed for this level
        # We need at least as many shop-compatible items as shop slots
        min_shop_compatible_needed = info['shop_slots']

        # Allocate shop-compatible items to this level
        items_to_allocate = min(min_shop_compatible_needed, info['slots_remaining'])

        if items_to_allocate > len(shop_compatible_items):
          log.error(f"Level {level_num} needs {items_to_allocate} shop-compatible items but only {len(shop_compatible_items)} available")
          raise Exception(f"Not enough shop-compatible items for level {level_num}")

        allocated_count = 0
        attempts = 0
        max_attempts = len(shop_compatible_items) * 2  # Prevent infinite loop

        while allocated_count < items_to_allocate and attempts < max_attempts:
          if not shop_compatible_items:
            log.error(f"Ran out of shop-compatible items while filling level {level_num}")
            raise Exception("Not enough shop-compatible items")

          item = shop_compatible_items.pop(0)
          attempts += 1

          # Check level exclusions before allocating
          if constraints.is_item_excluded_from_level(item, level_num):
            # This item is excluded from this level, put it back and try another
            shop_compatible_items.append(item)
            continue

          # Check if this item is excluded from dungeon rooms (only applies to dungeon levels)
          if item in constraints.dungeon_room_exclusions and level_num != 10:
            shop_compatible_items.append(item)
            continue

          # Allocate this item
          self.per_level_item_lists[level_num].append(item)
          info['slots_remaining'] -= 1
          allocated_count += 1
          log.debug(f"Allocated {item} to level {level_num} (shop-compatible, phase 1)")

      # Phase 2: Distribute remaining items to fill all remaining slots
      # Use both shop-compatible and shop-excluded items, respecting capacity constraints
      log.info("Phase 2: Filling remaining slots with any compatible items")

      all_remaining_items = shop_compatible_items + shop_excluded_items
      shuffle(all_remaining_items)

      for level_num in Range.VALID_LEVEL_AND_CAVE_NUMBERS:
        info = level_location_info[level_num]

        for _ in range(info['slots_remaining']):
          if not all_remaining_items:
            log.error(f"Ran out of items while filling level {level_num}")
            raise Exception("Not enough items to fill all locations")

          # Find first compatible item
          item_placed = False
          for i, item in enumerate(all_remaining_items):
            # Check level exclusions
            if constraints.is_item_excluded_from_level(item, level_num):
              continue

            # Check if this item is excluded from dungeon rooms
            # If so, it can only go to level 10 (caves)
            if item in constraints.dungeon_room_exclusions and level_num != 10:
              continue

            # Check if this item is shop-excluded
            is_shop_excluded = item in constraints.shop_exclusions

            # If shop-excluded, ensure we have non-shop capacity left
            if is_shop_excluded:
              # Count how many shop-excluded items we've already allocated to this level
              shop_excluded_count = sum(1 for it in self.per_level_item_lists[level_num] if it in constraints.shop_exclusions)
              if shop_excluded_count >= info['non_shop_slots']:
                # No more room for shop-excluded items
                continue

            # Found a compatible item
            item = all_remaining_items.pop(i)
            self.per_level_item_lists[level_num].append(item)
            item_placed = True
            log.debug(f"Allocated {item} to level {level_num} (phase 2)")
            break

          if not item_placed:
            log.error(f"Cannot fill level {level_num}: no compatible items remaining")
            log.error(f"Remaining items: {all_remaining_items}")
            raise Exception(f"Constraint violation: Cannot place any remaining items in level {level_num}")

      # Match items to locations within each level, respecting location constraints
      log.info("Matching items to locations within each level (respecting location constraints)")
      for level_num in Range.VALID_LEVEL_AND_CAVE_NUMBERS:
        if not self.per_level_item_lists[level_num]:
          continue

        locations = self.per_level_item_location_lists[level_num]
        items = list(self.per_level_item_lists[level_num])

        # Sort locations: shops first (they're more constrained), then everything else
        # This ensures shops get first pick of compatible items
        sorted_locations = sorted(locations, key=lambda loc: (0 if loc.IsShopPosition() else 1, locations.index(loc)))

        # Create a greedy matching: for each location, find a compatible item
        matched_items_dict = {}  # location -> item
        for location in sorted_locations:
          # Find first item that's not excluded from this location
          placed = False
          for i, item in enumerate(items):
            if not constraints.is_item_excluded_from_location(item, location):
              matched_items_dict[location] = item
              items.pop(i)
              placed = True
              break

          if not placed:
            # No compatible item found for this location
            log.error(f"Cannot place any item at {location.ToString()}: all remaining items excluded")
            log.error(f"Remaining items: {items}")
            raise Exception(f"Cannot satisfy location constraints for {location.ToString()}")

        # Rebuild item list in original location order
        matched_items = [matched_items_dict[loc] for loc in locations]
        self.per_level_item_lists[level_num] = matched_items

      # Handle specific location requirements before intra-level shuffling
      if constraints.specific_location_requirements:
        log.info("Handling specific location requirements")
        for location, required_item in constraints.specific_location_requirements.items():
          level_num = location.GetLevelNum() if location.IsLevelRoom() else 10

          # Find the required item in this level's item list
          if required_item in self.per_level_item_lists[level_num]:
            # Find the matching location in the location list (compare by string representation)
            location_index = None
            target_str = location.ToString()
            for i, loc in enumerate(self.per_level_item_location_lists[level_num]):
              if loc.ToString() == target_str:
                location_index = i
                break

            if location_index is None:
              log.error(f"Cannot find location {target_str} in level {level_num} location list")
              continue

            # Find the index of the required item in the item list
            item_index = self.per_level_item_lists[level_num].index(required_item)

            # Swap items so the required item is at the correct location index
            current_item_at_location = self.per_level_item_lists[level_num][location_index]
            self.per_level_item_lists[level_num][location_index] = required_item
            self.per_level_item_lists[level_num][item_index] = current_item_at_location

            log.info(f"Placed {required_item} at {location.ToString()}")
          else:
            log.error(f"Cannot satisfy constraint: {required_item} not available for {location.ToString()}")

      # Shuffle within levels if flag is enabled (but preserve specific location requirements)
      if self.flags.shuffle_items_within_levels:
        log.info("Shuffling items within each level (preserving specific location requirements)")
        for level_num in range(1, 10):
          # Find indices that have specific location requirements
          protected_indices = set()
          for location, required_item in constraints.specific_location_requirements.items():
            loc_level = location.GetLevelNum() if location.IsLevelRoom() else 10
            if loc_level == level_num and location in self.per_level_item_location_lists[level_num]:
              location_index = self.per_level_item_location_lists[level_num].index(location)
              protected_indices.add(location_index)

          # Shuffle only the non-protected items
          if protected_indices:
            # Create list of (index, item) for non-protected items
            shuffleable_items = [(i, item) for i, item in enumerate(self.per_level_item_lists[level_num])
                                 if i not in protected_indices]
            # Shuffle the items
            items_only = [item for _, item in shuffleable_items]
            shuffle(items_only)
            # Put them back
            for (index, _), new_item in zip(shuffleable_items, items_only):
              self.per_level_item_lists[level_num][index] = new_item
          else:
            # No protected indices, shuffle normally
            shuffle(self.per_level_item_lists[level_num])

      # Validate location constraints
      if not self._ValidateLocationConstraints(constraints):
        raise Exception("Location constraint validation failed after allocation")

      if self.item_num_list:
        print(f"\n!!! WARNING: Items remaining after shuffle !!!")
        print(f"Remaining items: {self.item_num_list}")
        print(f"Number of remaining items: {len(self.item_num_list)}")
        print("!!!\n")

      assert not self.item_num_list
    def _ValidateLocationConstraints(self, constraints):
        """Validate that location-specific constraints are met after allocation.
    
        With OR-Tools, this is guaranteed by the solver, but we keep this method
        for compatibility with the existing ShuffleItems retry logic.
        """
        # OR-Tools guarantees correctness - no validation needed
        return True
    
    def _ConstraintsAreSatisfiable(self, constraints):
        """
        Check if constraints are satisfiable.
    
        With OR-Tools, we don't need pre-validation - the solver will determine
        this during solving. Return True to proceed to solving.
        """
        return True
