"""
Fix Known Bugs.

Applies a collection of vanilla ROM bug fixes: scrolling glitch, continue
screen, enemy kill counter, enemy sprite rendering, quest mode check, enemy
flash/pause routine, and sound engine fixes.

B2 uses the STY $14 form (0x84 0x14) at bytes 8-9 of the routine at 0x7761,
matching the reference vanilla output (reduceFlashing=False). B6 (kill counter
stub) and B7 (JSR redirect) are installed here as a paired unit; they are
byte-equivalent to the edits ProgressiveItems would otherwise install.

Debug-only seam: ``_debug_disabled_fix_ids`` is a class-level frozenset of
VBR fix IDs (e.g. {"B14"}) that, when non-empty, suppresses the listed fixes.
This is intended for harness-driven bisection only — never set from user
config or flag-system code.
"""
from zora.game_config import GameConfig
from zora.patches.base import BehaviorPatch, RomEdit


# Each entry pairs a VBR fix ID (B-id) with a RomEdit. The fix_id is used by
# the debug seam to selectively disable fixes during bisection. Multiple edits
# may share a fix_id when they form a paired unit (routine + redirect).
_FIXES: list[tuple[str, RomEdit]] = [
    # B2: bug fix routine + JMP redirect to it.
    ("B2", RomEdit(
        offset=0x7761,
        new_bytes=bytes([72, 173, 2, 3, 201, 255, 208, 2, 0x84, 0x14, 104, 96]),
        old_bytes=bytes([0xFF] * 12),
        comment="Bug fix routine (STY $14 variant)",
    )),
    ("B2", RomEdit(
        offset=0x61A3,
        new_bytes=bytes([76, 81, 183]),
        old_bytes=bytes([0x84, 0x14, 0x60]),
        comment="JMP redirect to bug fix routine",
    )),
    # B3: continue screen fix routine + JSR redirect to it.
    ("B3", RomEdit(
        offset=0xEBF0,
        new_bytes=bytes([165, 255, 41, 251, 133, 255, 141, 0, 32, 76, 68, 128]),
        old_bytes=bytes([0xFF] * 12),
        comment="Continue screen fix routine",
    )),
    ("B3", RomEdit(
        offset=0x1E99E,
        new_bytes=bytes([32, 224, 171]),
        old_bytes=bytes([0x20, 0x44, 0x80]),
        comment="JSR redirect to continue screen fix",
    )),
    # B6/B7: enemy kill counter fix routine + JSR redirect (paired unit).
    # WARNING: never enable one without the other. Byte-equivalent to
    # ProgressiveItems' stub; ProgressiveItems omits these edits when
    # fix_known_bugs is active.
    ("B6", RomEdit(
        offset=0x1FFF4,
        new_bytes=bytes([0x8E, 0x02, 0x06, 0x8E, 0x72, 0x06, 0xEE, 0x4F, 0x03, 0x60]),
        old_bytes=bytes([0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x5A, 0x45, 0x4C]),
        comment="Enemy kill counter fix routine",
    )),
    ("B7", RomEdit(
        offset=0x6BFB,
        new_bytes=bytes([0x20, 0xE4, 0xFF]),
        old_bytes=bytes([0x8E, 0x02, 0x06]),
        comment="JSR redirect to enemy kill counter fix routine",
    )),
    # B8: RTS patch for enemy spawn routine bug (PRG Bank 4).
    ("B8", RomEdit(
        offset=0x12DA1,
        new_bytes=bytes([0x60]),
        old_bytes=bytes([0xEE]),
        comment="RTS patch for enemy spawn routine bug",
    )),
    # B9: enemy sprite fix routine + three redirects (paired unit).
    ("B9", RomEdit(
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
    )),
    ("B9", RomEdit(
        offset=0x1705C,
        new_bytes=bytes([32, 224, 175]),
        old_bytes=bytes([0xAD, 0xA6, 0x6B]),
        comment="JSR redirect to enemy sprite fix routine",
    )),
    ("B9", RomEdit(
        offset=0x17553,
        new_bytes=bytes([76, 201, 175]),
        old_bytes=bytes([0xA5, 0xEC, 0x10]),
        comment="JMP redirect (enemy sprite path)",
    )),
    ("B9", RomEdit(
        offset=0x17550,
        new_bytes=bytes([32, 192, 184]),
        old_bytes=bytes([0x20, 0x2F, 0x75]),
        comment="JSR redirect (enemy sprite path)",
    )),
    # B11: quest mode check routine (LDA $0522, CMP #$01, BEQ +3, JMP $752F, RTS).
    ("B11", RomEdit(
        offset=0x178D0,
        new_bytes=bytes([173, 34, 5, 201, 1, 240, 3, 76, 47, 117, 96]),
        old_bytes=bytes([0xFF] * 11),
        comment="Quest mode check routine",
    )),
    # B14: enemy flash/pause routine (38 bytes).
    ("B14", RomEdit(
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
    )),
    # B16: sound engine fix JSR redirect + trampoline (paired unit).
    # WARNING: never enable one without the other or the game will jump to 0xFF bytes.
    ("B16", RomEdit(
        offset=0x65A1,
        new_bytes=bytes([32, 144, 172]),
        old_bytes=bytes([0x20, 0x50, 0x6D]),
        comment="JSR redirect to sound engine fix trampoline at $AC90",
    )),
    ("B16", RomEdit(
        offset=0x16CA0,
        new_bytes=bytes([32, 80, 109, 234, 234, 234, 234, 234, 234, 96]),
        old_bytes=bytes([0xFF] * 10),
        comment="Sound engine fix trampoline",
    )),
    # ------------------------------------------------------------------
    # EXPERIMENTAL: testing entrance-direction hypothesis for B9 softlock.
    # See analysis/zero_flags_baseline/b9_investigation/probe_results.md
    # B9's runtime reads LevelInfo bytes 35 ($6BA1) and 61 ($6BBB) of each
    # block (OW + UW1..UW9). ZORA leaves them as stock 0xFF; reference
    # populates them with stable seed-independent values. Populating these
    # 19 differing slots tests whether B9's softlock disappears.
    # If confirmed, the proper fix is a separate BehaviorPatch — these
    # edits are scaffolding only.
    # ------------------------------------------------------------------
    # Byte 35 of each LevelInfo (CPU $6BA1) — UW1..UW9; OW already matches.
    ("EXP_B9_DIRS", RomEdit(offset=0x1942F, new_bytes=bytes([0x80]), old_bytes=bytes([0xFF]), comment="EXP UW1 byte35")),
    ("EXP_B9_DIRS", RomEdit(offset=0x1952B, new_bytes=bytes([0x80]), old_bytes=bytes([0xFF]), comment="EXP UW2 byte35")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19627, new_bytes=bytes([0x80]), old_bytes=bytes([0xFF]), comment="EXP UW3 byte35")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19723, new_bytes=bytes([0x85]), old_bytes=bytes([0xFF]), comment="EXP UW4 byte35")),
    ("EXP_B9_DIRS", RomEdit(offset=0x1981F, new_bytes=bytes([0x80]), old_bytes=bytes([0xFF]), comment="EXP UW5 byte35")),
    ("EXP_B9_DIRS", RomEdit(offset=0x1991B, new_bytes=bytes([0x80]), old_bytes=bytes([0xFF]), comment="EXP UW6 byte35")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19A17, new_bytes=bytes([0x81]), old_bytes=bytes([0xFF]), comment="EXP UW7 byte35")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19B13, new_bytes=bytes([0x81]), old_bytes=bytes([0xFF]), comment="EXP UW8 byte35")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19C0F, new_bytes=bytes([0x88]), old_bytes=bytes([0xFF]), comment="EXP UW9 byte35")),
    # Byte 61 of each LevelInfo (CPU $6BBB) — OW + UW1..UW9.
    ("EXP_B9_DIRS", RomEdit(offset=0x1934D, new_bytes=bytes([0x00]), old_bytes=bytes([0xFF]), comment="EXP OW  byte61")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19449, new_bytes=bytes([0x02]), old_bytes=bytes([0xFF]), comment="EXP UW1 byte61")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19545, new_bytes=bytes([0x02]), old_bytes=bytes([0xFF]), comment="EXP UW2 byte61")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19641, new_bytes=bytes([0x02]), old_bytes=bytes([0xFF]), comment="EXP UW3 byte61")),
    ("EXP_B9_DIRS", RomEdit(offset=0x1973D, new_bytes=bytes([0x02]), old_bytes=bytes([0xFF]), comment="EXP UW4 byte61")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19839, new_bytes=bytes([0x02]), old_bytes=bytes([0xFF]), comment="EXP UW5 byte61")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19935, new_bytes=bytes([0x02]), old_bytes=bytes([0xFF]), comment="EXP UW6 byte61")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19A31, new_bytes=bytes([0x02]), old_bytes=bytes([0xFF]), comment="EXP UW7 byte61")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19B2D, new_bytes=bytes([0x02]), old_bytes=bytes([0xFF]), comment="EXP UW8 byte61")),
    ("EXP_B9_DIRS", RomEdit(offset=0x19C29, new_bytes=bytes([0x02]), old_bytes=bytes([0xFF]), comment="EXP UW9 byte61")),
]


class FixKnownBugs(BehaviorPatch):

    # Debug-only seam for bisection. Set to a frozenset of VBR fix IDs to
    # suppress those fixes from the patch. Default empty set = full behavior.
    _debug_disabled_fix_ids: frozenset[str] = frozenset()

    def is_active(self, config: GameConfig) -> bool:
        return config.fix_known_bugs

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        disabled = self._debug_disabled_fix_ids
        return [edit for fix_id, edit in _FIXES if fix_id not in disabled]
