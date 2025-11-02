from typing import Dict, List, Tuple
import logging as log

from .randomizer_constants import CaveType, Direction, Enemy, Item, LevelNum, Range, RoomNum, RoomType, WallType
from .data_table import DataTable
from .inventory import Inventory
from .flags import Flags
from .constants import OVERWORLD_BLOCK_TYPES


class Validator(object):
  # Rooms where mobility is restricted without a ladder.
  # Note that while the player can exit and enter through any door in a CIRCLE_MOAT_ROOM, we keep
  # it in this Dict since a room item may not be able to be picked up without the ladder.
  POTENTIAL_LADDER_BLOCK_ROOMS_VALID_TRAVEL_DIRECTIONS: Dict[RoomType, List[Direction]] = {
      RoomType.CIRCLE_MOAT_ROOM: [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST],
      RoomType.DOUBLE_MOAT_ROOM: [Direction.EAST, Direction.WEST],
      RoomType.HORIZONTAL_MOAT_ROOM: [Direction.EAST, Direction.SOUTH, Direction.WEST],
      RoomType.VERTICAL_MOAT_ROOM: [Direction.SOUTH, Direction.WEST, Direction.NORTH],
      RoomType.CHEVY_ROOM: []
  }
  POTENTIAL_LADDER_BLOCK_ROOMS = POTENTIAL_LADDER_BLOCK_ROOMS_VALID_TRAVEL_DIRECTIONS.keys()

  MOVEMENT_CONSTRAINED_ROOMS_VALID_TRAVEL_DIRECTIONS: Dict[RoomType, List[Direction]] = {
      RoomType.HORIZONTAL_CHUTE_ROOM: [Direction.EAST, Direction.WEST],
      RoomType.VERTICAL_CHUTE_ROOM: [Direction.NORTH, Direction.SOUTH],
      RoomType.T_ROOM: [Direction.WEST, Direction.NORTH, Direction.EAST]
  }
  MOVEMENT_CONSTRAINED_ROOMS = MOVEMENT_CONSTRAINED_ROOMS_VALID_TRAVEL_DIRECTIONS.keys()

  def __init__(self, data_table: DataTable, flags: Flags) -> None:
    self.data_table = data_table
    self.flags = flags
    self.inventory = Inventory()
    # Track visited rooms as (level_num, room_num) tuples
    self.visited_rooms: set[tuple[int, int]] = set()

  def IsSeedValid(self) -> bool:
    # Check if accessible sword/wand requirement is met (default behavior, unless disabled by flag)
    if not self.flags.dont_guarantee_starting_sword_or_wand and not self.HasAccessibleSwordOrWand():
        return False

    # Check that no level's start room number equals its overworld entrance screen
    for level_num in Range.VALID_LEVEL_NUMBERS:
      for screen_num in range(0, 0x80):
        if self.data_table.GetScreenDestination(screen_num) == level_num:
          if self.data_table.GetLevelStartRoomNumber(level_num) == screen_num:
            log.warning(f"Invalid seed: Level {level_num} start room number equals overworld entrance screen ({hex(screen_num)})")
            return False

    self.inventory.Reset()
    self.inventory.SetStillMakingProgressBit()
    num_iterations = 0
    while self.inventory.StillMakingProgress():
      num_iterations += 1
      log.debug("Iteration %d of checking" % num_iterations)
      log.debug("Inventory contains: " + self.inventory.ToString())
      self.inventory.ClearMakingProgressBit()
      self.visited_rooms.clear()
      for destination in self.GetAccessibleDestinations():
        if destination in Range.VALID_LEVEL_NUMBERS:
          level_num = destination
          if level_num == 9 and self.inventory.GetTriforceCount() < 8:
            continue
          log.debug("Can access level %d" % level_num)
          self.ProcessLevel(level_num)
        else:
          cave_type = destination
          log.debug("Can access cave type %x" % cave_type)
          if self.CaveRequirementsMet(cave_type):
            for position_num in Range.VALID_CAVE_POSITION_NUMBERS:
              item = self.data_table.GetCaveItem(cave_type, position_num)
              self.inventory.AddItem(item, cave_type, position_num)
      if self.inventory.Has(Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM):
        log.debug("Seed appears to be beatable. :)")
        return True
      elif num_iterations > 10:
        return False
    log.debug("Seed doesn't appear to be beatable. :(")
    return False

  def HasAccessibleSwordOrWand(self) -> bool:
    """Check if wood sword cave or letter cave is accessible from an 'open'
    screen and contains a sword or wand.

    Returns:
        True if at least one of the two caves meets both conditions:
        1. Accessible from a screen with block type "Open"
        2. Contains a sword (any tier) or wand
    """
    # Check all screens with "Open" block type
    for screen_num in range(0x80):
      block_type = self.GetBlockType(screen_num)
      if block_type != "Open":
        continue

      # Get the destination for this open screen
      destination = self.data_table.GetScreenDestination(screen_num)

      # Check if it leads to wood sword cave or letter cave
      if destination == CaveType.WOOD_SWORD_CAVE or destination == CaveType.LETTER_CAVE:
        # Check all three positions in the cave for sword or wand
        for position_num in Range.VALID_CAVE_POSITION_NUMBERS:
          item = self.data_table.GetCaveItem(destination, position_num)

          # Check if item is a sword or wand
          if item in [Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.WAND]:
            return True

    return False

  def GetAccessibleDestinations(self):
    tbr = set()

    for screen_num in range(0, 0x80):
      # Check if we can access this screen
      if not self.CanAccessScreen(screen_num):
        continue

      destination = None      
      # Special case: Coast item screen (0x5F)
      if screen_num == 0x5F:
        destination = CaveType.COAST_ITEM
      # Special case: Armos item screen (read from ROM)
      elif screen_num == self.data_table.GetArmosItemScreen():
        destination = CaveType.ARMOS_ITEM
      else:
        # Normal case: get destination from data table
        destination = self.data_table.GetScreenDestination(screen_num)

      if destination != CaveType.NONE:
        tbr.add(destination)

        # If we can access the Lost Hills Hint cave, add the virtual item to inventory
        if destination == CaveType.LOST_HILLS_HINT:
          self.inventory.AddItem(Item.LOST_HILLS_HINT_VIRTUAL_ITEM, CaveType.LOST_HILLS_HINT, 1)

        # If we can access the Dead Woods Clue cave, add the virtual item to inventory
        if destination == CaveType.DEAD_WOODS_HINT:
          self.inventory.AddItem(Item.DEAD_WOODS_HINT_VIRTUAL_ITEM, CaveType.DEAD_WOODS_HINT, 1)

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


  def GetBlockType(self, screen_num: int) -> str | None:
    """Get the block type for a given screen, accounting for flags."""
    # Special case: Screen 0x5F is the coast item location (requires ladder)
    if screen_num == 0x5F:
      return "Ladder"

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


  def _IsMixedEnemyGroup(self, enemy: Enemy) -> bool:
    """Check if an enemy code represents a mixed enemy group (0x62-0x7F)."""
    return int(enemy) >= 0x62 and int(enemy) <= 0x7F

  def _GetActualEnemies(self, enemy: Enemy) -> List[Enemy]:
    """Get the actual list of enemies, expanding mixed groups from ROM data.

    Args:
        enemy: The enemy code from the room

    Returns:
        List containing either the single enemy or all enemies in a mixed group
    """
    if self._IsMixedEnemyGroup(enemy):
      return self.data_table.GetMixedEnemyGroup(enemy)
    return [enemy]

  def _ContainsEnemyType(self, room_enemy: Enemy, enemy_list: List[Enemy]) -> bool:
    """Check if room contains any of the specified enemy types.

    Expands mixed enemy groups from ROM data to check actual enemies.

    Args:
        room_enemy: The enemy code from the room
        enemy_list: List of enemy types to check for

    Returns:
        True if the room contains any of the specified enemies
    """
    actual_enemies = self._GetActualEnemies(room_enemy)
    return any(e in enemy_list for e in actual_enemies)

  def _RoomHasOnlyZeroHPEnemies(self, actual_enemies: List[Enemy]) -> bool:
    """Check if all enemies in the room have zero HP.

    Args:
        actual_enemies: List of actual enemies (already expanded if mixed group)

    Returns:
        True if ALL enemies have zero HP
    """
    zero_hp_enemies = [Enemy.GEL_1, Enemy.GEL_2, Enemy.BLUE_KEESE, Enemy.RED_KEESE, Enemy.DARK_KEESE]
    return len(actual_enemies) > 0 and all(e in zero_hp_enemies for e in actual_enemies)

  def CanGetRoomItem(self, entry_direction: Direction, level_num: LevelNum, room_num: RoomNum) -> bool:
    """Check if the player can get an item in the given room.

    Args:
        entry_direction: Direction player entered the room from
        level_num: The level number
        room_num: The room number

    Returns:
        True if the player can get the item in this room
    """
    room_type = self.data_table.GetRoomType(level_num, room_num)

    # Can't pick up a room item in any rooms with water/moats without a ladder.
    # TODO: Make a better determination here based on the drop location and the entry direction.
    if room_type in self.POTENTIAL_LADDER_BLOCK_ROOMS and not self.inventory.Has(Item.LADDER):
      return False

    has_drop_bit = self.data_table.HasDropBit(level_num, room_num)
    if has_drop_bit:
      if not self.CanDefeatEnemies(level_num, room_num):
        return False

    if (room_type == RoomType.HORIZONTAL_CHUTE_ROOM
        and entry_direction in [Direction.NORTH, Direction.SOUTH]):
      return False
    if (room_type == RoomType.VERTICAL_CHUTE_ROOM
        and entry_direction in [Direction.EAST, Direction.WEST]):
      return False
    if room_type == RoomType.T_ROOM:
      return False
    return True

  def CanDefeatEnemies(self, level_num: LevelNum, room_num: RoomNum) -> bool:
    """Check if the player can defeat the enemies in a room.

    Args:
        level_num: The level number
        room_num: The room number

    Returns:
        True if the player has the items needed to defeat the room's enemies
    """
    room_enemy = self.data_table.GetRoomEnemy(level_num, room_num)

    # Check if no enemies need to be killed
    if room_enemy in [Enemy.BUBBLE, Enemy.THREE_PAIRS_OF_TRAPS, Enemy.CORNER_TRAPS,
                      Enemy.OLD_MAN, Enemy.THE_KIDNAPPED, Enemy.NOTHING]:
      return True

    actual_enemies = self._GetActualEnemies(room_enemy)

    # Check for specific boss/enemy requirements using ROM data for mixed groups
    if ((room_enemy == Enemy.THE_BEAST and not self.inventory.HasBowSilverArrowsAndSword())
        or (room_enemy in [Enemy.SINGLE_DIGDOGGER, Enemy.TRIPLE_DIGDOGGER] and not self.inventory.HasRecorderAndReusableWeapon())
        or (room_enemy in [Enemy.RED_GOHMA, Enemy.BLUE_GOHMA] and not self.inventory.HasBowAndArrows())
        or (self._ContainsEnemyType(room_enemy, [Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE]) and not self.inventory.HasSword())
        or (room_enemy.IsGleeokOrPatra() and not self.inventory.HasSwordOrWand())
        or (self._RoomHasOnlyZeroHPEnemies(actual_enemies) and not self.inventory.HasReusableWeaponOrBoomerang())
        or (room_enemy == Enemy.HUNGRY_GORIYA and not self.inventory.Has(Item.BAIT))):
      return False

    # Check for Pols Voice using ROM data for mixed groups
    if (self._ContainsEnemyType(room_enemy, [Enemy.POLS_VOICE])
        and not (self.inventory.HasSwordOrWand() or self.inventory.HasBowAndArrows())):
      return False

    # Check for hard combat enemies using ROM data for mixed groups
    if (self.flags.avoid_required_hard_combat
        and self._ContainsEnemyType(room_enemy, [Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4,
                                                   Enemy.PATRA_1, Enemy.PATRA_2, Enemy.BLUE_DARKNUT, Enemy.BLUE_WIZZROBE])
        and not (self.inventory.HasRing() and self.inventory.Has(Item.WHITE_SWORD))):
      return False

    # At this point, assume regular enemies
    return self.inventory.HasReusableWeapon()

  def CaveRequirementsMet(self, cave_type: CaveType) -> bool:
    from .rom_data_specs import RomDataType
    if (cave_type == CaveType.WHITE_SWORD_CAVE
        and self.inventory.GetHeartCount() < self.data_table.GetRomData(RomDataType.WHITE_SWORD_HEART_REQUIREMENT)):
      return False
    if (cave_type == CaveType.MAGICAL_SWORD_CAVE
        and self.inventory.GetHeartCount() < self.data_table.GetRomData(RomDataType.MAGICAL_SWORD_HEART_REQUIREMENT)):
      return False
    if cave_type == CaveType.POTION_SHOP and not self.inventory.Has(Item.LETTER):
      return False
    if cave_type == CaveType.COAST_ITEM and not self.inventory.Has(Item.LADDER):
      raise Exception("Got to a Coast item check that shouldn't be reached")
      return False
    # If the Westlake Mall area is raft blocked, it's possible for the armos item to be raft-blocked
    if cave_type == CaveType.ARMOS_ITEM and not self.inventory.Has(Item.RAFT) and self.flags.EXTRA_RAFT_BLOCKS:
      raise Exception("Got to an Armos check that shouldn't be reached")
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

      # Check if this room has already been visited
      room_key = (level_num, room_num)
      if room_key in self.visited_rooms:
        return []

      log.debug("Visiting level %d room %x" % (level_num, room_num))
      self.visited_rooms.add(room_key)
      tbr = []

      # Check for room items
      if self.CanGetRoomItem(entry_direction, level_num, room_num):
        if self.data_table.HasRoomItem(level_num, room_num):
          room_item = self.data_table.GetRoomItemByCoords(level_num, room_num)
          self.inventory.AddItem(room_item, level_num, room_num)

      # Check for special enemy items
      room_enemy = self.data_table.GetRoomEnemy(level_num, room_num)
      if room_enemy == Enemy.THE_BEAST and self.CanGetRoomItem(entry_direction, level_num, room_num):
          self.inventory.AddItem(Item.BEAST_DEFEATED_VIRTUAL_ITEM, level_num, room_num)
      if room_enemy == Enemy.THE_KIDNAPPED:
          self.inventory.AddItem(Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM, level_num, room_num)

      for direction in (Direction.WEST, Direction.NORTH, Direction.EAST, Direction.SOUTH):
        if self.CanMove(entry_direction, direction, level_num, room_num):
          tbr.append((RoomNum(room_num + direction), Direction(-1 * direction)))

      # Only check for stairways if this room is configured to have a stairway entrance
      if not self._HasStairway(level_num, room_num):
          return tbr      
      
      for stairway_room_num in self.data_table.GetLevelStaircaseRoomNumberList(level_num):
          left_exit = self.data_table.GetStaircaseLeftExit(level_num, stairway_room_num)
          right_exit = self.data_table.GetStaircaseRightExit(level_num, stairway_room_num)

          # Item staircase. Add the item to our inventory.
          if left_exit == room_num and right_exit == room_num:
              staircase_item = self.data_table.GetStaircaseItem(level_num, stairway_room_num)
              if staircase_item is not None:
                  self.inventory.AddItem(staircase_item, level_num, stairway_room_num)
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

  def _HasStairway(self, level_num: LevelNum, room_num: RoomNum) -> bool:
        """Check if a room has a stairway that can be accessed.

        Args:
            level_num: The level number
            room_num: The room number

        Returns:
            True if the room has an accessible stairway
        """
        room_type = self.data_table.GetRoomType(level_num, room_num)

        # Spiral Stair, Narrow Stair, and Diamond Stair rooms always have a staircase
        if room_type.HasOpenStaircase():
            return True

        # Check if there are any shutter doors in this room. If so, they'll open when a middle
        # row pushblock is pushed instead of a stairway appearing
        for direction in [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]:
            if self.data_table.GetRoomWallType(level_num, room_num, direction) == WallType.SHUTTER_DOOR:
                return False

        # Check if "Movable block" bit is set in a room_type that has a middle row pushblock
        if room_type.CanHavePushBlock() and self.data_table.HasMovableBlockBit(level_num, room_num):
            return True
        return False

  def CanMove(self, entry_direction: Direction, exit_direction: Direction, level_num: LevelNum,
              room_num: RoomNum) -> bool:
    """Check if the player can move from one direction to another in a room.

    Args:
        entry_direction: Direction player entered the room from
        exit_direction: Direction player is trying to exit
        level_num: The level number
        room_num: The room number

    Returns:
        True if the player can move in the specified direction
    """
    # Use new traversal logic methods
    if (self._IsPathUnconditionallyBlocked(level_num, room_num, entry_direction, exit_direction)
        or self._HasWaterObstruction(level_num, room_num, entry_direction, exit_direction)):
      return False

    # Hungry goriya room doesn't have a closed shutter door.  So need a special check to similate how
    # it's not possible to move up in the room until the goriya has been properly fed.
    room_enemy = self.data_table.GetRoomEnemy(level_num, room_num)
    if (exit_direction == Direction.NORTH and room_enemy == Enemy.HUNGRY_GORIYA
        and not self.inventory.Has(Item.BAIT)):
      log.debug("Hungry goriya is still hungry :(")
      return False

    wall_type = self.data_table.GetRoomWallType(level_num, room_num, exit_direction)
    if wall_type == WallType.SHUTTER_DOOR and level_num == 9:
      next_room_num = RoomNum(room_num + exit_direction)
      next_room_enemy = self.data_table.GetRoomEnemy(level_num, next_room_num)
      if next_room_enemy == Enemy.THE_KIDNAPPED:
        return self.inventory.Has(Item.BEAST_DEFEATED_VIRTUAL_ITEM)

    if (wall_type == WallType.SOLID_WALL
        or (wall_type == WallType.SHUTTER_DOOR and not self.CanDefeatEnemies(level_num, room_num))):
      return False

    return True

  def _IsPathUnconditionallyBlocked(self, level_num: LevelNum, room_num: RoomNum,
                                     from_direction: Direction, to_direction: Direction) -> bool:
    """Check if a path through a room is unconditionally blocked due to room layout.

    Args:
        level_num: The level number
        room_num: The room number
        from_direction: Direction entering the room
        to_direction: Direction exiting the room

    Returns:
        True if the path is unconditionally blocked (e.g., by chute room constraints)
    """
    room_type = self.data_table.GetRoomType(level_num, room_num)
    if (room_type in self.MOVEMENT_CONSTRAINED_ROOMS
        and (from_direction not in
             self.MOVEMENT_CONSTRAINED_ROOMS_VALID_TRAVEL_DIRECTIONS[room_type] or to_direction
             not in self.MOVEMENT_CONSTRAINED_ROOMS_VALID_TRAVEL_DIRECTIONS[room_type])):
      return True
    return False

  def _HasWaterObstruction(self, level_num: LevelNum, room_num: RoomNum,
                           from_direction: Direction, to_direction: Direction) -> bool:
    """Check if a path through a room is blocked by water (requires ladder).

    Args:
        level_num: The level number
        room_num: The room number
        from_direction: Direction entering the room
        to_direction: Direction exiting the room

    Returns:
        True if the path is blocked by water and player doesn't have ladder
    """
    has_ladder = self.inventory.Has(Item.LADDER)
    room_type = self.data_table.GetRoomType(level_num, room_num)

    if not has_ladder and room_type in self.POTENTIAL_LADDER_BLOCK_ROOMS:
      if (from_direction not in
          self.POTENTIAL_LADDER_BLOCK_ROOMS_VALID_TRAVEL_DIRECTIONS[room_type] or to_direction
          not in self.POTENTIAL_LADDER_BLOCK_ROOMS_VALID_TRAVEL_DIRECTIONS[room_type]):
        return True

    return False
