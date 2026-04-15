"""
Like-Like Eats Rupees.

Makes Like-Likes eat rupees instead of a magical shield.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class LikeLikeRupees(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.like_like_rupees

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=0x011D45,
                new_bytes="01 8D 7E",
                old_bytes="00 8D 76",
                comment="Like-Likes eat rupees instead of magical shield",
            ),
        ]
