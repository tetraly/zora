"""The ROM's raw tables, sliced out of a ROM file (RawBinFiles)."""

from dataclasses import dataclass

from ..base_rom import piece_bytes
from ..layout import (
    ANY_ROAD_SCREENS_ADDRESS,
    AQUAMENTUS_SPRITE_PTR_ADDRESS,
    AQUAMENTUS_TILE_LAYOUT_TABLE_ADDRESS,
    AQUAMENTUS_TILE_LAYOUT_TABLE_SIZE,
    ARMOS_ITEM_ADDRESS,
    ARMOS_TABLES_ADDRESS,
    BOMB_COST_OFFSET,
    BOMB_COUNT_OFFSET,
    BOSS_HP_TABLE_ADDRESS,
    BOSS_HP_TABLE_SIZE,
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
    CAVE_PRICE_DATA_ADDRESS,
    CAVE_QUOTES_DATA_ADDRESS,
    COAST_ITEM_ADDRESS,
    CONTINUE_HEARTS_OPERAND_ADDRESS,
    DOOR_REPAIR_CHARGE_ADDRESS,
    DUNGEON_COMMON_SPRITES_ADDRESS,
    DUNGEON_COMMON_SPRITES_SIZE,
    DUNGEON_VARIOUS_DATA_Q2_BANK6_CPU,
    DUNGEON_VARIOUS_DATA_Q2_BANK6_FILE,
    DUNGEON_VARIOUS_DATA_Q2_INFO_OFFSET,
    DUNGEON_VARIOUS_DATA_Q2_LEN_TABLE,
    DUNGEON_VARIOUS_DATA_Q2_PTR_TABLE,
    ENEMY_HP_TABLE_ADDRESS,
    ENEMY_HP_TABLE_SIZE,
    ENEMY_SET_A_SPRITES_ADDRESS,
    ENEMY_SET_A_SPRITES_SIZE,
    ENEMY_SET_B_SPRITES_ADDRESS,
    ENEMY_SET_B_SPRITES_SIZE,
    ENEMY_SET_C_SPRITES_ADDRESS,
    ENEMY_SET_C_SPRITES_SIZE,
    GANON_HP_ADDRESS,
    GLEEOK_BODY_TILES_ADDRESS,
    GLEEOK_BODY_TILES_SIZE,
    GLEEOK_HEAD_HP_ADDRESS,
    GLEEOK_HEAD_SPRITE_PTR_A_ADDRESS,
    GLEEOK_HEAD_SPRITE_PTR_B_ADDRESS,
    GLEEOK_HEAD_SPRITE_PTR_C_ADDRESS,
    GLEEOK_NECK_HP_ADDRESS,
    HINT_SHOP_QUOTES_ADDRESS,
    ITEM_CARRIER_OPERAND_ADDRESSES,
    LAMNOLA_SEGMENT_HP_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS_Q2,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS_Q2,
    LEVEL_INFO_ADDRESS,
    LEVEL_INFO_SIZE,
    LEVEL_SPRITE_SET_POINTERS_ADDRESS,
    LIFE_OR_MONEY_PAYMENT_ADDRESS,
    LIFE_OR_MONEY_PAYMENT_SIZE,
    MAGICAL_SWORD_REQUIREMENT_ADDRESS,
    MAZE_DIRECTIONS_ADDRESS,
    MIXED_ENEMY_DATA_ADDRESS,
    MIXED_ENEMY_DATA_SIZE,
    MIXED_ENEMY_POINTER_TABLE_ADDRESS,
    MMG_LOSE_LARGE_OFFSET,
    MMG_LOSE_SMALL_2_OFFSET,
    MMG_LOSE_SMALL_OFFSET,
    MMG_WIN_LARGE_OFFSET_A,
    MMG_WIN_SMALL_OFFSET_A,
    MOLDORM_SEGMENT_HP_ADDRESS,
    NES_HEADER_SIZE,
    OBJECT_TYPE_OPERAND_873D_ADDRESS,
    OVERWORLD_DATA_ADDRESS,
    OVERWORLD_WIZZROBE_PATCH,
    OW_SPRITES_ADDRESS,
    OW_SPRITES_SIZE,
    PERSON_INIT_JUMP_TABLE_ADDRESS,
    PERSON_INIT_JUMP_TABLE_SIZE,
    PERSON_UPDATE_BRANCH_ADDRESS,
    PERSON_UPDATE_BRANCH_SIZE,
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
    ROPE_HP_OPERAND_ADDRESSES,
    START_HEARTS_ADDRESS,
    START_POSITION_Y_ADDRESS,
    START_SCREEN_ADDRESS,
    TILE_MAPPING_DATA_ADDRESS,
    TILE_MAPPING_DATA_SIZE,
    TILE_MAPPING_POINTERS_ADDRESS,
    TILE_MAPPING_POINTERS_SIZE,
    TITLE_VERSION_OFFSET,
    UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE,
    WHITE_SWORD_REQUIREMENT_ADDRESS,
)


