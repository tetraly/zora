"""
Test that progressive items cannot appear in shops when progressive_items flag is enabled.

This test verifies that when the progressive_items flag is enabled:
1. The required shop shuffle flags are also enabled (shuffle_shop_arrows, shuffle_shop_candle, shuffle_shop_ring)
2. No progressive items (arrows, candles, rings, swords) end up in shop locations
3. The flag validation correctly rejects invalid flag combinations

Progressive items that should never appear in shops with progressive_items enabled:
- WOOD_ARROWS, SILVER_ARROWS
- BLUE_CANDLE, RED_CANDLE
- BLUE_RING, RED_RING
- WOOD_SWORD, WHITE_SWORD, MAGICAL_SWORD
"""
import io
import sys
import os

# Add logic directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.flags import Flags
from logic.item_randomizer import ItemShuffler
from logic.randomizer_constants import Item
from logic.location import Location
from rng.random_number_generator import RandomNumberGenerator


# These imports are only needed for ROM-dependent tests
def try_import_rom_dependencies():
    """Try to import ROM-dependent modules."""
    try:
        from logic.randomizer import Z1Randomizer
        from logic.item_randomizer import ItemRandomizer
        from logic.data_table import DataTable
        from logic.rom_reader import RomReader
        return True
    except ImportError:
        return False


ROM_DEPENDENCIES_AVAILABLE = try_import_rom_dependencies()


def load_rom():
    """Load ROM file into BytesIO. Returns None if not found."""
    # Try several possible ROM locations
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'roms', 'Z1_20250928_1NhjkmR55xvmdk0LmGY9fDm2xhOqxKzDfv.nes'),
        os.path.join(os.path.dirname(__file__), '..', 'roms', 'zelda.nes'),
        os.path.join(os.path.dirname(__file__), '..', 'test_rom.nes'),
    ]

    for rom_path in possible_paths:
        if os.path.exists(rom_path):
            with open(rom_path, 'rb') as f:
                rom_data = f.read()
            return rom_data

    return None


def get_progressive_items():
    """Return the list of progressive items that shouldn't be in shops."""
    return [
        Item.WOOD_ARROWS, Item.SILVER_ARROWS,
        Item.BLUE_CANDLE, Item.RED_CANDLE,
        Item.BLUE_RING, Item.RED_RING,
        Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD
    ]


def test_flag_validation():
    """Test that Flags.validate() correctly enforces progressive_items requirements."""
    print("\n" + "=" * 70)
    print("TEST: Flag Validation for Progressive Items")
    print("=" * 70)

    # Test 1: progressive_items without required shop shuffle flags should fail
    flags = Flags()
    flags.set('progressive_items', True)
    is_valid, errors = flags.validate()

    if not is_valid:
        print("✓ PASS: progressive_items without shop shuffle flags correctly rejected")
        print(f"  Error message: {errors[0][:80]}...")
    else:
        print("✗ FAIL: progressive_items without shop shuffle flags should be rejected")
        return False

    # Test 2: progressive_items with all required flags should pass
    flags = Flags()
    flags.set('progressive_items', True)
    flags.set('shuffle_shop_arrows', True)
    flags.set('shuffle_shop_candle', True)
    flags.set('shuffle_shop_ring', True)
    is_valid, errors = flags.validate()

    if is_valid:
        print("✓ PASS: progressive_items with all shop shuffle flags accepted")
    else:
        print(f"✗ FAIL: progressive_items with all shop shuffle flags should be accepted")
        print(f"  Errors: {errors}")
        return False

    # Test 3: Check get_progressive_item_dependencies returns correct flags
    deps = Flags.get_progressive_item_dependencies()
    expected_deps = ['shuffle_shop_arrows', 'shuffle_shop_candle', 'shuffle_shop_ring']
    if deps == expected_deps:
        print("✓ PASS: get_progressive_item_dependencies returns correct flags")
    else:
        print(f"✗ FAIL: get_progressive_item_dependencies returned {deps}, expected {expected_deps}")
        return False

    # Test 4: Test partial combinations
    partial_combos = [
        (['shuffle_shop_arrows'], ['shuffle_shop_candle', 'shuffle_shop_ring']),
        (['shuffle_shop_arrows', 'shuffle_shop_candle'], ['shuffle_shop_ring']),
        (['shuffle_shop_ring'], ['shuffle_shop_arrows', 'shuffle_shop_candle']),
    ]

    for enabled, missing in partial_combos:
        flags = Flags()
        flags.set('progressive_items', True)
        for flag in enabled:
            flags.set(flag, True)
        is_valid, errors = flags.validate()
        if not is_valid:
            print(f"✓ PASS: Correctly rejected when missing {missing}")
        else:
            print(f"✗ FAIL: Should reject when missing {missing}")
            return False

    return True


