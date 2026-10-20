"""
Serializer: GameWorld → Patch

Converts a GameWorld data model back to a ROM Patch. Call serialize_game_world()
to produce a Patch, then Patch.apply() to write it into a ROM bytearray.

Covers all parsed ROM regions:
- Level grids (levels 1-9): room walls, enemies, items, room types
- Level info blocks: palette, qty table, metadata, stairway data
- Overworld screens: destinations, exits, enemy flags, quest visibility
- Cave item + price data (20 caves): shops, take-any, rupee values, door repair
- Cave quote ID table (20 bytes): quote_id per cave slot
- Hint shop slot quote ID table (6 bytes): quote_id per hint shop slot
- Sprite set pointer tables (bank 3): enemy + boss pattern block assignments
- Recorder warp destinations + Y coordinates
- Any-road shortcut screens + start screen
- Armos/coast items, white/magical sword heart requirements
- MMG win/lose prize amounts (9 patch locations)
- Bomb upgrade cost, count, and display tiles
- Quotes (38 hints): pointer table + encoded text
"""
from ...model.enums import DungeonNothingCode
from ...model.game_world import GameWorld
from .. import person_code
from ..base_rom import piece_bytes
from ..code_patches import (
    EXIT_ROOM_COUNT_FLAG,
    LEVEL_INFO_ARRIVAL_CODE,
    LEVEL_INFO_EXIT_ROOM_COUNT,
    OVERWORLD_START_Y,
    START_ITEMS_TABLE,
)
from ..game_config import GameConfig, HintMode
from ..layout import (
    ANY_ROAD_SCREENS_ADDRESS,
    ARMOS_TABLES_ADDRESS,
    ASM_NOTHING_CODE_PATCH_OFFSET,
    ASM_NOTHING_CODE_PATCH_VALUE,
    BEQ_OPCODE,
    BNE_OPCODE,
    BOSS_SET_A_SPRITES_ADDRESS,
    BOSS_SET_B_SPRITES_ADDRESS,
    BOSS_SET_C_SPRITES_ADDRESS,
    BOSS_SET_EXPANSION_SPRITES_ADDRESS,
    BOSS_SPRITE_SET_POINTERS_ADDRESS,
    DUNGEON_COMMON_SPRITES_ADDRESS,
    ENEMY_SET_A_SPRITES_ADDRESS,
    ENEMY_SET_B_SPRITES_ADDRESS,
    ENEMY_SET_C_SPRITES_ADDRESS,
    FLUTE_ROOM_SECRETS_OW_ADDRESS,
    FLUTE_SECRET_QUEST_BRANCH_ADDRESS,
    ITEM_CARRIER_OPERAND_ADDRESSES,
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS_Q2,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS_Q2,
    LEVEL_INFO_ADDRESS,
    LEVEL_INFO_SIZE,
    LEVEL_SPRITE_SET_POINTERS_ADDRESS,
    MAZE_DIRECTIONS_ADDRESS,
    MIXED_ENEMY_DATA_ADDRESS,
    OBJECT_TYPE_OPERAND_873D_ADDRESS,
    OVERWORLD_DATA_ADDRESS,
    OVERWORLD_WIZZROBE_PATCH,
    OW_SPRITES_ADDRESS,
    QUEST_MONSTER_BRANCH_ADDRESSES,
    RECORDER_WARP_DESTINATIONS_ADDRESS,
    RECORDER_WARP_Y_COORDINATES_ADDRESS,
    ROOM_BLOCK_ADDRESSES_Q1,
    ROOM_BLOCK_HIGH_BYTES,
    START_POSITION_Y_ADDRESS,
    START_SCREEN_ADDRESS,
    TILE_MAPPING_DATA_ADDRESS,
    TILE_MAPPING_POINTERS_ADDRESS,
)
from ..start_items import start_table
from .caves import _serialize_bomb_upgrade, _serialize_cave_data, _serialize_mmg_prizes
from .enemies import _serialize_enemy_hp, _serialize_enemy_tile_data
from .features import (
    _serialize_b10_constants,
    _serialize_credits,
    _serialize_new_file_hearts,
    _serialize_refusal_text,
    _serialize_title,
)
from .levels import (
    _serialize_level_info,
    _serialize_sprite_set_pointers,
    encode_level_block,
)
from .overworld import _serialize_overworld
from .patch import Patch
from .text import _serialize_hints