@dataclass
class RawBinFiles:
    level_1_6_data:       bytes   # 0x300 bytes
    level_7_9_data:       bytes   # 0x300 bytes
    level_info:           bytes   # 0xA * 0xFC bytes
    level_1_6_data_q2:   bytes   # 0x300 bytes
    level_7_9_data_q2:   bytes   # 0x300 bytes
    level_info_q2:        bytes   # 0xA * 0xFC bytes, patched from 1Q
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
    enemy_hp_table:               bytes   # 26 bytes at 0x1FB5E: ObjectTypeToHpPairs bytes 0-25
    boss_hp_table:                bytes   # 12 bytes at 0x1FB78: ObjectTypeToHpPairs bytes 26-37
    # Secondary boss HP bytes (single bytes, HP in high nibble)
    gleeok_neck_hp:               bytes   # 1 byte at 0x120C6: Gleeok neck HP (InitGleeok)
    gleeok_head_hp:               bytes   # 1 byte at 0x12735: Gleeok flying-head HP (Gleeok_CheckCollisions)
    ganon_hp:                     bytes   # 1 byte at 0x12F27: Ganon HP (Ganon_CheckCollisions)
    moldorm_segment_hp:           bytes   # 1 byte at 0x114D5: Moldorm segment HP (UpdateMoldorm)
    lamnola_segment_hp:           bytes   # 1 byte at 0x12A45: Lanmola segment HP (UpdateLamnola)
    # Boss engine sprite pointers (single bytes)
    aquamentus_sprite_ptr:        bytes   # 1 byte at 0x11898 (71832)
    gleeok_head_sprite_ptr_a:     bytes   # 1 byte at 0x126F8 (75512)
    gleeok_head_sprite_ptr_b:     bytes   # 1 byte at 0x126FE (75518)
    gleeok_head_sprite_ptr_c:     bytes   # 1 byte at 0x6F5A  (28506)
    # Player (Link) sprite banks
    player_main_sprites:              bytes  # 0x1C0 bytes at 0x808F
    player_cheer_sprites:             bytes  # 0x20 bytes at 0x4E44
    player_big_shield_profile_sprites: bytes # 0x20 bytes at 0x4EC4
    player_profile_no_shield_sprites: bytes  # 0x20 bytes at 0x85CF
    player_small_shield_sprites:      bytes  # 0x40 bytes at 0x860F
    player_large_shield_sprites:      bytes  # 0x20 bytes at 0x868F
    # Life-or-money toll / bomb-upgrade person code bytes (PS-MERCH-04,
    # PS-BOMB-03).
    person_update_branch:     bytes = b""   # 8 bytes at 0x04AED
    person_init_jump_table:   bytes = b""   # 20 bytes at 0x04A17
    life_or_money_payment:    bytes = b""   # 0x21 bytes at 0x04C1C
    start_hearts:             bytes = b""   # 1 byte at 0x0A868
    continue_hearts_operand:  bytes = b""   # 1 byte at 0x14B83
    # Hint-text selector tables (hints-behavior.md HT-SEL-01).
    underworld_text_selectors_a: bytes = b""  # 8 bytes at 0x4A2B
    underworld_text_selectors_b: bytes = b""  # 8 bytes at 0x4A71
    # Group-pass bytes (post-shapes-b4/b5.md).
    aquamentus_tiles:         bytes = b""   # 12 bytes at 0x11844 (AquamentusTiles)
    gleeok_body_tiles:        bytes = b""   # 18 bytes at 0x12819 (GleeokBodyTiles0-2)
    item_carrier_operands:    bytes = b""   # 0x1E70F, 0x1E713, 0x1E717
    rope_hp_operands:         bytes = b""   # 0x112D3, 0x112DF (InitRope)
    overworld_wizzrobe_patch: bool = False  # all four PS-EGRP-05 runs present
    object_type_operand_873d: bytes = b""   # 1 byte at 0x0474D


