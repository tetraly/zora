"""ROM layout constants for Zelda 1 (NES).

All file offsets include the 0x10-byte iNES header unless noted otherwise
(file offset = ROM address + NES_HEADER_SIZE).

This module imports only zora.rom.base_rom (which imports nothing from zora), so it
is safe to import from parser, serializer, and tests without circular dependencies.
"""
from zora.rom.base_rom import Original, Piece

# ---------------------------------------------------------------------------
# iNES header
# ---------------------------------------------------------------------------

NES_HEADER_SIZE = 0x10


def ines_header(rom: bytes) -> bytes:
    """The ROM image's iNES header (generation must never change it)."""
    return rom[:NES_HEADER_SIZE]

# ---------------------------------------------------------------------------
# Level grid addresses
# ---------------------------------------------------------------------------

LEVEL_1_6_DATA_ADDRESS    = 0x18700 + NES_HEADER_SIZE
LEVEL_7_9_DATA_ADDRESS    = 0x18A00 + NES_HEADER_SIZE
LEVEL_1_6_DATA_ADDRESS_Q2 = 0x18D00 + NES_HEADER_SIZE
LEVEL_7_9_DATA_ADDRESS_Q2 = 0x19000 + NES_HEADER_SIZE

# 2Q dungeon "Various Data" patch tables (ROM addresses; add NES_HEADER_SIZE for file offset).
# Pointer table: 9 x 2-byte LE CPU addresses pointing into bank 6 (CPU base 0x8000).
# Length table:  9 bytes, one per dungeon.  Each block patches level_info starting at +0x29.
DUNGEON_VARIOUS_DATA_Q2_PTR_TABLE  = 0x183A4 + NES_HEADER_SIZE  # 9 x 2 bytes
DUNGEON_VARIOUS_DATA_Q2_LEN_TABLE  = 0x183B6 + NES_HEADER_SIZE  # 9 bytes
DUNGEON_VARIOUS_DATA_Q2_BANK6_CPU  = 0x8000                     # CPU base of bank 6
DUNGEON_VARIOUS_DATA_Q2_BANK6_FILE = 0x18000 + NES_HEADER_SIZE  # file base of bank 6
# Byte offset within the 0xFC-byte level_info block where the patch data begins.
DUNGEON_VARIOUS_DATA_Q2_INFO_OFFSET = 0x29  # item_position_table[0]

# ---------------------------------------------------------------------------
# Overworld / level info addresses
# ---------------------------------------------------------------------------

OVERWORLD_DATA_ADDRESS = 0x18400 + NES_HEADER_SIZE
LEVEL_INFO_ADDRESS     = 0x19300 + NES_HEADER_SIZE

# ---------------------------------------------------------------------------
# Cave data addresses
# ---------------------------------------------------------------------------

CAVE_ITEM_DATA_ADDRESS  = 0x18600 + NES_HEADER_SIZE
CAVE_PRICE_DATA_ADDRESS = 0x1863C + NES_HEADER_SIZE

# ---------------------------------------------------------------------------
# Special item addresses
# ---------------------------------------------------------------------------

ARMOS_ITEM_ADDRESS    = 0x10CF5 + NES_HEADER_SIZE
COAST_ITEM_ADDRESS    = 0x1788A + NES_HEADER_SIZE

# Armos statue lookup tables (bank 4): 7 screen IDs then 7 sprite X-positions.
# ROM address 0x10CB2 (CPU), file offset = 0x10CB2 + NES_HEADER_SIZE.
ARMOS_TABLES_ADDRESS  = 0x10CB2 + NES_HEADER_SIZE

# ---------------------------------------------------------------------------
# Sword heart-requirement addresses
# ---------------------------------------------------------------------------

WHITE_SWORD_REQUIREMENT_ADDRESS   = 0x490D
MAGICAL_SWORD_REQUIREMENT_ADDRESS = 0x4916

# ---------------------------------------------------------------------------
# Door repair charge address
# ---------------------------------------------------------------------------

DOOR_REPAIR_CHARGE_ADDRESS = 0x4890 + NES_HEADER_SIZE

# ---------------------------------------------------------------------------
# Navigation addresses
# ---------------------------------------------------------------------------