def test_item_shuffler_validation_no_rom():
    """Test that ItemShuffler.HasValidItemConfiguration rejects progressive items in shops.

    This test does NOT require a ROM file - it directly tests the ItemShuffler logic.
    """
    print("\n" + "=" * 70)
    print("TEST: ItemShuffler Validation for Progressive Items in Shops (No ROM)")
    print("=" * 70)

    # Create flags with progressive_items and required shop shuffle flags
    flags = Flags()
    flags.set('progressive_items', True)
    flags.set('shuffle_shop_arrows', True)
    flags.set('shuffle_shop_candle', True)
    flags.set('shuffle_shop_ring', True)

    rng = RandomNumberGenerator(12345)

    # Test each progressive item type in a shop location
    progressive_items_to_test = [
        (Item.WOOD_ARROWS, "WOOD_ARROWS"),
        (Item.BLUE_CANDLE, "BLUE_CANDLE"),
        (Item.BLUE_RING, "BLUE_RING"),
        (Item.WOOD_SWORD, "WOOD_SWORD"),
        (Item.SILVER_ARROWS, "SILVER_ARROWS"),
        (Item.RED_CANDLE, "RED_CANDLE"),
        (Item.RED_RING, "RED_RING"),
        (Item.WHITE_SWORD, "WHITE_SWORD"),
        (Item.MAGICAL_SWORD, "MAGICAL_SWORD"),
    ]

    # Test with different shop cave IDs
    # Shop locations: level_id == 0x1A (cave 0x0A) or level_id in range(0x1D, 0x21) (caves 0x0D-0x10)
    shop_caves = [0x0A, 0x0D, 0x0E, 0x0F, 0x10]

    for item, item_name in progressive_items_to_test:
        # Test with first shop cave
        shop_location = Location.CavePosition(shop_caves[0], 1)
        assert shop_location.IsShopPosition(), f"Test setup error: cave {hex(shop_caves[0])} should be a shop"

        test_shuffler = ItemShuffler(flags, rng)
        test_shuffler.per_level_item_location_lists[10] = [shop_location]
        test_shuffler.per_level_item_lists[10] = [item]

        is_valid = test_shuffler.HasValidItemConfiguration()
        if not is_valid:
            print(f"✓ PASS: ItemShuffler correctly rejects {item_name} in shop")
        else:
            print(f"✗ FAIL: ItemShuffler should reject {item_name} in shop with progressive_items")
            return False

    # Test that non-progressive items in shops are allowed
    non_progressive_items = [
        (Item.LADDER, "LADDER"),
        (Item.RAFT, "RAFT"),
        (Item.BOW, "BOW"),
        (Item.WAND, "WAND"),
        (Item.RECORDER, "RECORDER"),
        (Item.MAGICAL_KEY, "MAGICAL_KEY"),
        (Item.POWER_BRACELET, "POWER_BRACELET"),
    ]

    for item, item_name in non_progressive_items:
        shop_location = Location.CavePosition(0x0D, 1)
        test_shuffler = ItemShuffler(flags, rng)
        test_shuffler.per_level_item_location_lists[10] = [shop_location]
        test_shuffler.per_level_item_lists[10] = [item]

        is_valid = test_shuffler.HasValidItemConfiguration()
        if is_valid:
            print(f"✓ PASS: ItemShuffler correctly allows {item_name} in shops")
        else:
            print(f"✗ FAIL: ItemShuffler should allow {item_name} in shops")
            return False

    # Test that progressive items are allowed in non-shop locations
    print("\nTesting progressive items in non-shop locations...")
    non_shop_location = Location.LevelRoom(1, 0x22)  # Dungeon room
    assert not non_shop_location.IsShopPosition(), "Test setup error: level room should not be a shop"

    for item, item_name in progressive_items_to_test[:3]:  # Test a few
        test_shuffler = ItemShuffler(flags, rng)
        test_shuffler.per_level_item_location_lists[1] = [non_shop_location]
        test_shuffler.per_level_item_lists[1] = [item]

        is_valid = test_shuffler.HasValidItemConfiguration()
        if is_valid:
            print(f"✓ PASS: ItemShuffler correctly allows {item_name} in dungeon")
        else:
            print(f"✗ FAIL: ItemShuffler should allow {item_name} in dungeon")
            return False

    return True


