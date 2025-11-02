"""Tests for OverworldRandomizer."""

import pytest
import io
import sys
import time
from pathlib import Path
from collections import Counter

# Add parent directory to path to import logic modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from logic.overworld_randomizer import OverworldRandomizer
from logic.rom_reader import RomReader
from logic.data_table import DataTable
from logic.flags import Flags
from logic.randomizer_constants import CaveType
from logic.rom_data_specs import RomDataType
from test_rom_builder import build_minimal_rom


@pytest.fixture(scope="session")
def vanilla_rom():
    """Create a minimal ROM from extracted test data.

    This fixture builds a minimal ROM (mostly 0xFF padding) with only the
    data regions that DataTable and Validator actually read. This allows
    tests to run without checking in the full ROM file.

    To generate the test data, run:
        python3 tests/extract_test_data.py roms/z1-prg1.nes
    """
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


def test_shuffle_simple_vs_constraint(modifiable_data_table, default_flags):
    """A/B test comparing simple shuffle vs constraint-based shuffle."""
    import random
    import copy

    # Set up flags
    flags = default_flags
    flags.shuffle_caves = True

    # Collect screens and destinations
    any_road_screens = modifiable_data_table.GetRomData(RomDataType.ANY_ROAD_SCREENS)
    first_quest_screens = []
    cave_destinations = []

    for screen_num in range(0x80):
        table5_byte = modifiable_data_table.overworld_raw_data[screen_num + 5*0x80]
        if (table5_byte & 0x80) != 0:
            continue
        destination = modifiable_data_table.GetScreenDestination(screen_num)
        if destination != CaveType.NONE:
            if screen_num not in any_road_screens:
                first_quest_screens.append(screen_num)
                cave_destinations.append(destination)

    # Save original cave counts
    original_counts = Counter(cave_destinations)

    # Test 1: Simple shuffle
    random.seed(12345)
    saved_data_simple = copy.deepcopy(modifiable_data_table.overworld_raw_data)
    overworld_randomizer = OverworldRandomizer(modifiable_data_table, flags)

    start_time = time.time()
    overworld_randomizer._ShuffleCaveDestinationsSimple(
        first_quest_screens.copy(),
        cave_destinations.copy()
    )
    simple_elapsed = time.time() - start_time

    # Collect results from simple shuffle
    simple_results = {}
    for screen in first_quest_screens:
        simple_results[screen] = modifiable_data_table.GetScreenDestination(screen)
    simple_counts = Counter(simple_results.values())

    # Restore data table
    modifiable_data_table.overworld_raw_data = copy.deepcopy(saved_data_simple)

    # Test 2: Constraint-based shuffle
    random.seed(12345)
    start_time = time.time()
    overworld_randomizer._ShuffleCaveDestinationsWithConstraints(
        first_quest_screens.copy(),
        cave_destinations.copy(),
        "1st_quest"  # Mode parameter
    )
    constraint_elapsed = time.time() - start_time

    # Collect results from constraint shuffle
    constraint_results = {}
    for screen in first_quest_screens:
        constraint_results[screen] = modifiable_data_table.GetScreenDestination(screen)
    constraint_counts = Counter(constraint_results.values())

    # Print comparison
    print(f"\n{'='*80}")
    print("A/B Test: Simple Shuffle vs Constraint-Based Shuffle")
    print(f"{'='*80}")
    print(f"Simple shuffle:     {simple_elapsed*1000:.2f}ms")
    print(f"Constraint shuffle: {constraint_elapsed*1000:.2f}ms")
    print(f"Slowdown factor:    {constraint_elapsed/simple_elapsed:.1f}x")
    print(f"{'='*80}")

    # Verify both preserve cave counts
    assert simple_counts == original_counts, "Simple shuffle changed cave counts!"
    assert constraint_counts == original_counts, "Constraint shuffle changed cave counts!"

    # Both methods should produce valid shuffles (all screens have caves)
    assert len(simple_results) == len(first_quest_screens)
    assert len(constraint_results) == len(first_quest_screens)


