"""
ROM binary parser: RawBinFiles → GameWorld

Parses extracted ROM bin files into a fully structured GameWorld. All file
offsets include the 0x10-byte iNES header (file offset = ROM address + 0x10).

Parsed regions
--------------
Level grid (LEVEL_1_6_DATA_ADDRESS, LEVEL_7_9_DATA_ADDRESS):
  6 tables x 0x80 bytes per grid. Levels 1-6 share one grid, 7-9 another.
  Each room slot has 6 bytes across the tables encoding walls, enemy, item, flags.
  Staircase room slots repurpose tables 0/1/2 for exit destinations.

Level info block (LEVEL_INFO_ADDRESS), 0xFC bytes per level, 10 slots (0=unused):
  +0x00  Palette raw (0x24 bytes)
  +0x24  Enemy quantity table (4 bytes)
  +0x28  Link's starting Y position (1 byte)
  +0x29  Item position table (4 bytes)
  +0x2D  Map start (1 byte)
  +0x2E  Map cursor offset (1 byte)
  +0x2F  Entrance room (1 byte)
  +0x30  Triforce/compass room (derived at serialization — read but discard)
  +0x31  Screen status RAM offset (2 bytes, preserve)
  +0x33  Level number (1 byte)
  +0x34  Stairway data (10 bytes, 0xFF terminated)
  +0x3E  Boss room (1 byte)

Overworld (OVERWORLD_DATA_ADDRESS): 6 tables x 0x80 bytes.

Cave data (CAVE_ITEM_DATA_ADDRESS, CAVE_PRICE_DATA_ADDRESS):
  20 caves x 3 bytes each for items and prices.
  Quote IDs from CAVE_QUOTES_DATA_ADDRESS (20 bytes, low 6 bits each).
  Hint shop slot quote IDs from HINT_SHOP_QUOTES_ADDRESS (6 bytes, low 6 bits each).

Sprite sets (LEVEL_SPRITE_SET_POINTERS_ADDRESS, BOSS_SPRITE_SET_POINTERS_ADDRESS):
  Start of bank 3 (file 0xC010). 10 x 2-byte LE CPU addresses each.
  Index 0 = overworld, 1-9 = levels.

Navigation (RECORDER_WARP_DESTINATIONS_ADDRESS, RECORDER_WARP_Y_COORDINATES_ADDRESS,
            ANY_ROAD_SCREENS_ADDRESS, START_SCREEN_ADDRESS):
  Recorder warp: 8 bytes each. Any-road: 4 bytes. Start screen: 1 byte.

Quotes (QUOTE_DATA_ADDRESS = file 0x4010):
  38 x 2-byte LE pointer table followed by variable-length encoded text.
  Pointer value = offset relative to start of quotes_data block.
  High byte has 0x80 set. Text bytes: low 6 bits = char code, high 2 bits = line break flags.

MMG win/lose values: 5 independent patchable ROM locations.
"""
from dataclasses import dataclass
from pathlib import Path

from zora.char_encoding import (
    BYTE_TO_CHAR as _BYTE_TO_CHAR,
)
from zora.char_encoding import (
    QUOTE_BLANK,
    QUOTE_CHAR_MASK,
    QUOTE_END_BITS,
    QUOTE_LINE1_BIT,
    QUOTE_LINE2_BIT,
)
from zora.data_model import (
    SCREEN_ENTRANCE_TYPES,
    VANILLA_BOSS_SPRITE_SETS,
    VANILLA_ENEMY_SPRITE_SETS,
    BombUpgrade,
    BossSpriteSet,
    CaveDefinition,
    Destination,
    Direction,
    DoorRepairCave,
    Enemy,
    EnemyData,
    EnemySpec,
    EnemySpriteSet,
    EntranceType,
    GameWorld,
    HintCave,
    HintShop,
    HintShopItem,
    Item,
    ItemCave,
    ItemPosition,
    Level,
    MoneyMakingGameCave,
    Overworld,
    OverworldDirection,
    OverworldItem,
    QuestVisibility,
    Quote,
    Room,
    RoomAction,
    RoomType,
    Screen,
    SecretCave,
    Shop,
    ShopItem,
    ShopType,
    SpriteData,
    StaircaseRoom,
    TakeAnyCave,
    WallSet,
    WallType,
)
from zora.rom_layout import (
    OW_SPRITES_ADDRESS,
    OW_SPRITES_SIZE,
    ANY_ROAD_SCREENS_ADDRESS,
    ARMOS_ITEM_ADDRESS,
    ARMOS_TABLES_ADDRESS,
    BOMB_COST_OFFSET,
    BOMB_COUNT_OFFSET,
    BOSS_SET_A_SPRITES_ADDRESS,
    BOSS_SET_A_SPRITES_SIZE,
    BOSS_SET_B_SPRITES_ADDRESS,
    BOSS_SET_B_SPRITES_SIZE,
    BOSS_SET_C_SPRITES_ADDRESS,
    BOSS_SET_C_SPRITES_SIZE,
    BOSS_SET_EXPANSION_SPRITES_ADDRESS,
    BOSS_SET_EXPANSION_SPRITES_SIZE,
    BOSS_SPRITE_SET_POINTERS_ADDRESS,
    CAVE_ITEM_DATA_ADDRESS,
    CAVE_NOTHING_CODE,
    CAVE_PRICE_DATA_ADDRESS,
    CAVE_QUOTES_DATA_ADDRESS,
    COAST_ITEM_ADDRESS,
    DOOR_REPAIR_CHARGE_ADDRESS,
    DUNGEON_COMMON_SPRITES_ADDRESS,
    DUNGEON_COMMON_SPRITES_SIZE,
    DUNGEON_NOTHING_CODE,
    ENEMY_SET_A_SPRITES_ADDRESS,
    ENEMY_SET_A_SPRITES_SIZE,
    ENEMY_SET_B_SPRITES_ADDRESS,
    ENEMY_SET_B_SPRITES_SIZE,
    ENEMY_SET_C_SPRITES_ADDRESS,
    ENEMY_SET_C_SPRITES_SIZE,
    FIRST_MIXED_GROUP_CODE,
    HINT_SHOP_QUOTES_ADDRESS,
    AQUAMENTUS_HP_ADDRESS,
    AQUAMENTUS_SP_ADDRESS,
    BOSS_HP_FIRST_ENEMY_VALUE,
    BOSS_HP_NIBBLE_COUNT,
    BOSS_HP_TABLE_ADDRESS,
    BOSS_HP_TABLE_SIZE,
    ENEMY_HP_NIBBLE_COUNT,
    ENEMY_HP_TABLE_ADDRESS,
    ENEMY_HP_TABLE_SIZE,
    GANON_HP_ADDRESS,
    GLEEOK_HP_ADDRESS,
    PATRA_HP_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_INFO_ADDRESS,
    LEVEL_INFO_SIZE,
    LEVEL_SPRITE_SET_POINTERS_ADDRESS,
    LEVEL_TABLE_SIZE,
    MAGICAL_SWORD_REQUIREMENT_ADDRESS,
    MAZE_DIRECTIONS_ADDRESS,
    MIXED_ENEMY_POINTER_TABLE_ADDRESS,
    MMG_LOSE_LARGE_OFFSET,
    MMG_LOSE_SMALL_2_OFFSET,
    MMG_LOSE_SMALL_OFFSET,
    MMG_WIN_LARGE_OFFSET_A,
    MMG_WIN_SMALL_OFFSET_A,
    NES_HEADER_SIZE,
    NUM_QUOTES,
    NUM_TABLES,
    OVERWORLD_DATA_ADDRESS,
    PLAYER_BIG_SHIELD_PROFILE_SPRITES_ADDRESS,
    PLAYER_BIG_SHIELD_PROFILE_SPRITES_SIZE,
    PLAYER_CHEER_SPRITES_ADDRESS,
    PLAYER_CHEER_SPRITES_SIZE,
    PLAYER_LARGE_SHIELD_SPRITES_ADDRESS,
    PLAYER_LARGE_SHIELD_SPRITES_SIZE,
    PLAYER_MAIN_SPRITES_ADDRESS,
    PLAYER_MAIN_SPRITES_SIZE,
    PLAYER_PROFILE_NO_SHIELD_SPRITES_ADDRESS,
    PLAYER_PROFILE_NO_SHIELD_SPRITES_SIZE,
    PLAYER_SMALL_SHIELD_SPRITES_ADDRESS,
    PLAYER_SMALL_SHIELD_SPRITES_SIZE,
    POINTER_COUNT,
    QUOTE_DATA_ADDRESS,
    RANDOMIZER_MAGIC,
    RECORDER_WARP_DESTINATIONS_ADDRESS,
    RECORDER_WARP_Y_COORDINATES_ADDRESS,
    START_POSITION_Y_ADDRESS,
    START_SCREEN_ADDRESS,
    TILE_MAPPING_DATA_ADDRESS,
    TILE_MAPPING_DATA_SIZE,
    TILE_MAPPING_POINTERS_ADDRESS,
    TILE_MAPPING_POINTERS_SIZE,
    TITLE_VERSION_OFFSET,
    WHITE_SWORD_REQUIREMENT_ADDRESS,
    read_le16,
)


