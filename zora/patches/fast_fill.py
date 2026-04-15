"""
Fast Fill.

Fill hearts faster from fairies and potions.

Patch courtesy of snarfblam.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class FastFill(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.fast_fill

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x017203,
                new_bytes="D7 B0 07 18 69 18",
                old_bytes="F8 B0 07 18 69 06",
                comment="Speed up heart fill rate",
            ),
        ]