def test_shuffle_preserves_cave_counts(modifiable_data_table, default_flags):
    """Test that shuffling preserves the count of each cave type."""
    flags = default_flags
    flags.shuffle_caves = True

    # Collect original cave destinations
    any_road_screens = modifiable_data_table.GetRomData(RomDataType.ANY_ROAD_SCREENS)
    original_caves = []

    for screen_num in range(0x80):
        table5_byte = modifiable_data_table.overworld_raw_data[screen_num + 5*0x80]
        if (table5_byte & 0x80) != 0:
            continue
        destination = modifiable_data_table.GetScreenDestination(screen_num)
        if destination != CaveType.NONE and screen_num not in any_road_screens:
            original_caves.append(destination)

    original_counts = Counter(original_caves)

    # Shuffle
    overworld_randomizer = OverworldRandomizer(modifiable_data_table, flags)
    overworld_randomizer.ShuffleCaveDestinations()

    # Collect shuffled cave destinations
    shuffled_caves = []
    for screen_num in range(0x80):
        table5_byte = modifiable_data_table.overworld_raw_data[screen_num + 5*0x80]
        if (table5_byte & 0x80) != 0:
            continue
        destination = modifiable_data_table.GetScreenDestination(screen_num)
        if destination != CaveType.NONE and screen_num not in any_road_screens:
            shuffled_caves.append(destination)

    shuffled_counts = Counter(shuffled_caves)

    # Verify counts match
    assert shuffled_counts == original_counts, "Shuffle changed cave type counts!"

    # Verify we still have the right duplicates
    assert shuffled_counts[CaveType.DOOR_REPAIR] == 9, "Should have 9 door repair caves"
    assert shuffled_counts[CaveType.POTION_SHOP] == 7, "Should have 7 potion shops"


def test_shuffle_deterministic(modifiable_data_table, default_flags):
    """Test that shuffling with same seed produces same result."""
    import random
    import copy

    flags = default_flags
    flags.shuffle_caves = True

    # Save original state
    original_data = copy.deepcopy(modifiable_data_table.overworld_raw_data)

    # First shuffle
    random.seed(42)
    overworld_randomizer = OverworldRandomizer(modifiable_data_table, flags)
    overworld_randomizer.ShuffleCaveDestinations()

    first_result = {}
    for screen_num in range(0x80):
        first_result[screen_num] = modifiable_data_table.GetScreenDestination(screen_num)

    # Restore and shuffle again with same seed
    modifiable_data_table.overworld_raw_data = copy.deepcopy(original_data)
    random.seed(42)
    overworld_randomizer = OverworldRandomizer(modifiable_data_table, flags)
    overworld_randomizer.ShuffleCaveDestinations()

    second_result = {}
    for screen_num in range(0x80):
        second_result[screen_num] = modifiable_data_table.GetScreenDestination(screen_num)

    # Verify they match
    assert first_result == second_result, "Same seed should produce same shuffle!"


def test_pin_wood_sword_cave_constraint(modifiable_data_table, default_flags):
    """Test that pin_wood_sword_cave flag keeps wood sword at screen 0x77."""
    import random

    flags = default_flags
    flags.shuffle_caves = True
    flags.pin_wood_sword_cave = True

    # Run shuffle with constraint
    random.seed(12345)
    overworld_randomizer = OverworldRandomizer(modifiable_data_table, flags)
    overworld_randomizer.ShuffleCaveDestinations()

    # Verify wood sword cave is at 0x77
    destination = modifiable_data_table.GetScreenDestination(0x77)
    assert destination == CaveType.WOOD_SWORD_CAVE, f"Wood Sword Cave should be at 0x77, but found {destination.name}"


def test_restrict_levels_to_vanilla_screens(modifiable_data_table, default_flags):
    """Test that restrict_levels_to_vanilla_screens keeps levels on vanilla screens."""
    import random
    from logic.overworld_randomizer import VANILLA_LEVEL_SCREENS

    flags = default_flags
    flags.shuffle_caves = True
    flags.restrict_levels_to_vanilla_screens = True

    # Run shuffle with constraint
    random.seed(12345)
    overworld_randomizer = OverworldRandomizer(modifiable_data_table, flags)
    overworld_randomizer.ShuffleCaveDestinations()

    # Find where levels ended up
    level_caves = [
        CaveType.LEVEL_1, CaveType.LEVEL_2, CaveType.LEVEL_3,
        CaveType.LEVEL_4, CaveType.LEVEL_5, CaveType.LEVEL_6,
        CaveType.LEVEL_7, CaveType.LEVEL_8, CaveType.LEVEL_9
    ]

    level_screens = []
    for screen_num in range(0x80):
        destination = modifiable_data_table.GetScreenDestination(screen_num)
        if destination in level_caves:
            level_screens.append(screen_num)

    # Verify all levels are on vanilla screens
    for screen in level_screens:
        assert screen in VANILLA_LEVEL_SCREENS, \
            f"Level found at screen {hex(screen)}, but should only be on vanilla screens: {[hex(s) for s in VANILLA_LEVEL_SCREENS]}"


