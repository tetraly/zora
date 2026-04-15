"""
Disable Music.

Disables all game music by zeroing out the music table and its two mirror
locations.

"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class DisableMusic(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.disable_music

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x1EBF0,
                new_bytes="00 00 00 00 00 00 00 00 00 00",
                old_bytes="01 40 40 40 40 40 40 40 40 20",
                comment="Zero out 10-entry music table",
            ),
            RomEdit(
                offset=0x12CE5,
                new_bytes="00",
                old_bytes="20",
                comment="Zero mirror location 1 (matches ShuffleMusic copy behavior)",
            ),
            RomEdit(
                offset=0x061B1,
                new_bytes="00",
                old_bytes="20",
                comment="Zero mirror location 2 (matches ShuffleMusic copy behavior)",
            ),
        ]
