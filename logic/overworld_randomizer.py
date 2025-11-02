
import random
import logging as log
from typing import List, Tuple

from .data_table import DataTable
from .flags import Flags
from .patch import Patch
from .randomizer_constants import CaveType, Range
from .rom_data_specs import RomDataType

# Screen location constants for constraint-based shuffling
VANILLA_LEVEL_SCREENS = [
    0x37,  # First quest Level 1
    0x3C,  # First quest Level 2
    0x74,  # First quest Level 3
    0x45,  # First quest Level 4
    0x0B,  # First quest Level 5
    0x22,  # First quest Level 6
    0x42,  # First quest Level 7
    0x6D,  # First quest Level 8
    0x05,  # First quest Level 9
]

# Expanded screen pool: vanilla 9 + 5 additional screens from second quest levels
EXPANDED_LEVEL_SCREENS = [
    0x37,  # First quest Level 1
    0x3C,  # First quest Level 2
    0x74,  # First quest Level 3
    0x45,  # First quest Level 4
    0x0B,  # First quest Level 5
    0x22,  # First quest Level 6
    0x42,  # First quest Level 7
    0x6D,  # First quest Level 8
    0x05,  # First quest Level 9
    0x34,  # Second quest Level 2
    0x1B,  # Second quest Level 4
    0x30,  # Second quest Level 6
    0x19,  # Second quest Level 8
    0x00,  # Second quest Level 9
]


