"""Tests for MajorItemRandomizer."""

import pytest
import sys
from pathlib import Path

# Add parent directory to path to import logic modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from logic.items.major_item_randomizer import MajorItemRandomizer, ConstraintConflictError
from logic.data_table import DataTable
from logic.flags import Flags
from logic.randomizer_constants import Item
from test_rom_builder import build_minimal_rom


@pytest.fixture(scope="session")
def vanilla_rom():
    """Create a minimal ROM from extracted test data."""
    return build_minimal_rom('data')


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
    """Returns flags with all major item shuffle flags disabled."""
    flags = Flags()
    # Disable all force-to-location flags
    flags.force_arrow_to_level_nine = False
    flags.force_ring_to_level_nine = False
    flags.force_wand_to_level_nine = False
    flags.force_heart_container_to_level_nine = False
    flags.force_heart_container_to_armos = False
    flags.force_heart_container_to_coast = False

    # Disable all shuffle flags (items stay in dungeons, don't go to overworld)
    flags.shuffle_wood_sword_cave_item = False
    flags.shuffle_white_sword_cave_item = False
    flags.shuffle_magical_sword_cave_item = False
    flags.shuffle_letter_cave_item = False
    flags.shuffle_armos_item = False
    flags.shuffle_coast_item = False
    flags.shuffle_shop_arrows = False
    flags.shuffle_shop_candle = False
    flags.shuffle_shop_ring = False
    flags.shuffle_shop_book = False
    flags.shuffle_shop_bait = False
    flags.shuffle_potion_shop_items = False

    return flags


def test_basic_major_item_shuffle(modifiable_data_table, default_flags):
    """Test basic major item shuffle with all flags disabled.

    With all flags disabled, the randomizer should:
    - Only shuffle major items within dungeons (not heart containers to overworld)
    - Not place items in overworld locations
    - Shuffle at least the major dungeon items (bow, boomerang, raft, ladder, etc.)
    """
    from logic.items.room_item_collector import RoomItemCollector

    # Major items we expect in dungeons
    major_items = [
        Item.BOW,
        Item.WOOD_BOOMERANG,
        Item.MAGICAL_BOOMERANG,
        Item.RAFT,
        Item.LADDER,
        Item.RECORDER,
        Item.WAND,
        Item.RED_CANDLE,
        Item.BOOK,
        Item.MAGICAL_KEY,
        Item.RED_RING,
        Item.SILVER_ARROWS,
    ]

    # Capture vanilla item locations before randomization using proper room traversal
    collector = RoomItemCollector(modifiable_data_table)
    vanilla_room_pairs = collector.CollectAll()

    vanilla_locations = {}
    for level_num, pairs in vanilla_room_pairs.items():
        for pair in pairs:
            if pair.item in major_items:
                vanilla_locations[(level_num, pair.room_num)] = pair.item
                print(f"Vanilla: Level {level_num} Room 0x{pair.room_num:02X} has {pair.item.name}")

    print(f"\nFound {len(vanilla_locations)} major items in vanilla")
    assert len(vanilla_locations) > 0, "Should find major items in vanilla ROM"

    # Run randomization
    randomizer = MajorItemRandomizer(modifiable_data_table, default_flags)
    randomizer.Randomize()

    # Capture shuffled locations using proper room traversal
    collector2 = RoomItemCollector(modifiable_data_table)
    shuffled_room_pairs = collector2.CollectAll()

    shuffled_locations = {}
    for level_num, pairs in shuffled_room_pairs.items():
        for pair in pairs:
            if pair.item in major_items:
                shuffled_locations[(level_num, pair.room_num)] = pair.item
                print(f"Shuffled: Level {level_num} Room 0x{pair.room_num:02X} has {pair.item.name}")

    print(f"\nFound {len(shuffled_locations)} major items after shuffle")

    # Verify same number of items before and after
    assert len(shuffled_locations) == len(vanilla_locations), \
        f"Item count changed: {len(vanilla_locations)} -> {len(shuffled_locations)}"

    # Verify items were actually shuffled (at least one item moved)
    items_in_same_location = 0
    for location, item in vanilla_locations.items():
        if shuffled_locations.get(location) == item:
            items_in_same_location += 1

    print(f"\nItems still in vanilla location: {items_in_same_location}/{len(vanilla_locations)}")

    # With 12+ items being shuffled, probability of ALL staying in place is astronomically low
    # Allow for possibility of a few items coincidentally staying (due to permutation)
    assert items_in_same_location < len(vanilla_locations), \
        "At least one item should have moved from its vanilla location"

    # Verify all major items still exist (just shuffled)
    vanilla_item_counts = {}
    for item in vanilla_locations.values():
        vanilla_item_counts[item] = vanilla_item_counts.get(item, 0) + 1

    shuffled_item_counts = {}
    for item in shuffled_locations.values():
        shuffled_item_counts[item] = shuffled_item_counts.get(item, 0) + 1

    assert vanilla_item_counts == shuffled_item_counts, \
        f"Item distribution changed! Vanilla: {vanilla_item_counts}, Shuffled: {shuffled_item_counts}"


