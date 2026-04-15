"""
Auto Show Letter.

Automatically shows the letter to NPCs without the player needing to
equip and use it manually.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class AutoShowLetter(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.auto_show_letter

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x004708,
                new_bytes="C9 01 F0 13 EA EA EA EA EA EA EA EA EA",
                old_bytes="AC 56 06 C0 0F D0 06 A5 F8 29 40 D0 0A",
                comment="Auto-show letter to NPCs without manual equip/use",
            ),
        ]
