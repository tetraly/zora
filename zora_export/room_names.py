"""The room layouts' glossary names (docs/glossary/room-layouts.csv, its community_name column) by layout
code, which the spoiler log's Full level names rooms by. The page's worker cannot read docs/, so the table
lives here; tests/test_spoiler_writers.py keeps it equal to the file. Codes $2A-$3D have no name (the file
gives them one range row): layout_name falls back to the code."""
LAYOUT_NAMES = {
    0x00: "Plain room",
    0x01: "Spike-trap room",
    0x02: "Four short blocks",
    0x03: "Four tall blocks",
    0x04: "Aquamentus room",
    0x05: "Gleeok room",
    0x06: "Gohma room",
    0x07: "Three rows",
    0x08: "Reverse C",
    0x09: "Circle wall",
    0x0A: "Double block",
    0x0B: "Lava moat",
    0x0C: "Maze room",
    0x0D: "Grid room",
    0x0E: "Vertical chute",
    0x0F: "Horizontal chute",
    0x10: "Vertical rows",
    0x11: "Zigzag room",
    0x12: "T room",
    0x13: "Vertical moat",
    0x14: "Circle moat",
    0x15: "Pointless moat",
    0x16: "Chevy room",
    0x17: "NSU room",
    0x18: "Horizontal moat",
    0x19: "Double moat",
    0x1A: "Diamond stair room",
    0x1B: "Narrow stair room",
    0x1C: "Spiral stair room",
    0x1D: "Double six-block",
    0x1E: "Single six-block",
    0x1F: "Five pair",
    0x20: "Turnstile room",
    0x21: "Entrance room",
    0x22: "Single block",
    0x23: "Two fireball statues",
    0x24: "Four fireball statues",
    0x25: "Desert room",
    0x26: "Black room",
    0x27: "Zelda's room",
    0x28: "Ganon's room",
    0x29: "Triforce room",
    0x3E: "Transport staircase (cellar corridor)",
    0x3F: "Item staircase (item cellar)",
}


def layout_name(code: int) -> str:
    """A layout by its glossary name, or by its code where the glossary gives none."""
    return LAYOUT_NAMES.get(code, f"Layout ${code:02X}")
