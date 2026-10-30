"""Mirror Overworld (B06; overworld-behavior.md OW-MIR-01 to OW-MIR-06): the overworld flipped left to
right, written as OW-MIR-01's MAY allows (a seed made as without B06, then flipped).

Screen s becomes its mirror m(s) = s XOR $0F (same row, column c becomes 15 - c); a square column x
becomes 15 - x, so a byte holding one in its high nibble is flipped by XOR $F0, one holding it in its
low nibble by XOR $0F. Caves and dungeons are not flipped.

The flip has two parts. What the model holds (the screen tables, the start screen, the Any Road and
Armos screens, the whirlwind list, the recorder's screens, the mazes) is flipped in the model, on the
copy FINISH writes (zora/generate/steps/mirror_overworld.py, pipeline.written_world), so a mirrored ROM
parsed back gives the same world (game data in the model, 2026-10-13). The rest is mirror_image's,
which the code patches' step runs last on a mirrored world (final_steps.write_code_patches): after every
other write to the overworld (the code patches' bridges, shortcut and hidden tiles among them, OW-MIR-06)
and before the level encoding (the tournament relocation, FP-TOURNEY-01). The parser knows a mirrored
ROM by the spawn call (is_mirrored), and a mirrored ROM written again is unmirrored first
(unmirror_image), so the patches go over PRG0's bytes as on a new seed.

A byte of PRG0's code that the flip rewrites (OW-MIR-04, the spawn call, the caption pointer) must
hold PRG0's value when the step runs: a ZORA patch that changed one first would need its own flip,
so the step stops with the offset instead of writing over it."""
from collections.abc import Iterable

# --- Notation ------------------------------------------------------------------------------------
SCREENS = 0x80
MIRROR_SCREEN = 0x0F                 # s XOR $0F: the screen's column flipped
HIGH_NIBBLE_COLUMN = 0xF0            # a square column in bits 7-4
LOW_NIBBLE_COLUMN = 0x0F             # a square column in bits 3-0
BYTE = 0x100

# --- OW-MIR-02: screen tables, layouts, column heaps ---------------------------------------------
SCREEN_TABLES = 0x18410              # LevelBlockOW: tables A to F, one byte per screen each
SCREEN_TABLE_COUNT = 6
EXIT_TABLE = 0                       # table A: bits 7-4 the cave-exit column, bits 1-0 a palette
CAVE_TABLE = 4                       # table E, indexed by cave, not by screen (OW-SHOP-01): not moved
ROOM_LAYOUTS_OW = 0x15428            # 124 rows of 16 column codes
LAYOUT_ROWS, LAYOUT_WIDTH = 124, 16
CAVE_ROOM_ROWS = frozenset({121, 122})   # RoomLayoutOWCave0 and RoomLayoutOWCave1: every cave keeps PRG0's look
# Column codes drawn as each other's mirror image
EXCHANGED_COLUMN_CODES = ((0x64, 0x66), (0xF2, 0xD8), (0xF3, 0xE5))
# ColumnHeapOW0 to ColumnHeapOWF, but for the last heap byte ($1B), which no pair names
COLUMN_HEAPS = range(0x15BF8, 0x15FAB)
SQUARE_TYPE_MASK = 0x3F              # a heap byte's square type; bits 7-6 are kept
# The squares drawn differently on their left and right side
EXCHANGED_SQUARES = ((0x34, 0x35), (0x32, 0x33), (0x08, 0x09), (0x15, 0x16), (0x17, 0x18), (0x2E, 0x2F),
                     (0x30, 0x31), (0x21, 0x23), (0x24, 0x25))

# --- OW-MIR-03: screen numbers and positions in the seed's records -------------------------------
START_ROOM = 0x1933F                 # LevelInfo_StartRoomId of the overworld
SHORTCUT_POSITIONS = range(0x19339, 0x1933D)   # LevelInfo_ShortcutOrItemPosArray: a column in bits 7-4
SHORTCUT_SCREENS = range(0x19344, 0x19348)     # LevelInfo_CellarRoomIdArray
ARMOS_SCREENS = range(0x10CC2, 0x10CC9)        # SecretArmosRoomIds
ARMOS_XS = range(0x10CC9, 0x10CD0)             # SecretArmosXs
WHIRLWIND_SCREENS = range(0x6020, 0x6028)      # WhirlwindPrevRoomIdList: the screen left of the arrival
RECORDER_SECRET_SCREENS = range(0x1EF76, 0x1EF81)  # FluteRoomSecretsOW ($80, a placeholder, becomes $8F)