@dataclass
class RawBinFiles:
    level_1_6_data:       bytes   # 0x300 bytes
    level_7_9_data:       bytes   # 0x300 bytes
    level_info:           bytes   # 0xA * 0xFC bytes
    level_pointers:       bytes
    overworld_data:       bytes   # 0x500 bytes
    mixed_enemy_data:     bytes
    mixed_enemy_pointers: bytes
    armos_tables:                 bytes   # 14 bytes: 7 screen IDs + 7 sprite X-positions
    armos_item:                   bytes   # 1 byte
    coast_item:                   bytes   # 1 byte
    white_sword_requirement:      bytes   # 1 byte: (hearts-1)*16 in upper nibble
    magical_sword_requirement:    bytes   # 1 byte: (hearts-1)*16 in upper nibble
    cave_item_data:               bytes   # 20 caves x 3 bytes = 60 bytes
    cave_price_data:              bytes   # 20 caves x 3 bytes = 60 bytes
    cave_quotes_data:             bytes   # 20 bytes at CAVE_QUOTES_DATA_ADDRESS; low 6 bits = quote_id
    hint_shop_quotes:             bytes   # 6 bytes at HINT_SHOP_QUOTES_ADDRESS; low 6 bits = quote_id
    bomb_cost:                    bytes   # 1 byte at BOMB_COST_OFFSET
    bomb_count:                   bytes   # 1 byte at BOMB_COUNT_OFFSET
    door_repair_charge:           bytes   # 1 byte
    mmg_lose_small:               bytes   # 1 byte
    mmg_lose_small_2:             bytes   # 1 byte
    mmg_lose_large:               bytes   # 1 byte
    mmg_win_small:                bytes   # 1 byte
    mmg_win_large:                bytes   # 1 byte
    recorder_warp_destinations:   bytes   # 8 bytes, one per level 1-8
    recorder_warp_y_coordinates:  bytes   # 8 bytes, one per level 1-8
    any_road_screens:             bytes   # 4 bytes: shortcut screen locations
    start_screen:                 bytes   # 1 byte: Link's starting overworld screen
    start_position_y:             bytes   # 1 byte: Link's starting Y position (ROM offset 0x19328+header)
    level_sprite_set_pointers:    bytes   # 10 x 2-byte CPU addrs (index 0=OW, 1-9=levels)
    boss_sprite_set_pointers:     bytes   # 10 x 2-byte CPU addrs (index 0=OW, 1-9=levels)
    quotes_data:                  bytes   # pointer table + quote text (0x4010-0x4582)
    maze_directions:              bytes   # 8 bytes: dead woods (0x6DA7-0x6DAA) + lost hills (0x6DAB-0x6DAE)
    ow_sprites:                   bytes   # 0x640 bytes at 0xD24B: overworld sprite bank (addl + enemy)
    enemy_set_b_sprites:          bytes   # 0x220 bytes at 0xD88B: enemy sprite set B
    enemy_set_c_sprites:          bytes   # 0x220 bytes at 0xDAAB: enemy sprite set C
    dungeon_common_sprites:       bytes   # 0x100 bytes at 0xDCCB: dungeon common sprites
    enemy_set_a_sprites:          bytes   # 0x220 bytes at 0xDDCB: enemy sprite set A
    boss_set_a_sprites:           bytes   # 0x400 bytes at 0xDFEB: boss sprite set A
    boss_set_b_sprites:           bytes   # 0x400 bytes at 0xE3EB: boss sprite set B
    boss_set_c_sprites:           bytes   # 0x400 bytes at 0xE7EB: boss sprite set C
    boss_set_expansion_sprites:   bytes   # 0x200 bytes at 0x8A8F: boss sprite expansion
    tile_mapping_pointers:        bytes   # 0x7F bytes at 0x6E14: tile codes for enemies + cave chars
    tile_mapping_data:            bytes   # 0xCC bytes at 0x6E93: tile codes for enemy animation frames
    # Enemy / boss HP tables (nibble-packed)
    enemy_hp_table:               bytes   # 25 bytes (50 nibbles) at file offset 129886
    boss_hp_table:                bytes   # 12 bytes (24 nibbles) at file offset 129911
    # Secondary boss HP bytes (single bytes, HP in high nibble)
    aquamentus_hp:                bytes   # 1 byte at 73926
    aquamentus_sp:                bytes   # 1 byte at 75573
    ganon_hp:                     bytes   # 1 byte at 77607
    gleeok_hp:                    bytes   # 1 byte at 70869
    patra_hp:                     bytes   # 1 byte at 76357
    # Player (Link) sprite banks
    player_main_sprites:              bytes  # 0x1C0 bytes at 0x808F
    player_cheer_sprites:             bytes  # 0x20 bytes at 0x4E44
    player_big_shield_profile_sprites: bytes # 0x20 bytes at 0x4EC4
    player_profile_no_shield_sprites: bytes  # 0x20 bytes at 0x85CF
    player_small_shield_sprites:      bytes  # 0x40 bytes at 0x860F
    player_large_shield_sprites:      bytes  # 0x20 bytes at 0x868F


