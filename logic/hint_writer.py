import logging as log
from typing import List, Dict

from rng.random_number_generator import RandomNumberGenerator
from .patch import Patch
from .randomizer_constants import HintType
from .hints import COMMUNITY_HINTS, NUMERICAL_HINTS


class HintWriter:
    """Writes hints to Legend of Zelda ROM."""

    # ROM file offsets (accounting for 0x10 NES header)
    # The NES maps 0x4000 in ROM file to 0x8000 in memory (Bank 1 starts at 0x8000)
    NES_HEADER_SIZE = 0x10
    HINT_POINTER_TABLE_START = 0x4010  # File offset for pointer table
    HINT_DATA_START = 0x405C  # File offset where hint data starts (0x404C + 0x10)
    NUM_HINT_SLOTS = 0x26  # 38 hint slots
    MAX_HINT_DATA_END = 0x4550  # Maximum file offset for hint data (with safety margin; hard limit is 0x4582)

    # Text encoding table
    CHAR_TO_BYTE = {
        '0': 0x00, '1': 0x01, '2': 0x02, '3': 0x03, '4': 0x04,
        '5': 0x05, '6': 0x06, '7': 0x07, '8': 0x08, '9': 0x09,
        'A': 0x0A, 'B': 0x0B, 'C': 0x0C, 'D': 0x0D, 'E': 0x0E,
        'F': 0x0F, 'G': 0x10, 'H': 0x11, 'I': 0x12, 'J': 0x13,
        'K': 0x14, 'L': 0x15, 'M': 0x16, 'N': 0x17, 'O': 0x18,
        'P': 0x19, 'Q': 0x1A, 'R': 0x1B, 'S': 0x1C, 'T': 0x1D,
        'U': 0x1E, 'V': 0x1F, 'W': 0x20, 'X': 0x21, 'Y': 0x22,
        'Z': 0x23, ' ': 0x24, '~': 0x25, ',': 0x28, '!': 0x29,
        "'": 0x2A, '&': 0x2B, '.': 0x2C, '"': 0x2D, '?': 0x2E,
        '-': 0x2F
    }

    def SetLostHillsHint(self, directions: List[int]) -> None:
        """
        Generate and set Lost Hills hint text from direction sequence.

        Args:
            directions: List of 4 direction values (0x08=Up, 0x04=Down, 0x01=Right)
        """
        # Map direction values to text
        dir_map = {0x08: "UP", 0x04: "DOWN", 0x01: "RIGHT"}

        # Convert directions to text
        dir_text = [dir_map.get(d, "UP") for d in directions]

        # Format: "GO {dir1}, {dir2}," / "{dir3}, {dir4}" / "THE MOUNTAIN AHEAD"
        hint_text = f"GO {dir_text[0]}, {dir_text[1]},|{dir_text[2]}, {dir_text[3]}|THE MOUNTAIN AHEAD"
        self.SetHint(HintType.LOST_HILLS_HINT, hint_text)

    def SetDeadWoodsHint(self, directions: List[int]) -> None:
        """
        Generate and set Dead Woods hint text from direction sequence.

        Args:
            directions: List of 4 direction values (0x08=North, 0x04=South, 0x02=West)
        """
        # Map direction values to text
        dir_map = {0x08: "NORTH", 0x04: "SOUTH", 0x02: "WEST"}

        # Convert directions to text
        dir_text = [dir_map.get(d, "NORTH") for d in directions]

        # Format: "GO {dir1}, {dir2}," / "{dir3}, {dir4} TO" / "THE FOREST OF MAZE"
        hint_text = f"GO {dir_text[0]}, {dir_text[1]},|{dir_text[2]}, {dir_text[3]} TO|THE FOREST OF MAZE"
        self.SetHint(HintType.DEAD_WOODS_HINT, hint_text)

    def SetWhiteSwordHeartHint(self, heart_requirement: int) -> None:
        """
        Generate and set White Sword cave hint based on heart requirement.

        Args:
            heart_requirement: The number of hearts required (4, 5, or 6)

        Raises:
            ValueError: If heart_requirement is not 4, 5, or 6
        """
        if heart_requirement not in NUMERICAL_HINTS:
            raise ValueError(f"Invalid white sword heart requirement: {heart_requirement}. Must be 4, 5, or 6.")

        hint_text = self.rng.choice(NUMERICAL_HINTS[heart_requirement])
        self.SetHint(HintType.WHITE_SWORD_CAVE, hint_text)

    def SetMagicalSwordHeartHint(self, heart_requirement: int) -> None:
        """
        Generate and set Magical Sword cave hint based on heart requirement.

        Args:
            heart_requirement: The number of hearts required (10, 11, or 12)

        Raises:
            ValueError: If heart_requirement is not 10, 11, or 12
        """
        if heart_requirement not in NUMERICAL_HINTS:
            raise ValueError(f"Invalid magical sword heart requirement: {heart_requirement}. Must be 10, 11, or 12.")

        hint_text = self.rng.choice(NUMERICAL_HINTS[heart_requirement])
        self.SetHint(HintType.MAGICAL_SWORD_CAVE, hint_text)

    def __init__(self, rng: RandomNumberGenerator):
        """Initialize the hint writer.

        Args:
            rng: RandomNumberGenerator instance for deterministic hint selection
        """
        self.rng = rng
        self.patch = Patch()
        self.hints: Dict[HintType, str] = {}

    def SetHint(self, hint_type: HintType, hint: str) -> None:
        """Set a hint for a specific hint type.

        Args:
            hint_type: The type of hint to set
            hint: The hint text as a pipe-separated string (e.g., "LINE1|LINE2|LINE3")
        """
        self.hints[hint_type] = hint

    def FillWithCommunityHints(self) -> None:
        """Fill empty hint slots with community hints.

        Hints 10, 12, 13, and 14 are left blank (single 0xFF byte).
        """
        # Hint numbers that should be blank
        blank_hint_nums = {10, 12, 13, 14}

        for hint_num in range(1, self.NUM_HINT_SLOTS + 1):
            hint_type = HintType(hint_num)
            if hint_type not in self.hints:
                # Make hints 10, 12, 13, 14 blank
                if hint_num in blank_hint_nums:
                    self.hints[hint_type] = " "
                elif hint_type in COMMUNITY_HINTS:
                    chosen = self.rng.choice(COMMUNITY_HINTS[hint_type])
                    self.hints[hint_type] = chosen
                else:
                    chosen = self.rng.choice(COMMUNITY_HINTS[HintType.OTHER])
                    self.hints[hint_type] = chosen

    def FillWithBlankHints(self) -> None:
        """Fill all hint slots with blank hints."""
        for hint_num in range(1, self.NUM_HINT_SLOTS + 1):
            hint_type = HintType(hint_num)
            if hint_type not in self.hints:
                self.hints[hint_type] = " "

    def GetPatch(self) -> Patch:
        """Generate a patch with hint data.

        Returns:
            Patch object with hint pointers and data
        """
        log.debug("Writing hints to ROM.")

        # Track current write position in ROM
        current_file_offset = self.HINT_DATA_START

        # Iterate through ALL hint slots in order
        for hint_num in range(1, self.NUM_HINT_SLOTS + 1):
            hint_type = HintType(hint_num)

            # Get hint text (if not set, use a blank)
            if hint_type not in self.hints:
                log.warning(f"Hint #{hint_num} not set. Using blank hint.")
                hint_text = " "
            else:
                hint_text = self.hints[hint_type]

            # Parse the hint text into lines
            lines = hint_text.split('|')

            # Encode the hint text
            encoded_hint = self._encode_text(lines)

            # Check if writing this hint would exceed the limit
            if current_file_offset + len(encoded_hint) >= self.MAX_HINT_DATA_END:
                # Would exceed limit - write a blank hint instead
                log.warning(f"Hint #{hint_num} would exceed ROM limit (0x{self.MAX_HINT_DATA_END:04X}). Writing blank hint instead.")
                encoded_hint = self._encode_text([" "])

                # Still check if even the blank hint fits
                if current_file_offset + len(encoded_hint) >= self.MAX_HINT_DATA_END:
                    log.error(f"Cannot fit any more hints after hint #{hint_num-1}. Pointer table will be incomplete!")
                    break
            # Calculate the pointer value (offset from pointer table start in ROM file)
            pointer_offset = current_file_offset - self.HINT_POINTER_TABLE_START

            # Write the encoded hint data
            self.patch.AddData(current_file_offset, encoded_hint)
            current_file_offset += len(encoded_hint)

            # Write pointer in little-endian format with 0x80 OR'd into high byte
            # Hint index is 0-based for pointer table (hint_num - 1)
            pointer_file_offset = self.HINT_POINTER_TABLE_START + ((hint_num - 1) * 2)
            low_byte = pointer_offset & 0xFF
            high_byte = ((pointer_offset >> 8) & 0xFF) | 0x80
            pointer_bytes = [low_byte, high_byte]
            self.patch.AddData(pointer_file_offset, pointer_bytes)

        return self.patch

    def _encode_text(self, lines: List[str]) -> List[int]:
        """
        Encode text lines into ROM format.

        Args:
            lines: List of text lines (1-3 lines, max 20 chars each)

        Returns:
            List of bytes representing the encoded text
        """
        result = []

        # Special case: blank hint (empty or all empty lines)
        has_content = any(line.strip() for line in lines)
        if not has_content:
            # Return single 0xFF byte for blank hints
            return [0xFF]

        for line_num, line in enumerate(lines):
            # Strip trailing spaces
            line = line.rstrip()

            # Skip empty lines
            if not line:
                continue

            # Calculate leading padding (using 0x25, not 0x24)
            # Each line is 24 chars total: 1 leading space min + up to 22 text + 1 implied trailing space
            line_len = len(line)
            max_text_len = 22

            if line_len > max_text_len:
                # Truncate if too long
                line = line[:max_text_len]
                line_len = max_text_len

            # Center the text: total 22 text positions available
            # For centering, we split the padding (22 - line_len) between left and right
            # But we always need at least 1 leading space
            available_padding = 22 - line_len

            if available_padding >= 2:
                # We have room to center
                # For even padding, split evenly; for odd padding, bias left
                if available_padding % 2 == 0:
                    left_padding = (available_padding // 2) + 1  # +1 for the required leading space
                else:
                    left_padding = (available_padding // 2) + 2  # +2 for bias left + required leading
            else:
                # Just use 1 leading space (minimum required)
                left_padding = 1

            # Add leading spaces using 0x25
            for _ in range(left_padding):
                result.append(0x25)

            # Encode the actual text (no trailing spaces)
            for char in line:
                char_upper = char.upper()
                if char_upper not in self.CHAR_TO_BYTE:
                    # Unknown character - use 0x25
                    byte_val = 0x25
                else:
                    byte_val = self.CHAR_TO_BYTE[char_upper]
                result.append(byte_val)

            # Set line break bits on the last character of this line
            if result and line_num < len(lines) - 1:
                if line_num == 0:
                    result[-1] |= 0x80  # Start second line
                elif line_num == 1:
                    result[-1] |= 0x40  # Start third line

        # Mark end of text (set both bits 6 and 7 on last byte)
        if result:
            result[-1] |= 0xC0

        return result
