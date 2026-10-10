"""Minimap synthesis (SH-MAP-01, SH-MAP-02).

Full synthesis from the level's cells, per the spec's SH-MAP-01 format
(formulas verified to match 540/540 corpus levels):

- map_data: 16-byte "explored" bitmap. Byte index = col - mincol + pad,
  bit = 7 - row. pad = (16 - width) // 2.
- map_ppu_commands: for each row pair (0-1 .. 6-7): $20, position byte,
  column count, then one tile byte per column of the level's bounding box:
  255 both rows / 251 top only / 103 bottom only / 36 neither.
  Position byte = 94 + pad + 32*pair_index. One $FF terminator follows
  (SH-MAP-01); ZORA writes nothing past it, so the rest of the 45-byte
  block keeps its previous bytes (command_block).
- map_start = (pad - mincol) & 0xF (SH-MAP-01 step 4: "how far the bitmap
  was shifted from the level's own leftmost column").
- map_cursor_offset = (8 * ((4 - (width + 1) // 2) - mincol)) & 0xFF.

Stair/freed cells are excluded (rooms only). Width must be ≤ 8 (validated
upstream; SPEC-GAP 28: inferred from the eight-column display).
"""
from .world import SetWorld

COMMAND_BLOCK_SIZE = 45          # LevelInfo +$4F..+$7B
COMMANDS_END = 0xFF              # the terminator the generator writes
END_OF_LIST_BIT = 0x80           # TransferTileBuf stops at a negative VRAM high byte
RECORD_HEADER = 3                # VRAM high byte, low byte, count
RECORD_COUNT_BITS = 0x3F         # the count byte's low six bits


def synthesize_minimap(cells: set[int]) -> tuple[bytes, bytes, int, int]:
    """Returns (map_data16, commands, map_start, map_cursor_offset), where
    commands are the drawing records and their terminator only; lay them
    over the level's previous block with command_block."""
    if not cells:
        return bytes(16), bytes([COMMANDS_END]), 0, 0
    minc = min(c & 0x0F for c in cells)
    maxc = max(c & 0x0F for c in cells)
    width = maxc - minc + 1
    pad = (16 - width) // 2

    data = [0] * 16
    for c in cells:
        row, col = c >> 4, c & 0x0F
        idx = col - minc + pad
        if 0 <= idx < 16:
            data[idx] |= 1 << (7 - row)

    cmds: list[int] = []
    for pair in range(4):
        top_row = pair * 2
        bot_row = pair * 2 + 1
        pos = (94 + pad + 32 * pair) & 0xFF
        block = [0x20, pos, width]
        for col in range(minc, maxc + 1):
            top = (top_row * 16 + col) in cells
            bot = (bot_row * 16 + col) in cells
            # Tile mapping per corpus byte-match (9000/9000 levels):
            # smaller row index ("top" of the grid) draws as 103 ($67) and
            # bottom row-only as 251 ($fb) — the inverse of the literal
            # "top-only 251" wording in SH-MAP-01, which evidently speaks in
            # display coordinates. The ROM bytes are the ground truth.
            if top and bot:
                block.append(255)
            elif top:
                block.append(103)
            elif bot:
                block.append(251)
            else:
                block.append(36)
        cmds.extend(block)
    cmds.append(COMMANDS_END)
    assert len(cmds) <= COMMAND_BLOCK_SIZE, f"minimap commands overflow 45 bytes (width {width})"

    map_start = (pad - minc) & 0x0F
    cursor = (8 * ((4 - (width + 1) // 2) - minc)) & 0xFF
    return bytes(data), bytes(cmds), map_start, cursor


def command_block(commands: bytes, previous: bytes) -> bytes:
    """The level's 45-byte command block after writing `commands` (records
    and terminator) at its start. Quirk (SH-MAP-01, corpus 9,000/9,000):
    the bytes past the terminator keep their previous values, which for a
    generated level are the vanilla level's; the engine never reads them
    (TransferTileBuf stops at the terminator)."""
    return commands + previous[len(commands):COMMAND_BLOCK_SIZE]


def drawn_commands(block: bytes) -> bytes:
    """The part of a command block the engine reads: its records through
    the terminator."""
    end = 0
    while end < len(block) and not block[end] & END_OF_LIST_BIT:
        end += RECORD_HEADER + (block[end + 2] & RECORD_COUNT_BITS)
    return block[:end + 1]


def compute_map_data(world: SetWorld, blob: int) -> bytes:
    cells = set(world.cells_by_blob[blob])
    return synthesize_minimap(cells)[0]


def level9_left_edge(world: SetWorld) -> int | None:
    """SH-MAP-02: level 9's left column for hint text.

    If level 9 is narrower than seven columns the recorded edge moves one
    column left (clamped at column 0; SPEC-GAP 8: clamp is an assumption —
    the value is not stored in the ROM, only returned for the hint step).
    """
    blob = next((b for b, lv in sorted(world.levels.items()) if lv == 9), None)
    if blob is None:
        return None
    cells = world.cells_by_blob[blob]
    mincol = min(c & 0x0F for c in cells)
    maxcol = max(c & 0x0F for c in cells)
    if maxcol - mincol + 1 < 7:
        return max(0, mincol - 1)
    return mincol
