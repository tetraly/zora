"""
Heart HUD Color Patch.

Changes the heart color in the dungeon HUD display to a player-selected
NES palette value. Writes to all 10 dungeon health tile positions.

"""
from zora.game_config import GameConfig
from zora.patches.base import RomEdit, VariableBehaviorPatch
from zora.rom_layout import HEART_COLOR_OFFSETS

# Vanilla NES palette byte for hearts (red)
_VANILLA_HEART = 0x16


class HeartColor(VariableBehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.heart_color is not None

    def test_only_get_all_variant_edits(self) -> list[RomEdit]:
        edits: list[RomEdit] = []
        for offset in HEART_COLOR_OFFSETS:
            edits.append(RomEdit(
                offset=offset,
                new_bytes=bytes([0x11]),
                old_bytes=bytes([_VANILLA_HEART]),
            ))
        return edits

    def get_edits_for_config(
        self, config: GameConfig, rom_version: int | None = None,
    ) -> list[RomEdit]:
        assert config.heart_color is not None
        color = config.heart_color
        return [
            RomEdit(
                offset=offset,
                new_bytes=bytes([color]),
                old_bytes=bytes([_VANILLA_HEART]),
                comment=f"Heart HUD color to NES palette 0x{color:02X}",
            )
            for offset in HEART_COLOR_OFFSETS
        ]
