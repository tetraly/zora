"""Validation tests for WriteLevelInfoEntryRoomMarkers.

The patch hardcodes the 9 vanilla outputs of the reference randomizer's
``SmallPatchers.AssignBaseDirections`` formula. These tests assert it
writes the expected bytes at the expected file offsets, so accidental
drift (typos, off-by-one, reorderings) is caught.
"""
from zora.game_config import GameConfig
from zora.patches.write_level_info_entry_room_markers import (
    WriteLevelInfoEntryRoomMarkers,
)

# Expected byte 35 ($6BA1) values per level from reference ROMs (seeds
# 101/105/110, vanilla flag string). OW byte 35 is already 0xFF in the
# base ROM, so the patch does not write it.
_EXPECTED_BYTE35 = {1: 0x80, 2: 0x80, 3: 0x80, 4: 0x85, 5: 0x80,
                    6: 0x80, 7: 0x81, 8: 0x81, 9: 0x88}

# Expected byte 61 ($6BBB) — entrance direction enum (0 = OW, 2 = SOUTH).
_EXPECTED_BYTE61 = {0: 0x00, 1: 0x02, 2: 0x02, 3: 0x02, 4: 0x02,
                    5: 0x02, 6: 0x02, 7: 0x02, 8: 0x02, 9: 0x02}

_LEVEL_BLOCK_BASE = 0x19310
_LEVEL_BLOCK_SIZE = 0xFC


def _byte35_offset(level: int) -> int:
    return _LEVEL_BLOCK_BASE + level * _LEVEL_BLOCK_SIZE + 0x23


def _byte61_offset(level: int) -> int:
    return _LEVEL_BLOCK_BASE + level * _LEVEL_BLOCK_SIZE + 0x3D


def test_patch_active_only_when_fix_known_bugs() -> None:
    bp = WriteLevelInfoEntryRoomMarkers()
    assert not bp.is_active(GameConfig(fix_known_bugs=False))
    assert bp.is_active(GameConfig(fix_known_bugs=True))


def test_writes_expected_byte35_for_each_dungeon() -> None:
    edits = WriteLevelInfoEntryRoomMarkers().get_edits()
    by_offset = {e.offset: e.new_bytes for e in edits}

    for level, expected in _EXPECTED_BYTE35.items():
        offset = _byte35_offset(level)
        assert offset in by_offset, f"L{level} byte 35 ({offset:#x}) not written"
        assert by_offset[offset] == bytes([expected]), (
            f"L{level} byte 35: expected {expected:#x}, got {by_offset[offset].hex()}"
        )

    # OW byte 35 must NOT be written (already 0xFF in the base ROM).
    assert _byte35_offset(0) not in by_offset, "OW byte 35 should not be written"


def test_writes_expected_byte61_for_each_level() -> None:
    edits = WriteLevelInfoEntryRoomMarkers().get_edits()
    by_offset = {e.offset: e.new_bytes for e in edits}

    for level, expected in _EXPECTED_BYTE61.items():
        offset = _byte61_offset(level)
        assert offset in by_offset, f"L{level} byte 61 ({offset:#x}) not written"
        assert by_offset[offset] == bytes([expected]), (
            f"L{level} byte 61: expected {expected:#x}, got {by_offset[offset].hex()}"
        )


def test_all_old_bytes_are_ff() -> None:
    """Every edit replaces a stock 0xFF slot — sanity-checks file offsets."""
    for edit in WriteLevelInfoEntryRoomMarkers().get_edits():
        assert edit.old_bytes == bytes([0xFF]), (
            f"@ {edit.offset:#x}: expected old_bytes 0xFF, got {edit.old_bytes!r}"
        )