def load_bin_files(test_data_dir: Path) -> RawBinFiles:
    def read(name: str) -> bytes:
        return (test_data_dir / name).read_bytes()
    def read_optional(name: str) -> bytes:
        p = test_data_dir / name
        return p.read_bytes() if p.exists() else b""
    return RawBinFiles(
        level_1_6_data       = read("level_1_6_data.bin"),
        level_7_9_data       = read("level_7_9_data.bin"),
        level_info           = read("level_info.bin"),
        level_pointers       = b"",  # placeholder
        overworld_data       = read("overworld_data.bin"),
        mixed_enemy_data     = read("mixed_enemy_data.bin"),
        mixed_enemy_pointers = read("mixed_enemy_pointers.bin"),
        armos_tables              = read("armos_tables.bin"),
        armos_item                = read("armos_item.bin"),
        coast_item                = read("coast_item.bin"),
        white_sword_requirement   = read("white_sword_requirement.bin"),
        magical_sword_requirement = read("magical_sword_requirement.bin"),
        cave_item_data            = read("cave_item_data.bin"),
        cave_price_data           = read("cave_price_data.bin"),
        cave_quotes_data          = read("cave_quotes_data.bin"),
        hint_shop_quotes          = read("hint_shop_quotes.bin"),
        bomb_cost                 = read("bomb_cost.bin"),
        bomb_count                = read("bomb_count.bin"),
        door_repair_charge        = read("door_repair_charge.bin"),
        mmg_lose_small            = read("mmg_lose_small.bin"),
        mmg_lose_small_2          = read("mmg_lose_small_2.bin"),
        mmg_lose_large            = read("mmg_lose_large.bin"),
        mmg_win_small             = read("mmg_win_small.bin"),
        mmg_win_large             = read("mmg_win_large.bin"),
        recorder_warp_destinations      = read("recorder_warp_destinations.bin"),
        recorder_warp_y_coordinates     = read("recorder_warp_y_coordinates.bin"),
        any_road_screens                = read("any_road_screens.bin"),
        start_screen                    = read("start_screen.bin"),
        start_position_y                = read("start_position_y.bin"),
        level_sprite_set_pointers       = read("level_sprite_set_pointers.bin"),
        boss_sprite_set_pointers        = read("boss_sprite_set_pointers.bin"),
        quotes_data                     = read_optional("quotes_data.bin"),
        maze_directions                 = read("maze_directions.bin"),
        ow_sprites                      = read("ow_sprites.bin"),
        enemy_set_b_sprites             = read("enemy_set_b_sprites.bin"),
        enemy_set_c_sprites             = read("enemy_set_c_sprites.bin"),
        dungeon_common_sprites          = read("dungeon_common_sprites.bin"),
        enemy_set_a_sprites             = read("enemy_set_a_sprites.bin"),
        boss_set_a_sprites              = read("boss_set_a_sprites.bin"),
        boss_set_b_sprites              = read("boss_set_b_sprites.bin"),
        boss_set_c_sprites              = read("boss_set_c_sprites.bin"),
        boss_set_expansion_sprites      = read_optional("boss_set_expansion_sprites.bin"),
        tile_mapping_pointers           = read("tile_mapping_pointers.bin"),
        tile_mapping_data               = read("tile_mapping_data.bin"),
        enemy_hp_table                  = read("enemy_hp_table.bin"),
        boss_hp_table                   = read("boss_hp_table.bin"),
        aquamentus_hp                   = read("aquamentus_hp.bin"),
        aquamentus_sp                   = read("aquamentus_sp.bin"),
        ganon_hp                        = read("ganon_hp.bin"),
        gleeok_hp                       = read("gleeok_hp.bin"),
        patra_hp                        = read("patra_hp.bin"),
        player_main_sprites              = read("player_main_sprites.bin"),
        player_cheer_sprites             = read("player_cheer_sprites.bin"),
        player_big_shield_profile_sprites = read("player_big_shield_profile_sprites.bin"),
        player_profile_no_shield_sprites = read("player_profile_no_shield_sprites.bin"),
        player_small_shield_sprites      = read("player_small_shield_sprites.bin"),
        player_large_shield_sprites      = read("player_large_shield_sprites.bin"),
    )


def load_bin_files_q2(test_data_dir: Path) -> RawBinFiles:
    """Load bin files for the second quest, swapping in Q2 grids and level info."""
    bins = load_bin_files(test_data_dir)
    def read(name: str) -> bytes:
        return (test_data_dir / name).read_bytes()
    return RawBinFiles(
        **{**bins.__dict__,
           "level_1_6_data": read("level_1_6_data_q2.bin"),
           "level_7_9_data": read("level_7_9_data_q2.bin"),
           "level_info":     read("level_info_q2.bin"),
        }
    )


# iNES header (16 bytes) + 128 KB PRG ROM = 131088 bytes exactly.
_NES_ROM_SIZE = NES_HEADER_SIZE + 0x20000
_NES_MAGIC    = b"NES\x1a"

# mixed_enemy_data sits immediately before the pointer table in bank 5.
_MIXED_ENEMY_DATA_ADDRESS = MIXED_ENEMY_POINTER_TABLE_ADDRESS - 201
_MIXED_ENEMY_DATA_SIZE    = 201


def is_randomizer_rom(rom_bytes: bytes) -> bool:
    """Return True if rom_bytes looks like a ZORA-randomized Zelda 1 ROM.

    Checks:
      - Correct iNES magic at offset 0.
      - Correct file size (16-byte header + 128 KB PRG).
      - RANDOMIZER_MAGIC bytes at TITLE_VERSION_OFFSET.
    """
    if len(rom_bytes) != _NES_ROM_SIZE:
        return False
    if rom_bytes[:4] != _NES_MAGIC:
        return False
    magic_slice = rom_bytes[TITLE_VERSION_OFFSET: TITLE_VERSION_OFFSET + len(RANDOMIZER_MAGIC)]
    return magic_slice == RANDOMIZER_MAGIC


