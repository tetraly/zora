"""The base ROMs ZORA accepts: the two US releases, PRG0 and PRG1 (Rev 1), and either one with
modified graphics (owner rulings, beta 5; docs/design/prg1.md).

identify_rom is the one check the web page, the scripts and Archipelago use. Only hashes and
file offsets of the releases are kept here, never their bytes.

PRG1 moves some of PRG0's code and data (docs/design/prg1.md section 3). ZORA works in PRG0's
layout on every revision. A PRG1 ROM is first moved into PRG0's layout (in_prg0_layout), the
generation and serializer write into that image as they do on PRG0, and the bytes they changed
then go back to PRG1's own places (back_to_revision). Nothing else knows the revision.
"""
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from functools import cache

# layout.py's values (it imports base_rom, which imports this module; tests/test_revision.py
# checks they agree)
NES_HEADER_SIZE = 0x10
BOSS_SET_EXPANSION_SPRITES_ADDRESS = 0x8A8F
BOSS_SET_EXPANSION_SPRITES_SIZE = 0x200

INES_MAGIC = b"NES\x1a"
# The iNES header of both releases' usual dumps (No-Intro's files are headerless; a ROM given
# without a header gets this one).
INES_HEADER = INES_MAGIC + bytes([0x08, 0x00, 0x12, 0x00]) + bytes(8)
ROM_DATA_SIZE = 0x20000


class Revision(Enum):
    PRG0 = "PRG0"
    PRG1 = "PRG1"


# The ROM data's SHA-1 (the 131,072 bytes after the iNES header, as No-Intro hashes them):
# "Legend of Zelda, The (USA)" and "Legend of Zelda, The (USA) (Rev 1)".
ROM_DATA_SHA1 = {
    Revision.PRG0: "a12d74c73a0481599a5d832361d168f4737bbcf6",
    Revision.PRG1: "be2f5dc8c5ba8ec1a344a71f9fb204750af24fe7",
}
# The same with every graphics block zeroed (graphics_free): what a ROM with modified graphics
# hashes to.
GRAPHICS_FREE_SHA1 = {
    Revision.PRG0: "002a3e56f1d3099d7e736a9e643c9d2a954fae89",
    Revision.PRG1: "90a704ffd450fd71ab4bd94ca2f05e253d13b6e8",
}

# The graphics a ROM may change and still be recognized: the 15 tile-pattern blocks of the
# disassembly's src/bins.xml (owner ruling: the pattern blocks only, palettes later). Offsets
# are the ROM data's, without the header, as bins.xml gives them.
GRAPHICS_BLOCKS: tuple[tuple[str, int, int], ...] = (
    ("DemoSpritePatterns", 19892, 2304),
    ("DemoBackgroundPatterns", 22196, 2080),
    ("CommonSpritePatterns", 32895, 1792),
    ("CommonBackgroundPatterns", 34687, 1792),
    ("CommonMiscPatterns", 36479, 224),
    ("PatternBlockUWBG", 49435, 2080),
    ("PatternBlockOWBG", 51515, 2080),
    ("PatternBlockOWSP", 53595, 1824),
    ("PatternBlockUWSP358", 55419, 544),
    ("PatternBlockUWSP469", 55963, 544),
    ("PatternBlockUWSP", 56507, 256),
    ("PatternBlockUWSP127", 56763, 544),
    ("PatternBlockUWSPBoss1257", 57307, 1024),
    ("PatternBlockUWSPBoss3468", 58331, 1024),
    ("PatternBlockUWSPBoss9", 59355, 1024),
)

NOT_RECOGNIZED = "ROM not recognized. If you believe this is in error, please file a bug in the ZORA Discord"


class RomNotRecognized(ValueError):
    """Neither release, with or without modified graphics."""

    def __init__(self) -> None:
        super().__init__(NOT_RECOGNIZED)


