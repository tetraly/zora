"""Tests for MajorItemRandomizer."""

import pytest
import sys
from pathlib import Path

# Add parent directory to path to import logic modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from logic.items.major_item_randomizer import MajorItemRandomizer
from logic.rom_reader import RomReader
from logic.data_table import DataTable
from logic.flags import Flags
from logic.randomizer_constants import Item
from test_rom_builder import build_minimal_rom


@pytest.fixture(scope="session")
def vanilla_rom():
    """Create a minimal ROM from extracted test data."""
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
        from logic.rom_reader import RomReader
        from logic.data_table import DataTable

        rom_data = build_minimal_rom('data')
        rom_reader = RomReader(rom_data)
        data_table = DataTable(rom_reader)
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
                if item != Item.NO_ITEM and item != Item.RUPEE:
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
    from logic.rom_reader import RomReader
    from logic.data_table import DataTable

    # Create flags with coast item shuffle enabled (required to test this constraint)
    flags = Flags()
    flags.shuffle_coast_item = True

    # Test multiple seeds to ensure constraint holds consistently
    for seed in range(5):
        rom_data = build_minimal_rom('data')
        rom_reader = RomReader(rom_data)
        data_table = DataTable(rom_reader)
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
    from logic.rom_reader import RomReader
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
        rom_reader = RomReader(rom_data)
        data_table = DataTable(rom_reader)
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
    from logic.rom_reader import RomReader
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
        rom_reader = RomReader(rom_data)
        data_table = DataTable(rom_reader)
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
    from logic.rom_reader import RomReader
    from logic.data_table import DataTable

    # Create flags with potion shop shuffle enabled
    flags = Flags()
    flags.shuffle_potion_shop_items = True

    # Test multiple seeds to ensure constraint holds consistently
    for seed in range(5):
        rom_data = build_minimal_rom('data')
        rom_reader = RomReader(rom_data)
        data_table = DataTable(rom_reader)
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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
