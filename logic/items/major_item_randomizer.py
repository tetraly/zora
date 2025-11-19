"""Major item randomizer using RandomizedBacktrackingSolver.

This module handles inter-dungeon shuffle of major items (including heart containers)
across all dungeons (1-9) and key overworld locations using RandomizedBacktrackingSolver.

Uses RandomizedBacktrackingSolver for consistent performance (~3.84ms) without external
dependencies. All constraints use the standard solver API (forbid, require, at_least_one_of)
which works with any solver implementation.

Items NOT included in major shuffle:
- TRIFORCE (levels 1-8) - stays in assigned level, shuffled intra-dungeon
- TRIFORCE_OF_POWER (level 9) - never shuffled, locked to original room
- MAP, COMPASS - always stay in their original locations
- KEY, BOMBS, FIVE_RUPEES - included in major shuffle if shuffle_minor_dungeon_items flag is enabled
- Filler items: RUPEE, etc.

These items are handled by the intra-dungeon shuffle (NewItemRandomizer).
"""

from .room_item_collector import RoomItemCollector
from collections import namedtuple
from typing import Dict, Optional, Union
import logging as log

from rng.random_number_generator import RandomNumberGenerator
from ..randomizer_constants import (
    CARDINAL_DIRECTIONS, CavePosition, CaveType, DUNGEON_LEVEL_NUMBERS, Item, LevelNum, RoomNum, Range, WallType
)
from ..data_table import DataTable
from ..flags import Flags
from ..solvers import RandomizedBacktrackingSolver


