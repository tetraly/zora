import logging
import random
from typing import List, Tuple

from .patch import Patch


class TextRandomizer:
    """Randomizes NPC text strings in Legend of Zelda."""

    # ROM file offsets (accounting for 0x10 NES header)
    # The NES maps 0x4000 in ROM file to 0x8000 in memory (Bank 1 starts at 0x8000)
    NES_HEADER_SIZE = 0x10
    TEXT_POINTER_TABLE_START = 0x4010  # File offset for pointer table
    TEXT_DATA_START = 0x405C  # File offset where text data starts

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

    # Community hints adapted from Z2 Randomizer
    # Format converted from Z2's $ line breaks to Z1's list format
    # Max 20 chars per line, max 3 lines

    # Priority quotes - always included first
    PRIORITY_QUOTES = [
        ["YOUR MESSAGE HERE", "GITHUB.COM SLASH", "TETRALY SLASH ZORA"],
        ["!LFG"],
        ["THIS AIN'T", "YOUR OLD MAN'S", "RANDOMIZER!"],
        ["SHOUTOUT TO", "NEXT GEN"],
        ["MEOW MEOW MEOW", "MEOW MEOW MEOW", "MEOW MEOW MEOW"],
        ["STAND CLEAR OF", "THE CLOSING DOORS", "PLEASE"],
        ["GO LOCAL", "SPORTS TEAM!"],
        ["WELCOME TO THE", "COFFEE ZONE"],
        ["HAPPY BIRTHDAY", "TO YOU!"],
        ["READ THE", "WIKI BRO!"],
        ["ARE YOU IN THE", "CATBIRD SEAT?"],
        ["THIS COULD", "BE YOU!"],
        ["YOU GOTTA", "HAVE HEART"],
        ["AS AN AI LANGUAGE", "MODEL I CANNOT", "DO THAT ..."],
    ]

    QUOTES = [
        # Generic Wizard Texts
        ["DO YOU KNOW WHY", "WE STOPPED THE CAR?"],
        ["LINK... I AM YOUR", "FATHER"],
        ["I LIKE BIG BOTS", "AND I CANNOT LIE"],
        ["WHY AM I LOCKED", "IN A BASEMENT"],
        ["THAT'S JUST LIKE", "YOUR OPINION MAN"],
        ["THE DUDE ABIDES"],
        ["BOY THIS IS REALLY", "EXPENSIVE"],
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
        ["THIS GAME NEEDS", "MORE CATEGORIES"],
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
        ["HOW MANY SHAKES", "CAN A DIGSHAKE", "SHAKE?"],
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
        ["TELL THE RIVERMAN", "I SAID HE'S", "AN IDIOT"],
        ["WANNA SEE A CORPSE?"],
        ["ALIENS ARE REAL"],
        ["RUPEES ARE MIND", "CONTROL DEVICES"],
        ["PLEASE DON'T TELL", "MY WIFE I AM HERE"],
        ["BAM BAM BAM"],
        ["HERE IS MY LIST", "OF DEMANDS"],
        ["MY EMAIL TO", "RIVER MAN WAS", "IN MY DRAFTS"],
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
        ["JUMP CROUCH", "IT'S ALL IN", "THE MIND!"],
        ["YOU WALKED PAST ME", "DIDN'T YOU"],
        ["UPSTAB IS THE", "BEST STAB"],
        ["DO THE SAFETY DANCE"],
        ["EASY MODE ACTIVATED"],
        ["NEVER GONNA GIVE", "YOU UP"],
        ["ARE YOU SCROOGE", "MCDUCK?"],

        # Upstab Texts
        ["BET YOU WISH THIS", "WAS DOWNSTAB"],
        ["YOU PROBABLY WON'T", "NEED THIS"],
        ["PRESS UP YOU IDIOT"],
        ["PRESS UP TO GO", "IN DOORS"],
        ["ARE YOU SANTA CLAUS?"],
        ["SHORYUKEN!"],
        ["YOU WASTED", "YOUR TIME?"],
        ["MARIO CAN DO THIS", "WITHOUT MAGIC"],
        ["DOWNSTAB IS THE", "BEST STAB"],
        ["TIGER UPPERCUT!"],
        ["NEVER GONNA LET", "YOU DOWN"],
        ["THANKS FOR NOT", "SKIPPING ME"],
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
        ["DID YOU CHECK", "THE OLD KASUTO", "HINT?"],

        # Not Enough Containers (adapted)
        ["ALL SIGNS POINT", "TO NO"],
        ["COME BACK AS", "ADULT LINK"],
        ["QUIT WASTING", "MY TIME"],
        ["YOU'RE SIXTEEN", "PIXELS SHORT"],
        ["DO YOU HAVE", "A DIPLOMA?"],
        ["THE MAGIC CLASS", "DID NOT HELP YOU", "ENOUGH"],
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

    def __init__(self, seed: int = None):
        """Initialize the text randomizer with an optional seed."""
        self.patch = Patch()
        if seed is not None:
            random.seed(seed)

    def GetPatch(self) -> Patch:
        """Generate a patch with randomized NPC text."""
        logging.debug("Randomizing NPC text.")

        # Start with priority quotes, then shuffle the rest
        shuffled_quotes = self.QUOTES.copy()
        random.shuffle(shuffled_quotes)

        # Combine priority quotes first, then random quotes to fill remaining slots
        all_quotes = self.PRIORITY_QUOTES.copy()
        remaining_slots = 26 - len(self.PRIORITY_QUOTES)
        all_quotes.extend(shuffled_quotes[:remaining_slots])

        # Start writing text data at file offset 0x405C
        # This corresponds to NES memory 0x804C (which is offset 0x4C from bank start at 0x8000)
        current_file_offset = self.TEXT_DATA_START

        for i in range(min(26, len(all_quotes))):
            quote = all_quotes[i]

            # Encode the text
            encoded_text = self._encode_text(quote)

            # Calculate the pointer value
            # The NES reads ROM file starting at 0x4010 as memory address 0x8000
            # So file offset 0x405C appears at NES memory 0x804C
            # The pointer stores the offset from 0x8000, so 0x804C -> offset 0x4C
            nes_memory_address = 0x8000 + (current_file_offset - 0x4010)
            offset_from_bank_start = nes_memory_address - 0x8000

            # Write pointer in little-endian format with 0x80 OR'd into high byte
            pointer_file_offset = self.TEXT_POINTER_TABLE_START + (i * 2)
            low_byte = offset_from_bank_start & 0xFF
            high_byte = ((offset_from_bank_start >> 8) & 0xFF) | 0x80
            pointer_bytes = [low_byte, high_byte]
            self.patch.AddData(pointer_file_offset, pointer_bytes)

            # Write the encoded text data
            self.patch.AddData(current_file_offset, encoded_text)

            # Move to next file offset
            current_file_offset += len(encoded_text)

        return self.patch

    def _encode_text(self, lines: List[str]) -> List[int]:
        """
        Encode text lines into ROM format with center-padding to 22 chars.

        Args:
            lines: List of text lines (1-3 lines, max 20 chars each)

        Returns:
            List of bytes representing the encoded text
        """
        result = []

        for line_num, line in enumerate(lines):
            # Pad the line to exactly 22 characters with centering bias to the right
            # Ensure at least 1 space on the right side
            line_len = len(line)
            if line_len < 22:
                # Calculate padding - add 2 extra to left for better centering
                # but ensure at least 1 space remains on the right
                total_padding = 22 - line_len
                left_padding = (total_padding // 2) + 2
                right_padding = 22 - line_len - left_padding

                # Ensure at least 1 space on the right
                if right_padding < 1:
                    left_padding -= (1 - right_padding)
                    right_padding = 1

                # Pad the line
                padded_line = (' ' * left_padding) + line + (' ' * right_padding)
            else:
                padded_line = line[:22]  # Truncate if somehow too long

            # Encode each character
            for char_pos, char in enumerate(padded_line):
                char_upper = char.upper()
                if char_upper not in self.CHAR_TO_BYTE:
                    # Skip unknown characters or use space
                    byte_val = self.CHAR_TO_BYTE[' ']
                else:
                    byte_val = self.CHAR_TO_BYTE[char_upper]

                # Add line break bits after the last character of a line (except the last line)
                # Bit 7 (0x80) = start second line after this character
                # Bit 6 (0x40) = start third line after this character
                if char_pos == len(padded_line) - 1 and line_num < len(lines) - 1:
                    if line_num == 0:
                        byte_val |= 0x80  # Start second line
                    elif line_num == 1:
                        byte_val |= 0x40  # Start third line

                result.append(byte_val)

        # Mark end of text (set both bits 6 and 7 on last byte)
        if result:
            result[-1] |= 0xC0

        return result