@dataclass(frozen=True)
class IdentifiedRom:
    """identify_rom's answer, for the page, the scripts and Archipelago to show."""
    revision: Revision
    modified_graphics: bool

    @property
    def message(self) -> str:
        graphics = " with modified graphics" if self.modified_graphics else ""
        return f"This is a {self.revision.value} ROM{graphics}"


def rom_data(data: bytes) -> bytes:
    """The ROM data: the file without its 16-byte iNES header, when it has one."""
    return data[NES_HEADER_SIZE:] if data[:len(INES_MAGIC)] == INES_MAGIC else data


def graphics_free(data: bytes) -> bytes:
    """The ROM data with every graphics block zeroed."""
    image = bytearray(data)
    for _name, offset, length in GRAPHICS_BLOCKS:
        image[offset:offset + length] = bytes(length)
    return bytes(image)


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def identify_rom(data: bytes) -> IdentifiedRom:
    """Which release `data` (a .nes file, or the ROM data without a header) is: its ROM data's
    SHA-1 against both releases', then, failing that, the same with the graphics blocks zeroed
    (modified graphics). RomNotRecognized otherwise. The header itself is never compared."""
    rom = rom_data(data)
    if len(rom) == ROM_DATA_SIZE:
        digest = _sha1(rom)
        for revision, expected in ROM_DATA_SHA1.items():
            if digest == expected:
                return IdentifiedRom(revision, modified_graphics=False)
        digest = _sha1(graphics_free(rom))
        for revision, expected in GRAPHICS_FREE_SHA1.items():
            if digest == expected:
                return IdentifiedRom(revision, modified_graphics=True)
    raise RomNotRecognized


def recognized(data: bytes) -> IdentifiedRom | None:
    """identify_rom, or None for any other ROM (a finished or corpus ROM)."""
    try:
        return identify_rom(data)
    except RomNotRecognized:
        return None


def headered(data: bytes) -> bytes:
    """The ROM as a .nes file: as given, or with INES_HEADER before ROM data given without one."""
    return data if data[:len(INES_MAGIC)] == INES_MAGIC else INES_HEADER + data


# --- PRG1's layout ------------------------------------------------------------------------------
# File offsets, with the header, as layout.py's. Measured with difflib's matching blocks between
# the two releases (docs/design/prg1.md section 3); tests/test_revision.py checks every entry
# against both ROMs when they are present.

@dataclass(frozen=True)
class Move:
    """PRG0's bytes [start, end) sit `shift` bytes further on in PRG1."""
    start: int
    end: int
    shift: int

    def __contains__(self, offset: int) -> bool:
        return self.start <= offset < self.end


PRG1_MOVES = (
    Move(0x01ACA, 0x01BA5, -2),      # TuneScripts1 .. CustomEnvelopeTune1 (bank 0, audio)
    Move(0x01BAF, 0x01F0F, -4),      # CustomEnvelopeTune1 .. StairsSfxNotes (DMC level, the songs)
    Move(0x14B04, 0x14B67, +3),      # Mode8 sprite values .. (bank 5, the game-over screen)
    Move(0x14B69, 0x15363, +10),     # UpdateMode8ContinueQuestion_Full .. CheckBossSoundEffectUW
    Move(0x1A2E2, 0x1ACD9, +139),    # StoryTileAttrTransferBuf, GameTitleTransferBuf (bank 6)
)

