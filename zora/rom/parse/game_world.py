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
  +0x30  Triforce-room pointer (locked at parse; the room re-deal pass of a
         later stage rewrites it — mid-pipeline in shapes-stage snapshots.
         Set None in the model to re-derive from room content at write)
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
from typing import Any

from ...model.enums import DungeonNothingCode
from ...model.game_world import GameWorld
from ...model.levels import Level, LevelBlock
from ...model.sprites import SpriteData
from .. import person_code
from ..game_config import GameConfig
from ..layout import (
    ASM_NOTHING_CODE_PATCH_OFFSET,
    ASM_NOTHING_CODE_PATCH_VALUE,
    BNE_OPCODE,
    BOSS_SET_EXPANSION_SPRITES_SIZE,
    DUNGEON_NOTHING_CODE,
    FIRST_MIXED_GROUP_CODE,
    HINT_SHOP_QUOTES_ADDRESS,
    LEVEL_INFO_SIZE,
    OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS,
    POINTER_COUNT,
    QUOTE_DATA_ADDRESS,
    ROOM_BLOCK_HIGH_BYTES,
    TOLL_TEXT_POINTER_ADDRESS,
)
from .bin_files import RawBinFiles
from .enemies import _parse_enemy_hp, _parse_enemy_tile_data, _parse_mixed_enemy_groups
from .features import _parse_b10_data
from .levels import _arrival_code, _parse_block, _parse_level
from .overworld import _parse_overworld
from .text import REFUSAL_SLOT, _parse_person_text, _slot_text

# ---------------------------------------------------------------------------
# Top-level parse
# ---------------------------------------------------------------------------

def parse_game_world(bins: RawBinFiles,
                     config: GameConfig | None = None,
                     rom_bytes: bytes | None = None) -> GameWorld:
    """Parse a GameWorld. `config` selects the "no item" room-byte encoding
    (game_config.DungeonNothingCode); the default is the vanilla $03
    sentinel, which keeps parse→serialize byte-identical."""
    nothing_code = config.dungeon_nothing_code.value if config is not None \
        else DUNGEON_NOTHING_CODE
    mixed_groups = _parse_mixed_enemy_groups(bins)

    def parse_block(grid: bytes) -> LevelBlock:
        return _parse_block(grid, mixed_groups, nothing_code)

    def parse_set(set_index: int, grid: bytes, block: LevelBlock, level_info: bytes) -> list[Level]:
        return [_parse_level(level_num, grid, block, bins, level_info=level_info)
                for level_num in SET_LEVELS[set_index]]

    grids_1q = (bins.level_1_6_data, bins.level_7_9_data)
    grids_2q = (bins.level_1_6_data_q2, bins.level_7_9_data_q2)
    blocks = [parse_block(grid) for grid in grids_1q]
    blocks_2q = [parse_block(grid) for grid in grids_2q]
    # SH-SRC-02: a set whose levels point at its second-quest block reads its rooms
    # there, with the level information as stored (the second-quest bytes already in
    # place, SH-SRC-03). levels_2q are PRG0's second-quest levels, each on its own copy
    # of the block when a set's levels use the block itself.
    second_quest_sets = _second_quest_sets(bins.level_pointers)
    levels: list[Level] = []
    levels_2q: list[Level] = []
    for set_index, (grid_1q, grid_2q) in enumerate(zip(grids_1q, grids_2q, strict=True)):
        second_quest = set_index in second_quest_sets
        levels += parse_set(set_index, *((grid_2q, blocks_2q[set_index]) if second_quest
                                         else (grid_1q, blocks[set_index])), bins.level_info)
        levels_2q += parse_set(set_index, grid_2q, parse_block(grid_2q) if second_quest else blocks_2q[set_index],
                               bins.level_info_q2)
        count = len(SET_LEVELS[set_index])
        for level in (levels[-count:] if second_quest else []) + levels_2q[-count:]:
            level.is_second_quest = True

    overworld = _parse_overworld(bins, mixed_groups)
    quotes, hint_pointers, hint_text_bytes = _parse_person_text(bins.quotes_data, rom_bytes=rom_bytes)

    sprites = SpriteData(
        enemy_set_a    = bytearray(bins.enemy_set_a_sprites),
        enemy_set_b    = bytearray(bins.enemy_set_b_sprites),
        enemy_set_c    = bytearray(bins.enemy_set_c_sprites),
        ow_sprites     = bytearray(bins.ow_sprites),
        boss_set_a     = bytearray(bins.boss_set_a_sprites),
        boss_set_b     = bytearray(bins.boss_set_b_sprites),
        boss_set_c     = bytearray(bins.boss_set_c_sprites),
        boss_set_expansion = (bytearray(bins.boss_set_expansion_sprites) if bins.boss_set_expansion_sprites
                              else bytearray(BOSS_SET_EXPANSION_SPRITES_SIZE)),
        dungeon_common = bytearray(bins.dungeon_common_sprites),
    )

    enemies = _parse_enemy_tile_data(bins.tile_mapping_pointers, bins.tile_mapping_data)
    _parse_enemy_hp(bins, enemies)

    enemies.mixed_groups = {
        code: list(spec.group_members or [])
        for code, spec in mixed_groups.items()
    }

    ptr_data = bins.mixed_enemy_pointers
    cpu_addrs = [ptr_data[i*2] | (ptr_data[i*2+1] << 8) for i in range(POINTER_COUNT)]
    min_cpu = min(cpu_addrs)
    enemies.mixed_enemy_data = bytearray(bins.mixed_enemy_data)
    enemies.mixed_group_offsets = {
        FIRST_MIXED_GROUP_CODE + i: cpu_addrs[i] - min_cpu
        for i in range(POINTER_COUNT)
    }

    return GameWorld(
        overworld=overworld,
        levels=levels,
        quotes=quotes,
        hint_pointers=tuple(hint_pointers),
        hint_text_bytes=hint_text_bytes if hint_text_bytes is not None else (),
        sprites=sprites,
        enemies=enemies,
        levels_2q=levels_2q,
        blocks=blocks,
        blocks_2q=blocks_2q,
        quotes_raw=bins.quotes_data,
        overworld_arrival_code=_arrival_code(bins.level_info[:LEVEL_INFO_SIZE]),
        dungeon_nothing_code=_engine_nothing_code(rom_bytes),
        **_parse_person_code(bins, rom_bytes=rom_bytes),
        **_parse_b10_data(rom_bytes, bins.tile_mapping_pointers, _slot_text(quotes, REFUSAL_SLOT)),
    )


