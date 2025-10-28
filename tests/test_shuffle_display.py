#!/usr/bin/env python3
"""
Test script to demonstrate item shuffling with before/after locations.
"""
import io
import random
from logic.flags import Flags
from logic.item_randomizer import ItemRandomizer
from logic.data_table import DataTable
from logic.rom_reader import RomReader

def load_rom(rom_path):
    """Load ROM file into bytes"""
    with open(rom_path, 'rb') as f:
        return f.read()

def main():
    print("=" * 80)
    print("ITEM SHUFFLE DEMONSTRATION")
    print("=" * 80)

    # Load ROM
    rom_path = './uploads/Legend of Zelda, The (USA) (Rev 1).nes'
    print(f"\nLoading ROM: {rom_path}")
    rom_data = load_rom(rom_path)
    rom_bytes = io.BytesIO(rom_data)

    # Set up flags
    print("\nConfiguring flags:")
    flags = Flags()
    flags.set('full_major_item_shuffle', True)
    flags.set('heart_container_in_each_level_1_8', True)
    flags.set('shuffle_wood_sword_cave_item', True)
    flags.set('shuffle_white_sword_cave_item', True)
    flags.set('shuffle_letter_cave_item', True)
    print("  ✓ full_major_item_shuffle = True")
    print("  ✓ heart_container_in_each_level_1_8 = True")
    print("  ✓ shuffle_wood_sword_cave_item = True")
    print("  ✓ shuffle_white_sword_cave_item = True")
    print("  ✓ shuffle_letter_cave_item = True")

    # Set seed
    seed = 42
    random.seed(seed)
    print(f"\nUsing seed: {seed}")

    # Create data table and item randomizer
    print("\nInitializing randomizer...")
    rom_reader = RomReader(rom_bytes)
    data_table = DataTable(rom_reader)
    item_randomizer = ItemRandomizer(data_table, flags)

    # Read items and locations (captures original state)
    print("Reading item locations from ROM...")
    item_randomizer.ReadItemsAndLocationsFromTable()

    # Capture BEFORE state - build a map of location -> original item
    print("Capturing BEFORE state...")
    before_state = {}

    # Get all locations that will have items
    all_locations = []
    for level_num in range(0, 11):
        all_locations.extend(item_randomizer.item_shuffler.per_level_item_location_lists[level_num])

    # Read the original items from the ROM at each location
    for location in all_locations:
        if location.IsLevelRoom():
            original_item = data_table.GetRoom(location.GetLevelNum(), location.GetRoomNum()).GetItem()
            before_state[location] = original_item
        elif location.IsCavePosition():
            original_item = data_table.GetCaveItem(location)
            before_state[location] = original_item

    # Summarize items going into shuffle pool
    items_in_pool = list(item_randomizer.item_shuffler.item_num_list)
    reserved_items_count = sum(len(v) for v in item_randomizer.item_shuffler.per_level_original_items.values())

    print(f"  Total locations: {len(all_locations)}")
    print(f"  Items in shuffle pool: {len(items_in_pool)}")
    print(f"  Reserved items (MAP/COMPASS/TRIFORCE/shop minor): {reserved_items_count}")

    # Now shuffle
    print("\nShuffling items...")
    item_randomizer.ShuffleItems()

    # Capture AFTER state
    print("Capturing AFTER state...")
    after_state = {}
    for level_num in range(0, 11):
        for location, item in zip(
            item_randomizer.item_shuffler.per_level_item_location_lists[level_num],
            item_randomizer.item_shuffler.per_level_item_lists[level_num]
        ):
            after_state[location] = item

    # Print results
    print("\n" + "=" * 80)
    print("SHUFFLE RESULTS: BEFORE vs AFTER")
    print("=" * 80)

    # Group by level and show before/after
    for level_num in range(1, 10):
        level_locations = [loc for loc in all_locations
                          if loc.IsLevelRoom() and loc.GetLevelNum() == level_num]
        if level_locations:
            print(f"\n{'='*80}")
            print(f"LEVEL {level_num}")
            print(f"{'='*80}")
            print(f"{'Location':<40} {'BEFORE':<20} {'AFTER':<20}")
            print(f"{'-'*80}")
            for loc in level_locations:
                before_item = before_state.get(loc, "???")
                after_item = after_state.get(loc, "???")
                moved = "  ←" if before_item != after_item else ""
                print(f"{loc.ToString():<40} {str(before_item):<20} {str(after_item):<20}{moved}")

    # Caves (level 10 / overworld)
    cave_locations = [loc for loc in all_locations if loc.IsCavePosition()]
    if cave_locations:
        print(f"\n{'='*80}")
        print(f"CAVES (Overworld)")
        print(f"{'='*80}")
        print(f"{'Location':<40} {'BEFORE':<20} {'AFTER':<20}")
        print(f"{'-'*80}")
        for loc in cave_locations[:15]:  # Show first 15
            before_item = before_state.get(loc, "???")
            after_item = after_state.get(loc, "???")
            moved = "  ←" if before_item != after_item else ""
            print(f"{loc.ToString():<40} {str(before_item):<20} {str(after_item):<20}{moved}")
        if len(cave_locations) > 15:
            print(f"... and {len(cave_locations) - 15} more cave locations")

    print("\n" + "=" * 80)
    print("✓ Shuffle demonstration complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()
