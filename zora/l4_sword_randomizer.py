"""
L4 sword setup: places a sword upgrade in the level 9 triforce check room.

When add_l4_sword is on (which requires progressive_items), the room one row
north of the L9 entrance (the triforce checker room) receives a WOOD_SWORD
item. With progressive items active, picking it up after already holding the
magical sword grants the L4 sword upgrade.
"""
from zora.data_model import GameWorld, Item, ItemPosition
from zora.game_config import GameConfig
from zora.rng import Rng


def place_l4_sword(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Place a sword upgrade in the L9 triforce check room. Mutates game_world in place.

    Only runs when config.add_l4_sword is True (which already implies
    progressive_items is on — enforced in resolve_game_config).
    """
    if not config.add_l4_sword:
        return

    level_9 = game_world.levels[8]  # levels list is 0-indexed; level 9 is index 8
    triforce_check_room_num = level_9.entrance_room - 0x10

    room = next(
        (r for r in level_9.rooms if r.room_num == triforce_check_room_num),
        None,
    )
    if room is None:
        raise RuntimeError(
            f"add_l4_sword: could not find L9 triforce check room "
            f"(room_num=0x{triforce_check_room_num:02X})"
        )

    room.item = Item.WOOD_SWORD
    room.item_position = ItemPosition.POSITION_C