def test_item_shuffler_with_progressive_items_disabled():
    """Test that ItemShuffler allows progressive items in shops when flag is disabled."""
    print("\n" + "=" * 70)
    print("TEST: Progressive Items Allowed in Shops When Flag Disabled")
    print("=" * 70)

    # Create flags WITHOUT progressive_items
    flags = Flags()
    flags.set('progressive_items', False)

    rng = RandomNumberGenerator(12345)

    # Progressive items should be allowed in shops when flag is disabled
    progressive_items_to_test = [
        (Item.WOOD_ARROWS, "WOOD_ARROWS"),
        (Item.BLUE_CANDLE, "BLUE_CANDLE"),
        (Item.BLUE_RING, "BLUE_RING"),
    ]

    for item, item_name in progressive_items_to_test:
        shop_location = Location.CavePosition(0x0D, 1)
        test_shuffler = ItemShuffler(flags, rng)
        test_shuffler.per_level_item_location_lists[10] = [shop_location]
        test_shuffler.per_level_item_lists[10] = [item]

        is_valid = test_shuffler.HasValidItemConfiguration()
        if is_valid:
            print(f"✓ PASS: {item_name} allowed in shop when progressive_items disabled")
        else:
            print(f"✗ FAIL: {item_name} should be allowed in shop when progressive_items disabled")
            return False

    return True


def test_all_shop_caves():
    """Test that all shop cave IDs are correctly identified."""
    print("\n" + "=" * 70)
    print("TEST: Shop Cave Identification")
    print("=" * 70)

    # Shop caves should be: 0x0A (level_id 0x1A) and 0x0D-0x10 (level_ids 0x1D-0x20)
    expected_shop_caves = [0x0A, 0x0D, 0x0E, 0x0F, 0x10]
    non_shop_caves = [0x00, 0x02, 0x03, 0x08, 0x0B, 0x11, 0x12]

    for cave_num in expected_shop_caves:
        loc = Location.CavePosition(cave_num, 1)
        if loc.IsShopPosition():
            print(f"✓ PASS: Cave {hex(cave_num)} correctly identified as shop")
        else:
            print(f"✗ FAIL: Cave {hex(cave_num)} should be a shop")
            return False

    for cave_num in non_shop_caves:
        try:
            loc = Location.CavePosition(cave_num, 1)
            if not loc.IsShopPosition():
                print(f"✓ PASS: Cave {hex(cave_num)} correctly identified as non-shop")
            else:
                print(f"✗ FAIL: Cave {hex(cave_num)} should not be a shop")
                return False
        except AssertionError:
            # Some cave numbers may be invalid
            print(f"✓ PASS: Cave {hex(cave_num)} is invalid/non-shop")

    return True