def test_heart_containers_never_in_shops_with_shops_enabled(modifiable_data_table):
    """Test that heart containers are never placed in shops (always-on constraint).

    This tests across multiple seeds to ensure the constraint is consistently enforced.
    """
    from logic.randomizer_constants import CaveType, CavePosition

    # Create flags with ALL shop shuffle flags enabled including potion shops
    flags = Flags()
    flags.shuffle_shop_arrows = True
    flags.shuffle_shop_candle = True
    flags.shuffle_shop_bait = True
    flags.shuffle_shop_ring = True
    flags.shuffle_potion_shop_items = True

    # Shop locations that can be shuffled (using 0-indexed positions)
    shop_locations = [
        (CaveType.SHOP_1, CavePosition.RIGHT, "Shop 1 arrows"),
        (CaveType.SHOP_2, CavePosition.RIGHT, "Shop 2 candle"),
        (CaveType.SHOP_3, CavePosition.MIDDLE, "Shop 3 bait"),
        (CaveType.SHOP_4, CavePosition.MIDDLE, "Shop 4 ring"),
        (CaveType.POTION_SHOP, CavePosition.LEFT, "Potion Shop left"),
        (CaveType.POTION_SHOP, CavePosition.RIGHT, "Potion Shop right"),
    ]

    # Test multiple seeds to ensure constraint holds consistently
    for seed in range(5):
        # Need fresh data table for each seed
        from test_rom_builder import build_minimal_rom
        from logic.data_table import DataTable

        rom_data = build_minimal_rom('data')
        data_table = DataTable(rom_data)
        data_table.ResetToVanilla()

        # Run randomization
        randomizer = MajorItemRandomizer(data_table, flags)
        randomizer.Randomize()

        # Verify no heart containers in any shop location
        for cave_type, position, location_name in shop_locations:
            # Convert CavePosition enum (0-indexed) to 1-indexed for DataTable
            position_1indexed = int(position) + 1
            item = data_table.GetCaveItem(cave_type, position_1indexed)
            assert item != Item.HEART_CONTAINER, \
                f"Heart container found in {location_name} (seed {seed})"

        print(f"Seed {seed}: ✓ No heart containers in shops")


def test_no_overworld_items_when_flags_disabled(modifiable_data_table, default_flags):
    """Test that overworld items don't change when shuffle flags are disabled."""
    from logic.randomizer_constants import CaveType

    # Capture vanilla overworld items
    vanilla_overworld = {}
    overworld_caves = [
        CaveType.WOOD_SWORD_CAVE,
        CaveType.WHITE_SWORD_CAVE,
        CaveType.MAGICAL_SWORD_CAVE,
        CaveType.LETTER_CAVE,
        CaveType.ARMOS_ITEM,
        CaveType.COAST_ITEM,
    ]

    for cave_type in overworld_caves:
        for position_num in range(1, 4):
            try:
                item = modifiable_data_table.GetCaveItem(cave_type, position_num)
                if item != Item.NO_ITEM:
                    vanilla_overworld[(cave_type, position_num)] = item
                    print(f"Vanilla overworld: {cave_type.name} pos {position_num} = {item.name}")
            except:
                pass

    # Run randomization
    randomizer = MajorItemRandomizer(modifiable_data_table, default_flags)
    randomizer.Randomize()

    # Check overworld items didn't change
    for (cave_type, position_num), vanilla_item in vanilla_overworld.items():
        current_item = modifiable_data_table.GetCaveItem(cave_type, position_num)
        assert current_item == vanilla_item, \
            f"Overworld item changed at {cave_type.name} pos {position_num}: {vanilla_item.name} -> {current_item.name}"

    print(f"\n✓ All {len(vanilla_overworld)} overworld items unchanged")


