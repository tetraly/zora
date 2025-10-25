"""State management classes for the ZORA UI."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from logic.flags import FlagsEnum, Flags


# ============================================================================
# FLAG STATE MANAGEMENT
# ============================================================================

class FlagState:
    """Manages the state of randomizer flags."""

    # Class-level constants for flagstring encoding
    LETTER_MAP = ['B', 'C', 'D', 'F', 'G', 'H', 'K', 'L']
    VALID_LETTERS = {'B': 0, 'C': 1, 'D': 2, 'F': 3, 'G': 4, 'H': 5, 'K': 6, 'L': 7}

    def __init__(self):
        # Create a dictionary to store flag states, excluding complex flags
        self.flags = {}
        self.complex_flags = {'starting_items', 'skip_items'}

        for flag in FlagsEnum:
            if flag.value not in self.complex_flags:
                self.flags[flag.value] = False

        self.seed = ""

    def to_flagstring(self) -> str:
        """Convert flag state to a 5-letter flagstring.

        Each letter represents 3 flags in octal format:
        B=000, C=001, D=010, F=011, G=100, H=101, K=110, L=111
        (Avoiding A, E, I, O, U vowels)
        """

        # Get all non-complex flags in order
        non_complex_flags = [f for f in FlagsEnum if f.value not in self.complex_flags]

        # Build binary string from flags
        binary_str = ''.join('1' if self.flags.get(f.value, False) else '0' for f in non_complex_flags)

        # Pad to multiple of 3 if needed
        while len(binary_str) % 3 != 0:
            binary_str += '0'

        # Convert to letter format (3 bits per letter)
        letters = []
        for i in range(0, len(binary_str), 3):
            chunk = binary_str[i:i+3]
            octal_value = int(chunk, 2)
            letters.append(self.LETTER_MAP[octal_value])

        return ''.join(letters)

    def from_flagstring(self, flagstring: str) -> bool:
        """Parse a flagstring and update state.

        Returns:
            bool: True if valid flagstring, False otherwise
        """
        s = flagstring.strip().upper()

        # Check if all characters are valid letters
        if not all(c in self.VALID_LETTERS for c in s):
            return False

        # Convert letters to binary string
        binary_str = ''
        for letter in s:
            octal_value = self.VALID_LETTERS[letter]
            binary_str += format(octal_value, '03b')

        # Apply to flags
        non_complex_flags = [f for f in FlagsEnum if f.value not in self.complex_flags]
        for i, flag in enumerate(non_complex_flags):
            if i < len(binary_str):
                self.flags[flag.value] = binary_str[i] == '1'

        return True

    def to_randomizer_flags(self):
        """Convert FlagState to a Flags object for the randomizer.

        Returns:
            Flags: A Flags object with all enabled flags set
        """
        randomizer_flags = Flags()
        for flag_key, flag_value in self.flags.items():
            if flag_value:  # Only set flags that are True
                setattr(randomizer_flags, flag_key, True)
        return randomizer_flags


class RomInfo:
    """Stores information about the loaded ROM."""

    def __init__(self):
        self.filename = ""
        self.rom_type = ""
        self.flagstring = ""
        self.seed = ""
        self.code = ""

    def clear(self) -> None:
        """Reset all ROM info."""
        self.filename = ""
        self.rom_type = ""
        self.flagstring = ""
        self.seed = ""
        self.code = ""
