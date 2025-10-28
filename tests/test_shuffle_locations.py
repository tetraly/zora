#!/usr/bin/env python3
"""
Show item shuffle with actual before/after locations.
"""
import logging
import io
import random
from logic.flags import Flags
from logic.item_randomizer import ItemRandomizer
from logic.data_table import DataTable
from logic.rom_reader import RomReader

log = logging.getLogger(__name__)

def main():
    # Load ROM
    rom_path = './uploads/Legend of Zelda, The (USA) (Rev 1).nes'
    with open(rom_path, 'rb') as f:
        rom_data = f.read()

    # Setup flags - Feel free to toggle these True/False to test different combinations!
    flags = Flags()

    # === CORE SHUFFLE FLAGS ===
    flags.set('progressive_items', True)                         # Progressive item system (WOOD_SWORD/ARROWS/etc upgrade)
    flags.set('full_major_item_shuffle', True)                   # Enable inter-level item shuffling

    # === HEART CONTAINER CONSTRAINTS ===
    flags.set('heart_container_in_each_level_1_8', True)        # Force exactly 1 HC in each level 1-8
    flags.set('force_two_heart_containers_to_level_nine', False)  # Force 2 HCs in level 9

    # === LEVEL 9 CONSTRAINTS ===
    flags.set('allow_important_items_in_level_nine', False)      # Allow BOW/LADDER/RAFT/RECORDER/BRACELET in L9
    flags.set('force_arrow_to_level_nine', True)
    flags.set('force_ring_to_level_nine', True)
    flags.set('force_heart_container_to_coast', True)

    # === CAVE ITEM SHUFFLES ===
    flags.set('shuffle_wood_sword_cave_item', True)              # Shuffle starting sword cave
    flags.set('shuffle_white_sword_cave_item', True)             # Shuffle white sword cave
    flags.set('shuffle_magical_sword_cave_item', True)           # Shuffle magical sword cave
    flags.set('shuffle_letter_cave_item', True)                  # Shuffle letter cave
    flags.set('shuffle_coast_item', True)                        # Shuffle coast/armos knight items
    flags.set('shuffle_armos_item', True)                        # Shuffle armos knight items

    # === SHOP ITEM SHUFFLES ===
    flags.set('shuffle_shop_arrows', True)                       # Shuffle arrows from shops
    flags.set('shuffle_shop_candle', True)                       # Shuffle candle from shops
    flags.set('shuffle_shop_ring', True)                         # Shuffle ring from shops
    flags.set('shuffle_shop_book', True)                         # Shuffle book from shops
    flags.set('shuffle_potion_shop_items', True)                 # Shuffle potion shop items

    # === SEED ===
    seed = 123  # Try: 123, 12345, 99999, 42, 777
    random.seed(seed)

    print("=" * 80)
    print("ITEM SHUFFLE: BEFORE AND AFTER LOCATIONS")
    print("=" * 80)
    print(f"Seed: {seed}")
    print(f"\nFlags configured:")
    print(f"  Core:")
    print(f"    - progressive_items = {flags.get('progressive_items')}")
    print(f"    - full_major_item_shuffle = {flags.get('full_major_item_shuffle')}")
    print(f"  Heart Containers:")
    print(f"    - heart_container_in_each_level_1_8 = {flags.get('heart_container_in_each_level_1_8')}")
    print(f"    - force_two_heart_containers_to_level_nine = {flags.get('force_two_heart_containers_to_level_nine')}")
    print(f"  Level 9:")
    print(f"    - allow_important_items_in_level_nine = {flags.get('allow_important_items_in_level_nine')}")
    print(f"  Caves:")
    print(f"    - shuffle_wood_sword_cave_item = {flags.get('shuffle_wood_sword_cave_item')}")
    print(f"    - shuffle_white_sword_cave_item = {flags.get('shuffle_white_sword_cave_item')}")
    print(f"    - shuffle_magical_sword_cave_item = {flags.get('shuffle_magical_sword_cave_item')}")
    print(f"    - shuffle_letter_cave_item = {flags.get('shuffle_letter_cave_item')}")
    print(f"    - shuffle_coast_item = {flags.get('shuffle_coast_item')}")
    print(f"    - shuffle_armos_item = {flags.get('shuffle_armos_item')}")
    print(f"  Shops:")
    print(f"    - shuffle_shop_arrows = {flags.get('shuffle_shop_arrows')}")
    print(f"    - shuffle_shop_candle = {flags.get('shuffle_shop_candle')}")
    print(f"    - shuffle_shop_ring = {flags.get('shuffle_shop_ring')}")
    print(f"    - shuffle_shop_book = {flags.get('shuffle_shop_book')}")
    print(f"    - shuffle_potion_shop_items = {flags.get('shuffle_potion_shop_items')}")
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

    # Capture BEFORE state - map each location to its original item
    shuffler = item_randomizer.item_shuffler
    before_state = {}
    for level_num in range(0, 11):
        for location in shuffler.per_level_item_location_lists[level_num]:
            # Read the original item from the ROM at this location
            if location.IsLevelRoom():
                original_item = data_table.GetRoom(location.GetLevelNum(), location.GetRoomNum()).GetItem()
                before_state[location.ToString()] = original_item
            elif location.IsCavePosition():
                original_item = data_table.GetCaveItem(location)
                before_state[location.ToString()] = original_item

    # Shuffle
    log.setLevel(logging.DEBUG)
    item_randomizer.ShuffleItems()

    # Capture AFTER state - map each location to its new item
    after_state = {}
    for level_num in range(0, 11):
        for location, item in zip(
            shuffler.per_level_item_location_lists[level_num],
            shuffler.per_level_item_lists[level_num]
        ):
            after_state[location.ToString()] = item

    # Display results grouped by level
    print("\nITEM LOCATIONS: BEFORE vs AFTER")
    print("=" * 80)
    print(f"{'Location':<40} {'BEFORE':<20} {'AFTER':<20}")
    print("=" * 80)

    for level_num in range(1, 10):
        level_locations = [loc for loc in shuffler.per_level_item_location_lists[level_num]]

        if level_locations:
            print(f"\n{'LEVEL ' + str(level_num):^80}")
            print("-" * 80)

            for location in level_locations:
                loc_str = location.ToString()
                before_item = before_state.get(loc_str, "???")
                after_item = after_state.get(loc_str, "???")

                # Mark if item changed
                if before_item != after_item:
                    marker = " ←"
                else:
                    marker = ""

                before_name = before_item.name if hasattr(before_item, 'name') else str(before_item)
                after_name = after_item.name if hasattr(after_item, 'name') else str(after_item)

                print(f"{loc_str:<40} {before_name:<20} {after_name:<20}{marker}")

    # Caves
    cave_locations = [loc for loc in shuffler.per_level_item_location_lists[10]]

    if cave_locations:
        print(f"\n{'CAVES (Overworld)':^80}")
        print("-" * 80)

        for location in cave_locations:
            loc_str = location.ToString()
            before_item = before_state.get(loc_str, "???")
            after_item = after_state.get(loc_str, "???")

            # Mark if item changed
            if before_item != after_item:
                marker = " ←"
            else:
                marker = ""

            before_name = before_item.name if hasattr(before_item, 'name') else str(before_item)
            after_name = after_item.name if hasattr(after_item, 'name') else str(after_item)

            print(f"{loc_str:<40} {before_name:<20} {after_name:<20}{marker}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    total_locations = sum(len(shuffler.per_level_item_location_lists[i]) for i in range(0, 11))
    changes = sum(1 for loc_str in before_state if before_state[loc_str] != after_state.get(loc_str))
    print(f"Total shuffled locations: {total_locations}")
    print(f"Items that moved: {changes}")
    print(f"Items that stayed: {total_locations - changes}")
    print(f"\nNote: MAP, COMPASS, TRIFORCE, and shop minor items stay in original ROM")
    print(f"      locations and are not included in the shuffle.")
    print("=" * 80)

if __name__ == "__main__":
    main()