class ConstraintConflictError(Exception):
    """Raised when flag settings create impossible constraints for the assignment solver."""
    pass


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

    def __init__(self, data_table: DataTable, flags: Flags, rng: RandomNumberGenerator) -> None:
        self.data_table = data_table
        self.flags = flags
        self.rng = rng
        self.location_item_pairs: list[LocationItemPair] = []
        self.forbidden_solution_maps: list[Dict[Union[DungeonLocation, CaveLocation], Item]] = []
        self.last_solution_map: Optional[dict[Union[DungeonLocation, CaveLocation], Item]] = None

    def set_forbidden_solution_maps(
            self,
            forbidden: list[Dict[Union[DungeonLocation, CaveLocation], Item]]) -> None:
        """Supply a list of solver assignments (location -> item) to skip."""
        self.forbidden_solution_maps = forbidden

    def Randomize(self, seed: int | None = None) -> bool:
        """Main entry point for major item randomization.

        Args:
            seed: Optional seed forwarded to the assignment solver.

        Returns:
            True if a valid shuffle was produced, otherwise False.
        """
        log.info("Starting major item randomization...")
        
        # Collect all major item locations and their current items
        self.location_item_pairs = self._CollectLocationsAndItems()

        if not self.location_item_pairs:
            log.warning("No major items found to shuffle")
            return True

        log.info(f"Found {len(self.location_item_pairs)} item locations")

        # Extract locations and items for shuffling
        locations = [pair.location for pair in self.location_item_pairs]
        items = [pair.item for pair in self.location_item_pairs]

        solver = RandomizedBacktrackingSolver(self.rng)
        solver.add_permutation_problem(keys=locations, values=items, shuffle_seed=seed)
        for assignment in self.forbidden_solution_maps:
            solver.add_forbidden_solution_map(assignment)

        # Validate constraints before solving
        self._ValidateConstraints(locations, items)

        # Add constraints based on flags
        self._AddConstraints(solver, locations, items)

        # Scale solver parameters based on problem size
        # For problems with many items (e.g., when shuffle_minor_dungeon_items is enabled),
        # we need more iterations to find a valid solution
        num_items = len(locations)
        if num_items > 80:
            # Large problem (100+ items): need many more attempts
            max_iterations = 5000
            log.info(f"Large problem ({num_items} items) - using max_iterations={max_iterations}")
        elif num_items > 40:
            # Medium problem (40-80 items): moderate increase
            max_iterations = 2000
            log.debug(f"Medium problem ({num_items} items) - using max_iterations={max_iterations}")
        else:
            # Small problem (< 40 items): default is fine
            max_iterations = 1000
            log.debug(f"Small problem ({num_items} items) - using max_iterations={max_iterations}")

        # Solve (max_backtrack_depth scales automatically in solver based on problem size)
        solver_seed = self._solver_seed(seed)
        solution = solver.solve(seed=solver_seed, time_limit_seconds=10.0, max_iterations=max_iterations)

        if solution is None:
            log.error("No valid major item shuffle exists with current constraints")
            return False

        # Write solution back to data table
        self.last_solution_indices = solver.last_solution_indices.copy() if solver.last_solution_indices else None
        self.last_solution_map = solver.last_solution.copy() if solver.last_solution else None
        self._WriteSolutionToDataTable(solution)

        # Replace shop 4 right position with fairy if shuffle_shop_bait is enabled
        self._ReplaceBaitWithFairy()

        log.info("Major item randomization completed successfully")
        return True

    def _CollectLocationsAndItems(self) -> list[LocationItemPair]:
        """Collect all major item locations and their current items.

        Returns:
            List of LocationItemPair namedtuples containing location and item info.
        """

        location_item_pairs: list[LocationItemPair] = []
        collector = RoomItemCollector(self.data_table)

        # Collect location items from dungeons (levels 1-9)
        room_item_pair_lists = collector.CollectAll()

        # Keep only Major Items and Heart Containers (conditionally)
        for level_num, pairs in room_item_pair_lists.items():
            for pair in pairs:
                include_item = False

                # Always include major items
                if pair.item.IsMajorItem():
                    include_item = True

                # Only include heart containers if shuffle_dungeon_hearts is enabled
                elif pair.item == Item.HEART_CONTAINER:
                    include_item = self.flags.shuffle_dungeon_hearts

                # Include bombs, keys, and five_rupees if shuffle_minor_dungeon_items is enabled
                # TODO: When shuffle_minor_dungeon_items is enabled, we should also force
                # shuffle_minor_items to be enabled to ensure consistency. This should be
                # implemented in a separate PR.
                elif pair.item in [Item.BOMBS, Item.KEY, Item.FIVE_RUPEES]:
                    include_item = self.flags.shuffle_minor_dungeon_items

                if include_item:
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
            # Note: When shuffle_shop_bait is enabled, SHOP_4 RIGHT position will be replaced
            # with a fairy after the shuffle completes (see _ReplaceBaitWithFairy method)
            (CaveType.POTION_SHOP, CavePosition.LEFT, self.flags.shuffle_potion_shop_items),
            (CaveType.POTION_SHOP, CavePosition.RIGHT, self.flags.shuffle_potion_shop_items),
        ]

        for cave_type, position, should_add in locations:
            if should_add:
                # Convert CavePosition enum (0-indexed) to 1-indexed for DataTable
                position_1indexed = int(position) + 1
                item = self.data_table.GetCaveItemNew(cave_type, position_1indexed)
                if item and item != Item.NO_ITEM and item != Item.OVERWORLD_NO_ITEM:
                    location = CaveLocation(cave_type, position)
                    pairs.append(LocationItemPair(location, item))

        return pairs

    def _solver_seed(self, seed: int | None) -> Optional[int]:
        """Normalize the provided seed into the range expected by OR-Tools."""
        if seed is None:
            return None
        solver_seed = seed % 2147483647
        if solver_seed == 0:
            solver_seed = 1
        return solver_seed

    def _ValidateConstraints(self, locations: list[Union[DungeonLocation, CaveLocation]],
                            items: list[Item]) -> None:
        """Validate that flag settings don't create impossible constraints.

        Raises:
            ConstraintConflictError: If flag combinations are impossible to satisfy.
        """
        # Count available heart containers in the pool
        heart_container_count = items.count(Item.HEART_CONTAINER)

        # Check for impossible force-to-location constraints
        errors = []

        # Validate force_heart_container_to_armos
        if self.flags.force_heart_container_to_armos:
            if not self.flags.shuffle_armos_item:
                errors.append(
                    "Flag 'Force heart container to Armos' requires 'Shuffle the Armos Item' to be enabled."
                )
            elif heart_container_count == 0:
                errors.append(
                    "Flag 'Force heart container to Armos' requires at least one heart container in the pool. "
                    "Enable 'Shuffle Dungeon Hearts' or 'Shuffle the Coast Item'."
                )

        # Validate force_heart_container_to_coast
        if self.flags.force_heart_container_to_coast:
            if not self.flags.shuffle_coast_item:
                errors.append(
                    "Flag 'Force heart container to Coast' requires 'Shuffle the Coast Item' to be enabled."
                )
            elif heart_container_count == 0:
                errors.append(
                    "Flag 'Force heart container to Coast' requires at least one heart container in the pool. "
                    "Enable 'Shuffle Dungeon Hearts' or 'Shuffle the Armos Item'."
                )

        # Validate force_heart_container_to_level_nine
        if self.flags.force_heart_container_to_level_nine:
            if heart_container_count == 0:
                errors.append(
                    "Flag 'Force a heart container to be in level 9' requires at least one heart container in the pool. "
                    "Enable 'Shuffle Dungeon Hearts', 'Shuffle the Coast Item', or 'Shuffle the Armos Item'."
                )

        # Validate force_two_heart_containers_to_level_nine
        if self.flags.force_two_heart_containers_to_level_nine:
            if heart_container_count < 2:
                errors.append(
                    f"Flag 'Force two heart containers to be in level 9' requires at least 2 heart containers in the pool, "
                    f"but only {heart_container_count} available. Enable 'Shuffle Dungeon Hearts' to add 8 more heart containers, "
                    f"or enable both 'Shuffle the Coast Item' and 'Shuffle the Armos Item' for 2 total."
                )

            # Check for conflict with force_heart_container_to_level_nine
            if self.flags.force_heart_container_to_level_nine:
                errors.append(
                    "Flags 'Force two heart containers to level 9' and 'Force a heart container to level 9' "
                    "cannot be enabled together. Level 9 has only 2 item slots, so forcing 3 total is impossible."
                )

        # If there are any errors, raise an exception with all of them
        if errors:
            error_message = "Impossible flag combination detected:\n\n" + "\n\n".join(f"• {error}" for error in errors)
            raise ConstraintConflictError(error_message)

    def _AddConstraints(self, solver,
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
            # Forbid ALL progressive items (both base and enhanced) from shops
            progressive_items = [item for item in items if item.IsProgressiveUpgradeItem()]
            solver.forbid_all(sources=shop_locations, targets=progressive_items)
            log.debug(f"Constraint: {len(progressive_items)} progressive items forbidden from shops")

        # 3. Ladder cannot go in coast location (requires ladder to access)
        coast_locations = [loc for loc in locations if is_cave_location(loc) and loc.cave_type == CaveType.COAST_ITEM]
        if Item.LADDER in items and coast_locations:
            solver.forbid_all(sources=coast_locations, targets=Item.LADDER)
            log.debug("Constraint: Ladder forbidden from coast location")

        # 4. Shop-only items cannot go in dungeons (due to 5-bit item field overflow)
        # Dungeon rooms can only hold items 0-31 (0x00-0x1F) due to 5-bit field
        # Items > 31: RED_POTION (0x20), SINGLE_HEART (0x22), FAIRY (0x23), OVERWORLD_NO_ITEM (0x3F)
        dungeon_locations = [loc for loc in locations if is_dungeon_location(loc)]
        shop_only_items = [item for item in items if int(item) > 31]
        if dungeon_locations and shop_only_items:
            for dungeon_loc in dungeon_locations:
                for shop_item in shop_only_items:
                    solver.forbid(source=dungeon_loc, target=shop_item)
            log.debug(f"Constraint: {len(shop_only_items)} shop-only items forbidden from {len(dungeon_locations)} dungeon locations (5-bit field limit)")

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

        # Force TWO heart containers to level 9 (using require constraints)
        if self.flags.force_two_heart_containers_to_level_nine:
            level_9_locations = [loc for loc in locations if is_dungeon_location(loc) and loc.level_num == 9]
            if level_9_locations and Item.HEART_CONTAINER in items:
                # Force heart containers into first two level 9 locations
                # This ensures 2 different locations in level 9 have heart containers
                for i in range(min(2, len(level_9_locations))):
                    solver.require(source=level_9_locations[i], target=Item.HEART_CONTAINER)
                    log.debug(f"Constraint: Heart container required at Level 9 Location {i+1}")

        self._ForceItemsToLocation(solver, locations, items, [
            (self.flags.force_heart_container_to_armos and self.flags.shuffle_armos_item,
             CaveType.ARMOS_ITEM, [Item.HEART_CONTAINER], "Armos"),
            (self.flags.force_heart_container_to_coast and self.flags.shuffle_coast_item,
             CaveType.COAST_ITEM, [Item.HEART_CONTAINER], "Coast"),
        ])

        # Note: force_major_item_to_boss and force_major_item_to_triforce_room are
        # intra-dungeon constraints, handled by DungeonItemRandomizer, not here

    def _ForceItemsToLevel9(self, solver,
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

    def _ForceItemsToLocation(self, solver,
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
                self.data_table.SetCaveItemNew(location.cave_type, position_1indexed, item)
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
        # Tier 1: Sword, Ring, Any Key - 230 ± 25
        if item in [Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD,
                    Item.BLUE_RING, Item.RED_RING, Item.MAGICAL_KEY]:
            return self.rng.randint(205, 255)

        # Tier 2: Bow, Wand, Ladder - 100 ± 20
        elif item in [Item.BOW, Item.WAND, Item.LADDER]:
            return self.rng.randint(80, 120)

        # Tier 3: Recorder, Arrows, HC - 80 ± 20
        elif item in [Item.RECORDER, Item.WOOD_ARROWS, Item.SILVER_ARROWS, Item.HEART_CONTAINER]:
            return self.rng.randint(60, 100)

        # Tier 4: Everything else - 60 ± 20
        else:
            return self.rng.randint(40, 80)

    def _ReplaceBaitWithFairy(self) -> None:
        """Replace the right position of shop 4 with a fairy if shuffle_shop_bait is enabled.

        When shuffle_shop_bait is enabled, one bait is shuffled into the major item pool,
        and the right position of shop 4 is replaced with a fairy that costs 20-40 rupees.
        """
        if not self.flags.shuffle_shop_bait:
            return

        # Replace shop 4's right position (position 3 in 1-indexed) with a fairy
        position_1indexed = 3
        self.data_table.SetCaveItemNew(CaveType.SHOP_4, position_1indexed, Item.FAIRY)

        # Set the fairy's price to a random amount between 20 and 40 rupees
        fairy_price = self.rng.randint(20, 40)
        self.data_table.SetCavePrice(CaveType.SHOP_4, position_1indexed, fairy_price)

        log.info(f"Replaced SHOP_4 right position with FAIRY at {fairy_price} rupees")
