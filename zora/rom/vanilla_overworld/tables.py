"""Where the overworld tables sit in the PRG0 base ROM.

Every address is a label of the pinned aldonunez disassembly (AGENTS.md,
commit 50a1c86). The PRG offsets were taken from ld65's debug file after
assembling those sources against the PRG0 base (byte-identical), and the
readers' tests check each table's first bytes against the values the
disassembly lists.

A PRG offset counts from the start of PRG ROM; the file offset adds the
16-byte iNES header. Banks 0-6 map at CPU $8000-$BFFF, bank 7 at $C000.
"""
from dataclasses import dataclass

INES_HEADER_SIZE = 0x10
BANK_SIZE = 0x4000
SWITCHABLE_BANK_CPU_BASE = 0x8000


def cpu_to_prg(bank: int, cpu_address: int) -> int:
    """The PRG offset of a CPU address in a switchable bank (0-6)."""
    assert 0 <= bank <= 6 and SWITCHABLE_BANK_CPU_BASE <= cpu_address < SWITCHABLE_BANK_CPU_BASE + BANK_SIZE
    return bank * BANK_SIZE + cpu_address - SWITCHABLE_BANK_CPU_BASE


@dataclass(frozen=True)
class RomTable:
    """One labelled table: its disassembly label, where it lives, its size."""
    label: str
    source: str          # the disassembly file and how the CPU sees it
    prg_offset: int
    size: int

    @property
    def file_offset(self) -> int:
        return self.prg_offset + INES_HEADER_SIZE

    def read(self, rom: bytes) -> bytes:
        """The table's bytes from a headered ROM image."""
        start = self.file_offset
        data = rom[start:start + self.size]
        assert len(data) == self.size, f"{self.label}: ROM too short"
        return data


SCREEN_COUNT = 0x80                  # overworld room ids $00-$7F
ATTRIBUTE_TABLE_SIZE = 0x80          # one byte per room in each of tables A-F
OW_LAYOUT_COUNT = 121                # RoomLayoutsOW: 1,936 bytes / 16 columns
LAYOUT_COLUMNS = 0x10
CAVE_LAYOUT_COUNT = 3                # RoomLayoutOWCave0..2
COLUMN_HEAP_COUNT = 0x10             # ColumnHeapOW0..ColumnHeapOWF
CAVE_COUNT = 20                      # cave dwellers: object types $6A-$7D
WARES_PER_CAVE = 3
RECORDER_LEVELS = 8                  # levels 1-8
LEVEL_INFO_SIZE = 0xFC

# Z_06.asm, bank 6 ($8400): the overworld's room attributes, six tables of
# $80 bytes loaded to LevelBlockAttrsA-F ($687E-$6AFD).
LEVEL_BLOCK_OW = RomTable("LevelBlockOW", "Z_06.asm, bank 6 $8400", 0x18400,
                          6 * ATTRIBUTE_TABLE_SIZE)
# Z_06.asm, bank 6 ($9300): the overworld's level info, loaded to
# LevelInfo_PalettesTransferBuf ($6B7E).
LEVEL_INFO_OW = RomTable("LevelInfoOW", "Z_06.asm, bank 6 $9300", 0x19300, LEVEL_INFO_SIZE)
# Z_05.asm, bank 5 ($9418): 16 column descriptors per unique screen layout.
ROOM_LAYOUTS_OW = RomTable("RoomLayoutsOW", "Z_05.asm, bank 5 $9418", 0x15418,
                           OW_LAYOUT_COUNT * LAYOUT_COLUMNS)
# Z_05.asm, bank 5 ($9BA8): the three cave interiors' column descriptors
# (RoomLayoutOWCave0, 1, 2 follow each other).
ROOM_LAYOUTS_OW_CAVE = RomTable("RoomLayoutOWCave0", "Z_05.asm, bank 5 $9BA8", 0x15BA8,
                                CAVE_LAYOUT_COUNT * LAYOUT_COLUMNS)
# Z_06.asm, segment BANK_06_DATA: stored in bank 6, copied to RAM $6827.
# Sixteen little-endian pointers into bank 5, one per ColumnHeapOW0-F.
COLUMN_DIRECTORY_OW = RomTable("ColumnDirectoryOW", "Z_06.asm, BANK_06_DATA, runs at $6827",
                               0x19D0F, 2 * COLUMN_HEAP_COUNT)
COLUMN_HEAP_BANK = 5
# Z_05.asm, bank 5 ($A97C): the first tile of each square index.
PRIMARY_SQUARES_OW = RomTable("PrimarySquaresOW", "Z_05.asm, bank 5 $A97C", 0x1697C, 0x38)
# Z_05.asm, bank 5 ($A9B4): four tiles for each square index below $10.
SECONDARY_SQUARES_OW = RomTable("SecondarySquaresOW", "Z_05.asm, bank 5 $A9B4", 0x169B4, 0x40)
# Z_01.asm, bank 1 ($85A2): per cave dweller, the person text selector
# (bits 0-5) and the "pay" / "pick up" cave flags (bits 7, 6).
OVERWORLD_PERSON_TEXT_SELECTORS = RomTable("OverworldPersonTextSelectors",
                                           "Z_01.asm, bank 1 $85A2", 0x045A2, CAVE_COUNT)
# Z_01.asm, bank 1 ($A010): per recorder destination, the room that acts
# as the previous room while scrolling right into the level's entrance.
WHIRLWIND_PREV_ROOM_ID_LIST = RomTable("WhirlwindPrevRoomIdList", "Z_01.asm, bank 1 $A010",
                                       0x06010, RECORDER_LEVELS)
# Z_01.asm, bank 1 ($A119): the whirlwind's Y where it drops Link.
TELEPORT_YS = RomTable("TeleportYs", "Z_01.asm, bank 1 $A119", 0x06119, RECORDER_LEVELS)
# Z_06.asm, bank 6 ($815F / $8167): the second quest's eight overworld
# LevelBlockAttrsB replacements (offsets from LevelBlockAttrsB, values).
Q2_B_REPLACEMENT_OFFSETS = RomTable("LevelBlockAttrsBQ2ReplacementOffsets",
                                    "Z_06.asm, bank 6 $815F", 0x1815F, 8)
Q2_B_REPLACEMENT_VALUES = RomTable("LevelBlockAttrsBQ2ReplacementValues",
                                   "Z_06.asm, bank 6 $8167", 0x18167, 8)
# Z_04.asm, bank 4 ($8CB2 / $8CB9): the secret Armos formation's seven
# screens and their Xs (position 0 is the screen whose armos hides the item).
ARMOS_FORMATION_SIZE = 7
SECRET_ARMOS_ROOM_IDS = RomTable("SecretArmosRoomIds", "Z_04.asm, bank 4 $8CB2", 0x10CB2,
                                 ARMOS_FORMATION_SIZE)
SECRET_ARMOS_XS = RomTable("SecretArmosXs", "Z_04.asm, bank 4 $8CB9", 0x10CB9, ARMOS_FORMATION_SIZE)