RECORDER_WARP_DESTINATIONS_ADDRESS  = 0x6010 + NES_HEADER_SIZE
RECORDER_WARP_Y_COORDINATES_ADDRESS = 0x6119 + NES_HEADER_SIZE
ANY_ROAD_SCREENS_ADDRESS            = 0x19334 + NES_HEADER_SIZE
START_SCREEN_ADDRESS                = 0x1932F + NES_HEADER_SIZE
START_POSITION_Y_ADDRESS            = 0x19328 + NES_HEADER_SIZE

# ---------------------------------------------------------------------------
# Sprite set pointer table addresses
# ---------------------------------------------------------------------------

LEVEL_SPRITE_SET_POINTERS_ADDRESS = 0x3 * 0x4000 + NES_HEADER_SIZE   # start of bank 3
BOSS_SPRITE_SET_POINTERS_ADDRESS  = LEVEL_SPRITE_SET_POINTERS_ADDRESS + 20  # immediately after

# ---------------------------------------------------------------------------
# Mixed enemy group addresses (bank 5)
# ---------------------------------------------------------------------------

MIXED_ENEMY_POINTER_TABLE_ADDRESS = 0x1473F + NES_HEADER_SIZE
MIXED_ENEMY_DATA_SIZE             = 201
MIXED_ENEMY_DATA_ADDRESS          = MIXED_ENEMY_POINTER_TABLE_ADDRESS - MIXED_ENEMY_DATA_SIZE
FIRST_MIXED_GROUP_CODE            = 0x62
POINTER_COUNT                     = 0x1E
BANK_5_ROM_START                  = 0x14000 + NES_HEADER_SIZE
BANK_5_CPU_START                  = 0x8000

# ---------------------------------------------------------------------------
# Cave quote / hint shop addresses
# ---------------------------------------------------------------------------

# Cave quote ID table (20 bytes): low 6 bits of each byte = quote_id per cave slot
CAVE_QUOTES_DATA_ADDRESS = 0x45B2

# Hint shop slot quote ID table (6 bytes): low 6 bits = quote_id per slot
# Slots 0-2 = Hint Shop 1, slots 3-5 = Hint Shop 2
HINT_SHOP_QUOTES_ADDRESS = 0x494B

# Overworld person text selectors (Z_01.asm, bank 1 $85A2): 20 bytes.
# Entry 2 is the white-sword cave's selector (HT-SEL-02).
OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS = 0x45B2

# Underworld person text selector tables (Z_01.asm, bank 1 $8A1B / $8A61).
# Each table's first 8 entries correspond to person codes $0B-$12.
UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS = 0x4A2B
UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS = 0x4A71
UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE = 8

# Object animation pointer table (Z_01.asm, bank 1 $6E14): one byte per object
# type. Entries 109-117 are used by the hint person-name entries.
OBJ_ANIMATIONS_ADDRESS = 0x6E14
OBJ_ANIMATIONS_SIZE = 0x7F

# ---------------------------------------------------------------------------
# Quote / hint addresses
# ---------------------------------------------------------------------------

QUOTE_DATA_ADDRESS = 0x4010  # file offset: pointer table (38 x 2 bytes) + quote text

# Vanilla hint text block: starts at 0x404C (immediately after the 76-byte pointer
# table at QUOTE_DATA_ADDRESS), next ROM region at 0x45A2.
VANILLA_HINT_TEXT_MAX_BYTES = 0x45A2 - 0x404C   # 1366 bytes

# Extended hint bank — a blank region further in the ROM that provides a much
# larger budget. By pointing all 38 hint pointers here we abandon the vanilla
# text block (which becomes dead bytes) and gain ~1853 bytes of headroom.
EXT_HINT_DATA_ROM_START = 0x7780   # ROM offset where extended text begins
# PI-HINT-01: the area ends at $BE40 (was 0x7EBD, $BEAD), whatever the flags, so the layout is
# fixed: fp-prog-01's bank-1 segment starts there. 1,744 bytes.
EXT_HINT_DATA_ROM_END   = 0x7E50   # exclusive upper bound
EXT_HINT_CPU_BASE       = 0x8000   # bank 1 maps to $8000 in CPU address space
EXT_BANK1_ROM_START     = 0x4010   # bank 1 byte 0 in ROM file (= QUOTE_DATA_ADDRESS)

