"""Change Hidden OW Tiles (B89; features-behavior.md FP-VIS-01): the overworld's four secret squares
drawn with their own looks, those looks solid, and, under the first or second overworld quest, the
second-quest-only secrets made plain. Written by the final steps after the code patches and the
crossings' bytes (B87, B88), whose values are not in step 3's list.

  1. The looks: the four secret squares' primary squares ($26 to $29, `TileObjectPrimarySquaresOW`)
     become $38, $3C, $34 and $30, drawn from background tiles $30 to $3F. The spec puts them at
     $50-$5F; ZORA shares $30-$3F with the common boss block instead (step 4), which leaves $50-$5F
     for the tiles that must be loaded everywhere (owner decision, 2026-11-14: Pegasus Boots' blank
     $50/$51, the Item Counter's chest and slash $52/$53, the Archipelago logo $5C-$5F). The spec
     gives its drawings as informative bytes; ZORA draws with them.
  2. Solid: the shove and step tests (bank 7 $EEFD and $F116) switch to bank 4 and call a routine
     at $BE00 (PRG0 unused space) that treats tiles $30 to $3F as unwalkable and every other tile as
     PRG0 does, returning to the callers' branches with bank 4 still in.
  3. Under C01 = 0 or 1 (resolved), every overworld screen whose quest field (table F bits 7-6) is 2
     or 3 gets its layout's secret columns swapped for their plain twins in RoomLayoutsOW.
  4. The swap: the secret squares are drawn only on the overworld and the common boss block's
     $30-$3F only in a level, so each level load (InitMode2) writes one or the other into the
     background table. FP-FIX-03's TransferLevelPatternBlocksPlus1 ends `JMP TransferLevelPatternBlocks`;
     it jumps to SwapCommonTiles (bank 3 $AC00, the linker gap) instead, which calls it (the screen is
     still off) and then sends PPU $1300-$13FF (background tiles $30-$3F) from one of two 256-byte
     copies beside it: the squares' when CurLevel is 0, else the ROM's own tiles $30-$3F (the boss
     tiles Randomize Boss Groups put there, or the blank ones). Code in bank 3 cannot read bank 2's
     CommonBackgroundPatterns, hence the second copy. CommonBackgroundPatterns keeps the boss tiles,
     which TransferCommonPatterns loads at power-on, so the title screen is as before.

A finished ROM written again (parse_rom then serialize_to_rom, the round trip) runs the steps on an
image that already holds them: each site may hold PRG0's bytes or FP-VIS-01's own, and step 3 finds
no secret column left to swap.
"""
from __future__ import annotations

import hashlib

from .base_rom import Original, Piece, original_bytes, piece_bytes
from .layout import BOSS_SET_EXPANSION_SPRITES_ADDRESS, OVERWORLD_DATA_ADDRESS
from .overworld_crossings import layout_column_offset
from .vanilla_overworld.tables import LAYOUT_COLUMNS

Writes = list[tuple[int, bytes]]

