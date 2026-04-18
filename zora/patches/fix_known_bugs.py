"""
Fix Known Bugs.

Applies a collection of vanilla ROM bug fixes: scrolling glitch, continue
screen, enemy kill counter, enemy sprite rendering, quest mode check, enemy
flash/pause routine, and sound engine fixes.

Assumes reduceFlashing=True: bytes 9-10 of the bug fix routine at 0x7761
are patched to NOP/NOP (0xEA 0xEA) instead of STY/value.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


class FixKnownBugs(BehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.fix_known_bugs

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        return [
            # Bug fix routine (12 bytes); bytes 9-10 are NOP/NOP (reduceFlashing=True)
            RomEdit(
                offset=0x7761,
                new_bytes=bytes([72, 173, 2, 3, 201, 255, 208, 2, 0xEA, 0xEA, 104, 96]),
                old_bytes=bytes([0xFF] * 12),
                comment="Bug fix routine (reduceFlashing NOP/NOP variant)",
            ),
            # JMP patch redirecting into the bug fix routine
            RomEdit(
                offset=0x61A3,
                new_bytes=bytes([76, 81, 183]),
                old_bytes=bytes([0x84, 0x14, 0x60]),
                comment="JMP redirect to bug fix routine",
            ),
            # Continue screen fix routine (12 bytes)
            RomEdit(
                offset=0xEBF0,
                new_bytes=bytes([165, 255, 41, 251, 133, 255, 141, 0, 32, 76, 68, 128]),
                old_bytes=bytes([0xFF] * 12),
                comment="Continue screen fix routine",
            ),
            # JSR redirect into continue screen fix
            RomEdit(
                offset=0x1E99E,
                new_bytes=bytes([32, 224, 171]),
                old_bytes=bytes([0x20, 0x44, 0x80]),
                comment="JSR redirect to continue screen fix",
            ),
            # Enemy kill counter fix (10 bytes) and its JSR redirect at 0x6BFB are
            # identical to the ProgressiveItems patch stub — those edits are omitted
            # here to avoid conflicts; ProgressiveItems installs the same bytes.
            # RTS patch: fixes bug in enemy spawn routine (PRG Bank 4)
            RomEdit(
                offset=0x12DA1,
                new_bytes=bytes([0x60]),
                old_bytes=bytes([0xEE]),
                comment="RTS patch for enemy spawn routine bug",
            ),
            # Enemy sprite fix routine (55 bytes)
            RomEdit(
                offset=0x16FD9,
                new_bytes=bytes([
                    165, 236, 48, 11, 73, 128, 205, 161, 107, 208, 9,
                    164, 16, 240, 5, 133, 236, 76, 71, 181,
                    76, 89, 181, 172, 187, 107, 185, 241, 175, 133, 152,
                    185, 246, 175, 133, 112, 185, 251, 175, 96,
                    0, 4, 8, 1, 2, 120, 120, 120, 0, 240,
                    141, 61, 221, 141, 141,
                ]),
                old_bytes=bytes([0xFF] * 55),
                comment="Enemy sprite fix routine",
            ),
            # JSR redirect to enemy sprite fix
            RomEdit(
                offset=0x1705C,
                new_bytes=bytes([32, 224, 175]),
                old_bytes=bytes([0xAD, 0xA6, 0x6B]),
                comment="JSR redirect to enemy sprite fix routine",
            ),
            # JMP redirect (enemy sprite path)
            RomEdit(
                offset=0x17553,
                new_bytes=bytes([76, 201, 175]),
                old_bytes=bytes([0xA5, 0xEC, 0x10]),
                comment="JMP redirect (enemy sprite path)",
            ),
            # JSR redirect (enemy sprite path, overlapping address)
            RomEdit(
                offset=0x17550,
                new_bytes=bytes([32, 192, 184]),
                old_bytes=bytes([0x20, 0x2F, 0x75]),
                comment="JSR redirect (enemy sprite path)",
            ),
            # Quest mode check routine (11 bytes): LDA $0522, CMP #$01, BEQ +3, JMP $752F, RTS
            RomEdit(
                offset=0x178D0,
                new_bytes=bytes([173, 34, 5, 201, 1, 240, 3, 76, 47, 117, 96]),
                old_bytes=bytes([0xFF] * 11),
                comment="Quest mode check routine",
            ),
            # Enemy flash/pause routine (38 bytes)
            RomEdit(
                offset=0x14ABD,
                new_bytes=bytes([
                    173, 206, 4, 240, 21, 165, 84, 208, 17, 169, 8, 133, 14,
                    37, 238, 240, 10, 70, 14, 165, 14, 208, 246, 141, 206, 4,
                    96, 165, 14, 133, 2, 32, 246, 163, 201, 7, 208, 235,
                ]),
                old_bytes=bytes([
                    0xAD, 0xCE, 0x04, 0xF0, 0x10, 0xA9, 0x08, 0x85, 0x0E, 0xA5, 0x0E,
                    0x25, 0xEE, 0xF0, 0x0C, 0x46, 0x0E, 0xA5, 0x0E, 0xD0, 0xF4, 0xA9,
                    0x00, 0x8D, 0xCE, 0x04, 0x60, 0xA5, 0x0E, 0x85, 0x02, 0x20, 0xF6,
                    0xA3, 0xC9, 0x07, 0xD0, 0xE9,
                ]),
                comment="Enemy flash/pause routine",
            ),
            # JSR redirect to sound engine fix trampoline at $AC90 (ROM 0x16CA0).
            # The trampoline calls the original routine at $6D50, then returns.
            # WARNING: This redirect and the trampoline below are a paired unit —
            # do not enable one without the other or the game will jump to 0xFF bytes.
            RomEdit(
                offset=0x65A1,
                new_bytes=bytes([32, 144, 172]),
                old_bytes=bytes([0x20, 0x50, 0x6D]),
                comment="JSR redirect to sound engine fix trampoline at $AC90",
            ),
            # Sound engine fix trampoline (10 bytes): JSR $6D50, NOP x6, RTS
            RomEdit(
                offset=0x16CA0,
                new_bytes=bytes([32, 80, 109, 234, 234, 234, 234, 234, 234, 96]),
                old_bytes=bytes([0xFF] * 10),
                comment="Sound engine fix trampoline",
            ),
        ]