# The overflow region (HT-TEXT-03: the rebuild allocates the space; PI-HINT-02:
# every extended mode): the old PersonText block after the pointer table, up
# to the FP-TRIF-01 refusal text. Texts that do not fit in the extended bank
# continue here, in slot order. ZORA's serializer then fills the bank's unused
# tail with HINT_TEXT_SPILL_FILL, a byte that ends no text, so a reader of its
# bodies knows where the bank's texts stop.
CONSTERNATION_HINT_SLOTS = 45
EXTENDED_HINT_POINTERS = 38        # COMMUNITY and HELPFUL keep PRG0's table
HINT_TEXT_SPILL_FILL = 0x00


def hint_text_regions(pointer_count: int) -> tuple[tuple[int, int], ...]:
    """PI-HINT-02: where a mode's texts go, in order: the extended bank, then
    the old text area after its pointer table, up to the refusal text."""
    return ((EXT_HINT_DATA_ROM_START, EXT_HINT_DATA_ROM_END),
            (QUOTE_DATA_ADDRESS + 2 * pointer_count, REFUSAL_TEXT_ADDRESS))


def place_hint_texts(lengths: list[int], pointer_count: int) -> list[int]:
    """File offsets of a mode's slot texts, in slot order: the extended bank
    first, then the overflow region (HT-TEXT-03, PI-HINT-02). Text goes to the
    overflow region only when it does not fit, so texts that fit the bank keep
    their places. Raises when they do not fit: a text is never truncated."""
    regions = iter(hint_text_regions(pointer_count))
    start, end = next(regions)
    offsets = []
    for length in lengths:
        while start + length > end:
            following = next(regions, None)
            if following is None:
                raise ValueError(f"HT-TEXT-03: the {len(lengths)} hint texts need {sum(lengths)} bytes, "
                                 f"more than the regions {hint_text_regions(pointer_count)} hold")
            start, end = following
        offsets.append(start)
        start += length
    return offsets


def cpu_address_in_bank1(file_offset: int) -> int:
    return EXT_HINT_CPU_BASE + (file_offset - EXT_BANK1_ROM_START)

# ---------------------------------------------------------------------------
# ASM patch: dungeon nothing-code
# ---------------------------------------------------------------------------

# Operand of `CMP #$03` in aldonunez CreateRoomObjects (bank 5, CPU $B84F):
# the room-item code that deactivates the room item at load ("no item").
# The ZORA remap rewrites it from $03 to $0E (ASM_NOTHING_CODE_PATCH_VALUE).
ASM_NOTHING_CODE_PATCH_OFFSET = 0x1785F
# The byte the engine compares room items against for "no item" once the
# serialization setting selects the ZORA remap (see
# game_config.DungeonNothingCode.ZORA_REMAP). The remap frees $03 so the
# magical sword can appear as a dungeon room item.
ASM_NOTHING_CODE_PATCH_VALUE  = 0x0E

# ---------------------------------------------------------------------------
# MMG prize patch offsets and vanilla values (bank 1)
# ---------------------------------------------------------------------------

MMG_LOSE_SMALL_OFFSET   = 0x045C6   # MoneyGameLossAmounts[0]
MMG_LOSE_LARGE_OFFSET   = 0x045C7   # MoneyGameLossAmounts[1]
MMG_LOSE_SMALL_2_OFFSET = 0x04688   # LDA # operand (fixed lose amount loaded into RAM)
MMG_WIN_SMALL_OFFSET_A  = 0x0468D   # LDY # operand (win variant A)
MMG_WIN_SMALL_OFFSET_B  = 0x049DF   # CMP # in rupee add/subtract handler
MMG_WIN_SMALL_OFFSET_C  = 0x049F9   # CMP # in PrependSignToPrice
MMG_WIN_LARGE_OFFSET_A  = 0x04695   # LDY # operand (win variant B)
MMG_WIN_LARGE_OFFSET_B  = 0x049E3   # CMP # in rupee add/subtract handler
MMG_WIN_LARGE_OFFSET_C  = 0x049FD   # CMP # in PrependSignToPrice

MMG_VANILLA_LOSE_SMALL   = 10
MMG_VANILLA_LOSE_SMALL_2 = 10
MMG_VANILLA_LOSE_LARGE   = 40
MMG_VANILLA_WIN_SMALL    = 20
MMG_VANILLA_WIN_LARGE    = 50

# ---------------------------------------------------------------------------
# Bomb upgrade patch offsets and vanilla values (bank 1 + bank 6)
# ---------------------------------------------------------------------------