# ---------------------------------------------------------------------------
# Top-level serialize
# ---------------------------------------------------------------------------

def serialize_game_world(game_world: GameWorld, original_bins_bytes: dict[str, bytes],
                         hint_mode: HintMode = HintMode.VANILLA,
                         config: GameConfig | None = None, start_y_in_patch: bool | None = None) -> Patch:
    """
    Produce a Patch from a GameWorld.

    original_bins_bytes: dict mapping bin filename → bytes, used to initialize
    output buffers with original data before overwriting changed fields.

    config: game-serialization settings. GameConfig.dungeon_nothing_code
    selects the ROM byte encoding for the Item.NOTHING meaning in dungeon
    rooms ($03 vanilla — the Consternation preset, byte-identical round
    trips — or $0E for the ZORA remap); the engine's sentinel byte is the
    model's (GameWorld.dungeon_nothing_code). The code patches, the level
    encoding and the seed's code are final ROM steps (zora/rom/final_steps.py).

    start_y_in_patch: where the overworld start Y goes (FP-ENTR-01): the
    code patches' own byte, or LevelInfo_StartY. Default: the patch byte
    exactly when the code patches are written (GameConfig.features_b10).
    """
    patch = Patch()
    cfg = config or GameConfig()
    if start_y_in_patch is None:
        start_y_in_patch = cfg.features_b10
    _serialize_levels(game_world, original_bins_bytes, cfg, patch)
    if game_world.dungeon_nothing_code is DungeonNothingCode.ZORA_REMAP:
        # the engine's sentinel comparison reads $0E, so $03 can be the magical sword in dungeons
        patch.add(ASM_NOTHING_CODE_PATCH_OFFSET, bytes([ASM_NOTHING_CODE_PATCH_VALUE]))
    _serialize_overworld_data(game_world, original_bins_bytes, cfg, start_y_in_patch, patch)
    _serialize_sprites_and_enemies(game_world, patch)
    _serialize_hints(game_world, patch, hint_mode)
    _serialize_person_code(game_world, cfg, hint_mode, patch)
    return patch


def _serialize_levels(game_world: GameWorld, original_bins_bytes: dict[str, bytes], cfg: GameConfig,
                      patch: Patch) -> None:
    """Every room of the four room blocks, from the model, the block each level points at
    (SH-SRC-02), the quest-number branches (SH-SRC-05) and the levels' level-information
    blocks."""
    nothing_code = cfg.dungeon_nothing_code.value
    patch.add(LEVEL_1_6_DATA_ADDRESS, encode_level_block(game_world.blocks[0], nothing_code))
    patch.add(LEVEL_7_9_DATA_ADDRESS, encode_level_block(game_world.blocks[1], nothing_code))
    # A second-quest block is written only when a level reads it from its own slot: an unread one
    # keeps the base ROM's bytes, PRG0's nothing code included. With level encoding on, a read one
    # is stored in its set's first-quest slot instead (GameWorld.store_second_quest_sets_in_first_quest_slots),
    # which the levels then point at, and its own slot keeps the base ROM's bytes: the encoding
    # (a final step) takes the second-quest blocks' space for itself, whatever they hold.
    for address, block in zip((LEVEL_1_6_DATA_ADDRESS_Q2, LEVEL_7_9_DATA_ADDRESS_Q2), game_world.blocks_2q,
                              strict=True):
        if not any(lvl.block is block for lvl in game_world.levels) or any(stored is block
                                                                           for stored in game_world.blocks):
            continue
        if cfg.level_encoding is not None:
            raise ValueError("level encoding needs each second-quest set stored in its first-quest slot "
                             "(GameWorld.store_second_quest_sets_in_first_quest_slots)")
        patch.add(address, encode_level_block(block, nothing_code))
    # the first slot holding the level's block names it: a first-quest slot before a second-quest one
    blocks = [*game_world.blocks, *game_world.blocks_2q]
    for lvl in game_world.levels:
        block_index = next(index for index, block in enumerate(blocks) if block is lvl.block)
        patch.add(ROOM_BLOCK_ADDRESSES_Q1 + 2 * lvl.level_num + 1, bytes([ROOM_BLOCK_HIGH_BYTES[block_index]]))
    branch = BNE_OPCODE if game_world.monsters_take_second_quest_path else BEQ_OPCODE
    for address in QUEST_MONSTER_BRANCH_ADDRESSES:
        patch.add(address, bytes([branch]))
    level_info = bytearray(original_bins_bytes["level_info.bin"])
    for lvl in game_world.levels:
        offset = lvl.level_num * LEVEL_INFO_SIZE
        block_arr = bytearray(level_info[offset:offset + LEVEL_INFO_SIZE])
        _serialize_level_info(lvl, block_arr)
        level_info[offset:offset + LEVEL_INFO_SIZE] = block_arr
    if cfg.features_b10:
        _serialize_level_entry_codes(game_world, level_info)
    patch.add(LEVEL_INFO_ADDRESS, bytes(level_info))


