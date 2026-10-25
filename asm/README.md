# asm/: ZORA's 6502 patches

Everything here is code ZORA wrote. No disassembly text and no byte of the original game
is tracked. The builders fetch the pinned disassembly from git (AGENTS.md "Disassembly pin":
aldonunez/zelda1-disassembly at a fixed commit, read with `git archive` from the clone at
`../zelda1-disassembly`, never its working tree). They check that it rebuilds the player's
PRG0 ROM, apply ZORA's patches to that fetched copy in `temp/`, and assemble it with
ca65/ld65. The game bytes a patch keeps or moves are recorded as `Original` pieces and read
from the player's ROM when a ROM is written (`zora/rom/base_rom.py`).

## The disassembly

The builders need a clone of the public disassembly,
https://github.com/aldonunez/zelda1-disassembly. They read only its pinned commit (the
`DISASSEMBLY_COMMIT` in `scripts/asm_patches.py`), through git, so the clone may be on any
branch or hold any edits. By default they look next to this repo:

```
git clone https://github.com/aldonunez/zelda1-disassembly ../zelda1-disassembly
```

To use a clone somewhere else, set `ZORA_DISASSEMBLY` to its path. If the clone or the
commit is missing, a build stops with a message saying how to fix it. The tests that need
it (or ca65/ld65) skip. The generated data in `zora/rom/` is committed, so ZORA itself
runs without any of this.

## Layout

```
asm/
  series.txt              the code patches, in build order
  fp-fix-06/              one folder per patch
    patch.toml            segments, imports/exports, hooks
    bank_05.s             ZORA's routines that join bank 5's source file (Z_05.asm)
  ...
  fp-stats-01/            the statistics screen: a player setting's patch, built by asm/settings/build.py
  settings/               the player-setting choices (docs/player-settings-patches.md)
    build.py              builds asm/settings/player_settings_data.py
    music-off/            one folder per choice that differs from ZORA's code
  progressive/            the progressive patches' test harness (docs/progressive-patches.md)
    build.py              builds asm/progressive/progressive_data.py
  flags2/                 the ZORA 2.0 flag patches, not wired (asm/flags2/README.md)
    build.py              builds asm/flags2/flags2_data.py
  asnb/                   All Swords No Boards' ROM side, not wired (asm/asnb/README.md)
    build.py              builds asm/asnb/asnb_data.py
```

```
asm/
  rom_space.toml          PRG0's free space, z1rr-coop's reservations, every segment's slot, the bytes
                          ZORA's Python writes in free space, and the bytes two owners may share
  rom_space.py            reads it: the overlap check and the placement of new segments
  placements.toml         where the build placed each segment that leaves out `start` (the lock file)
```

`scripts/asm_patches.py` builds the series into `zora/rom/code_patch_data.py`.

## A patch folder

### `bank_NN.s`: routines

The patch's routines, in ca65 syntax, each in its own segment:

```
.SEGMENT "ZORA_FP_FIX_06"

CheckMazesUnlessWhirlwind:
    LDA WhirlwindTeleportingState
    ...
```

The builder appends the file to bank NN's source file (`Z_NN.asm`) of the fetched
disassembly. The routines therefore see that file's labels, its includes and its imports
by name.

### `patch.toml`

```toml
# ZORA FP-FIX-06: what the patch does, in one or two lines.

# Optional: build another folder's bank_NN.s into this patch's own segments and hooks
# (asm/fp-stats-01-music builds asm/fp-stats-01's this way).
# routines_from = "../fp-stats-01"

[[segment]]                 # each segment of the routines, in a bank's free space
name = "ZORA_FP_FIX_06"
bank = 5
start = 0xB8A0              # CPU address; asm/rom_space.toml records the slot

[[segment]]                 # a new segment leaves out `start`: the build places it
name = "ZORA_FP_NEW_01"
bank = 5                    # or banks = [7, 3]: any one of them, tried in order
size = 0x40                 # the slot: room for the code to grow without moving
# align = 0x10              # the default

[imports]                   # .IMPORT lines added to a bank's file (other banks' symbols)
bank_07 = ["TransferLevelPatternBlocksPlus1"]

[exports]                   # .EXPORT lines added to a bank's file
bank_03 = ["TransferLevelPatternBlocksPlus1"]

[[hook]]                    # ZORA's code in place of PRG0's instructions
name = "maze-check"
offset = 0x17550            # headered file offset of the first replaced byte
length = 3                  # bytes replaced
note = "CalculateNextRoomForDoor calls CheckMazesUnlessWhirlwind for its overworld maze check."
code = """
    JSR CheckMazesUnlessWhirlwind
"""
```

A hook stores no original bytes. It gives only where (offset and length) and ZORA's
replacement (its code). The builder maps the offset to the source lines that assemble
there, using the debug info of the build before the patch. It checks that those lines
cover exactly `length` bytes of whole instructions or data. It then replaces them with
`code`, which is assembled in place, so it may use the routine's local labels
(`@FlagBReady`) and anonymous labels (`:+`).