BOMB_COST_OFFSET  = 0x04B82   # PRG $4B72: LDA immediate — rupee cost
BOMB_COUNT_OFFSET = 0x04B9B   # PRG $4B8B: ADC immediate — bombs added to MaxBombs
BOMB_DISP_BASE    = 0x1A2B2   # ROM 0x1A2B2-0x1A2B4: price display tiles (hundreds, tens, ones)

BOMB_VANILLA_COST  = 100
BOMB_VANILLA_COUNT = 4

# ---------------------------------------------------------------------------
# Life-or-money toll and bomb-upgrade person (post-shapes-b1.md PS-MERCH-04,
# PS-BOMB-03; headered file offsets, aldonunez labels where one exists)
# ---------------------------------------------------------------------------

PERSON_INIT_JUMP_TABLE_ADDRESS = 0x04A17  # InitUnderworldPerson_Full_JumpTable: 10 .ADDR entries, entry L = level L
PERSON_INIT_JUMP_TABLE_SIZE    = 20
PERSON_UPDATE_BRANCH_ADDRESS = 0x04AED   # UpdateUnderworldPerson_Full: BCC ($90 $08) .. CMP #7 operand at 0x04AF4
PERSON_UPDATE_BRANCH_SIZE    = 8         # 0x04AED-0x04AF4
LIFE_OR_MONEY_ITEM_TYPES_ADDRESS = 0x04BD9   # LifeOrMoneyItemTypes, 2 bytes
LIFE_OR_MONEY_PAYMENT_ADDRESS    = 0x04C1C   # money check + heart-container payment
LIFE_OR_MONEY_PAYMENT_SIZE       = 0x21      # 0x04C1C-0x04C3C
TOLL_TEXT_ADDRESS   = 0x04CC0   # CPU $8CB0 bank 1, free space: the toll text
TOLL_TEXT_SIZE      = 40        # longest toll text: 22 + 18 bytes
TOLL_TEXT_POINTER_ADDRESS = 0x04046   # PersonTextAddrs slot 27 (inside the quotes block)
TOLL_TEXT_POINTER = bytes([0xB0, 0x8C])
# FP-TRIF-01: the level-9 refusal text (person-text slot 34) lies outside the
# generated hint block, in the old person-text area of bank 1, as in 1,000 of
# 1,000 corpus finals (CPU $8536; the corpus's text takes 72 bytes, ending
# before the cave quote IDs at 0x045B2).
REFUSAL_TEXT_ADDRESS = 0x04546      # CPU $8536 bank 1
REFUSAL_TEXT_SIZE = 72
REFUSAL_TEXT_POINTER_ADDRESS = 0x04054   # PersonTextAddrs slot 34
REFUSAL_TEXT_POINTER = bytes([0x36, 0x85])
LIFE_OR_MONEY_COST_TEXT_ADDRESS = 0x1A2B6   # LifeOrMoneyCostTextTransferBuf
LIFE_OR_MONEY_COST_TEXT_SIZE    = 13
# PS-MERCH-04's starting-hearts byte H (post-shapes-b1.md): CPU $A858 in
# bank 2. PRG0 has $FF there (free space), which the rule caps to 34.
START_HEARTS_ADDRESS = 0x0A868
# FP-START-01: the two routines that set a save file's starting state.
# PRG0 stores immediates; a ROM may instead jump to a routine that copies a
# 40-byte table into Items (LDY #$27 / LDA table,Y), as the corpus finals do.
NEW_FILE_START_STATE_ADDRESS = 0x09F4E      # UpdateModeERegister, CPU $9F3E: LDY #$18 / LDA #$22 ...
SECOND_QUEST_START_STATE_ADDRESS = 0x0AF8B  # SwitchProfileToSecondQuest, CPU $AF7B: LDA #$22 / STA HeartValues ...
# FL-ALT-02: the HeartValues immediates of those two routines in PRG0's form (LDA #$22).
NEW_FILE_HEART_VALUES_OPERAND_ADDRESS = NEW_FILE_START_STATE_ADDRESS + 3
SECOND_QUEST_HEART_VALUES_OPERAND_ADDRESS = SECOND_QUEST_START_STATE_ADDRESS + 1
BANK_2_FILE_START = 0x08010
CONTINUE_HEARTS_OPERAND_ADDRESS = 0x14B83  # Continue hearts restore operand

