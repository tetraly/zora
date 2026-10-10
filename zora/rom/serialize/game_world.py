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
from ...model.game_world import GameWorld
from .. import person_code
from ..base_rom import piece_bytes
from ..code_patches import OVERWORLD_START_Y
from ..game_config import GameConfig, HintMode
from ..layout import (
    ANY_ROAD_SCREENS_ADDRESS,
    ARMOS_TABLES_ADDRESS,
    BOSS_SET_A_SPRITES_ADDRESS,
    BOSS_SET_B_SPRITES_ADDRESS,
    BOSS_SET_C_SPRITES_ADDRESS,
    BOSS_SET_EXPANSION_SPRITES_ADDRESS,
    BOSS_SPRITE_SET_POINTERS_ADDRESS,
    DUNGEON_COMMON_SPRITES_ADDRESS,
    ENEMY_SET_A_SPRITES_ADDRESS,
    ENEMY_SET_B_SPRITES_ADDRESS,
    ENEMY_SET_C_SPRITES_ADDRESS,
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
    RECORDER_WARP_DESTINATIONS_ADDRESS,
    RECORDER_WARP_Y_COORDINATES_ADDRESS,
    START_POSITION_Y_ADDRESS,
    START_SCREEN_ADDRESS,
    TILE_MAPPING_DATA_ADDRESS,
    TILE_MAPPING_POINTERS_ADDRESS,
)
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
    trips — or $0E for the ZORA remap, which also needs the engine sentinel
    patch: a final ROM step, zora/rom/final_steps.py, as are the code
    patches, the level encoding and the seed's code).

    start_y_in_patch: where the overworld start Y goes (FP-ENTR-01): the
    code patches' own byte, or LevelInfo_StartY. Default: the patch byte
    exactly when the code patches are written (GameConfig.features_b10).
    """
    patch = Patch()
    cfg = config or GameConfig()
    if start_y_in_patch is None:
        start_y_in_patch = cfg.features_b10
    _serialize_levels(game_world, original_bins_bytes, cfg, patch)
    _serialize_overworld_data(game_world, original_bins_bytes, cfg, start_y_in_patch, patch)
    _serialize_sprites_and_enemies(game_world, patch)
    _serialize_hints(game_world, patch, hint_mode)
    _serialize_person_code(game_world, cfg, hint_mode, patch)
    return patch


def _serialize_levels(game_world: GameWorld, original_bins_bytes: dict[str, bytes], cfg: GameConfig,
                      patch: Patch) -> None:
    """Every room of both quest-1 blocks, from the model, and the levels' level-information blocks."""
    nothing_code = cfg.dungeon_nothing_code.value
    patch.add(LEVEL_1_6_DATA_ADDRESS, encode_level_block(game_world.blocks[0], nothing_code))
    patch.add(LEVEL_7_9_DATA_ADDRESS, encode_level_block(game_world.blocks[1], nothing_code))
    level_info = bytearray(original_bins_bytes["level_info.bin"])
    for lvl in game_world.levels:
        offset = lvl.level_num * LEVEL_INFO_SIZE
        block_arr = bytearray(level_info[offset:offset + LEVEL_INFO_SIZE])
        _serialize_level_info(lvl, block_arr)
        level_info[offset:offset + LEVEL_INFO_SIZE] = block_arr
    patch.add(LEVEL_INFO_ADDRESS, bytes(level_info))


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
    _serialize_new_file_hearts(game_world, patch)
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
                                            game_world.starting_hearts):
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


def serialize_game_world_q2(game_world: GameWorld, original_bins_bytes: dict[str, bytes],
                            config: GameConfig | None = None) -> Patch:
    """Produce a Patch for the second-quest level grids only.

    Note: the 2Q level_info block is not stored directly in the ROM (it is 1Q
    level_info patched by the "various data" tables, rebuilt at parse time by
    _build_level_info_q2_from_rom). There is therefore no valid ROM destination
    for serialized 2Q level_info, and the previous version of this function
    wrote it over the 1Q block — a latent bug. Grids use game_world.blocks_2q,
    not levels. QUESTIONS.md #13.
    """
    patch = Patch()
    cfg = config or GameConfig()
    if cfg.level_encoding is not None:
        # The second-quest blocks hold the level encoding's key material.
        raise ValueError("second-quest level blocks cannot be written with level encoding on")
    nothing_code = cfg.dungeon_nothing_code.value

    patch.add(LEVEL_1_6_DATA_ADDRESS_Q2,
              encode_level_block(game_world.blocks_2q[0], nothing_code))
    patch.add(LEVEL_7_9_DATA_ADDRESS_Q2,
              encode_level_block(game_world.blocks_2q[1], nothing_code))

    return patch