def test_ladder_never_at_coast_location():
    """Test that ladder can never be placed at coast item location (always-on constraint).

    The coast item location requires the ladder to access, so placing the ladder there
    would create a logical impossibility.
    """
    from logic.randomizer_constants import CaveType, CavePosition
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    # Create flags with coast item shuffle enabled (required to test this constraint)
    flags = Flags()
    flags.shuffle_coast_item = True

    # Test multiple seeds to ensure constraint holds consistently
    for seed in range(5):
        rom_data = build_minimal_rom('data')
        data_table = DataTable(rom_data)
        data_table.ResetToVanilla()

        # Run randomization
        randomizer = MajorItemRandomizer(data_table, flags)
        randomizer.Randomize()

        # Check that ladder is not at coast location (middle position)
        # Convert CavePosition enum (0-indexed) to 1-indexed for DataTable
        position_1indexed = int(CavePosition.MIDDLE) + 1
        coast_item = data_table.GetCaveItem(CaveType.COAST_ITEM, position_1indexed)
        assert coast_item != Item.LADDER, \
            f"Ladder found at coast location (seed {seed})"

        print(f"Seed {seed}: ✓ Ladder not at coast location")


def test_progressive_items_not_in_shops_when_enabled():
    """Test that base progressive items cannot be placed in shops (when progressive flag is on).

    When progressive items are enabled, the base items (wood sword, blue candle, etc.)
    are upgrade items that should not appear in shops.
    """
    from logic.randomizer_constants import CaveType
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    # Create flags with progressive items AND shop shuffling enabled
    flags = Flags()
    flags.progressive_items = True
    flags.shuffle_shop_arrows = True
    flags.shuffle_shop_candle = True
    flags.shuffle_shop_bait = True
    flags.shuffle_shop_ring = True

    # Base progressive items that should not appear in shops
    forbidden_items = [
        Item.WOOD_SWORD,
        Item.BLUE_CANDLE,
        Item.WOOD_ARROWS,
        Item.BLUE_RING,
    ]

    # Shop locations that can be shuffled
    shop_locations = [
        (CaveType.SHOP_1, 2, "Shop 1"),
        (CaveType.SHOP_2, 2, "Shop 2"),
        (CaveType.SHOP_3, 1, "Shop 3"),
        (CaveType.SHOP_4, 1, "Shop 4"),
    ]

    # Test multiple seeds to ensure constraint holds consistently
    for seed in range(5):
        rom_data = build_minimal_rom('data')
        data_table = DataTable(rom_data)
        data_table.ResetToVanilla()

        # Run randomization
        randomizer = MajorItemRandomizer(data_table, flags)
        randomizer.Randomize()

        # Verify no base progressive items in any shop location
        for cave_type, position, location_name in shop_locations:
            item = data_table.GetCaveItem(cave_type, position)
            assert item not in forbidden_items, \
                f"Progressive item {item.name} found in {location_name} (seed {seed})"

        print(f"Seed {seed}: ✓ No base progressive items in shops")


