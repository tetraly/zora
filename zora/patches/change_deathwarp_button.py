"""
Deathwarp Button Remapping.

Remaps the button combination used to deathwarp (Up + A on the second
controller in vanilla) to a first-controller combination.

Three modes:
  P2_UP_A    — Vanilla behavior: Up + A on second controller (no patch applied).
  P1_UP_A    — Remap to Up + A on first controller.
  P1_UP_SEL  — Remap to Up + SELECT on first controller.

"""
from flags.flags_generated import DeathwarpButton
from zora.game_config import GameConfig
from zora.patches.base import RomEdit, VariableBehaviorPatch


class ChangeDeathwarpButton(VariableBehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.deathwarp_button != DeathwarpButton.P2_UP_A

    def test_only_get_all_variant_edits(self) -> list[RomEdit]:
        from unittest.mock import MagicMock
        edits: list[RomEdit] = []
        seen: set[tuple[int, bytes]] = set()
        for mode in DeathwarpButton:
            if mode == DeathwarpButton.P2_UP_A:
                continue  # inactive variant, produces no edits
            config = MagicMock()
            config.deathwarp_button = mode
            for edit in self.get_edits_for_config(config):
                key = (edit.offset, edit.new_bytes)
                if key not in seen:
                    seen.add(key)
                    edits.append(edit)
        return edits

    def get_edits_for_config(self, config: GameConfig, rom_version: int | None = None) -> list[RomEdit]:
        edits: list[RomEdit] = [
            # 0x140EB: controller-select byte. Vanilla 0xFB reads controller 2;
            # 0xFA reads controller 1 instead.
            RomEdit(
                offset=0x140EB,
                new_bytes=bytes([0xFA]),
                old_bytes=bytes([0xFB]),
                comment="Remap deathwarp read from controller 2 to controller 1",
            ),
        ]
        if config.deathwarp_button == DeathwarpButton.P1_UP_SEL:
            # Replace the Up (0x08) check bytes with SELECT (0x20) at the two
            # branch-target bytes in the same routine.
            edits += [
                RomEdit(
                    offset=0x140ED,
                    new_bytes=bytes([0x28]),
                    old_bytes=bytes([0x88]),
                    comment="Change button mask from Up (0x08) to Up+SELECT (0x28) — byte 1",
                ),
                RomEdit(
                    offset=0x140EF,
                    new_bytes=bytes([0x28]),
                    old_bytes=bytes([0x88]),
                    comment="Change button mask from Up (0x08) to Up+SELECT (0x28) — byte 2",
                ),
            ]
        return edits