def _serialize_level_entry_codes(game_world: GameWorld, level_info: bytearray) -> None:
    """FP-ENTR-01 and FP-ENTR-02, written with ZORA's code patches, which read them: each level's
    exit room with bit 7 set (+$23) and arrival code (+$3D), and the overworld's arrival code
    (GameWorld.record_level_entry_codes; a parsed ROM carries them as written)."""
    unset = [lvl.level_num for lvl in game_world.levels if lvl.exit_room is None or lvl.arrival_code is None]
    if unset or game_world.overworld_arrival_code is None:
        raise ValueError(f"the code patches need every level's entry codes (levels {unset} and the overworld: "
                         "GameWorld.record_level_entry_codes)")
    for lvl in game_world.levels:
        offset = lvl.level_num * LEVEL_INFO_SIZE
        assert lvl.exit_room is not None and lvl.arrival_code is not None
        level_info[offset + LEVEL_INFO_EXIT_ROOM_COUNT] = lvl.exit_room | EXIT_ROOM_COUNT_FLAG
        level_info[offset + LEVEL_INFO_ARRIVAL_CODE] = lvl.arrival_code
    level_info[LEVEL_INFO_ARRIVAL_CODE] = game_world.overworld_arrival_code


def _serialize_overworld_data(game_world: GameWorld, original_bins_bytes: dict[str, bytes], cfg: GameConfig,
                              start_y_in_patch: bool, patch: Patch) -> None:
    """The overworld screens, the caves, the money-making game and bomb upgrade,
    B10's DATA items and the overworld's own tables."""
    grid_ow = bytearray(original_bins_bytes["overworld_data.bin"])
    _serialize_overworld(game_world.overworld, grid_ow)
    patch.add(OVERWORLD_DATA_ADDRESS, bytes(grid_ow))
    # cave data: items, prices, door repair, armos, coast, heart requirements, quote tables
    _serialize_cave_data(game_world.overworld, patch)
    _serialize_mmg_prizes(game_world.overworld, patch)
    _serialize_bomb_upgrade(game_world.overworld, patch)
    _serialize_new_file_hearts(game_world, patch, start_table_written=cfg.features_b10 and game_world.uses_start_table)
    if cfg.features_b10 and game_world.uses_start_table:
        # FP-START-03: fp-start-02's table, with the start hearts and pieces (the patch's own copy is
        # PRG0's start, so the code patches carry this table too: code_patches.seed_data)
        patch.add(START_ITEMS_TABLE, start_table(game_world.start_items, game_world.new_file_heart_containers,
                                                 game_world.new_file_full_hearts, game_world.start_triforce_pieces))
    if cfg.features_b10:
        _serialize_b10_constants(game_world, patch)
        _serialize_credits(game_world, patch)
        _serialize_title(game_world, patch)

    ow = game_world.overworld
    patch.add(ARMOS_TABLES_ADDRESS, bytes(ow.armos_screen_ids) + bytes(ow.armos_positions))
    maze_bytes = bytes([d.value for d in ow.dead_woods_directions]) \
        + bytes([d.value for d in ow.lost_hills_directions])
    patch.add(MAZE_DIRECTIONS_ADDRESS, maze_bytes)
    patch.add(RECORDER_WARP_DESTINATIONS_ADDRESS,  bytes(ow.recorder_warp_destinations))
    patch.add(RECORDER_WARP_Y_COORDINATES_ADDRESS, bytes(ow.recorder_warp_y_coordinates))
    patch.add(ANY_ROAD_SCREENS_ADDRESS,            bytes(ow.any_road_screens))
    patch.add(FLUTE_ROOM_SECRETS_OW_ADDRESS,       bytes(ow.recorder_secret_screens))
    patch.add(FLUTE_SECRET_QUEST_BRANCH_ADDRESS,
              bytes([BNE_OPCODE if ow.recorder_reveals_listed_secrets_in_first_quest else BEQ_OPCODE]))
    patch.add(START_SCREEN_ADDRESS,                bytes([ow.start_screen]))
    if start_y_in_patch:
        # With the code patches, FP-ENTR-01 reads the start Y from its own
        # byte and LevelInfo_StartY keeps PRG0's value.
        patch.add(OVERWORLD_START_Y, bytes([ow.start_position_y]))
    else:
        patch.add(START_POSITION_Y_ADDRESS, bytes([ow.start_position_y]))