def test_restrict_levels_to_expanded_screens(modifiable_data_table, default_flags):
    """Test that restrict_levels_to_expanded_screens keeps levels on expanded screen pool."""
    import random
    from logic.overworld_randomizer import EXPANDED_LEVEL_SCREENS

    flags = default_flags
    flags.shuffle_caves = True
    flags.restrict_levels_to_expanded_screens = True

    # Run shuffle with constraint
    random.seed(12345)
    overworld_randomizer = OverworldRandomizer(modifiable_data_table, flags)
    overworld_randomizer.ShuffleCaveDestinations()

    # Find where levels ended up
    level_caves = [
        CaveType.LEVEL_1, CaveType.LEVEL_2, CaveType.LEVEL_3,
        CaveType.LEVEL_4, CaveType.LEVEL_5, CaveType.LEVEL_6,
        CaveType.LEVEL_7, CaveType.LEVEL_8, CaveType.LEVEL_9
    ]

    level_screens = []
    for screen_num in range(0x80):
        destination = modifiable_data_table.GetScreenDestination(screen_num)
        if destination in level_caves:
            level_screens.append(screen_num)

    # Verify all levels are on expanded screens
    for screen in level_screens:
        assert screen in EXPANDED_LEVEL_SCREENS, \
            f"Level found at screen {hex(screen)}, but should only be on expanded screens: {[hex(s) for s in EXPANDED_LEVEL_SCREENS]}"

def test_examine_screen_0x00(vanilla_data_table, default_flags):
    """Examine screen 0x00 to see its quest bits and destination."""
    # Check screen 0x00 (should be 2nd quest level 9)
    first_quest_only, second_quest_only = vanilla_data_table.GetQuestBits(0x00)
    destination = vanilla_data_table.GetScreenDestination(0x00)
    destination_raw = vanilla_data_table.GetScreenDestinationRaw(0x00)

    print(f"\nScreen 0x00:")
    print(f"  first_quest_only bit (bit 6): {first_quest_only}")
    print(f"  second_quest_only bit (bit 7): {second_quest_only}")
    print(f"  GetScreenDestination(): {destination} ({destination.name if destination != CaveType.NONE else 'NONE'})")
    print(f"  GetScreenDestinationRaw(): {destination_raw} ({destination_raw.name if destination_raw != CaveType.NONE else 'NONE'})")

    # Verify the raw method returns LEVEL_9
    assert destination_raw == CaveType.LEVEL_9, f"Expected LEVEL_9, got {destination_raw.name}"
    assert second_quest_only == True, "Screen 0x00 should be marked as 2nd quest only"
    assert first_quest_only == False, "Screen 0x00 should not be marked as 1st quest only"