# Every byte where PRG1 differs from PRG0, as windows [start, end): the moved code and data
# with what PRG1 changed or added around them (the 51 ranges of docs/design/prg1.md, joined
# within a routine).
PRG1_CHANGED = (
    (0x0184B, 0x01855), (0x018DA, 0x018DB), (0x0192E, 0x0192F), (0x0197C, 0x0197D), (0x01AC7, 0x01F0F),
    (0x08A8F, 0x08A9C),
    (0x14366, 0x14367), (0x14514, 0x14515), (0x148C3, 0x148CA), (0x1494E, 0x1494F), (0x14AF5, 0x1536C),
    (0x17151, 0x17153), (0x172AF, 0x172B0), (0x172BF, 0x172C9), (0x172D5, 0x172D6), (0x17472, 0x1747D),
    (0x1A012, 0x1A014), (0x1A01E, 0x1A021), (0x1A03C, 0x1A060), (0x1A06E, 0x1A074), (0x1A2C8, 0x1AD64),
    (0x1E000, 0x1E010), (0x1E945, 0x1E94C), (0x1EB2D, 0x1EB2E), (0x1EB8C, 0x1EB9D), (0x1EC19, 0x1EC1A),
    (0x1ED4C, 0x1ED4D), (0x1F063, 0x1F064), (0x1F08A, 0x1F08B), (0x1F09B, 0x1F09C), (0x1FD20, 0x1FD21),
    (0x20000, 0x20002),
)

# PRG1's bytes that PRG0's layout image holds as PRG0 has them, so that a world parsed from
# PRG1 equals one parsed from PRG0 (the parser reads both):
DMC_LEVEL_OPERAND = 0x01BC4     # layout.DMC_LEVEL_OPERAND_ADDRESS: PRG1 sets $40, as B10 does
PRG0_DMC_LEVEL = 0x7F
TRADEMARK_TILE = BOSS_SET_EXPANSION_SPRITES_ADDRESS     # PRG1's "TM" glyph, background tile $30
TILE_SIZE = 16

# ZORA writes into PRG1's changed bytes at these places only, PRG0's layout and PRG1's alike:
# the boss expansion block (the boss groups' common block, from tile $30) and Select Swap's
# TransferBufAddrs entry (its "off" value is an Original, read from the player's ROM).
TRANSFER_BUF_ADDRS_SELECT_SWAP = 0x1A040
WRITABLE_CHANGED = (
    (BOSS_SET_EXPANSION_SPRITES_ADDRESS, BOSS_SET_EXPANSION_SPRITES_ADDRESS + BOSS_SET_EXPANSION_SPRITES_SIZE),
    (TRANSFER_BUF_ADDRS_SELECT_SWAP, TRANSFER_BUF_ADDRS_SELECT_SWAP + 2),
)

# Operands and pointers ZORA writes outside the moved code and data that point into it, each
# moved with what it points at:
# - Music: Off's `JSR $9D46` (bank 0's moved audio code; $9D42 on PRG1);
# - Select Swap's TransferBufAddrs entry: Swap only restores PRG0's pointer, $A316, to a
#   transfer buffer PRG1 moves ($A3A1); "off" reads the player's own (an Original), "toggle"
#   points at RAM;
# - Pegasus Boots' `JSR BootsSpeed` in InitLinkSpeed: BootsSpeed is in WieldBoomerang's old body
#   ($8E3E), inside bank 5's moved code ($8E48 on PRG1);
# - Red Bubble Curse's slow speed with Pegasus Boots: its routine's own `JSR BootsSpeed`
#   (uphill_battle.SLOW_SPEED_CALLED; without the boots the word there is RAM's $052E or free
#   space, which no move holds);
# - Rupees Affect Speed with Pegasus Boots: its routine's own `JSR BootsSpeed`
#   (small_settings.RUPEE_BOOTS_CALLED; without the boots the word there is RAM's $066D or free
#   space).
# tests/test_revision.py scans every patch for other operands.
MUSIC_OFF_AUDIO_CALL = 0x02228       # the JSR's operand in Music: Off's routine at bank 0's $A200
PEGASUS_BOOTS_SPEED_CALL = 0x17377
SLOW_SPEED_BOOTS_CALL = 0x17D11
RUPEE_SPEED_BOOTS_CALL = 0x1791B
MOVED_POINTERS = (MUSIC_OFF_AUDIO_CALL, TRANSFER_BUF_ADDRS_SELECT_SWAP, PEGASUS_BOOTS_SPEED_CALL, SLOW_SPEED_BOOTS_CALL,
                  RUPEE_SPEED_BOOTS_CALL)

