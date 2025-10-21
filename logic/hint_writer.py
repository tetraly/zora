import logging as log
import random
from typing import List, Dict

from .patch import Patch
from .randomizer_constants import HintType


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

    # Community hints adapted from text_randomizer.py
    # Priority hints - always included first
    PRIORITY_HINTS = [
        ["HEJ"],
        ["!LFG"],
        ["THIS AIN'T", "YOUR OLD MAN'S", "RANDOMIZER!"],
        ["MEOW MEOW MEOW MEOW"],
        ["STAND CLEAR OF", "THE CLOSING DOORS", "PLEASE"],
        ["GO LOCAL", "SPORTS TEAM!"],
        ["WELCOME TO THE", "COFFEE ZONE"],
        ["HAPPY BIRTHDAY", "TO YOU!"],
        ["READ THE", "WIKI BRO!"],
        ["ARE YOU IN THE", "CATBIRD SEAT?"],
        ["THIS COULD", "BE YOU!"],
        ["YOU GOTTA", "HAVE HEART"],
    ]

    HINTS = [
        # Generic Wizard Texts
        ["DO YOU KNOW WHY", "WE STOPPED THE CAR?"],
        ["I LIKE BIG BOTS", "AND I CANNOT LIE"],
        ["WHY AM I LOCKED", "IN A BASEMENT"],
        ["THAT'S JUST LIKE", "YOUR OPINION MAN"],
        ["THE DUDE ABIDES"],
        ["10TH ENEMY HAS", "THE BOMB"],
        ["STAY AWHILE", "AND LISTEN"],
        ["YOU TEACH ME", "A SPELL"],
        ["YOU KNOW NOTHING"],
        ["THAT'S WHAT", "SHE SAID"],
        ["JUMP IN LAVA FOR", "200 RUPEES"],
        ["YOU WON'T BE ABLE", "TO CAST THIS"],
        ["BIG BUCKS", "NO WHAMMYS"],
        ["BAGU OWES ME", "20 RUPEES"],
        ["YOU ARE THE", "WEAKEST LINK"],
        ["LINK I AM", "YOUR FATHER"],
        ["THERE'S NO WIFI", "HERE"],
        ["A WILD LINK", "APPEARS"],
        ["WHAT'S THE WIFI", "PASSWORD"],
        ["DON'T SEND ME BACK", "TO THE HOME"],
        ["I'D LIKE TO BUY", "A VOWEL"],
        ["I ONLY KNOW", "ONE SPELL"],
        ["I WENT TO COLLEGE", "FOR THIS"],
        ["WHO PICKED THESE", "FLAGS"],
        ["I FOUND THIS", "IN THE GARBAGE"],
        ["HAVE YOU HEARD", "MY MIXTAPE"],
        ["DOES THIS ROBE", "MAKE ME LOOK FAT?"],
        ["NO POM POM", "SHAKING HERE"],
        ["YOU'RE A WIZARD,", "LINK"],
        ["TAKE ANY ROBE", "YOU WANT"],
        ["DON'T MOVE", "I DROPPED A", "CONTACT LENS"],
        ["PLEASE SUPPORT ZSR"],
        ["THIS WON'T HURT", "A BIT"],
        ["FREE YOUR MIND"],
        ["DA NA NA NA", "NAAAAAAAAA"],
        ["JOIN THE NINTENDO", "POWER CLUB"],
        ["SILVERS ARE IN", "PALACE 1"],
        ["NEEDS MORE COWBELL"],
        ["WHICH TIMELINE", "IS THIS?"],
        ["HURRY! I HAVE TO", "PREHEAT THE OVEN"],
        ["POYO!"],
        ["SPLOOSH KABOOM!"],
        ["LET ME READ MY", "VOGON POETRY"],
        ["SOMEBODY SET UP", "US THE BOMB"],
        ["BOAT LEAGUE", "CONFIRMED"],

        # River Man Texts
        ["BAGU SAID WHAT?", "THAT JERK!"],
        ["TRY NOT TO DROWN"],
        ["WHY CAN'T YOU SWIM?"],
        ["WHAT IS YOUR QUEST?"],
        ["TICKETS PLEASE"],
        ["WRAAAAAAFT"],
        ["WHICH WAY TO", "DENVER?"],
        ["DO YOU KNOW", "THE WAY TO", "SAN JOSE?"],
        ["DO YOU KNOW", "THE MUFFIN MAN"],
        ["CAN WE FIX IT?"],
        ["WHAT? YOU CAN'T", "SWIM?"],
        ["LINK.EXE HAS", "STOPPED WORKING"],
        ["NO RUNNING BY", "THE POOL"],

        # Bagu Texts
        ["HAVE YOU SEEN ERROR", "AROUND?"],
        ["WANNA SEE A CORPSE?"],
        ["ALIENS ARE REAL"],
        ["RUPEES ARE MIND", "CONTROL DEVICES"],
        ["BAM BAM BAM"],
        ["HERE IS MY LIST", "OF DEMANDS"],
        ["HEY! LISTEN!"],
        ["PIZZA DUDE'S GOT", "THIRTY SECONDS"],
        ["I AM BATMAN"],
        ["I AM GROOT"],
        ["BAGU SMAAAAASH"],
        ["GET OUT OF", "MA SWAMP!!"],
        ["PRAISE THE SUN"],
        ["AM I BEING", "DETAINED?"],
        ["ERROR IS THE", "EVIL TWIN"],
        ["TINGLE TINGLE", "KOOLOO LIMPAH!"],
        ["IS THIS A", "PEDESTAL SEED?"],
        ["DOES SPEC ROCK", "WEAR GLASSES?"],
        ["EVERYONE GETS", "A BRIDGE"],

        # Downstab Texts
        ["STICK THEM WITH", "THE POINTY END"],
        ["YOU'LL STAB YOUR", "EYE OUT"],
        ["PRESS DOWN", "YOU IDIOT"],
        ["HAVE A POGO STICK"],
        ["YAKHAMMER ACQUIRED"],
        ["PRESS DOWN TO", "CROUCH"],
        ["KICK PUNCH CHOP", "BLOCK DUCK JUMP"],
        ["YOU WALKED PAST ME", "DIDN'T YOU"],
        ["UPSTAB IS THE", "BEST STAB"],
        ["DO THE SAFETY DANCE"],
        ["EASY MODE ACTIVATED"],
        ["NEVER GONNA GIVE", "YOU UP"],
        ["ARE YOU SCROOGE", "MCDUCK?"],

        # Upstab Texts
        ["BET YOU WISH THIS", "WAS DOWNSTAB"],
        ["YOU PROBABLY WON'T", "NEED THIS"],
        ["PRESS UP TO GO", "IN DOORS"],
        ["ARE YOU SANTA CLAUS?"],
        ["SHORYUKEN!"],
        ["YOU WASTED", "YOUR TIME?"],
        ["MARIO CAN DO THIS", "WITHOUT MAGIC"],
        ["TIGER UPPERCUT!"],
        ["NEVER GONNA LET", "YOU DOWN"],
        ["THE OPPORTUNITY", "ARISES"],

        # Know Nothing Texts
        ["I KNOW NOTHING"],
        ["KNOWLEDGE IS", "NOT MINE"],
        ["I LIKE WASTING", "YOUR TIME"],
        ["THIS IS ABOUT", "AS USEFUL AS I AM"],
        ["NOTHING KNOW I"],
        ["TRY TO GET A GUIDE"],
        ["GIT GUD"],
        ["WHAT? YEAH! OKAY!"],
        ["NO HINT FOR YOU"],
        ["WHAT TIMELINE", "IS THIS?"],
        ["YOUR CALL IS", "IMPORTANT", "PLEASE HOLD"],
        ["SILENCE IS GOLDEN"],
        ["BLESS YOU"],
        ["HOLA!"],
        ["I AM NOT A VIRE", "IN DISGUISE"],
        ["WOAH! DUDE!"],
        ["PAY ME AND", "I'LL TALK"],
        ["THE HINT IS IN", "ANOTHER CASTLE"],

        # Not Enough Containers (adapted)
        ["ALL SIGNS POINT", "TO NO"],
        ["COME BACK AS", "ADULT LINK"],
        ["QUIT WASTING", "MY TIME"],
        ["YOU'RE SIXTEEN", "PIXELS SHORT"],
        ["DO YOU HAVE", "A DIPLOMA?"],
        ["SHOW ME YOUR", "CREDITS!"],
        ["I CANNOT CONTAIN", "MY LAUGHTER"],
        ["YOU MUST CONSTRUCT", "ADDITIONAL PYLONS"],
        ["BET YOU FORGOT", "THIS FLAG WAS ON"],
        ["I'LL TELL YOU WHEN", "YOU'RE OLDER"],

        # Spell Texts (adapted)
        ["HAVE YOU TRIED", "NOT DYING?"],
        ["I ALREADY HAVE ONE"],
        ["IS THIS A RED RING?"],
        ["I GET UP AND", "NOTHIN GETS", "ME DOWN"],
        ["KRIS KROSS WILL", "MAKE YOU"],
        ["HAVE YOU TRIED THE", "HEALMORE SPELL?"],
        ["DON'T BLAME ME", "IF THIS IS 1 BAR"],
        ["HOW MANY BARS", "WILL I HEAL"],
        ["HEY! LISTEN"],
        ["JUST DON'T SAY", "HEY LISTEN!"],
        ["WATCH OUT FOR IRON"],
        ["THIS IS FINE"],
        ["USE THIS TO", "BURN GEMS"],
        ["THIS SPELL IS", "WORTHLESS"],
        ["GOODNESS GRACIOUS!"],
        ["THIS ONE GOES OUT", "TO THE ONE I LOVE"],
        ["ROLLING AROUND", "AT THE SPEED", "OF SOUND"],
        ["GOTTA GO FAST"],
        ["USE THE BOOST", "TO GET THROUGH"],
        ["I AM NOT", "MIRROR SHIELD"],
        ["CRYSTA WAS HERE"],
        ["YOU'RE RUBBER,", "THEY'RE GLUE"],
        ["SEND CAROCK", "MY REGARDS"],
        ["IS THIS HERA", "BASEMENT?"],
        ["TITULAR REDUNDANCY", "INCLUDED"],
        ["WAIT? WHICH SPELL?"],
        ["YOU SHOULD RESCUE", "ME INSTEAD OF", "ZELDA"],
        ["CAN YOU USE IT", "IN A SENTENCE?"],
        ["METAMORPH THY ENEMY"],
        ["WITH THIS YOU", "CAN NOW BEAT", "THE GAME"],
        ["ULTRAZORD POWER UP!"],
        ["TERRIBLE TERRIBLE", "DAMAGE"],
        ["HE'S DEAD JIM"],
        ["A WINNER IS YOU"],
        ["WATER YOU DOING?"],
        ["YOU SAVED A KID", "FOR THIS?"],
        ["DON'T FORGET TO GET", "UPSTAB"],
        ["SORRY ABOUT", "THE MOAS"],

        # Community Non-Spell Get Texts (adapted)
        ["GET EQUIPPED", "WITH THIS"],
        ["TIS A GOOD DAY"],
        ["I CAN'T BELIEVE IT"],
        ["ALL HAIL HEROES", "RISE AGAIN"],
        ["CONGRATS!"],
        ["ONE FISH TWO FISH", "RED FISH"],
        ["MASTER IT AND YOU", "CAN HAVE THIS"],
        ["IT'S WHAT PLANTS", "CRAVE"],
        ["BAGU GIVES IT", "5 STARS"],
        ["THE POWER IS YOURS"],
        ["GANON IS JEALOUS"],
        ["THE SECRET TO LIFE"],
        ["YOUR LOVE IS", "LIKE BAD"],
        ["SCREW THE RULES", "I HAVE THIS"],
        ["EXCUSE ME YOU", "FORGOT THIS"],
        ["TAKE THIS! NOW I", "CAN RETIRE"],
        ["YOU GOTTA HAVE IT"],
        ["I LOVE IT", "IT'S SO BAD"],
        ["DON'T FEED AFTER", "MIDNIGHT"],
        ["TAKE IT LEAVE", "THE CANNOLI"],
        ["YAY!"],
        ["I WILL GIVE YOU", "THIS TO GO AWAY"],
        ["DOES NOT SPARK JOY"],
        ["LET'S TALK ABOUT", "IT BABY!"],
        ["WHEN ALL ELSE", "FAILS TRY THIS"],
        ["IT'S WHAT'S FOR", "DINNER"],
        ["NEEDS FOOD BADLY"],
        ["DETECTED"],
        ["BADGER BADGER", "BADGER"],
        ["THE WORLD IS A"],
        ["LINK MEETS"],
        ["A BRAND NEW!!!"],
        ["EARTH FIRE WIND", "WATER"],
        ["HAPPY DAY!!"],
        ["NEVER CHANGES"],
        ["IS CHEATING"],
        ["THIS SEED", "SPONSORED BY"],
        ["WE ALL LIVE IN", "A YELLOW"],
        ["IT'S TIME!"],
        ["FRESH 50 RUPEES", "OBO"],
        ["NO WHAMMY NO", "WHAMMY AND STOP!"],
        ["ALL YOU NEED IS"],
        ["THE SECRET WORD IS"],
        ["HAVE ONE ON", "THE HOUSE"],
    ]

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
        line1 = f"GO {dir_text[0]}, {dir_text[1]},"
        line2 = f"{dir_text[2]}, {dir_text[3]}"
        line3 = "THE MOUNTAIN AHEAD"

        hint_text = [line1, line2, line3]
        self.SetHint(HintType.HINT_4, hint_text)

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
        line1 = f"GO {dir_text[0]}, {dir_text[1]},"
        line2 = f"{dir_text[2]}, {dir_text[3]} TO"
        line3 = "THE FOREST OF MAZE"

        hint_text = [line1, line2, line3]
        self.SetHint(HintType.HINT_8, hint_text)

    def __init__(self):
        """Initialize the hint writer.

        Note: Relies on the random number generator being seeded externally
        by the main randomizer for deterministic hint selection.
        """
        self.patch = Patch()
        self.hints: Dict[HintType, str] = {}

    def SetHint(self, hint_type: HintType, hint: str) -> None:
        """Set a hint for a specific hint type.

        Args:
            hint_type: The type of hint to set
            hint: The hint text (can be string or list of lines)
        """
        self.hints[hint_type] = hint

    def FillWithCommunityHints(self) -> None:
        """Fill empty hint slots with community hints from priority and regular lists."""
        # Collect all community hints, priority first
        shuffled_hints = self.HINTS.copy()
        random.shuffle(shuffled_hints)

        all_community_hints = self.PRIORITY_HINTS.copy()
        all_community_hints.extend(shuffled_hints)

        # Fill empty slots
        community_hint_index = 0
        for hint_num in range(1, self.NUM_HINT_SLOTS + 1):
            hint_type = HintType(hint_num)
            if hint_type not in self.hints and community_hint_index < len(all_community_hints):
                self.hints[hint_type] = all_community_hints[community_hint_index]
                community_hint_index += 1

    def FillWithBlankHints(self) -> None:
        """Fill all hint slots with blank/test hints.

        Hint #1 is blank, hints #2-38 are labeled "TEST HINT 02" through "TEST HINT 38".
        """
        for hint_num in range(1, self.NUM_HINT_SLOTS + 1):
            hint_type = HintType(hint_num)
            if hint_num == 1:
                self.hints[hint_type] = ""
            elif hint_type not in self.hints:
                self.hints[hint_type] = f"TEST HINT {hint_num:02d}"

    def GetPatch(self) -> Patch:
        """Generate a patch with hint data.

        Returns:
            Patch object with hint pointers and data
        """
        log.debug("Writing hints to ROM.")

        # Track current write position in ROM
        current_file_offset = self.HINT_DATA_START

        # Iterate through hint types in order
        for hint_num in range(1, self.NUM_HINT_SLOTS + 1):
            hint_type = HintType(hint_num)

            # Get hint text (if not set, skip - should be filled by FillWithCommunityHints)
            if hint_type not in self.hints:
                continue

            hint = self.hints[hint_type]

            # Convert string to list if needed
            if isinstance(hint, str):
                lines = [hint]
            else:
                lines = hint

            # Encode the hint text
            encoded_hint = self._encode_text(lines)

            # Check if writing this hint would exceed the limit
            if current_file_offset + len(encoded_hint) >= self.MAX_HINT_DATA_END:
                # Would exceed limit - write a blank hint instead
                log.warning(f"Hint #{hint_num} would exceed ROM limit (0x{self.MAX_HINT_DATA_END:04X}). Writing blank hint instead.")
                encoded_hint = self._encode_text([""])

            # Calculate the pointer value
            nes_memory_address = 0x8000 + (current_file_offset - 0x4010)
            offset_from_bank_start = nes_memory_address - 0x8000

            # Write the encoded hint data
            self.patch.AddData(current_file_offset, encoded_hint)
            current_file_offset += len(encoded_hint)

            # Write pointer in little-endian format with 0x80 OR'd into high byte
            # Hint index is 0-based for pointer table (hint_num - 1)
            pointer_file_offset = self.HINT_POINTER_TABLE_START + ((hint_num - 1) * 2)
            low_byte = offset_from_bank_start & 0xFF
            high_byte = ((offset_from_bank_start >> 8) & 0xFF) | 0x80
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
            # Return one space followed by a second space with EOF bits set
            return [0x24, 0xE4]

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
