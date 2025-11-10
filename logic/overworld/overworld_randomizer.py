import logging as log
from typing import List
from rng.random_number_generator import RandomNumberGenerator
from logic.data_table import DataTable
from logic.flags import Flags

# Offset in level_info for the start screen/room
START_SCREEN_OFFSET = 0x2F

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

    def _GetStartScreen(self) -> int:
        """Get the current start screen from level info.

        Returns:
            The overworld start screen number (0x00-0x7F)
        """
        return self.data_table.level_info[0][START_SCREEN_OFFSET]

    def _SetStartScreen(self, screen_num: int) -> None:
        """Set the start screen in level info.

        Args:
            screen_num: The overworld screen number to set as start (0x00-0x7F)
        """
        assert 0 <= screen_num < 0x80, f"Invalid screen number: {hex(screen_num)}"
        self.data_table.level_info[0][START_SCREEN_OFFSET] = screen_num
        log.debug(f"Set start screen to {hex(screen_num)}")

    def _GetEnemyData(self, screen_num: int) -> int:
        """Get the enemy data byte for a screen from Table 2.

        The enemy data byte contains:
        - Bits 0-5: Enemy type
        - Bits 6-7: Enemy quantity code (0-3, indexes into quantity table)

        Args:
            screen_num: The overworld screen number (0x00-0x7F)

        Returns:
            The enemy data byte from Table 2
        """
        assert 0 <= screen_num < 0x80, f"Invalid screen number: {hex(screen_num)}"
        return self.data_table.overworld_raw_data[screen_num + 2 * 0x80]

    def _SetEnemyData(self, screen_num: int, enemy_data: int) -> None:
        """Set the enemy data byte for a screen in Table 2.

        Args:
            screen_num: The overworld screen number (0x00-0x7F)
            enemy_data: The enemy data byte to set (contains type and quantity code)
        """
        assert 0 <= screen_num < 0x80, f"Invalid screen number: {hex(screen_num)}"
        assert 0 <= enemy_data <= 0xFF, f"Invalid enemy data: {hex(enemy_data)}"
        self.data_table.overworld_raw_data[screen_num + 2 * 0x80] = enemy_data
        log.debug(f"Set enemy data for screen {hex(screen_num)} to {hex(enemy_data)}")

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
        old_start_screen = self._GetStartScreen()
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

        # Remove the current start screen from valid choices to ensure a change
        if old_start_screen in valid_screens:
            valid_screens.remove(old_start_screen)

        # Choose a new random start screen
        new_start_screen = self.rng.choice(valid_screens)
        log.debug(f"Selected new start screen: {hex(new_start_screen)}")

        # Exchange enemy data between old and new start screens
        # This ensures the new start screen has no enemies (like vanilla 0x77)
        old_enemy_data = self._GetEnemyData(old_start_screen)
        new_enemy_data = self._GetEnemyData(new_start_screen)

        log.debug(f"Swapping enemy data: screen {hex(old_start_screen)} ({hex(old_enemy_data)}) "
                  f"<-> screen {hex(new_start_screen)} ({hex(new_enemy_data)})")

        self._SetEnemyData(old_start_screen, new_enemy_data)
        self._SetEnemyData(new_start_screen, old_enemy_data)

        # Set the new start screen
        self._SetStartScreen(new_start_screen)

        log.info(f"Shuffled start screen from {hex(old_start_screen)} to {hex(new_start_screen)}")
