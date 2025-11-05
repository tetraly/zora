"""Major item randomizer using constraint solver approach.

This module handles inter-dungeon shuffle of major items (including heart containers)
across all dungeons (1-9) and key overworld locations using the AssignmentSolver.

Items NOT included in major shuffle:
- TRIFORCE (levels 1-8) - stays in assigned level, shuffled intra-dungeon
- TRIFORCE_OF_POWER (level 9) - never shuffled, locked to original room
- Minor items: KEY, MAP, COMPASS, BOMBS, FIVE_RUPEES
- Filler items: RUPEE, etc.

These items are handled by the intra-dungeon shuffle (NewItemRandomizer).
"""

from .room_item_collector import RoomItemCollector
from collections import namedtuple
from typing import Union
import logging as log

from ..randomizer_constants import (
    CARDINAL_DIRECTIONS, CavePosition, CaveType, DUNGEON_LEVEL_NUMBERS, Item, LevelNum, RoomNum, Range, WallType
)
from ..data_table import DataTable
from ..flags import Flags
from ..assignment_solver import AssignmentSolver


# NamedTuple definitions for location representation
DungeonLocation = namedtuple('DungeonLocation', ['level_num', 'room_num'])
# level_num: int - the dungeon level (1-9)
# room_num: int - the room number within that level

CaveLocation = namedtuple('CaveLocation', ['cave_type', 'position_num'])
# cave_type: CaveType - the cave type enum value
# position_num: int - the position within that cave (1-3)

LocationItemPair = namedtuple('LocationItemPair', ['location', 'item'])
# location: Union[DungeonLocation, CaveLocation] - the location
# item: Item - the item at that location


def is_dungeon_location(location: Union[DungeonLocation, CaveLocation]) -> bool:
    """Check if a location is a dungeon location."""
    return isinstance(location, DungeonLocation)


def is_cave_location(location: Union[DungeonLocation, CaveLocation]) -> bool:
    """Check if a location is a cave location."""
    return isinstance(location, CaveLocation)


