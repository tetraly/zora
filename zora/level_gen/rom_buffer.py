"""Shared ROM buffer infrastructure for the new-level generation pipeline.

All sub-functions in the pipeline read/write a shared bytearray via these
constants and helpers.  After the pipeline completes, the grid regions are
extracted and fed into parser.py's _parse_level() to produce Level objects.

Ported from the C# GeneratorState.Rom usage patterns across all
new_level/*.cs files.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Grid geometry
# ---------------------------------------------------------------------------

GRID_ROWS = 8
GRID_COLS = 16
LEVEL_TABLE_SIZE = 0x80  # 128 bytes per table
NUM_TABLES = 6
GRID_SIZE = NUM_TABLES * LEVEL_TABLE_SIZE  # 0x300 = 768 bytes per grid

# ---------------------------------------------------------------------------
# ROM offset constants (C# decimal values, iNES header INCLUDED)
#
# These are the raw addresses used by the C# code (state.Rom[addr]).
# The C# ROM buffer is a full .nes file including the 0x10-byte iNES
# header.  Our rom bytearray must also include the header so that these
# offsets work unchanged.
# ---------------------------------------------------------------------------

# Grid table base addresses
ROMOFS_SCREEN_LAYOUT = 100112      # 0x18710 — Table 0 base (levels 1-6)
ROMOFS_SCREEN_LAYOUT_Q2 = 100880  # 0x18A10 — Table 0 base (levels 7-9)

# Table offsets from grid base (each table is 0x80 bytes)
# T0 = +0x000  (screen layout / north-south walls + palette_0)
# T1 = +0x080  (east-west walls + palette_1)
# T2 = +0x100  (enemy qty + enemy code)       — C# calls this "ItemData"
# T3 = +0x180  (room_type + flags)             — C# calls this "EnemyData"
# T4 = +0x200  (item + sound flags + darkness) — C# calls this "DoorData"
# T5 = +0x280  (item_position + room_action)   — C# calls this "RoomFlags"

ROMOFS_ITEM_DATA = 100368      # 0x18810 — T2 base (levels 1-6)
ROMOFS_ENEMY_DATA = 100496     # 0x18890 — T3 base (levels 1-6)
ROMOFS_DOOR_DATA = 100624      # 0x18910 — T4 base (levels 1-6)
ROMOFS_ROOM_FLAGS = 100752     # 0x18990 — T5 base (levels 1-6)

ROMOFS_ENTRANCE_DATA = 103231  # 0x1933F — level_info entrance_room field

# Boss sprite page IDs (written by PlaceBosses)
ROMOFS_BOSS_SPRITE_PAGE = 0xC025

# Overworld enemy tables (read-only, used by PlaceEnemies)
ROMOFS_OW_ENEMY_TABLE_1 = 0x18510  # 128 bytes
ROMOFS_OW_ENEMY_TABLE_2 = 0x18590  # 128 bytes

# Level info block base and stride
ROMOFS_LEVEL_INFO_BASE = 0x19310  # level_info block for level 0
LEVEL_INFO_STRIDE = 0xFC          # 252 bytes per level

# ---------------------------------------------------------------------------
# Derived table addresses
# ---------------------------------------------------------------------------

def grid_base(start_level: int) -> int:
    """Return the ROM base address for the grid containing *start_level*.

    start_level == 1 → levels 1-6 grid (0x18710)
    start_level == 7 → levels 7-9 grid (0x18A10)
    """
    if start_level == 7:
        return ROMOFS_SCREEN_LAYOUT_Q2
    return ROMOFS_SCREEN_LAYOUT


def base_offset(start_level: int) -> int:
    """Return the C# *baseOfs* value for the given start level.

    The C# code computes table addresses as
        0x18710 + baseOfs + table_offset + room_num
    where baseOfs is 0 for levels 1-6 and 0x300 for levels 7-9.
    """
    if start_level == 7:
        return ROMOFS_SCREEN_LAYOUT_Q2 - ROMOFS_SCREEN_LAYOUT  # 0x300
    return 0


# ---------------------------------------------------------------------------
# LevelGrid type alias
# ---------------------------------------------------------------------------

LevelGrid = list[list[int]]


def make_level_grid() -> LevelGrid:
    """Create a fresh 8x16 grid initialized to 0."""
    return [[0] * GRID_COLS for _ in range(GRID_ROWS)]


# ---------------------------------------------------------------------------
# ROM buffer helpers
# ---------------------------------------------------------------------------

def make_rom_buffer(source_rom: bytes | bytearray) -> bytearray:
    """Create a mutable ROM buffer from an existing ROM image.

    The caller should pass the full .nes file INCLUDING the 0x10-byte
    iNES header, since all C# ROM offsets assume header-inclusive
    file offsets.
    """
    return bytearray(source_rom)


def clear_grid_data(rom: bytearray, start_level: int) -> None:
    """Zero out the 0x300-byte grid region for the given level group.

    Equivalent to C# NewLevelClearData: zeroes all 6 tables (T0-T5)
    for the grid that contains *start_level*.
    """
    base = grid_base(start_level)
    for i in range(GRID_SIZE):
        rom[base + i] = 0


# ---------------------------------------------------------------------------
# Round-trip: ROM buffer → parser.py
# ---------------------------------------------------------------------------

def extract_grid_bytes(rom: bytearray, start_level: int) -> bytes:
    """Extract the 0x300-byte grid region for feeding into parser.py.

    Returns the 6-table block that _parse_level() expects as its
    *grid_data* parameter.
    """
    base = grid_base(start_level)
    return bytes(rom[base: base + GRID_SIZE])


def signed_byte(val: int) -> int:
    """Emulate C# (sbyte) cast: sign-extend an unsigned byte."""
    val &= 0xFF
    return val if val < 128 else val - 256
