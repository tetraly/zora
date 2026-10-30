"""A Link sprite sheet (PNG) as a sprite-set file (docs/link-sprite-sets.md "From a sprite sheet").

The sheet is the one artists draw Link's poses on: a row of 14 cells of 16x16 pixels, each framed by a
1-pixel border (so a row is 239 pixels wide), and as many rows as the artist likes (one variant per
row; --row picks one). The cells, left to right:

     0, 1  walking down, with the small shield     2, 3  walking sideways
     4, 5  walking up                               6  attacking down
     7     attacking sideways                       8  attacking up
     9     lifting an item with one hand           10, 11  walking down, with the magical shield
    12, 13 walking sideways, with the magical shield

Every one of the set's 40 tiles is read from one cell (SOURCES); the game draws the other cells from
the same tiles, flipped or shared (walking up's second frame is the first, mirrored), so where the
sheet draws those differently the game cannot show it: the script lists each such difference.

Colors: the sheet's background is transparent (color 0), and each other color is the nearest of
--colors' three (the tunic, color 1, then colors 2 and 3), by default the game's own Link colors.

    python3 scripts/link_sprite_sheet.py SHEET.png OUT.json --name NAME --author AUTHOR
        [--provenance TEXT] [--row N] [--colors TUNIC,COLOR2,COLOR3] [--background RRGGBB]
        [--recommended GREEN,BLUE,RED,COLOR2,COLOR3]

--recommended: the NES colors (hex, $00-$3F) the art was drawn for, which the page offers to apply.
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zora.rom.link_sprite import (  # noqa: E402
    LINK_HALVES,
    SPRITE_SET_SIZE,
    TILE_SIZE,
    RecommendedColors,
    SpriteSet,
    sprite_set_file,
)

CELL = 16
BORDER = 1
CELLS_PER_ROW = 14
HALF = 8                       # a sprite is two 8x16 halves, each two tiles (top, bottom)
GAME_LINK_COLORS = ((128, 208, 16), (252, 152, 56), (200, 76, 12))      # NES $29, $27, $17

# The set's 40 tiles as 20 halves (8x16, two tiles each), in LINK_TILE_GROUPS' order
SET_HALVES = LINK_HALVES


@dataclass(frozen=True)
class Use:
    """A half of a cell: the cell, its side (0 left, 1 right), and whether the game flips it."""
    cell: int
    side: int
    flipped: bool = False


# Where each half is read from, then the other places the game draws it (zora/rom/link_sprite.py's
# tiles; the disassembly's Link_EndMoveAndAnimate and DrawLinkLiftingItem).
SOURCES: dict[str, tuple[Use, ...]] = {
    "$00": (Use(2, 0), Use(12, 0)),                       # sideways 1; with the magical shield
    "$02": (Use(2, 1),),
    "$04": (Use(3, 0), Use(13, 0)),                       # sideways 2
    "$06": (Use(3, 1),),
    "$08": (Use(1, 1, True), Use(11, 1, True), Use(9, 1, True)),     # down 2's right side, mirrored
    "$0A": (Use(0, 1), Use(10, 1)),                       # down 1's right side
    "$0C": (Use(4, 0), Use(5, 1, True)),                  # up: the second frame is the first, mirrored
    "$0E": (Use(4, 1), Use(5, 0, True)),
    "$10": (Use(7, 0),), "$12": (Use(7, 1),),             # attacking sideways
    "$14": (Use(6, 0),), "$16": (Use(6, 1),),             # attacking down
    "$18": (Use(8, 0),), "$1A": (Use(8, 1),),             # attacking up
    "$78": (Use(9, 0),),                                  # lifting an item (both hands: mirrored)
    "$80": (Use(12, 1),),                                 # sideways 1, the magical shield
    "$54": (Use(13, 1),),                                 # sideways 2, the magical shield
    "$58": (Use(0, 0),),                                  # down 1, the small shield
    "$5A": (Use(1, 0),),                                  # down 2, the small shield
    "$60": (Use(10, 0), Use(11, 0)),                      # down, the magical shield
}
assert set(SOURCES) == set(SET_HALVES)

Pixels = list[list[tuple[int, int, int]]]


def read_png(path: Path) -> Pixels:
    """An 8-bit RGB or RGBA PNG (not interlaced) as rows of (r, g, b): no image library needed."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path}: not a PNG")
    position, chunks, header = 8, b"", None
    while position < len(data):
        length, kind = struct.unpack(">I4s", data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            chunks += body
        position += 12 + length
    assert header is not None
    width, height, depth, color_type, _, _, interlace = header
    if depth != 8 or color_type not in (2, 6) or interlace:
        raise SystemExit(f"{path}: an 8-bit RGB or RGBA PNG, not interlaced, please")
    channels = 3 if color_type == 2 else 4
    raw = zlib.decompress(chunks)
    stride = width * channels
    rows: list[bytearray] = []
    previous = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            up = previous[x]
            up_left = previous[x - channels] if x >= channels else 0
            if kind == 1:
                line[x] = (line[x] + left) & 0xFF
            elif kind == 2:
                line[x] = (line[x] + up) & 0xFF
            elif kind == 3:
                line[x] = (line[x] + (left + up) // 2) & 0xFF
            elif kind == 4:
                guess = left + up - up_left
                nearest = min((abs(guess - left), 0, left), (abs(guess - up), 1, up),
                              (abs(guess - up_left), 2, up_left))[2]
                line[x] = (line[x] + nearest) & 0xFF
        rows.append(line)
        previous = line
    return [[(row[x], row[x + 1], row[x + 2]) for x in range(0, stride, channels)] for row in rows]


def cell_half(sheet: Pixels, row: int, use: Use) -> list[tuple[tuple[int, int, int], ...]]:
    """One half of a cell, 16 rows of 8 pixels, mirrored back when the game draws it flipped."""
    top = BORDER + row * (CELL + BORDER)
    left = BORDER + use.cell * (CELL + BORDER) + use.side * HALF
    lines = [tuple(sheet[top + y][left:left + HALF]) for y in range(CELL)]
    return [line[::-1] for line in lines] if use.flipped else lines


def color_index(pixel: tuple[int, int, int], background: tuple[int, int, int],
                colors: tuple[tuple[int, int, int], ...]) -> int:
    if pixel == background:
        return 0
    distances = [sum((a - b) ** 2 for a, b in zip(pixel, color, strict=True)) for color in colors]
    return 1 + distances.index(min(distances))


def tile_bytes(indexes: list[list[int]]) -> bytes:
    """An 8x8 tile of color indexes in the console's 2-bit format."""
    low = bytes(sum((value & 1) << (7 - x) for x, value in enumerate(line)) for line in indexes)
    high = bytes(sum((value >> 1) << (7 - x) for x, value in enumerate(line)) for line in indexes)
    return low + high


def convert(sheet: Pixels, row: int, colors: tuple[tuple[int, int, int], ...],
            background: tuple[int, int, int] | None) -> tuple[bytes, list[str]]:
    """The set's 640 bytes from one row of the sheet, and the differences the game cannot show."""
    rows = len(sheet) // (CELL + BORDER)      # a sheet's last bottom border may be missing
    if len(sheet[0]) != BORDER + CELLS_PER_ROW * (CELL + BORDER) or not 0 <= row < rows:
        raise SystemExit(f"a sheet is {CELLS_PER_ROW} cells of {CELL} pixels with {BORDER}-pixel borders; "
                         f"this one is {len(sheet[0])}x{len(sheet)} (row {row} of {rows})")
    background = background or sheet[BORDER + row * (CELL + BORDER)][BORDER]
    tiles = b""
    differences = []
    for name in SET_HALVES:
        source, *others = SOURCES[name]
        half = [[color_index(pixel, background, colors) for pixel in line] for line in cell_half(sheet, row, source)]
        tiles += tile_bytes(half[:HALF]) + tile_bytes(half[HALF:])
        for use in others:
            other = [[color_index(pixel, background, colors) for pixel in line] for line in cell_half(sheet, row, use)]
            changed = sum(a != b for line, other_line in zip(half, other, strict=True)
                          for a, b in zip(line, other_line, strict=True))
            if changed:
                side = ("left", "right")[use.side]
                differences.append(f"cell {use.cell} {side}: {changed} pixels differ from cell {source.cell}'s "
                                   f"(the game draws both from tile {name})")
    assert len(tiles) == SPRITE_SET_SIZE == 40 * TILE_SIZE
    return tiles, differences


def hex_color(text: str) -> tuple[int, int, int]:
    text = text.strip().lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sheet", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--provenance", default="")
    parser.add_argument("--row", type=int, default=0, help="the sheet's row, from 0 (default 0)")
    parser.add_argument("--colors", help="the sheet's tunic, color 2 and color 3 as RRGGBB,RRGGBB,RRGGBB "
                                         "(default: the game's Link colors)")
    parser.add_argument("--background", help="the sheet's background, RRGGBB (default: the first cell's corner)")
    parser.add_argument("--recommended", help="the NES colors the art was drawn for: GREEN,BLUE,RED,COLOR2,COLOR3 "
                                              "(hex, for example 29,32,16,27,17)")
    args = parser.parse_args()
    colors = tuple(hex_color(text) for text in args.colors.split(",")) if args.colors else GAME_LINK_COLORS
    if len(colors) != 3:
        raise SystemExit("--colors: three colors")
    background = hex_color(args.background) if args.background else None
    tiles, differences = convert(read_png(args.sheet), args.row, colors, background)
    recommended = None
    if args.recommended:
        values = [int(text, 16) for text in args.recommended.split(",")]
        if len(values) != 5:
            raise SystemExit("--recommended: five colors")
        recommended = RecommendedColors((values[0], values[1], values[2]), (values[3], values[4]))
    args.out.write_text(sprite_set_file(SpriteSet(args.name, args.author, args.provenance, tiles, recommended)))
    print(f"{args.out}: {args.name}, by {args.author}")
    for line in differences:
        print(f"  not shown in the game: {line}")


if __name__ == "__main__":
    main()