BOMB_DISPLAY_SPACE_TILE = 0x24   # leading-zero suppression tile (blank)

# ---------------------------------------------------------------------------
# Enemy / Boss HP table addresses (file offsets, iNES header included)
#
# One engine table, aldonunez `ObjectTypeToHpPairs` (bank 7, 38 bytes at
# 0x1FB5E): byte k holds object type 2k in the HIGH nibble and 2k+1 in the
# LOW nibble (ExtractHitPointValue), covering types $00-$4B. zora splits it
# into two non-overlapping slices:
#   Enemy HP: bytes 0-25  (0x1FB5E, 26 bytes, 52 nibbles) → Enemy 0x00-0x33
#   Boss HP:  bytes 26-37 (0x1FB78, 12 bytes, 24 nibbles) → Enemy 0x34-0x4B
# (Before 2026-09-27 the boss slice started at byte 25 — 0x1FB77, Enemy
# 0x32 — overlapping the enemy slice by one byte and leaving byte 37 unread.)
#
# Secondary HP bytes: `LDA #imm` operands (value in the high nibble) that the
# engine stores to ObjHP directly, outside the table:
#   GLEEOK_NECK_HP     0x120C6  InitGleeok              LDA #$A0 → ObjHP+1,X
#   GLEEOK_HEAD_HP     0x12735  Gleeok_CheckCollisions  LDA #$60 (flying head)
#   GANON_HP           0x12F27  Ganon_CheckCollisions   LDA #$F0
#   MOLDORM_SEGMENT_HP 0x114D5  UpdateMoldorm           LDA #$20
#   LAMNOLA_SEGMENT_HP 0x12A45  UpdateLamnola           LDA #$20
# (The first two and last two were formerly misnamed AQUAMENTUS_HP/_SP and
# GLEEOK_HP/PATRA_HP — they never belonged to Aquamentus or Patra.)
# ---------------------------------------------------------------------------

ENEMY_HP_TABLE_ADDRESS = 0x1FB5E      # ObjectTypeToHpPairs bytes 0-25 (Enemy 0x00-0x33)
ENEMY_HP_TABLE_SIZE    = 26
ENEMY_HP_NIBBLE_COUNT  = 52

BOSS_HP_TABLE_ADDRESS  = 0x1FB78      # ObjectTypeToHpPairs bytes 26-37 (Enemy 0x34-0x4B)
BOSS_HP_TABLE_SIZE     = 12
BOSS_HP_NIBBLE_COUNT   = 24

BOSS_HP_FIRST_ENEMY_VALUE = 0x34      # Enemy.RED_GOHMA — first entry in the boss slice

# Secondary boss HP byte offsets (file offsets; see the table above)
GLEEOK_NECK_HP_ADDRESS     = 0x120C6
GLEEOK_HEAD_HP_ADDRESS     = 0x12735
GANON_HP_ADDRESS           = 0x12F27
MOLDORM_SEGMENT_HP_ADDRESS = 0x114D5
LAMNOLA_SEGMENT_HP_ADDRESS = 0x12A45

