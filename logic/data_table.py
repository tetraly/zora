import logging as log
from typing import Any, Dict, List
from .randomizer_constants import CaveNum, CaveType, Direction, Enemy, Item, LevelNum, Range, RoomNum, RoomType, WallType
from .constants import ENTRANCE_DIRECTION_MAP
from .room import Room
from .location import Location
from .cave import Cave
from .patch import Patch
from .rom_reader import RomReader

NES_FILE_OFFSET = 0x10
START_ROOM_OFFSET = 0x2F
STAIRWAY_LIST_OFFSET = 0x34
LEVEL_1_TO_6_DATA_START_ADDRESS = 0x18700 + NES_FILE_OFFSET
LEVEL_7_TO_9_DATA_START_ADDRESS = 0x18A00 + NES_FILE_OFFSET
LEVEL_TABLE_SIZE = 0x80
NUM_BYTES_OF_DATA_PER_ROOM = 6
CAVE_ITEM_DATA_START_ADDRESS = 0x18600 + NES_FILE_OFFSET
CAVE_PRICE_DATA_START_ADDRESS = 0x1863C + NES_FILE_OFFSET
CAVE_NUMBER_REPRESENTING_ARMOS_ITEM = 0x14
CAVE_NUMBER_REPRESENTING_COAST_ITEM = 0x15
ARMOS_ITEM_ADDRESS = 0x10CF5 + NES_FILE_OFFSET
ARMOS_SCREEN_ADDRESS = 0x10CB2  # ROM address (without header) - _ReadMemory adds NES_HEADER_OFFSET
COAST_ITEM_ADDRESS = 0x1788A + NES_FILE_OFFSET
COMPASS_ROOM_NUMBER_ADDRESS = 0x1942C + NES_FILE_OFFSET
SPECIAL_DATA_LEVEL_OFFSET = 0xFC