# Step 1: TileObjectPrimarySquaresOW's four secret squares, and their drawings
SECRET_LOOKS = 0x16986
SECRET_LOOKS_PRG0 = bytes.fromhex("c8d8c4bc")         # the plain rock, rock wall, tree and gravestone
MARKED_LOOKS = bytes.fromhex("383c3430")
SQUARE_TILES = range(0x30, 0x40)                      # background tiles $30-$3F, shared with the bosses
# The spec's drawings, two eight-byte planes per tile: most planes are PRG0's own overworld
# background patterns, read from the player's ROM (a release ships no original-game bytes)
MARKED_TILE_PIECES: tuple[Piece, ...] = (
    Original(0x0CE0B, 8), bytes.fromhex("fcf8f0e3c3ccccc3"),    # tile $30
    Original(0x0CE1B, 8), Original(0x0CE23, 8),    # tile $31
    Original(0x0CE2B, 8), Original(0x0CE33, 8),    # tile $32
    Original(0x0CE3B, 8), Original(0x0CE43, 8),    # tile $33
    Original(0x0CE8B, 8), Original(0x0CE93, 8),    # tile $34
    Original(0x0CE9B, 8), Original(0x0CEA3, 8),    # tile $35
    bytes.fromhex("000080c0c0c0c0c0"), Original(0x0CEB3, 8),    # tile $36
    bytes.fromhex("40c080c00000c000"), Original(0x0CEC3, 8),    # tile $37
    Original(0x0CECB, 8), Original(0x0CED3, 8),    # tile $38
    bytes.fromhex("735141e3f7ff7d00"), bytes.fromhex("8484800000008000"),    # tile $39
    Original(0x0CEEB, 8), Original(0x0CEF3, 8),    # tile $3A
    Original(0x0CEFB, 8), Original(0x0CF03, 8),    # tile $3B
    Original(0x0CFCB, 8), bytes.fromhex("0102028280000000"),    # tile $3C
    bytes.fromhex("e3e341409c9e3e2c"), bytes.fromhex("0000808020200052"),    # tile $3D
    Original(0x0CFEB, 8), Original(0x0CFF3, 8),    # tile $3E
    Original(0x0CFFB, 8), Original(0x0D003, 8),    # tile $3F
)
# Step 2: the two eight-byte tests (JSR $EDFA / CMP $034A / branch) and the routine in bank 4
SHOVE_TEST, STEP_TEST = 0x1EF0D, 0x1F126
TEST_LENGTH = 8
# PRG0's two tests, by their SHA-256: a release ships no run of the original game's bytes
SHOVE_TEST_PRG0_SHA256 = "5ddf2540702093db3462c91f22b4f08b6a87f5faa81f2739431baa1934cde3c5"
STEP_TEST_PRG0_SHA256 = "6d293c243119942aae88ba5df9164ce5b53fe298aa6c95f0f64c9a2095be7f33"
SHOVE_HOOK = bytes.fromhex("a90420acff4c0bbe")       # LDA #$04 / JSR SwitchBank / JMP $BE0B
STEP_HOOK = bytes.fromhex("a90420acff4c00be")        # LDA #$04 / JSR SwitchBank / JMP $BE00
SOLID_ROUTINE = 0x13E10                               # bank 4 $BE00
# Its tile test is CMP #$30 / BCC / CMP #$40 / BCC (the spec's $50 and $60, step 1's move)
SOLID_ROUTINE_CODE = bytes.fromhex("2016beb0034c4ef14c1ef12016beb0034c05ef4ce4ee20faed"
                                   "c9309004c9409004cd4a03603860")
# Step 4: the swap, in bank 3's linker gap (asm/rom_space.toml site "hidden-tiles-swap")
FIX_03_JMP_OPERAND = 0x0EBFA                          # bank 3 $ABEA: FP-FIX-03's JMP TransferLevelPatternBlocks
TRANSFER_LEVEL_PATTERN_BLOCKS = 0x8044
SWAP_ROUTINE = 0x0EC10                                # bank 3 $AC00
SWAP_ROUTINE_CPU = 0xAC00
SQUARES_COPY = 0x0EC50                                # bank 3 $AC40
BOSSES_COPY = 0x0ED50                                 # bank 3 $AD40
# The boss expansion (layout.BOSS_SET_EXPANSION_SPRITES_ADDRESS) starts at CommonBackgroundPatterns' tile $30
BOSS_TILES_SIZE = 0x100
SWAP_ROUTINE_CODE = bytes.fromhex(
    "204480"                    # JSR TransferLevelPatternBlocks (video is off)
    "ad0220"                    # LDA PpuStatus_2002: reset the address latch
    "a9138d0620"                # LDA #$13 / STA PpuAddr_2006
    "a9008d0620"                # LDA #$00 / STA PpuAddr_2006: background tile $30
    "a000"                      # LDY #0
    "a510"                      # LDA CurLevel
    "d00a"                      # BNE @Bosses
    "b940ac8d0720c8d0f760"      # @Squares: LDA $AC40,Y / STA PpuData_2007 / INY / BNE @Squares / RTS
    "b940ad8d0720c8d0f760")     # @Bosses: LDA $AD40,Y / STA PpuData_2007 / INY / BNE @Bosses / RTS
assert len(SWAP_ROUTINE_CODE) <= SQUARES_COPY - SWAP_ROUTINE
# Step 3: tables D (layout, bits 6-0) and F (quest field, bits 7-6), and the secret columns' plain twins
OVERWORLD_SCREENS = 0x80
TABLE_SIZE = 0x80
LAYOUT_TABLE = OVERWORLD_DATA_ADDRESS + 3 * TABLE_SIZE   # table D
QUEST_TABLE = OVERWORLD_DATA_ADDRESS + 5 * TABLE_SIZE    # table F (0x18690)
LAYOUT_MASK = 0x7F
QUEST_SHIFT = 6
SECOND_QUEST_ONLY_FIELDS = frozenset({2, 3})
PLAIN_TWINS = {0x14: 0x15, 0x31: 0x25, 0x71: 0x34, 0x75: 0x00, 0x81: 0x01, 0x85: 0x47, 0x88: 0x82,
               0xD2: 0x02, 0xD3: 0x07, 0xD4: 0x72, 0xE4: 0x22, 0xF7: 0x62}