def test_collect_second_quest_screens(vanilla_data_table, default_flags):
    """Test that _CollectSecondQuestScreens returns the correct screens and destinations for vanilla ROM."""
    overworld_randomizer = OverworldRandomizer(vanilla_data_table, default_flags)

    # Collect second quest screens
    screens, destinations = overworld_randomizer._CollectSecondQuestScreens()

    # Print to see actual data
    print(f"\nActual screens ({len(screens)}): {[hex(s) for s in screens]}")
    dest_counts = Counter(destinations)
    print(f"\nDestination counts:")
    for cave_type, count in sorted(dest_counts.items(), key=lambda x: x[0].value):
        print(f"  {cave_type.name}: {count}")

    # Expected screens (updated with GetScreenDestinationRaw fix - now includes 2nd quest only screens)
    expected_screens = [
        0x0, 0x1, 0x2, 0x3, 0x4, 0x6, 0x7, 0x9, 0xa, 0xc, 0xd, 0xe, 0xf, 0x10,
        0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1e,
        0x1f, 0x20, 0x22, 0x25, 0x26, 0x28, 0x29, 0x2b, 0x2d, 0x2f, 0x30, 0x33,
        0x34, 0x37, 0x3a, 0x3c, 0x3d, 0x44, 0x45, 0x46, 0x48, 0x4a, 0x4b, 0x4d,
        0x4e, 0x51, 0x53, 0x56, 0x58, 0x5b, 0x5e, 0x60, 0x63, 0x64, 0x66, 0x68,
        0x6a, 0x6c, 0x6e, 0x6f, 0x70, 0x72, 0x74, 0x75, 0x76, 0x77, 0x78, 0x7c,
        0x7d
    ]

    # Expected destination counts (after applying 2nd quest patches)
    # Patches change some destinations, notably SHOP_2 increases from 4 to 6
    expected_dest_counts = {
        CaveType.LEVEL_1: 1,
        CaveType.LEVEL_2: 1,
        CaveType.LEVEL_3: 1,
        CaveType.LEVEL_4: 1,
        CaveType.LEVEL_5: 1,
        CaveType.LEVEL_6: 1,
        CaveType.LEVEL_7: 1,
        CaveType.LEVEL_8: 1,
        CaveType.LEVEL_9: 1,
        CaveType.WOOD_SWORD_CAVE: 1,
        CaveType.TAKE_ANY: 4,
        CaveType.WHITE_SWORD_CAVE: 1,
        CaveType.MAGICAL_SWORD_CAVE: 1,
        CaveType.LOST_HILLS_HINT: 1,
        CaveType.MONEY_MAKING_GAME: 6,
        CaveType.DOOR_REPAIR: 10,
        CaveType.LETTER_CAVE: 1,
        CaveType.DEAD_WOODS_HINT: 1,
        CaveType.POTION_SHOP: 9,
        CaveType.HINT_SHOP_1: 1,
        CaveType.HINT_SHOP_2: 1,
        CaveType.SHOP_1: 4,
        CaveType.SHOP_2: 6, 
        CaveType.SHOP_3: 4,
        CaveType.SHOP_4: 1,
        CaveType.MEDIUM_SECRET: 7,
        CaveType.LARGE_SECRET: 1,
        CaveType.SMALL_SECRET: 6,
    }

    # Verify the screen list matches expected
    assert screens == expected_screens, \
        f"Screen list doesn't match. Expected {len(expected_screens)}, got {len(screens)}"

    # Verify destination counts match expected
    dest_counts = Counter(destinations)
    assert dest_counts == expected_dest_counts, \
        f"Destination counts don't match. Expected {expected_dest_counts}, got {dest_counts}"

    # Verify lengths match (75 after excluding 0x0B and 0x42 via overrides)
    assert len(screens) == len(destinations) == 75, \
        f"Expected 75 screens and destinations, got {len(screens)} screens and {len(destinations)} destinations"

    # Verify all screens have correct quest bits (not marked as 1st quest only)
    for screen in screens:
        first_quest_only, second_quest_only = vanilla_data_table.GetQuestBits(screen)
        assert not first_quest_only, \
            f"Screen {hex(screen)} should not be marked as 1st quest only"

    # Verify all destinations are valid (not NONE)
    for dest in destinations:
        assert dest != CaveType.NONE, "Should not have NONE destinations in the list"


