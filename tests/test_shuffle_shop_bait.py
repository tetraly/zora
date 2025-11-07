"""Unit tests for the shuffle_shop_bait flag"""

import io
import sys
import os
import unittest

# Add logic directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from logic.randomizer import Z1Randomizer
from logic.flags import Flags
from logic.location import Location
from logic.randomizer_constants import Item


def load_rom():
    """Load ROM file into BytesIO"""
    rom_path = os.path.join(os.path.dirname(__file__), '..', 'roms', 'Z1_20250928_1NhjkmR55xvmdk0LmGY9fDm2xhOqxKzDfv.nes')

    if not os.path.exists(rom_path):
        return None

    with open(rom_path, 'rb') as f:
        rom_data = f.read()

    return rom_data


class ShuffleShopBaitTest(unittest.TestCase):
    """Test that the shuffle_shop_bait flag works correctly."""

    def test_shuffle_shop_bait_places_fairy_in_shop_4_right(self):
        """Test that shuffle_shop_bait places a fairy in shop 4's right position with correct price."""
        # Load ROM
        rom_data = load_rom()
        if rom_data is None:
            self.skipTest("ROM file not found")
        rom_bytes = io.BytesIO(rom_data)

        # Set up flags
        flags = Flags()
        flags.set('shuffle_shop_bait', True)

        # Run randomizer
        seed = 12345
        randomizer = Z1Randomizer(rom_bytes, seed, flags)

        # Get the data table
        data_table = randomizer.data_table

        # Check that shop 4's right position (cave 0x20, position 3) has a fairy
        shop_4_right_location = Location.CavePosition(0x20, 3)
        item_at_location = data_table.GetCaveItem(shop_4_right_location)

        self.assertEqual(
            item_at_location,
            Item.FAIRY,
            f"Shop 4 right position should contain a fairy, but found {item_at_location}"
        )

        # Check that the price is between 20 and 40 rupees
        cave_num = 0x20
        price_data = data_table.overworld_caves[cave_num].GetPriceData()
        # Position 3 corresponds to index 2 in the price data array (0-indexed)
        fairy_price = price_data[2]

        self.assertGreaterEqual(
            fairy_price,
            20,
            f"Fairy price should be at least 20 rupees, but is {fairy_price}"
        )
        self.assertLessEqual(
            fairy_price,
            40,
            f"Fairy price should be at most 40 rupees, but is {fairy_price}"
        )

    def test_shuffle_shop_bait_deterministic(self):
        """Test that shuffle_shop_bait produces deterministic results."""
        # Load ROM
        rom_data = load_rom()
        if rom_data is None:
            self.skipTest("ROM file not found")

        # Set up flags
        flags = Flags()
        flags.set('shuffle_shop_bait', True)

        # First run
        seed = 99999
        rom_bytes_1 = io.BytesIO(rom_data)
        randomizer_1 = Z1Randomizer(rom_bytes_1, seed, flags)
        data_table_1 = randomizer_1.data_table

        # Get fairy and price from first run
        shop_4_right_location = Location.CavePosition(0x20, 3)
        item_1 = data_table_1.GetCaveItem(shop_4_right_location)
        price_1 = data_table_1.overworld_caves[0x20].GetPriceData()[2]

        # Second run with same seed
        rom_bytes_2 = io.BytesIO(rom_data)
        randomizer_2 = Z1Randomizer(rom_bytes_2, seed, flags)
        data_table_2 = randomizer_2.data_table

        # Get fairy and price from second run
        item_2 = data_table_2.GetCaveItem(shop_4_right_location)
        price_2 = data_table_2.overworld_caves[0x20].GetPriceData()[2]

        # Check that both runs produced the same results
        self.assertEqual(
            item_1,
            item_2,
            "Item at shop 4 right should be the same across runs with same seed"
        )
        self.assertEqual(
            price_1,
            price_2,
            f"Price at shop 4 right should be the same across runs with same seed (got {price_1} and {price_2})"
        )


if __name__ == "__main__":
    unittest.main()
