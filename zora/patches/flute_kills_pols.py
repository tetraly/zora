"""
Flute Kills Dungeon Pols Voice.

Play the flute (recorder) to kill all Pols Voice in dungeons.
Does not work on the overworld.

Patch courtesy of Stratoform.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class FluteKillsPols(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.flute_kills_pols

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x011C47,
                new_bytes="30 BF",
                old_bytes="D0 79",
                comment="Branch to flute-kills-pols routine",
            ),
            RomEdit(
                offset=0x013F40,
                new_bytes="20 D0 79 AD 1B 05 F0 0E B5 28 D0 05 A9 C3 95 28 60 30 03 20 A6 FE 60",
                old_bytes="FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF",
                comment="Flute kills Pols Voice in dungeons subroutine (unused space)",
            ),
        ]
