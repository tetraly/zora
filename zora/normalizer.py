"""
Data normalization step.

Runs before any randomizers or shufflers to put the game world into a
canonical state that the rest of the pipeline can rely on.
"""

from zora.data_model import Destination, GameWorld, Item, RoomType, Shop
from zora.game_config import GameConfig
from zora.rng import Rng

_CENTER_COORD = 0x89  # X=8, Y=9 — center of the room


def normalize_data(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Normalize game world data before randomization.

    1. Item staircases are forced to render their item at the center of the
       room (coord 0x89). We look up the index of 0x89 in each level's
       item_position_table and write that index into t5 bits 4-5 of every
       item-staircase row. If the level's table has no 0x89 entry (some
       vanilla levels don't), we leave the staircase alone.

    2. When shuffle_major_shop_items is on, replaces the second BAIT slot in
       shops A-D with a FAIRY. Vanilla shops C and D both carry BAIT; having
       two copies would allow assumed fill to treat BAIT as a duplicated
       major item. Replacing the second occurrence ensures there is exactly
       one BAIT in the shop item pool before assumed fill runs.
    """
    for level in game_world.levels:
        try:
            center_idx = level.item_position_table.index(_CENTER_COORD)
        except ValueError:
            continue
        for sr in level.staircase_rooms:
            if sr.room_type == RoomType.ITEM_STAIRCASE:
                sr.t5_raw = (sr.t5_raw & ~0x30) | ((center_idx & 0x03) << 4)

    if not config.shuffle_major_shop_items:
        return

    ow = game_world.overworld
    bait_seen = False
    for dest in [Destination.SHOP_1, Destination.SHOP_2, Destination.SHOP_3, Destination.SHOP_4]:
        shop = ow.get_cave(dest, Shop)
        if shop is None:
            continue
        for si in shop.items:
            if si.item == Item.BAIT:
                if bait_seen:
                    si.item = Item.FAIRY
                    return
                bait_seen = True