# --- OW-MIR-04: room numbers and positions in PRG0's code (offset, PRG0's value, the new value) ---
CODE_SITES: tuple[tuple[int, int, int], ...] = (
    (0x1EEAA, 0x1F, 0x10), (0x1EEB6, 0x80, 0x70),      # the false wall of screen $1F and Link's X
    (0x17412, 0x22, 0x2D),                             # level 6's wide entrance (CheckWarps)
    (0x06DB7, 0x61, 0x6E), (0x06DD9, 0x1B, 0x14),      # the forest and mountain mazes' screens
    (0x14954, 0x3F, 0x30), (0x14958, 0x55, 0x5A),      # the dock screens (SetupTileObjectOW)
    (0x10F90, 0x80, 0x70), (0x10F94, 0x55, 0x5A), (0x10F98, 0x60, 0x90),  # the dock's X (UpdateDock)
    (0x1EA9C, 0x0F, 0x00),                             # the "secret found" tune on walking into screen $0F
    (0x178AA, 0x5F, 0x50),                             # the coast heart container's screen
    (0x1FF3A, 0x60, 0x90),                             # the pond stairs' X (RevealPondStairs)
    (0x1717C, 0x44, 0x4B),                             # the screen whose attributes a cave borrows
)
# The coast item's X (LDA #$C0 before @StoreLocation's STA ObjX+19). With ZORA's progressive items
# (fp-prog-02's coast-item hook) the load moves into StoreCoastItemAtNextLevel, reached by the JSR that
# replaces it, whose last instructions are LDA #$C0 / RTS.
COAST_ITEM_X = 0x1789E
PRG0_COAST_ITEM_X, MIRRORED_COAST_ITEM_X = 0xC0, 0x30
COAST_ITEM_HOOK = 0x1789B
COAST_ROUTINE_SEARCH = 0x20          # bytes of the hook's routine searched for the X's load
LDA_IMMEDIATE = 0xA9
LADDER_SCREENS = 0x1F21D             # LadderRoomsOW
PRG0_LADDER_SCREENS = bytes([0x17, 0x18, 0x19, 0x27, 0x4F, 0x5F])
MIRRORED_LADDER_SCREENS = bytes([0x18, 0x17, 0x16, 0x28, 0x40, 0x50])
# The mazes' steps (ForestMazeDirs, forest then mountain) and free exits: right (1) and left (2) exchange
MAZE_STEPS = range(0x06DA7, 0x06DAF)
MAZE_FREE_EXITS = (0x06DD0, 0x06DE2)
RIGHT, LEFT = 0x01, 0x02

# --- OW-MIR-05: the monster spawn spots and the TRIFORCE caption ---------------------------------
SPAWN_LISTS = 0x1465E                # SpawnPosList0 to SpawnPosList3, nine spots each (row in bits 7-4)
SPAWN_LIST_COUNT, SPAWN_LIST_LENGTH = 4, 9
# The overworld's copies (lists 0 and 1 exchanged, every column flipped) and the routine that points
# the spawn list at them on the overworld, in bank 5's linker gap (OW-MIR-05's MAY: the spec's own
# build uses PRG0's $FF block at $85B8, which the music patches take)
BANK_5_FILE, BANK_CPU = 0x14010, 0x8000
SPAWN_ROUTINE_CPU = 0xBF00
SPAWN_COPIES_CPU = 0xBF20
SPAWN_COPY_POINTERS_CPU = 0xBF44     # four low bytes, then four high bytes
SPAWN_ROUTINE, SPAWN_COPIES, SPAWN_COPY_POINTERS = (BANK_5_FILE + cpu - BANK_CPU for cpu in (
    SPAWN_ROUTINE_CPU, SPAWN_COPIES_CPU, SPAWN_COPY_POINTERS_CPU))
CUR_LEVEL, SPAWN_LIST_POINTER, SPAWN_CYCLE = 0x10, 0x06, 0x0524
LDA_ZERO_PAGE, BNE, LDA_ABSOLUTE_Y, STA_ZERO_PAGE, LDY_ABSOLUTE, RTS, JSR = 0xA5, 0xD0, 0xB9, 0x85, 0xAC, 0x60, 0x20
OVERWORLD_ONLY_SKIP = 0x0A           # past the two loads and stores, to the replaced LDY


