"""Randomize Lost Hills' own screen layouts for $0B (asm/flags2/lost-hills; docs/design/zora-flags-2.0.md
section 12).

Screen $0B shares its layout with $3C: layout $0A (the 1Q5 and 1Q2 doorways) in the first quest's look,
$7B (the fairy fountain and the pond) in the second's. Lost Hills joins $0B to $0C through $0B's right
edge, which must open without $3C's. So $0B shows a layout of its own: the patch's routine lets a screen
name $7C-$7F, read from ZORA's table EXTRA_LAYOUTS, and this module writes there

  - $7C: layout $7B with layout $0A's right edge opened (column 15 is column code $01), and
  - $7D: layout $0A with the same edge;

the generation step zora/generate/steps/lost_hills_layouts.py gives $0B the one for its look. Each row is
copied from the image as written so far (PRG0's rows; nothing before this changes $0A or $7B), so no
original-game bytes are stored here. Mirror Overworld flips the rows with the game's afterwards
(mirror_overworld._flip_layouts)."""
from .vanilla_overworld.layouts import screen_layout_codes
from .vanilla_overworld.tables import EXTRA_LAYOUTS, FIRST_EXTRA_LAYOUT, LAYOUT_COLUMNS

FOUNTAIN_LAYOUT = 0x7B          # RoomLayoutOWCave2: the second quest's fountain on $0B and pond on $3C
DOORWAY_LAYOUT = 0x0A           # the 1Q5 doorway on $0B and the 1Q2 doorway on $3C
# A shared layout -> $0B's own copy of it
OWN_LAYOUTS = {FOUNTAIN_LAYOUT: FIRST_EXTRA_LAYOUT, DOORWAY_LAYOUT: FIRST_EXTRA_LAYOUT + 1}
EAST_EDGE_COLUMN = LAYOUT_COLUMNS - 1
OPEN_EAST_EDGE = 0x01           # the column code Lost Hills' $0C has at its left edge: open ground at the maze's row


def own_layout_row(rom: bytes | bytearray, shared: int) -> bytes:
    """$0B's copy of a shared layout: its column codes with the east edge opened."""
    codes = bytearray(screen_layout_codes(bytes(rom), shared))
    codes[EAST_EDGE_COLUMN] = OPEN_EAST_EDGE
    return bytes(codes)


def extra_layout_writes(rom: bytes | bytearray) -> list[tuple[int, bytes]]:
    """The rows of OWN_LAYOUTS in EXTRA_LAYOUTS, from the image `rom` (with Randomize Lost Hills on)."""
    return [(EXTRA_LAYOUTS.file_offset + (own - FIRST_EXTRA_LAYOUT) * LAYOUT_COLUMNS, own_layout_row(rom, shared))
            for shared, own in OWN_LAYOUTS.items()]