assert not set(PLAIN_TWINS) & set(PLAIN_TWINS.values())   # a layout met twice is unchanged


def marked_tile_bytes() -> bytes:
    """The 256 bytes of the secret squares' tiles under B89 (loaded at $30-$3F on the overworld)."""
    return b"".join(piece_bytes(piece) for piece in MARKED_TILE_PIECES)


def _unchanged(rom: bytes | bytearray, offset: int, prg0: bytes | str, written: bytes, name: str) -> None:
    """The site holds PRG0's bytes (`prg0`, or their SHA-256) in the player's ROM, and in the image
    either those or FP-VIS-01's own (`written`, a finished ROM written again)."""
    length = TEST_LENGTH if isinstance(prg0, str) else len(prg0)
    original = original_bytes(offset, length)
    matches = hashlib.sha256(original).hexdigest() == prg0 if isinstance(prg0, str) else original == prg0
    assert matches, f"{name} is not PRG0's"
    assert bytes(rom[offset:offset + length]) in (original, written), f"{name} was written before FP-VIS-01"


def hidden_tiles_writes(rom: bytes | bytearray, plain_dead_secrets: bool) -> Writes:
    """FP-VIS-01's four steps on the ROM image as the code patches and crossings leave it."""
    tiles = marked_tile_bytes()
    boss_tiles = bytes(rom[BOSS_SET_EXPANSION_SPRITES_ADDRESS:BOSS_SET_EXPANSION_SPRITES_ADDRESS + BOSS_TILES_SIZE])
    _unchanged(rom, SECRET_LOOKS, SECRET_LOOKS_PRG0, MARKED_LOOKS, "TileObjectPrimarySquaresOW")
    _unchanged(rom, SHOVE_TEST, SHOVE_TEST_PRG0_SHA256, SHOVE_HOOK, "the shove's tile test")
    _unchanged(rom, STEP_TEST, STEP_TEST_PRG0_SHA256, STEP_HOOK, "the step's tile test")
    _unchanged(rom, SOLID_ROUTINE, b"\xff" * len(SOLID_ROUTINE_CODE), SOLID_ROUTINE_CODE, "FP-VIS-01's routine space")
    _unchanged(rom, SWAP_ROUTINE, b"\xff" * len(SWAP_ROUTINE_CODE), SWAP_ROUTINE_CODE, "the swap's routine space")
    _unchanged(rom, SQUARES_COPY, b"\xff" * len(tiles), tiles, "the squares' copy space")
    _unchanged(rom, BOSSES_COPY, b"\xff" * len(boss_tiles), boss_tiles, "the boss tiles' copy space")
    jump = int.from_bytes(rom[FIX_03_JMP_OPERAND:FIX_03_JMP_OPERAND + 2], "little")
    assert jump in (TRANSFER_LEVEL_PATTERN_BLOCKS, SWAP_ROUTINE_CPU), "FP-FIX-03's jump is not its own"
    writes = [(SECRET_LOOKS, MARKED_LOOKS), (SHOVE_TEST, SHOVE_HOOK), (STEP_TEST, STEP_HOOK),
              (SOLID_ROUTINE, SOLID_ROUTINE_CODE), (SWAP_ROUTINE, SWAP_ROUTINE_CODE), (SQUARES_COPY, tiles),
              (BOSSES_COPY, boss_tiles), (FIX_03_JMP_OPERAND, SWAP_ROUTINE_CPU.to_bytes(2, "little"))]
    if plain_dead_secrets:
        writes += plain_dead_secret_writes(rom)
    return writes


def plain_dead_secret_writes(rom: bytes | bytearray) -> Writes:
    """Step 3: the layout of each screen whose quest field is 2 or 3, its secret columns swapped for
    their plain twins (a layout met twice is unchanged the second time)."""
    writes: Writes = []
    layouts = sorted({rom[LAYOUT_TABLE + screen] & LAYOUT_MASK for screen in range(OVERWORLD_SCREENS)
                      if rom[QUEST_TABLE + screen] >> QUEST_SHIFT in SECOND_QUEST_ONLY_FIELDS})
    for layout in layouts:
        for column in range(LAYOUT_COLUMNS):
            offset = layout_column_offset(layout, column)
            if rom[offset] in PLAIN_TWINS:
                writes.append((offset, bytes([PLAIN_TWINS[rom[offset]]])))
    return writes
