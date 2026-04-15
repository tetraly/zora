"""
Four Potion Inventory.

Increases the potion inventory from 2 to 4 blue potions.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class FourPotionInventory(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.four_potion_inventory

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x006C6F,
                new_bytes="C9 05",
                old_bytes="C9 03",
                comment="Raise potion inventory comparison from 2 to 4",
            ),
            RomEdit(
                offset=0x006C73,
                new_bytes="A9 04",
                old_bytes="A9 02",
                comment="Set max potion slot count to 4",
            ),
        ]
