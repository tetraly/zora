#!/usr/bin/env python3
"""
Demonstrate item shuffling with before/after locations.
"""
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

    # Setup flags
    flags = Flags()
    flags.set('full_major_item_shuffle', True)
    flags.set('allow_important_items_in_level_nine', True)

    seed = 12345
    random.seed(seed)

    print("=" * 80)
    print("ITEM SHUFFLE DEMONSTRATION - BEFORE AND AFTER")
    print("=" * 80)
    print(f"Seed: {seed}")
    print(f"Flags: full_major_item_shuffle=True, allow_important_items_in_level_nine=True")
    print("=" * 80)

    # Create randomizer and read items
    rom_bytes = io.BytesIO(rom_data)
    rom_reader = RomReader(rom_bytes)
    data_table = DataTable(rom_reader)
    item_randomizer = ItemRandomizer(data_table, flags)

    # Prepare like Z1Randomizer does
    data_table.ResetToVanilla()
    item_randomizer.ReplaceProgressiveItemsWithUpgrades()
    item_randomizer.ResetState()
    item_randomizer.ReadItemsAndLocationsFromTable()

    # Capture BEFORE state (items by their original level)
    shuffler = item_randomizer.item_shuffler
    before_by_level = {}
    for level_num in range(0, 11):
        if shuffler.per_level_original_items[level_num]:
            before_by_level[level_num] = list(shuffler.per_level_original_items[level_num])

    # Shuffle
    item_randomizer.ShuffleItems()

    # Capture AFTER state (items by their new level)
    after_by_level = {}
    for level_num in range(0, 11):
        if shuffler.per_level_item_lists[level_num]:
            after_by_level[level_num] = list(shuffler.per_level_item_lists[level_num])

    # Display results
    print("\nITEM DISTRIBUTION BY LEVEL")
    print("=" * 80)

    for level_num in range(1, 10):
        before_items = before_by_level.get(level_num, [])
        after_items = after_by_level.get(level_num, [])

        if before_items or after_items:
            print(f"\n{'='*80}")
            print(f"LEVEL {level_num}")
            print(f"{'='*80}")

            print(f"\nBEFORE (original {len(before_items)} items):")
            for item in before_items:
                print(f"  {item.name}")

            print(f"\nAFTER (shuffled {len(after_items)} items):")
            for item in after_items:
                moved = "  ← MOVED HERE" if item not in before_items else ""
                print(f"  {item.name}{moved}")

    # Caves/Overworld
    before_cave_items = before_by_level.get(10, [])
    after_cave_items = after_by_level.get(10, [])

    if before_cave_items or after_cave_items:
        print(f"\n{'='*80}")
        print(f"CAVES (Overworld)")
        print(f"{'='*80}")

        print(f"\nBEFORE (original {len(before_cave_items)} items):")
        for item in before_cave_items:
            print(f"  {item.name}")

        print(f"\nAFTER (shuffled {len(after_cave_items)} items):")
        for item in after_cave_items:
            moved = "  ← MOVED HERE" if item not in before_cave_items else ""
            print(f"  {item.name}{moved}")

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    total_shuffled = sum(len(items) for items in after_by_level.values())
    print(f"Total items in shuffle pool: {total_shuffled}")
    print(f"Note: MAP, COMPASS, TRIFORCE, and shop minor items stay in original locations")
    print(f"      (not shown above)")
    print("=" * 80)

if __name__ == "__main__":
    main()
