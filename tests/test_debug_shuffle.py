#!/usr/bin/env python3
"""Debug script to see what's happening with item allocation."""
import io
import random
from logic.flags import Flags
from logic.item_randomizer import ItemRandomizer
from logic.data_table import DataTable
from logic.rom_reader import RomReader

def main():
    # Load ROM
    rom_path = './uploads/Legend of Zelda, The (USA) (Rev 1).nes'
    with open(rom_path, 'rb') as f:
        rom_data = f.read()

    # Setup
    flags = Flags()
    flags.set('full_major_item_shuffle', True)
    flags.set('heart_container_in_each_level_1_8', True)

    seed = 42
    random.seed(seed)

    # Create randomizer
    rom_bytes = io.BytesIO(rom_data)
    rom_reader = RomReader(rom_bytes)
    data_table = DataTable(rom_reader)
    item_randomizer = ItemRandomizer(data_table, flags)

    # Prepare like Z1Randomizer does
    data_table.ResetToVanilla()
    item_randomizer.ReplaceProgressiveItemsWithUpgrades()
    item_randomizer.ResetState()

    # Read items
    item_randomizer.ReadItemsAndLocationsFromTable()

    # Check state before shuffle
    shuffler = item_randomizer.item_shuffler

    print("=" * 80)
    print("BEFORE SHUFFLE")
    print("=" * 80)
    print(f"Items in shuffle pool: {len(shuffler.item_num_list)}")
    print(f"Items: {shuffler.item_num_list[:10]}...")
    print()

    total_locations = 0
    total_reserved = 0
    for level_num in range(0, 11):
        num_locations = len(shuffler.per_level_item_location_lists[level_num])
        num_reserved = len(shuffler.per_level_original_items[level_num])
        total_locations += num_locations
        total_reserved += num_reserved
        if num_locations > 0:
            print(f"Level {level_num}: {num_locations} locations, {num_reserved} reserved items")

    print(f"\nTotal locations: {total_locations}")
    print(f"Items tracked by original level: {total_reserved}")
    print(f"Items in shuffle pool: {len(shuffler.item_num_list)}")
    print(f"\nNote: per_level_original_items tracks which level each shuffleable item")
    print(f"originally came from (for no-shuffle mode). These are the SAME items")
    print(f"as in item_num_list, just organized by original level.")
    print(f"\nExpected: locations ({total_locations}) = pool ({len(shuffler.item_num_list)})")

    if total_locations != len(shuffler.item_num_list):
        print("❌ MISMATCH!")
    else:
        print("✓ Counts match!")

if __name__ == "__main__":
    main()
