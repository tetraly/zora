import logging as log
from typing import List, Tuple
from rng.random_number_generator import RandomNumberGenerator
from logic.data_table import DataTable
from logic.flags import Flags
from logic.randomizer_constants import CaveType

# Vanilla start screen
VANILLA_START_SCREEN = 0x77


class OverworldRandomizer:
    """Randomizer for overworld features like start screen location."""

    def __init__(self, data_table: DataTable, flags: Flags, rng: RandomNumberGenerator) -> None:
        """Initialize the OverworldRandomizer.

        Args:
            data_table: The DataTable instance to read from and write to
            flags: The Flags instance containing user settings
            rng: Random number generator for shuffling
        """
        self.data_table = data_table
        self.flags = flags
        self.rng = rng

    def _GetEasyStartScreens(self) -> List[int]:
        """Get the list of valid screens for easy start screen shuffle.

        Excludes screens that are too difficult or problematic for starting.
        Excluded screens (hex): 0x00-0x0F, 0x10-0x16, 0x19-0x1B, 0x1E, 0x1F,
        0x20-0x26, 0x2F, 0x30, 0x31, 0x33-0x36, 0x40, 0x41, 0x44, 0x45

        Returns:
            List of valid screen numbers for easy shuffle
        """
        # Define excluded screen ranges and individual screens
        excluded = set()

        # Add ranges
        excluded.update(range(0x00, 0x10))  # 0x00-0x0F
        excluded.update(range(0x10, 0x17))  # 0x10-0x16
        excluded.update(range(0x19, 0x1C))  # 0x19-0x1B
        excluded.update(range(0x20, 0x27))  # 0x20-0x26
        excluded.update(range(0x33, 0x37))  # 0x33-0x36

        # Add individual screens
        excluded.update([0x1E, 0x1F, 0x2F, 0x30, 0x31, 0x40, 0x41, 0x44, 0x45])

        # Generate list of all valid screens (0x00-0x7F minus excluded)
        valid_screens = [screen for screen in range(0x80) if screen not in excluded]

        log.debug(f"Easy start shuffle has {len(valid_screens)} valid screens")
        return valid_screens

    def ShuffleStartScreen(self) -> None:
        """Shuffle the overworld start screen location.

        If full_start_shuffle is enabled, any of the 0x80 screens is possible.
        Otherwise, only "easy" screens are used (excluding difficult/problematic areas).

        This also exchanges enemy type and quantity between the new start screen
        and the vanilla start screen (0x77) so that the new start has no enemies.
        """
        if not self.flags.shuffle_start_screen:
            log.debug("Start screen shuffle is disabled")
            return

        # Get current start screen (should be 0x77 in vanilla)
        old_start_screen = self.data_table.GetStartScreen()
        log.debug(f"Current start screen: {hex(old_start_screen)}")

        # Determine valid screens for shuffle
        if self.flags.full_start_shuffle:
            # Full shuffle: all 0x80 screens are valid
            valid_screens = list(range(0x80))
            log.debug("Using full start screen shuffle (all 0x80 screens)")
        else:
            # Easy shuffle: only safe screens
            valid_screens = self._GetEasyStartScreens()
            log.debug("Using easy start screen shuffle")

        # Choose a new random start screen
        new_start_screen = self.rng.choice(valid_screens)
        log.debug(f"Selected new start screen: {hex(new_start_screen)}")

        # Exchange enemy data between old and new start screens
        # This ensures the new start screen has no enemies (like vanilla 0x77)
        old_enemy_data = self.data_table.GetOverworldEnemyData(old_start_screen)
        new_enemy_data = self.data_table.GetOverworldEnemyData(new_start_screen)

        log.debug(f"Swapping enemy data: screen {hex(old_start_screen)} ({hex(old_enemy_data)}) "
                  f"<-> screen {hex(new_start_screen)} ({hex(new_enemy_data)})")

        self.data_table.SetOverworldEnemyData(old_start_screen, new_enemy_data)
        self.data_table.SetOverworldEnemyData(new_start_screen, old_enemy_data)

        # Set the new start screen
        self.data_table.SetStartScreen(new_start_screen)
        log.debug(f"Set start screen to {hex(new_start_screen)}")

        log.info(f"Shuffled start screen from {hex(old_start_screen)} to {hex(new_start_screen)}")

    def ShuffleCaveDestinations(self) -> None:
        """Shuffle cave destinations for all 1st quest overworld screens.

        This finds all screens that have cave destinations in the 1st quest,
        then randomly redistributes those destinations among those same screens.

        Any Road screens are excluded from the shuffle to prevent game crashes.
        """
        # Read the four "take any road" screen IDs from the data_table
        any_road_screens = self.data_table.get_any_road_screens()
        log.debug(f"Any Road screen IDs: {[hex(x) for x in any_road_screens]}")

        # Find all screens that have cave destinations and should appear in 1st quest
        first_quest_screens = []
        cave_destinations = []

        for screen_num in range(0x80):
            # Skip if this is a 2nd quest only screen
            if not self.data_table.is_screen_first_quest(screen_num):
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
        for screen_num, destination in zip(first_quest_screens, cave_destinations):
            log.debug(f"BEFORE: Screen {hex(screen_num)}: {destination.name}")

        # Shuffle the destinations
        self.rng.shuffle(cave_destinations)

        # Redistribute shuffled destinations back to the screens
        for screen_num, new_destination in zip(first_quest_screens, cave_destinations):
            log.debug(f"AFTER: Setting screen {hex(screen_num)} to {new_destination.name}")
            self.data_table.SetScreenDestination(screen_num, new_destination)

    def CalculateAndSetRecorderWarpDestinations(self) -> None:
        """Calculate and set recorder warp destinations for levels 1-8 after cave shuffle.

        The recorder warps Link to a screen one to the left of each level entrance.
        This is because the whirlwind scrolls Link to the right automatically.

        This method calculates the new warp destinations based on current cave
        destinations and writes them directly to the data_table.
        """
        # Map of level number to CaveType enum (levels 1-8)
        level_cave_types = [
            CaveType.LEVEL_1,
            CaveType.LEVEL_2,
            CaveType.LEVEL_3,
            CaveType.LEVEL_4,
            CaveType.LEVEL_5,
            CaveType.LEVEL_6,
            CaveType.LEVEL_7,
            CaveType.LEVEL_8
        ]

        warp_destinations = []
        warp_y_coordinates = []

        # For each level (1-8), find its screen and calculate warp destination
        for level_num, cave_type in enumerate(level_cave_types, start=1):
            level_screen = None

            # Search all overworld screens to find this level
            for screen_num in range(0x80):
                destination = self.data_table.GetScreenDestination(screen_num)
                if destination == cave_type:
                    level_screen = screen_num
                    break

            if level_screen is None:
                raise ValueError(f"Could not find screen for Level {level_num}")

            # Calculate warp destination (one screen to the left)
            # Special case: if level is at screen 0, don't subtract 1
            # Special case: if level is at screen 0x0E, warp to 0x1D (below)
            if level_screen == 0:
                warp_screen = 0
            elif level_screen == 0x0E:
                warp_screen = 0x1D
            else:
                warp_screen = level_screen - 1

            # Special cases for y coordinate of Link warping to a screen
            y_coordinate = 0x8D
            # Vanilla locations with lower Y coordinate (screens: L2, L5, L7, L9, Bogie's Arrow, Waterfall, Monocle Rock)
            if level_screen in [0x3C, 0x0B, 0x42, 0x05, 0x09, 0x0A, 0x2C]:
                y_coordinate = 0xAD
            # Vanilla L8 location
            elif level_screen in [0x6D]:
                y_coordinate = 0x5D

            log.debug(f"Level {level_num} at screen {hex(level_screen)}, recorder warp to {hex(warp_screen)}, Y={hex(y_coordinate)}")
            warp_destinations.append(warp_screen)
            warp_y_coordinates.append(y_coordinate)

        # Write the calculated warp data to data_table
        self.data_table.set_recorder_warp_destinations(warp_destinations)
        self.data_table.set_recorder_warp_y_coordinates(warp_y_coordinates)

        log.debug(f"Updated recorder warp destinations: {[hex(x) for x in warp_destinations]}")
        log.debug(f"Updated recorder y coordinates: {[hex(x) for x in warp_y_coordinates]}")

    def RandomizeHeartRequirements(self) -> None:
        """Randomize heart container requirements for sword caves based on flags.

        White Sword: Randomized to 4, 5, or 6 hearts if randomize_heart_container_requirements is set.
        Magical Sword: Randomized to 10, 11, or 12 hearts if randomize_heart_container_requirements
                       or shuffle_magical_sword_cave_item is set.
        """
        if self.flags.randomize_heart_container_requirements:
            ws_hearts = self.rng.choice([4, 5, 6])
            self.data_table.set_heart_container_requirement(ws_hearts, for_magical_sword=False)
            log.debug(f"Set white sword heart requirement to {ws_hearts}")

        if self.flags.shuffle_magical_sword_cave_item or self.flags.randomize_heart_container_requirements:
            ms_hearts = self.rng.choice([10, 11, 12])
            self.data_table.set_heart_container_requirement(ms_hearts, for_magical_sword=True)
            log.debug(f"Set magical sword heart requirement to {ms_hearts}")
