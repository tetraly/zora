import pytest
import io
import sys
from pathlib import Path

# Add parent directory to path to import logic modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from logic.validator import Validator
from logic.rom_reader import RomReader
from logic.data_table import DataTable
from logic.flags import Flags
from logic.location import Location
from logic.randomizer_constants import Item
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

def test_validator_vanilla(vanilla_data_table, default_flags):
    validator = Validator(vanilla_data_table, default_flags)
    assert validator.IsSeedValid()




def test_validator_ladder_blocked_ladder(modifiable_data_table, default_flags):
    """Test that swapping the ladder with the coast heart makes the seed invalid.

    In vanilla:
    - Level 4, Room 0x60 has the LADDER
    - Coast item (Cave 21, Position 2) has a HEART_CONTAINER

    By swapping them, the ladder will be at the coast (which requires the ladder
    to access), creating an impossible situation.
    """
    # Define the locations
    level_4_ladder_location = Location.LevelRoom(4, 0x60)
    # Coast item: cave_num 21 -> CaveType 0x25 (COAST_ITEM), position 2
    coast_cave_type = 21 + 0x10

    # Swap the items: put heart at level 4, put ladder at coast
    modifiable_data_table.SetRoomItem(level_4_ladder_location, Item.HEART_CONTAINER)
    modifiable_data_table.SetCaveItem(coast_cave_type, 2, Item.LADDER)

    # This should make the seed invalid because the ladder is required to reach the coast
    validator = Validator(modifiable_data_table, default_flags)
    assert not validator.IsSeedValid()


def test_validator_starting_sword_requirement(modifiable_data_table):
    """Test that moving the wood sword into level 1 requires the dont_guarantee flag.

    In vanilla:
    - Cave 0, Position 2 has the WOOD_SWORD
    - Level 1, Room 0x74 (one right from start) has a KEY

    By swapping them, the wood sword is in level 1. With default flags, this makes the
    seed invalid because you need a weapon to enter level 1 to get the weapon.
    However, with the dont_guarantee_starting_sword_or_wand flag enabled, this should
    be valid because the player can dive level 1 weaponless to get the sword.
    """
    # Define the locations
    # Wood sword cave: cave_num 0 -> CaveType 0x10, position 2
    wood_sword_cave_type = 0 + 0x10
    level_1_key_room_location = Location.LevelRoom(1, 0x74)

    # Swap the items: put key in wood sword cave, put wood sword in level 1
    modifiable_data_table.SetCaveItem(wood_sword_cave_type, 2, Item.KEY)
    modifiable_data_table.SetRoomItem(level_1_key_room_location, Item.WOOD_SWORD)

    # Test 1: With default flags, this should be invalid
    default_flags = Flags()
    validator = Validator(modifiable_data_table, default_flags)
    assert not validator.IsSeedValid(), "Should be invalid with default flags"

    # Test 2: With dont_guarantee_starting_sword_or_wand flag, this should be valid
    flags_with_dont_guarantee = Flags()
    flags_with_dont_guarantee.set('dont_guarantee_starting_sword_or_wand', True)
    validator = Validator(modifiable_data_table, flags_with_dont_guarantee)
    assert validator.IsSeedValid(), "Should be valid with dont_guarantee_starting_sword_or_wand flag"