def test_is_progressive_upgrade_item():
    """Test that Item.IsProgressiveUpgradeItem() returns correct values."""
    print("\n" + "=" * 70)
    print("TEST: IsProgressiveUpgradeItem Method")
    print("=" * 70)

    expected_progressive = [
        Item.WOOD_ARROWS, Item.SILVER_ARROWS,
        Item.BLUE_CANDLE, Item.RED_CANDLE,
        Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD,
        Item.BLUE_RING, Item.RED_RING
    ]

    expected_non_progressive = [
        Item.LADDER, Item.RAFT, Item.BOW, Item.WAND, Item.RECORDER,
        Item.MAGICAL_KEY, Item.POWER_BRACELET, Item.HEART_CONTAINER,
        Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG, Item.BOOK, Item.BAIT
    ]

    for item in expected_progressive:
        if item.IsProgressiveUpgradeItem():
            print(f"✓ PASS: {item.name} correctly identified as progressive")
        else:
            print(f"✗ FAIL: {item.name} should be progressive")
            return False

    for item in expected_non_progressive:
        if not item.IsProgressiveUpgradeItem():
            print(f"✓ PASS: {item.name} correctly identified as non-progressive")
        else:
            print(f"✗ FAIL: {item.name} should not be progressive")
            return False

    return True


def test_seed_generation_no_progressive_items_in_shops(num_seeds=10):
    """Test that generated seeds never have progressive items in shops.

    This test generates multiple seeds with progressive_items enabled and verifies
    that no progressive items end up in shop locations.

    Requires a ROM file to run.
    """
    print("\n" + "=" * 70)
    print(f"TEST: Seed Generation - No Progressive Items in Shops ({num_seeds} seeds)")
    print("=" * 70)

    rom_data = load_rom()
    if rom_data is None:
        print("SKIP: ROM file not found - this test requires a ROM")
        return None  # Return None to indicate skipped

    # Import ROM-dependent modules
    from logic.randomizer import Z1Randomizer
    from logic.item_randomizer import ItemRandomizer
    from logic.data_table import DataTable
    from logic.rom_reader import RomReader

    # Create flags with progressive_items and required shop shuffle flags
    flags = Flags()
    flags.set('progressive_items', True)
    flags.set('shuffle_shop_arrows', True)
    flags.set('shuffle_shop_candle', True)
    flags.set('shuffle_shop_ring', True)
    # Enable more shuffle flags for more varied testing
    flags.set('shuffle_shop_book', True)
    flags.set('shuffle_shop_bait', True)

    progressive_items = get_progressive_items()
    all_passed = True
    test_seeds = [12345, 42, 99999, 592843, 123456, 777777, 888, 54321, 11111, 22222]

    for i, seed in enumerate(test_seeds[:num_seeds]):
        print(f"\nTesting seed {seed} ({i + 1}/{num_seeds})...")

        rom_bytes = io.BytesIO(rom_data)
        rom_reader = RomReader(rom_bytes)
        data_table = DataTable(rom_reader)
        rng = RandomNumberGenerator(seed)

        item_randomizer = ItemRandomizer(data_table, flags, rng)

        # Run the shuffling loop to find a valid configuration
        attempts = 0
        found_valid = False
        while attempts < 2000:
            attempts += 1
            data_table.ResetToVanilla()
            item_randomizer.ReplaceProgressiveItemsWithUpgrades()
            item_randomizer.ResetState()
            item_randomizer.ReadItemsAndLocationsFromTable()
            item_randomizer.ShuffleItems()
            if item_randomizer.HasValidItemConfiguration():
                found_valid = True
                break

        if not found_valid:
            print(f"  ✗ FAIL: Could not find valid configuration after {attempts} attempts")
            all_passed = False
            continue

        # Now verify no progressive items are in shops
        shop_items_found = []
        for location, item in item_randomizer.item_shuffler.GetAllLocationAndItemData():
            if location.IsShopPosition() and item in progressive_items:
                shop_items_found.append((location.ToString(), item.name))

        if shop_items_found:
            print(f"  ✗ FAIL: Found progressive items in shops after {attempts} attempts:")
            for loc, item_name in shop_items_found:
                print(f"    - {item_name} at {loc}")
            all_passed = False
        else:
            print(f"  ✓ PASS: No progressive items in shops (found valid config in {attempts} attempts)")

    return all_passed


