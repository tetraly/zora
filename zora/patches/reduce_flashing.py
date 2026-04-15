"""
Reduce Flashing.

Removes the triforce collection flash effect by NOPing the two instructions
that trigger the palette-cycling flash routine.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class ReduceFlashing(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.reduce_flashing

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x16895,
                new_bytes=bytes([0xEA, 0xEA]),
                old_bytes=bytes([0x84, 0x14]),
                comment="NOP triforce flash trigger (STY $14 → NOP NOP)",
            ),
        ]
