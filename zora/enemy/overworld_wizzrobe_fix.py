"""Behavior patch: 6502 ASM patches for Wizzrobe collision/spawn handling on overworld.

Applied when CaveGroups[3] (the overworld enemy group) contains enemy 36
(RED_WIZZROBE). These patches modify the NES engine so that Wizzrobes
render and behave correctly on overworld screens.

Source: EnemyShufflers.cs lines 1253-1287 (ChangeDungeonEnemyGroups).
Note: The C# is a port of decompiled C++ binary; comments there may be inaccurate.
"""

from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class OverworldWizzrobeFix(BehaviorPatch):
    """Patches NES engine code so Wizzrobes work correctly on overworld screens.

    Only active when overworld enemy shuffling places Wizzrobes (enemy 36)
    in the overworld group. The four patches modify collision detection and
    spawn logic at fixed ROM addresses.
    """

    def is_active(self, config: GameConfig) -> bool:
        # This patch is conditionally applied at runtime based on the
        # actual group assignment, not just config flags. The caller
        # should check whether the overworld group contains Wizzrobes
        # before applying. For the BehaviorPatch API, we gate on the
        # config flags that enable overworld enemy shuffling.
        return config.shuffle_enemy_groups and config.randomize_overworld_enemies

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            # Patch 1: ROM 0x11E4B — 18 bytes
            # Sprite position range check for Wizzrobe rendering.
            #   CMP #$9A
            #   BCC +14        ; skip if < $9A
            #   CMP #$CC
            #   BCC +6         ; branch if < $CC
            #   AND #$FC
            #   CMP #$E0
            #   BNE +4         ; skip if != $E0
            #   JMP $AFF5
            #   BRK
            RomEdit(
                offset=0x11E4B,
                old_bytes=(
                    b"\xEB\x9E\xB4\x98\x98\x29\x0C\xF0\x06"
                    b"\x98\x49\x0C\x95\x98\xA8\x98\x29\x03"
                ),
                new_bytes=(
                    b"\xC9\x9A\x90\x0E\xC9\xCC\x90\x06\x29\xFC"
                    b"\xC9\xE0\xD0\x04\x4C\xF5\xAF\x00"
                ),
                comment="Wizzrobe overworld sprite position range check",
            ),
            # Patch 2: ROM 0x13005 — 11 bytes
            # Kill-state branch for Wizzrobe spawning.
            #   LDA $0394,X
            #   BEQ +3         ; branch if kill state == 0
            #   JMP $9E17
            #   JMP $9EEB
            RomEdit(
                offset=0x13005,
                old_bytes=bytes([0xFF] * 11),
                new_bytes=(
                    b"\xBD\x94\x03\xF0\x03\x4C\x17\x9E\x4C\xEB\x9E"
                ),
                comment="Wizzrobe overworld kill-state dispatch",
            ),
            # Patch 3: ROM 0x13F10 — 41 bytes
            # Main Wizzrobe overworld collision handler. Calls three
            # subroutines, checks position bounds, then dispatches
            # based on kill state.
            #   JSR $9E58
            #   JSR $9E9D
            #   JSR $9F2C
            #   BCS +3
            #   JMP $9E57
            #   LDA $041F,X
            #   AND #$FC
            #   CMP #$B0
            #   BEQ +7
            #   CMP #$F4
            #   BCS +3
            #   JMP $9E3D
            #   LDA $0394,X
            #   BEQ +3
            #   JMP $9E17
            #   JMP $9EEB
            RomEdit(
                offset=0x13F10,
                old_bytes=bytes([0xFF] * 41),
                new_bytes=(
                    b"\x20\x58\x9E\x20\x9D\x9E\x20\x2C\x9F\xB0\x03"
                    b"\x4C\x57\x9E\xBD\x1F\x04\x29\xFC\xC9\xB0\xF0"
                    b"\x07\xC9\xF4\xB0\x03\x4C\x3D\x9E\xBD\x94\x03"
                    b"\xF0\x03\x4C\x17\x9E\x4C\xEB\x9E"
                ),
                comment="Wizzrobe overworld main collision/spawn handler",
            ),
            # Patch 4: ROM 0x12D2E — 3 bytes
            # Jump hook into the collision handler above.
            #   JSR $BF00
            RomEdit(
                offset=0x12D2E,
                old_bytes=b"\x20\x1D\x9E",
                new_bytes=b"\x20\x00\xBF",
                comment="Wizzrobe overworld collision hook (JSR $BF00)",
            ),
        ]