# Boss engine sprite pointer offsets (hardcoded ROM locations that tell the
# engine where specific boss sprite tiles live in VRAM).
AQUAMENTUS_SPRITE_PTR_ADDRESS        = 0x11898
AQUAMENTUS_TILE_LAYOUT_TABLE_ADDRESS = 0x11844  # 12-byte tile column table for Aquamentus/Ganon draw routine
AQUAMENTUS_TILE_LAYOUT_TABLE_SIZE    = 12
GLEEOK_BODY_TILES_ADDRESS = 0x12819   # GleeokBodyTiles0-2, 18 bytes (bank 4)
GLEEOK_BODY_TILES_SIZE    = 18
ITEM_CARRIER_OPERAND_ADDRESSES = (0x1E70F, 0x1E713, 0x1E717)   # PS-EGRP-05: MoveAndDrawRoomItem CMP operands
# PS-HP-01: InitRope's two LDA #imm hit-point operands (quest 1, quest 2)
ROPE_HP_OPERAND_ADDRESSES = (0x112D3, 0x112DF)
# PS-EGRP-05 (post-shapes-b4.md S7): the four byte runs that make overworld
# red Wizzrobes work, written when the red Wizzrobe joins the overworld group.
OVERWORLD_WIZZROBE_PATCH: tuple[tuple[int, Piece], ...] = (
    (0x11E3B, bytes([0xC9, 0x9A, 0x90, 0x0E, 0xC9, 0xCC, 0x90, 0x06, 0x29, 0xFC, 0xC9, 0xE0,
                     0xD0, 0x04, 0x4C, 0xF5, 0xAF, 0x00])),
    (0x13005, bytes([0xBD, 0x94, 0x03, 0xF0, 0x03, 0x4C, 0x17, 0x9E, 0x4C, 0xEB, 0x9E])),
    # The run at 0x13F10 holds copies of PRG0's code: its three JSRs at 0x11E2D and the
    # object test at 0x11BE4. They are read from the player's ROM when written
    # (base_rom.Original), not stored here.
    (0x13F10, Original(0x11E2D, 9)),
    (0x13F19, bytes([0xB0, 0x03, 0x4C, 0x57, 0x9E])),
    (0x13F1E, Original(0x11BE4, 8)),
    (0x13F26, bytes([0x07, 0xC9,
                     0xF4, 0xB0, 0x03, 0x4C, 0x3D, 0x9E, 0xBD, 0x94, 0x03, 0xF0, 0x03, 0x4C,
                     0x17, 0x9E, 0x4C, 0xEB, 0x9E])),
    (0x12D2E, bytes([0x20, 0x00, 0xBF])),
)
OBJECT_TYPE_OPERAND_873D_ADDRESS = 0x0474D                    # PS-EGRP-06, CPY # operand
GLEEOK_HEAD_SPRITE_PTR_A_ADDRESS = 0x126F8
GLEEOK_HEAD_SPRITE_PTR_B_ADDRESS = 0x126FE
GLEEOK_HEAD_SPRITE_PTR_C_ADDRESS = 0x6F5A

# ---------------------------------------------------------------------------
# Enemy tile mapping addresses (bank 1, file offsets = raw ROM addr + 0x10)
# ---------------------------------------------------------------------------

TILE_MAPPING_POINTERS_ADDRESS = 0x6E14   # 0x7F bytes: tile codes for enemies + cave chars
TILE_MAPPING_DATA_ADDRESS     = 0x6E93   # 0xCC bytes: tile codes for enemy animation frames

TILE_MAPPING_POINTERS_SIZE = 0x7F
TILE_MAPPING_DATA_SIZE     = 0xCC

# ---------------------------------------------------------------------------
# Sprite data block addresses (file offsets)
#
# All values include the 0x10 iNES header.
# ---------------------------------------------------------------------------

OW_SPRITES_ADDRESS             = 0xD24B   # 0x640 bytes: overworld sprite bank (addl + enemy, contiguous)
ENEMY_SET_B_SPRITES_ADDRESS    = 0xD88B   # 0x220 bytes: enemy sprite set B
ENEMY_SET_C_SPRITES_ADDRESS    = 0xDAAB   # 0x220 bytes: enemy sprite set C
DUNGEON_COMMON_SPRITES_ADDRESS = 0xDCCB   # 0x100 bytes: dungeon common sprites
ENEMY_SET_A_SPRITES_ADDRESS    = 0xDDCB   # 0x220 bytes: enemy sprite set A
BOSS_SET_A_SPRITES_ADDRESS     = 0xDFEB   # 0x400 bytes: boss sprite set A
BOSS_SET_B_SPRITES_ADDRESS     = 0xE3EB   # 0x400 bytes: boss sprite set B
BOSS_SET_C_SPRITES_ADDRESS     = 0xE7EB   # 0x400 bytes: boss sprite set C
BOSS_SET_EXPANSION_SPRITES_ADDRESS = 0x8A8F  # 0x200 bytes: previously unused region repurposed for boss sprites

OW_SPRITES_SIZE             = 0x640
ENEMY_SET_B_SPRITES_SIZE    = 0x220
ENEMY_SET_C_SPRITES_SIZE    = 0x220
DUNGEON_COMMON_SPRITES_SIZE = 0x100
ENEMY_SET_A_SPRITES_SIZE    = 0x220
BOSS_SET_A_SPRITES_SIZE     = 0x400
BOSS_SET_B_SPRITES_SIZE     = 0x400
BOSS_SET_C_SPRITES_SIZE     = 0x400
BOSS_SET_EXPANSION_SPRITES_SIZE = 0x200