def load_bin_files_from_rom(rom_bytes: bytes) -> RawBinFiles:
    """Build a RawBinFiles by slicing a full .nes ROM file in memory.

    Equivalent to load_bin_files() but reads from a bytes object instead of
    individual .bin files on disk.  The caller is responsible for validating
    the ROM with is_randomizer_rom() before calling this.
    """
    def s(addr: int, size: int) -> bytes:
        return rom_bytes[addr: addr + size]

    return RawBinFiles(
        level_1_6_data              = s(LEVEL_1_6_DATA_ADDRESS,              0x300),
        level_7_9_data              = s(LEVEL_7_9_DATA_ADDRESS,              0x300),
        level_info                  = s(LEVEL_INFO_ADDRESS,                  0xA * 0xFC),
        level_pointers              = b"",
        overworld_data              = s(OVERWORLD_DATA_ADDRESS,              0x500),
        mixed_enemy_data            = s(_MIXED_ENEMY_DATA_ADDRESS,           _MIXED_ENEMY_DATA_SIZE),
        mixed_enemy_pointers        = s(MIXED_ENEMY_POINTER_TABLE_ADDRESS,   POINTER_COUNT * 2),
        armos_tables                = s(ARMOS_TABLES_ADDRESS,                14),
        armos_item                  = s(ARMOS_ITEM_ADDRESS,                  1),
        coast_item                  = s(COAST_ITEM_ADDRESS,                  1),
        white_sword_requirement     = s(WHITE_SWORD_REQUIREMENT_ADDRESS,     1),
        magical_sword_requirement   = s(MAGICAL_SWORD_REQUIREMENT_ADDRESS,   1),
        cave_item_data              = s(CAVE_ITEM_DATA_ADDRESS,              60),
        cave_price_data             = s(CAVE_PRICE_DATA_ADDRESS,             60),
        cave_quotes_data            = s(CAVE_QUOTES_DATA_ADDRESS,            20),
        hint_shop_quotes            = s(HINT_SHOP_QUOTES_ADDRESS,            6),
        bomb_cost                   = s(BOMB_COST_OFFSET,                    1),
        bomb_count                  = s(BOMB_COUNT_OFFSET,                   1),
        door_repair_charge          = s(DOOR_REPAIR_CHARGE_ADDRESS,          1),
        mmg_lose_small              = s(MMG_LOSE_SMALL_OFFSET,               1),
        mmg_lose_small_2            = s(MMG_LOSE_SMALL_2_OFFSET,             1),
        mmg_lose_large              = s(MMG_LOSE_LARGE_OFFSET,               1),
        mmg_win_small               = s(MMG_WIN_SMALL_OFFSET_A,              1),
        mmg_win_large               = s(MMG_WIN_LARGE_OFFSET_A,              1),
        recorder_warp_destinations  = s(RECORDER_WARP_DESTINATIONS_ADDRESS,  8),
        recorder_warp_y_coordinates = s(RECORDER_WARP_Y_COORDINATES_ADDRESS, 8),
        any_road_screens            = s(ANY_ROAD_SCREENS_ADDRESS,            4),
        start_screen                = s(START_SCREEN_ADDRESS,                1),
        start_position_y            = s(START_POSITION_Y_ADDRESS,            1),
        level_sprite_set_pointers   = s(LEVEL_SPRITE_SET_POINTERS_ADDRESS,   20),
        boss_sprite_set_pointers    = s(BOSS_SPRITE_SET_POINTERS_ADDRESS,    20),
        quotes_data                 = s(QUOTE_DATA_ADDRESS,                  1442),
        maze_directions             = s(MAZE_DIRECTIONS_ADDRESS,             8),
        ow_sprites                  = s(OW_SPRITES_ADDRESS,             OW_SPRITES_SIZE),
        enemy_set_b_sprites         = s(ENEMY_SET_B_SPRITES_ADDRESS,    ENEMY_SET_B_SPRITES_SIZE),
        enemy_set_c_sprites         = s(ENEMY_SET_C_SPRITES_ADDRESS,    ENEMY_SET_C_SPRITES_SIZE),
        dungeon_common_sprites      = s(DUNGEON_COMMON_SPRITES_ADDRESS, DUNGEON_COMMON_SPRITES_SIZE),
        enemy_set_a_sprites         = s(ENEMY_SET_A_SPRITES_ADDRESS,    ENEMY_SET_A_SPRITES_SIZE),
        boss_set_a_sprites          = s(BOSS_SET_A_SPRITES_ADDRESS,     BOSS_SET_A_SPRITES_SIZE),
        boss_set_b_sprites          = s(BOSS_SET_B_SPRITES_ADDRESS,     BOSS_SET_B_SPRITES_SIZE),
        boss_set_c_sprites          = s(BOSS_SET_C_SPRITES_ADDRESS,     BOSS_SET_C_SPRITES_SIZE),
        boss_set_expansion_sprites  = s(BOSS_SET_EXPANSION_SPRITES_ADDRESS, BOSS_SET_EXPANSION_SPRITES_SIZE),
        tile_mapping_pointers       = s(TILE_MAPPING_POINTERS_ADDRESS, TILE_MAPPING_POINTERS_SIZE),
        tile_mapping_data           = s(TILE_MAPPING_DATA_ADDRESS,     TILE_MAPPING_DATA_SIZE),
        enemy_hp_table              = s(ENEMY_HP_TABLE_ADDRESS,        ENEMY_HP_TABLE_SIZE),
        boss_hp_table               = s(BOSS_HP_TABLE_ADDRESS,         BOSS_HP_TABLE_SIZE),
        aquamentus_hp               = s(AQUAMENTUS_HP_ADDRESS,         1),
        aquamentus_sp               = s(AQUAMENTUS_SP_ADDRESS,         1),
        ganon_hp                    = s(GANON_HP_ADDRESS,              1),
        gleeok_hp                   = s(GLEEOK_HP_ADDRESS,             1),
        patra_hp                    = s(PATRA_HP_ADDRESS,              1),
        player_main_sprites              = s(PLAYER_MAIN_SPRITES_ADDRESS,              PLAYER_MAIN_SPRITES_SIZE),
        player_cheer_sprites             = s(PLAYER_CHEER_SPRITES_ADDRESS,             PLAYER_CHEER_SPRITES_SIZE),
        player_big_shield_profile_sprites = s(PLAYER_BIG_SHIELD_PROFILE_SPRITES_ADDRESS, PLAYER_BIG_SHIELD_PROFILE_SPRITES_SIZE),
        player_profile_no_shield_sprites = s(PLAYER_PROFILE_NO_SHIELD_SPRITES_ADDRESS, PLAYER_PROFILE_NO_SHIELD_SPRITES_SIZE),
        player_small_shield_sprites      = s(PLAYER_SMALL_SHIELD_SPRITES_ADDRESS,      PLAYER_SMALL_SHIELD_SPRITES_SIZE),
        player_large_shield_sprites      = s(PLAYER_LARGE_SHIELD_SPRITES_ADDRESS,      PLAYER_LARGE_SHIELD_SPRITES_SIZE),
    )


# ---------------------------------------------------------------------------
# Mixed enemy group parsing
# ---------------------------------------------------------------------------

def _parse_mixed_enemy_groups(bins: RawBinFiles) -> dict[int, EnemySpec]:
    """Returns a dict mapping enemy code (0x62-0x7F) → EnemySpec."""
    groups: dict[int, EnemySpec] = {}
    ptr_data = bins.mixed_enemy_pointers
    cpu_addrs = [ptr_data[i*2] | (ptr_data[i*2+1] << 8) for i in range(POINTER_COUNT)]
    min_cpu = min(cpu_addrs)
    for i in range(POINTER_COUNT):
        code = FIRST_MIXED_GROUP_CODE + i
        cpu_addr = cpu_addrs[i]
        data_offset = cpu_addr - min_cpu
        member_bytes = bins.mixed_enemy_data[data_offset:data_offset + 8]
        members = [Enemy(b) for b in member_bytes]
        groups[code] = EnemySpec(
            enemy=Enemy(code),
            is_group=True,
            group_members=members,
        )
    return groups


# ---------------------------------------------------------------------------
# Level info helpers
# ---------------------------------------------------------------------------

def _level_info_block(bins: RawBinFiles, level_index: int) -> bytes:
    """level_index 0 = overworld info slot, 1 = Level 1, ..., 9 = Level 9"""
    offset = level_index * LEVEL_INFO_SIZE
    return bins.level_info[offset:offset + LEVEL_INFO_SIZE]

def _level_info_block_by_index(bins: RawBinFiles, index: int) -> bytes:
    offset = index * LEVEL_INFO_SIZE
    return bins.level_info[offset:offset + LEVEL_INFO_SIZE]


# ---------------------------------------------------------------------------
# Room parsing
# ---------------------------------------------------------------------------

def _parse_staircase_room(
    room_num: int,
    t0: int, t1: int, t2: int, t3: int, t4: int, t5: int,
) -> "StaircaseRoom":
    room_type = RoomType(t3 & 0x3F)
    exit_x = (t2 >> 4) & 0x0F
    exit_y = t2 & 0x0F
    if room_type == RoomType.TRANSPORT_STAIRCASE:
        return StaircaseRoom(
            room_num=room_num,
            room_type=room_type,
            exit_x=exit_x,
            exit_y=exit_y,
            left_exit=t0 & 0x7F,
            right_exit=t1 & 0x7F,
            t5_raw=t5,
        )
    # ITEM_STAIRCASE
    return StaircaseRoom(
        room_num=room_num,
        room_type=room_type,
        exit_x=exit_x,
        exit_y=exit_y,
        item=Item(t4 & 0x1F),
        return_dest=t0 & 0x7F,
        t5_raw=t5,
    )


