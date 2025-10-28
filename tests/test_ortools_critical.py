#!/usr/bin/env python3
"""
Critical test suite for OR-Tools ItemShuffler before deleting old implementation.
"""

import io
import random
from logic.flags import Flags
from logic.item_randomizer import ItemRandomizer
from logic.data_table import DataTable
from logic.rom_reader import RomReader
from logic.randomizer_constants import Item


def load_and_shuffle(flags_dict, seed):
    """Helper to load ROM and run shuffle."""
    rom_path = './uploads/Legend of Zelda, The (USA) (Rev 1).nes'
    with open(rom_path, 'rb') as f:
        rom_data = f.read()

    flags = Flags()
    for flag_name, flag_value in flags_dict.items():
        flags.set(flag_name, flag_value)

    random.seed(seed)
    rom_bytes = io.BytesIO(rom_data)
    rom_reader = RomReader(rom_bytes)
    data_table = DataTable(rom_reader)
    item_randomizer = ItemRandomizer(data_table, flags)

    data_table.ResetToVanilla()
    item_randomizer.ReplaceProgressiveItemsWithUpgrades()
    item_randomizer.ResetState()
    item_randomizer.ReadItemsAndLocationsFromTable()
    item_randomizer.ShuffleItems()

    return item_randomizer.item_shuffler


def test_1_heavy_constraints():
    """Test 1: Heavy constraints - multiple level requirements + shop exclusions."""
    print("\n[TEST 1] Heavy constraints...")

    flags = {
        'progressive_items': True,
        'full_major_item_shuffle': True,
        'heart_container_in_each_level_1_8': True,
        'force_arrow_to_level_nine': True,
        'force_ring_to_level_nine': True,
        'shuffle_shop_arrows': True,
        'shuffle_shop_candle': True,
        'shuffle_shop_ring': True,
        'shuffle_shop_book': True,
        'shuffle_potion_shop_items': True
    }

    try:
        shuffler = load_and_shuffle(flags, 12345)

        # Verify HCs in levels 1-8
        for level in range(1, 9):
            hc_count = sum(1 for item in shuffler.per_level_item_lists[level] if item == Item.HEART_CONTAINER)
            if hc_count != 1:
                print(f"  FAIL: Level {level} has {hc_count} HCs, expected 1")
                return False

        # Verify L9 has arrow and ring
        level_9 = shuffler.per_level_item_lists[9]
        has_arrow = any(item in [Item.WOOD_ARROWS, Item.SILVER_ARROWS] for item in level_9)
        has_ring = any(item in [Item.BLUE_RING, Item.RED_RING] for item in level_9)

        if not has_arrow or not has_ring:
            print(f"  FAIL: L9 missing arrow={not has_arrow} or ring={not has_ring}")
            return False

        # Verify no progressive items in shops
        for i, loc in enumerate(shuffler.per_level_item_location_lists[10]):
            if loc.IsShopPosition():
                item = shuffler.per_level_item_lists[10][i]
                if item in [Item.WOOD_SWORD, Item.WOOD_ARROWS, Item.BLUE_CANDLE, Item.BLUE_RING]:
                    print(f"  FAIL: Progressive item {item} found in shop")
                    return False

        print("  PASS: All constraints satisfied")
        return True

    except Exception as e:
        print(f"  FAIL: Exception - {e}")
        return False


def test_2_specific_location():
    """Test 2: Specific location requirements."""
    print("\n[TEST 2] Specific location requirements...")

    flags = {
        'progressive_items': True,
        'full_major_item_shuffle': True,
        'shuffle_coast_item': True,
        'force_heart_container_to_coast': True
    }

    try:
        shuffler = load_and_shuffle(flags, 54321)

        # Find coast location (Cave 0x15 = 21 decimal)
        coast_item = None
        for i, loc in enumerate(shuffler.per_level_item_location_lists[10]):
            loc_str = loc.ToString()
            if 'Cave 0x15 Position 2' in loc_str:
                coast_item = shuffler.per_level_item_lists[10][i]
                break

        if coast_item == Item.HEART_CONTAINER:
            print("  PASS: HC at coast")
            return True
        else:
            print(f"  FAIL: Coast has {coast_item}, expected HC")
            return False

    except Exception as e:
        print(f"  FAIL: Exception - {e}")
        import traceback
        traceback.print_exc()  # Print full traceback
        return False


