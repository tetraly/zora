#8192192025 ice's seed
from typing import List, Tuple
import logging
from .randomizer_constants import CaveNum, CaveType, Direction, Item, LevelNum, Enemy
from .randomizer_constants import Range, RoomNum, RoomType, WallType
from .data_table import DataTable
from .inventory import Inventory
from .location import Location
from .room import Room
from .flags import Flags
from .constants import OVERWORLD_BLOCK_TYPES

import logging as log


class Validator(object):
  WHITE_SWORD_CAVE_NUMBER = 2
  MAGICAL_SWORD_CAVE_NUMBER = 3
  NUM_HEARTS_FOR_WHITE_SWORD_ITEM = 5
  NUM_HEARTS_FOR_MAGICAL_SWORD_ITEM = 12
  POTION_SHOP_NUMBER = 10
  ARMOS_VIRTUAL_CAVE_NUMBER = 0x14
  COAST_VIRTUAL_CAVE_NUMBER = 0x15

  def __init__(self, data_table: DataTable, flags: Flags, white_sword_hearts: int = 5, magical_sword_hearts: int = 12) -> None:
    self.data_table = data_table
    self.flags = flags
    self.inventory = Inventory()
    self.white_sword_hearts = white_sword_hearts
    self.magical_sword_hearts = magical_sword_hearts

  def GetBlockType(self, screen_num: int) -> str:
    """Get the block type for a given screen, accounting for flags."""
    # Get the base block type from the constants
    base_block_type = OVERWORLD_BLOCK_TYPES.get(screen_num)

    # If randomize_lost_hills flag is enabled, mark Vanilla 5 and the two caves to the east as LostHillsHint
    if self.flags.randomize_lost_hills and screen_num in [0x0B, 0x0C, 0x0D]:
      return "LostHillsHint"

    # If randomize_dead_woods flag is enabled, mark screens 0x70, 0x71, 0x72 as DeadWoodsHint
    if self.flags.randomize_dead_woods and screen_num in [0x70, 0x71, 0x72]:
      return "DeadWoodsHint"

    # If extra_raft_blocks flag is enabled, override certain screens
    if self.flags.extra_raft_blocks:
      # Westlake Mall and Casino Corner screens: 0x34, 0x44, 0x0F, 0x0E, 0x1F, 0x1E
      if screen_num in [0x34, 0x44, 0x0F, 0x0E, 0x1F]:
        return "Raft"
      elif screen_num == 0x1E:
        # 0x1E is already Bomb-blocked, so it becomes Raft+Bomb
        return "Raft+Bomb"
        
    # If extra_power_bracelet_blocks flag is enabled, override West Death Mountain screens
    if self.flags.extra_power_bracelet_blocks:
      if screen_num in [0x00, 0x01, 0x02, 0x03, 0x10, 0x12, 0x13]:
        # 0x11 is already Power Bracelet blocked so no change needed
        return "Power Bracelet+Bomb"
    return base_block_type

  def GetAvailableOverworldCaves(self, block_type: str) -> List[int]:
    tbr = set()
    for screen_num in range(0, 0x80):
      # Check if this screen has the required block type
      if self.GetBlockType(screen_num) != block_type:
        continue

      # Get the destination for this screen
      destination = self.data_table.GetScreenDestination(screen_num)
      if destination != CaveType.NONE:
        tbr.add(destination)

    return list(tbr)

  def CanAccessScreen(self, screen_num: int) -> bool:
    """Check if the player can access a given screen based on current inventory."""
    block_type = self.GetBlockType(screen_num)
    if block_type is None:
      return False

    # Check if we have the items required for this block type
    if block_type == "Open":
      return True
    elif block_type == "Bomb":
      return self.inventory.HasSwordOrWand()
    elif block_type == "Ladder+Bomb":
      return self.inventory.HasSwordOrWand() and self.inventory.Has(Item.LADDER)
    elif block_type == "Raft+Bomb":
      return self.inventory.HasSwordOrWand() and self.inventory.Has(Item.RAFT)
    elif block_type == "Candle":
      return self.inventory.HasCandle()
    elif block_type == "Recorder":
      return self.inventory.Has(Item.RECORDER)
    elif block_type == "Raft":
      return self.inventory.Has(Item.RAFT)
    elif block_type == "Power Bracelet":
      return self.inventory.Has(Item.POWER_BRACELET)
    elif block_type == "Power Bracelet+Bomb":
      return self.inventory.HasSwordOrWand() and self.inventory.Has(Item.POWER_BRACELET)
    elif block_type == "LostHillsHint":
      return self.inventory.Has(Item.LOST_HILLS_HINT_VIRTUAL_ITEM)
    elif block_type == "DeadWoodsHint":
      return self.inventory.Has(Item.DEAD_WOODS_HINT_VIRTUAL_ITEM)

    return False

  def GetAccessibleDestinations(self):
    tbr = set()

    for screen_num in range(0, 0x80):
      # Check if we can access this screen
      if not self.CanAccessScreen(screen_num):
        continue

      # Get its destination and add it
      destination = self.data_table.GetScreenDestination(screen_num)
      if destination != CaveType.NONE:
        tbr.add(destination)
        
        # If we can access the Lost Hills Hint cave, add the virtual item to inventory
        if destination == CaveType.LOST_HILLS_HINT:
          self.inventory.AddItem(Item.LOST_HILLS_HINT_VIRTUAL_ITEM,
                                 Location(cave_num=int(CaveType.LOST_HILLS_HINT)-0x10, position_num=1))

        # If we can access the Dead Woods Clue cave, add the virtual item to inventory
        if destination == CaveType.DEAD_WOODS_HINT:
          self.inventory.AddItem(Item.DEAD_WOODS_HINT_VIRTUAL_ITEM,
                                 Location(cave_num=int(CaveType.DEAD_WOODS_HINT)-0x10, position_num=1))

    return list(tbr)


  def IsSeedValid(self) -> bool:
    log.debug("Starting check of whether the seed is valid or not")

    # Check if accessible sword/wand requirement is met (default behavior, unless disabled by flag)
    if not self.flags.dont_guarantee_starting_sword_or_wand:
      if not self.HasAccessibleSwordOrWand():
        return False

    # Check that no level's start room number equals its overworld entrance screen
    for level_num in Range.VALID_LEVEL_NUMBERS:
      start_room_num = self.data_table.GetLevelStartRoomNumber(level_num)
      # Find which overworld screen leads to this level
      for screen_num in range(0, 0x80):
        destination = self.data_table.GetScreenDestination(screen_num)
        if destination == level_num:
          if screen_num == start_room_num:
            log.warning(f"Invalid seed: Level {level_num} start room ({hex(start_room_num)}) equals overworld entrance screen ({hex(screen_num)})")
            return False
          break

    self.inventory.Reset()
    self.inventory.SetStillMakingProgressBit()
    num_iterations = 0
    while self.inventory.StillMakingProgress():
      num_iterations += 1
      log.debug("Iteration %d of checking" % num_iterations)
      log.debug("Inventory contains: " + self.inventory.ToString())
      self.inventory.ClearMakingProgressBit()
      self.data_table.ClearAllVisitMarkers()
      log.debug("Checking caves")
      for destination in self.GetAccessibleDestinations():
        if destination in Range.VALID_LEVEL_NUMBERS:
          level_num = destination
          if level_num == 9 and self.inventory.GetTriforceCount() < 8:
            continue
          log.debug("Can access level %d" % level_num)
          self.ProcessLevel(level_num)
        else:
          cave_num = destination - 0x10
          log.debug("Can access cave type %x" % cave_num)
          if self.CanGetItemsFromCave(cave_num):
            for position_num in Range.VALID_CAVE_POSITION_NUMBERS:
              location = Location(cave_num=cave_num, position_num=position_num)
              self.inventory.AddItem(self.data_table.GetCaveItem(location), location)
      if self.CanEnterLevel(9):
        pass
      if self.inventory.Has(Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM):
        log.debug("Seed appears to be beatable. :)")
        return True
      elif num_iterations > 100:
        return False
    log.debug("Seed doesn't appear to be beatable. :(")
    return False

  def CanGetRoomItem(self, entry_direction: Direction, room: Room) -> bool:
    # Can't pick up a room in any rooms with water/moats without a ladder.
    # TODO: Make a better determination here based on the drop location and the entry direction.
    if room.HasPotentialLadderBlock() and not self.inventory.Has(Item.LADDER):
      return False
    if room.HasDropBitSet() and not self.CanDefeatEnemies(room):
      return False
    if (room.GetType() == RoomType.HORIZONTAL_CHUTE_ROOM
        and entry_direction in [Direction.NORTH, Direction.SOUTH]):
      return False
    if (room.GetType() == RoomType.VERTICAL_CHUTE_ROOM
        and entry_direction in [Direction.EAST, Direction.WEST]):
      return False
    if room.GetType() == RoomType.T_ROOM:
      return False
    return True

  def CanDefeatEnemies(self, room: Room) -> bool:
    if room.HasNoEnemiesToKill():
      return True
    if ((room.HasTheBeast() and not self.inventory.HasBowSilverArrowsAndSword())
        or (room.HasDigdogger() and not self.inventory.HasRecorderAndReusableWeapon())
        or (room.HasGohma() and not self.inventory.HasBowAndArrows())
        or (room.HasWizzrobes() and not self.inventory.HasSword())
        or (room.GetEnemy().IsGleeokOrPatra() and not self.inventory.HasSwordOrWand())
        or (room.HasOnlyZeroHPEnemies() and not self.inventory.HasReusableWeaponOrBoomerang())
        or (room.HasHungryGoriya() and not self.inventory.Has(Item.BAIT))):
      return False
    if (room.HasPolsVoice()
        and not (self.inventory.HasSwordOrWand() or self.inventory.HasBowAndArrows())):
      return False
    if (self.flags.avoid_required_hard_combat and room.HasHardCombatEnemies()
        and not (self.inventory.HasRing() and self.inventory.Has(Item.WHITE_SWORD))):
      return False

    # At this point, assume regular enemies
    return self.inventory.HasReusableWeapon()

  def CanGetItemsFromCave(self, cave_num: CaveNum) -> bool:
    if (cave_num == self.WHITE_SWORD_CAVE_NUMBER
        and self.inventory.GetHeartCount() < self.white_sword_hearts):
      return False
    if (cave_num == self.MAGICAL_SWORD_CAVE_NUMBER
        and self.inventory.GetHeartCount() < self.magical_sword_hearts):
      return False
    if cave_num == self.POTION_SHOP_NUMBER and not self.inventory.Has(Item.LETTER):
      return False
    if cave_num == self.COAST_VIRTUAL_CAVE_NUMBER and not self.inventory.Has(Item.LADDER):
      return False
    # If the Westlake Mall area is raft blocked, it's possible for the armos item to be raft-blocked
    if self.flags.EXTRA_RAFT_BLOCKS and not self.inventory.Has(Item.RAFT) and cave_num == self.ARMOS_VIRTUAL_CAVE_NUMBER:
        return False 
    return True

  #TODO: Refactor this method now that we have more sophisitcated OW validation logic
  def CanEnterLevel(self, level_num: LevelNum) -> bool:
    if level_num == 4 and not self.inventory.Has(Item.RAFT):
      return False
    if level_num == 7 and not self.inventory.Has(Item.RECORDER):
      return False
    if level_num == 8 and not self.inventory.HasCandle():
      return False
    if level_num == 9 and self.inventory.GetTriforceCount() < 8:
      return False
    return True

  def ProcessLevel(self, level_num: int) -> None:
      rooms_to_visit = [(self.data_table.GetLevelStartRoomNumber(level_num), 
                         self.data_table.GetLevelEntranceDirection(level_num))]
      while True:
          room_num, direction = rooms_to_visit.pop()
          new_rooms = self._VisitRoom(level_num, room_num, direction)
          if new_rooms:
              rooms_to_visit.extend(new_rooms)
          if not rooms_to_visit:
              break
      
  def _VisitRoom(self,
                 level_num: int,
                 room_num: RoomNum,
                 entry_direction: Direction) -> List[Tuple[RoomNum, Direction]]:
      if room_num not in range(0, 0x80):
        return []
      room = self.data_table.GetRoom(level_num, room_num)
      if room.IsMarkedAsVisited():
        return []
      log.debug("Visiting level %d room %x" % (level_num, room_num))
      room.MarkAsVisited()
      tbr = []

      if self.CanGetRoomItem(entry_direction, room) and room.HasItem():
          self.inventory.AddItem(room.GetItem(), Location.LevelRoom(level_num, room_num))
      if room.GetEnemy() == Enemy.THE_BEAST and self.CanGetRoomItem(entry_direction, room):
          self.inventory.AddItem(Item.BEAST_DEFEATED_VIRTUAL_ITEM, Location.LevelRoom(level_num, room_num))
      if room.GetEnemy() == Enemy.THE_KIDNAPPED:
          self.inventory.AddItem(Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM, Location.LevelRoom(level_num, room_num))

      for direction in (Direction.WEST, Direction.NORTH, Direction.EAST, Direction.SOUTH):
        if self.CanMove(entry_direction, direction, level_num, room_num, room):
          tbr.append((RoomNum(room_num + direction), Direction(-1 * direction)))

      # Only check for stairways if this room is configured to have a stairway entrance
      if not self._HasStairway(room):
          return tbr      
      
      for stairway_room_num in self.data_table.GetLevelStaircaseRoomNumberList(level_num):
          stairway_room = self.data_table.GetRoom(level_num, stairway_room_num)
          left_exit = stairway_room.GetLeftExit()
          right_exit = stairway_room.GetRightExit()

          # Item staircase. Add the item to our inventory.
          if left_exit == room_num and right_exit == room_num:
              self.inventory.AddItem(
                  stairway_room.GetItem(), Location.LevelRoom(level_num, stairway_room_num))
          # Transport stairway cases. Add the connecting room to be checked.
          elif left_exit == room_num and right_exit != room_num:
                tbr.append((right_exit, Direction.STAIRCASE))
                # Stop looking for additional staircases after finding one
                break
          elif right_exit == room_num and left_exit != room_num:
                tbr.append((left_exit, Direction.STAIRCASE))
                # Stop looking for additional staircases after finding one
                break
      return tbr

  def _HasStairway(self, room: Room) -> bool:
        room_type = room.GetType()

        # Spiral Stair, Narrow Stair, and Diamond Stair rooms always have a staircase
        if room_type.HasOpenStaircase():
            return True

        # Check if there are any shutter doors in this room. If so, they'll open when a middle
        # row pushblock is pushed instead of a stairway appearing
        for direction in [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]:
            if room.GetWallType(direction) == WallType.SHUTTER_DOOR:
                return False

        # Check if "Movable block" bit is set in a room_type that has a middle row pushblock
        if room_type.CanHavePushBlock() and room.HasMovableBlockBitSet():
            return True
        return False


  def CanMove(self, entry_direction: Direction, exit_direction: Direction, level_num: LevelNum,
              room_num: RoomNum, room: Room) -> bool:
    if (room.PathUnconditionallyObstructed(entry_direction, exit_direction)
        or room.PathObstructedByWater(entry_direction, exit_direction,
                                      self.inventory.Has(Item.LADDER))):
      return False

    # Hungry goriya room doesn't have a closed shutter door.  So need a special check to similate how
    # it's not possible to move up in the room until the goriya has been properly fed.
    if (exit_direction == Direction.NORTH and room.HasHungryGoriya() and not self.inventory.Has(Item.BAIT)):
      log.debug("Hungry goriya is still hungry :(")
      return False

    wall_type = room.GetWallType(exit_direction)
    if wall_type == WallType.SHUTTER_DOOR and level_num == 9:
      next_room = self.data_table.GetRoom(level_num, RoomNum(room_num + exit_direction))
      if next_room.GetEnemy() == Enemy.THE_KIDNAPPED:
        return self.inventory.Has(Item.BEAST_DEFEATED_VIRTUAL_ITEM)
     
    if (wall_type == WallType.SOLID_WALL
        or (wall_type == WallType.SHUTTER_DOOR and not self.CanDefeatEnemies(room))):
      return False

    # Disable key checking for now
    #if wall_type in [WallType.LOCKED_DOOR_1, WallType.LOCKED_DOOR_2]:
    #  if self.inventory.HasKey():
    #    self.inventory.UseKey(level_num, room_num, exit_direction)
    #  else:
    #    return False
    return True

  def HasAccessibleSwordOrWand(self) -> bool:
    """Check if wood sword cave (cave 0) or letter cave (cave 8) is accessible from an 'open'
    screen and contains a sword or wand.

    Returns:
        True if at least one of the two caves meets both conditions:
        1. Accessible from a screen with block type "Open"
        2. Contains a sword (any tier) or wand
    """
    WOOD_SWORD_CAVE_NUM = 0
    LETTER_CAVE_NUM = 8

    # Check all screens with "Open" block type
    for screen_num in range(0x80):
      block_type = self.GetBlockType(screen_num)
      if block_type != "Open":
        continue

      # Get the destination for this open screen
      destination = self.data_table.GetScreenDestination(screen_num)

      # Check if it leads to wood sword cave or letter cave
      if destination == CaveType.WOOD_SWORD_CAVE or destination == CaveType.LETTER_CAVE:
        cave_num = int(destination) - 0x10

        # Check all three positions in the cave for sword or wand
        for position_num in Range.VALID_CAVE_POSITION_NUMBERS:
          location = Location(cave_num=cave_num, position_num=position_num)
          item = self.data_table.GetCaveItem(location)

          # Check if item is a sword or wand
          if item in [Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.WAND]:
            return True

    return False