class DataTable():

  def __init__(self, rom_reader: RomReader) -> None:
    self.rom_reader = rom_reader

    # Check if this is a Race ROM before attempting to read level data
    if self.rom_reader.IsRaceRom():
      raise ValueError(
        "This appears to be a Race ROM, which is not supported.\n\n"
        "Race ROMs use a modified memory layout that prevents the randomizer\n"
        "from reading level data correctly.\n\n"
        "Please try again using a ROM generated without the Race ROM feature."
      )

    self.level_1_to_6_raw_data = self.rom_reader.GetLevelBlock(1)
    self.level_7_to_9_raw_data = self.rom_reader.GetLevelBlock(7)
    self.overworld_raw_data = self.rom_reader.GetLevelBlock(0)
    self.overworld_cave_raw_data = self.rom_reader.GetLevelBlock(0)[0x80*4:0x80*5]
    self.level_info: List[List[int]] = []
    self._ReadLevelInfo()

    self.level_1_to_6_rooms: List[Room] = []
    self.level_7_to_9_rooms: List[Room] = []
    self.overworld_caves: List[Cave] = []
    self.triforce_locations: Dict[LevelNum, RoomNum] = {}

    # Read mixed enemy group data from ROM
    self.mixed_enemy_groups = self.rom_reader.GetMixedEnemyGroups()

    # Initialize ROM data state using ROM_DATA_SPECS
    # For readable data, read from ROM; for write-only data, use default_value
    from .rom_data_specs import ROM_DATA_SPECS, RomDataType
    for data_type, spec in ROM_DATA_SPECS.items():
      state_key = f"_{data_type.name.lower()}"
      if spec.readable:
        # Read from ROM
        raw_data = list(self.rom_reader._ReadMemory(spec.cpu_address, spec.size))
        if spec.decoder:
          setattr(self, state_key, spec.decoder(raw_data))
        else:
          setattr(self, state_key, raw_data)
      else:
        # Write-only: use default value
        setattr(self, state_key, spec.default_value)

  def ResetToVanilla(self) -> None:
    self.level_1_to_6_rooms = self._ReadDataForLevelGrid(self.level_1_to_6_raw_data)
    self.level_7_to_9_rooms = self._ReadDataForLevelGrid(self.level_7_to_9_raw_data)
    self._ReadDataForOverworldCaves()
    self.triforce_locations = {}

  def GetScreenDestination(self, screen_num: int) -> CaveType:
    # Skip any screens that aren't "Secret in 1st Quest"
    if (self.overworld_raw_data[screen_num + 5*0x80] & 0x80) > 0:
      return CaveType.NONE
    # Cave destination is upper 6 bits of table 1
    destination = self.overworld_raw_data[screen_num + 1*0x80] >> 2
    if destination == 0:
      return CaveType.NONE
    return CaveType(destination)

  def SetScreenDestination(self, screen_num: int, cave_type: CaveType) -> None:
    """Set the cave/level destination for an overworld screen.

    Args:
        screen_num: The overworld screen number (0-127)
        cave_type: The CaveType enum value to set as the destination
    """
    # Preserve the lower 2 bits of table 1 (which contain other data)
    lower_bits = self.overworld_raw_data[screen_num + 1*0x80] & 0x03
    # Set the upper 6 bits to the cave type value (shift left by 2)
    self.overworld_raw_data[screen_num + 1*0x80] = (int(cave_type) << 2) | lower_bits

  def GetArmosItemScreen(self) -> int:
    """Get the screen number where the armos item is located.

    Returns:
        The overworld screen number (0-127) where the armos item statue is located
    """
    return self.rom_reader._ReadMemory(ARMOS_SCREEN_ADDRESS, 1)[0]

  def _ReadLevelInfo(self):
    self.is_z1r = True
    for level_num in range(0, 10):
        level_info = self.rom_reader.GetLevelInfo(level_num)
        self.level_info.append(level_info)
        vals = level_info[0x34:0x3E]
        if vals[-1] in range(0, 5):
            continue
        self.is_z1r = False

  def _ReadDataForLevelGrid(self, level_data: List[int]) -> List[Room]:
    rooms: List[Room] = []
    for room_num in Range.VALID_ROOM_NUMBERS:
      room_data: List[int] = []
      for byte_num in range(0, NUM_BYTES_OF_DATA_PER_ROOM):
        room_data.append(level_data[byte_num * LEVEL_TABLE_SIZE + room_num])
      rooms.append(Room(room_data))
    return rooms

  def _ReadDataForOverworldCaves(self) -> None:
    self.overworld_caves = []
    for cave_num in Range.VALID_CAVE_NUMBERS:
      if cave_num == CAVE_NUMBER_REPRESENTING_ARMOS_ITEM:
        self.overworld_caves.append(Cave([0x3F, self.rom_reader.GetArmosItem(), 0x7F, 0x00, 0x00, 0x00]))
      elif cave_num == CAVE_NUMBER_REPRESENTING_COAST_ITEM:
        self.overworld_caves.append(Cave([0x3F, self.rom_reader.GetCoastItem(), 0x7F, 0x00, 0x00, 0x00]))
      else:
        assert cave_num in range(0, 0x14)
        cave_data: List[int] = []
        for cave_item_byte_num in range(0, 3):
          cave_data.append(self.overworld_cave_raw_data[(3 * cave_num) + cave_item_byte_num])
        for cave_price_byte_num in range(0, 3):
          cave_data.append(
              self.overworld_cave_raw_data[0x3C + (3 * cave_num) + cave_price_byte_num])
        self.overworld_caves.append(Cave(cave_data))
    assert len(self.overworld_caves) == 22  # 0-19 are actual caves, 20-21 are for the armos/coast

  def GetRoom(self, level_num: LevelNum, room_num: RoomNum) -> Room:
    assert level_num in Range.VALID_LEVEL_NUMBERS
    assert room_num in Range.VALID_ROOM_NUMBERS

    if level_num in [7, 8, 9]:
      return self.level_7_to_9_rooms[room_num]
    return self.level_1_to_6_rooms[room_num]

  def GetRoomItem(self, location: Location) -> Item:
    assert location.IsLevelRoom()
    if location.GetLevelNum() in [7, 8, 9]:
      return self.level_7_to_9_rooms[location.GetRoomNum()].GetItem()
    return self.level_1_to_6_rooms[location.GetRoomNum()].GetItem()

  def SetRoomItem(self, location: Location, item: Item) -> None:
    assert location.IsLevelRoom()
    if location.GetLevelNum() in [7, 8, 9]:
      self.level_7_to_9_rooms[location.GetRoomNum()].SetItem(item)
    else:
      self.level_1_to_6_rooms[location.GetRoomNum()].SetItem(item)

  def SetItemPosition(self, location: Location, position_num: int) -> None:
    assert location.IsLevelRoom()
    if location.GetLevelNum() in [7, 8, 9]:
      self.level_7_to_9_rooms[location.GetRoomNum()].SetItemPosition(position_num)
    else:
      self.level_1_to_6_rooms[location.GetRoomNum()].SetItemPosition(position_num)

  def GetCaveItem(self, cave_type: int, position_num: int) -> Item:
    """Get an item from a cave at a specific position.

    Args:
        cave_type: CaveType value (0x10-0x25)
        position_num: Position within the cave (0-2)

    Returns:
        The item at the specified location
    """
    # Convert CaveType to cave_num (array index)
    cave_num = cave_type - 0x10

    # Special case: Armos item (cave_num would be 0x14)
    if cave_num == CAVE_NUMBER_REPRESENTING_ARMOS_ITEM:
      return Item(self.rom_reader.GetOverworldItemData()[0])
    # Special case: Coast item (cave_num would be 0x15)
    elif cave_num == CAVE_NUMBER_REPRESENTING_COAST_ITEM:
      return Item(self.rom_reader.GetOverworldItemData()[1])
    return self.overworld_caves[cave_num].GetItemAtPosition(position_num)

  def SetCaveItem(self, cave_type: int, position_num: int, item: Item) -> None:
    """Set an item in a cave at a specific position.

    Args:
        cave_type: CaveType value (0x10-0x25)
        position_num: Position within the cave (0-2)
        item: The item to place
    """
    # Convert CaveType to cave_num (array index)
    cave_num = cave_type - 0x10
    self.overworld_caves[cave_num].SetItemAtPosition(item, position_num)

  def UpdateTriforceLocation(self, location: Location) -> None:
    room_num = location.GetRoomNum()
    room = self.GetRoom(location.GetLevelNum(), room_num)
    if room.IsItemStaircase():
      room_num = room.GetLeftExit()
    self.triforce_locations[location.GetLevelNum()] = room_num

  # Gets the Room number of the start screen for a level.
  #def GetLevelStartRoomNumber(self, level_num: LevelNum) -> RoomNum:
  #  assert level_num in Range.VALID_LEVEL_NUMBERS
  #  return self.LEVEL_START_ROOM_NUMBERS[level_num - 1]

  def GetLevelStartRoomNumber(self, level_num: int) -> RoomNum:
      log.debug("Level %d start room is %x" %
                      (level_num, self.level_info[level_num][START_ROOM_OFFSET]))
      return RoomNum(self.level_info[level_num][START_ROOM_OFFSET])

  def GetLevelEntranceDirection(self, level_num: int) -> Direction:
      if not self.is_z1r:
          return Direction.SOUTH
      # Cast from constants.Direction to randomizer_constants.Direction
      return Direction(ENTRANCE_DIRECTION_MAP[self._GetRawLevelStairwayRoomNumberList(level_num)[-1]])
  # Gets a list of staircase rooms for a level.
  #
  # Note that this will include not just passage staircases between two
  # dungeon rooms but also item rooms with only one passage two and
  # from a dungeon room.
  #def GetLevelStaircaseRoomNumberList(self, level_num: LevelNum) -> List[RoomNum]:
  #  assert level_num in Range.VALID_LEVEL_NUMBERS
  #  return self.STAIRCASE_LISTS[level_num]

  def _GetRawLevelStairwayRoomNumberList(self, level_num: int) -> List[int]:
        vals = self.level_info[level_num][
            STAIRWAY_LIST_OFFSET:STAIRWAY_LIST_OFFSET + 10]
        stairway_list = []  # type: List[int]
        for val in vals:
            if val != 0xFF:
                stairway_list.append(val)

        # This is a hack needed in order to make vanilla L3 work.  For some reason,
        # the vanilla ROM's data for level 3 doesn't include a stairway room even
        # though there obviously is one in vanilla level 3.
        #
        # See http://www.romhacking.net/forum/index.php?topic=18750.msg271821#msg271821
        # for more information about why this is the case and why this hack
        # is needed.
        if level_num == 3 and not stairway_list:
            stairway_list.append(0x0F)
        return stairway_list

  def GetLevelStaircaseRoomNumberList(self, level_num: int) -> List[RoomNum]:
        stairway_list = self._GetRawLevelStairwayRoomNumberList(level_num)
        # In randomized roms, the last item in the stairway list is the entrance dir.
        if self.is_z1r:
            stairway_list.pop(-1)
        return [RoomNum(room) for room in stairway_list]

  def GetPatch(self) -> Patch:
    patch = Patch()
    patch += self._GetPatchForLevelGrid(LEVEL_1_TO_6_DATA_START_ADDRESS,
                                        self.level_1_to_6_rooms)
    patch += self._GetPatchForLevelGrid(LEVEL_7_TO_9_DATA_START_ADDRESS,
                                        self.level_7_to_9_rooms)
    patch += self._GetPatchForOverworldCaveData()
    patch += self._GetPatchForOverworldScreenDestinations()
    patch += self._GetPatchForRomData()  # Generic ROM data patches (includes heart requirements)
    return patch

  def _GetPatchForLevelGrid(self, start_address: int, rooms: List[Room]) -> Patch:
    patch = Patch()
    for room_num in Range.VALID_ROOM_NUMBERS:
      room_data = rooms[room_num].GetRomData()
      assert len(room_data) == NUM_BYTES_OF_DATA_PER_ROOM

      for table_num in range(0, NUM_BYTES_OF_DATA_PER_ROOM):
        patch.AddData(start_address + table_num * LEVEL_TABLE_SIZE + room_num,
                      [room_data[table_num]])
    # Write Triforce room location to update where the compass displays it in levels 1-8.
    # The room the compass points to in level 9 doesn't change.
    for level_num in range(1, 9):
      assert level_num in self.triforce_locations
      patch.AddData(
          COMPASS_ROOM_NUMBER_ADDRESS + (level_num - 1) * SPECIAL_DATA_LEVEL_OFFSET,
          [self.triforce_locations[level_num]])
    return patch

  def _GetPatchForOverworldCaveData(self) -> Patch:
    patch = Patch()
    for cave_num in Range.VALID_CAVE_NUMBERS:
      if cave_num == CAVE_NUMBER_REPRESENTING_ARMOS_ITEM:
        patch.AddData(ARMOS_ITEM_ADDRESS,
                      [self.overworld_caves[cave_num].GetItemAtPosition(2)])
        continue
      if cave_num == CAVE_NUMBER_REPRESENTING_COAST_ITEM:
        patch.AddData(COAST_ITEM_ADDRESS,
                      [self.overworld_caves[cave_num].GetItemAtPosition(2)])
        continue

      # Note that the Cave class is responsible for protecting bits 6 and 7 in its item data
      patch.AddData(CAVE_ITEM_DATA_START_ADDRESS + (3 * cave_num),
                    self.overworld_caves[cave_num].GetItemData())
      patch.AddData(CAVE_PRICE_DATA_START_ADDRESS + (3 * cave_num),
                    self.overworld_caves[cave_num].GetPriceData())
    return patch

  def _GetPatchForOverworldScreenDestinations(self) -> Patch:
    """Generate patch data for overworld screen destinations (table 1)."""
    patch = Patch()
    # Overworld table 1 starts at OVERWORLD_DATA_LOCATION + 0x80 (table offset)
    # Each table is 0x80 bytes (128 screens), and table 1 is the second table
    OVERWORLD_TABLE_1_ADDRESS = 0x18400 + NES_FILE_OFFSET + 0x80  # 0x18490

    # Write all 128 bytes of table 1 (screen destinations)
    for screen_num in range(0x80):
      patch.AddData(OVERWORLD_TABLE_1_ADDRESS + screen_num,
                   [self.overworld_raw_data[screen_num + 1*0x80]])
    return patch

  def _GetPatchForRomData(self) -> Patch:
    """Generate patch data for all modified ROM data.

    This generates patches for any ROM data that has been modified via SetRomData().
    Only data that differs from its initial state (or is write-only with a value set)
    will be included in the patch.
    """
    from .rom_data_specs import ROM_DATA_SPECS, RomDataType

    patch = Patch()

    for data_type, spec in ROM_DATA_SPECS.items():
      state_key = f"_{data_type.name.lower()}"
      if not hasattr(self, state_key):
        continue

      value = getattr(self, state_key)

      # Skip if value is None (not set for write-only data)
      if value is None:
        continue

      # Skip readable data if it hasn't been modified
      # (For readable data, we initialized it from ROM, so check if it changed)
      if spec.readable:
        # Re-read original value from ROM
        raw_data = list(self.rom_reader._ReadMemory(spec.cpu_address, spec.size))
        if spec.decoder:
          original_value = spec.decoder(raw_data)
        else:
          original_value = raw_data

        # Skip if unchanged
        if value == original_value:
          continue

      # Encode the value for ROM
      if spec.encoder:
        encoded_data = spec.encoder(value)
      elif isinstance(value, list):
        encoded_data = value
      else:
        encoded_data = [value]

      # Add to patch using file_offset
      patch.AddData(spec.file_offset, encoded_data)

    return patch

  def GetMixedEnemyGroup(self, enemy: Enemy) -> List[Enemy]:
    """Get the list of Enemy enums for a mixed enemy group.

    Args:
        enemy: The Enemy enum representing a mixed enemy group

    Returns:
        List of Enemy enums in the group, or empty list if not a mixed group
    """
    return self.mixed_enemy_groups.get(int(enemy), [])

  # Generic ROM data access methods

  def GetRomData(self, data_type: 'RomDataType') -> Any:
    """Generic getter for ROM data using RomDataType enum.

    Args:
        data_type: The type of ROM data to retrieve

    Returns:
        The data value (type depends on the specific data type)

    Raises:
        ValueError: If data_type is write-only
    """
    from .rom_data_specs import ROM_DATA_SPECS

    spec = ROM_DATA_SPECS[data_type]
    if not spec.readable:
      raise ValueError(f"{data_type.name} is write-only")

    # Check if we have modified state stored
    state_key = f"_{data_type.name.lower()}"
    if hasattr(self, state_key):
      value = getattr(self, state_key)
      if value is not None:
        return value

    # Otherwise read from ROM
    raw_data = list(self.rom_reader._ReadMemory(spec.cpu_address, spec.size))
    if spec.decoder:
      return spec.decoder(raw_data)
    return raw_data

  def SetRomData(self, data_type: 'RomDataType', data: Any) -> None:
    """Generic setter for ROM data using RomDataType enum.

    Args:
        data_type: The type of ROM data to set
        data: The data value to set

    Raises:
        ValueError: If data_type is read-only
    """
    from .rom_data_specs import ROM_DATA_SPECS

    spec = ROM_DATA_SPECS[data_type]
    if not spec.writable:
      raise ValueError(f"{data_type.name} is read-only")

    # Store in instance variable
    state_key = f"_{data_type.name.lower()}"
    setattr(self, state_key, data)

  # New query methods for validator - Phase 1 refactoring

  def GetRoomEnemy(self, level_num: LevelNum, room_num: RoomNum) -> Enemy:
    """Get the enemy type in a specific room."""
    room = self.GetRoom(level_num, room_num)
    return room.GetEnemy()

  def GetRoomItemByCoords(self, level_num: LevelNum, room_num: RoomNum) -> Item:
    """Get the item in a specific room, or None if no item."""
    room = self.GetRoom(level_num, room_num)
    return room.GetItem()

  def GetRoomType(self, level_num: LevelNum, room_num: RoomNum) -> RoomType:
    """Get the room type (layout) for a specific room."""
    room = self.GetRoom(level_num, room_num)
    return room.GetType()

  def GetRoomWallType(self, level_num: LevelNum, room_num: RoomNum, direction: Direction) -> WallType:
    """Get the wall type in a specific direction for a room."""
    room = self.GetRoom(level_num, room_num)
    return room.GetWallType(direction)

  def HasRoomItem(self, level_num: LevelNum, room_num: RoomNum) -> bool:
    """Check if a room has an item."""
    room = self.GetRoom(level_num, room_num)
    return room.HasItem()

  def HasDropBit(self, level_num: LevelNum, room_num: RoomNum) -> bool:
    """Check if a room has the drop bit set (enemy defeat required for item)."""
    room = self.GetRoom(level_num, room_num)
    return room.HasDropBitSet()

  def HasMovableBlockBit(self, level_num: LevelNum, room_num: RoomNum) -> bool:
    """Check if a room has the movable block bit set."""
    room = self.GetRoom(level_num, room_num)
    return room.HasMovableBlockBitSet()

  def GetStaircaseLeftExit(self, level_num: LevelNum, staircase_room_num: RoomNum) -> RoomNum:
    """Get the left exit room number for a staircase room."""
    room = self.GetRoom(level_num, staircase_room_num)
    return room.GetLeftExit()

  def GetStaircaseRightExit(self, level_num: LevelNum, staircase_room_num: RoomNum) -> RoomNum:
    """Get the right exit room number for a staircase room."""
    room = self.GetRoom(level_num, staircase_room_num)
    return room.GetRightExit()

  def IsItemStaircase(self, level_num: LevelNum, staircase_room_num: RoomNum) -> bool:
    """Check if a staircase is an item staircase (left == right exits)."""
    room = self.GetRoom(level_num, staircase_room_num)
    left = room.GetLeftExit()
    right = room.GetRightExit()
    return left == right

  def GetStaircaseItem(self, level_num: LevelNum, staircase_room_num: RoomNum) -> Item | None:
    """Get the item in a staircase room, or None if not an item staircase."""
    if not self.IsItemStaircase(level_num, staircase_room_num):
      return None
    room = self.GetRoom(level_num, staircase_room_num)
    return room.GetItem()
