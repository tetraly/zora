"""ROM interface - the main public API for ROM data access.

This module provides RomInterface, the primary interface for reading and
modifying ROM game data. External code should use this class instead
of accessing Room, Cave, or other internal classes directly.
"""

import logging as log
from typing import Dict, List, Optional

from logic.randomizer_constants import (
    CaveType, Direction, Enemy, Item, ItemPosition, LevelNum, Range, RoomAction, RoomNum, RoomType, WallType
)
from logic.constants import ENTRANCE_DIRECTION_MAP
from logic.location import Location
from logic.patch import Patch

from .rom_data import RomData, load_from_file, load_from_bytes, load_from_test_data
from .rom_config import (
    NES_HEADER_SIZE,
    RomLayout,
    LEVEL_TABLE_SIZE,
    NUM_BYTES_OF_DATA_PER_ROOM,
    LEVEL_INFO_BLOCK_SIZE,
    LEVEL_INFO_PPU_PALETTE_SIZE,
    LEVEL_INFO_ITEM_POSITIONS_OFFSET,
    LEVEL_INFO_START_ROOM_OFFSET,
    LEVEL_INFO_STAIRWAY_LIST_OFFSET,
    LEVEL_INFO_COMPASS_OFFSET,
    CAVE_NUMBER_ARMOS_ITEM,
    CAVE_NUMBER_COAST_ITEM,
)
from .room import Room
from .cave import Cave


