"""
Title Screen Version Patch.

Writes two things to the title screen nametable:
1. RANDOMIZER_MAGIC at TITLE_VERSION_OFFSET — used by is_randomizer_rom() to
   detect that a ROM was produced by ZORA.
2. The version string (e.g. "  ZORA  V2.0.0  ") over the vanilla
   "PUSH START BUTTON" text.

The "PUSH START BUTTON" text lives at different offsets in PRG0 vs PRG1, so
get_edits() selects the correct address based on rom_version.
"""

from zora.char_encoding import CHAR_TO_BYTE
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit
from zora.rom_layout import RANDOMIZER_MAGIC, TITLE_VERSION_OFFSET
from zora.version import __version_rom__

# "PUSH START BUTTON" nametable offset per PRG revision.
# PRG0 (rom_version=0): 0x1AB40
# PRG1 (rom_version=1 or None/unknown): 0x1ABCB
_PUSH_START_OFFSET_PRG0 = 0x1AB40
_PUSH_START_OFFSET_PRG1 = 0x1ABCB

# Vanilla bytes at each location (20 bytes: "PUSH START BUTTON" + 3 trailing spaces)
_PUSH_START_OLD_BYTES = bytes([
    0x19, 0x1E, 0x1C, 0x11, 0x24, 0x1C, 0x1D, 0x0A, 0x1B, 0x1D,
    0x24, 0x0B, 0x1E, 0x1D, 0x1D, 0x18, 0x17, 0x24, 0x24, 0x24,
])

# Vanilla bytes at TITLE_VERSION_OFFSET differ per PRG revision (10 bytes).
_TITLE_VERSION_OLD_PRG0 = bytes([0x24] * 10)
_TITLE_VERSION_OLD_PRG1 = bytes([0xE3, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24])

_VERSION_TEXT_LENGTH = 20  # must match the "PUSH START BUTTON" + trailing spaces


def _encode_version_text() -> bytes:
    """Encode the version string to 20 NES tile bytes, space-padded."""
    text = f"  ZORA  {__version_rom__}"
    padded = text.ljust(_VERSION_TEXT_LENGTH)[:_VERSION_TEXT_LENGTH]
    return bytes(CHAR_TO_BYTE[ch] for ch in padded)


class WriteTitleScreenVersion(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return True  # always active

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        is_prg0 = rom_version == 0

        push_offset = _PUSH_START_OFFSET_PRG0 if is_prg0 else _PUSH_START_OFFSET_PRG1
        title_old = _TITLE_VERSION_OLD_PRG0 if is_prg0 else _TITLE_VERSION_OLD_PRG1

        return [
            RomEdit(
                offset=TITLE_VERSION_OFFSET,
                new_bytes=RANDOMIZER_MAGIC,
                old_bytes=title_old,
                comment="RANDOMIZER_MAGIC identifier",
            ),
            RomEdit(
                offset=push_offset,
                new_bytes=_encode_version_text(),
                old_bytes=_PUSH_START_OLD_BYTES,
                comment=f"Title screen version: {__version_rom__.strip()}",
            ),
        ]