# ---------------------------------------------------------------------------
# Player (Link) sprite data block addresses (file offsets)
#
# CHR tile regions for alternate player sprite poses (Link/Zelda swap, old
# man swap, etc.). Some later write destinations fall inside boss_set_c and
# are handled through that bank — they are NOT duplicated here.
# ---------------------------------------------------------------------------

PLAYER_MAIN_SPRITES_ADDRESS              = 0x808F   # 0x1C0 bytes: main Link sprite sheet
PLAYER_CHEER_SPRITES_ADDRESS             = 0x4E44   # 0x20 bytes: Link/Zelda cheer pose
PLAYER_BIG_SHIELD_PROFILE_SPRITES_ADDRESS = 0x4EC4  # 0x20 bytes: big shield profile
PLAYER_PROFILE_NO_SHIELD_SPRITES_ADDRESS = 0x85CF   # 0x20 bytes: profile, no shield
PLAYER_SMALL_SHIELD_SPRITES_ADDRESS      = 0x860F   # 0x40 bytes: small shield frames
PLAYER_LARGE_SHIELD_SPRITES_ADDRESS      = 0x868F   # 0x20 bytes: large shield

PLAYER_MAIN_SPRITES_SIZE              = 0x1C0
PLAYER_CHEER_SPRITES_SIZE             = 0x20
PLAYER_BIG_SHIELD_PROFILE_SPRITES_SIZE = 0x20
PLAYER_PROFILE_NO_SHIELD_SPRITES_SIZE = 0x20
PLAYER_SMALL_SHIELD_SPRITES_SIZE      = 0x40
PLAYER_LARGE_SHIELD_SPRITES_SIZE      = 0x20

# ---------------------------------------------------------------------------
# Maze direction sequence addresses (bank 1)
#
# These 8 bytes encode the Dead Woods and Lost Hills direction sequences.
# All offsets already include the 0x10 iNES header.
# Dead Woods: 4 bytes at 0x6DA7-0x6DAA  (North=0x08, South=0x04, West=0x02)
# Lost Hills: 4 bytes at 0x6DAB-0x6DAE  (Up=0x08, Down=0x04, Right=0x01)
# ---------------------------------------------------------------------------

MAZE_DIRECTIONS_ADDRESS = 0x6DA7   # file offset; Dead Woods first, Lost Hills second

# ---------------------------------------------------------------------------
# Grid / table layout constants
# ---------------------------------------------------------------------------

LEVEL_TABLE_SIZE = 0x80
NUM_TABLES       = 6
LEVEL_INFO_SIZE  = 0xFC
NUM_QUOTES       = 38

# ---------------------------------------------------------------------------
# Cave data sentinels
# ---------------------------------------------------------------------------

CAVE_NOTHING_CODE   = 0x3F   # item code meaning "nothing" in cave item data
# The vanilla dungeon room item sentinel for "nothing" (used by the
# Consternation preset). The GAME-LEVEL meaning lives in the model as
# Item.NOTHING; which byte encodes it is a serialization setting —
# game_config.DungeonNothingCode ($03 vanilla / $0E ZORA remap).
DUNGEON_NOTHING_CODE = 0x03

# ---------------------------------------------------------------------------
# Randomizer ROM identification
# ---------------------------------------------------------------------------

# File offset of the title-screen version line (the randomizer writes its build string here).
TITLE_VERSION_OFFSET = 0x1AB19

# ---------------------------------------------------------------------------
# Level name string
# ---------------------------------------------------------------------------

# 6-byte string shown on the dungeon HUD as "LEVEL-1", "STAGE-3", etc.
# The dash tile in HUD context is 0x62, not the quote-encoding 0x2F.
LEVEL_NAME_OFFSET = 0x19D17
LEVEL_NAME_LENGTH = 6
LEVEL_NAME_DASH_TILE = 0x62
LEVEL_NAME_DASH_OFFSET = 0x19D1C  # sixth tile of the HUD level-name string
FP_LEVEL_DASH_TILE = 0x2F          # FP-LEVEL-01 replacement dash tile

# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tunic & heart color offsets
# ---------------------------------------------------------------------------

START_TUNIC_COLOR_OFFSET = 0xA297       # Vanilla: 0x29 (green)
BLUE_RING_TUNIC_COLOR_OFFSET = 0x6BA6   # Vanilla: 0x32 (blue)
RED_RING_TUNIC_COLOR_OFFSET = 0x6BA7    # Vanilla: 0x16 (red)

