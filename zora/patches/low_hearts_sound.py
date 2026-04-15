"""
Softer Low Hearts Sound.

Changes the low hearts sound to a softer heartbeat sound.

Patch courtesy of gzip.
"""
from flags.flags_generated import LowHeartsSound as LowHeartsSoundMode
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class LowHeartsSound(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.low_hearts_sound == LowHeartsSoundMode.SOFTER

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x001872,
                new_bytes="9C 80 80 08 08 08 08 08",
                old_bytes="95 50 08 08 08 08 08 90",
                comment="Replace low hearts beep with softer heartbeat sound",
            ),
        ]