def _word(address: int) -> bytes:
    return bytes([address & 0xFF, address >> 8])


# LDA CurLevel / BNE (not the overworld) / LDA lows,Y / STA $06 / LDA highs,Y / STA $07 / LDY SpawnCycle / RTS
SPAWN_ROUTINE_BYTES = bytes([LDA_ZERO_PAGE, CUR_LEVEL, BNE, OVERWORLD_ONLY_SKIP,
                             LDA_ABSOLUTE_Y, *_word(SPAWN_COPY_POINTERS_CPU), STA_ZERO_PAGE, SPAWN_LIST_POINTER,
                             LDA_ABSOLUTE_Y, *_word(SPAWN_COPY_POINTERS_CPU + SPAWN_LIST_COUNT),
                             STA_ZERO_PAGE, SPAWN_LIST_POINTER + 1,
                             LDY_ABSOLUTE, *_word(SPAWN_CYCLE), RTS])
SPAWN_CALL = 0x149AB                 # LDY SpawnCycle, replaced by JSR to the routine
PRG0_SPAWN_CALL = bytes([LDY_ABSOLUTE, *_word(SPAWN_CYCLE)])
SPAWN_CALL_BYTES = bytes([JSR, *_word(SPAWN_ROUTINE_CPU)])
# The caption's own copy of its transfer record, ending in $FF, and its pointer (bank 6). Its bytes are
# copied from the record PRG0 keeps at 0x19D6B, which ends in $FF: the PPU address $2BAC, eight
# letters, then the end mark
CAPTION_RECORD = 0x1AD80             # CPU $AD70, in bank 6's linker gap
CAPTION_SOURCE = 0x19D6B
CAPTION_RECORD_SIZE = 12
CAPTION_HEADER = bytes([0x2B, 0xAC, 0x08])
END_OF_RECORD = 0xFF
CAPTION_POINTER = 0x1A06C
PRG0_CAPTION_POINTER = bytes.fromhex("7368")
CAPTION_POINTER_BYTES = bytes.fromhex("70AD")


def mirror_screen(screen: int) -> int:
    """m(s): the screen with its column flipped, in the same row."""
    return screen ^ MIRROR_SCREEN


def _flip_screen_tables(rom: bytearray) -> None:
    """OW-MIR-02 step 1: tables A to D and F re-indexed by m(s); then table A's exit column flipped."""
    for table in range(SCREEN_TABLE_COUNT):
        if table == CAVE_TABLE:
            continue
        start = SCREEN_TABLES + table * SCREENS
        old = bytes(rom[start:start + SCREENS])
        rom[start:start + SCREENS] = bytes(old[mirror_screen(screen)] for screen in range(SCREENS))
    exits = SCREEN_TABLES + EXIT_TABLE * SCREENS
    for offset in range(exits, exits + SCREENS):
        rom[offset] ^= HIGH_NIBBLE_COLUMN


def _exchange(value: int, pairs: Iterable[tuple[int, int]]) -> int:
    for first, second in pairs:
        if value == first:
            return second
        if value == second:
            return first
    return value


def _flip_layouts(rom: bytearray) -> None:
    """OW-MIR-02 step 2: every layout row but the two cave rooms reversed, the mirror codes exchanged."""
    for row in range(LAYOUT_ROWS):
        if row in CAVE_ROOM_ROWS:
            continue
        start = ROOM_LAYOUTS_OW + row * LAYOUT_WIDTH
        codes = rom[start:start + LAYOUT_WIDTH]
        rom[start:start + LAYOUT_WIDTH] = bytes(_exchange(code, EXCHANGED_COLUMN_CODES) for code in reversed(codes))


def _flip_column_heaps(rom: bytearray) -> None:
    """OW-MIR-02 step 3: each heap byte's square type exchanged with its mirror square."""
    for offset in COLUMN_HEAPS:
        square = rom[offset] & SQUARE_TYPE_MASK
        rom[offset] = (rom[offset] & ~SQUARE_TYPE_MASK) | _exchange(square, EXCHANGED_SQUARES)