# 10 dungeon HUD heart color positions (252 bytes apart)
HEART_COLOR_OFFSETS: list[int] = [
    0x19318, 0x19414, 0x19510, 0x1960C, 0x19708,
    0x19804, 0x19900, 0x199FC, 0x19AF8, 0x19BF4,
]

# ---------------------------------------------------------------------------
# Randomizer magic
# ---------------------------------------------------------------------------

# Encoded bytes for "RANDOMIZER" using the NES tile encoding (letter = ASCII - 55).
# Used to detect whether an uploaded ROM was produced by this randomizer.
RANDOMIZER_MAGIC = bytes([0x1B, 0x0A, 0x17, 0x0D, 0x18, 0x16, 0x12, 0x23, 0x0E, 0x1B])

# ---------------------------------------------------------------------------
# B10 DATA-item sites (docs/spec/features-behavior.md)
# ---------------------------------------------------------------------------

# FP-LOCK-02: credits text pointer table for lines 12-15.
# The full table is 23 lo bytes at 0xAC3E followed by 23 hi bytes at 0xAC55;
# lines 12-15 are entries 12-15.
CREDITS_POINTERS_LO_ADDRESS = 0xAC3E
CREDITS_POINTERS_HI_ADDRESS = 0xAC55
CREDITS_LINE_12_INDEX = 12
CREDITS_LINE_13_INDEX = 13
CREDITS_LINE_14_INDEX = 14
CREDITS_LINE_15_INDEX = 15
CREDITS_BLANK_TILE = 0x24
CREDITS_COPYRIGHT_SYMBOL_TILE = 0xFC
# The three replacement records (lines 12, 13, 14: 32, 8 and 25 bytes) in
# bank-2 free space, after FP-HOT-01's slot (docs/rom-map.md, slot $B080-$B0DF).
CREDITS_RECORD_CPU_ADDRESSES = (0xB080, 0xB0A0, 0xB0A8)
CREDITS_FREE_SPACE_ADDRESS = 0xB090  # file offset of CPU $B080 in bank 2
CREDITS_COPYRIGHT_POINTER = 0xAC72   # line 15 keeps PRG0's copyright record

# FP-RESET-01
RESET_BUTTON_OPERAND_ADDRESS = 0x140EB
RESET_BUTTON_OPERAND_VALUE = 0xFA

# FP-TEXT-01
TEXT_SPEED_OPERAND_ADDRESS = 0x482D
TEXT_SPEED_OPERAND_VALUE = 0x02

# FP-BEEP-01
LOW_HEALTH_BEEP_OPERAND_ADDRESS = 0x1ED33
LOW_HEALTH_BEEP_OPERAND_VALUE = 0x00

# FP-FIX-01
DMC_LEVEL_OPERAND_ADDRESS = 0x1BC4
DMC_LEVEL_OPERAND_VALUE = 0x40

# FP-Q2R-01
Q2_ROOM_3E_TRIGGER_ADDRESS = 0x18FCE
Q2_ROOM_3E_TRIGGER_VALUE = 0x01

# FP-TITLE-01
TITLE_SEED_ROW_ADDRESS = 0x1AAD3
TITLE_VERSION_ROW_ADDRESS = TITLE_VERSION_OFFSET
TITLE_ROW_LENGTH = 24

# FP-PERSON-01
def _animation_address(slot: int) -> int:
    """File offset of an ObjAnimations slot (object type 0x00-0x7E)."""
    return OBJ_ANIMATIONS_ADDRESS + slot

CAVE_PERSON_ANIMATION_SLOTS = list(range(0x6B, 0x7C))  # 17 object types $6B-$7B
CAVE_PERSON_ANIMATION_BASE = 0x58
CAVE_PERSON_ANIMATION_MODULO = 4

# ---------------------------------------------------------------------------
# Little-endian 16-bit helpers
# ---------------------------------------------------------------------------

def read_le16(data: bytes, index: int) -> int:
    """Read a little-endian 2-byte value from a pointer table at the given index."""
    return data[index * 2] | (data[index * 2 + 1] << 8)


def write_le16(buf: bytearray, index: int, value: int) -> None:
    """Write a little-endian 2-byte value into a pointer table at the given index."""
    buf[index * 2]     = value & 0xFF
    buf[index * 2 + 1] = (value >> 8) & 0xFF

