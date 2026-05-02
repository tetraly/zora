# This test exists because mmg_lose_large.bin and mmg_lose_small_2.bin were transcribed with transposed bytes, drifting from base.nes and silently corrupting MMG output at zero flags.
"""Consistency check: rom_data/*.bin must equal the corresponding slice of
rom_data/base.nes at the offset declared in zora/rom_layout.py.

If a .bin file's contents drift from the canonical base.nes bytes, the
parser/serializer can disagree about what "vanilla" means depending on whether
bins are loaded from disk (load_bin_files) or sliced from a ROM
(load_bin_files_from_rom). This test catches that.

A .bin without an obvious layout-constant mapping is reported but not failed.
"""
from pathlib import Path

import pytest

from zora import rom_layout as RL

ROM_DATA = Path(__file__).parent.parent / "rom_data"

# bin_filename -> (offset, size). Sizes match load_bin_files_from_rom slicing.
BIN_TO_LAYOUT: dict[str, tuple[int, int]] = {
    "level_1_6_data.bin":              (RL.LEVEL_1_6_DATA_ADDRESS, 0x300),
    "level_7_9_data.bin":              (RL.LEVEL_7_9_DATA_ADDRESS, 0x300),
    "level_1_6_data_q2.bin":           (RL.LEVEL_1_6_DATA_ADDRESS_Q2, 0x300),
    "level_7_9_data_q2.bin":           (RL.LEVEL_7_9_DATA_ADDRESS_Q2, 0x300),
    "level_info.bin":                  (RL.LEVEL_INFO_ADDRESS, 0xA * 0xFC),
    "overworld_data.bin":              (RL.OVERWORLD_DATA_ADDRESS, 0x500),
    "armos_item.bin":                  (RL.ARMOS_ITEM_ADDRESS, 1),
    "armos_tables.bin":                (RL.ARMOS_TABLES_ADDRESS, 14),
    "coast_item.bin":                  (RL.COAST_ITEM_ADDRESS, 1),
    "white_sword_requirement.bin":     (RL.WHITE_SWORD_REQUIREMENT_ADDRESS, 1),
    "magical_sword_requirement.bin":   (RL.MAGICAL_SWORD_REQUIREMENT_ADDRESS, 1),
    "door_repair_charge.bin":          (RL.DOOR_REPAIR_CHARGE_ADDRESS, 1),
    "cave_item_data.bin":              (RL.CAVE_ITEM_DATA_ADDRESS, 60),
    "cave_price_data.bin":             (RL.CAVE_PRICE_DATA_ADDRESS, 60),
    "cave_quotes_data.bin":            (RL.CAVE_QUOTES_DATA_ADDRESS, 20),
    "hint_shop_quotes.bin":            (RL.HINT_SHOP_QUOTES_ADDRESS, 6),
    "bomb_cost.bin":                   (RL.BOMB_COST_OFFSET, 1),
    "bomb_count.bin":                  (RL.BOMB_COUNT_OFFSET, 1),
    "mmg_lose_small.bin":              (RL.MMG_LOSE_SMALL_OFFSET, 1),
    "mmg_lose_small_2.bin":            (RL.MMG_LOSE_SMALL_2_OFFSET, 1),
    "mmg_lose_large.bin":              (RL.MMG_LOSE_LARGE_OFFSET, 1),
    "mmg_win_small.bin":               (RL.MMG_WIN_SMALL_OFFSET_A, 1),
    "mmg_win_large.bin":               (RL.MMG_WIN_LARGE_OFFSET_A, 1),
    "recorder_warp_destinations.bin":  (RL.RECORDER_WARP_DESTINATIONS_ADDRESS, 8),
    "recorder_warp_y_coordinates.bin": (RL.RECORDER_WARP_Y_COORDINATES_ADDRESS, 8),
    "any_road_screens.bin":            (RL.ANY_ROAD_SCREENS_ADDRESS, 4),
    "start_screen.bin":                (RL.START_SCREEN_ADDRESS, 1),
    "start_position_y.bin":            (RL.START_POSITION_Y_ADDRESS, 1),
    "level_sprite_set_pointers.bin":   (RL.LEVEL_SPRITE_SET_POINTERS_ADDRESS, 20),
    "boss_sprite_set_pointers.bin":    (RL.BOSS_SPRITE_SET_POINTERS_ADDRESS, 20),
    "quotes_data.bin":                 (RL.QUOTE_DATA_ADDRESS, 1442),
    "maze_directions.bin":             (RL.MAZE_DIRECTIONS_ADDRESS, 8),
    "ow_sprites.bin":                  (RL.OW_SPRITES_ADDRESS, RL.OW_SPRITES_SIZE),
    "enemy_set_a_sprites.bin":         (RL.ENEMY_SET_A_SPRITES_ADDRESS, RL.ENEMY_SET_A_SPRITES_SIZE),
    "enemy_set_b_sprites.bin":         (RL.ENEMY_SET_B_SPRITES_ADDRESS, RL.ENEMY_SET_B_SPRITES_SIZE),
    "enemy_set_c_sprites.bin":         (RL.ENEMY_SET_C_SPRITES_ADDRESS, RL.ENEMY_SET_C_SPRITES_SIZE),
    "dungeon_common_sprites.bin":      (RL.DUNGEON_COMMON_SPRITES_ADDRESS, RL.DUNGEON_COMMON_SPRITES_SIZE),
    "boss_set_a_sprites.bin":          (RL.BOSS_SET_A_SPRITES_ADDRESS, RL.BOSS_SET_A_SPRITES_SIZE),
    "boss_set_b_sprites.bin":          (RL.BOSS_SET_B_SPRITES_ADDRESS, RL.BOSS_SET_B_SPRITES_SIZE),
    "boss_set_c_sprites.bin":          (RL.BOSS_SET_C_SPRITES_ADDRESS, RL.BOSS_SET_C_SPRITES_SIZE),
    "tile_mapping_pointers.bin":       (RL.TILE_MAPPING_POINTERS_ADDRESS, RL.TILE_MAPPING_POINTERS_SIZE),
    "tile_mapping_data.bin":           (RL.TILE_MAPPING_DATA_ADDRESS, RL.TILE_MAPPING_DATA_SIZE),
    "enemy_hp_table.bin":              (RL.ENEMY_HP_TABLE_ADDRESS, RL.ENEMY_HP_TABLE_SIZE),
    "boss_hp_table.bin":               (RL.BOSS_HP_TABLE_ADDRESS, RL.BOSS_HP_TABLE_SIZE),
    "aquamentus_hp.bin":               (RL.AQUAMENTUS_HP_ADDRESS, 1),
    "aquamentus_sp.bin":               (RL.AQUAMENTUS_SP_ADDRESS, 1),
    "ganon_hp.bin":                    (RL.GANON_HP_ADDRESS, 1),
    "gleeok_hp.bin":                   (RL.GLEEOK_HP_ADDRESS, 1),
    "patra_hp.bin":                    (RL.PATRA_HP_ADDRESS, 1),
    "aquamentus_sprite_ptr.bin":       (RL.AQUAMENTUS_SPRITE_PTR_ADDRESS, 1),
    "gleeok_head_sprite_ptr_a.bin":    (RL.GLEEOK_HEAD_SPRITE_PTR_A_ADDRESS, 1),
    "gleeok_head_sprite_ptr_b.bin":    (RL.GLEEOK_HEAD_SPRITE_PTR_B_ADDRESS, 1),
    "gleeok_head_sprite_ptr_c.bin":    (RL.GLEEOK_HEAD_SPRITE_PTR_C_ADDRESS, 1),
    "player_main_sprites.bin":         (RL.PLAYER_MAIN_SPRITES_ADDRESS, RL.PLAYER_MAIN_SPRITES_SIZE),
    "player_cheer_sprites.bin":        (RL.PLAYER_CHEER_SPRITES_ADDRESS, RL.PLAYER_CHEER_SPRITES_SIZE),
    "player_big_shield_profile_sprites.bin": (RL.PLAYER_BIG_SHIELD_PROFILE_SPRITES_ADDRESS, RL.PLAYER_BIG_SHIELD_PROFILE_SPRITES_SIZE),
    "player_profile_no_shield_sprites.bin":  (RL.PLAYER_PROFILE_NO_SHIELD_SPRITES_ADDRESS, RL.PLAYER_PROFILE_NO_SHIELD_SPRITES_SIZE),
    "player_small_shield_sprites.bin":       (RL.PLAYER_SMALL_SHIELD_SPRITES_ADDRESS, RL.PLAYER_SMALL_SHIELD_SPRITES_SIZE),
    "player_large_shield_sprites.bin":       (RL.PLAYER_LARGE_SHIELD_SPRITES_ADDRESS, RL.PLAYER_LARGE_SHIELD_SPRITES_SIZE),
    "tile_mapping_enemies.bin":        (RL.TILE_MAPPING_ENEMIES_ADDRESS, RL.TILE_MAPPING_ENEMIES_SIZE),
    "tile_mapping_enemy_frames.bin":   (RL.TILE_MAPPING_ENEMY_FRAMES_ADDRESS, RL.TILE_MAPPING_ENEMY_FRAMES_SIZE),
    "mixed_enemy_data.bin":            (RL.MIXED_ENEMY_DATA_ADDRESS, RL.MIXED_ENEMY_DATA_SIZE),
    "mixed_enemy_pointers.bin":        (RL.MIXED_ENEMY_POINTER_TABLE_ADDRESS, RL.POINTER_COUNT * 2),
}


@pytest.mark.parametrize("bin_name", sorted(BIN_TO_LAYOUT))
def test_bin_matches_base_rom(bin_name: str) -> None:
    offset, size = BIN_TO_LAYOUT[bin_name]
    rom = (ROM_DATA / "base.nes").read_bytes()
    expected = rom[offset:offset + size]
    actual = (ROM_DATA / bin_name).read_bytes()
    assert actual == expected, (
        f"{bin_name} ({len(actual)} bytes) != base.nes[{offset:#x}:{offset+size:#x}] "
        f"({len(expected)} bytes). First differing byte index: "
        f"{next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), 'len mismatch')}"
    )


def test_unmapped_bins_inventory() -> None:
    """Report .bin files that have no layout mapping. Informational only."""
    bins = {p.name for p in ROM_DATA.glob("*.bin")}
    unmapped = sorted(bins - set(BIN_TO_LAYOUT))
    if unmapped:
        # Don't fail; just emit so we know what's not covered.
        print("\nUnmapped .bin files (no layout constant mapping):")
        for n in unmapped:
            print(f"  - {n}")
