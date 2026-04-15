"""
Speed up dungeon screen transitions.

Replaces the 2-byte branch instruction driving a busy-wait loop at each of
five sites in the dungeon transition routine with NOP NOP, removing the
added delay without touching surrounding logic.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class SpeedUpDungeonTransitions(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.speed_up_dungeon_transitions

    _OLD_BYTES: dict[int, str] = {
        0x141F3: "D0 02",
        0x1426B: "D0 03",
        0x1446B: "D0 02",
        0x14478: "D0 02",
        0x144AD: "D0 02",
    }

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=offset,
                new_bytes="EA EA",
                old_bytes=self._OLD_BYTES[offset],
                comment=f"NOP out transition busy-wait branch at {offset:#07x}",
            )
            for offset in [0x141F3, 0x1426B, 0x1446B, 0x14478, 0x144AD]
        ]