def test_3_edge_case():
    """Test 3: Edge case - minimal slots with maximum constraints."""
    print("\n[TEST 3] Edge case (L9 with 2 slots, 2 requirements)...")

    flags = {
        'progressive_items': True,
        'full_major_item_shuffle': True,
        'force_arrow_to_level_nine': True,
        'force_ring_to_level_nine': True,
        'allow_important_items_in_level_nine': False
    }

    try:
        shuffler = load_and_shuffle(flags, 99999)

        level_9 = shuffler.per_level_item_lists[9]

        # Level 9 should have exactly 2 items
        if len(level_9) != 2:
            print(f"  FAIL: L9 has {len(level_9)} items, expected 2")
            return False

        # Both should be the required items
        has_arrow = any(item in [Item.WOOD_ARROWS, Item.SILVER_ARROWS] for item in level_9)
        has_ring = any(item in [Item.BLUE_RING, Item.RED_RING] for item in level_9)

        if has_arrow and has_ring:
            print("  PASS: L9 has exactly arrow + ring")
            return True
        else:
            print(f"  FAIL: L9 missing required items")
            return False

    except Exception as e:
        print(f"  FAIL: Exception - {e}")
        return False


def test_4_multiple_seeds():
    """Test 4: Multiple seeds produce different results."""
    print("\n[TEST 4] Randomization across seeds...")

    flags = {
        'progressive_items': True,
        'full_major_item_shuffle': True,
        'heart_container_in_each_level_1_8': True
    }

    try:
        results = []
        for seed in [111, 222, 333]:
            shuffler = load_and_shuffle(flags, seed)
            # Capture level 1 items as fingerprint
            level_1 = tuple(shuffler.per_level_item_lists[1])
            results.append(level_1)

        # Check that at least 2 are different
        unique = len(set(results))

        if unique >= 2:
            print(f"  PASS: {unique}/3 shuffles are unique")
            return True
        else:
            print(f"  FAIL: All 3 seeds produced identical shuffles")
            return False

    except Exception as e:
        print(f"  FAIL: Exception - {e}")
        return False


def test_5_intentional_failure():
    """Test 5: Impossible constraints should fail with helpful error."""
    print("\n[TEST 5] Intentional failure (impossible constraints)...")

    # This should fail: 8 HCs required in levels 1-8, plus 2 in L9 = 10 HCs total
    # But if we also require HC at coast (level 10), that's 11 HCs - impossible!
    flags = {
        'progressive_items': True,
        'full_major_item_shuffle': True,
        'heart_container_in_each_level_1_8': True,
        'force_two_heart_containers_to_level_nine': True,
        'shuffle_coast_item': True,
        'force_heart_container_to_coast': True
    }

    try:
        shuffler = load_and_shuffle(flags, 777)
        print(f"  FAIL: Should have raised exception for impossible constraints")
        return False

    except Exception as e:
        error_str = str(e)
        # Check for helpful error message
        if "INFEASIBLE" in error_str or "No valid item shuffle" in error_str or "cannot be satisfied" in error_str:
            print(f"  PASS: Correctly detected infeasibility")
            return True
        else:
            print(f"  FAIL: Exception but not helpful: {error_str[:100]}")
            return False


def main():
    """Run all critical tests."""
    print("=" * 70)
    print("CRITICAL TEST SUITE FOR OR-TOOLS ITEMSHUFFLER")
    print("=" * 70)

    results = {
        "Test 1 - Heavy constraints": test_1_heavy_constraints(),
        "Test 2 - Specific location": test_2_specific_location(),
        "Test 3 - Edge case": test_3_edge_case(),
        "Test 4 - Multiple seeds": test_4_multiple_seeds(),
        "Test 5 - Intentional failure": test_5_intentional_failure()
    }

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_test in results.items():
        status = "✓ PASS" if passed_test else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\n{passed}/{total} tests passed")
    print("=" * 70)

    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Safe to delete ItemShufflerOld")
        return True
    else:
        print("\n⚠️  SOME TESTS FAILED - Do not delete ItemShufflerOld yet")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
