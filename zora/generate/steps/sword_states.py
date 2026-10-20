"""Swords (C07; features-behavior.md FP-WOOD-01 to FP-WOOD-03): the cave wares each wooden-sword
state changes, on the staged overworld, before any random pass (no draw). The code patches are
the ROM's (zora/rom/sword_states.py); the acceptance walk's rules are VA-REJ-22's (LogicRules)."""

from ...flags.fields import WoodenSwordState
from ...model.enums import Destination, Item
from ...model.overworld import ItemCave, Overworld

# FP-WOOD-02: under these two the white sword's item, $02, is a bomb upgrade, and the
# magical-sword cave offers it
BOMB_UPGRADE_STATES = frozenset({WoodenSwordState.WOODEN_SWORD_ONLY, WoodenSwordState.SWORDLESS})


def change_sword_caves(overworld: Overworld, state: WoodenSwordState) -> None:
    """FP-WOOD-01 to FP-WOOD-03: No Wood Sword empties the wooden-sword cave's sword ware ($3F);
    Swordless puts the blue candle there ($3F, $06, $7F: Extra Candles, B09, later adds one more
    in ware 0); Wood Sword Only and Swordless make the magical-sword cave offer item $02."""
    wood_sword_cave = overworld.get_cave(Destination.WOOD_SWORD_CAVE, ItemCave)
    magical_sword_cave = overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    assert wood_sword_cave is not None and magical_sword_cave is not None
    if state is WoodenSwordState.NO_WOODEN_SWORD:
        wood_sword_cave.item = Item.OVERWORLD_NO_ITEM
    elif state is WoodenSwordState.SWORDLESS:
        wood_sword_cave.item = Item.BLUE_CANDLE
    if state in BOMB_UPGRADE_STATES:
        magical_sword_cave.item = Item.WHITE_SWORD
