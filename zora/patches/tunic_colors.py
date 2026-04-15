"""
Tunic Color Patches.

Changes the starting (green), blue ring, and red ring tunic colors to
player-selected NES palette values.

"""
from zora.game_config import GameConfig
from zora.patches.base import RomEdit, VariableBehaviorPatch
from zora.rom_layout import (
    BLUE_RING_TUNIC_COLOR_OFFSET,
    RED_RING_TUNIC_COLOR_OFFSET,
    START_TUNIC_COLOR_OFFSET,
)

# Vanilla NES palette bytes at each offset
_VANILLA_START = 0x29   # green
_VANILLA_BLUE = 0x32    # blue
_VANILLA_RED = 0x16     # red


class TunicColors(VariableBehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return any(c is not None for c in (
            config.green_tunic_color,
            config.blue_ring_color,
            config.red_ring_color,
        ))

    def test_only_get_all_variant_edits(self) -> list[RomEdit]:
        edits: list[RomEdit] = []
        # One representative edit per offset is sufficient
        for color, offset, vanilla in [
            (0x11, START_TUNIC_COLOR_OFFSET, _VANILLA_START),
            (0x11, BLUE_RING_TUNIC_COLOR_OFFSET, _VANILLA_BLUE),
            (0x11, RED_RING_TUNIC_COLOR_OFFSET, _VANILLA_RED),
        ]:
            edits.append(RomEdit(
                offset=offset,
                new_bytes=bytes([color]),
                old_bytes=bytes([vanilla]),
            ))
        return edits

    def get_edits_for_config(
        self, config: GameConfig, rom_version: int | None = None,
    ) -> list[RomEdit]:
        edits: list[RomEdit] = []
        for color, offset, vanilla, label in [
            (config.green_tunic_color, START_TUNIC_COLOR_OFFSET, _VANILLA_START, "start tunic"),
            (config.blue_ring_color, BLUE_RING_TUNIC_COLOR_OFFSET, _VANILLA_BLUE, "blue ring tunic"),
            (config.red_ring_color, RED_RING_TUNIC_COLOR_OFFSET, _VANILLA_RED, "red ring tunic"),
        ]:
            if color is not None:
                edits.append(RomEdit(
                    offset=offset,
                    new_bytes=bytes([color]),
                    old_bytes=bytes([vanilla]),
                    comment=f"Change {label} color to NES palette 0x{color:02X}",
                ))
        return edits