class MajorItemRandomizer:
    """Handles inter-dungeon shuffle of major items using constraint solver.

    Only shuffles major items and heart containers across the entire game.
    Minor items (keys, maps, compasses, bombs, rupees) and triforces are NOT included.
    """

    def __init__(self, data_table: DataTable, flags: Flags) -> None:
        self.data_table = data_table
        self.flags = flags
        self.location_item_pairs: list[LocationItemPair] = []

    def Randomize(self) -> None:
        """Main entry point for major item randomization."""
        log.info("Starting major item randomization...")

        self.data_table.NormalizeNoItemCode()
        
        # Collect all major item locations and their current items
        self.location_item_pairs = self._CollectLocationsAndItems()

        if not self.location_item_pairs:
            log.warning("No major items found to shuffle")
            return

        log.info(f"Found {len(self.location_item_pairs)} item locations")

        # Extract locations and items for shuffling
        locations = [pair.location for pair in self.location_item_pairs]
        items = [pair.item for pair in self.location_item_pairs]

        # Setup solver with permutation problem
        solver = AssignmentSolver()
        solver.add_permutation_problem(keys=locations, values=items)

        # Add constraints based on flags
        self._AddConstraints(solver, locations, items)

        # Solve
        solution = solver.solve(seed=None, time_limit_seconds=10.0)

        if solution is None:
            log.error("No valid major item shuffle exists with current constraints")
            return

        # Write solution back to data table
        self._WriteSolutionToDataTable(solution)

        log.info("Major item randomization completed successfully")

    def _CollectLocationsAndItems(self) -> list[LocationItemPair]:
        """Collect all major item locations and their current items.

        Returns:
            List of LocationItemPair namedtuples containing location and item info.
        """

        location_item_pairs: list[LocationItemPair] = []
        collector = RoomItemCollector(self.data_table)

        # Collect location items from dungeons (levels 1-9)
        room_item_pair_lists = collector.CollectAll()

        # Keep only Major Items and Heart Containers
        for level_num, pairs in room_item_pair_lists.items():
            for pair in pairs:
                if pair.item.IsMajorItem() or pair.item == Item.HEART_CONTAINER:
                    location = DungeonLocation(level_num, pair.room_num)
                    location_item_pairs.append(LocationItemPair(location, pair.item))

        # Collect from overworld caves
        location_item_pairs.extend(self._CollectOverworldCaveLocations())

        return location_item_pairs

    def _CollectOverworldCaveLocations(self) -> list[LocationItemPair]:
        """Collect major item locations from overworld caves.

        Only includes locations if their respective flags are enabled:
        - Sword caves (always included if items exist)
        - Letter cave (always included)
        - Armos item (check flag)
        - Coast item (check flag)
        - Potion shops (check randomize_potions flag)

        Returns:
            List of LocationItemPair for overworld major items.
        """        
        pairs = []

        # Caves with items (using CavePosition enum for clarity)
        locations = [
            (CaveType.WOOD_SWORD_CAVE, CavePosition.MIDDLE, self.flags.shuffle_wood_sword_cave_item),
            (CaveType.WHITE_SWORD_CAVE, CavePosition.MIDDLE, self.flags.shuffle_white_sword_cave_item),
            (CaveType.MAGICAL_SWORD_CAVE, CavePosition.MIDDLE, self.flags.shuffle_magical_sword_cave_item),
            (CaveType.LETTER_CAVE, CavePosition.MIDDLE, self.flags.shuffle_letter_cave_item),
            (CaveType.ARMOS_ITEM, CavePosition.MIDDLE, self.flags.shuffle_armos_item),
            (CaveType.COAST_ITEM, CavePosition.MIDDLE, self.flags.shuffle_coast_item),
            (CaveType.SHOP_1, CavePosition.RIGHT, self.flags.shuffle_shop_arrows),
            (CaveType.SHOP_2, CavePosition.RIGHT, self.flags.shuffle_shop_candle),
            (CaveType.SHOP_3, CavePosition.MIDDLE, self.flags.shuffle_shop_bait),
            (CaveType.SHOP_4, CavePosition.MIDDLE, self.flags.shuffle_shop_ring),
            (CaveType.POTION_SHOP, CavePosition.LEFT, self.flags.shuffle_potion_shop_items),
            (CaveType.POTION_SHOP, CavePosition.RIGHT, self.flags.shuffle_potion_shop_items),
        ]

        for cave_type, position, should_add in locations:
            if should_add:
                # Convert CavePosition enum (0-indexed) to 1-indexed for DataTable
                position_1indexed = int(position) + 1
                item = self.data_table.GetCaveItem(cave_type, position_1indexed)
                if item and item != Item.NO_ITEM and item != Item.OVERWORLD_NO_ITEM:
                    location = CaveLocation(cave_type, position)
                    pairs.append(LocationItemPair(location, item))

        return pairs
    
    def _AddConstraints(self, solver: AssignmentSolver,
                       locations: list[Union[DungeonLocation, CaveLocation]],
                       items: list[Item]) -> None:
        """Add all constraints to the solver based on flags.

        Args:
            solver: The constraint solver.
            locations: List of all locations being shuffled.
            items: List of all items being shuffled.
        """
        # Identify shop locations (needed for multiple constraints)
        shop_locations = [loc for loc in locations if is_cave_location(loc) and loc.cave_type.IsShop()]

        # ALWAYS-ON CONSTRAINTS (not flag-dependent)

        # 1. Heart containers cannot go in shops (always)
        if Item.HEART_CONTAINER in items and shop_locations:
            solver.forbid_all(sources=shop_locations, targets=Item.HEART_CONTAINER)
            log.debug(f"Constraint: Heart containers forbidden from {len(shop_locations)} shop locations")

        # 2. Progressive items cannot go in shops if progressive flag is enabled
        if self.flags.progressive_items and shop_locations:
            # Only forbid the BASE progressive items (wood sword, blue candle, etc.)
            # The higher tiers (white/magical sword, red candle, etc.) don't exist in progressive mode
            progressive_base_items = [item for item in items if item in [Item.WOOD_SWORD, Item.BLUE_CANDLE, Item.WOOD_ARROWS, Item.BLUE_RING]]
            if progressive_base_items:
                solver.forbid_all(sources=shop_locations, targets=progressive_base_items)
                log.debug(f"Constraint: {len(progressive_base_items)} progressive base items forbidden from shops")

        # 3. Ladder cannot go in coast location (requires ladder to access)
        coast_locations = [loc for loc in locations if is_cave_location(loc) and loc.cave_type == CaveType.COAST_ITEM]
        if Item.LADDER in items and coast_locations:
            solver.forbid_all(sources=coast_locations, targets=Item.LADDER)
            log.debug("Constraint: Ladder forbidden from coast location")

        # 4. Red potion must be in a shop (cannot go in dungeons due to 5-bit item field overflow)
        # Red potion is 0x20 which exceeds the 5-bit max of 0x1F for dungeon items
        dungeon_locations = [loc for loc in locations if is_dungeon_location(loc)]
        if Item.RED_POTION in items and dungeon_locations:
            for dungeon_loc in dungeon_locations:
                solver.forbid(source=dungeon_loc, target=Item.RED_POTION)
            log.debug(f"Constraint: Red potion forbidden from {len(dungeon_locations)} dungeon locations (must be in shops)")

        # 5. Letter cannot go in potion shop (letter is required to access potion shop)
        potion_shop_locations = [loc for loc in locations if is_cave_location(loc) and loc.cave_type == CaveType.POTION_SHOP]
        if Item.LETTER in items and potion_shop_locations:
            for potion_loc in potion_shop_locations:
                solver.forbid(source=potion_loc, target=Item.LETTER)
            log.debug(f"Constraint: Letter forbidden from {len(potion_shop_locations)} potion shop locations")

        # FLAG-DEPENDENT CONSTRAINTS

        # Helper: Force specific items to level 9
        self._ForceItemsToLevel9(solver, locations, items, [
            (self.flags.force_arrow_to_level_nine, [Item.WOOD_ARROWS, Item.SILVER_ARROWS], "arrow"),
            (self.flags.force_ring_to_level_nine, [Item.BLUE_RING, Item.RED_RING], "ring"),
            (self.flags.force_wand_to_level_nine, [Item.WAND], "wand"),
            (self.flags.force_heart_container_to_level_nine, [Item.HEART_CONTAINER], "heart container"),
        ])

        self._ForceItemsToLocation(solver, locations, items, [
            (self.flags.force_heart_container_to_armos and self.flags.shuffle_armos_item,
             CaveType.ARMOS_ITEM, [Item.HEART_CONTAINER], "Armos"),
            (self.flags.force_heart_container_to_coast and self.flags.shuffle_coast_item,
             CaveType.COAST_ITEM, [Item.HEART_CONTAINER], "Coast"),
        ])

        # Note: force_major_item_to_boss and force_major_item_to_triforce_room are
        # intra-dungeon constraints, handled by DungeonItemRandomizer, not here

    def _ForceItemsToLevel9(self, solver: AssignmentSolver,
                           locations: list[Union[DungeonLocation, CaveLocation]],
                           items: list[Item],
                           constraints: list[tuple[bool, list[Item], str]]) -> None:
        """Helper to force specific items to level 9 based on flags.

        Args:
            solver: The constraint solver.
            locations: List of all locations being shuffled.
            items: List of all items being shuffled.
            constraints: List of tuples (flag_enabled, target_items, item_name_for_log).
        """
        level_9_locations = [loc for loc in locations if is_dungeon_location(loc) and loc.level_num == 9]

        if not level_9_locations:
            return

        for flag_enabled, target_items, item_name in constraints:
            if flag_enabled:
                matching_items = [item for item in items if item in target_items]
                if matching_items:
                    solver.at_least_one_of(sources=level_9_locations, targets=matching_items)
                    log.debug(f"Constraint: At least one {item_name} must be in level 9")

    def _ForceItemsToLocation(self, solver: AssignmentSolver,
                             locations: list[Union[DungeonLocation, CaveLocation]],
                             items: list[Item],
                             constraints: list[tuple[bool, CaveType, list[Item], str]]) -> None:
        """Helper to force specific items to specific cave locations based on flags.

        Args:
            solver: The constraint solver.
            locations: List of all locations being shuffled.
            items: List of all items being shuffled.
            constraints: List of tuples (flag_enabled, cave_type, target_items, location_name_for_log).
        """
        for flag_enabled, cave_type, target_items, location_name in constraints:
            if flag_enabled:
                matching_locations = [loc for loc in locations
                                     if is_cave_location(loc) and loc.cave_type == cave_type]
                matching_items = [item for item in items if item in target_items]

                if matching_items and matching_locations:
                    solver.at_least_one_of(sources=matching_locations, targets=matching_items)
                    log.debug(f"Constraint: At least one {target_items[0].name.lower().replace('_', ' ')} must be at {location_name}")

    def _WriteSolutionToDataTable(self, solution: dict) -> None:
        """Write shuffled items back to data table.

        Args:
            solution: Dictionary mapping locations to items.
        """
        for location, item in solution.items():
            if is_dungeon_location(location):
                self.data_table.SetItem(location.level_num, location.room_num, item)
                log.debug(f"Set Level {location.level_num} Room 0x{location.room_num:02X} to {item.name}")

            elif is_cave_location(location):
                # Convert CavePosition enum (0-indexed) to 1-indexed for DataTable
                position_1indexed = int(location.position_num) + 1
                self.data_table.SetCaveItem(location.cave_type, position_1indexed, item)
                log.debug(f"Set Cave {location.cave_type.name} Position {location.position_num} to {item.name}")

                # Set randomized shop prices if applicable
                if location.cave_type.IsShop():
                    price = self._GetRandomizedShopPrice(item)
                    self.data_table.SetCavePrice(location.cave_type, position_1indexed, price)
                    log.debug(f"Set price for {item.name} in shop to {price} rupees")


    def _GetRandomizedShopPrice(self, item: Item) -> int:
        """Get a randomized price for an item placed in a shop.

        Price tiers:
        - Sword, Ring, Any Key: 230 ± 25 (range: 205-255)
        - Bow, Wand, Ladder: 100 ± 20 (range: 80-120)
        - Recorder, Arrows, HC: 80 ± 20 (range: 60-100)
        - Everything else: 60 ± 20 (range: 40-80)

        Args:
            item: The item being placed in the shop.

        Returns:
            The randomized price in rupees.
        """
        from random import randint

        # Tier 1: Sword, Ring, Any Key - 230 ± 25
        if item in [Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD,
                    Item.BLUE_RING, Item.RED_RING, Item.MAGICAL_KEY]:
            return randint(205, 255)

        # Tier 2: Bow, Wand, Ladder - 100 ± 20
        elif item in [Item.BOW, Item.WAND, Item.LADDER]:
            return randint(80, 120)

        # Tier 3: Recorder, Arrows, HC - 80 ± 20
        elif item in [Item.RECORDER, Item.WOOD_ARROWS, Item.SILVER_ARROWS, Item.HEART_CONTAINER]:
            return randint(60, 100)

        # Tier 4: Everything else - 60 ± 20
        else:
            return randint(40, 80)