def _flip_records(rom: bytearray) -> None:
    """OW-MIR-03: the start screen, the shortcut stairs, the secret Armos, the whirlwind and the
    recorder's secret screens. The model holds all but the shortcut stairs' columns
    (zora/generate/steps/mirror_overworld.py flips them there); this is the finished image's reference."""
    rom[START_ROOM] = mirror_screen(rom[START_ROOM])
    for screens in (SHORTCUT_SCREENS, ARMOS_SCREENS, RECORDER_SECRET_SCREENS):
        for offset in screens:
            rom[offset] = mirror_screen(rom[offset])
    for offset in ARMOS_XS:
        rom[offset] ^= HIGH_NIBBLE_COLUMN
    for offset in WHIRLWIND_SCREENS:
        # the screen left of the flipped arrival: OW-WARP-01's rule on the flipped door
        rom[offset] = (mirror_screen((rom[offset] + 1) % BYTE) - 1) % BYTE
    for offset in MAZE_STEPS:
        rom[offset] = _exchange(rom[offset], ((RIGHT, LEFT),))


def _flip_shortcut_columns(rom: bytearray) -> None:
    """OW-MIR-03: the shortcut stairs' columns (LevelInfo_ShortcutOrItemPosArray), which the model does
    not hold. Its own inverse."""
    for offset in SHORTCUT_POSITIONS:
        rom[offset] ^= HIGH_NIBBLE_COLUMN


def _expect(rom: bytearray, offset: int, value: bytes) -> None:
    found = bytes(rom[offset:offset + len(value)])
    if found != value:
        raise ValueError(f"Mirror Overworld: 0x{offset:05X} holds {found.hex()}, not PRG0's {value.hex()}; "
                         "a patch changed it, so the flip needs that patch's own rule (OW-MIR-04)")


def _flip_code(rom: bytearray) -> None:
    """OW-MIR-04: PRG0's code bytes naming a screen or an X, and the mazes' free exits."""
    for offset, prg0, value in CODE_SITES:
        _expect(rom, offset, bytes([prg0]))
        rom[offset] = value
    _flip_coast_item_x(rom)
    _expect(rom, LADDER_SCREENS, PRG0_LADDER_SCREENS)
    rom[LADDER_SCREENS:LADDER_SCREENS + len(MIRRORED_LADDER_SCREENS)] = MIRRORED_LADDER_SCREENS
    for offset in MAZE_FREE_EXITS:
        rom[offset] = _exchange(rom[offset], ((RIGHT, LEFT),))


def _unflip_code(rom: bytearray) -> None:
    """_flip_code undone: PRG0's code bytes back."""
    for offset, prg0, value in CODE_SITES:
        _expect(rom, offset, bytes([value]))
        rom[offset] = prg0
    _flip_coast_item_x(rom, back=True)
    _expect(rom, LADDER_SCREENS, MIRRORED_LADDER_SCREENS)
    rom[LADDER_SCREENS:LADDER_SCREENS + len(PRG0_LADDER_SCREENS)] = PRG0_LADDER_SCREENS
    for offset in MAZE_FREE_EXITS:
        rom[offset] = _exchange(rom[offset], ((RIGHT, LEFT),))


def _flip_coast_item_x(rom: bytearray, back: bool = False) -> None:
    """OW-MIR-04: the coast item's X, $C0 to $30 ($30 to $C0 going back), in PRG0's code or in
    fp-prog-02's hook routine."""
    old, new = (MIRRORED_COAST_ITEM_X, PRG0_COAST_ITEM_X) if back else (PRG0_COAST_ITEM_X, MIRRORED_COAST_ITEM_X)
    if rom[COAST_ITEM_X] == old and rom[COAST_ITEM_HOOK] != JSR:
        rom[COAST_ITEM_X] = new
        return
    _expect(rom, COAST_ITEM_HOOK, bytes([JSR]))
    target = rom[COAST_ITEM_HOOK + 1] | rom[COAST_ITEM_HOOK + 2] << 8
    routine = BANK_5_FILE + target - BANK_CPU
    found = rom.find(bytes([LDA_IMMEDIATE, old, RTS]), routine, routine + COAST_ROUTINE_SEARCH)
    if found < 0:
        raise ValueError(f"Mirror Overworld: the coast-item hook's routine at 0x{routine:05X} has no "
                         f"LDA #${old:02X} / RTS")
    rom[found + 1] = new


def mirrored_spawn_lists(rom: bytes | bytearray) -> bytes:
    """OW-MIR-05 item 1: the overworld's spawn lists, lists 0 and 1 exchanged, each spot's column flipped."""
    lists = [rom[SPAWN_LISTS + index * SPAWN_LIST_LENGTH:SPAWN_LISTS + (index + 1) * SPAWN_LIST_LENGTH]
             for index in range(SPAWN_LIST_COUNT)]
    lists[0], lists[1] = lists[1], lists[0]
    return b"".join(bytes(spot ^ LOW_NIBBLE_COLUMN for spot in spots) for spots in lists)


