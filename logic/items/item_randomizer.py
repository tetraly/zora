"""Main item randomizer orchestrator.

This module coordinates the major and minor item randomizers and handles
progressive item conversions.
"""

import logging as log

from .major_item_randomizer import MajorItemRandomizer
from .minor_item_randomizer import MinorItemRandomizer
from ..data_table import DataTable
from ..flags import Flags
from ..randomizer_constants import Item


class ItemRandomizer:
    """Orchestrates item randomization and progressive item conversions.

    This class:
    1. Runs the MajorItemRandomizer (inter-dungeon shuffle)
    2. Runs the MinorItemRandomizer (intra-dungeon shuffle)
    3. Applies progressive item conversions based on flags
    4. TODO: Randomizes shop items
    """

    def __init__(self, data_table: DataTable, flags: Flags) -> None:
        self.data_table = data_table
        self.flags = flags

    def Randomize(self) -> None:
        """Main entry point for item randomization."""
        log.info("Starting item randomization...")

        # Step 1: Run major item randomizer (inter-dungeon shuffle)
        self._RunMajorItemRandomizer()

        # Step 2: Run minor item randomizer (intra-dungeon shuffle)
        self._RunMinorItemRandomizer()

        # Step 3: Apply progressive item conversions
        self._ApplyProgressiveItems()

        # TODO: Step 4: Randomize shop items (prices, etc.)
        # self._RandomizeShopItems()

        log.info("Item randomization completed successfully")

    def _RunMajorItemRandomizer(self) -> None:
        """Run the major item randomizer for inter-dungeon shuffle."""
        log.info("Running major item randomizer...")
        major_randomizer = MajorItemRandomizer(self.data_table, self.flags)
        major_randomizer.Randomize()

    def _ApplyProgressiveItems(self) -> None:
        """Apply progressive item conversions based on flags.

        Progressive items replace higher-tier items with their base versions:
        - RED_CANDLE → BLUE_CANDLE
        - RED_RING → BLUE_RING
        - SILVER_ARROWS → WOOD_ARROWS
        - WHITE_SWORD/MAGICAL_SWORD → WOOD_SWORD
        - MAGICAL_BOOMERANG → WOOD_BOOMERANG (if flag set)
        """
        if not self.flags.progressive_items:
            log.debug("Progressive items disabled, skipping conversion")
            return

        log.info("Applying progressive item conversions...")

        # Get additional progressive flags (if they exist)
        progressive_candles = getattr(self.flags, 'progressive_candles', False)
        progressive_rings = getattr(self.flags, 'progressive_rings', False)
        progressive_arrows = getattr(self.flags, 'progressive_arrows', False)
        progressive_swords = getattr(self.flags, 'progressive_swords', False)
        progressive_boomerangs = getattr(self.flags, 'progressive_boomerangs', False)

        conversions = 0

        # Convert dungeon items (levels 1-9)
        for level_num in range(1, 10):
            for room_num in range(0, 0x80):
                item = self.data_table.GetItem(level_num, room_num)
                converted_item = self._ConvertProgressiveItem(
                    item, progressive_candles, progressive_rings,
                    progressive_arrows, progressive_swords, progressive_boomerangs
                )
                if converted_item != item:
                    self.data_table.SetItem(level_num, room_num, converted_item)
                    conversions += 1
                    log.debug(f"L{level_num} R{room_num:02X}: {item.name} → {converted_item.name}")

        # Convert overworld cave items
        # Note: Caves use 1-indexed positions (1-3)
        from ..randomizer_constants import CaveType
        for cave_type in CaveType:
            for position in range(1, 4):  # 1-indexed: 1, 2, 3
                try:
                    item = self.data_table.GetCaveItem(cave_type, position)
                    converted_item = self._ConvertProgressiveItem(
                        item, progressive_candles, progressive_rings,
                        progressive_arrows, progressive_swords, progressive_boomerangs
                    )
                    if converted_item != item:
                        self.data_table.SetCaveItem(cave_type, position, converted_item)
                        conversions += 1
                        log.debug(f"{cave_type.name} pos{position}: {item.name} → {converted_item.name}")
                except:
                    # Skip invalid cave positions
                    pass

        log.info(f"Applied {conversions} progressive item conversions")

    def _ConvertProgressiveItem(self, item: Item, progressive_candles: bool = False,
                                progressive_rings: bool = False, progressive_arrows: bool = False,
                                progressive_swords: bool = False, progressive_boomerangs: bool = False) -> Item:
        """Convert a single item to its progressive base version if applicable.

        Args:
            item: The item to potentially convert
            progressive_candles: Enable candle progression
            progressive_rings: Enable ring progression
            progressive_arrows: Enable arrow progression
            progressive_swords: Enable sword progression
            progressive_boomerangs: Enable boomerang progression

        Returns:
            The converted item (or original if no conversion applies)
        """
        if (self.flags.progressive_items or progressive_candles) and item == Item.RED_CANDLE:
            return Item.BLUE_CANDLE
        if (self.flags.progressive_items or progressive_rings) and item == Item.RED_RING:
            return Item.BLUE_RING
        if (self.flags.progressive_items or progressive_arrows) and item == Item.SILVER_ARROWS:
            return Item.WOOD_ARROWS
        if (self.flags.progressive_items or progressive_swords) and item in [Item.WHITE_SWORD, Item.MAGICAL_SWORD]:
            return Item.WOOD_SWORD
        if progressive_boomerangs and item == Item.MAGICAL_BOOMERANG:
            return Item.WOOD_BOOMERANG
        return item

    def _RunMinorItemRandomizer(self) -> None:
        """Run the minor item randomizer for intra-dungeon shuffle.

        Shuffles items within each dungeon level (keys, maps, compasses, etc.)
        and randomizes item positions based on room types.
        """
        log.info("Running minor item randomizer...")
        minor_randomizer = MinorItemRandomizer(self.data_table, self.flags)
        minor_randomizer.Randomize()

    def _RandomizeShopItems(self) -> None:
        """Randomize shop items and prices.

        TODO: Implement shop item randomization:
        - Randomize which items appear in shops
        - Randomize shop prices
        - Handle special cases (take-any caves, etc.)
        """
        log.info("Shop item randomization not yet implemented")
        pass
