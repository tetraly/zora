"""Tests for RoomItemCollector."""

import pytest
import sys
from pathlib import Path

# Add parent directory to path to import logic modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from logic.items.room_item_collector import RoomItemCollector
from logic.rom_reader import RomReader
from logic.data_table import DataTable
from logic.randomizer_constants import Item, RoomType
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


def test_collect_all_finds_rooms_in_each_level(modifiable_data_table):
    """Test that CollectAll finds rooms in each level."""
    collector = RoomItemCollector(modifiable_data_table)
    room_item_pairs = collector.CollectAll()

    # Check that we found rooms in each level
    for level_num in range(1, 10):  # Dungeons 1-9 only
        room_count = len(room_item_pairs[level_num])
        print(f"Level {level_num}: {room_count} rooms")
        assert room_count > 0, f"No rooms found in level {level_num}"


def test_filters_out_entrance_rooms(modifiable_data_table):
    """Test that CollectAll filters out entrance rooms."""
    collector = RoomItemCollector(modifiable_data_table)
    room_item_pairs = collector.CollectAll()

    # Verify no entrance rooms in results
    for level_num in range(1, 10):
        for pair in room_item_pairs[level_num]:
            room_type = modifiable_data_table.GetRoomType(level_num, pair.room_num)
            assert room_type != RoomType.ENTRANCE_ROOM, \
                f"Level {level_num} room 0x{pair.room_num:02X} is an entrance room"


def test_filters_out_transport_staircases(modifiable_data_table):
    """Test that CollectAll filters out transport staircases."""
    collector = RoomItemCollector(modifiable_data_table)
    room_item_pairs = collector.CollectAll()

    # Verify no transport staircases in results
    for level_num in range(1, 10):
        for pair in room_item_pairs[level_num]:
            room_type = modifiable_data_table.GetRoomType(level_num, pair.room_num)
            assert room_type != RoomType.TRANSPORT_STAIRCASE, \
                f"Level {level_num} room 0x{pair.room_num:02X} is a transport staircase"


def test_includes_item_staircases(modifiable_data_table):
    """Test that CollectAll includes item staircases."""
    collector = RoomItemCollector(modifiable_data_table)
    room_item_pairs = collector.CollectAll()

    # Find at least one item staircase
    found_item_staircase = False
    for level_num in range(1, 10):
        for pair in room_item_pairs[level_num]:
            room_type = modifiable_data_table.GetRoomType(level_num, pair.room_num)
            if room_type == RoomType.ITEM_STAIRCASE:
                found_item_staircase = True
                print(f"Found item staircase: Level {level_num} room 0x{pair.room_num:02X}")
                break
        if found_item_staircase:
            break

    assert found_item_staircase, "Should find at least one item staircase"


def test_filters_out_npc_rooms(modifiable_data_table):
    """Test that CollectAll filters out rooms with NPCs."""
    collector = RoomItemCollector(modifiable_data_table)
    room_item_pairs = collector.CollectAll()

    # Verify no NPC rooms in results
    for level_num in range(1, 10):
        for pair in room_item_pairs[level_num]:
            room_type = modifiable_data_table.GetRoomType(level_num, pair.room_num)
            # Skip item staircases since enemy byte is repurposed
            if room_type == RoomType.ITEM_STAIRCASE:
                continue

            enemy = modifiable_data_table.GetRoomEnemy(level_num, pair.room_num)
            assert not enemy.IsNPC(), \
                f"Level {level_num} room 0x{pair.room_num:02X} has NPC {enemy.name}"


def test_room_item_pairs_have_correct_structure(modifiable_data_table):
    """Test that RoomItemPair tuples have correct structure."""
    collector = RoomItemCollector(modifiable_data_table)
    room_item_pairs = collector.CollectAll()

    # Verify structure of pairs
    for level_num in range(1, 10):
        for pair in room_item_pairs[level_num]:
            # Should have room_num and item attributes
            assert hasattr(pair, 'room_num'), "Pair should have room_num"
            assert hasattr(pair, 'item'), "Pair should have item"

            # room_num should be in valid range
            assert 0 <= pair.room_num < 0x80, f"Invalid room_num: 0x{pair.room_num:02X}"

            # item should be an Item enum
            assert isinstance(pair.item, Item), f"Item should be Item enum, got {type(pair.item)}"


def test_total_rooms_collected(modifiable_data_table):
    """Test that a reasonable number of rooms are collected across all levels."""
    collector = RoomItemCollector(modifiable_data_table)
    room_item_pairs = collector.CollectAll()

    total_rooms = sum(len(pairs) for pairs in room_item_pairs.values())
    print(f"\nTotal rooms collected: {total_rooms}")

    # Vanilla game has about 10-20 item rooms per level
    # Expect at least 50 total (very conservative)
    assert total_rooms >= 50, f"Expected at least 50 rooms, found {total_rooms}"

    # But not too many (shouldn't include every single room)
    assert total_rooms < 500, f"Found too many rooms: {total_rooms}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