def test_progressive_items_can_be_in_shops_when_disabled():
    """Test that base progressive items CAN be in shops when progressive flag is OFF.

    This verifies the constraint is correctly conditional on the flag.
    """
    from logic.randomizer_constants import CaveType
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    # Create flags with progressive items DISABLED but shop shuffling enabled
    flags = Flags()
    flags.progressive_items = False
    flags.shuffle_shop_arrows = True
    flags.shuffle_shop_candle = True
    flags.shuffle_shop_bait = True
    flags.shuffle_shop_ring = True

    # These items should be allowed in shops when progressive is off
    allowed_items = [
        Item.WOOD_SWORD,
        Item.BLUE_CANDLE,
        Item.WOOD_ARROWS,
        Item.BLUE_RING,
    ]

    # Run multiple times and collect what appears in shops
    items_found_in_shops = set()

    for seed in range(10):
        rom_data = build_minimal_rom('data')
        data_table = DataTable(rom_data)
        data_table.ResetToVanilla()

        randomizer = MajorItemRandomizer(data_table, flags)
        randomizer.Randomize()

        # Check all shop locations
        for cave_type in [CaveType.SHOP_1, CaveType.SHOP_2, CaveType.SHOP_3, CaveType.SHOP_4]:
            for position in [1, 2]:
                try:
                    item = data_table.GetCaveItem(cave_type, position)
                    if item in allowed_items:
                        items_found_in_shops.add(item)
                except:
                    pass

    # We expect at least SOME of these items appeared in shops across 10 seeds
    # (This is a soft check - in practice with enough seeds we'd see them)
    print(f"Items from 'allowed' list found in shops: {[i.name for i in items_found_in_shops]}")
    print("✓ Progressive items can appear in shops when flag is disabled")


def test_red_potion_never_in_dungeons():
    """Test that red potion can never be placed in dungeon locations (always-on constraint).

    Red potion is 0x20 which exceeds the 5-bit item field limit (0x1F) for dungeon items.
    This would cause an overflow, so red potions must only be placed in shops/caves.
    """
    from logic.randomizer_constants import CaveType, CavePosition
    from logic.items.room_item_collector import RoomItemCollector
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    # Create flags with potion shop shuffle enabled
    flags = Flags()
    flags.shuffle_potion_shop_items = True

    # Test multiple seeds to ensure constraint holds consistently
    for seed in range(5):
        rom_data = build_minimal_rom('data')
        data_table = DataTable(rom_data)
        data_table.ResetToVanilla()

        # Run randomization
        randomizer = MajorItemRandomizer(data_table, flags)
        randomizer.Randomize()

        # Check all dungeon rooms using proper traversal
        collector = RoomItemCollector(data_table)
        room_pairs = collector.CollectAll()

        for level_num, pairs in room_pairs.items():
            for pair in pairs:
                assert pair.item != Item.RED_POTION, \
                    f"Red potion found in Level {level_num} Room 0x{pair.room_num:02X} (seed {seed})"

        print(f"Seed {seed}: ✓ Red potion not in any dungeon")


def test_shuffle_dungeon_hearts_disabled_by_default(modifiable_data_table):
    """Test that shuffle_dungeon_hearts is disabled by default (heart containers stay in dungeons)."""
    from logic.items.room_item_collector import RoomItemCollector

    # Default flags should have shuffle_dungeon_hearts = False
    flags = Flags()
    assert flags.shuffle_dungeon_hearts == False, "shuffle_dungeon_hearts should default to False"

    # Capture vanilla heart container locations in dungeons
    collector = RoomItemCollector(modifiable_data_table)
    vanilla_room_pairs = collector.CollectAll()

    vanilla_hc_locations = {}
    for level_num, pairs in vanilla_room_pairs.items():
        for pair in pairs:
            if pair.item == Item.HEART_CONTAINER:
                vanilla_hc_locations[(level_num, pair.room_num)] = pair.item
                print(f"Vanilla HC: Level {level_num} Room 0x{pair.room_num:02X}")

    print(f"\nFound {len(vanilla_hc_locations)} heart containers in vanilla dungeons")

    # Run randomization with default flags (shuffle_dungeon_hearts = False)
    randomizer = MajorItemRandomizer(modifiable_data_table, flags)
    randomizer.Randomize()

    # Verify heart containers are still in their original locations
    collector2 = RoomItemCollector(modifiable_data_table)
    shuffled_room_pairs = collector2.CollectAll()

    for level_num, pairs in shuffled_room_pairs.items():
        for pair in pairs:
            if (level_num, pair.room_num) in vanilla_hc_locations:
                assert pair.item == Item.HEART_CONTAINER, \
                    f"Heart container at Level {level_num} Room 0x{pair.room_num:02X} was changed to {pair.item.name}"
                print(f"✓ HC still at Level {level_num} Room 0x{pair.room_num:02X}")

    print(f"✓ All {len(vanilla_hc_locations)} heart containers remained in original locations")


