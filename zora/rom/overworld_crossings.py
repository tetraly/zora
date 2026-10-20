"""Add Bridges to the River (B87; features-behavior.md FP-BRIDGE-01) and Add Lost Woods Shortcut
(B88; FP-WOODS-01): three fixed overworld data bytes, written after the code patches with their
fields on, and taking no draw (a "?" is its coin, FL-DEP-04).

Aldonunez labels, at the pinned commit (file offsets, PRG0):
  B87: room $17 (layout $16) draws its square column 6 from column 4 of ColumnHeapOWB, which no
       other layout uses; the byte drawing rows 7 and 8 (0x15E9D) becomes square $0B twice, PRG0's
       bridge square, in place of square $05 (water) twice. Room $27 (layout $26) takes column $12
       (ColumnHeapOW1's column 2: water with a bridge at row 5, room $38's) for its square column 6
       in RoomLayoutsOW (0x1568E) in place of column $13 (water at every row).
  B88: room $51 (layout $4D) takes column $16 (ColumnHeapOW1's column 6: trees open at rows 4 to
       6, its own east edge) for its square column 0 in RoomLayoutsOW (0x158F8) in place of column
       $15 (trees at every row), so its west edge opens into room $50: a one-way way around the
       forest maze (room $50's east edge stays rock, which a westward step never tests).
Layouts $16, $26 and $4D serve those rooms alone under every Overworld Quest (OW-APP-A4).
"""
from __future__ import annotations

from .base_rom import original_bytes
from .vanilla_overworld.tables import LAYOUT_COLUMNS, ROOM_LAYOUTS_OW

# FP-BRIDGE-01: room $17's column byte for rows 7 and 8 (ColumnHeapOWB, column 4)
ROOM_17_RIVER_ROWS = 0x15E9D
ROOM_17_RIVER_PRG0 = 0x45             # square $05 (water), twice
ROOM_17_BRIDGE = 0x4B                 # square $0B (bridge), twice
# FP-BRIDGE-01: layout $26's (room $27's) column for square column 6
ROOM_27_LAYOUT = 0x26
RIVER_COLUMN = 6
WATER_COLUMN = 0x13                   # ColumnHeapOW1's column 3: water at every row
BRIDGE_COLUMN = 0x12                  # ColumnHeapOW1's column 2: a bridge at row 5
# FP-WOODS-01: layout $4D's (room $51's) column for square column 0
ROOM_51_LAYOUT = 0x4D
WEST_EDGE_COLUMN = 0
TREES_COLUMN = 0x15                   # ColumnHeapOW1's column 5: trees at every row
OPEN_TREES_COLUMN = 0x16              # ColumnHeapOW1's column 6: open at rows 4 to 6


def layout_column_offset(layout: int, column: int) -> int:
    """The file offset of one layout's column descriptor in RoomLayoutsOW."""
    return ROOM_LAYOUTS_OW.file_offset + layout * LAYOUT_COLUMNS + column


ROOM_27_RIVER_COLUMN = layout_column_offset(ROOM_27_LAYOUT, RIVER_COLUMN)          # 0x1568E
ROOM_51_WEST_EDGE = layout_column_offset(ROOM_51_LAYOUT, WEST_EDGE_COLUMN)         # 0x158F8


def _checked(offset: int, prg0: int, new: int) -> tuple[int, bytes]:
    assert original_bytes(offset, 1)[0] == prg0, f"overworld data at {offset:#x} is not PRG0's"
    return offset, bytes([new])


def river_bridge_writes() -> list[tuple[int, bytes]]:
    """FP-BRIDGE-01's two bytes as (file offset, bytes), checked against the player's ROM."""
    return [_checked(ROOM_17_RIVER_ROWS, ROOM_17_RIVER_PRG0, ROOM_17_BRIDGE),
            _checked(ROOM_27_RIVER_COLUMN, WATER_COLUMN, BRIDGE_COLUMN)]


def lost_woods_shortcut_writes() -> list[tuple[int, bytes]]:
    """FP-WOODS-01's byte as (file offset, bytes), checked against the player's ROM."""
    return [_checked(ROOM_51_WEST_EDGE, TREES_COLUMN, OPEN_TREES_COLUMN)]
