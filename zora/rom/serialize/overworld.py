"""The overworld screens."""

from ...model.enums import QuestVisibility
from ...model.overworld import Overworld

# ---------------------------------------------------------------------------
# Overworld serialization
# ---------------------------------------------------------------------------

def _serialize_overworld(overworld: Overworld, grid: bytearray) -> None:
    """Write overworld screen data into the 6-table grid bytearray in-place."""
    for screen in overworld.screens:
        s = screen.screen_num
        t0 = ((screen.exit_x_position & 0x0F) << 4) \
           | (0x08 if screen.has_zola else 0) \
           | (0x04 if screen.has_ocean_sound else 0) \
           | (screen.outer_palette & 0x03)
        t1 = ((screen.destination & 0x3F) << 2) | (screen.inner_palette & 0x03)
        enemy_code = screen.enemy_spec.enemy.value
        enemy_low  = (enemy_code - 0x40) if enemy_code >= 0x40 else enemy_code
        t2 = (overworld.qty_table.index(screen.enemy_quantity) << 6) | (enemy_low & 0x3F)
        mixed_bit = 0x80 if enemy_code >= 0x40 else 0
        t3 = mixed_bit | (screen.screen_code & 0x7F)
        # t4 is the cave item table region — written entirely by _serialize_cave_data
        if screen.quest_visibility == QuestVisibility.BOTH_QUESTS:
            qv = 0
        elif screen.quest_visibility == QuestVisibility.FIRST_QUEST:
            qv = 1
        elif screen.quest_visibility == QuestVisibility.SECOND_QUEST:
            qv = 2
        else:
            qv = 3
        t5 = ((qv & 0x03) << 6) \
           | ((screen.stairs_position_code & 0x03) << 4) \
           | (0x08 if screen.enemies_from_sides else 0) \
           | (screen.exit_y_position & 0x07)
        grid[0 * 0x80 + s] = t0
        grid[1 * 0x80 + s] = t1
        grid[2 * 0x80 + s] = t2
        grid[3 * 0x80 + s] = t3
        # grid[4 * 0x80 + s] intentionally not written here
        grid[5 * 0x80 + s] = t5