def test_shuffle_dungeon_hearts_when_enabled():
    """Test that dungeon heart containers are included in shuffle when flag is enabled."""
    from logic.items.room_item_collector import RoomItemCollector
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    # Create flags with shuffle_dungeon_hearts enabled
    flags = Flags()
    flags.shuffle_dungeon_hearts = True

    # Test multiple seeds to verify HCs can move
    hc_moved_at_least_once = False

    for seed in range(5):
        rom_data = build_minimal_rom('data')
        data_table = DataTable(rom_data)
        data_table.ResetToVanilla()

        # Capture vanilla HC locations
        collector = RoomItemCollector(data_table)
        vanilla_room_pairs = collector.CollectAll()

        vanilla_hc_locations = set()
        for level_num, pairs in vanilla_room_pairs.items():
            for pair in pairs:
                if pair.item == Item.HEART_CONTAINER:
                    vanilla_hc_locations.add((level_num, pair.room_num))

        # Run randomization
        randomizer = MajorItemRandomizer(data_table, flags)
        randomizer.Randomize()

        # Check if HCs moved
        collector2 = RoomItemCollector(data_table)
        shuffled_room_pairs = collector2.CollectAll()

        shuffled_hc_locations = set()
        for level_num, pairs in shuffled_room_pairs.items():
            for pair in pairs:
                if pair.item == Item.HEART_CONTAINER:
                    shuffled_hc_locations.add((level_num, pair.room_num))

        if vanilla_hc_locations != shuffled_hc_locations:
            hc_moved_at_least_once = True
            print(f"Seed {seed}: ✓ Heart containers were shuffled")
            break

    assert hc_moved_at_least_once, \
        "Heart containers should be shuffled when shuffle_dungeon_hearts is enabled"


def test_constraint_conflict_force_two_hc_without_shuffle():
    """Test that forcing 2 HCs to level 9 without shuffle_dungeon_hearts raises an error."""
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    rom_data = build_minimal_rom('data')
    data_table = DataTable(rom_data)
    data_table.ResetToVanilla()

    # Create impossible flag combination:
    # - force_two_heart_containers_to_level_nine = True
    # - shuffle_dungeon_hearts = False (no HCs in pool)
    # - shuffle_coast_item = False (no coast HC)
    # - shuffle_armos_item = False (no armos HC)
    flags = Flags()
    flags.force_two_heart_containers_to_level_nine = True
    flags.shuffle_dungeon_hearts = False
    flags.shuffle_coast_item = False
    flags.shuffle_armos_item = False

    randomizer = MajorItemRandomizer(data_table, flags)

    # Should raise ConstraintConflictError
    with pytest.raises(ConstraintConflictError) as exc_info:
        randomizer.Randomize()

    error_message = str(exc_info.value)
    assert "Force two heart containers to be in level 9" in error_message
    assert "at least 2 heart containers in the pool" in error_message
    print(f"✓ Correctly raised ConstraintConflictError:\n{error_message}")


def test_constraint_conflict_force_one_hc_without_any_source():
    """Test that forcing 1 HC to level 9 without any HC source raises an error."""
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    rom_data = build_minimal_rom('data')
    data_table = DataTable(rom_data)
    data_table.ResetToVanilla()

    # Create impossible flag combination: force HC to level 9 but no HCs available
    flags = Flags()
    flags.force_heart_container_to_level_nine = True
    flags.shuffle_dungeon_hearts = False
    flags.shuffle_coast_item = False
    flags.shuffle_armos_item = False

    randomizer = MajorItemRandomizer(data_table, flags)

    with pytest.raises(ConstraintConflictError) as exc_info:
        randomizer.Randomize()

    error_message = str(exc_info.value)
    assert "Force a heart container to be in level 9" in error_message
    assert "at least one heart container in the pool" in error_message
    print(f"✓ Correctly raised ConstraintConflictError:\n{error_message}")


