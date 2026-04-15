"""
Nothing-code patch.

When magical sword is shuffled with progressive items off, item code 0x03
(magical sword) collides with the vanilla dungeon "nothing" sentinel.
This patch changes the ASM sentinel comparison value from 0x03 to 0x18,
allowing the game engine to correctly distinguish "no item" from the magical
sword item code.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit
from zora.rom_layout import ASM_NOTHING_CODE_PATCH_OFFSET, ASM_NOTHING_CODE_PATCH_VALUE


class NothingCode(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.shuffle_magical_sword and not config.progressive_items

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            RomEdit(
                offset=ASM_NOTHING_CODE_PATCH_OFFSET,
                new_bytes=bytes([ASM_NOTHING_CODE_PATCH_VALUE]),
                old_bytes="03",
                comment="Change dungeon nothing-sentinel from 0x03 to 0x18",
            ),
        ]
