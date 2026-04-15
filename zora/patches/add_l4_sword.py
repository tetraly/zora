"""
Add L4 Sword.

Changes the level 9 triforce checker from requiring sword_level == 3 (BEQ)
to sword_level >= 3 (BCS), so that having a L4 sword also opens the gate.

See https://github.com/aldonunez/zelda1-disassembly/blob/master/src/Z_01.asm#L6067
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class AddL4Sword(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.add_l4_sword

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x7540,
                new_bytes="B0",
                old_bytes="F0",
                comment="L9 triforce checker: BEQ (sword==3) → BCS (sword>=3) for L4 sword support",
            ),
        ]
