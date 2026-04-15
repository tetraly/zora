"""
Data normalization step.

Runs before any randomizers or shufflers to put the game world into a
canonical state that the rest of the pipeline can rely on.
"""

from zora.data_model import Destination, GameWorld, Item, Shop
from zora.game_config import GameConfig
from zora.rng import Rng


def normalize_data(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Normalize game world data before randomization.

    When shuffle_major_shop_items is on, replaces the second BAIT slot in
    shops A-D with a FAIRY. Vanilla shops C and D both carry BAIT; having two
    copies would allow assumed fill to treat BAIT as a duplicated major item.
    Replacing the second occurrence ensures there is exactly one BAIT in the
    shop item pool before assumed fill runs.
    """
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
