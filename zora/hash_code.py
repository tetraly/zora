"""
Hash code generation and ROM patch for the ZORA seed identifier.

The hash is a 4-byte value derived from a SHA-224 digest of the fully
assembled patch data. It is written into the ROM so it displays in-game
as four item sprites, and returned to the caller for UI display.

Call apply_hash_code(patch) after serialize_game_world() and any other
patch modifications, but before writing the ROM. It mutates the patch
in-place and returns the 4-byte hash.
"""

import hashlib
from enum import IntEnum

from zora.serializer import Patch

# ROM addresses
HASH_CODE_DATA_ADDRESS    = 0xAFD4
HASH_CODE_DISPLAY_ADDRESS = 0xAFA0
HASH_CODE_JUMP_ADDRESS    = 0xA4CD
ZORA_LABEL_ADDRESS        = 0x1A129

# ASM display routine
_DISPLAY_ROUTINE = bytes.fromhex(
    "A9008D0801A20AA9FF95ACCAD0FBA204"
    "A060BDC3AF9D440498691BA89570A920"
    "9584A90095ACCAD0E9209D97A9148514"
    "E61360FF"
)

# JMP to display routine
_JUMP_TO_DISPLAY = bytes([0x4C, 0x90, 0xAF])

# Replaces "CODE" with "ZORA" on the title screen
_ZORA_LABEL = bytes.fromhex("23181B0A2424242424242424242424")


class CodeItem(IntEnum):
    """Item sprite slots used for the ZORA hash code display."""
    BOMBS           = 0x00
    SWORD           = 0x01
    MAGICAL_SWORD   = 0x03
    BAIT            = 0x04
    RECORDER        = 0x05
    CANDLE          = 0x06
    ARROW           = 0x08
    BOW             = 0x0A
    MAGICAL_KEY     = 0x0B
    RAFT            = 0x0C
    LADDER          = 0x0D
    RUPEE           = 0x0F
    WAND            = 0x10
    BOOK            = 0x11
    RING            = 0x12
    POWER_BRACELET  = 0x14
    LETTER          = 0x15
    COMPASS         = 0x16
    KEY             = 0x19
    HEART_CONTAINER = 0x1A
    TRIFORCE        = 0x1B
    SHIELD          = 0x1C
    BOOMERANG       = 0x1D
    POTION          = 0x1F
    CLOCK           = 0x21
    HEART           = 0x22
    FAIRY           = 0x23
    BEAM            = 0x27

    def display_name(self) -> str:
        """Return a human-readable name, e.g. HEART_CONTAINER -> 'Heart Container'."""
        return self.name.replace("_", " ").title()


def _compute_hash(patch: Patch) -> bytes:
    """Compute a 4-byte hash over the patch data.

    Uses SHA-224 over all (address, data) pairs in sorted address order.
    Each of the first 4 digest bytes is reduced modulo the number of CodeItems
    to select a sprite slot, giving each item an equal chance.
    """
    pool = list(CodeItem)
    h = hashlib.sha224()
    for address in sorted(patch.data.keys()):
        h.update(str(address).encode("utf-8"))
        h.update(patch.data[address])

    result = bytearray()
    for byte in h.digest()[:4]:
        result.append(pool[byte % len(pool)])
    return bytes(result)


def apply_hash_code(patch: Patch) -> bytes:
    """Compute the hash over patch, write hash ROM entries, and return the 4-byte hash.

    Mutates patch in-place with four additions:
      1. The 4-byte hash values at HASH_CODE_DATA_ADDRESS
      2. The ASM display routine at HASH_CODE_DISPLAY_ADDRESS
      3. A JMP instruction at HASH_CODE_JUMP_ADDRESS
      4. The "ZORA" label replacement at ZORA_LABEL_ADDRESS

    Returns the 4-byte hash for UI display. Use hash_code_display_names() to
    convert to strings.

    Must be called AFTER all gameplay patch data is assembled, since the hash
    covers the full patch contents at the time of the call.
    """
    hash_bytes = _compute_hash(patch)

    patch.add(HASH_CODE_DATA_ADDRESS,    hash_bytes)
    patch.add(HASH_CODE_DISPLAY_ADDRESS, _DISPLAY_ROUTINE)
    patch.add(HASH_CODE_JUMP_ADDRESS,    _JUMP_TO_DISPLAY)
    patch.add(ZORA_LABEL_ADDRESS,        _ZORA_LABEL)

    return hash_bytes


def hash_code_display_names(hash_bytes: bytes) -> list[str]:
    """Return a list of 4 display name strings for a hash returned by apply_hash_code.

    Names are returned in the same order the sprites appear in-game (reversed
    relative to the hash byte order, since the ROM writes them right-to-left).
    """
    def name_for(b: int) -> str:
        try:
            return CodeItem(b).display_name()
        except ValueError:
            return f"Unknown ({b:#04x})"

    return [name_for(b) for b in reversed(hash_bytes)]
