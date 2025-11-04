"""Tests for NewItemRandomizer."""

import pytest
import sys
from pathlib import Path

# Add parent directory to path to import logic modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from logic.items import NewItemRandomizer
from logic.rom_reader import RomReader
from logic.data_table import DataTable
from logic.flags import Flags
from logic.randomizer_constants import Item
from test_rom_builder import build_minimal_rom


@pytest.fixture(scope="session")
def vanilla_rom():
    """Create a minimal ROM from extracted test data."""
    rom_data = build_minimal_rom('data')
    return RomReader(rom_data)


@pytest.fixture(scope="session")
def vanilla_data_table(vanilla_rom):
    data_table = DataTable(vanilla_rom)
    data_table.ResetToVanilla()
    return data_table


@pytest.fixture
def modifiable_data_table(vanilla_rom):
    """Returns a fresh data table that can be modified in tests."""
    data_table = DataTable(vanilla_rom)
    data_table.ResetToVanilla()
    return data_table


@pytest.fixture
def default_flags():
    return Flags()


def test_normalize_no_item_code(modifiable_data_table):
    """Test that NormalizeNoItemCode changes 0x03 to 0x18 in dungeons."""
    # Before normalization, some rooms should have 0x03 (MAGICAL_SWORD code used for NO_ITEM)
    rooms_with_03_before = 0
    for level_num in range(1, 10):  # Dungeons 1-9 only
        for room_num in range(0, 0x80):
            item = modifiable_data_table.GetItem(level_num, room_num)
            if item == Item.MAGICAL_SWORD:  # 0x03
                rooms_with_03_before += 1

    print(f"\nRooms with 0x03 before normalization: {rooms_with_03_before}")

    # Normalize
    modifiable_data_table.NormalizeNoItemCode()

    # After normalization, no rooms should have 0x03, and some should have 0x18
    rooms_with_03_after = 0
    rooms_with_18_after = 0
    for level_num in range(1, 10):  # Dungeons 1-9 only
        for room_num in range(0, 0x80):
            item = modifiable_data_table.GetItem(level_num, room_num)
            if item == Item.MAGICAL_SWORD:  # 0x03
                rooms_with_03_after += 1
            if item == Item.NO_ITEM:  # 0x18
                rooms_with_18_after += 1

    print(f"Rooms with 0x03 after normalization: {rooms_with_03_after}")
    print(f"Rooms with 0x18 after normalization: {rooms_with_18_after}")

    # Verify normalization happened
    assert rooms_with_03_after == 0, "Should have no 0x03 codes after normalization"
    assert rooms_with_18_after == rooms_with_03_before, \
        f"Expected {rooms_with_03_before} rooms with 0x18, got {rooms_with_18_after}"


def test_visit_all_rooms(modifiable_data_table, default_flags):
    """Test that VisitAllRooms finds rooms in each level."""
    item_randomizer = NewItemRandomizer(modifiable_data_table, default_flags)
    item_randomizer.VisitAllRooms()

    # Check that we found rooms in each level
    for level_num in range(1, 10):  # Dungeons 1-9 only
        room_count = len(item_randomizer.visited_rooms[level_num])
        print(f"Level {level_num}: {room_count} rooms")
        assert room_count > 0, f"No rooms found in level {level_num}"


def test_filter_impossible_item_rooms(modifiable_data_table, default_flags):
    """Test that FilterOutImpossibleItemRooms removes entrance rooms and NPC rooms."""
    item_randomizer = NewItemRandomizer(modifiable_data_table, default_flags)
    item_randomizer.VisitAllRooms()

    # Count rooms before filtering
    rooms_before = {}
    for level_num in range(1, 10):  # Dungeons 1-9 only
        rooms_before[level_num] = len(item_randomizer.visited_rooms[level_num])

    # Filter
    for level_num in range(1, 10):  # Dungeons 1-9 only
        item_randomizer.FilterOutImpossibleItemRooms(level_num)

    # Count rooms after filtering
    rooms_after = {}
    for level_num in range(1, 10):  # Dungeons 1-9 only
        rooms_after[level_num] = len(item_randomizer.visited_rooms[level_num])
        print(f"Level {level_num}: {rooms_before[level_num]} -> {rooms_after[level_num]} rooms")

    # Verify filtering removed some rooms
    total_before = sum(rooms_before.values())
    total_after = sum(rooms_after.values())
    assert total_after < total_before, \
        f"Filtering should remove some rooms. Before: {total_before}, After: {total_after}"


def test_full_randomization(modifiable_data_table, default_flags):
    """Test the full randomization pipeline."""
    item_randomizer = NewItemRandomizer(modifiable_data_table, default_flags)

    # Run full randomization
    item_randomizer.Randomize()

    # Verify that rooms were visited
    total_rooms = sum(len(rooms) for rooms in item_randomizer.visited_rooms.values())
    print(f"\nTotal rooms processed: {total_rooms}")
    assert total_rooms > 0, "Should have processed at least some rooms"

    # Verify NO_ITEM code was normalized (no 0x03 in dungeons)
    for level_num in range(1, 10):  # Dungeons 1-9 only
        for room_num in range(0, 0x80):
            item = modifiable_data_table.GetItem(level_num, room_num)
            assert item != Item.MAGICAL_SWORD or item == Item.RUPEE or item != 0x03, \
                f"Found 0x03 in level {level_num} room {hex(room_num)} after normalization"


def test_item_stairway_constraint(modifiable_data_table, default_flags):
    """Test that item stairways always have items after shuffling."""
    item_randomizer = NewItemRandomizer(modifiable_data_table, default_flags)
    item_randomizer.Randomize()

    # Check all item stairways have items (not NO_ITEM/RUPEE)
    violations = []
    for level_num in range(1, 10):  # Dungeons 1-9 only
        staircase_rooms = modifiable_data_table.GetLevelStaircaseRoomNumberList(level_num)
        for stairway_room_num in staircase_rooms:
            if modifiable_data_table.IsItemStaircase(level_num, stairway_room_num):
                item = modifiable_data_table.GetItem(level_num, stairway_room_num)
                if item == Item.NO_ITEM:  # 0x18
                    violations.append((level_num, stairway_room_num))

    if violations:
        print(f"\nItem stairways with NO_ITEM: {violations}")
        assert False, f"Found {len(violations)} item stairways with NO_ITEM"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
