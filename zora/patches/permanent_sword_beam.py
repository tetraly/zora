"""
Permanent Sword Beam.

Makes the sword beam fire at any health level (not just full hearts).

"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class PermanentSwordBeam(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.permanent_sword_beam

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x1F875,
                new_bytes="4C 7D F8",
                old_bytes="AD 6F 06",
                comment="JMP redirect: sword beam fires at any health level",
            ),
        ]
