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

[[segment]]                 # each segment of the routines, in a bank's free space
name = "ZORA_FP_FIX_06"
bank = 5
start = 0xB8A0              # CPU address; docs/rom-map.md records the slot

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

To add a patch:
1. Create its folder.
2. Add its name to `series.txt`.
3. Record its segments in `docs/rom-map.md`.
4. Use `locate` for each hook's offset and length.