SET_LEVELS = (range(1, 7), range(7, 10))


def _engine_nothing_code(rom_bytes: bytes | None) -> DungeonNothingCode:
    """The "no item" code the engine's sentinel comparison reads (GameWorld.dungeon_nothing_code):
    ZORA_REMAP where the ROM carries the remap's byte; PRG0's otherwise, and without a ROM image.
    The room bytes are read in the code the caller's GameConfig names."""
    if rom_bytes is not None and rom_bytes[ASM_NOTHING_CODE_PATCH_OFFSET] == ASM_NOTHING_CODE_PATCH_VALUE:
        return DungeonNothingCode.ZORA_REMAP
    return DungeonNothingCode.VANILLA


def _second_quest_sets(level_pointers: bytes) -> list[int]:
    """SH-SRC-02: the sets (0 = levels 1-6, 1 = levels 7-9) whose levels point at their
    second-quest block in LevelBlockAddrsQ1 (high bytes $8D, $90); a set's levels all
    point at one block."""
    if not level_pointers:
        return []
    sets = []
    for set_index, level_nums in enumerate(SET_LEVELS):
        high_bytes = {level_pointers[2 * level_num + 1] for level_num in level_nums}
        if high_bytes == {ROOM_BLOCK_HIGH_BYTES[2 + set_index]}:
            sets.append(set_index)
        elif high_bytes != {ROOM_BLOCK_HIGH_BYTES[set_index]}:
            raise ValueError(f"levels {level_nums.start}-{level_nums.stop - 1} point at room blocks "
                             f"{sorted(f'${b:02X}' for b in high_bytes)}")
    return sets


def _parse_person_code(bins: RawBinFiles, rom_bytes: bytes | None = None) -> dict[str, Any]:
    """GameWorld's toll, bomb-upgrade levels and starting hearts (PS-MERCH-04,
    PS-BOMB-03); vanilla values when the bins carry no ROM image.  When a full
    ROM is available, also reads the hint-text selector bytes."""
    if not bins.life_or_money_payment:
        return {}
    slot_27 = TOLL_TEXT_POINTER_ADDRESS - QUOTE_DATA_ADDRESS
    result: dict[str, Any] = {
        "life_or_money_toll": person_code.life_or_money_toll(
            bins.life_or_money_payment, bins.quotes_data[slot_27:slot_27 + 2]
        ),
        "bomb_upgrade_levels": person_code.bomb_upgrade_levels(bins.person_update_branch),
        "person_inits": person_code.person_inits(bins.person_init_jump_table),
        "starting_hearts": bins.start_hearts[0],
        "continue_hearts_operand": bins.continue_hearts_operand[0] if bins.continue_hearts_operand else 2,
        "heart_meter_blank_branch": bins.heart_meter_blank_branch[0] if bins.heart_meter_blank_branch else 0x04,
        "item_carrier_operands": (bins.item_carrier_operands[0], bins.item_carrier_operands[1],
                                  bins.item_carrier_operands[2]),
        "object_type_operand_873d": bins.object_type_operand_873d[0],
        "monsters_take_second_quest_path": bins.quest_monster_branches == bytes([BNE_OPCODE] * 3),
        "overworld_wizzrobe_patch": bins.overworld_wizzrobe_patch,
        "underworld_text_selectors_a": bins.underworld_text_selectors_a,
        "underworld_text_selectors_b": bins.underworld_text_selectors_b,
    }
    if rom_bytes is not None:
        result["white_sword_text_selector"] = rom_bytes[OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS + 2]
        selectors = [rom_bytes[HINT_SHOP_QUOTES_ADDRESS + i] for i in range(6)]
        result["hint_shop_offer_selectors"] = tuple(selectors)
    return result
