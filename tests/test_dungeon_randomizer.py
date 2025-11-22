"""
Test script for the DungeonRandomizer and DungeonLayoutGenerator.
Tests the region-growing algorithm directly without needing a ROM file.
"""
import sys
import os

# Add logic directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rng.random_number_generator import RandomNumberGenerator
from logic.dungeons.dungeon_randomizer import (
    DungeonLayoutGenerator,
    DungeonRegion,
    room_to_coords,
    coords_to_room,
    get_adjacent_rooms,
    calculate_max_rooms,
    GRID_ROWS,
    GRID_COLS,
    TOTAL_ROOMS,
    BOTTOM_ROW,
    MIN_ROOMS_PER_LEVEL,
    MAX_REGION_WIDTH,
)


def test_coordinate_conversion():
    """Test room_to_coords and coords_to_room functions."""
    print("\n=== Testing Coordinate Conversion ===")

    # Test some known values
    test_cases = [
        (0x00, (0, 0)),   # Top-left
        (0x0F, (0, 15)),  # Top-right
        (0x70, (7, 0)),   # Bottom-left
        (0x7F, (7, 15)),  # Bottom-right
        (0x35, (3, 5)),   # Middle
    ]

    all_passed = True
    for room_num, expected_coords in test_cases:
        coords = room_to_coords(room_num)
        if coords != expected_coords:
            print(f"  FAIL: room_to_coords(0x{room_num:02X}) = {coords}, expected {expected_coords}")
            all_passed = False

        # Test reverse
        back_to_room = coords_to_room(*expected_coords)
        if back_to_room != room_num:
            print(f"  FAIL: coords_to_room{expected_coords} = 0x{back_to_room:02X}, expected 0x{room_num:02X}")
            all_passed = False

    if all_passed:
        print("  PASS: All coordinate conversions correct")
    return all_passed


def test_adjacent_rooms():
    """Test get_adjacent_rooms function."""
    print("\n=== Testing Adjacent Rooms ===")

    all_passed = True

    # Corner room - should have 2 neighbors
    corner_adj = get_adjacent_rooms(0x00)
    if len(corner_adj) != 2:
        print(f"  FAIL: Corner room 0x00 should have 2 neighbors, got {len(corner_adj)}")
        all_passed = False

    # Edge room - should have 3 neighbors
    edge_adj = get_adjacent_rooms(0x08)  # Middle of top row
    if len(edge_adj) != 3:
        print(f"  FAIL: Edge room 0x08 should have 3 neighbors, got {len(edge_adj)}")
        all_passed = False

    # Middle room - should have 4 neighbors
    middle_adj = get_adjacent_rooms(0x35)
    if len(middle_adj) != 4:
        print(f"  FAIL: Middle room 0x35 should have 4 neighbors, got {len(middle_adj)}")
        all_passed = False

    if all_passed:
        print("  PASS: All adjacent room tests correct")
    return all_passed


def test_region_contiguity():
    """Test DungeonRegion.is_contiguous method."""
    print("\n=== Testing Region Contiguity ===")

    all_passed = True

    # Test contiguous region
    region1 = DungeonRegion(1, 0x70)
    region1.add_room(0x71)
    region1.add_room(0x60)  # Above 0x70
    if not region1.is_contiguous():
        print("  FAIL: Contiguous region marked as non-contiguous")
        all_passed = False

    # Test non-contiguous region (manually add disconnected room)
    region2 = DungeonRegion(2, 0x70)
    region2.rooms.add(0x00)  # Disconnected room
    if region2.is_contiguous():
        print("  FAIL: Non-contiguous region marked as contiguous")
        all_passed = False

    if all_passed:
        print("  PASS: All contiguity tests correct")
    return all_passed


def test_region_width_constraint():
    """Test that region width constraint is enforced."""
    print("\n=== Testing Region Width Constraint ===")

    region = DungeonRegion(1, 0x70)  # Column 0

    # Should be able to add rooms within 8 columns
    can_add_col7 = region.can_add_room(0x77)  # Column 7, same row
    if not can_add_col7:
        print("  FAIL: Should be able to add room in column 7")
        return False

    # Add a room to make width 8
    region.add_room(0x77)

    # Should NOT be able to add room in column 8 (would make width 9)
    can_add_col8 = region.can_add_room(0x78)
    if can_add_col8:
        print("  FAIL: Should NOT be able to add room that exceeds width 8")
        return False

    print("  PASS: Width constraint working correctly")
    return True