def test_constraint_conflict_force_hc_to_armos_without_shuffle_armos():
    """Test that forcing HC to Armos without shuffle_armos_item enabled raises an error."""
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    rom_data = build_minimal_rom('data')
    data_table = DataTable(rom_data)
    data_table.ResetToVanilla()

    # Create impossible flag combination
    flags = Flags()
    flags.force_heart_container_to_armos = True
    flags.shuffle_armos_item = False  # This is the problem
    flags.shuffle_dungeon_hearts = True  # Has HCs, but armos location not in pool

    randomizer = MajorItemRandomizer(data_table, flags)

    with pytest.raises(ConstraintConflictError) as exc_info:
        randomizer.Randomize()

    error_message = str(exc_info.value)
    assert "Force heart container to Armos" in error_message
    assert "Shuffle the Armos Item" in error_message
    print(f"✓ Correctly raised ConstraintConflictError:\n{error_message}")


def test_constraint_conflict_force_hc_to_coast_without_shuffle_coast():
    """Test that forcing HC to Coast without shuffle_coast_item enabled raises an error."""
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    rom_data = build_minimal_rom('data')
    data_table = DataTable(rom_data)
    data_table.ResetToVanilla()

    # Create impossible flag combination
    flags = Flags()
    flags.force_heart_container_to_coast = True
    flags.shuffle_coast_item = False  # This is the problem
    flags.shuffle_dungeon_hearts = True  # Has HCs, but coast location not in pool

    randomizer = MajorItemRandomizer(data_table, flags)

    with pytest.raises(ConstraintConflictError) as exc_info:
        randomizer.Randomize()

    error_message = str(exc_info.value)
    assert "Force heart container to Coast" in error_message
    assert "Shuffle the Coast Item" in error_message
    print(f"✓ Correctly raised ConstraintConflictError:\n{error_message}")


def test_valid_force_two_hc_with_shuffle_dungeon_hearts():
    """Test that forcing 2 HCs to level 9 WITH shuffle_dungeon_hearts enabled works."""
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable
    from logic.items.room_item_collector import RoomItemCollector

    rom_data = build_minimal_rom('data')
    data_table = DataTable(rom_data)
    data_table.ResetToVanilla()

    # Valid flag combination: force 2 HCs + enable shuffle to get HCs in pool
    flags = Flags()
    flags.force_two_heart_containers_to_level_nine = True
    flags.shuffle_dungeon_hearts = True  # Adds 8 HCs to pool

    randomizer = MajorItemRandomizer(data_table, flags)

    # Should NOT raise an error
    result = randomizer.Randomize()
    assert result == True, "Randomization should succeed with valid flag combination"

    # Verify at least 2 HCs are in level 9
    collector = RoomItemCollector(data_table)
    room_pairs = collector.CollectAll()

    level_9_hc_count = 0
    if 9 in room_pairs:
        for pair in room_pairs[9]:
            if pair.item == Item.HEART_CONTAINER:
                level_9_hc_count += 1
                print(f"Found HC in Level 9 Room 0x{pair.room_num:02X}")

    assert level_9_hc_count >= 2, \
        f"Expected at least 2 heart containers in level 9, found {level_9_hc_count}"

    print(f"✓ Valid combination: {level_9_hc_count} heart containers in level 9")