def _write_spawn_spots(rom: bytearray) -> None:
    """OW-MIR-05 item 1: the copies, their pointers, the routine and its call."""
    _expect(rom, SPAWN_CALL, PRG0_SPAWN_CALL)
    copies = mirrored_spawn_lists(rom)
    pointers = [SPAWN_COPIES_CPU + index * SPAWN_LIST_LENGTH for index in range(SPAWN_LIST_COUNT)]
    pointer_bytes = bytes(pointer & 0xFF for pointer in pointers) + bytes(pointer >> 8 for pointer in pointers)
    for offset, data in ((SPAWN_ROUTINE, SPAWN_ROUTINE_BYTES), (SPAWN_COPIES, copies),
                         (SPAWN_COPY_POINTERS, pointer_bytes), (SPAWN_CALL, SPAWN_CALL_BYTES)):
        rom[offset:offset + len(data)] = data


def _write_caption(rom: bytearray) -> None:
    """OW-MIR-05 item 2: the TRIFORCE caption ends on its own $FF, whatever table A's first byte is."""
    _expect(rom, CAPTION_POINTER, PRG0_CAPTION_POINTER)
    record = bytes(rom[CAPTION_SOURCE:CAPTION_SOURCE + CAPTION_RECORD_SIZE])
    if record[:len(CAPTION_HEADER)] != CAPTION_HEADER or record[-1] != END_OF_RECORD:
        raise ValueError(f"Mirror Overworld: 0x{CAPTION_SOURCE:05X} holds {record.hex()}, not the caption's record")
    rom[CAPTION_RECORD:CAPTION_RECORD + CAPTION_RECORD_SIZE] = record
    rom[CAPTION_POINTER:CAPTION_POINTER + len(CAPTION_POINTER_BYTES)] = CAPTION_POINTER_BYTES


def is_mirrored(rom: bytes | bytearray) -> bool:
    """Whether an image's overworld is mirrored: the spawn call (OW-MIR-05) is the flip's own, a JSR
    no other patch writes there (the parser's test; zora/rom/parse/rom_file.py)."""
    return bytes(rom[SPAWN_CALL:SPAWN_CALL + len(SPAWN_CALL_BYTES)]) == SPAWN_CALL_BYTES


def mirror_image(rom: bytearray) -> None:
    """OW-MIR-02 to OW-MIR-05's writes the model does not hold, on the image in place, once: the layout
    rows, the column heaps, the shortcut stairs' columns, the code sites, the spawn spots and the
    caption. The model's own part (the screen tables, the records) is flipped in the model before
    serialization (zora/generate/steps/mirror_overworld.py), so a parsed mirrored world written again
    gets the same bytes (final_steps.write_code_patches)."""
    _flip_layouts(rom)
    _flip_column_heaps(rom)
    _flip_shortcut_columns(rom)
    _flip_code(rom)
    _write_spawn_spots(rom)
    _write_caption(rom)


def unmirror_image(rom: bytearray) -> None:
    """mirror_image undone on a mirrored image (is_mirrored), before the code patches are written
    again over it: the flipped layouts, heaps and columns flipped back (each step its own inverse),
    PRG0's code bytes, spawn call and caption pointer back. The routine, the copies and the caption
    record stay; mirror_image writes them the same."""
    _flip_layouts(rom)
    _flip_column_heaps(rom)
    _flip_shortcut_columns(rom)
    _unflip_code(rom)
    rom[SPAWN_CALL:SPAWN_CALL + len(PRG0_SPAWN_CALL)] = PRG0_SPAWN_CALL
    rom[CAPTION_POINTER:CAPTION_POINTER + len(PRG0_CAPTION_POINTER)] = PRG0_CAPTION_POINTER


def mirror_overworld(rom: bytearray) -> None:
    """The whole flip of a finished image (OW-MIR-02 to OW-MIR-05): the model's part as the image holds
    it, then mirror_image. Generation flips the model instead; the tests check that a mirrored seed is
    its unmirrored seed flipped by this."""
    _flip_screen_tables(rom)
    _flip_records(rom)
    mirror_image(rom)