# iNES header (16 bytes) + 128 KB PRG ROM = 131088 bytes exactly.
_NES_ROM_SIZE = NES_HEADER_SIZE + 0x20000
_NES_MAGIC    = b"NES\x1a"



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


def _build_level_info_q2_from_rom(rom_bytes: bytes) -> bytes:
    """Derive 2Q level_info bytes by patching 1Q level_info with the ROM's 2Q Various Data.

    The ROM stores compact patch blocks for each 2Q dungeon at addresses listed in a
    pointer table (DUNGEON_VARIOUS_DATA_Q2_PTR_TABLE).  Each block replaces bytes in
    the level_info starting at offset +DUNGEON_VARIOUS_DATA_Q2_INFO_OFFSET (+0x29).
    The block length is given by DUNGEON_VARIOUS_DATA_Q2_LEN_TABLE.
    """
    level_info_q2 = bytearray(rom_bytes[LEVEL_INFO_ADDRESS: LEVEL_INFO_ADDRESS + 0xA * LEVEL_INFO_SIZE])

    for i in range(9):
        level_num = i + 1
        ptr_off  = DUNGEON_VARIOUS_DATA_Q2_PTR_TABLE + i * 2
        cpu_addr = rom_bytes[ptr_off] | (rom_bytes[ptr_off + 1] << 8)
        file_off = DUNGEON_VARIOUS_DATA_Q2_BANK6_FILE + (cpu_addr - DUNGEON_VARIOUS_DATA_Q2_BANK6_CPU)
        length   = rom_bytes[DUNGEON_VARIOUS_DATA_Q2_LEN_TABLE + i]

        patch = rom_bytes[file_off: file_off + length]
        dest  = level_num * LEVEL_INFO_SIZE + DUNGEON_VARIOUS_DATA_Q2_INFO_OFFSET
        level_info_q2[dest: dest + length] = patch

    return bytes(level_info_q2)


