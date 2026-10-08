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

from zora.model.game_world import GameWorld
from zora.model.levels import Level, LevelBlock
from zora.model.sprites import SpriteData
from zora.rom import person_code
from zora.rom.game_config import GameConfig
from zora.rom.layout import (
    BOSS_SET_EXPANSION_SPRITES_SIZE,
    DUNGEON_NOTHING_CODE,
    FIRST_MIXED_GROUP_CODE,
    HINT_SHOP_QUOTES_ADDRESS,
    OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS,
    POINTER_COUNT,
    QUOTE_DATA_ADDRESS,
    TOLL_TEXT_POINTER_ADDRESS,
)
from zora.rom.parse.bin_files import RawBinFiles
from zora.rom.parse.enemies import _parse_enemy_hp, _parse_enemy_tile_data, _parse_mixed_enemy_groups
from zora.rom.parse.features import _parse_b10_data
from zora.rom.parse.levels import _parse_block, _parse_level
from zora.rom.parse.overworld import _parse_overworld
from zora.rom.parse.text import REFUSAL_SLOT, _parse_person_text, _slot_text

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

    def parse_quest(grids: tuple[bytes, bytes], level_info: bytes
                    ) -> tuple[list[LevelBlock], list[Level]]:
        blocks = [_parse_block(g, mixed_groups, nothing_code) for g in grids]
        levels = [_parse_level(level_num, grids[set_index], blocks[set_index],
                               bins, level_info=level_info)
                  for set_index, level_nums in enumerate((range(1, 7), range(7, 10)))
                  for level_num in level_nums]
        return blocks, levels

    blocks, levels = parse_quest((bins.level_1_6_data, bins.level_7_9_data),
                                 bins.level_info)
    blocks_2q, levels_2q = parse_quest(
        (bins.level_1_6_data_q2, bins.level_7_9_data_q2), bins.level_info_q2
    )

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
        **_parse_person_code(bins, rom_bytes=rom_bytes),
        **_parse_b10_data(rom_bytes, bins.tile_mapping_pointers, _slot_text(quotes, REFUSAL_SLOT)),
    )


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
        "item_carrier_operands": (bins.item_carrier_operands[0], bins.item_carrier_operands[1],
                                  bins.item_carrier_operands[2]),
        "object_type_operand_873d": bins.object_type_operand_873d[0],
        "overworld_wizzrobe_patch": bins.overworld_wizzrobe_patch,
        "underworld_text_selectors_a": bins.underworld_text_selectors_a,
        "underworld_text_selectors_b": bins.underworld_text_selectors_b,
    }
    if rom_bytes is not None:
        result["white_sword_text_selector"] = rom_bytes[OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS + 2]
        selectors = [rom_bytes[HINT_SHOP_QUOTES_ADDRESS + i] for i in range(6)]
        result["hint_shop_offer_selectors"] = tuple(selectors)
    return result
