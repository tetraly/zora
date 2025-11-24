"""Test ROM builder for creating custom test scenarios.

This module provides TestRomBuilder, a fluent builder pattern for creating
RomData and RomInterface instances with specific configurations for testing.

Usage:
    # Start from test data and customize
    state = (TestRomBuilder.from_test_data()
        .with_room_item(level=3, room=0x0F, item=Item.TRIFORCE)
        .with_cave_item(CaveType.SHOP_A, position=1, item=Item.BLUE_CANDLE)
        .build_state())

    # Or just get RomData
    rom_data = (TestRomBuilder.from_test_data()
        .with_room_item(3, 0x0F, Item.TRIFORCE)
        .build())
"""

from __future__ import annotations
from typing import List, Optional
import copy

from logic.randomizer_constants import CaveType, Enemy, Item, RoomType

from .rom_data import RomData, load_from_test_data
from .rom_config import (
    LEVEL_TABLE_SIZE,
    NUM_BYTES_OF_DATA_PER_ROOM,
    CAVE_NUMBER_ARMOS_ITEM,
    CAVE_NUMBER_COAST_ITEM,
)


class TestRomBuilder:
    """Builder for creating custom RomData/RomInterface instances for testing.

    This class provides a fluent API for constructing ROM data with specific
    configurations, making it easy to set up test scenarios without needing
    to understand the underlying ROM data format.

    All methods return self to allow method chaining.
    """

    def __init__(self, base: Optional[RomData] = None) -> None:
        """Initialize the builder with optional base data.

        Args:
            base: Optional RomData to start from. If None, creates empty data.
        """
        if base is None:
            # Create minimal empty RomData
            self._data = RomData(
                level_1_to_6_block=[0] * 0x300,
                level_7_to_9_block=[0] * 0x300,
                overworld_block=[0] * 0x300,
                level_info=[],
                level_info_raw=[],
                armos_item=0,
                coast_item=0,
                mixed_enemy_groups={},
                is_z1r=True,
                overworld_pointer=0x8400,
                level_1_to_6_pointer=0x8700,
                level_7_to_9_pointer=0x8A00,
            )
        else:
            # Deep copy to avoid modifying the original
            self._data = RomData(
                level_1_to_6_block=base.level_1_to_6_block[:],
                level_7_to_9_block=base.level_7_to_9_block[:],
                overworld_block=base.overworld_block[:],
                level_info=[info[:] for info in base.level_info],
                level_info_raw=[info[:] for info in base.level_info_raw],
                armos_item=base.armos_item,
                coast_item=base.coast_item,
                mixed_enemy_groups=copy.deepcopy(base.mixed_enemy_groups),
                is_z1r=base.is_z1r,
                overworld_pointer=base.overworld_pointer,
                level_1_to_6_pointer=base.level_1_to_6_pointer,
                level_7_to_9_pointer=base.level_7_to_9_pointer,
            )

    @classmethod
    def from_test_data(cls, data_dir: Optional[str] = None) -> TestRomBuilder:
        """Create a builder starting from test data files.

        Args:
            data_dir: Path to test data directory (defaults to tests/data/)

        Returns:
            TestRomBuilder instance initialized with test data
        """
        return cls(load_from_test_data(data_dir))

    @classmethod
    def empty(cls) -> TestRomBuilder:
        """Create a builder with empty/zeroed data.

        Returns:
            TestRomBuilder instance with empty data
        """
        return cls(None)

    # =========================================================================
    # Room Modification Methods
    # =========================================================================

    def with_room_item(self, level: int, room: int, item: Item) -> TestRomBuilder:
        """Set an item in a specific dungeon room.

        Args:
            level: The level number (1-9)
            room: The room number (0x00-0x7F)
            item: The Item enum to place

        Returns:
            self for method chaining
        """
        block = self._get_level_block(level)
        # Item is stored in table 4 (byte 4 of room data)
        # Lower 5 bits are item, upper 3 bits preserved
        offset = 4 * LEVEL_TABLE_SIZE + room
        block[offset] = (block[offset] & 0xE0) | int(item)
        return self

    def with_room_type(self, level: int, room: int, room_type: RoomType) -> TestRomBuilder:
        """Set the room type for a specific room.

        Args:
            level: The level number (1-9)
            room: The room number (0x00-0x7F)
            room_type: The RoomType enum to set

        Returns:
            self for method chaining
        """
        block = self._get_level_block(level)
        # Room type is stored in table 3 (byte 3 of room data)
        # Lower 6 bits are room type, upper 2 bits preserved
        offset = 3 * LEVEL_TABLE_SIZE + room
        block[offset] = (block[offset] & 0xC0) | int(room_type)
        return self

    def with_room_enemy(self, level: int, room: int, enemy: Enemy) -> TestRomBuilder:
        """Set the enemy for a specific room.

        Args:
            level: The level number (1-9)
            room: The room number (0x00-0x7F)
            enemy: The Enemy enum to set

        Returns:
            self for method chaining
        """
        block = self._get_level_block(level)
        enemy_val = int(enemy)

        # Enemy low bits (0-5) are in table 2, upper 2 bits preserved
        offset_2 = 2 * LEVEL_TABLE_SIZE + room
        block[offset_2] = (block[offset_2] & 0xC0) | (enemy_val & 0x3F)

        # Enemy bit 6 is stored in table 3 bit 7
        offset_3 = 3 * LEVEL_TABLE_SIZE + room
        if enemy_val & 0x40:
            block[offset_3] |= 0x80
        else:
            block[offset_3] &= ~0x80

        return self

    # =========================================================================
    # Cave Modification Methods
    # =========================================================================

    def with_cave_item(self, cave_type: CaveType, position: int, item: Item) -> TestRomBuilder:
        """Set an item in a cave at a specific position.

        Args:
            cave_type: The CaveType enum
            position: Position within the cave (1-indexed: 1-3)
            item: The Item enum to place

        Returns:
            self for method chaining
        """
        cave_num = int(cave_type) - 0x10

        if cave_num == CAVE_NUMBER_ARMOS_ITEM:
            if position == 2:  # Armos item is at position 2
                self._data.armos_item = int(item)
        elif cave_num == CAVE_NUMBER_COAST_ITEM:
            if position == 2:  # Coast item is at position 2
                self._data.coast_item = int(item)
        else:
            # Cave data is in overworld_block at table 4 (offset 0x200)
            # Each cave has 3 items starting at offset 0x200 + cave_num * 3
            cave_offset = 0x200 + (cave_num * 3) + (position - 1)
            # Preserve upper 2 bits, set lower 6 bits to item
            self._data.overworld_block[cave_offset] = (
                (self._data.overworld_block[cave_offset] & 0xC0) | int(item)
            )

        return self

    def with_cave_price(self, cave_type: CaveType, position: int, price: int) -> TestRomBuilder:
        """Set the price for an item in a cave.

        Args:
            cave_type: The CaveType enum
            position: Position within the cave (1-indexed: 1-3)
            price: The price in rupees

        Returns:
            self for method chaining
        """
        cave_num = int(cave_type) - 0x10

        if cave_num not in [CAVE_NUMBER_ARMOS_ITEM, CAVE_NUMBER_COAST_ITEM]:
            # Price data is at offset 0x23C + cave_num * 3 + (position - 1)
            price_offset = 0x23C + (cave_num * 3) + (position - 1)
            self._data.overworld_block[price_offset] = price

        return self

    def with_armos_item(self, item: Item) -> TestRomBuilder:
        """Set the armos item directly.

        Args:
            item: The Item enum to place

        Returns:
            self for method chaining
        """
        self._data.armos_item = int(item)
        return self

    def with_coast_item(self, item: Item) -> TestRomBuilder:
        """Set the coast item directly.

        Args:
            item: The Item enum to place

        Returns:
            self for method chaining
        """
        self._data.coast_item = int(item)
        return self

    # =========================================================================
    # Level Metadata Methods
    # =========================================================================

    def with_level_start_room(self, level: int, room: int) -> TestRomBuilder:
        """Set the starting room for a level.

        Args:
            level: The level number (0-9, 0 is overworld)
            room: The room number (0x00-0x7F)

        Returns:
            self for method chaining
        """
        if level < len(self._data.level_info):
            # Start room is at offset 0x0B within level info
            self._data.level_info[level][0x0B] = room
        return self

    def with_z1r_flag(self, is_z1r: bool) -> TestRomBuilder:
        """Set whether this should be detected as a Z1R ROM.

        Args:
            is_z1r: True if this should be detected as randomized

        Returns:
            self for method chaining
        """
        self._data.is_z1r = is_z1r
        return self

    # =========================================================================
    # Build Methods
    # =========================================================================

    def build(self) -> RomData:
        """Build and return the RomData instance.

        Returns:
            The constructed RomData
        """
        return self._data

    def build_state(self) -> 'RomInterface':
        """Build a RomInterface instance from the constructed data.

        Returns:
            A RomInterface initialized with the constructed data
        """
        # Import here to avoid circular imports
        from .rom_interface import RomInterface
        state = RomInterface(self._data)
        state.reset_to_vanilla()  # Initialize internal structures
        return state

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _get_level_block(self, level: int) -> List[int]:
        """Get the appropriate level block for a level number."""
        if level in [7, 8, 9]:
            return self._data.level_7_to_9_block
        return self._data.level_1_to_6_block
