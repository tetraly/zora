"""
Write LevelInfo entry-room markers (byte 35) and entrance direction (byte 61).

B9 (enemy sprite carry-over fix) reads two LevelInfo bytes at runtime:
  - byte 35 ($6BA1): the "virtual entry room" marker, value | 0x80
  - byte 61 ($6BBB): entrance direction enum (1=N, 2=S, 3=E, 4=W; 0 = OW)

Vanilla ZORA leaves both bytes as stock 0xFF for OW + UW1..UW9 (10 LevelInfo
blocks, 252 bytes each at file offset 0x19310). Reference randomizers populate
them with stable, seed-independent values; without them, B9 dereferences
garbage and softlocks at the dungeon entry sprite-carry-over check.

This patch is gated on ``config.fix_known_bugs`` so FKB-off ROMs remain
byte-equivalent to the upstream baseline.

Implementation note (temporary pragmatic choice — option B):
The reference randomizer's vanilla writer ``SmallPatchers.AssignBaseDirections``
computes byte 35 as ``count | 0x80`` where ``count`` is the number of leading
sentinel entries in ``RoomTypeMapping[layout]`` (a 4×128 static table). ZORA
does not yet load that table — ``zora/level_gen/remap_maps.py`` declares a
parameter for it but the function is dead code. Rather than port the table
just for B9, we hardcode the 9 vanilla output values produced by the
reference's formula. Upgrade to data-driven computation when ZORA implements
dungeon entrance shuffle or dungeon room randomization, which will need
RoomTypeMapping anyway.

For full investigation, see:
  analysis/zero_flags_baseline/b9_investigation/byte_35_analysis.md
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


# LevelInfo block layout: 252 (0xFC) bytes, base at file offset 0x19310,
# 10 blocks (OW + UW1..UW9). Within a block:
#   byte 35 (0x23): entry-room marker  ($6BA1)
#   byte 61 (0x3D): entrance direction ($6BBB)
_LEVEL_BLOCK_BASE = 0x19310
_LEVEL_BLOCK_SIZE = 0xFC
_BYTE35_OFFSET = 0x23
_BYTE61_OFFSET = 0x3D

# Indexed by level: 0 = OW, 1..9 = UW1..UW9.
# Hardcoded vanilla outputs of the reference's AssignBaseDirections formula.
# These are seed-independent and reproduced from reference ROMs; see the
# investigation report linked in the module docstring.
_VANILLA_BYTE35 = [0xFF, 0x80, 0x80, 0x80, 0x85, 0x80, 0x80, 0x81, 0x81, 0x88]
_VANILLA_BYTE61 = [0x00, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02]


def _vanilla_entry_room_markers() -> list[tuple[int, int]]:
    """Return (file_offset, value) pairs for all byte-35 and byte-61 writes.

    OW byte 35 is already 0xFF in the base ROM, so it is omitted (no-op edit).
    """
    edits: list[tuple[int, int]] = []
    for level in range(10):
        block_base = _LEVEL_BLOCK_BASE + level * _LEVEL_BLOCK_SIZE
        b35 = _VANILLA_BYTE35[level]
        if b35 != 0xFF:
            edits.append((block_base + _BYTE35_OFFSET, b35))
        edits.append((block_base + _BYTE61_OFFSET, _VANILLA_BYTE61[level]))
    return edits


class WriteLevelInfoEntryRoomMarkers(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.fix_known_bugs

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=offset,
                new_bytes=bytes([value]),
                old_bytes=bytes([0xFF]),
                comment=f"LevelInfo entry-room marker / entrance dir @ {offset:#x}",
            )
            for offset, value in _vanilla_entry_room_markers()
        ]