def test_collect_first_quest_screens(vanilla_data_table, default_flags):
    """Test that _CollectFirstQuestScreens returns the correct screens and destinations for vanilla ROM."""
    overworld_randomizer = OverworldRandomizer(vanilla_data_table, default_flags)

    # Collect first quest screens
    screens, destinations = overworld_randomizer._CollectFirstQuestScreens()

    # Print to see actual data
    print(f"\nActual screens ({len(screens)}): {[hex(s) for s in screens]}")
    dest_counts = Counter(destinations)
    print(f"\nDestination counts:")
    for cave_type, count in sorted(dest_counts.items(), key=lambda x: x[0].value):
        print(f"  {cave_type.name}: {count}")

    # Expected screens for first quest
    expected_screens = [
        0x1, 0x3, 0x4, 0x5, 0x7, 0xa, 0xb, 0xc, 0xd, 0xe, 0xf, 0x10, 0x12, 0x13,
        0x14, 0x16, 0x1a, 0x1c, 0x1e, 0x1f, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28,
        0x2c, 0x2d, 0x2f, 0x33, 0x34, 0x37, 0x3c, 0x3d, 0x42, 0x44, 0x45, 0x46,
        0x47, 0x48, 0x4a, 0x4b, 0x4d, 0x4e, 0x51, 0x56, 0x5b, 0x5e, 0x62, 0x63,
        0x64, 0x66, 0x67, 0x68, 0x6a, 0x6b, 0x6d, 0x6f, 0x70, 0x71, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x7b, 0x7c, 0x7d
    ]

    # Expected destination counts for first quest
    expected_dest_counts = {
        CaveType.LEVEL_1: 1,
        CaveType.LEVEL_2: 1,
        CaveType.LEVEL_3: 1,
        CaveType.LEVEL_4: 1,
        CaveType.LEVEL_5: 1,
        CaveType.LEVEL_6: 1,
        CaveType.LEVEL_7: 1,
        CaveType.LEVEL_8: 1,
        CaveType.LEVEL_9: 1,
        CaveType.WOOD_SWORD_CAVE: 1,
        CaveType.TAKE_ANY: 4,
        CaveType.WHITE_SWORD_CAVE: 1,
        CaveType.MAGICAL_SWORD_CAVE: 1,
        CaveType.LOST_HILLS_HINT: 1,
        CaveType.MONEY_MAKING_GAME: 5,
        CaveType.DOOR_REPAIR: 9,
        CaveType.LETTER_CAVE: 1,
        CaveType.DEAD_WOODS_HINT: 1,
        CaveType.POTION_SHOP: 7,
        CaveType.HINT_SHOP_1: 1,
        CaveType.HINT_SHOP_2: 1,
        CaveType.SHOP_1: 4,
        CaveType.SHOP_2: 3,
        CaveType.SHOP_3: 4,
        CaveType.SHOP_4: 1,
        CaveType.MEDIUM_SECRET: 7,
        CaveType.LARGE_SECRET: 3,
        CaveType.SMALL_SECRET: 4,
    }

    # Verify the screen list matches expected
    assert screens == expected_screens, \
        f"Screen list doesn't match. Expected {len(expected_screens)}, got {len(screens)}"

    # Verify destination counts match expected
    dest_counts = Counter(destinations)
    assert dest_counts == expected_dest_counts, \
        f"Destination counts don't match. Expected {expected_dest_counts}, got {dest_counts}"

    # Verify lengths match
    assert len(screens) == len(destinations) == 68, \
        f"Expected 68 screens and destinations, got {len(screens)} screens and {len(destinations)} destinations"

    # Verify all screens have correct quest bits (not marked as 2nd quest only)
    for screen in screens:
        first_quest_only, second_quest_only = vanilla_data_table.GetQuestBits(screen)
        assert not second_quest_only, \
            f"Screen {hex(screen)} should not be marked as 2nd quest only"

    # Verify all destinations are valid (not NONE)
    for dest in destinations:
        assert dest != CaveType.NONE, "Should not have NONE destinations in the list"