# The title screen (GameTitleTransferBuf; FP-TITLE-01's rows): PRG1 draws its "TM" glyph
# (tile $30) beside the logo, at row 8, column 23. ZORA's rows and its boss tiles in tile $30
# change what PRG0's title screen shows; with either, PRG1's title cell gets PRG0's blank, so the
# two title screens look the same (owner ruling 1).
TITLE_TRADEMARK_CELL = 0x1A9AB      # PRG0's layout; PRG1's 0x1AA36
TITLE_BLANK_TILE = 0x24
TITLE_ROWS = ((0x1AAD3, 24), (0x1AB19, 24))     # layout.TITLE_SEED_ROW_ADDRESS, TITLE_VERSION_ROW_ADDRESS

BANK_SIZE = 0x4000
FIXED_BANK = 7
SWITCHABLE_BANK_CPU = 0x8000
FIXED_BANK_CPU = 0xC000


def bank_of(offset: int) -> int:
    return (offset - NES_HEADER_SIZE) // BANK_SIZE


def cpu_to_file(bank: int, cpu: int) -> int:
    """The file offset of a CPU address seen from code in `bank`: $C000 and up is the fixed bank."""
    if cpu >= FIXED_BANK_CPU:
        return NES_HEADER_SIZE + FIXED_BANK * BANK_SIZE + cpu - FIXED_BANK_CPU
    return NES_HEADER_SIZE + bank * BANK_SIZE + cpu - SWITCHABLE_BANK_CPU


def move_of(offset: int) -> Move | None:
    return next((move for move in PRG1_MOVES if offset in move), None)


def prg1_offset(offset: int) -> int:
    """Where PRG0's file offset `offset` is in PRG1."""
    move = move_of(offset)
    return offset + move.shift if move else offset


def _within(offset: int, windows: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= offset < end for start, end in windows)


@cache
def _prg1_occupied() -> frozenset[int]:
    """PRG1's changed bytes and every byte the moves fill: no write in PRG0's layout outside
    the moves may land on them."""
    occupied = {offset for start, end in PRG1_CHANGED for offset in range(start, end)}
    occupied |= {offset + move.shift for move in PRG1_MOVES for offset in range(move.start, move.end)}
    return frozenset(occupied)


# Where GameTitleTransferBuf's first record (name table $2000, 32 tiles: $20 $00 $20) starts in
# each release's layout; ZORA never writes it. It tells which layout any ROM made from them has,
# a finished ROM too, and an image already moved into PRG0's layout reads as PRG0's.
TITLE_FIRST_RECORD = bytes([0x20, 0x00, 0x20])
TITLE_BUFFER = {Revision.PRG0: 0x1A879, Revision.PRG1: 0x1A879 + 139}


def layout_of(rom: bytes) -> Revision | None:
    """Whose layout a headered ROM has (a finished ROM too), or None for neither."""
    for revision, start in TITLE_BUFFER.items():
        if rom[start:start + len(TITLE_FIRST_RECORD)] == TITLE_FIRST_RECORD:
            return revision
    return None


def moved_to_prg0_layout(data: bytes) -> bytes:
    """A headered ROM in PRG1's layout with its moved code and data back at PRG0's offsets, and
    the pointers of MOVED_POINTERS pointing at them there (so an Original of one reads as PRG0's
    and back_to_revision moves it on again). PRG1's other changes stay where they are."""
    image = bytearray(data)
    for move in PRG1_MOVES:
        image[move.start:move.end] = data[move.start + move.shift:move.end + move.shift]
    for site in MOVED_POINTERS:
        target = image[site] | image[site + 1] << 8
        if target < SWITCHABLE_BANK_CPU:
            continue
        moved = next((move for move in PRG1_MOVES
                      if move.start + move.shift <= cpu_to_file(bank_of(site), target) < move.end + move.shift), None)
        if moved is not None:
            target -= moved.shift
            image[site], image[site + 1] = target & 0xFF, target >> 8
    return bytes(image)