def test_layout_generator_6_regions(seed=12345):
    """Test generating a layout with 6 regions (for levels 1-6)."""
    print(f"\n=== Testing Layout Generator with 6 Regions (seed={seed}) ===")

    rng = RandomNumberGenerator(seed)
    generator = DungeonLayoutGenerator(num_regions=6, rng=rng)
    max_rooms = generator.max_rooms_per_region

    success = generator.generate()
    if not success:
        print("  FAIL: Layout generation failed")
        return False

    # Verify all rooms are assigned
    assignments = generator.get_room_assignments()
    if len(assignments) != TOTAL_ROOMS:
        print(f"  FAIL: Only {len(assignments)} rooms assigned, expected {TOTAL_ROOMS}")
        return False

    # Verify each region meets constraints
    for region in generator.regions:
        # Size constraint
        if region.size() < MIN_ROOMS_PER_LEVEL or region.size() > max_rooms:
            print(f"  FAIL: Region {region.level_num} has size {region.size()}, "
                  f"expected {MIN_ROOMS_PER_LEVEL}-{max_rooms}")
            return False

        # Width constraint
        if region.get_width() > MAX_REGION_WIDTH:
            print(f"  FAIL: Region {region.level_num} has width {region.get_width()}, "
                  f"max is {MAX_REGION_WIDTH}")
            return False

        # Contiguity
        if not region.is_contiguous():
            print(f"  FAIL: Region {region.level_num} is not contiguous")
            return False

        # Bottom row entry
        has_bottom_room = any(room in BOTTOM_ROW for room in region.rooms)
        if not has_bottom_room:
            print(f"  FAIL: Region {region.level_num} has no room in bottom row")
            return False

    # Print region info
    print(f"  Layout generated successfully (max rooms per region: {max_rooms}):")
    for region in generator.regions:
        print(f"    Level {region.level_num}: {region.size()} rooms, "
              f"width {region.get_width()}, start=0x{region.start_room:02X}")

    print("  PASS: 6-region layout meets all constraints")
    return True


def test_layout_generator_3_regions(seed=12345):
    """Test generating a layout with 3 regions (for levels 7-9)."""
    print(f"\n=== Testing Layout Generator with 3 Regions (seed={seed}) ===")

    rng = RandomNumberGenerator(seed)
    generator = DungeonLayoutGenerator(num_regions=3, rng=rng)
    max_rooms = generator.max_rooms_per_region

    success = generator.generate()
    if not success:
        print("  FAIL: Layout generation failed")
        return False

    # Verify all rooms are assigned
    assignments = generator.get_room_assignments()
    if len(assignments) != TOTAL_ROOMS:
        print(f"  FAIL: Only {len(assignments)} rooms assigned, expected {TOTAL_ROOMS}")
        return False

    # Verify each region meets constraints
    for region in generator.regions:
        # Size constraint (with 3 regions, sizes will be larger)
        if region.size() < MIN_ROOMS_PER_LEVEL or region.size() > max_rooms:
            print(f"  FAIL: Region {region.level_num} has size {region.size()}, "
                  f"expected {MIN_ROOMS_PER_LEVEL}-{max_rooms}")
            return False

        # Width constraint
        if region.get_width() > MAX_REGION_WIDTH:
            print(f"  FAIL: Region {region.level_num} has width {region.get_width()}, "
                  f"max is {MAX_REGION_WIDTH}")
            return False

        # Contiguity
        if not region.is_contiguous():
            print(f"  FAIL: Region {region.level_num} is not contiguous")
            return False

        # Bottom row entry
        has_bottom_room = any(room in BOTTOM_ROW for room in region.rooms)
        if not has_bottom_room:
            print(f"  FAIL: Region {region.level_num} has no room in bottom row")
            return False

    # Print region info
    print(f"  Layout generated successfully (max rooms per region: {max_rooms}):")
    for region in generator.regions:
        print(f"    Level {region.level_num}: {region.size()} rooms, "
              f"width {region.get_width()}, start=0x{region.start_room:02X}")

    print("  PASS: 3-region layout meets all constraints")
    return True


def test_multiple_seeds():
    """Test layout generation with multiple seeds for robustness."""
    print("\n=== Testing Multiple Seeds ===")

    test_seeds = [1, 42, 12345, 99999, 7777777]
    all_passed = True

    for seed in test_seeds:
        rng = RandomNumberGenerator(seed)

        # Test 6 regions
        gen6 = DungeonLayoutGenerator(num_regions=6, rng=rng)
        if not gen6.generate():
            print(f"  FAIL: 6-region generation failed for seed {seed}")
            all_passed = False
            continue

        # Test 3 regions
        rng2 = RandomNumberGenerator(seed)  # Reset RNG
        gen3 = DungeonLayoutGenerator(num_regions=3, rng=rng2)
        if not gen3.generate():
            print(f"  FAIL: 3-region generation failed for seed {seed}")
            all_passed = False
            continue

        print(f"  Seed {seed}: 6-region sizes = {[r.size() for r in gen6.regions]}, "
              f"3-region sizes = {[r.size() for r in gen3.regions]}")

    if all_passed:
        print("  PASS: All seeds generated valid layouts")
    return all_passed


def visualize_layout(generator: DungeonLayoutGenerator):
    """Print a visual representation of the layout."""
    print("\n  Layout visualization (level numbers):")
    assignments = generator.get_room_assignments()

    for row in range(GRID_ROWS):
        line = "  "
        for col in range(GRID_COLS):
            room = coords_to_room(row, col)
            level = assignments.get(room, 0)
            line += f"{level:X} "
        print(line)


def main():
    """Run all tests."""
    print("=" * 70)
    print("DUNGEON RANDOMIZER TESTS")
    print("=" * 70)

    tests = [
        test_coordinate_conversion,
        test_adjacent_rooms,
        test_region_contiguity,
        test_region_width_constraint,
        test_layout_generator_6_regions,
        test_layout_generator_3_regions,
        test_multiple_seeds,
    ]

    all_passed = True
    for test in tests:
        try:
            if not test():
                all_passed = False
        except Exception as e:
            print(f"  ERROR in {test.__name__}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    # Show a sample visualization
    print("\n=== Sample Layout Visualization ===")
    rng = RandomNumberGenerator(42)
    gen = DungeonLayoutGenerator(num_regions=6, rng=rng)
    gen.generate()
    visualize_layout(gen)

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