class OverworldRandomizer:
    """Handles overworld randomization logic including:
    - Cave destination shuffling
    - Recorder warp updates
    - Heart requirement randomization
    - Lost Hills and Dead Woods randomization
    - Extra block type enablement (raft blocks, power bracelet blocks)
    """

    def __init__(self, data_table: DataTable, flags: Flags):
        """Initialize the overworld randomizer.

        Args:
            data_table: DataTable instance for ROM access
            flags: Flags instance for configuration
        """
        self.data_table = data_table
        self.flags = flags
        self.cave_destinations_randomized_in_base_seed = False

        # Track which features have been enabled for patch generation
        self._lost_hills_enabled = False
        self._dead_woods_enabled = False

    def HasVanillaWoodSwordCaveStartScreen(self) -> bool:
        """Check if the wood sword cave is at its vanilla screen location.

        The vanilla wood sword cave is at screen 0x77. If it's not there,
        we assume the base ROM has cave destinations already shuffled.

        Returns:
            Whether the wood sword cave is in its vanilla screen (0x77)
        """
        VANILLA_WOOD_SWORD_SCREEN = 0x77
        destination = self.data_table.GetScreenDestination(VANILLA_WOOD_SWORD_SCREEN)
        return destination == CaveType.WOOD_SWORD_CAVE

    def DetectPreShuffledCaves(self) -> bool:
        """Detect if cave destinations are already randomized in the base ROM.

        Returns:
            True if caves appear to be pre-shuffled
        """
        if not self.HasVanillaWoodSwordCaveStartScreen():
            self.cave_destinations_randomized_in_base_seed = True
            log.debug("Detected shuffled caves in base ROM - auto-enabling cave shuffle")
            return True
        return False

    def RandomizeHeartRequirements(self) -> None:
        """Randomize sword cave heart requirements based on flags."""
        if self.flags.randomize_heart_container_requirements:
            white_sword_hearts = random.choice([4, 5, 6])
            self.data_table.SetRomData(RomDataType.WHITE_SWORD_HEART_REQUIREMENT, white_sword_hearts)

        if self.flags.shuffle_magical_sword_cave_item or self.flags.randomize_heart_container_requirements:
            magical_sword_hearts = random.choice([10, 11, 12])
            self.data_table.SetRomData(RomDataType.MAGICAL_SWORD_HEART_REQUIREMENT, magical_sword_hearts)

    def ShuffleCaveDestinations(self) -> None:
        """Shuffle cave destinations for all 1st quest overworld screens.

        This finds all screens that have cave destinations in the 1st quest,
        then randomly redistributes those destinations among those same screens.

        Any Road screens are excluded from the shuffle to prevent game crashes.

        Uses either simple random.shuffle() or OR-Tools constraint solver depending
        on whether constraint flags are enabled.
        """
        import time

        # Collect screens and destinations
        any_road_screens = self.data_table.GetRomData(RomDataType.ANY_ROAD_SCREENS)
        log.debug(f"Any Road screen IDs: {[hex(x) for x in any_road_screens]}")

        first_quest_screens = []
        cave_destinations = []

        for screen_num in range(0x80):
            # Only shuffle screens that appear in 1st quest (bit 7 is not set)
            table5_byte = self.data_table.overworld_raw_data[screen_num + 5*0x80]
            if (table5_byte & 0x80) != 0:
                continue

            destination = self.data_table.GetScreenDestination(screen_num)

            # Only include screens that actually have a destination
            if destination != CaveType.NONE:
                # Exclude any road screens from the shuffle to prevent crashes
                if screen_num not in any_road_screens:
                    first_quest_screens.append(screen_num)
                    cave_destinations.append(destination)
                else:
                    log.debug(f"Excluding Any Road screen {hex(screen_num)} from shuffle")

        log.debug(f"Found {len(first_quest_screens)} first quest screens with cave destinations (excluding Any Road screens)")

        # Check if we need constraint-based shuffling
        use_constraints = (
            self.flags.pin_wood_sword_cave or
            self.flags.restrict_levels_to_vanilla_screens or
            self.flags.restrict_levels_to_expanded_screens
        )

        if use_constraints:
            # Use OR-Tools constraint solver
            start_time = time.time()
            self._ShuffleCaveDestinationsWithConstraints(first_quest_screens, cave_destinations)
            elapsed = time.time() - start_time
            log.debug(f"Constraint-based shuffle took {elapsed*1000:.2f}ms")
        else:
            # Use simple random shuffle
            start_time = time.time()
            self._ShuffleCaveDestinationsSimple(first_quest_screens, cave_destinations)
            elapsed = time.time() - start_time
            log.debug(f"Simple shuffle took {elapsed*1000:.2f}ms")

    def _ShuffleCaveDestinationsSimple(
        self,
        first_quest_screens: List[int],
        cave_destinations: List[CaveType]
    ) -> None:
        """Simple random shuffle of cave destinations (original algorithm).

        Args:
            first_quest_screens: List of screen numbers to shuffle
            cave_destinations: List of cave destinations to shuffle
        """
        for screen_num, destination in zip(first_quest_screens, cave_destinations):
            log.debug(f"BEFORE: Screen {hex(screen_num)}: {destination.name}")

        # Shuffle the destinations
        random.shuffle(cave_destinations)

        # Redistribute shuffled destinations back to the screens
        for screen_num, new_destination in zip(first_quest_screens, cave_destinations):
            log.debug(f"AFTER: Setting screen {hex(screen_num)} to {new_destination.name}")
            self.data_table.SetScreenDestination(screen_num, new_destination)

    def _ShuffleCaveDestinationsWithConstraints(
        self,
        first_quest_screens: List[int],
        cave_destinations: List[CaveType]
    ) -> None:
        """Constraint-based shuffle using OR-Tools.

        This shuffles which screen gets which cave using a permutation solver.
        The solver handles duplicate cave types automatically.

        This allows expressing constraints like:
        - Screen 0x77 must get wood sword cave
        - These 15 screens can only get level caves
        - etc.

        Args:
            first_quest_screens: List of screen numbers to shuffle
            cave_destinations: List of cave destinations (in same order as screens)
        """
        from .assignment_solver import AssignmentSolver

        # Create solver and define the permutation problem
        solver = AssignmentSolver()
        solver.add_permutation_problem(
            keys=first_quest_screens,  # Screens (unique)
            values=cave_destinations   # Caves (can have duplicates like 9x DOOR_REPAIR)
        )

        # Apply constraint flags
        # Constraint #1: Pin wood sword cave to vanilla screen
        if self.flags.pin_wood_sword_cave:
            solver.require(0x77, CaveType.WOOD_SWORD_CAVE)
            log.debug("Constraint: Wood Sword Cave pinned to screen 0x77")

        # Constraint #2: Restrict levels to vanilla screens only
        # In permutation mode with allow_only, the API is backwards from what you'd expect:
        # - First param (sources/keys) = what screen gets restricted
        # - Second param (targets/values) = what caves are allowed on that screen
        # But we want to restrict "where can levels go", so we need to forbid levels from non-vanilla screens
        if self.flags.restrict_levels_to_vanilla_screens:
            level_caves = [
                CaveType.LEVEL_1, CaveType.LEVEL_2, CaveType.LEVEL_3,
                CaveType.LEVEL_4, CaveType.LEVEL_5, CaveType.LEVEL_6,
                CaveType.LEVEL_7, CaveType.LEVEL_8, CaveType.LEVEL_9
            ]
            # Find screens that are NOT vanilla level screens
            non_vanilla_screens = [s for s in first_quest_screens if s not in VANILLA_LEVEL_SCREENS]
            # Forbid levels from going to non-vanilla screens
            solver.forbid_group(non_vanilla_screens, level_caves)
            log.debug(f"Constraint: {len(level_caves)} levels forbidden from {len(non_vanilla_screens)} non-vanilla screens")

        # Constraint #3: Restrict levels to expanded screen pool
        if self.flags.restrict_levels_to_expanded_screens:
            level_caves = [
                CaveType.LEVEL_1, CaveType.LEVEL_2, CaveType.LEVEL_3,
                CaveType.LEVEL_4, CaveType.LEVEL_5, CaveType.LEVEL_6,
                CaveType.LEVEL_7, CaveType.LEVEL_8, CaveType.LEVEL_9
            ]
            # Find screens that are NOT in the expanded pool
            non_expanded_screens = [s for s in first_quest_screens if s not in EXPANDED_LEVEL_SCREENS]
            # Forbid levels from going to non-expanded screens
            solver.forbid_group(non_expanded_screens, level_caves)
            log.debug(f"Constraint: {len(level_caves)} levels forbidden from {len(non_expanded_screens)} non-expanded screens")

        # Solve with the current random seed
        solution = solver.solve(seed=random.randint(0, 2**31 - 1))

        if solution is None:
            raise ValueError("Could not find valid cave shuffle solution - constraints may be contradictory")

        # Apply the solution (screen -> cave mapping)
        for screen_num, cave_dest in solution.items():
            log.debug(f"AFTER: Setting screen {hex(screen_num)} to {cave_dest.name}")
            self.data_table.SetScreenDestination(screen_num, cave_dest)

    def UpdateRecorderWarps(self) -> None:
        """Calculate and update recorder warp destinations for levels 1-8 after cave shuffle.

        The recorder warps Link to a screen one to the left of each level entrance.
        Y-coordinates are adjusted based on the level's screen position.
        """
        warp_destinations = []
        y_coordinates = []

        # For each level (1-8), find its screen and calculate warp destination
        for level_num in range(1, 9):
            level_screen = None

            # Search all overworld screens to find this level
            for screen_num in range(0x80):
                destination = self.data_table.GetScreenDestination(screen_num)
                if destination == level_num:
                    level_screen = screen_num
                    break

            if level_screen is None:
                raise ValueError(f"Could not find screen for Level {level_num}")

            # Calculate warp destination (one screen to the left)
            # Special case: if level is at screen 0, don't subtract 1
            # Special case: letter cave at 0x0E (warp goes one screen down)
            if level_screen == 0:
                warp_screen = 0
            elif level_screen == 0x0E:
                warp_screen = 0x1D
            else:
                warp_screen = level_screen - 1

            # Special cases for y coordinate of Link warping to a screen
            if level_screen in [0x3B, 0x0A, 0x41, 0x05, 0x08, 0x09, 0x2B]:  # Vanilla 2, 5, 7, 9, Bogie's Arrow, Waterfall, Monocle Rock
                y_coord = 0xAD
            elif level_screen in [0x6C]:  # Vanilla 8
                y_coord = 0x5D
            else:
                y_coord = 0x8D

            log.debug(f"Level {level_num} at screen {hex(level_screen)}, recorder warp to {hex(warp_screen)}")
            warp_destinations.append(warp_screen)
            y_coordinates.append(y_coord)

        # Store in data_table
        self.data_table.SetRomData(RomDataType.RECORDER_WARP_DESTINATIONS, warp_destinations)
        self.data_table.SetRomData(RomDataType.RECORDER_WARP_Y_COORDINATES, y_coordinates)

    def RandomizeLostHills(self) -> List[int]:
        """Randomize Lost Hills direction sequence.

        Returns:
            List of 4 direction bytes for hint generation
        """
        # Generate 3 random directions from {Up, Right, Down} + Up at the end
        # Up=0x08, Down=0x04, Right=0x01
        direction_options = [0x08, 0x04, 0x01]  # Up, Down, Right
        lost_hills_directions = random.choices(direction_options, k=3)
        lost_hills_directions.append(0x08)  # Always Up at the end

        # Store in data_table
        self.data_table.SetRomData(RomDataType.LOST_HILLS_DIRECTIONS, lost_hills_directions)

        # Mark as enabled for patch generation
        self._lost_hills_enabled = True

        return lost_hills_directions

    def RandomizeDeadWoods(self) -> List[int]:
        """Randomize Dead Woods direction sequence.

        Returns:
            List of 4 direction bytes for hint generation
        """
        # Generate 3 random directions from {North, West, South} + South at the end
        # North=0x08, South=0x04, West=0x02
        direction_options = [0x08, 0x02, 0x04]  # North, West, South
        dead_woods_directions = random.choices(direction_options, k=3)
        dead_woods_directions.append(0x04)  # Always South at the end

        # Store in data_table
        self.data_table.SetRomData(RomDataType.DEAD_WOODS_DIRECTIONS, dead_woods_directions)

        # Mark as enabled for patch generation
        self._dead_woods_enabled = True

        return dead_woods_directions

    def _GetLostHillsOverworldPatches(self) -> Patch:
        """Generate overworld patches for Lost Hills randomization.

        These patches annex the two screens to the right of vanilla Level 5
        to create the Lost Hills area.
        """
        patch = Patch()
        patch.AddDataFromHexString(0x154D7, "01010101010101")
        patch.AddDataFromHexString(0x154F1, "09")
        patch.AddDataFromHexString(0x154F5, "06")
        patch.AddDataFromHexString(0x155DD, "02")
        patch.AddDataFromHexString(0x155F5, "51")
        return patch

    def _GetDeadWoodsOverworldPatches(self) -> Patch:
        """Generate overworld patches for Dead Woods randomization.

        These patches wall off southwest caves and add passage for non-screen-scrollers.
        """
        patch = Patch()
        # Wall off three southwest caves
        patch.AddDataFromHexString(0x15B08, "29")
        # Add passage from screen above Dead Woods to the west for non-screen-scrollers
        patch.AddDataFromHexString(0x158F8, "16")
        return patch

    def _GetExtraRaftBlocksPatches(self) -> Patch:
        """Generate patches for extra raft blocks feature."""
        patch = Patch()
        patch.AddDataFromHexString(0x154F8, "0C")
        patch.AddDataFromHexString(0x155F7, "0C 0C")
        patch.AddDataFromHexString(0x15613, "EB")
        patch.AddDataFromHexString(0x15615, "AF")
        patch.AddDataFromHexString(0x15715, "B6")
        patch.AddDataFromHexString(0x15765, "91 78")
        patch.AddDataFromHexString(0x1582F, "02 08 0B 0B 0B 0B 0B 0B 0B 0B 01")
        patch.AddDataFromHexString(0x1592F, "17 17")
        return patch

    def _GetExtraPowerBraceletBlocksPatches(self) -> Patch:
        """Generate patches for extra power bracelet blocks feature."""
        patch = Patch()
        patch.AddDataFromHexString(0x1554E, "38")
        patch.AddDataFromHexString(0x15554, "06E7000000")
        patch.AddDataFromHexString(0x15649, "00A9")
        patch.AddDataFromHexString(0x1564E, "B6")
        patch.AddDataFromHexString(0x1574E, "02")
        return patch

    def GetOverworldPatches(self) -> Patch:
        """Get all overworld-related patches based on what was randomized.

        Returns:
            Patch containing all overworld modifications
        """
        patch = Patch()

        # Lost Hills patches
        if self._lost_hills_enabled:
            patch += self._GetLostHillsOverworldPatches()

        # Dead Woods patches
        if self._dead_woods_enabled:
            patch += self._GetDeadWoodsOverworldPatches()

        # Extra blocks (check flags directly)
        if self.flags.extra_raft_blocks:
            patch += self._GetExtraRaftBlocksPatches()

        if self.flags.extra_power_bracelet_blocks:
            patch += self._GetExtraPowerBraceletBlocksPatches()

        return patch

    def Randomize(self) -> Tuple[List[int] | None, List[int] | None]:
        """Main randomization entry point.

        Performs all enabled overworld randomizations in the correct order.

        Returns:
            Tuple of (lost_hills_directions, dead_woods_directions) for hint generation.
            Either or both can be None if those randomizations are disabled.
        """
        lost_hills_directions = None
        dead_woods_directions = None

        # Shuffle cave destinations if enabled or detected in base ROM
        if self.flags.shuffle_caves or self.cave_destinations_randomized_in_base_seed:
            self.ShuffleCaveDestinations()
            self.UpdateRecorderWarps()

        # Randomize Lost Hills if enabled
        if self.flags.randomize_lost_hills:
            lost_hills_directions = self.RandomizeLostHills()

        # Randomize Dead Woods if enabled
        if self.flags.randomize_dead_woods:
            dead_woods_directions = self.RandomizeDeadWoods()

        return (lost_hills_directions, dead_woods_directions)
