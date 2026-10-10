# asm/asnb/: All Swords No Boards, the ROM side

The ROM changes of the owner's ASNB design (docs/design/asnb.md section 3), one folder each, in
asm/'s format (asm/README.md). `build.py` applies each one on its own on top of asm/series.txt
(fp-prog-01 and fp-prog-02 included) and writes `asnb_data.py`, which imports `.base_rom`
relatively: zora/rom/asnb_patch_data.py is its verbatim copy, from which
zora/rom/owner_patches.py writes take-l4 and sword-cap (switch $01) with Add L4 Sword on, and
level-9-gate with Level 9 Entrance = Level 4 sword.

| Patch | Design | Sites (headered file offsets) |
|---|---|---|
| `take-l4` | 3a: level 4 from any pickup | 0x06D04 (5 bytes): `HandleClass2`'s `LDA $0A / CMP Items, Y` becomes `JSR TakeGradeWithL4` + 2 NOPs; `TakeGradeWithL4` (21 bytes) at $BFE0 in each of banks 0-6 (0x03FF0 + N x 0x4000) |
| `sword-cap` | 3b: the sword line tops out at level 4 | 0x07F30, 0x13949, 0x17B49 (4 bytes each, becoming 14): `@Fits` in each `ResolveProgressive` copy; per-seed operands `ZORA_B1_SwordLineToL4` 0x07F33, `ZORA_B4_SwordLineToL4` 0x1394C, `ZORA_B5_SwordLineToL4` 0x17B4C |
| `level-9-gate` | 3c: level 9 opens for sword level 4 | 0x04AB1 (7 bytes): `InitUnderworldPersonC`'s `LDA InvTriforce / CMP #$FF / BNE @Exit` becomes `LDA InvSword / CMP #$04 / BCC @Exit` |

docs/rom-map.md has the rows ("All Swords No Boards").

## take-l4

Every pickup path ends in TakeItem's graded store: caves, shops, dungeon rooms and cellars, the
coast, the Armos and dropped items. `TakeGradeWithL4` returns the grade to store, with the flags
of its compare with `Items, Y` for the `BCC` and `STA Items, Y` that follow the hook: level 4 for
the magical sword (grade 3) taken at sword level 3, the grade taken otherwise. It keeps X and Y.

TakeItem is part of the common code `CopyCommonCodeToRam` copies to work RAM ($6C90), and runs
there with whichever of banks 0-6 is switched in, so each holds the routine at the same address.

**Address.** Banks 0-6 are all $FF at $BFC0-$BFF9, between the ISR copy's code ($BF50-$BFBF)
and the vectors ($BFFA): the free-space table of docs/rom-map.md, z1rr-coop's reserved ranges
(none there), the level encoding's region and sites (bank 6 $8400-$92FF and two sites below
$8080) and every other ZORA patch were checked (tests/test_asnb_patches.py). The one collision is
the design's $BFC0 itself: bank 1's $BFC0-$BFCE is l4-sword-take's `RaiseSwordToL4` (asm/flags2/,
written by Add L4 Sword today). So the copies sit at **$BFE0-$BFF4** (21 of 26 bytes), and
take-l4 and l4-sword-take share no byte. Written together they also agree: whichever raises the
sword to 4 first, the other then finds level 4 and does nothing.

**Retiring l4-sword-take (the wiring step).** Once the Add L4 Sword setting writes take-l4 (both
settings, Level 2 and Level 9), it stops writing l4-sword-take. That frees:

- bank 7 $FF43-$FF4C (0x1FF53-0x1FF5C, `TakeRoomItemForL4Sword`; with $FF4D-$FF4F the whole
  13-byte gap) and the hook at 0x06BEB (TryTakeItem's `JSR SetRoomFlagUWItemState` is PRG0's
  again);
- bank 1 $BFC0-$BFCE (0x07FD0-0x07FDE, `RaiseSwordToL4`; with the rest, $BFC0-$BFDF).

Then: drop `l4-sword-take` from asm/flags2/build.py's PATCHES and FREE_SPACE (its folder and
README row go), rebuild flags2_data.py and its zora/rom/ copy, remove the patch from the owner
patches' writer, mark the bank 7 and bank 1 rows free in docs/rom-map.md, and update
tests/test_flags2_emulator.py's l4-sword-take case. take-l4
does not move: $BFC0-$BFDF stays free in banks 0-6 for later use.

## sword-cap

**Behaviour.** With the per-seed byte $01, at sword level 3 a sword item shows the magical sword
($03) but not as the line's top: a shop still sells it, and a cave or room gives it (take-l4 then
gives level 4). At sword level 4 it shows $03 as the top: a shop hides it, and taken elsewhere it
changes nothing. Every other line is unchanged. With $00 the routine behaves as fp-prog's.

**The byte (the design's open item 1).** A separate byte, not Progressive Items' on/off byte.
`ZORA_B1_ProgressiveItems` is in bank 1; the bank 4 and 5 copies run with their own bank switched
in and never read it (fp-prog-02 is left out when Progressive Items is off). A byte all three
could read would need bank 7, whose free space is nearly gone, or new RAM, which the design rules
out. So each copy carries the switch as the operand of its own `CMP #`: one per-seed value,
written to three places (`SYMBOLS` in asnb_data.py), $01 with Add L4 Sword on and $00 otherwise.
The three copies stay byte-identical when the three operands agree.

**The code.** At `@Fits`, [00] holds the steps taken back from past the line's top and [01] the
line's slot (the sword's is 0). `CMP #byte` on the slot leaves the carry clear only for slot 0
with the byte $01, so `SBC #$00` then takes one step off the count; a count of 0 stays 0. 10 more
bytes per copy (81 to 91).

**Space (the design's open item 2).** The copies grow inside their slots, so nothing moves to a
new address: bank 1 `ZORA_FP_PROG_01_RESOLVE` 98 of 112 bytes, bank 4 `ZORA_FP_PROG_02_ARMOS`
113 of 256, bank 5 `ZORA_FP_PROG_02_ROOM` 145 of 256 (no move needed after the walk-back fix).

**Hooks inside ZORA's code.** The hooks' offsets are in the ZORA build, so a change to
fp-prog-01 or fp-prog-02 can move them; the build then stops (a hook off whole instructions, or
an operand label off its `CMP`), and tests/test_asnb_patches.py's fresh-build test fails. When it
is wired, the change can move into fp-prog-01's and fp-prog-02's routines themselves, with the
operand as a labelled per-seed byte like `ZORA_B1_ProgressiveItems`.

## level-9-gate

In place, no new space. The man's refusal is person text 34, written at 0x04546 (bank 1 $8536,
72 bytes; the pointer in `PersonTextAddrs` at 0x04054): FP-TRIF-01's `REFUSAL_TEXT_ADDRESS` in
zora/rom/layout.py, where the generator writes the ASNB refusal text.

## Commands

```
python3 asm/asnb/build.py build             # rebuild asm/asnb/asnb_data.py
python3 asm/asnb/build.py check             # exit 1 if it is out of date
python3 asm/asnb/build.py edit NAME         # the sources with NAME applied, in temp/asm-asnb/edit/src
python3 asm/asnb/build.py refresh NAME      # check NAME applies; list its hook sites
```

Tests: tests/test_asnb_patches.py (the module is current; the copies; each routine run on
tests/mini6502.py; no byte written by two patches; z1rr-coop's reserved bytes and the level
encoding's sites untouched; ZORA's output holds the ZORA build where the patches write) and
tests/test_asnb_emulator.py (every pickup path at sword levels 0-4, the gate, save and reload).
