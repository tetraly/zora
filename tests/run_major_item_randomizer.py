"""Test script for MajorItemRandomizer basic functionality."""

import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Setup logging to see debug messages
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from logic.data_table import DataTable
from logic.flags import Flags
from logic.items.major_item_randomizer import (
    MajorItemRandomizer, is_dungeon_location, is_cave_location
)
from tests.test_rom_builder import build_minimal_rom

def test_basic_collection():
    """Test basic location and item collection."""
    print("=" * 80)
    print("Testing MajorItemRandomizer Basic Collection")
    print("=" * 80)

    try:
        # Build minimal ROM from test data
        rom_data = build_minimal_rom('data')
        data_table = DataTable(rom_data)
        data_table.ResetToVanilla()

        # Create default flags
        flags = Flags()

        # Create randomizer
        randomizer = MajorItemRandomizer(data_table, flags)

        # Test location collection
        print("\nCollecting locations and items...")
        pairs = randomizer._CollectLocationsAndItems()

        print(f"\nFound {len(pairs)} total major item locations:")

        # Group by type
        dungeon_pairs = [p for p in pairs if is_dungeon_location(p.location)]
        cave_pairs = [p for p in pairs if is_cave_location(p.location)]

        print(f"  - {len(dungeon_pairs)} dungeon locations")
        print(f"  - {len(cave_pairs)} overworld cave locations")

        # Show dungeon locations by level
        print("\nDungeon Locations by Level:")
        for level_num in range(1, 10):
            level_pairs = [p for p in dungeon_pairs if p.location.level_num == level_num]
            print(f"  Level {level_num}: {len(level_pairs)} items")
            for pair in level_pairs:
                print(f"    Room 0x{pair.location.room_num:02X}: {pair.item.name}")

        # Show cave locations
        print("\nOverworld Cave Locations:")
        for pair in cave_pairs:
            print(f"  Cave {pair.location.cave_num} Position {pair.location.position_num}: {pair.item.name}")

        print("\n" + "=" * 80)
        print("Basic collection test completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    success = test_basic_collection()
    sys.exit(0 if success else 1)