- **Same length.** Code of the same length as the bytes it replaces (pad with `NOP`, or
  `.RES n, $EA`) keeps every following byte where it was. Almost every hook works this way.
- **Insertion.** A hook with `length = 0` inserts its code before the instruction at
  `offset`.
- **Removal.** A hook with no `code` removes the instructions.

  Together, an insertion and a removal move the code between them. fp-fix-05 does this
  inside `CheckShutters`. The moved bytes are recorded as an `Original` piece.

Hooks of one patch must not overlap. Hooks of different patches never touch the same byte
(`tests/test_asm_patches.py`).

### A player-setting choice

A choice folder in `asm/settings/` has the same format, applied on top of the ZORA build.
It may also change the series it is built on:

```toml
[series]
leave_out = ["fp-hot-01.item-screen"]           # series hooks left out: PRG0's code stays

[series.routines]                                 # a series patch's routine file, replaced
"fp-hot-01/bank_02.s" = "replaces-fp-hot-01-bank_02.s"
```

## Commands

```
python3 scripts/asm_patches.py build             # rebuild zora/rom/code_patch_data.py
python3 scripts/asm_patches.py check             # exit 1 if it is out of date
python3 scripts/asm_patches.py edit NAME         # the sources with the series through NAME, in temp/asm/edit/src
python3 scripts/asm_patches.py refresh NAME      # check NAME applies; list its hook sites
python3 scripts/asm_patches.py locate Z_05.asm 7514   # a source line's file offset and length, for a new hook
python3 asm/settings/build.py build|check|edit CHOICE|refresh CHOICE
python3 asm/progressive/build.py build|check
python3 asm/flags2/build.py build|check|edit NAME|refresh NAME
python3 asm/asnb/build.py build|check|edit NAME|refresh NAME
```

To change a patch, edit its folder, run `build`, and run the tests. `edit` writes the
patched sources to `temp/asm/edit/src` so you can read a hook in context. Never edit that
copy, and never copy disassembly lines into this folder. Every other build works in a
scratch folder of its own under `temp/`, removed when it ends, so builds running at the
same time never collide.

## Adding a patch

1. Create its folder with `patch.toml` and its `bank_NN.s` files. Give each segment a `name`, a
   `bank` (or `banks`, or `mirrored`, below) and a `size`, its slot: the most bytes it may grow to.
   Leave out `start`.
2. Add its name to `series.txt` (a ZORA flag patch goes in `asm/flags2/`, an ASNB patch in
   `asm/asnb/`; a player-setting choice goes in `asm/settings/` and names its setting,
   `owner = "setting:SETTING"`).
3. Use `locate` for each hook's offset and length.
4. Run the builder's `build`. It places each new segment at the lowest address (aligned to `align`,
   default $10) where `size` bytes are free in PRG0 and claimed by nothing in `rom_space.toml`, no
   other slot, no z1rr-coop reservation, no site, no earlier placement. The builders load their
   patches in a fixed order (series order, then each builder's own), so the result does not depend
   on who builds. It records the placement in `placements.toml`.
5. Commit `placements.toml` with the patch. Every later build keeps the recorded address, so a patch
   added after yours never moves it. A segment whose `size` or banks change no longer matches its row
   and the build stops: delete the row to place it again, which changes its bytes on purpose (a
   changelog line).
6. Run the tests. `tests/test_rom_space.py` runs the overlap check: two owners may write the same
   byte only where a `[[shared]]` row of `rom_space.toml` names both (a hook on another patch's code,
   a setting choice rewriting ZORA's code, InitLinkSpeed's writers), and a patch's bytes in free space
   stay inside its slot or placement.
7. Add a row for each segment and hook to `docs/rom-map.md` (the test checks that each slot,
   placement and site range is written there).

A segment with `start` keeps its address; the existing patches all do, with a `[[slot]]` row in
`rom_space.toml` each. Bytes ZORA's Python writes in free space (a per-seed table, a flag's routine)
are a `[[site]]` row there, named after the module constant that holds the address.

### Segments in several banks

`banks = [7, 3]` places the segment in the first listed bank that has room (code that may run from
either). `mirrored = [0, 1, 2, 3, 4, 5, 6]` places one copy at the same address in each bank, for
code that runs with any of them switched in: its routines go in `mirrored.s`, appended to each bank's
file with `{BANK}` replaced by the bank number, and its segment in each bank is NAME_B<bank>:

```
.SEGMENT "ZORA_FP_NEW_02_B{BANK}"
LookUpItemSlot:
    ...
```

There is no such window today in all of banks 0-6: bank 1's free space is full from $B770 (the
extended hint text, then fp-prog-01), banks 0, 2 and 4 share no free 16 bytes elsewhere, and
$BFC0-$BFF9, free in every bank, is ASNB's. A window there needs room made first (docs/reports/research-ap-item-codes-and-deathlink.md).