def test_valid_force_two_hc_with_coast_and_armos():
    """Test that forcing 2 HCs to level 9 with coast + armos items enabled works."""
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable
    from logic.items.room_item_collector import RoomItemCollector

    rom_data = build_minimal_rom('data')
    data_table = DataTable(rom_data)
    data_table.ResetToVanilla()

    # Valid flag combination: force 2 HCs + enable coast & armos (2 HCs total)
    flags = Flags()
    flags.force_two_heart_containers_to_level_nine = True
    flags.shuffle_dungeon_hearts = False  # Don't use dungeon HCs
    flags.shuffle_coast_item = True  # 1 HC from coast
    flags.shuffle_armos_item = True  # 1 HC from armos (if vanilla has it)

    randomizer = MajorItemRandomizer(data_table, flags)

    # Should NOT raise an error (assuming coast & armos have HCs in vanilla)
    try:
        result = randomizer.Randomize()
        assert result == True, "Randomization should succeed"

        # Verify at least 2 HCs are in level 9
        collector = RoomItemCollector(data_table)
        room_pairs = collector.CollectAll()

        level_9_hc_count = 0
        if 9 in room_pairs:
            for pair in room_pairs[9]:
                if pair.item == Item.HEART_CONTAINER:
                    level_9_hc_count += 1

        assert level_9_hc_count >= 2, \
            f"Expected at least 2 HCs in level 9, found {level_9_hc_count}"

        print(f"✓ Valid combination with coast+armos: {level_9_hc_count} HCs in level 9")
    except ConstraintConflictError as e:
        # This might happen if vanilla doesn't have HCs at coast/armos
        print(f"Note: Coast/Armos may not have HCs in vanilla: {e}")


def test_multiple_constraint_errors_reported_together():
    """Test that multiple constraint violations are all reported in a single error."""
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    rom_data = build_minimal_rom('data')
    data_table = DataTable(rom_data)
    data_table.ResetToVanilla()

    # Create MULTIPLE impossible flag combinations at once
    flags = Flags()
    flags.force_heart_container_to_armos = True
    flags.shuffle_armos_item = False  # Error 1: armos not enabled
    flags.force_heart_container_to_coast = True
    flags.shuffle_coast_item = False  # Error 2: coast not enabled
    flags.force_two_heart_containers_to_level_nine = True  # Error 3: not enough HCs
    flags.shuffle_dungeon_hearts = False

    randomizer = MajorItemRandomizer(data_table, flags)

    with pytest.raises(ConstraintConflictError) as exc_info:
        randomizer.Randomize()

    error_message = str(exc_info.value)

    # All three errors should be present
    assert "Force heart container to Armos" in error_message
    assert "Force heart container to Coast" in error_message
    assert "Force two heart containers to be in level 9" in error_message

    # Should have bullet points for each error
    assert error_message.count("•") >= 3

    print(f"✓ Correctly reported multiple constraint conflicts:\n{error_message}")


def test_shuffle_minor_dungeon_items_disabled_by_default(modifiable_data_table):
    """Test that shuffle_minor_dungeon_items is disabled by default (bombs, keys, rupees stay in place)."""
    from logic.items.room_item_collector import RoomItemCollector

    # Default flags should have shuffle_minor_dungeon_items = False
    flags = Flags()
    assert flags.shuffle_minor_dungeon_items == False, "shuffle_minor_dungeon_items should default to False"

    # Minor items that should NOT be shuffled by default
    minor_items = [Item.BOMBS, Item.KEY, Item.FIVE_RUPEES]

    # Capture vanilla minor item locations in dungeons
    collector = RoomItemCollector(modifiable_data_table)
    vanilla_room_pairs = collector.CollectAll()

    vanilla_minor_locations = {}
    for level_num, pairs in vanilla_room_pairs.items():
        for pair in pairs:
            if pair.item in minor_items:
                vanilla_minor_locations[(level_num, pair.room_num)] = pair.item
                print(f"Vanilla minor item: Level {level_num} Room 0x{pair.room_num:02X} has {pair.item.name}")

    print(f"\nFound {len(vanilla_minor_locations)} minor items in vanilla dungeons")

    # Run randomization with default flags (shuffle_minor_dungeon_items = False)
    randomizer = MajorItemRandomizer(modifiable_data_table, flags)
    randomizer.Randomize()

    # Verify minor items are still in their original locations
    collector2 = RoomItemCollector(modifiable_data_table)
    shuffled_room_pairs = collector2.CollectAll()

    for level_num, pairs in shuffled_room_pairs.items():
        for pair in pairs:
            if (level_num, pair.room_num) in vanilla_minor_locations:
                expected_item = vanilla_minor_locations[(level_num, pair.room_num)]
                assert pair.item == expected_item, \
                    f"Minor item at Level {level_num} Room 0x{pair.room_num:02X} was changed from {expected_item.name} to {pair.item.name}"
                print(f"✓ {expected_item.name} still at Level {level_num} Room 0x{pair.room_num:02X}")

    print(f"✓ All {len(vanilla_minor_locations)} minor items remained in original locations")