def finished_in_prg0_layout(rom: bytes) -> bytes:
    """Any ROM in PRG0's layout, for the parser: a finished ROM made from PRG1 moved back, any
    other as it is."""
    return moved_to_prg0_layout(rom) if layout_of(rom) is Revision.PRG1 else rom


def in_prg0_layout(data: bytes, revision: Revision) -> bytes:
    """The player's ROM (with its header) in PRG0's layout: PRG0 itself; PRG1 with its moved
    code and data back at PRG0's offsets and the bytes the parser reads made PRG0's
    (DMC_LEVEL_OPERAND, TRADEMARK_TILE). PRG1's other changes stay where they are, unread."""
    if revision is Revision.PRG0:
        return data
    image = bytearray(moved_to_prg0_layout(data))
    image[DMC_LEVEL_OPERAND] = PRG0_DMC_LEVEL
    image[TRADEMARK_TILE:TRADEMARK_TILE + TILE_SIZE] = bytes(TILE_SIZE)
    return bytes(image)


class WriteOnMovedBytes(ValueError):
    """A write in PRG0's layout that would land on bytes PRG1 changed or moved: a new patch site
    that needs an entry in this module."""


def _changed(before: bytes, after: bytes) -> Iterator[int]:
    """The offsets where `after` differs from `before`, found a block at a time (most blocks are
    equal; this runs once per PRG1 ROM)."""
    block = 256
    for start in range(0, len(after), block):
        if after[start:start + block] != before[start:start + block]:
            for offset in range(start, min(start + block, len(after))):
                if after[offset] != before[offset]:
                    yield offset


def back_to_revision(data: bytes, revision: Revision, before: bytes, after: bytes) -> bytes:
    """The finished ROM on the player's own release: `after` is the image ZORA wrote in PRG0's
    layout (from `before`, in_prg0_layout(data)). On PRG1 each changed byte goes to its PRG1
    offset over the player's ROM, the pointers into moved code and data ZORA wrote are moved too, and the
    title's TM glyph is blanked when ZORA changed what the title shows."""
    if revision is Revision.PRG0:
        return after
    out = bytearray(data)
    occupied = _prg1_occupied()
    changed = list(_changed(before, after))
    # The trademark tile holds PRG0's zeros in the image: once ZORA changes any of it, all of it
    # is ZORA's (a boss tile's zero bytes are not changes, but must still replace PRG1's glyph).
    trademark = range(TRADEMARK_TILE, TRADEMARK_TILE + TILE_SIZE)
    if any(offset in trademark for offset in changed):
        changed = sorted(set(changed) | set(trademark))
    for offset in changed:
        if move_of(offset) is None and offset in occupied and not _within(offset, WRITABLE_CHANGED):
            raise WriteOnMovedBytes(f"a write at 0x{offset:05X} lands on bytes PRG1 changes or moves")
        out[prg1_offset(offset)] = after[offset]
    written = set(changed)
    for site in MOVED_POINTERS:
        if written & {site, site + 1}:
            target = after[site] | after[site + 1] << 8
            move = move_of(cpu_to_file(bank_of(site), target)) if target >= SWITCHABLE_BANK_CPU else None
            if move is not None:
                target += move.shift
                out[prg1_offset(site)], out[prg1_offset(site) + 1] = target & 0xFF, target >> 8
    title_changed = any(written & set(range(start, start + length)) for start, length in TITLE_ROWS)
    if title_changed or written & set(range(TRADEMARK_TILE, TRADEMARK_TILE + TILE_SIZE)):
        out[prg1_offset(TITLE_TRADEMARK_CELL)] = TITLE_BLANK_TILE
    return bytes(out)