def test_collect_mixed_quest_screens(vanilla_data_table, default_flags):
    """Test that _CollectMixedQuestScreens returns the correct screens and destinations for vanilla ROM."""
    overworld_randomizer = OverworldRandomizer(vanilla_data_table, default_flags)

    # Collect mixed quest screens
    screens, destinations, both_quest_screens = overworld_randomizer._CollectMixedQuestScreens()

    # Print to see actual data
    print(f"\nActual total screens ({len(screens)}): {[hex(s) for s in screens]}")
    print(f"\nBoth quest screens ({len(both_quest_screens)}): {[hex(s) for s in both_quest_screens]}")
    dest_counts = Counter(destinations)
    print(f"\nDestination counts:")
    for cave_type, count in sorted(dest_counts.items(), key=lambda x: x[0].value):
        print(f"  {cave_type.name}: {count}")

    # Expected both quest screens (screens that appear in both quests)
    # Excludes 0x0B and 0x42 (marked as 1Q only via override)
    expected_both_quest_screens = [
        0x1, 0x3, 0x4, 0x7, 0xa, 0xc, 0xd, 0xe, 0xf, 0x10, 0x12, 0x13, 0x14,
        0x16, 0x1a, 0x1c, 0x1e, 0x1f, 0x22, 0x25, 0x26, 0x28, 0x2d, 0x2f, 0x33,
        0x34, 0x37, 0x3c, 0x3d, 0x44, 0x45, 0x46, 0x48, 0x4a, 0x4b, 0x4d,
        0x4e, 0x51, 0x56, 0x5b, 0x5e, 0x63, 0x64, 0x66, 0x68, 0x6a, 0x6f, 0x70,
        0x74, 0x75, 0x76, 0x77, 0x78, 0x7c, 0x7d
    ]

    # Expected total screens (all screens from both quests, sorted numerically)
    expected_total_screens = [
        0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x9, 0xa, 0xb, 0xc, 0xd, 0xe,
        0xf, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x18, 0x19, 0x1a, 0x1b,
        0x1c, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2b,
        0x2c, 0x2d, 0x2f, 0x30, 0x33, 0x34, 0x37, 0x3a, 0x3c, 0x3d, 0x42, 0x44,
        0x45, 0x46, 0x47, 0x48, 0x4a, 0x4b, 0x4d, 0x4e, 0x51, 0x53, 0x56, 0x58,
        0x5b, 0x5e, 0x60, 0x62, 0x63, 0x64, 0x66, 0x67, 0x68, 0x6a, 0x6b, 0x6c,
        0x6d, 0x6e, 0x6f, 0x70, 0x71, 0x72, 0x74, 0x75, 0x76, 0x77, 0x78, 0x7b,
        0x7c, 0x7d
    ]

    # Expected destination counts (same as first quest, since destinations come from 1Q)
    expected_dest_counts = {
        CaveType.LEVEL_1: 1,
        CaveType.LEVEL_2: 1,
        CaveType.LEVEL_3: 1,
        CaveType.LEVEL_4: 1,
        CaveType.LEVEL_5: 1,
        CaveType.LEVEL_6: 1,
        CaveType.LEVEL_7: 1,
        CaveType.LEVEL_8: 1,
        CaveType.LEVEL_9: 1,
        CaveType.WOOD_SWORD_CAVE: 1,
        CaveType.TAKE_ANY: 4,
        CaveType.WHITE_SWORD_CAVE: 1,
        CaveType.MAGICAL_SWORD_CAVE: 1,
        CaveType.LOST_HILLS_HINT: 1,
        CaveType.MONEY_MAKING_GAME: 5,
        CaveType.DOOR_REPAIR: 9,
        CaveType.LETTER_CAVE: 1,
        CaveType.DEAD_WOODS_HINT: 1,
        CaveType.POTION_SHOP: 7,
        CaveType.HINT_SHOP_1: 1,
        CaveType.HINT_SHOP_2: 1,
        CaveType.SHOP_1: 4,
        CaveType.SHOP_2: 3,
        CaveType.SHOP_3: 4,
        CaveType.SHOP_4: 1,
        CaveType.MEDIUM_SECRET: 7,
        CaveType.LARGE_SECRET: 3,
        CaveType.SMALL_SECRET: 4,
    }

    # Verify the both quest screen list matches expected
    assert both_quest_screens == expected_both_quest_screens, \
        f"Both quest screen list doesn't match. Expected {len(expected_both_quest_screens)}, got {len(both_quest_screens)}"

    # Verify the total screen list matches expected
    assert screens == expected_total_screens, \
        f"Total screen list doesn't match. Expected {len(expected_total_screens)}, got {len(screens)}"

    # Verify destination counts match expected
    dest_counts = Counter(destinations)
    assert dest_counts == expected_dest_counts, \
        f"Destination counts don't match. Expected {expected_dest_counts}, got {dest_counts}"

    # Verify lengths match (86 total after excluding 0x0B and 0x42 from both quests)
    assert len(screens) == 88, \
        f"Expected 88 total screens, got {len(screens)}"
    assert len(both_quest_screens) == 55, \
        f"Expected 55 both quest screens (excludes 0x0B, 0x42), got {len(both_quest_screens)}"
    assert len(destinations) == 68, \
        f"Expected 68 destinations (from 1Q), got {len(destinations)}"

    # Verify all destinations are valid (not NONE)
    for dest in destinations:
        assert dest != CaveType.NONE, "Should not have NONE destinations in the list"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
