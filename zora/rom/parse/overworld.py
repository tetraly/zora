"""The overworld screens, with their caves and monsters."""

from zora.model.enums import Destination, Enemy, OverworldDirection, QuestVisibility
from zora.model.overworld import SCREEN_ENTRANCE_TYPES, BombUpgrade, EntranceType, Overworld, Screen
from zora.model.rooms import EnemySpec
from zora.rom.parse.bin_files import RawBinFiles
from zora.rom.parse.caves import _parse_cave_data
from zora.rom.parse.levels import _level_info_block_by_index, _parse_enemy_sprite_set

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
        elif qv_code == 2:
            quest_visibility = QuestVisibility.SECOND_QUEST
        else:
            quest_visibility = QuestVisibility.NEITHER_QUEST

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