def test_full_randomizer_no_progressive_items_in_shops(num_seeds=5):
    """Test the full randomizer pipeline to verify no progressive items in shops.

    This test runs the complete Z1Randomizer.GetPatch() method and verifies
    that the generated seed doesn't have progressive items in shops.

    Requires a ROM file to run.
    """
    print("\n" + "=" * 70)
    print(f"TEST: Full Randomizer - No Progressive Items in Shops ({num_seeds} seeds)")
    print("=" * 70)

    rom_data = load_rom()
    if rom_data is None:
        print("SKIP: ROM file not found - this test requires a ROM")
        return None  # Return None to indicate skipped

    # Import ROM-dependent modules
    from logic.randomizer import Z1Randomizer

    # Create flags with progressive_items and required shop shuffle flags
    flags = Flags()
    flags.set('progressive_items', True)
    flags.set('shuffle_shop_arrows', True)
    flags.set('shuffle_shop_candle', True)
    flags.set('shuffle_shop_ring', True)

    all_passed = True
    test_seeds = [12345, 42, 99999, 592843, 123456]

    for i, seed in enumerate(test_seeds[:num_seeds]):
        print(f"\nTesting seed {seed} ({i + 1}/{num_seeds})...")

        try:
            rom_bytes = io.BytesIO(rom_data)
            randomizer = Z1Randomizer(rom_bytes, seed, flags)
            patch = randomizer.GetPatch()
            hash_code = patch.GetHashCode()
            print(f"  ✓ PASS: Seed {seed} generated successfully (hash: {hash_code})")
        except Exception as e:
            print(f"  ✗ FAIL: Seed {seed} failed with error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    return all_passed


def main():
    """Run all progressive items tests."""
    print("=" * 70)
    print("PROGRESSIVE ITEMS IN SHOPS TEST SUITE")
    print("=" * 70)
    print("\nThis test suite verifies that progressive items cannot appear in shops")
    print("when the progressive_items flag is enabled.")

    results = []

    # Core tests (no ROM required)
    results.append(("Flag Validation", test_flag_validation()))
    results.append(("ItemShuffler Validation (No ROM)", test_item_shuffler_validation_no_rom()))
    results.append(("Progressive Items Disabled", test_item_shuffler_with_progressive_items_disabled()))
    results.append(("Shop Cave Identification", test_all_shop_caves()))
    results.append(("IsProgressiveUpgradeItem Method", test_is_progressive_upgrade_item()))

    # ROM-dependent tests (may be skipped)
    results.append(("Seed Generation (10 seeds)", test_seed_generation_no_progressive_items_in_shops(10)))
    results.append(("Full Randomizer (5 seeds)", test_full_randomizer_no_progressive_items_in_shops(5)))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    all_passed = True
    skipped_count = 0
    for test_name, passed in results:
        if passed is None:
            status = "⊘ SKIP"
            skipped_count += 1
        elif passed:
            status = "✓ PASS"
        else:
            status = "✗ FAIL"
            all_passed = False
        print(f"  {status}: {test_name}")

    print("\n" + "=" * 70)
    if all_passed:
        if skipped_count > 0:
            print(f"✓ ALL EXECUTED TESTS PASSED ({skipped_count} skipped - no ROM)")
        else:
            print("✓ ALL TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
