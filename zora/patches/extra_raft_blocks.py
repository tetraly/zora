"""
Extra raft blocks.

Adds raft-gated blocks to the Westlake Mall and Casino Corner region
(screens 0x0E, 0x0F, 0x1E, 0x1F, 0x34, 0x44), requiring the raft
to pass through those overworld screens.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class ExtraRaftBlocks(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.extra_raft_blocks

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(offset=0x154F8, old_bytes="80",          new_bytes="0C"),
            RomEdit(offset=0x155F7, old_bytes="51 51",       new_bytes="0C 0C"),
            RomEdit(offset=0x15613, old_bytes="F2",          new_bytes="EB"),
            RomEdit(offset=0x15615, old_bytes="02",          new_bytes="AF"),
            RomEdit(offset=0x15715, old_bytes="00",          new_bytes="B6"),
            RomEdit(offset=0x15765, old_bytes="47 91",       new_bytes="91 78"),
            RomEdit(offset=0x1582F, old_bytes="07 18 45 13 13 13 13 13 13 13 00",
                                    new_bytes="02 08 0B 0B 0B 0B 0B 0B 0B 0B 01"),
            RomEdit(offset=0x1592F, old_bytes="23 23",       new_bytes="17 17"),
        ]
