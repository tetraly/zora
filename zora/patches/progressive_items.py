"""
Progressive items.

Rewrites the item-pickup routine so collecting a sword or shield upgrades
whatever the player already has, rather than overwriting unconditionally.
"""
from unittest.mock import MagicMock

from zora.game_config import GameConfig
from zora.patches.base import RomEdit, VariableBehaviorPatch


class ProgressiveItems(VariableBehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.progressive_items

    def get_edits_for_config(self, config: GameConfig, rom_version: int | None = None) -> list[RomEdit]:
        edits: list[RomEdit] = [
            RomEdit(
                offset=0x6D06,
                new_bytes="18 79 57 06 EA",
                old_bytes="D9 57 06 90 20",
                comment="Hook item pickup: load from upgrade table instead of raw item id",
            ),
        ]
        # The JSR redirect at 0x6BFB and the stub at 0x1FFF4 are byte-equivalent
        # to FixKnownBugs' B6/B7 enemy-kill-counter fix. FixKnownBugs is now
        # always active so it owns those edits and we don't install them here.
        # Kept as commented-out code in case progressive items ever needs to
        # own them again (e.g. if FKB's variant of B6/B7 changes).
        #
        # edits.extend([
        #     RomEdit(
        #         offset=0x6BFB,
        #         new_bytes="20 E4 FF",
        #         old_bytes="8E 02 06",
        #         comment="Redirect item-got handler to progressive upgrade stub",
        #     ),
        #     RomEdit(
        #         offset=0x1FFF4,
        #         new_bytes="8E 02 06 8E 72 06 EE 4F 03 60",
        #         old_bytes="FF FF FF FF FF FF FF 5A 45 4C",
        #         comment="Upgrade stub: write both RAM mirrors, bump counter, return",
        #     ),
        # ])
        return edits

    def test_only_get_all_variant_edits(self) -> list[RomEdit]:
        return list(self.get_edits_for_config(MagicMock()))