def _parse_room(
    room_num: int,
    t0: int, t1: int, t2: int, t3: int, t4: int, t5: int,
    qty_table: list[int],
    mixed_groups: dict[int, EnemySpec],
) -> Room:
    room_type = RoomType(t3 & 0x3F)
    movable_block = bool(t3 & 0x40)

    north_wall = WallType((t0 >> 5) & 0x07)
    south_wall = WallType((t0 >> 2) & 0x07)
    west_wall  = WallType((t1 >> 5) & 0x07)
    east_wall  = WallType((t1 >> 2) & 0x07)
    walls = WallSet(north=north_wall, east=east_wall,
                    south=south_wall, west=west_wall)
    palette_0 = t0 & 0x03
    palette_1 = t1 & 0x03

    enemy_code = t2 & 0x3F
    if t3 & 0x80:
        enemy_code += 0x40
    qty_code = (t2 >> 6) & 0x03
    enemy_quantity = qty_table[qty_code]

    if enemy_code in mixed_groups:
        enemy_spec = EnemySpec(
            enemy=Enemy(enemy_code),
            is_group=True,
            group_members=list(mixed_groups[enemy_code].group_members or []),
        )
    else:
        enemy_spec = EnemySpec(enemy=Enemy(enemy_code))

    is_dark    = bool(t4 & 0x80)
    boss_cry_2 = bool(t4 & 0x40)
    boss_cry_1 = bool(t4 & 0x20)
    item_code  = t4 & 0x1F

    if item_code == DUNGEON_NOTHING_CODE:
        item = Item.NOTHING
    else:
        item = Item(item_code)

    item_position = ItemPosition((t5 >> 4) & 0x03)
    room_action   = RoomAction(t5 & 0x07)

    return Room(
        room_num=room_num,
        room_type=room_type,
        walls=walls,
        enemy_spec=enemy_spec,
        enemy_quantity=enemy_quantity,
        item=item,
        item_position=item_position,
        room_action=room_action,
        is_dark=is_dark,
        boss_cry_1=boss_cry_1,
        boss_cry_2=boss_cry_2,
        movable_block=movable_block,
        palette_0=palette_0,
        palette_1=palette_1,
    )


# ---------------------------------------------------------------------------
# Level parsing
# ---------------------------------------------------------------------------

_CPU_TO_ENEMY_SET: dict[int, EnemySpriteSet] = {
    0x9DBB: EnemySpriteSet.A,
    0x987B: EnemySpriteSet.B,
    0x9A9B: EnemySpriteSet.C,
    0x965B: EnemySpriteSet.OW,
}

_CPU_TO_BOSS_SET: dict[int, BossSpriteSet] = {
    0x9FDB: BossSpriteSet.A,
    0xA3DB: BossSpriteSet.B,
    0xA7DB: BossSpriteSet.C,
}


def _read_cpu_addr(data: bytes, index: int) -> int:
    return read_le16(data, index)


def _parse_enemy_sprite_set(bins: RawBinFiles, level_num: int) -> EnemySpriteSet:
    cpu_addr = _read_cpu_addr(bins.level_sprite_set_pointers, level_num)
    return _CPU_TO_ENEMY_SET.get(cpu_addr, VANILLA_ENEMY_SPRITE_SETS[level_num])


def _parse_boss_sprite_set(bins: RawBinFiles, level_num: int) -> BossSpriteSet:
    cpu_addr = _read_cpu_addr(bins.boss_sprite_set_pointers, level_num)
    return _CPU_TO_BOSS_SET.get(cpu_addr, VANILLA_BOSS_SPRITE_SETS[level_num])


def _flood_fill_level_rooms(
    entrance_room: int,
    staircase_slots: set[int],
    t: list[bytes],
) -> set[int]:
    """Flood-fill from entrance_room to find all reachable room slots."""
    direction_offsets = [
        (Direction.NORTH, -0x10),
        (Direction.SOUTH, +0x10),
        (Direction.EAST,  +0x01),
        (Direction.WEST,  -0x01),
    ]

    def in_bounds(rn: int) -> bool:
        return 0x00 <= rn <= 0x7F

    def neighbor_in_bounds(rn: int, direction: Direction) -> bool:
        row, col = rn >> 4, rn & 0xF
        if direction == Direction.NORTH and row == 0:
            return False
        if direction == Direction.SOUTH and row == 7:
            return False
        if direction == Direction.WEST and col == 0:
            return False
        if direction == Direction.EAST and col == 15:
            return False
        return True

    def wall_fill(seeds: list[int], visited: set[int]) -> None:
        queue = list(seeds)
        while queue:
            rn = queue.pop()
            if rn in visited or not in_bounds(rn):
                continue
            visited.add(rn)
            if rn in staircase_slots:
                continue
            north_wall = WallType((t[0][rn] >> 5) & 0x07)
            south_wall = WallType((t[0][rn] >> 2) & 0x07)
            west_wall  = WallType((t[1][rn] >> 5) & 0x07)
            east_wall  = WallType((t[1][rn] >> 2) & 0x07)
            wall_by_dir = {
                Direction.NORTH: north_wall,
                Direction.SOUTH: south_wall,
                Direction.WEST:  west_wall,
                Direction.EAST:  east_wall,
            }
            for direction, offset in direction_offsets:
                if wall_by_dir[direction] != WallType.SOLID_WALL:
                    if neighbor_in_bounds(rn, direction):
                        neighbor = rn + offset
                        if neighbor not in visited:
                            queue.append(neighbor)

    visited: set[int] = set()
    wall_fill([entrance_room], visited)

    while True:
        new_seeds = []
        for rn in staircase_slots:
            if rn in visited:
                continue
            if RoomType(t[3][rn] & 0x3F) == RoomType.TRANSPORT_STAIRCASE:
                left_exit  = t[0][rn] & 0x7F
                right_exit = t[1][rn] & 0x7F
                if left_exit in visited or right_exit in visited:
                    visited.add(rn)
                    new_seeds.append(left_exit)
                    new_seeds.append(right_exit)
        if not new_seeds:
            break
        wall_fill(new_seeds, visited)

    return visited


