"""
Remove Health Beep.

Disables the low hearts beeping sound entirely.
"""
from flags.flags_generated import LowHeartsSound as LowHeartsSoundMode
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class RemoveHealthBeep(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.low_hearts_sound == LowHeartsSoundMode.DISABLED

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x1ED33,
                new_bytes="00",
                old_bytes="40",
                comment="Disable low hearts beeping sound",
            ),
        ]
