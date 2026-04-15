"""ROM layout constants for Zelda 1 (NES).

All file offsets include the 0x10-byte iNES header unless noted otherwise
(file offset = ROM address + NES_HEADER_SIZE).

This module has no zora imports and is safe to import from parser, serializer,
and tests without creating circular dependencies.
"""

# ---------------------------------------------------------------------------
# iNES header
# ---------------------------------------------------------------------------

NES_HEADER_SIZE = 0x10

# ---------------------------------------------------------------------------
# Level grid addresses
# ---------------------------------------------------------------------------

LEVEL_1_6_DATA_ADDRESS    = 0x18700 + NES_HEADER_SIZE
LEVEL_7_9_DATA_ADDRESS    = 0x18A00 + NES_HEADER_SIZE
LEVEL_1_6_DATA_ADDRESS_Q2 = 0x18D00 + NES_HEADER_SIZE
LEVEL_7_9_DATA_ADDRESS_Q2 = 0x19000 + NES_HEADER_SIZE

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

WHITE_SWORD_REQUIREMENT_ADDRESS   = 0x48FD + NES_HEADER_SIZE
MAGICAL_SWORD_REQUIREMENT_ADDRESS = 0x4906 + NES_HEADER_SIZE

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
EXT_HINT_DATA_ROM_END   = 0x7EBD   # exclusive upper bound (~1853 bytes available)
EXT_HINT_CPU_BASE       = 0x8000   # bank 1 maps to $8000 in CPU address space
EXT_BANK1_ROM_START     = 0x4010   # bank 1 byte 0 in ROM file (= QUOTE_DATA_ADDRESS)

# ---------------------------------------------------------------------------
# ASM patch: dungeon nothing-code
# ---------------------------------------------------------------------------

# Changes the game engine's item rendering sentinel from 0x03 to 0x18.
ASM_NOTHING_CODE_PATCH_OFFSET = 0x1785F
ASM_NOTHING_CODE_PATCH_VALUE  = 0x18

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

BOMB_DISPLAY_SPACE_TILE = 0x24   # leading-zero suppression tile (blank)

# ---------------------------------------------------------------------------
# Enemy tile mapping addresses (bank 1, file offsets = raw ROM addr + 0x10)
# ---------------------------------------------------------------------------

TILE_MAPPING_ENEMIES_ADDRESS      = 0x6E14   # 0x7F bytes: tile codes for enemies + cave chars
TILE_MAPPING_ENEMY_FRAMES_ADDRESS = 0x6E93   # 0xCC bytes: tile codes for enemy animation frames

TILE_MAPPING_ENEMIES_SIZE      = 0x7F
TILE_MAPPING_ENEMY_FRAMES_SIZE = 0xCC

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
# These are the CHR tile regions written by RemapLinkSprite's swap functions
# (SwapLinkAndZelda, SwapLinkAndOldMan, etc.).  The last two write
# destinations (0xEAEB, 0xEB4B) fall inside boss_set_c and are handled
# through that bank — they are NOT duplicated here.
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
DUNGEON_NOTHING_CODE = 0x03  # vanilla dungeon room item sentinel for "nothing"

# ---------------------------------------------------------------------------
# Randomizer ROM identification
# ---------------------------------------------------------------------------

# File offset of the title-screen version line written by WriteTitleScreenInfo.
TITLE_VERSION_OFFSET = 0x1AB19

# ---------------------------------------------------------------------------
# Level name string
# ---------------------------------------------------------------------------

# 6-byte string shown on the dungeon HUD as "LEVEL-1", "STAGE-3", etc.
# The dash tile in HUD context is 0x62, not the quote-encoding 0x2F.
LEVEL_NAME_OFFSET = 0x19D17
LEVEL_NAME_LENGTH = 6
LEVEL_NAME_DASH_TILE = 0x62

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
# Little-endian 16-bit helpers
# ---------------------------------------------------------------------------

def read_le16(data: bytes, index: int) -> int:
    """Read a little-endian 2-byte value from a pointer table at the given index."""
    return data[index * 2] | (data[index * 2 + 1] << 8)


def write_le16(buf: bytearray, index: int, value: int) -> None:
    """Write a little-endian 2-byte value into a pointer table at the given index."""
    buf[index * 2]     = value & 0xFF
    buf[index * 2 + 1] = (value >> 8) & 0xFF