def _serialize_sprites_and_enemies(game_world: GameWorld, patch: Patch) -> None:
    """The sprite set pointer tables, the sprite data blocks, the enemy tile
    maps, the enemy and boss hit points and the mixed enemy groups."""
    level_ptrs, boss_ptrs = _serialize_sprite_set_pointers(game_world)
    patch.add(LEVEL_SPRITE_SET_POINTERS_ADDRESS, level_ptrs)
    patch.add(BOSS_SPRITE_SET_POINTERS_ADDRESS,  boss_ptrs)
    sp = game_world.sprites
    patch.add(OW_SPRITES_ADDRESS,              sp.ow_sprites)
    patch.add(ENEMY_SET_B_SPRITES_ADDRESS,    sp.enemy_set_b)
    patch.add(ENEMY_SET_C_SPRITES_ADDRESS,    sp.enemy_set_c)
    patch.add(DUNGEON_COMMON_SPRITES_ADDRESS, sp.dungeon_common)
    patch.add(ENEMY_SET_A_SPRITES_ADDRESS,    sp.enemy_set_a)
    patch.add(BOSS_SET_A_SPRITES_ADDRESS,     sp.boss_set_a)
    patch.add(BOSS_SET_B_SPRITES_ADDRESS,     sp.boss_set_b)
    patch.add(BOSS_SET_C_SPRITES_ADDRESS,     sp.boss_set_c)
    patch.add(BOSS_SET_EXPANSION_SPRITES_ADDRESS, sp.boss_set_expansion)
    ptr_bytes, frame_bytes = _serialize_enemy_tile_data(game_world)
    patch.add(TILE_MAPPING_POINTERS_ADDRESS, ptr_bytes)
    patch.add(TILE_MAPPING_DATA_ADDRESS,     frame_bytes)
    _serialize_enemy_hp(game_world, patch)
    if game_world.enemies.mixed_enemy_data:
        patch.add(MIXED_ENEMY_DATA_ADDRESS,
                  bytes(game_world.enemies.mixed_enemy_data))


def _serialize_person_code(game_world: GameWorld, cfg: GameConfig, hint_mode: HintMode, patch: Patch) -> None:
    """The life-or-money toll and bomb-upgrade person code (PS-MERCH-04,
    PS-BOMB-03; the text pointer lies inside the quotes block, so this goes
    after the quotes), the level-9 refusal text, the person inits and the
    group passes' operand bytes (PS-EGRP-05/-06)."""
    for address, data in person_code.encode(game_world.life_or_money_toll,
                                            game_world.bomb_upgrade_levels,
                                            game_world.new_file_heart_containers):
        patch.add(address, data)
    for address, data in person_code.text_pointer_write(game_world.life_or_money_toll):
        patch.add(address, data)
    if cfg.features_b10 and hint_mode == HintMode.CONSTERNATION:
        _serialize_refusal_text(game_world, patch)
    for address, data in person_code.person_init_writes(game_world.person_inits):
        patch.add(address, data)
    for address, value in zip(ITEM_CARRIER_OPERAND_ADDRESSES, game_world.item_carrier_operands, strict=True):
        patch.add(address, bytes([value]))
    patch.add(OBJECT_TYPE_OPERAND_873D_ADDRESS, bytes([game_world.object_type_operand_873d]))
    if game_world.overworld_wizzrobe_patch:
        for address, piece in OVERWORLD_WIZZROBE_PATCH:
            patch.add(address, piece_bytes(piece))
