"""
Speed up text scroll.

Reduces the per-character text delay counter from its vanilla value to 0x02,
making in-game text scroll significantly faster.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class SpeedUpText(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.speed_up_text

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x482D,
                new_bytes=bytes([0x02]),
                old_bytes=bytes([0x06]),
                comment="Reduce text scroll delay counter to 0x02",
            ),
        ]
