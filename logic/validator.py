from typing import List, Tuple
import logging as log

from .randomizer_constants import CaveType, Direction, Item, LevelNum, Enemy
from .randomizer_constants import Range, RoomNum, RoomType, WallType
from .data_table import DataTable, Room  # Room re-exported from rom module for backward compat
from .inventory import Inventory
from .location import Location
from .flags import Flags
from .constants import OVERWORLD_BLOCK_TYPES


class Validator(object):

  def __init__(self, data_table: DataTable, flags: Flags, white_sword_hearts: int = 5, magical_sword_hearts: int = 12) -> None:
    self.data_table = data_table
    self.flags = flags
    self.inventory = Inventory()
    self.white_sword_hearts = white_sword_hearts
    self.magical_sword_hearts = magical_sword_hearts

  def GetBlockType(self, screen_num: int) -> str:
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
    elif block_type == "Ladder":
      return self.inventory.Has(Item.LADDER)
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
    else:
        raise Exception(f"Encountered unknown screen block type {block_type}")

    return False

  def GetAccessibleDestinations(self):
    """Return reachable overworld destinations in deterministic order.

    We preserve insertion order so the validator processes caves/levels the same
    way every run while still granting inventory side-effects for duplicate visits.
    """
    seen = set()
    destinations_in_order = []

    for screen_num in range(0, 0x80):
      if not self.CanAccessScreen(screen_num):
        continue

      # Resolve the destination for this screen
      if screen_num == 0x5F:
        destination = CaveType.COAST_ITEM
      elif screen_num == self.data_table.GetArmosItemScreen():
        destination = CaveType.ARMOS_ITEM
      else:
        destination = self.data_table.GetScreenDestination(screen_num)

      if destination == CaveType.NONE:
        continue

      # Apply Lost Hills / Dead Woods side effects regardless of dedupe status
      if destination == CaveType.LOST_HILLS_HINT:
        self.inventory.AddItem(
            Item.LOST_HILLS_HINT_VIRTUAL_ITEM,
            Location(cave_num=CaveType.LOST_HILLS_HINT - 0x10, position_num=1))
      if destination == CaveType.DEAD_WOODS_HINT:
        self.inventory.AddItem(
            Item.DEAD_WOODS_HINT_VIRTUAL_ITEM,
            Location(cave_num=CaveType.DEAD_WOODS_HINT - 0x10, position_num=1))

      if destination not in seen:
        seen.add(destination)
        destinations_in_order.append(destination)

    return destinations_in_order


  def _LogInventorySummary(self, iteration: int) -> None:
    """Log categorized inventory summary at INFO level."""
    log.info(f"\n{'='*60}")
    log.info(f"ITERATION {iteration}")
    log.info(f"{'='*60}")

    # Weapons
    weapons = []
    if self.inventory.Has(Item.WOOD_SWORD): weapons.append("Wood Sword")
    if self.inventory.Has(Item.WHITE_SWORD): weapons.append("White Sword")
    if self.inventory.Has(Item.MAGICAL_SWORD): weapons.append("Magical Sword")
    if self.inventory.Has(Item.WAND): weapons.append("Wand")
    if self.inventory.Has(Item.BOW): weapons.append("Bow")
    if self.inventory.Has(Item.WOOD_ARROWS): weapons.append("Wood Arrows")
    if self.inventory.Has(Item.SILVER_ARROWS): weapons.append("Silver Arrows")
    if self.inventory.Has(Item.BLUE_CANDLE): weapons.append("Blue Candle")
    if self.inventory.Has(Item.RED_CANDLE): weapons.append("Red Candle")
    if self.inventory.Has(Item.WOOD_BOOMERANG): weapons.append("Wood Boomerang")
    if self.inventory.Has(Item.MAGICAL_BOOMERANG): weapons.append("Magical Boomerang")
    log.info(f"  Weapons: {', '.join(weapons) if weapons else 'NONE'}")

    # Traversal
    traversal = []
    if self.inventory.Has(Item.LADDER): traversal.append("Ladder")
    if self.inventory.Has(Item.RAFT): traversal.append("Raft")
    if self.inventory.Has(Item.RECORDER): traversal.append("Recorder")
    if self.inventory.Has(Item.POWER_BRACELET): traversal.append("Power Bracelet")
    if self.inventory.Has(Item.LOST_HILLS_HINT_VIRTUAL_ITEM): traversal.append("Lost Hills Hint")
    if self.inventory.Has(Item.DEAD_WOODS_HINT_VIRTUAL_ITEM): traversal.append("Dead Woods Hint")
    log.info(f"  Traversal: {', '.join(traversal) if traversal else 'NONE'}")

    # Key items
    key_items = []
    if self.inventory.Has(Item.MAGICAL_KEY): key_items.append("Magical Key")
    if self.inventory.Has(Item.LETTER): key_items.append("Letter")
    if self.inventory.Has(Item.BOOK): key_items.append("Book")
    if self.inventory.Has(Item.BLUE_RING): key_items.append("Blue Ring")
    if self.inventory.Has(Item.RED_RING): key_items.append("Red Ring")
    if self.inventory.Has(Item.BAIT): key_items.append("Bait")
    log.info(f"  Key Items: {', '.join(key_items) if key_items else 'NONE'}")

    # Progress
    log.info(f"  Progress: {self.inventory.GetHeartCount()} Hearts, {self.inventory.GetTriforceCount()} Triforces")
    if self.inventory.Has(Item.BEAST_DEFEATED_VIRTUAL_ITEM):
      log.info(f"  Status: Beast Defeated")
    if self.inventory.Has(Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM):
      log.info(f"  Status: Kidnapped Rescued!")

    # Missing important items
    missing = []
    required_items = [
      (Item.WHITE_SWORD, "White Sword"),
      (Item.RECORDER, "Recorder"),
      (Item.RED_CANDLE, "Red Candle"),
      (Item.SILVER_ARROWS, "Silver Arrows"),
      (Item.BOW, "Bow"),
      (Item.MAGICAL_KEY, "Magical Key"),
      (Item.RAFT, "Raft"),
      (Item.LADDER, "Ladder"),
      (Item.WAND, "Wand"),
      (Item.BOOK, "Book"),
      (Item.RED_RING, "Red Ring"),
      (Item.POWER_BRACELET, "Power Bracelet"),
      (Item.LETTER, "Letter"),
      (Item.MAGICAL_BOOMERANG, "Magical Boomerang")
    ]
    for item, name in required_items:
      if not self.inventory.Has(item):
        missing.append(name)
    if missing:
      log.info(f"  MISSING Important Items: {', '.join(missing)}")

  def _LogDestinationAccessibility(self, accessible_destinations: list) -> None:
    """Log which destinations are accessible and which screens are blocked."""
    log.info(f"\n--- Destination Accessibility ---")

    # Log accessible destinations
    accessible_levels = [d for d in accessible_destinations if d in Range.VALID_LEVEL_NUMBERS]
    accessible_caves = [d for d in accessible_destinations if d not in Range.VALID_LEVEL_NUMBERS]

    if accessible_levels:
      log.info(f"  Accessible Levels: {', '.join(['L' + str(l) for l in sorted(accessible_levels)])}")
    else:
      log.info(f"  Accessible Levels: NONE")

    if accessible_caves:
      cave_names = []
      for cave in accessible_caves:
        cave_names.append(f"{cave.name} (0x{cave:02X})")
      log.info(f"  Accessible Caves: {', '.join(cave_names)}")
    else:
      log.info(f"  Accessible Caves: NONE")

    # Log blocked screens with details
    blocked_screens = []
    for screen_num in range(0, 0x80):
      block_type = self.GetBlockType(screen_num)
      if block_type is None or block_type == "Open":
        continue

      if not self.CanAccessScreen(screen_num):
        # Get destination for context
        if screen_num == 0x5F:
          destination = CaveType.COAST_ITEM
        elif screen_num == self.data_table.GetArmosItemScreen():
          destination = CaveType.ARMOS_ITEM
        else:
          destination = self.data_table.GetScreenDestination(screen_num)

        if destination != CaveType.NONE:
          dest_str = f"L{destination}" if destination in Range.VALID_LEVEL_NUMBERS else destination.name
          blocked_screens.append(f"0x{screen_num:02X} ({block_type}) -> {dest_str}")

    if blocked_screens:
      log.info(f"  BLOCKED Screens ({len(blocked_screens)}):")
      for blocked in blocked_screens[:10]:  # Limit to first 10 to avoid spam
        log.info(f"    {blocked}")
      if len(blocked_screens) > 10:
        log.info(f"    ... and {len(blocked_screens) - 10} more blocked screens")

  def _LogFailureState(self, failure_type: str) -> None:
    """Log detailed failure state information at INFO level."""
    log.info(f"\n{'='*60}")
    log.info(f"FAILURE ANALYSIS ({failure_type})")
    log.info(f"{'='*60}")

    # Get accessible destinations
    accessible_destinations = self.GetAccessibleDestinations()
    accessible_levels = [d for d in accessible_destinations if d in Range.VALID_LEVEL_NUMBERS]

    log.info(f"Final Inventory: {self.inventory.ToString()}")
    log.info(f"Hearts: {self.inventory.GetHeartCount()}, Triforces: {self.inventory.GetTriforceCount()}")

    # Show missing required items
    missing = []
    required_items = [
      (Item.WOOD_SWORD, "Wood Sword"),
      (Item.WHITE_SWORD, "White Sword"),
      (Item.MAGICAL_SWORD, "Magical Sword"),
      (Item.BAIT, "Bait"),
      (Item.RECORDER, "Recorder"),
      (Item.BLUE_CANDLE, "Blue Candle"),
      (Item.RED_CANDLE, "Red Candle"),
      (Item.WOOD_ARROWS, "Wood Arrows"),
      (Item.SILVER_ARROWS, "Silver Arrows"),
      (Item.BOW, "Bow"),
      (Item.MAGICAL_KEY, "Magical Key"),
      (Item.RAFT, "Raft"),
      (Item.LADDER, "Ladder"),
      (Item.WAND, "Wand"),
      (Item.BOOK, "Book"),
      (Item.BLUE_RING, "Blue Ring"),
      (Item.RED_RING, "Red Ring"),
      (Item.POWER_BRACELET, "Power Bracelet"),
      (Item.LETTER, "Letter"),
      (Item.WOOD_BOOMERANG, "Wood Boomerang"),
      (Item.MAGICAL_BOOMERANG, "Magical Boomerang"),
      (Item.LOST_HILLS_HINT_VIRTUAL_ITEM, "Lost Hills Hint"),
      (Item.DEAD_WOODS_HINT_VIRTUAL_ITEM, "Dead Woods Hint")
    ]
    for item, name in required_items:
      if not self.inventory.Has(item):
        missing.append(name)
    if missing:
      log.info(f"Missing Required Items: {', '.join(missing)}")

    if accessible_levels:
      log.info(f"Levels Ever Accessible: {', '.join(['L' + str(l) for l in sorted(accessible_levels)])}")
    else:
      log.info(f"Levels Ever Accessible: NONE")

    # Check if Level 9 was accessible
    level_9_accessible = 9 in accessible_levels
    level_9_triforce_ok = self.inventory.GetTriforceCount() >= 8
    log.info(f"Level 9 Status: Accessible={level_9_accessible}, Triforces OK={level_9_triforce_ok}")

    if failure_type == "MISSING_ITEMS":
      # List the missing important items
      missing = []
      required_items = [
        (Item.WHITE_SWORD, "White Sword"),
        (Item.RECORDER, "Recorder"),
        (Item.RED_CANDLE, "Red Candle"),
        (Item.SILVER_ARROWS, "Silver Arrows"),
        (Item.BOW, "Bow"),
        (Item.MAGICAL_KEY, "Magical Key"),
        (Item.RAFT, "Raft"),
        (Item.LADDER, "Ladder"),
        (Item.WAND, "Wand"),
        (Item.BOOK, "Book"),
        (Item.RED_RING, "Red Ring"),
        (Item.POWER_BRACELET, "Power Bracelet"),
        (Item.LETTER, "Letter"),
        (Item.MAGICAL_BOOMERANG, "Magical Boomerang")
      ]
      for item, name in required_items:
        if not self.inventory.Has(item):
          missing.append(name)
      log.info(f"Missing Required Items: {', '.join(missing)}")

    elif failure_type == "NO_RESCUE":
      # Show why we couldn't rescue the kidnapped
      if not level_9_accessible:
        log.info("Problem: Could not access Level 9")
      elif not level_9_triforce_ok:
        log.info(f"Problem: Had access to Level 9 but only {self.inventory.GetTriforceCount()}/8 triforces")
      else:
        log.info("Problem: Had access to Level 9 with 8 triforces, but couldn't reach/defeat the kidnapped room")

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
      # self._LogInventorySummary(num_iterations)
      log.debug("Inventory contains: " + self.inventory.ToString())
      self.inventory.ClearMakingProgressBit()
      self.data_table.ClearAllVisitMarkers()
      log.debug("Checking caves")
      accessible_destinations = self.GetAccessibleDestinations()
      # self._LogDestinationAccessibility(accessible_destinations)

      log.debug(f"\n--- Processing Destinations ---")
      for destination in accessible_destinations:
        if destination in Range.VALID_LEVEL_NUMBERS:
          level_num = destination
          if level_num == 9 and self.inventory.GetTriforceCount() < 8:
            log.debug(f"  Level 9: SKIPPED (need 8 triforces, have {self.inventory.GetTriforceCount()})")
            continue
          log.debug(f"  Processing Level {level_num}")
          self.ProcessLevel(level_num)
        else:
          cave_type = destination
          if self.CanGetItemsFromCave(cave_type):
            log.debug(f"  Processing Cave: {cave_type.name}")
            items_found = []
            for position_num in Range.VALID_CAVE_POSITION_NUMBERS:
              # Location constructor still expects cave_num (array index 0x00-0x15)
              location = Location(cave_num=cave_type - 0x10, position_num=position_num)
              item = self.data_table.GetCaveItem(location)
              if item not in [Item.OVERWORLD_NO_ITEM, Item.MAP, Item.COMPASS, Item.MAGICAL_SHIELD,
                             Item.BOMBS, Item.FIVE_RUPEES, Item.NO_ITEM, Item.SINGLE_HEART,
                             Item.TRIFORCE_OF_POWER]:
                items_found.append(item.name)
              self.inventory.AddItem(item, location)
            if items_found:
              log.debug(f"    -> Found: {', '.join(items_found)}")
          else:
            log.debug(f"  Cave {cave_type.name}: BLOCKED (requirements not met)")

      if num_iterations > 100:
        log.warning("TIMEOUT: Exceeded 100 iterations without completing validation")
        self._LogFailureState("TIMEOUT")
        return False

    if self.inventory.Has(Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM):
      if self.HasAllImportantItems():
        log.info(f"\n{'='*60}")
        log.info("SUCCESS: Seed is valid!")
        log.info(f"{'='*60}")
        return True
      else:
        log.warning("FAILURE: Rescued kidnapped but missing important items")
        self._LogFailureState("MISSING_ITEMS")
        return False
    else:
      log.warning("FAILURE: Never rescued the kidnapped")
      self._LogFailureState("NO_RESCUE")
      return False

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

  def CanGetRoomItem(self, entry_direction: Direction, room: Room) -> bool:
    # Can't pick up a room item in any rooms with water/moats without a ladder.
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

    room_enemy = room.GetEnemy()
    actual_enemies = self._GetActualEnemies(room_enemy)

    # Check for specific boss/enemy requirements using ROM data for mixed groups
    if ((room.HasTheBeast() and not self.inventory.HasBowSilverArrowsAndSword())
        or (room.HasDigdogger() and not self.inventory.HasRecorderAndReusableWeapon())
        or (room.HasGohma() and not self.inventory.HasBowAndArrows())
        or (self._ContainsEnemyType(room_enemy, [Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE]) and not self.inventory.HasSword())
        or (room_enemy.IsGleeokOrPatra() and not self.inventory.HasSwordOrWand())
        or (self._RoomHasOnlyZeroHPEnemies(actual_enemies) and not self.inventory.HasReusableWeaponOrBoomerang())
        or (room.HasHungryGoriya() and not self.inventory.Has(Item.BAIT))):
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

  def CanGetItemsFromCave(self, cave_type: CaveType) -> bool:
    if (cave_type == CaveType.WHITE_SWORD_CAVE
        and self.inventory.GetHeartCount() < self.white_sword_hearts):
      return False
    if (cave_type == CaveType.MAGICAL_SWORD_CAVE
        and self.inventory.GetHeartCount() < self.magical_sword_hearts):
      return False
    if cave_type == CaveType.POTION_SHOP and not self.inventory.Has(Item.LETTER):
      return False
    if cave_type == CaveType.COAST_ITEM and not self.inventory.Has(Item.LADDER):
      return False
    # If the Westlake Mall area is raft blocked, it's possible for the armos item to be raft-blocked
    if cave_type == CaveType.ARMOS_ITEM and not self.inventory.Has(Item.RAFT) and self.flags.EXTRA_RAFT_BLOCKS:
        return False
    return True

  def ProcessLevel(self, level_num: int) -> None:
      # Track (room_num, entry_direction) pairs to allow visiting rooms from different directions
      # This is critical for chute rooms where entry direction affects available exits
      visited_room_direction_pairs = set()

      rooms_to_visit = [(self.data_table.GetLevelStartRoomNumber(level_num),
                         self.data_table.GetLevelEntranceDirection(level_num))]
      while True:
          room_num, direction = rooms_to_visit.pop()

          # Skip if we've already visited this room from this direction
          if (room_num, direction) in visited_room_direction_pairs:
              if not rooms_to_visit:
                  break
              continue

          visited_room_direction_pairs.add((room_num, direction))
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

      log.debug("Visiting level %d room %x" % (level_num, room_num))

      tbr = []

      # Only collect items once per room (not once per entry direction)
      # Use the room's visited marker to track if we've collected items
      if not room.IsMarkedAsVisited():
        room.MarkAsVisited()
        if self.CanGetRoomItem(entry_direction, room) and room.HasItem():
            self.inventory.AddItem(room.GetItem(), Location.LevelRoom(level_num, room_num))
        if room.GetEnemy() == Enemy.THE_BEAST and self.CanGetRoomItem(entry_direction, room):
            self.inventory.AddItem(Item.BEAST_DEFEATED_VIRTUAL_ITEM, Location.LevelRoom(level_num, room_num))
        if room.GetEnemy() == Enemy.THE_KIDNAPPED:
            self.inventory.AddItem(Item.KIDNAPPED_RESCUED_VIRTUAL_ITEM, Location.LevelRoom(level_num, room_num))

      for direction in (Direction.WEST, Direction.NORTH, Direction.EAST, Direction.SOUTH):
        can_move = self.CanMove(entry_direction, direction, level_num, room_num, room)
        if can_move:
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

    # Handle shutter doors
    if wall_type == WallType.SHUTTER_DOOR:
      # Special case: Rooms with RoomAction = 3 (TriforceOfPowerOpensShutters)
      # require BEAST_DEFEATED to pass through shutter doors
      if room.GetRoomAction() == 3:  # RoomAction.TriforceOfPowerOpensShutters
        return self.inventory.Has(Item.BEAST_DEFEATED_VIRTUAL_ITEM)

      # Normal case: Must be able to defeat enemies to open shutters
      if not self.CanDefeatEnemies(room):
        return False

    if wall_type == WallType.SOLID_WALL:
      return False

    # Check for locked doors
    if wall_type in [WallType.LOCKED_DOOR_1, WallType.LOCKED_DOOR_2]:
      if not self.inventory.HasKey():
        return False
      # Use a key when passing through (unless magical key)
      self.inventory.UseKey(level_num, room_num, exit_direction)

    # Check for bomb holes (bombable walls)
    if wall_type == WallType.BOMB_HOLE:
      if not self.inventory.HasSwordOrWand():
        return False

    return True

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
          location = Location(cave_num=destination - 0x10, position_num=position_num)
          item = self.data_table.GetCaveItem(location)

          # Check if item is a sword or wand
          if item in [Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.WAND]:
            return True

    return False

    
  def HasAllImportantItems(self) -> bool:
      for item in [Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.BAIT, Item.RECORDER,
                   Item.BLUE_CANDLE, Item.RED_CANDLE, Item.WOOD_ARROWS, Item.SILVER_ARROWS, Item.BOW, 
                   Item.MAGICAL_KEY, Item.RAFT, Item.LADDER, Item.WAND, Item.BOOK,Item.BLUE_RING,
                   Item.RED_RING, Item.POWER_BRACELET, Item.LETTER, Item.WOOD_BOOMERANG,
                   Item.MAGICAL_BOOMERANG, Item.LOST_HILLS_HINT_VIRTUAL_ITEM, 
                   Item.DEAD_WOODS_HINT_VIRTUAL_ITEM]:
          if not self.inventory.Has(item):
              log.warning(self.inventory.ToString())
              log.warning(f"Found a seed without {item.name}")
              return False
      return True
