"""Main item randomizer orchestrator with deterministic solver sequencing."""

from typing import Dict, Optional

import logging as log
import random

from .major_item_randomizer import MajorItemRandomizer
from .minor_item_randomizer import MinorItemRandomizer
from .room_item_collector import RoomItemCollector
from ..data_table import DataTable
from ..flags import Flags
from ..randomizer_constants import  CaveType, Item, ValidItemPositions

class ItemRandomizer:
    """Orchestrates item randomization and progressive item conversions."""

    def __init__(self, data_table: DataTable, flags: Flags) -> None:
        self.data_table = data_table
        self.flags = flags
        self.major_randomizer = MajorItemRandomizer(self.data_table, self.flags)
        self.seed: int
        # Track solver permutations to keep retries deterministic.
        self.forbidden_major_solution_maps: list[Dict] = []
        self.last_major_solution_map: Optional[Dict] = None

    def set_forbidden_major_solutions(self, forbidden: list[Dict]) -> None:
        """Provide solver assignments that must be skipped on the next shuffle."""
        self.forbidden_major_solution_maps = forbidden

    def get_last_major_solution_map(self) -> Optional[Dict]:
        return self.last_major_solution_map

    def ReplaceProgressiveItemsWithUpgrades(self):
        pass

    def ResetState(self):
        pass

    def ReadItemsAndLocationsFromTable(self):
        pass

    def ShuffleItems(self, seed: int):
        self.seed = seed

    def WriteItemsAndLocationsToTable(self):
        pass

    def HasValidItemConfiguration(self) -> bool:
        return self.Randomize(self.seed)

    def Randomize(self, seed: int) -> bool:
        """Main entry point for item randomization.

        Args:
            seed: Optional seed to pass through to solver-based shufflers.

        Returns:
            True if both major and minor randomization succeeded, otherwise False.
        """
        log.info("Starting item randomization...")

        # Step 1: Run major item randomizer (inter-dungeon shuffle)
        # Skip major item randomization if flag is not enabled
        if self.flags.major_item_shuffle:
            log.info("Running major item randomizer...")
            self.major_randomizer.set_forbidden_solution_maps(self.forbidden_major_solution_maps)
            result = self.major_randomizer.Randomize(seed=seed)

            if not result:
                log.error("Major item randomization failed")
                return False
            self.last_major_solution_map = (
                self.major_randomizer.last_solution_map.copy()
                if self.major_randomizer.last_solution_map
                else None
            )
        else:
            log.info("Major item shuffle disabled - skipping major item randomization")

        # Step 2: Run minor item randomizer (intra-dungeon shuffle)
        if not self._RunMinorItemRandomizer(seed):
            log.error("Minor item randomization failed")
            return False

        # Step 3: Apply progressive item conversions
        self.ConvertProgressiveItemsToUpgrades()
        
        #Step 3.5: Randomize Item Positions
        self.RandomizeItemPositions()

        # TODO: Step 4: Randomize shop items (prices, etc.)
        # self._RandomizeShopItems()

        log.info("Item randomization completed successfully")
        return True

    def ConvertProgressiveItemsToUpgrades(self) -> None:
        """Apply progressive item conversions based on flags.

        Progressive items replace higher-tier items with their base versions:
        - RED_CANDLE → BLUE_CANDLE
        - RED_RING → BLUE_RING
        - SILVER_ARROWS → WOOD_ARROWS
        - WHITE_SWORD/MAGICAL_SWORD → WOOD_SWORD
        """
        log.info("Applying progressive item conversions...")
        conversions = 0

        # Convert dungeon items (levels 1-9)
        collector = RoomItemCollector(self.data_table)
        for level_num, pairs in collector.CollectAll().items():
            for pair in pairs:
                item = self.data_table.GetItem(level_num, pair.room_num)
                if not item.IsProgressiveEnhancedItem():
                    continue
                base_item = item.GetProgressiveBaseItem()
                self.data_table.SetItem(level_num, pair.room_num, base_item)
                conversions += 1
                log.info(f"L{level_num} R{pair.room_num:02X}: {item.name} → {base_item.name}")

        # Convert overworld cave items
        # Note: Caves use 1-indexed positions (1-3)
        for cave_type in CaveType.AllShopsAndItemCaves(): 
            for position in range(1, 4):  # 1-indexed: 1, 2, 3
                item = self.data_table.GetCaveItemNew(cave_type, position)
                if not item.IsProgressiveEnhancedItem():
                    continue
                base_item = item.GetProgressiveBaseItem()
                self.data_table.SetCaveItemNew(cave_type, position, base_item)
                conversions += 1
                log.info(f"{cave_type.name} pos{position}: {item.name} → {base_item.name}")

        log.info(f"Applied {conversions} progressive item conversions")

    def _RunMinorItemRandomizer(self, seed: int) -> bool:
        """Run the minor item randomizer for intra-dungeon shuffle.

        Shuffles items within each dungeon level (keys, maps, compasses, etc.)
        and randomizes item positions based on room types.
        """
        log.info("Running minor item randomizer...")
        minor_randomizer = MinorItemRandomizer(self.data_table, self.flags)
        return minor_randomizer.Randomize(seed=seed)

    def _RandomizeShopItems(self) -> None:
        """Randomize shop items and prices.

        TODO: Implement shop item randomization:
        - Randomize which items appear in shops
        - Randomize shop prices
        - Handle special cases (take-any caves, etc.)
        """
        log.info("Shop item randomization not yet implemented")
        pass

    def RandomizeItemPositions(self) -> None:
        for level_num in CaveType.AllLevels():
            self.data_table.SetLevelItemPositionCoordinates(level_num, [0x89, 0xD6, 0xC9, 0x2C])
            log.warning(f"Set coords for level {level_num} ")

        # Collect location items from dungeons (levels 1-9)
        collector = RoomItemCollector(self.data_table)
        for level_num, pairs in collector.CollectAll().items():
            for pair in pairs:
                room_type = self.data_table.GetRoomType(level_num, pair.room_num)
                item_position = random.choice(ValidItemPositions[room_type])
                self.data_table.SetItemPositionNew(level_num, pair.room_num, item_position)
            
            
            