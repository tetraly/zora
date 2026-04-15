"""
Progressive items.

Rewrites the item-pickup routine so collecting a sword or shield upgrades
whatever the player already has, rather than overwriting unconditionally.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class ProgressiveItems(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.progressive_items

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x6D06,
                new_bytes="18 79 57 06 EA",
                old_bytes="D9 57 06 90 20",
                comment="Hook item pickup: load from upgrade table instead of raw item id",
            ),
            RomEdit(
                offset=0x6BFB,
                new_bytes="20 E4 FF",
                old_bytes="8E 02 06",
                comment="Redirect item-got handler to progressive upgrade stub",
            ),
            RomEdit(
                offset=0x1FFF4,
                new_bytes="8E 02 06 8E 72 06 EE 4F 03 60",
                old_bytes="FF FF FF FF FF FF FF 5A 45 4C",
                comment="Upgrade stub: write both RAM mirrors, bump counter, return",
            ),
        ]
