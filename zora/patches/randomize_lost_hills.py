"""
Randomize Lost Hills screen patches.

Applies ROM patches that enable the Lost Hills maze direction sequence
randomization — modifies overworld column graphics data so the screen
visually reflects the randomized directions.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class RandomizeLostHills(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.randomize_lost_hills

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(offset=0x154D7, old_bytes="00 00 00 00 00 00 50", new_bytes="01 01 01 01 01 01 01"),
            RomEdit(offset=0x154F1, old_bytes="D2",                   new_bytes="09"),
            RomEdit(offset=0x154F5, old_bytes="38",                   new_bytes="06"),
            RomEdit(offset=0x155DD, old_bytes="B6",                   new_bytes="02"),
            RomEdit(offset=0x155F5, old_bytes="B8",                   new_bytes="51"),
        ]