def _parse_level(
    level_num: int,
    grid_data: bytes,
    level_index: int,
    bins: RawBinFiles,
    mixed_groups: dict[int, EnemySpec],
) -> Level:
    block = _level_info_block(bins, level_num)

    palette_raw      = bytes(block[0x00:0x24])
    fade_palette_raw = bytes(block[0x7C:0xDC])
    qty_table        = list(block[0x24:0x28])

    start_y              = block[0x28]
    item_position_table  = list(block[0x29:0x2D])
    map_start            = block[0x2D]
    map_cursor_offset    = block[0x2E]
    entrance_room        = block[0x2F]
    screen_status_ram_offset = bytes(block[0x31:0x33])
    rom_level_num        = block[0x33]
    stairway_data_raw    = bytes(block[0x34:0x3E])
    boss_room            = block[0x3E]

    staircase_room_pool: list[int] = []
    for b in stairway_data_raw:
        if b == 0xFF:
            break
        staircase_room_pool.append(b)

    if level_num == 3 and len(staircase_room_pool) == 0:
        staircase_room_pool.append(0x0F)

    t = [grid_data[table * LEVEL_TABLE_SIZE: (table + 1) * LEVEL_TABLE_SIZE]
         for table in range(NUM_TABLES)]

    staircase_slots = set(staircase_room_pool)
    reachable = _flood_fill_level_rooms(entrance_room, staircase_slots, t)
    regular_room_slots = reachable - staircase_slots

    rooms: list[Room] = []
    for room_num in sorted(regular_room_slots):
        rooms.append(_parse_room(
            room_num=room_num,
            t0=t[0][room_num], t1=t[1][room_num],
            t2=t[2][room_num], t3=t[3][room_num],
            t4=t[4][room_num], t5=t[5][room_num],
            qty_table=qty_table,
            mixed_groups=mixed_groups,
        ))

    staircase_rooms: list[StaircaseRoom] = []
    for room_num in sorted(staircase_slots):
        staircase_rooms.append(_parse_staircase_room(
            room_num=room_num,
            t0=t[0][room_num], t1=t[1][room_num],
            t2=t[2][room_num], t3=t[3][room_num],
            t4=t[4][room_num], t5=t[5][room_num],
        ))

    return Level(
        level_num=level_num,
        entrance_room=entrance_room,
        entrance_direction=Direction.SOUTH,
        palette_raw=palette_raw,
        fade_palette_raw=fade_palette_raw,
        staircase_room_pool=staircase_room_pool,
        rooms=rooms,
        staircase_rooms=staircase_rooms,
        boss_room=boss_room,
        enemy_sprite_set=_parse_enemy_sprite_set(bins, level_num),
        boss_sprite_set=_parse_boss_sprite_set(bins, level_num),
        start_y=start_y,
        item_position_table=item_position_table,
        map_start=map_start,
        map_cursor_offset=map_cursor_offset,
        qty_table=qty_table,
        stairway_data_raw=stairway_data_raw,
        rom_level_num=rom_level_num,
        screen_status_ram_offset=screen_status_ram_offset,
    )


# ---------------------------------------------------------------------------
# Cave data parsing
# ---------------------------------------------------------------------------

def _cave_item(raw: int) -> Item:
    """Extract item from a cave data byte (low 6 bits; 0x3F = nothing)."""
    code = raw & 0x3F
    if code == CAVE_NOTHING_CODE:
        return Item.NOTHING
    return Item(code)

def _cave_qid(cave_quotes: bytes, cave_index: int) -> int:
    """Extract quote_id from the cave quotes table (low 6 bits of each byte).
    The ROM stores quote_id * 2; divide by 2 to get the logical quote index."""
    return (cave_quotes[cave_index] & 0x3F) // 2