class RomInterface:
    """High-level API for querying and modifying ROM game data.

    This class provides game-oriented methods for working with dungeon rooms,
    caves, items, enemies, etc. Implementation details like Room and Cave
    classes are internal and not exposed in the public API.

    Usage:
        # From a ROM file
        state = RomInterface.from_rom_file("game.nes")

        # From test data
        state = RomInterface.from_test_data()

        # From raw bytes
        rom_data = load_from_bytes(rom_bytes)
        state = RomInterface(rom_data)

        # Query and modify
        item = state.get_room_item(level_num=3, room_num=0x0F)
        state.set_cave_item(CaveType.SHOP_A, position=1, item=Item.BLUE_CANDLE)

        # Generate patch
        patch = state.get_patch()
    """

    def __init__(self, rom_data: RomData) -> None:
        """Initialize RomInterface from a RomData container.

        Args:
            rom_data: The ROM data to operate on
        """
        self._rom_data = rom_data

        # Copy data for modification
        self._level_1_to_6_raw_data = rom_data.level_1_to_6_block[:]
        self._level_7_to_9_raw_data = rom_data.level_7_to_9_block[:]
        self._overworld_raw_data = rom_data.overworld_block[:]
        self._overworld_cave_raw_data = rom_data.overworld_block[0x80*4:0x80*5]

        # Level info (already has PPU palette stripped)
        self._level_info: List[List[int]] = [info[:] for info in rom_data.level_info]
        self._level_info_raw: List[List[int]] = [info[:] for info in rom_data.level_info_raw]

        # Internal state
        self._level_1_to_6_rooms: List[Room] = []
        self._level_7_to_9_rooms: List[Room] = []
        self._overworld_caves: List[Cave] = []
        self._triforce_locations: Dict[LevelNum, RoomNum] = {}

        # Copy mixed enemy groups
        self._mixed_enemy_groups = dict(rom_data.mixed_enemy_groups)

        # Recorder warp data (8 entries for levels 1-8)
        self._recorder_warp_destinations = rom_data.recorder_warp_destinations[:]
        self._recorder_warp_y_coordinates = rom_data.recorder_warp_y_coordinates[:]

        # Any road screens (4 entries)
        self._any_road_screens = rom_data.any_road_screens[:]

        # Heart container requirements (raw ROM bytes)
        self._white_sword_hearts_raw = rom_data.white_sword_hearts_raw
        self._magical_sword_hearts_raw = rom_data.magical_sword_hearts_raw

        # Detection flags
        self._is_z1r = rom_data.is_z1r

    # =========================================================================
    # Factory Methods
    # =========================================================================

    @classmethod
    def from_rom_file(cls, rom_path: str) -> 'RomInterface':
        """Create RomInterface from a ROM file.

        Args:
            rom_path: Path to the .nes ROM file

        Returns:
            RomInterface instance
        """
        return cls(load_from_file(rom_path))

    @classmethod
    def from_rom_bytes(cls, rom_bytes: bytes) -> 'RomInterface':
        """Create RomInterface from raw ROM bytes.

        Args:
            rom_bytes: Complete ROM file contents (including NES header)

        Returns:
            RomInterface instance
        """
        return cls(load_from_bytes(rom_bytes))

    @classmethod
    def from_test_data(cls, data_dir: Optional[str] = None) -> 'RomInterface':
        """Create RomInterface from test data files.

        Args:
            data_dir: Path to test data directory (defaults to tests/data/)

        Returns:
            RomInterface instance
        """
        return cls(load_from_test_data(data_dir))

    # =========================================================================
    # Initialization
    # =========================================================================

    def reset_to_vanilla(self) -> None:
        """Reset all modified data back to the original ROM state."""
        self._level_1_to_6_rooms = self._read_data_for_level_grid(self._level_1_to_6_raw_data)
        self._level_7_to_9_rooms = self._read_data_for_level_grid(self._level_7_to_9_raw_data)
        self._read_data_for_overworld_caves()
        self._level_info = [info[:] for info in self._level_info_raw]
        self._triforce_locations = {}

    # =========================================================================
    # Overworld Screen Methods
    # =========================================================================

    def get_screen_destination(self, screen_num: int) -> CaveType:
        """Get the cave/level destination for an overworld screen.

        Args:
            screen_num: The overworld screen number (0-127)

        Returns:
            CaveType enum for the destination, or CaveType.NONE if no destination
        """
        # Skip any screens that aren't "Secret in 1st Quest"
        if (self._overworld_raw_data[screen_num + 5*0x80] & 0x80) > 0:
            return CaveType.NONE
        # Cave destination is upper 6 bits of table 1
        destination = self._overworld_raw_data[screen_num + 1*0x80] >> 2
        if destination == 0:
            return CaveType.NONE
        return CaveType(destination)

    def set_screen_destination(self, screen_num: int, cave_type: CaveType) -> None:
        """Set the cave/level destination for an overworld screen.

        Args:
            screen_num: The overworld screen number (0-127)
            cave_type: The CaveType enum value to set as the destination
        """
        # Preserve the lower 2 bits of table 1 (which contain other data)
        lower_bits = self._overworld_raw_data[screen_num + 1*0x80] & 0x03
        # Set the upper 6 bits to the cave type value (shift left by 2)
        self._overworld_raw_data[screen_num + 1*0x80] = (int(cave_type) << 2) | lower_bits

    def get_start_screen(self) -> int:
        """Get the overworld start screen from level info.

        Returns:
            The overworld screen number (0x00-0x7F) where Link starts
        """
        return self._level_info[0][LEVEL_INFO_START_ROOM_OFFSET]

    def set_start_screen(self, screen_num: int) -> None:
        """Set the overworld start screen in level info.

        Args:
            screen_num: The overworld screen number to set as start (0x00-0x7F)
        """
        assert 0 <= screen_num < 0x80, f"Invalid screen number: {hex(screen_num)}"
        self._level_info[0][LEVEL_INFO_START_ROOM_OFFSET] = screen_num

    def get_overworld_enemy_data(self, screen_num: int) -> int:
        """Get the enemy data byte for an overworld screen.

        The enemy data byte contains:
        - Bits 0-5: Enemy type
        - Bits 6-7: Enemy quantity code (0-3)

        Args:
            screen_num: The overworld screen number (0x00-0x7F)

        Returns:
            The enemy data byte from Table 2
        """
        assert 0 <= screen_num < 0x80, f"Invalid screen number: {hex(screen_num)}"
        return self._overworld_raw_data[screen_num + 2 * 0x80]

    def set_overworld_enemy_data(self, screen_num: int, enemy_data: int) -> None:
        """Set the enemy data byte for an overworld screen.

        Args:
            screen_num: The overworld screen number (0x00-0x7F)
            enemy_data: The enemy data byte to set (contains type and quantity code)
        """
        assert 0 <= screen_num < 0x80, f"Invalid screen number: {hex(screen_num)}"
        assert 0 <= enemy_data <= 0xFF, f"Invalid enemy data: {hex(enemy_data)}"
        self._overworld_raw_data[screen_num + 2 * 0x80] = enemy_data

    # =========================================================================
    # Room Methods (Public API)
    # =========================================================================

    def get_room_item(self, level_num: int, room_num: int) -> Item:
        """Get the item in a specific dungeon room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)

        Returns:
            The Item enum in the room
        """
        return self._get_room(level_num, room_num).GetItem()

    def set_room_item(self, level_num: int, room_num: int, item: Item) -> None:
        """Set the item in a specific dungeon room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)
            item: The Item enum to place
        """
        self._get_room(level_num, room_num).SetItem(item)

    def get_room_type(self, level_num: int, room_num: int) -> RoomType:
        """Get the room type (layout) for a specific room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)

        Returns:
            The RoomType enum
        """
        return self._get_room(level_num, room_num).GetType()

    def set_room_type(self, level_num: int, room_num: int, room_type: RoomType) -> None:
        """Set the room type (layout) for a specific room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)
            room_type: The RoomType enum value to set
        """
        self._get_room(level_num, room_num).SetType(room_type)

    def get_wall_type(self, level_num: int, room_num: int, direction: Direction) -> WallType:
        """Get the wall type in a specific direction for a room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)
            direction: The Direction (NORTH, SOUTH, EAST, WEST)

        Returns:
            The WallType enum
        """
        return self._get_room(level_num, room_num).GetWallType(direction)

    def set_wall_type(self, level_num: int, room_num: int, direction: Direction, wall_type: WallType) -> None:
        """Set the wall type for a specific direction in a room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)
            direction: The Direction (NORTH, SOUTH, EAST, WEST)
            wall_type: The WallType enum value to set
        """
        self._get_room(level_num, room_num).SetWallType(direction, wall_type)

    def get_room_enemy(self, level_num: int, room_num: int) -> Enemy:
        """Get the enemy type in a specific room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)

        Returns:
            The Enemy enum, or Enemy.NO_ENEMY for staircase rooms
        """
        if self.get_room_type(level_num, room_num).IsStaircaseRoom():
            return Enemy.NO_ENEMY
        return self._get_room(level_num, room_num).GetEnemy()

    def set_room_enemy(self, level_num: int, room_num: int, enemy: Enemy) -> None:
        """Set the enemy type for a specific room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)
            enemy: The Enemy enum value to set
        """
        self._get_room(level_num, room_num).SetEnemy(enemy)

    def set_room_enemy_quantity(self, level_num: int, room_num: int, quantity: int) -> None:
        """Set the enemy quantity code for a specific room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)
            quantity: The quantity code (0-3)
        """
        self._get_room(level_num, room_num).SetEnemyQuantity(quantity)

    def get_item_position(self, level_num: int, room_num: int) -> ItemPosition:
        """Get the item position code for a room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)

        Returns:
            The ItemPosition enum
        """
        return self._get_room(level_num, room_num).GetItemPosition()

    def set_item_position(self, level_num: int, room_num: int, position_num: int) -> None:
        """Set the item position code for a room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)
            position_num: The position code (0-3)
        """
        self._get_room(level_num, room_num).SetItemPosition(position_num)

    def is_item_staircase(self, level_num: int, room_num: int) -> bool:
        """Check if a room is an item staircase room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)

        Returns:
            True if the room is an item staircase
        """
        return self._get_room(level_num, room_num).IsItemStaircase()

    def has_movable_block_bit(self, level_num: int, room_num: int) -> bool:
        """Check if a room has the movable block bit set.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)

        Returns:
            True if the movable block bit is set
        """
        return self._get_room(level_num, room_num).HasMovableBlockBitSet()

    def get_staircase_left_exit(self, level_num: int, staircase_room_num: int) -> int:
        """Get the left exit room number for a staircase room.

        Args:
            level_num: The level number (1-9)
            staircase_room_num: The staircase room number

        Returns:
            The room number for the left exit
        """
        return self._get_room(level_num, staircase_room_num).GetLeftExit()

    def get_staircase_right_exit(self, level_num: int, staircase_room_num: int) -> int:
        """Get the right exit room number for a staircase room.

        Args:
            level_num: The level number (1-9)
            staircase_room_num: The staircase room number

        Returns:
            The room number for the right exit
        """
        return self._get_room(level_num, staircase_room_num).GetRightExit()

    def get_room_action(self, level_num: int, room_num: int) -> RoomAction:
        """Get the room action (secret trigger) code for a room.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)

        Returns:
            The RoomAction enum value
        """
        return self._get_room(level_num, room_num).GetRoomAction()

    def has_drop_bit(self, level_num: int, room_num: int) -> bool:
        """Check if a room has the drop bit set (item drops from enemies).

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)

        Returns:
            True if the drop bit is set
        """
        return self._get_room(level_num, room_num).HasDropBitSet()

    def is_room_visited(self, level_num: int, room_num: int) -> bool:
        """Check if a room has been marked as visited.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)

        Returns:
            True if the room has been visited
        """
        return self._get_room(level_num, room_num).IsMarkedAsVisited()

    def mark_room_visited(self, level_num: int, room_num: int) -> None:
        """Mark a room as visited.

        Args:
            level_num: The level number (1-9)
            room_num: The room number within the level (0x00-0x7F)
        """
        self._get_room(level_num, room_num).MarkAsVisited()

    # =========================================================================
    # Cave Methods (Public API - uses CaveType)
    # =========================================================================

    def get_cave_item(self, cave_type: CaveType, position: int) -> Item:
        """Get an item from a cave at a specific position.

        Args:
            cave_type: The CaveType enum
            position: Position within the cave (1-indexed: 1-3)

        Returns:
            The Item enum at the specified position
        """
        cave_index = int(cave_type) - 0x10
        return self._overworld_caves[cave_index].GetItemAtPosition(position)

    def set_cave_item(self, cave_type: CaveType, position: int, item: Item) -> None:
        """Set an item in a cave at a specific position.

        Args:
            cave_type: The CaveType enum
            position: Position within the cave (1-indexed: 1-3)
            item: The Item enum to place
        """
        cave_index = int(cave_type) - 0x10
        self._overworld_caves[cave_index].SetItemAtPosition(item, position)

    def set_cave_price(self, cave_type: CaveType, position: int, price: int) -> None:
        """Set the price for an item in a cave at a specific position.

        Args:
            cave_type: The CaveType enum
            position: Position within the cave (1-indexed: 1-3)
            price: The price in rupees
        """
        cave_index = int(cave_type) - 0x10
        self._overworld_caves[cave_index].SetPriceAtPosition(price, position)

    # =========================================================================
    # Level Metadata Methods
    # =========================================================================

    def get_level_start_room(self, level_num: int) -> int:
        """Get the starting room number for a level.

        Args:
            level_num: The level number (1-9)

        Returns:
            The room number where the level starts
        """
        log.debug("Level %d start room is %x" %
                  (level_num, self._level_info[level_num][LEVEL_INFO_START_ROOM_OFFSET]))
        return self._level_info[level_num][LEVEL_INFO_START_ROOM_OFFSET]

    def set_level_start_room(self, level_num: int, room_num: int) -> None:
        """Set the starting room for a level.

        Args:
            level_num: The level number (1-9)
            room_num: The room number to set as the start room (0x00-0x7F)
        """
        self._level_info[level_num][LEVEL_INFO_START_ROOM_OFFSET] = room_num

    def get_level_entrance_direction(self, level_num: int) -> Direction:
        """Get the entrance direction for a level.

        Args:
            level_num: The level number (1-9)

        Returns:
            The Direction enum for the entrance
        """
        if not self._is_z1r:
            return Direction.SOUTH
        return Direction(ENTRANCE_DIRECTION_MAP[self._get_raw_level_stairway_room_number_list(level_num)[-1]])

    def get_level_staircase_room_list(self, level_num: int) -> List[int]:
        """Get the list of staircase room numbers for a level.

        Args:
            level_num: The level number (1-9)

        Returns:
            List of room numbers that are staircases
        """
        stairway_list = self._get_raw_level_stairway_room_number_list(level_num)
        # In randomized roms, the last item in the stairway list is the entrance dir.
        if self._is_z1r:
            stairway_list.pop(-1)
        return stairway_list

    def set_level_item_position_coordinates(self, level_num: int, item_position_coordinates: List[int]) -> None:
        """Set the item position coordinates for a level.

        Args:
            level_num: The level number (1-9)
            item_position_coordinates: List of 4 coordinate values
        """
        assert len(item_position_coordinates) == 4
        for i in range(4):
            self._level_info[level_num][LEVEL_INFO_ITEM_POSITIONS_OFFSET + i] = item_position_coordinates[i]

    def update_triforce_location(self, location: Location) -> None:
        """Update the compass pointer for a triforce location.

        Args:
            location: The Location where the triforce is placed
        """
        room_num = location.GetRoomNum()
        room = self._get_room(location.GetLevelNum(), room_num)
        if room.IsItemStaircase():
            # The triforce is in an item staircase room. The compass should point to the room
            # that contains the stairs leading down to this staircase room.
            room_num = room.GetLeftExit()
        self._triforce_locations[location.GetLevelNum()] = room_num

        # Also update level_info with the new compass pointer
        level_num = location.GetLevelNum()
        if level_num in range(1, 9):  # Only levels 1-8 have updatable compass pointers
            self._level_info[level_num][LEVEL_INFO_COMPASS_OFFSET] = room_num

    # =========================================================================
    # Recorder Warp Methods (Bulk API)
    # =========================================================================

    def get_recorder_warp_destinations(self) -> List[int]:
        """Get all recorder warp destination screens for levels 1-8.

        Returns:
            List of 8 screen numbers, one per level (1-8)
        """
        return self._recorder_warp_destinations[:]

    def set_recorder_warp_destinations(self, destinations: List[int]) -> None:
        """Set all recorder warp destination screens for levels 1-8.

        Args:
            destinations: List of exactly 8 screen numbers, one per level (1-8)
        """
        assert len(destinations) == 8, f"Expected 8 destinations, got {len(destinations)}"
        self._recorder_warp_destinations = destinations[:]

    def get_recorder_warp_y_coordinates(self) -> List[int]:
        """Get all recorder warp Y coordinates for levels 1-8.

        Returns:
            List of 8 Y coordinate values, one per level (1-8)
        """
        return self._recorder_warp_y_coordinates[:]

    def set_recorder_warp_y_coordinates(self, y_coords: List[int]) -> None:
        """Set all recorder warp Y coordinates for levels 1-8.

        Args:
            y_coords: List of exactly 8 Y coordinate values, one per level (1-8)
        """
        assert len(y_coords) == 8, f"Expected 8 Y coordinates, got {len(y_coords)}"
        self._recorder_warp_y_coordinates = y_coords[:]

    # =========================================================================
    # Any Road & Quest Methods
    # =========================================================================

    def get_any_road_screens(self) -> List[int]:
        """Get the four Any Road destination screens.

        Returns:
            List of 4 screen numbers for Any Road destinations
        """
        return self._any_road_screens[:]

    def is_screen_first_quest(self, screen_num: int) -> bool:
        """Check if an overworld screen is a first quest secret.

        First quest screens have bit 7 (0x80) clear in table 5 data.
        Second quest screens have bit 7 set.

        Args:
            screen_num: The overworld screen number (0x00-0x7F)

        Returns:
            True if the screen is a first quest secret, False if second quest
        """
        assert 0 <= screen_num < 0x80, f"Invalid screen number: {hex(screen_num)}"
        return (self._overworld_raw_data[screen_num + 5 * 0x80] & 0x80) == 0

    # =========================================================================
    # Heart Container Requirements
    # =========================================================================

    def get_heart_container_requirement(self, for_magical_sword: bool = False) -> int:
        """Get the heart container requirement for a sword cave.

        Args:
            for_magical_sword: If True, returns magical sword requirement;
                              if False, returns white sword requirement.

        Returns:
            The number of hearts required (e.g., 4-6 for WS, 10-12 for MS)
        """
        raw = self._magical_sword_hearts_raw if for_magical_sword else self._white_sword_hearts_raw
        return (raw // 16) + 1

    def set_heart_container_requirement(self, requirement: int, for_magical_sword: bool = False) -> None:
        """Set the heart container requirement for a sword cave.

        Args:
            requirement: The number of hearts required (e.g., 4-6 for WS, 10-12 for MS)
            for_magical_sword: If True, sets magical sword requirement;
                              if False, sets white sword requirement.
        """
        raw_value = (requirement - 1) * 16
        if for_magical_sword:
            self._magical_sword_hearts_raw = raw_value
        else:
            self._white_sword_hearts_raw = raw_value

    # =========================================================================
    # Mixed Enemy Groups
    # =========================================================================

    def get_mixed_enemy_group(self, enemy: Enemy) -> List[Enemy]:
        """Get the list of Enemy enums for a mixed enemy group.

        Args:
            enemy: The Enemy enum representing a mixed enemy group

        Returns:
            List of Enemy enums in the group, or empty list if not a mixed group
        """
        return self._mixed_enemy_groups.get(int(enemy), [])

    # =========================================================================
    # Visit Markers (for pathfinding algorithms)
    # =========================================================================

    def clear_all_visit_markers(self) -> None:
        """Clear all room visit markers (used by pathfinding algorithms)."""
        log.debug("Clearing Visit markers")
        for room in self._level_1_to_6_rooms:
            room.ClearVisitMark()
        for room in self._level_7_to_9_rooms:
            room.ClearVisitMark()

    # =========================================================================
    # Patch Generation
    # =========================================================================

    def get_patch(self) -> Patch:
        """Generate a Patch containing all modified ROM data.

        Returns:
            Patch object that can be applied to a ROM
        """
        patch = Patch()
        patch += self._get_patch_for_level_grid(
            RomLayout.LEVEL_1_TO_6_FIRST_QUEST_DATA.file_offset,
            self._level_1_to_6_rooms
        )
        patch += self._get_patch_for_level_grid(
            RomLayout.LEVEL_7_TO_9_FIRST_QUEST_DATA.file_offset,
            self._level_7_to_9_rooms
        )
        patch += self._get_patch_for_overworld()
        patch += self._get_patch_for_level_info()
        patch += self._get_patch_for_recorder_warps()
        patch += self._get_patch_for_heart_requirements()
        return patch

    # =========================================================================
    # Legacy Compatibility Methods
    # These maintain compatibility with existing code that uses Location objects
    # =========================================================================

    def GetRoom(self, level_num: LevelNum, room_num: RoomNum) -> Room:
        """Legacy method: Get a Room object directly.

        DEPRECATED: Use specific getter methods instead.
        """
        return self._get_room(level_num, room_num)

    def GetRoomItem(self, location: Location) -> Item:
        """Legacy method for Location-based item retrieval."""
        assert location.IsLevelRoom()
        return self.get_room_item(location.GetLevelNum(), location.GetRoomNum())

    def SetRoomItem(self, location: Location, item: Item) -> None:
        """Legacy method for Location-based item setting."""
        assert location.IsLevelRoom()
        self.set_room_item(location.GetLevelNum(), location.GetRoomNum(), item)

    def GetCaveItem(self, location: Location) -> Item:
        """Legacy method for Location-based cave item retrieval."""
        assert location.IsCavePosition()
        cave_type = CaveType(location.GetCaveNum())
        return self.get_cave_item(cave_type, location.GetPositionNum())

    def SetCaveItem(self, location: Location, item: Item) -> None:
        """Legacy method for Location-based cave item setting."""
        assert location.IsCavePosition()
        cave_type = CaveType(location.GetCaveNum())
        self.set_cave_item(cave_type, location.GetPositionNum(), item)

    def SetItemPosition(self, location: Location, position_num: int) -> None:
        """Legacy method for Location-based item position setting."""
        assert location.IsLevelRoom()
        self.set_item_position(location.GetLevelNum(), location.GetRoomNum(), position_num)

    def UpdateTriforceLocation(self, location: Location) -> None:
        """Legacy method alias."""
        self.update_triforce_location(location)

    # Legacy property aliases
    @property
    def level_1_to_6_rooms(self) -> List[Room]:
        return self._level_1_to_6_rooms

    @property
    def level_7_to_9_rooms(self) -> List[Room]:
        return self._level_7_to_9_rooms

    @property
    def overworld_caves(self) -> List[Cave]:
        return self._overworld_caves

    @property
    def overworld_raw_data(self) -> List[int]:
        return self._overworld_raw_data

    @property
    def level_info(self) -> List[List[int]]:
        return self._level_info

    @property
    def triforce_locations(self) -> Dict[LevelNum, RoomNum]:
        return self._triforce_locations

    @property
    def mixed_enemy_groups(self) -> Dict[int, List[Enemy]]:
        return self._mixed_enemy_groups

    @property
    def is_z1r(self) -> bool:
        return self._is_z1r

    # More legacy method aliases
    def ResetToVanilla(self) -> None:
        self.reset_to_vanilla()

    def GetScreenDestination(self, screen_num: int) -> CaveType:
        return self.get_screen_destination(screen_num)

    def SetScreenDestination(self, screen_num: int, cave_type: CaveType) -> None:
        self.set_screen_destination(screen_num, cave_type)

    def GetLevelStartRoomNumber(self, level_num: int) -> RoomNum:
        return RoomNum(self.get_level_start_room(level_num))

    def GetLevelEntranceDirection(self, level_num: int) -> Direction:
        return self.get_level_entrance_direction(level_num)

    def GetLevelStaircaseRoomNumberList(self, level_num: int) -> List[RoomNum]:
        return [RoomNum(r) for r in self.get_level_staircase_room_list(level_num)]

    def ClearAllVisitMarkers(self) -> None:
        self.clear_all_visit_markers()

    def GetPatch(self) -> Patch:
        return self.get_patch()

    def GetMixedEnemyGroup(self, enemy: Enemy) -> List[Enemy]:
        return self.get_mixed_enemy_group(enemy)

    def GetItem(self, level_num: LevelNum, room_num: RoomNum) -> Item:
        return self.get_room_item(level_num, room_num)

    def SetItem(self, level_num: LevelNum, room_num: RoomNum, item: Item) -> None:
        self.set_room_item(level_num, room_num, item)

    def GetRoomWallType(self, level_num: LevelNum, room_num: RoomNum, direction: Direction) -> WallType:
        return self.get_wall_type(level_num, room_num, direction)

    def GetRoomType(self, level_num: LevelNum, room_num: RoomNum) -> RoomType:
        return self.get_room_type(level_num, room_num)

    def SetRoomType(self, level_num: LevelNum, room_num: RoomNum, room_type: RoomType) -> None:
        self.set_room_type(level_num, room_num, room_type)

    def SetWall(self, level_num: LevelNum, room_num: RoomNum, direction: Direction, wall_type: WallType) -> None:
        self.set_wall_type(level_num, room_num, direction, wall_type)

    def SetEnemy(self, level_num: LevelNum, room_num: RoomNum, enemy: Enemy) -> None:
        self.set_room_enemy(level_num, room_num, enemy)

    def SetEnemyQuantity(self, level_num: LevelNum, room_num: RoomNum, quantity: int) -> None:
        self.set_room_enemy_quantity(level_num, room_num, quantity)

    def SetLevelStartRoom(self, level_num: int, room_num: int) -> None:
        self.set_level_start_room(level_num, room_num)

    def HasMovableBlockBit(self, level_num: LevelNum, room_num: RoomNum) -> bool:
        return self.has_movable_block_bit(level_num, room_num)

    def GetStaircaseLeftExit(self, level_num: LevelNum, staircase_room_num: RoomNum) -> RoomNum:
        return RoomNum(self.get_staircase_left_exit(level_num, staircase_room_num))

    def GetStaircaseRightExit(self, level_num: LevelNum, staircase_room_num: RoomNum) -> RoomNum:
        return RoomNum(self.get_staircase_right_exit(level_num, staircase_room_num))

    def GetRoomEnemy(self, level_num: LevelNum, room_num: RoomNum) -> Enemy:
        return self.get_room_enemy(level_num, room_num)

    def IsItemStaircase(self, level_num: LevelNum, room_num: RoomNum) -> bool:
        return self.is_item_staircase(level_num, room_num)

    def SetLevelItemPositionCoordinates(self, level_num: int, item_position_coordinates: List[int]) -> None:
        self.set_level_item_position_coordinates(level_num, item_position_coordinates)

    def GetItemPosition(self, level_num: int, room_num: int) -> ItemPosition:
        return self.get_item_position(level_num, room_num)

    def SetItemPositionNew(self, level_num: int, room_num: int, position_num: int) -> None:
        self.set_item_position(level_num, room_num, position_num)

    def GetCaveItemNew(self, cave_type: int, position_num: int) -> Item:
        return self.get_cave_item(CaveType(cave_type), position_num)

    def SetCaveItemNew(self, cave_type: int, position_num: int, item: Item) -> None:
        self.set_cave_item(CaveType(cave_type), position_num, item)

    def SetCavePrice(self, cave_type: int, position_num: int, price: int) -> None:
        self.set_cave_price(CaveType(cave_type), position_num, price)

    def GetStartScreen(self) -> int:
        return self.get_start_screen()

    def SetStartScreen(self, screen_num: int) -> None:
        self.set_start_screen(screen_num)

    def GetOverworldEnemyData(self, screen_num: int) -> int:
        return self.get_overworld_enemy_data(screen_num)

    def SetOverworldEnemyData(self, screen_num: int, enemy_data: int) -> None:
        self.set_overworld_enemy_data(screen_num, enemy_data)

    # =========================================================================
    # Private Implementation
    # =========================================================================

    def _get_room(self, level_num: int, room_num: int) -> Room:
        """Internal: Get the Room object for a level/room combination."""
        assert level_num in Range.VALID_LEVEL_NUMBERS
        assert room_num in Range.VALID_ROOM_NUMBERS

        if level_num in [7, 8, 9]:
            return self._level_7_to_9_rooms[room_num]
        return self._level_1_to_6_rooms[room_num]

    def _read_data_for_level_grid(self, level_data: List[int]) -> List[Room]:
        """Internal: Parse level data into Room objects."""
        rooms: List[Room] = []
        for room_num in Range.VALID_ROOM_NUMBERS:
            room_data: List[int] = []
            for byte_num in range(NUM_BYTES_OF_DATA_PER_ROOM):
                room_data.append(level_data[byte_num * LEVEL_TABLE_SIZE + room_num])
            rooms.append(Room(room_data))
        return rooms

    def _read_data_for_overworld_caves(self) -> None:
        """Internal: Parse overworld cave data into Cave objects."""
        self._overworld_caves = []
        for cave_num in Range.VALID_CAVE_NUMBERS:
            if cave_num == CAVE_NUMBER_ARMOS_ITEM:
                self._overworld_caves.append(Cave([0x3F, self._rom_data.armos_item, 0x7F, 0x00, 0x00, 0x00]))
            elif cave_num == CAVE_NUMBER_COAST_ITEM:
                self._overworld_caves.append(Cave([0x3F, self._rom_data.coast_item, 0x7F, 0x00, 0x00, 0x00]))
            else:
                assert cave_num in range(0, 0x14)
                cave_data: List[int] = []
                for cave_item_byte_num in range(3):
                    cave_data.append(self._overworld_cave_raw_data[(3 * cave_num) + cave_item_byte_num])
                for cave_price_byte_num in range(3):
                    cave_data.append(
                        self._overworld_cave_raw_data[0x3C + (3 * cave_num) + cave_price_byte_num])
                self._overworld_caves.append(Cave(cave_data))
        assert len(self._overworld_caves) == 22  # 0-19 are actual caves, 20-21 are for the armos/coast

    def _get_raw_level_stairway_room_number_list(self, level_num: int) -> List[int]:
        """Internal: Get raw stairway room list from level info."""
        vals = self._level_info[level_num][
            LEVEL_INFO_STAIRWAY_LIST_OFFSET:LEVEL_INFO_STAIRWAY_LIST_OFFSET + 10]
        stairway_list: List[int] = []
        for val in vals:
            if val != 0xFF:
                stairway_list.append(val)

        # Hack for vanilla L3 - see comment in original code
        if level_num == 3 and not stairway_list:
            stairway_list.append(0x0F)
        return stairway_list

    def _get_patch_for_level_grid(self, start_address: int, rooms: List[Room]) -> Patch:
        """Internal: Generate patch data for a level grid."""
        patch = Patch()
        for room_num in Range.VALID_ROOM_NUMBERS:
            room_data = rooms[room_num].GetRomData()
            assert len(room_data) == NUM_BYTES_OF_DATA_PER_ROOM

            for table_num in range(NUM_BYTES_OF_DATA_PER_ROOM):
                patch.AddData(
                    start_address + table_num * LEVEL_TABLE_SIZE + room_num,
                    [room_data[table_num]]
                )
        return patch

    def _get_patch_for_overworld(self) -> Patch:
        """Internal: Generate patch data for overworld data."""
        patch = Patch()

        # Write cave item and price data
        for cave_num in Range.VALID_CAVE_NUMBERS:
            if cave_num == CAVE_NUMBER_ARMOS_ITEM:
                patch.AddData(
                    RomLayout.ARMOS_ITEM.file_offset,
                    [self._overworld_caves[cave_num].GetItemAtPosition(2)]
                )
                continue
            if cave_num == CAVE_NUMBER_COAST_ITEM:
                patch.AddData(
                    RomLayout.COAST_ITEM.file_offset,
                    [self._overworld_caves[cave_num].GetItemAtPosition(2)]
                )
                continue

            patch.AddData(
                RomLayout.CAVE_ITEM_DATA.file_offset + (3 * cave_num),
                self._overworld_caves[cave_num].GetItemData()
            )
            patch.AddData(
                RomLayout.CAVE_PRICE_DATA.file_offset + (3 * cave_num),
                self._overworld_caves[cave_num].GetPriceData()
            )

        # Write overworld screen data
        overworld_start = RomLayout.OVERWORLD_DATA.file_offset

        # Table 1 (offset 0x80): Screen destinations
        for screen_num in range(0x80):
            patch.AddData(
                overworld_start + 0x80 + screen_num,
                [self._overworld_raw_data[screen_num + 1*0x80]]
            )

        # Table 2 (offset 0x100): Enemy data
        for screen_num in range(0x80):
            patch.AddData(
                overworld_start + 0x100 + screen_num,
                [self._overworld_raw_data[screen_num + 2*0x80]]
            )

        return patch

    def _get_patch_for_level_info(self) -> Patch:
        """Internal: Generate patch data for level info tables."""
        patch = Patch()
        for level_num, info in enumerate(self._level_info):
            # Start writing at offset 0x24 to skip PPU palette data
            start = (RomLayout.LEVEL_INFO.file_offset +
                     level_num * LEVEL_INFO_BLOCK_SIZE +
                     LEVEL_INFO_PPU_PALETTE_SIZE)
            patch.AddData(start, info)
        return patch

    def _get_patch_for_recorder_warps(self) -> Patch:
        """Internal: Generate patch data for recorder warp destinations and Y coords."""
        patch = Patch()
        patch.AddData(
            RomLayout.RECORDER_WARP_DESTINATIONS.file_offset,
            self._recorder_warp_destinations
        )
        patch.AddData(
            RomLayout.RECORDER_WARP_Y_COORDINATES.file_offset,
            self._recorder_warp_y_coordinates
        )
        return patch

    def _get_patch_for_heart_requirements(self) -> Patch:
        """Internal: Generate patch data for heart container requirements."""
        patch = Patch()
        patch.AddData(
            RomLayout.WHITE_SWORD_REQUIREMENT.file_offset,
            [self._white_sword_hearts_raw]
        )
        patch.AddData(
            RomLayout.MAGICAL_SWORD_REQUIREMENT.file_offset,
            [self._magical_sword_hearts_raw]
        )
        return patch
