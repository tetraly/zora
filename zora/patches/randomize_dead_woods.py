"""
Randomize Dead Woods screen patches.

Applies ROM patches that enable the Dead Woods maze direction sequence
randomization — modifies overworld column graphics data so the screen
visually reflects the randomized directions.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class RandomizeDeadWoods(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.randomize_dead_woods

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(offset=0x15B08, old_bytes="30", new_bytes="29"),
            RomEdit(offset=0x158F8, old_bytes="15", new_bytes="16"),
        ]
