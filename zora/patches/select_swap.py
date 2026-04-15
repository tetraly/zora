"""
Select Button Item Swap.

Patches the pause menu to allow switching the equipped B-button item via
the SELECT button while paused.

Two variants:
  Swap   — Pressing SELECT while paused jumps directly to item slot 7
            (the last slot). Smaller patch: 23 bytes of code + 3-byte
            trampoline.
  Toggle — Pressing SELECT while paused cycles between two item pages.
            Also patches the pause menu display to show SWAP/PAUSE labels
            and renders item page contents during display. Larger patch
            spanning multiple ROM regions.
"""
from flags.flags_generated import SelectSwapMode
from zora.game_config import GameConfig
from zora.patches.base import RomEdit, VariableBehaviorPatch

# NES tile encoding for pause-menu labels used by the Toggle variant.
# "SWAP " -> S=0x1C, W=0x20, A=0x0A, P=0x19, space=0x24
_SWAP_TILES  = bytes([0x1C, 0x20, 0x0A, 0x19, 0x24])
# "PAUSE" -> P=0x19, A=0x0A, U=0x1E, S=0x1C, E=0x0E
_PAUSE_TILES = bytes([0x19, 0x0A, 0x1E, 0x1C, 0x0E])


class SelectSwap(VariableBehaviorPatch):

    def is_active(self, config: GameConfig) -> bool:
        return config.select_swap_mode != SelectSwapMode.PAUSE

    def test_only_get_all_variant_edits(self) -> list[RomEdit]:
        return self._swap_edits() + self._toggle_edits()

    def get_edits_for_config(self, config: GameConfig, rom_version: int | None = None) -> list[RomEdit]:
        if config.select_swap_mode == SelectSwapMode.SWAP:
            return self._swap_edits()
        return self._toggle_edits()

    def _swap_edits(self) -> list[RomEdit]:
        # EnableHotKey variant: jump directly to item slot 7 on SELECT press.
        return [
            # Main hot-key routine at 0x1FFD0 (23 bytes, all unused/FF in vanilla).
            # LDA #$05; JSR $FFAC   — load controller and call check routine
            # LDA $0656             — read button state
            # CMP #$0F              — compare to SELECT bitmask
            # BNE +2                — skip if not SELECT
            # LDA #$07              — load item index 7
            # TAY
            # LDA #$01
            # JSR $B7C8             — apply item switch
            # JMP $EC58             — return to main loop
            RomEdit(
                offset=0x1FFD0,
                new_bytes=(
                    "A9 05 20 AC FF "
                    "AD 56 06 "
                    "C9 0F "
                    "D0 02 "
                    "A9 07 "
                    "A8 "
                    "A9 01 "
                    "20 C8 B7 "
                    "4C 58 EC"
                ),
                old_bytes="FF " * 22 + "FF",
                comment="Hot-key routine: SELECT while paused jumps to item slot 7",
            ),
            # Trampoline JMP at 0x1EC4C (CPU addr 0x1EC3C + 0x10 header) (3 bytes, non-FF in vanilla).
            # JMP $FFC0 — redirect pause-menu controller poll to our routine.
            RomEdit(
                offset=0x1EC4C,
                new_bytes="4C C0 FF",
                old_bytes="A5 E0 49",
                comment="Trampoline: redirect pause poll to hot-key routine at $FFC0",
            ),
        ]

    def _toggle_edits(self) -> list[RomEdit]:
        # EnableHotKey2 variant: cycle between two item pages on SELECT press,
        # with SWAP/PAUSE labels rendered on the pause menu.
        edits: list[RomEdit] = []

        # Block 1: Main hot-key routine at 0x1FFD0 (20 bytes, all FF in vanilla).
        # LDA #$05; JSR $FFAC   — load controller
        # LDA $067B             — read page toggle state
        # BEQ +7                — if page 0, skip to $85A0 (vanilla handler)
        # LDA $E0               — read current item index
        # EOR #$01              — flip bit 0 (toggle between two slots)
        # JMP $EC40             — apply new item selection
        # JMP $85A0             — fallthrough to vanilla handler
        edits.append(RomEdit(
            offset=0x1FFD0,
            new_bytes=(
                "A9 05 20 AC FF "
                "AD 7B 06 "
                "F0 07 "
                "A5 E0 "
                "49 01 "
                "4C 40 EC "
                "4C A0 85"
            ),
            old_bytes="FF " * 19 + "FF",
            comment="Toggle hot-key: SELECT cycles between item pages",
        ))

        # Block 2: Secondary controller check at 0x145B0 (18 bytes, all FF in vanilla).
        # LDA $0656; CMP #$0F; BNE +2; LDA #$07; TAY; LDA #$01; JSR $B7C8; JMP $EC58
        edits.append(RomEdit(
            offset=0x145B0,
            new_bytes=(
                "AD 56 06 "
                "C9 0F "
                "D0 02 "
                "A9 07 "
                "A8 "
                "A9 01 "
                "20 C8 B7 "
                "4C 58 EC"
            ),
            old_bytes="FF " * 17 + "FF",
            comment="Secondary SELECT check: route to item-switch subroutine",
        ))

        # Block 3: Trampoline JMP at 0x1EC4C (3 bytes, non-FF in vanilla).
        edits.append(RomEdit(
            offset=0x1EC4C,
            new_bytes="4C C0 FF",
            old_bytes="A5 E0 49",
            comment="Trampoline: redirect pause poll to toggle routine at $FFC0",
        ))

        # Block 4a: Item cycle routine, first 16 bytes at 0x153C0 (all FF in vanilla).
        # LDA $F8; AND #$20; BEQ +31; LDA $067B; EOR #$01; STA $067B; BEQ +2; LDA #$08
        edits.append(RomEdit(
            offset=0x153C0,
            new_bytes="A5 F8 29 20 F0 1F AD 7B 06 49 01 8D 7B 06 F0 02",
            old_bytes="FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF",
            comment="Item cycle routine part 1 (bytes 0-15, unused ROM)",
        ))

        # Block 4b: Item cycle routine, remaining 28 bytes at 0x153D0 (all FF in vanilla).
        # LDA #$08; CLC; ADC #$93; STA $00; LDA #$93; STA $01; LDY #$05;
        # LDA ($00),Y; STA $0100,Y; DEY; BPL -8; LDA $F8; AND #$10; JMP $80F7
        edits.append(RomEdit(
            offset=0x153D0,
            new_bytes=(
                "A9 08 "
                "18 "
                "69 93 "
                "85 00 "
                "A9 93 "
                "85 01 "
                "A0 05 "
                "B1 00 "
                "99 00 01 "
                "88 "
                "10 F8 "
                "A5 F8 "
                "29 10 "
                "4C F7 80"
            ),
            old_bytes="FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF",
            comment="Item cycle routine part 2 (bytes 16-43, unused ROM)",
        ))

        # Block 5: Secondary trampoline at 0x14103 (3 bytes, non-FF in vanilla).
        # JMP $93B0
        edits.append(RomEdit(
            offset=0x14103,
            new_bytes="4C B0 93",
            old_bytes="A5 F8 29",
            comment="Secondary trampoline: JMP $93B0 for item cycle",
        ))

        # Block 6: Bank-switch trampoline at 0x16CA6 (3 bytes, all FF in vanilla).
        # JSR $AC30
        edits.append(RomEdit(
            offset=0x16CA6,
            new_bytes="20 30 AC",
            old_bytes="FF FF FF",
            comment="Bank-switch trampoline: JSR $AC30",
        ))

        # Block 7: PPU copy routine at 0x16C40 (45 bytes, all FF in vanilla).
        edits.append(RomEdit(
            offset=0x16C40,
            new_bytes=(
                "AD 00 01 "
                "D0 01 "
                "60 "
                "A9 29 "
                "8D 36 03 "
                "A9 84 "
                "8D 37 03 "
                "A9 05 "
                "8D 38 03 "
                "A9 FF "
                "8D 3E 03 "
                "A0 00 "
                "B9 00 01 "
                "99 39 03 "
                "A9 00 "
                "99 00 01 "
                "C8 "
                "C0 05 "
                "D0 F0 "
                "60"
            ),
            old_bytes="FF " * 44 + "FF",
            comment="PPU copy routine for pause-menu item page display",
        ))

        # Block 8: Pause-menu item display at 0x19FD0 (31 bytes, all FF in vanilla).
        edits.append(RomEdit(
            offset=0x19FD0,
            new_bytes=(
                "8A "
                "C9 30 "
                "D0 17 "
                "AD 7B 06 "
                "F0 0A "
                "A9 F0 "
                "85 00 "
                "A9 9F "
                "85 01 "
                "D0 08 "
                "A9 E0 "
                "85 00 "
                "A9 9F "
                "85 01 "
                "4C F6 A0"
            ),
            old_bytes="FF " * 30 + "FF",
            comment="Pause-menu display: select page pointer based on toggle state",
        ))

        # Block 9: JSR trampoline at 0x1A09C (3 bytes, non-FF in vanilla).
        # JSR $9FC0
        edits.append(RomEdit(
            offset=0x1A09C,
            new_bytes="20 C0 9F",
            old_bytes="20 F6 A0",
            comment="JSR trampoline to pause-menu display routine at $9FC0",
        ))

        # Single-byte patches: display pointer high/low/length bytes for SWAP/PAUSE
        # labels. All are in unused ROM (FF) in vanilla.
        # The length-byte write at 0x153AB is omitted because it is
        # superseded by the PAUSE tile write below (PAUSE[0] overwrites it).
        for offset, byte_val in [
            (0x153A9, 0x29), (0x153A0, 0x29),  # high bytes (0x29 = PPU nametable hi)
            (0x1A000, 0x29), (0x19FF0, 0x29),
            (0x153AA, 0x84), (0x153A1, 0x84),  # low bytes (0x84)
            (0x1A001, 0x84), (0x19FF1, 0x84),
            (0x153A2, 0x05),                    # length byte (5 chars) — SWAP group
            (0x1A002, 0x05),                    # length byte (5 chars) — mirror
            (0x19FF2, 0x05),                    # length byte (5 chars) — mirror 2
        ]:
            edits.append(RomEdit(
                offset=offset,
                new_bytes=bytes([byte_val]),
                old_bytes=bytes([0xFF]),
                comment=f"Label display pointer byte at 0x{offset:05X}",
            ))

        # SWAP tile data at 0x153A3-0x153A7 and mirror 0x19FF3-0x19FF7
        for i, tile in enumerate(_SWAP_TILES):
            edits.append(RomEdit(
                offset=0x153A3 + i,
                new_bytes=bytes([tile]),
                old_bytes=bytes([0xFF]),
                comment=f"SWAP tile [{i}] at 0x{0x153A3+i:05X}",
            ))
            edits.append(RomEdit(
                offset=0x19FF3 + i,
                new_bytes=bytes([tile]),
                old_bytes=bytes([0xFF]),
                comment=f"SWAP tile [{i}] mirror at 0x{0x19FF3+i:05X}",
            ))

        # PAUSE tile data at 0x153AB-0x153AF and mirror 0x1A003-0x1A007
        # Note: 0x153AB was already written as part of the pointer byte above (0x05).
        # The PAUSE string overwrites it starting at 0x153AB.
        for i, tile in enumerate(_PAUSE_TILES):
            edits.append(RomEdit(
                offset=0x153AB + i,
                new_bytes=bytes([tile]),
                old_bytes=bytes([0xFF]),
                comment=f"PAUSE tile [{i}] at 0x{0x153AB+i:05X}",
            ))
            edits.append(RomEdit(
                offset=0x1A003 + i,
                new_bytes=bytes([tile]),
                old_bytes=bytes([0xFF]),
                comment=f"PAUSE tile [{i}] mirror at 0x{0x1A003+i:05X}",
            ))

        # Terminator bytes (0xFF written to unused ROM — no-op edits, omit)
        # rom[86961]=FF, rom[86952]=FF, rom[106488]=FF, rom[106504]=FF are already FF.

        return edits
