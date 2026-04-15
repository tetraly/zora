"""
Extra power bracelet blocks.

Adds power-bracelet-gated blocks to West Death Mountain
(screens 0x00-0x03, 0x10, 0x12, 0x13), requiring the power bracelet
to push blocks and access those overworld screens.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class ExtraPowerBraceletBlocks(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.extra_power_bracelet_blocks

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(offset=0x1554E, old_bytes="06",             new_bytes="38"),
            RomEdit(offset=0x15554, old_bytes="A1 84 90 02 02", new_bytes="06 E7 00 00 00"),
            RomEdit(offset=0x15649, old_bytes="A9 02",          new_bytes="00 A9"),
            RomEdit(offset=0x1564E, old_bytes="B5",             new_bytes="B6"),
            RomEdit(offset=0x1574E, old_bytes="B6",             new_bytes="02"),
        ]