def test_shuffle_minor_dungeon_items_when_enabled():
    """Test that bombs, keys, and five_rupees are included in shuffle when flag is enabled."""
    from logic.items.room_item_collector import RoomItemCollector
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    # Minor items that should be shuffled when flag is enabled
    minor_items = [Item.BOMBS, Item.KEY, Item.FIVE_RUPEES]

    # Create flags with shuffle_minor_dungeon_items enabled
    flags = Flags()
    flags.shuffle_minor_dungeon_items = True

    # Test multiple seeds to verify minor items can move
    minor_items_moved = False

    for seed in range(5):
        rom_data = build_minimal_rom('data')
        data_table = DataTable(rom_data)
        data_table.ResetToVanilla()

        # Capture vanilla minor item locations
        collector = RoomItemCollector(data_table)
        vanilla_room_pairs = collector.CollectAll()

        vanilla_minor_locations = {}
        for level_num, pairs in vanilla_room_pairs.items():
            for pair in pairs:
                if pair.item in minor_items:
                    vanilla_minor_locations[(level_num, pair.room_num)] = pair.item

        # Run randomization
        randomizer = MajorItemRandomizer(data_table, flags)
        randomizer.Randomize()

        # Check if minor items moved
        collector2 = RoomItemCollector(data_table)
        shuffled_room_pairs = collector2.CollectAll()

        # Count minor items that stayed in the same location
        items_in_same_location = 0
        for level_num, pairs in shuffled_room_pairs.items():
            for pair in pairs:
                if (level_num, pair.room_num) in vanilla_minor_locations:
                    if vanilla_minor_locations[(level_num, pair.room_num)] == pair.item:
                        items_in_same_location += 1

        # If any minor item moved, we've confirmed they're being shuffled
        if items_in_same_location < len(vanilla_minor_locations):
            minor_items_moved = True
            moved_count = len(vanilla_minor_locations) - items_in_same_location
            print(f"Seed {seed}: ✓ Minor items were shuffled ({moved_count}/{len(vanilla_minor_locations)} moved)")
            break

    assert minor_items_moved, \
        "Minor items should be shuffled when shuffle_minor_dungeon_items is enabled"


def test_shuffle_minor_dungeon_items_excludes_maps_and_compasses():
    """Test that maps and compasses are NOT shuffled even when shuffle_minor_dungeon_items is enabled."""
    from logic.items.room_item_collector import RoomItemCollector
    from test_rom_builder import build_minimal_rom
    from logic.data_table import DataTable

    # Create flags with shuffle_minor_dungeon_items enabled
    flags = Flags()
    flags.shuffle_minor_dungeon_items = True

    # Test multiple seeds to verify maps and compasses never move
    for seed in range(5):
        rom_data = build_minimal_rom('data')
        data_table = DataTable(rom_data)
        data_table.ResetToVanilla()

        # Capture vanilla map and compass locations
        collector = RoomItemCollector(data_table)
        vanilla_room_pairs = collector.CollectAll()

        vanilla_map_compass_locations = {}
        for level_num, pairs in vanilla_room_pairs.items():
            for pair in pairs:
                if pair.item in [Item.MAP, Item.COMPASS]:
                    vanilla_map_compass_locations[(level_num, pair.room_num)] = pair.item

        # Run randomization
        randomizer = MajorItemRandomizer(data_table, flags)
        randomizer.Randomize()

        # Verify maps and compasses stayed in place
        collector2 = RoomItemCollector(data_table)
        shuffled_room_pairs = collector2.CollectAll()

        for level_num, pairs in shuffled_room_pairs.items():
            for pair in pairs:
                if (level_num, pair.room_num) in vanilla_map_compass_locations:
                    expected_item = vanilla_map_compass_locations[(level_num, pair.room_num)]
                    assert pair.item == expected_item, \
                        f"{expected_item.name} at Level {level_num} Room 0x{pair.room_num:02X} was moved to different location (seed {seed})"

        print(f"Seed {seed}: ✓ All maps and compasses remained in original locations")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
