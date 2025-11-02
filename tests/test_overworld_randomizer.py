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
        cave_destinations.copy()
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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