def load_bin_files_from_rom(rom_bytes: bytes) -> RawBinFiles:
    """Build a RawBinFiles by slicing a full .nes ROM file in memory.

    The caller is responsible for validating
    the ROM with is_randomizer_rom() before calling this.
    """
    def s(addr: int, size: int) -> bytes:
        return rom_bytes[addr: addr + size]

    # FP-ENTR-01: with ZORA's code patches, the overworld start Y lives in
    # the patch's own byte (LevelInfo_StartY keeps PRG0's value).
    from ..code_patches import overworld_start_y
    patched_start_y = overworld_start_y(rom_bytes)
    start_position_y = (s(START_POSITION_Y_ADDRESS, 1) if patched_start_y is None
                        else bytes([patched_start_y]))

    return RawBinFiles(
        level_1_6_data              = s(LEVEL_1_6_DATA_ADDRESS,              0x300),
        level_7_9_data              = s(LEVEL_7_9_DATA_ADDRESS,              0x300),
        level_info                  = s(LEVEL_INFO_ADDRESS,                  0xA * 0xFC),
        level_1_6_data_q2           = s(LEVEL_1_6_DATA_ADDRESS_Q2,           0x300),
        level_7_9_data_q2           = s(LEVEL_7_9_DATA_ADDRESS_Q2,           0x300),
        level_info_q2               = _build_level_info_q2_from_rom(rom_bytes),
        level_pointers              = b"",
        overworld_data              = s(OVERWORLD_DATA_ADDRESS,              0x300),
        mixed_enemy_data            = s(MIXED_ENEMY_DATA_ADDRESS,            MIXED_ENEMY_DATA_SIZE),
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
        start_position_y            = start_position_y,
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
        gleeok_neck_hp              = s(GLEEOK_NECK_HP_ADDRESS,        1),
        gleeok_head_hp              = s(GLEEOK_HEAD_HP_ADDRESS,        1),
        ganon_hp                    = s(GANON_HP_ADDRESS,              1),
        moldorm_segment_hp          = s(MOLDORM_SEGMENT_HP_ADDRESS,    1),
        lamnola_segment_hp          = s(LAMNOLA_SEGMENT_HP_ADDRESS,    1),
        aquamentus_sprite_ptr       = s(AQUAMENTUS_SPRITE_PTR_ADDRESS,    1),
        gleeok_head_sprite_ptr_a    = s(GLEEOK_HEAD_SPRITE_PTR_A_ADDRESS, 1),
        gleeok_head_sprite_ptr_b    = s(GLEEOK_HEAD_SPRITE_PTR_B_ADDRESS, 1),
        gleeok_head_sprite_ptr_c    = s(GLEEOK_HEAD_SPRITE_PTR_C_ADDRESS, 1),
        player_main_sprites              = s(PLAYER_MAIN_SPRITES_ADDRESS,              PLAYER_MAIN_SPRITES_SIZE),
        player_cheer_sprites             = s(PLAYER_CHEER_SPRITES_ADDRESS,             PLAYER_CHEER_SPRITES_SIZE),
        player_big_shield_profile_sprites = s(PLAYER_BIG_SHIELD_PROFILE_SPRITES_ADDRESS,
                                              PLAYER_BIG_SHIELD_PROFILE_SPRITES_SIZE),
        player_profile_no_shield_sprites = s(PLAYER_PROFILE_NO_SHIELD_SPRITES_ADDRESS,
                                             PLAYER_PROFILE_NO_SHIELD_SPRITES_SIZE),
        player_small_shield_sprites      = s(PLAYER_SMALL_SHIELD_SPRITES_ADDRESS,
                                             PLAYER_SMALL_SHIELD_SPRITES_SIZE),
        player_large_shield_sprites      = s(PLAYER_LARGE_SHIELD_SPRITES_ADDRESS,
                                             PLAYER_LARGE_SHIELD_SPRITES_SIZE),
        person_update_branch     = s(PERSON_UPDATE_BRANCH_ADDRESS,     PERSON_UPDATE_BRANCH_SIZE),
        person_init_jump_table   = s(PERSON_INIT_JUMP_TABLE_ADDRESS,   PERSON_INIT_JUMP_TABLE_SIZE),
        life_or_money_payment    = s(LIFE_OR_MONEY_PAYMENT_ADDRESS,    LIFE_OR_MONEY_PAYMENT_SIZE),
        start_hearts             = s(START_HEARTS_ADDRESS,             1),
        continue_hearts_operand  = s(CONTINUE_HEARTS_OPERAND_ADDRESS,  1),
        underworld_text_selectors_a = s(UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS,
                                        UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE),
        underworld_text_selectors_b = s(UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS,
                                        UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE),
        aquamentus_tiles         = s(AQUAMENTUS_TILE_LAYOUT_TABLE_ADDRESS, AQUAMENTUS_TILE_LAYOUT_TABLE_SIZE),
        gleeok_body_tiles        = s(GLEEOK_BODY_TILES_ADDRESS,        GLEEOK_BODY_TILES_SIZE),
        item_carrier_operands    = bytes(rom_bytes[a] for a in ITEM_CARRIER_OPERAND_ADDRESSES),
        rope_hp_operands         = bytes(rom_bytes[a] for a in ROPE_HP_OPERAND_ADDRESSES),
        overworld_wizzrobe_patch = all(rom_bytes[a:a + len(run)] == run for a, run in
                                       ((a, piece_bytes(piece)) for a, piece in OVERWORLD_WIZZROBE_PATCH)),
        object_type_operand_873d = s(OBJECT_TYPE_OPERAND_873D_ADDRESS, 1),
    )