def _parse_cave_data(bins: RawBinFiles) -> list[CaveDefinition]:
    """Parse all cave/shop definitions into a list of CaveDefinition instances."""
    items  = bins.cave_item_data
    prices = bins.cave_price_data
    cq     = bins.cave_quotes_data   # 20-byte quote ID table
    hsq    = bins.hint_shop_quotes   # 6-byte hint shop slot quote table

    def ci(idx: int) -> tuple[int, int, int]:
        return items[idx*3], items[idx*3+1], items[idx*3+2]

    def cp(idx: int) -> tuple[int, int, int]:
        return prices[idx*3], prices[idx*3+1], prices[idx*3+2]

    def dest(idx: int) -> Destination:
        return Destination(0x10 + idx)

    def qid(idx: int) -> int:
        return _cave_qid(cq, idx)

    caves: list[CaveDefinition] = []

    def _extra_candle(raw: int) -> Item:
        """Parse optional extra candle item from byte 0 low 6 bits (0x3F = none)."""
        code = raw & 0x3F
        return Item.OVERWORLD_NO_ITEM if code == CAVE_NOTHING_CODE else Item(code)

    # 0: Wood Sword Cave — optional extra item in byte 0, main item in byte 1, nothing in byte 2
    ws_b0, ws_b1, _ = ci(0)
    caves.append(ItemCave(
        destination=dest(0),
        item=_cave_item(ws_b1),
        maybe_extra_candle=_extra_candle(ws_b0),
        quote_id=qid(0),
    ))

    # 1: Take Any — left item in byte 0, middle item in byte 1, right item in byte 2
    b0, b1, b2 = ci(1)
    caves.append(TakeAnyCave(
        destination=dest(1),
        quote_id=qid(1),
        items = [_cave_item(b0), _cave_item(b1), _cave_item(b2)]
    ))

    # 2: White Sword Cave — optional extra item in byte 0, main item in byte 1, nothing in byte 2
    white_hearts = (bins.white_sword_requirement[0] >> 4) + 1
    ws2_b0, ws2_b1, _ = ci(2)
    caves.append(ItemCave(
        destination=dest(2),
        item=_cave_item(ws2_b1),
        maybe_extra_candle=_extra_candle(ws2_b0),
        quote_id=qid(2),
        heart_requirement=white_hearts,
    ))

    # 3: Magical Sword Cave — optional extra item in byte 0, main item in byte 1, nothing in byte 2
    magical_hearts = (bins.magical_sword_requirement[0] >> 4) + 1
    ms_b0, ms_b1, _ = ci(3)
    caves.append(ItemCave(
        destination=dest(3),
        item=_cave_item(ms_b1),
        maybe_extra_candle=_extra_candle(ms_b0),
        quote_id=qid(3),
        heart_requirement=magical_hearts,
    ))

    # 4: Any Road — hint only, no item data
    caves.append(HintCave(
        destination=dest(4),
        quote_id=qid(4),
    ))

    # 5: Lost Hills Hint — hint only, no item data
    caves.append(HintCave(
        destination=dest(5),
        quote_id=qid(5),
    ))

    # 6: Money Making Game — bet amounts from price bytes; win/lose from separate ROM locations
    mmg_p0, mmg_p1, mmg_p2 = cp(6)
    caves.append(MoneyMakingGameCave(
        destination=dest(6),
        quote_id=qid(6),
        bet_low=mmg_p0,
        bet_mid=mmg_p1,
        bet_high=mmg_p2,
        lose_small=bins.mmg_lose_small[0],
        lose_small_2=bins.mmg_lose_small_2[0],
        lose_large=bins.mmg_lose_large[0],
        win_small=bins.mmg_win_small[0],
        win_large=bins.mmg_win_large[0],
    ))

    # 7: Door Repair — cost from separate bin; no item data
    caves.append(DoorRepairCave(
        destination=dest(7),
        quote_id=qid(7),
        cost=bins.door_repair_charge[0],
    ))

    # 8: Letter Cave — optional extra item in byte 0, main item in byte 1, nothing in byte 2
    lc_b0, lc_b1, _ = ci(8)
    caves.append(ItemCave(
        destination=dest(8),
        item=_cave_item(lc_b1),
        maybe_extra_candle=_extra_candle(lc_b0),
        quote_id=qid(8),
    ))

    # 9: Dead Woods Hint — hint only, no item data
    caves.append(HintCave(
        destination=dest(9),
        quote_id=qid(9),
    ))

    # 10: Potion Shop (SHOP_E) — items in bytes 0 and 2 only (2-item shop); letter required
    shop_e_b0, _, shop_e_b2 = ci(10)
    shop_e_p0, _, shop_e_p2 = cp(10)
    caves.append(Shop(
        destination=dest(10),
        quote_id=qid(10),
        shop_type=ShopType.SHOP_E,
        letter_requirement=True,
        items=[
            ShopItem(item=_cave_item(shop_e_b0), price=shop_e_p0),
            ShopItem(item=_cave_item(shop_e_b2), price=shop_e_p2),
        ],
    ))

    # 11: Hint Shop 1 — slot quote IDs from hint_shop_quotes[0:3]
    hs1_p0, hs1_p1, hs1_p2 = cp(11)
    caves.append(HintShop(
        destination=dest(11),
        quote_id=qid(11),
        hints=[
            HintShopItem(quote_id=(hsq[0] & 0x3F) // 2, price=hs1_p0),
            HintShopItem(quote_id=(hsq[1] & 0x3F) // 2, price=hs1_p1),
            HintShopItem(quote_id=(hsq[2] & 0x3F) // 2, price=hs1_p2),
        ],
    ))

    # 12: Hint Shop 2 — slot quote IDs from hint_shop_quotes[3:6]
    hs2_p0, hs2_p1, hs2_p2 = cp(12)
    caves.append(HintShop(
        destination=dest(12),
        quote_id=qid(12),
        hints=[
            HintShopItem(quote_id=(hsq[3] & 0x3F) // 2, price=hs2_p0),
            HintShopItem(quote_id=(hsq[4] & 0x3F) // 2, price=hs2_p1),
            HintShopItem(quote_id=(hsq[5] & 0x3F) // 2, price=hs2_p2),
        ],
    ))

    # 13-16: Shops A-D — all 3 items and prices
    for idx, shop_type in enumerate([ShopType.SHOP_A, ShopType.SHOP_B,
                                      ShopType.SHOP_C, ShopType.SHOP_D]):
        cave_idx = 13 + idx
        b0, b1, b2 = ci(cave_idx)
        p0, p1, p2 = cp(cave_idx)
        caves.append(Shop(
            destination=dest(cave_idx),
            quote_id=qid(cave_idx),
            shop_type=shop_type,
            letter_requirement=False,
            items=[
                ShopItem(item=_cave_item(b0), price=p0),
                ShopItem(item=_cave_item(b1), price=p1),
                ShopItem(item=_cave_item(b2), price=p2),
            ],
        ))

    # 17-19: Secret caves — rupee value in price byte 1
    for cave_idx, destination in [
        (17, Destination.MEDIUM_SECRET),
        (18, Destination.LARGE_SECRET),
        (19, Destination.SMALL_SECRET),
    ]:
        caves.append(SecretCave(
            destination=destination,
            quote_id=qid(cave_idx),
            rupee_value=cp(cave_idx)[1],
        ))

    # Overworld items — no cave table entry, no quote
    caves.append(OverworldItem(
        destination=Destination.ARMOS_ITEM,
        item=Item(bins.armos_item[0]),
    ))
    caves.append(OverworldItem(
        destination=Destination.COAST_ITEM,
        item=Item(bins.coast_item[0]),
        ladder_requirement=True,
    ))

    return caves


# ---------------------------------------------------------------------------
# Overworld parsing
# ---------------------------------------------------------------------------

def _parse_overworld(bins: RawBinFiles, mixed_groups: dict[int, EnemySpec]) -> Overworld:
    ow = bins.overworld_data
    t = [ow[i * 0x80:(i + 1) * 0x80] for i in range(6)]

    ow_block     = _level_info_block_by_index(bins, 0)
    ow_qty_table = list(ow_block[0x24:0x28])

    screens: list[Screen] = []
    for s in range(0x80):
        t0, t1, t2, t3, _t4, t5 = t[0][s], t[1][s], t[2][s], t[3][s], t[4][s], t[5][s]

        exit_x       = (t0 >> 4) & 0x0F
        has_zola     = bool(t0 & 0x08)
        has_ocean    = bool(t0 & 0x04)
        outer_palette = t0 & 0x03

        destination   = Destination((t1 >> 2) & 0x3F)
        inner_palette = t1 & 0x03

        qty_code   = (t2 >> 6) & 0x03
        enemy_low  = t2 & 0x3F
        is_mixed   = bool(t3 & 0x80)
        enemy_code = (enemy_low + 0x40) if is_mixed else enemy_low
        enemy_spec = mixed_groups.get(enemy_code, EnemySpec(enemy=Enemy(enemy_code)))
        enemy_quantity = ow_qty_table[qty_code]

        screen_code = t3 & 0x7F

        qv_code = (t5 >> 6) & 0x03
        if qv_code == 0:
            quest_visibility = QuestVisibility.BOTH_QUESTS
        elif qv_code == 1:
            quest_visibility = QuestVisibility.FIRST_QUEST
        else:
            quest_visibility = QuestVisibility.SECOND_QUEST

        screens.append(Screen(
            screen_num=s,
            destination=destination,
            entrance_type=SCREEN_ENTRANCE_TYPES.get(s, EntranceType.NONE),
            enemy_spec=enemy_spec,
            enemy_quantity=enemy_quantity,
            exit_x_position=exit_x,
            exit_y_position=t5 & 0x07,
            has_zola=has_zola,
            has_ocean_sound=has_ocean,
            enemies_from_sides=bool(t5 & 0x08),
            stairs_position_code=(t5 >> 4) & 0x03,
            quest_visibility=quest_visibility,
            outer_palette=outer_palette,
            inner_palette=inner_palette,
            screen_code=screen_code,
        ))

    return Overworld(
        screens=screens,
        enemy_sprite_set=_parse_enemy_sprite_set(bins, 0),
        caves=_parse_cave_data(bins),
        qty_table=ow_qty_table,
        dead_woods_directions=[OverworldDirection(b) for b in bins.maze_directions[0:4]],
        lost_hills_directions=[OverworldDirection(b) for b in bins.maze_directions[4:8]],
        armos_screen_ids=list(bins.armos_tables[0:7]),
        armos_positions=list(bins.armos_tables[7:14]),
        bomb_upgrade=BombUpgrade(cost=bins.bomb_cost[0], count=bins.bomb_count[0]),
        any_road_screens=list(bins.any_road_screens),
        recorder_warp_destinations=list(bins.recorder_warp_destinations),
        recorder_warp_y_coordinates=list(bins.recorder_warp_y_coordinates),
        start_screen=bins.start_screen[0],
        start_position_y=bins.start_position_y[0],
    )


# ---------------------------------------------------------------------------
# Quotes parsing
# ---------------------------------------------------------------------------

def _decode_quote(data: bytes, offset: int) -> str:
    """Decode one quote starting at data[offset]. Returns pipe-separated lines."""
    if offset >= len(data) or data[offset] == QUOTE_BLANK:
        return ""
    lines: list[str] = []
    current: list[str] = []
    while offset < len(data):
        raw = data[offset]
        offset += 1
        char = _BYTE_TO_CHAR.get(raw & QUOTE_CHAR_MASK, "?")
        current.append(char)
        high = raw & QUOTE_END_BITS
        if high == QUOTE_LINE1_BIT:
            lines.append("".join(current))
            current = []
        elif high == QUOTE_LINE2_BIT:
            lines.append("".join(current))
            current = []
        elif high == QUOTE_END_BITS:
            lines.append("".join(current))
            break
    return "|".join(lines)


def _parse_quotes(quotes_data: bytes) -> list[Quote]:
    """Parse all 38 quotes from the quotes_data block (pointer table + text)."""
    quotes = []
    for i in range(NUM_QUOTES):
        low  = quotes_data[i * 2]
        high = quotes_data[i * 2 + 1]
        data_offset = (high & 0x7F) * 0x100 + low
        # Extended hint bank pointers are CPU addresses into a different ROM
        # region and will be out of range for this buffer.  Return blank text
        # — the hint randomizer overwrites every quote anyway.
        if data_offset >= len(quotes_data):
            text = ""
        else:
            text = _decode_quote(quotes_data, data_offset)
        quotes.append(Quote(quote_id=i, text=text))
    return quotes


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Enemy tile mapping parse
# ---------------------------------------------------------------------------

# Enemy enum values that have tile table entries, in ROM slot order (slot = enemy_id + 1).
_TILE_TABLE_ENEMIES: list[Enemy] = sorted(
    [e for e in Enemy if e.value <= 0x52],
    key=lambda e: e.value,
)
_OVERWORLD_NPC_SLOT_COUNT = 43   # slots 0x54-0x7E
_TILE_MAPPING_POINTERS_TOTAL = 0x7F   # total slots in the pointer table


def _parse_enemy_tile_data(ptr_bytes: bytes, frame_bytes: bytes) -> "EnemyData":
    """Parse the flat tile mapping tables into structured EnemyData fields.

    ptr_bytes  — 0x7F bytes at ROM 0x6E14: one pointer (frame buffer index) per slot.
    frame_bytes — 0xCC bytes at ROM 0x6E93: tile codes for all animation frames.

    Slot layout:
      slot 0          = player (Link)
      slots 1-0x53    = Enemy enum values 0x00-0x52 (slot = enemy_id + 1)
      slots 0x54-0x7E = overworld NPC sprite variants (43 entries)

    Frame list length for a pointer p = (next higher unique pointer value) - p.
    Multiple slots may share the same pointer; the frame list length is determined
    by sorted unique pointer values, not by adjacent slot order.
    """
    # Build a lookup: pointer value -> tile list, using sorted unique pointer values.
    unique_ptrs = sorted(set(ptr_bytes))
    ptr_to_tiles: dict[int, list[int]] = {}
    for i, p in enumerate(unique_ptrs):
        end = unique_ptrs[i + 1] if i + 1 < len(unique_ptrs) else len(frame_bytes)
        ptr_to_tiles[p] = list(frame_bytes[p:end])

    # Slot 0: player
    player_pointer = ptr_bytes[0]
    player_tiles   = ptr_to_tiles[player_pointer]

    # Slots 1-0x53: enemy enum entries
    tile_pointers: dict[Enemy, int]        = {}
    tile_frames:   dict[Enemy, list[int]]  = {}
    for enemy in _TILE_TABLE_ENEMIES:
        slot = enemy.value + 1
        tile_pointers[enemy] = ptr_bytes[slot]
        tile_frames[enemy]   = ptr_to_tiles[ptr_bytes[slot]]

    # Slots 0x54-0x7E: overworld NPC sprite variants
    overworld_npc_pointers: list[int]         = []
    overworld_npc_frames:   list[list[int]]   = []
    for i in range(_OVERWORLD_NPC_SLOT_COUNT):
        slot = 0x54 + i
        overworld_npc_pointers.append(ptr_bytes[slot])
        overworld_npc_frames.append(ptr_to_tiles[ptr_bytes[slot]])

    return EnemyData(
        player_pointer          = player_pointer,
        player_tiles            = player_tiles,
        tile_pointers           = tile_pointers,
        tile_frames             = tile_frames,
        overworld_npc_pointers  = overworld_npc_pointers,
        overworld_npc_frames    = overworld_npc_frames,
    )


def _read_hp_nibble(table: bytes, nibble_index: int) -> int:
    """Read a single HP nibble from a packed byte table.

    Even indices are stored in the high nibble, odd indices in the low nibble.
    """
    byte_val = table[nibble_index >> 1]
    if nibble_index & 1 == 0:
        return (byte_val >> 4) & 0x0F
    return byte_val & 0x0F


def _parse_enemy_hp(bins: RawBinFiles, enemies: EnemyData) -> None:
    """Populate EnemyData.hp and secondary boss HP fields from raw bin data."""
    # Enemy HP table: 52 nibbles, Enemy 0x00-0x33
    for i in range(ENEMY_HP_NIBBLE_COUNT):
        enemy_val = i
        try:
            enemy = Enemy(enemy_val)
        except ValueError:
            continue
        enemies.hp[enemy] = _read_hp_nibble(bins.enemy_hp_table, i)

    # Boss HP table: 24 nibbles, Enemy 0x34-0x4B
    for j in range(BOSS_HP_NIBBLE_COUNT):
        enemy_val = BOSS_HP_FIRST_ENEMY_VALUE + j
        try:
            enemy = Enemy(enemy_val)
        except ValueError:
            continue
        enemies.hp[enemy] = _read_hp_nibble(bins.boss_hp_table, j)

    # Secondary boss HP bytes (HP stored in high nibble)
    enemies.aquamentus_hp = (bins.aquamentus_hp[0] >> 4) & 0x0F
    enemies.aquamentus_sp = (bins.aquamentus_sp[0] >> 4) & 0x0F
    enemies.ganon_hp      = (bins.ganon_hp[0] >> 4) & 0x0F
    enemies.gleeok_hp     = (bins.gleeok_hp[0] >> 4) & 0x0F
    enemies.patra_hp      = (bins.patra_hp[0] >> 4) & 0x0F


# ---------------------------------------------------------------------------
# Top-level parse
# ---------------------------------------------------------------------------

def parse_game_world(bins: RawBinFiles) -> GameWorld:
    mixed_groups = _parse_mixed_enemy_groups(bins)

    levels: list[Level] = []

    for level_num in range(1, 7):
        levels.append(_parse_level(
            level_num=level_num,
            grid_data=bins.level_1_6_data,
            level_index=level_num - 1,
            bins=bins,
            mixed_groups=mixed_groups,
        ))

    for level_num in range(7, 10):
        levels.append(_parse_level(
            level_num=level_num,
            grid_data=bins.level_7_9_data,
            level_index=level_num - 7,
            bins=bins,
            mixed_groups=mixed_groups,
        ))

    overworld = _parse_overworld(bins, mixed_groups)
    quotes    = _parse_quotes(bins.quotes_data) if bins.quotes_data else []

    sprites = SpriteData(
        enemy_set_a    = bytearray(bins.enemy_set_a_sprites),
        enemy_set_b    = bytearray(bins.enemy_set_b_sprites),
        enemy_set_c    = bytearray(bins.enemy_set_c_sprites),
        ow_sprites     = bytearray(bins.ow_sprites),
        boss_set_a     = bytearray(bins.boss_set_a_sprites),
        boss_set_b     = bytearray(bins.boss_set_b_sprites),
        boss_set_c     = bytearray(bins.boss_set_c_sprites),
        boss_set_expansion = bytearray(bins.boss_set_expansion_sprites) if bins.boss_set_expansion_sprites else bytearray(BOSS_SET_EXPANSION_SPRITES_SIZE),
        dungeon_common = bytearray(bins.dungeon_common_sprites),
    )

    enemies = _parse_enemy_tile_data(bins.tile_mapping_pointers, bins.tile_mapping_data)
    _parse_enemy_hp(bins, enemies)

    return GameWorld(
        overworld=overworld,
        levels=levels,
        quotes=quotes,
        sprites=sprites,
        enemies=enemies,
    )
