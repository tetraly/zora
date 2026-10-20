"""Tests that read or write a ROM at PRG0's file offsets, on a ROM of either release (docs/design/
prg1.md; zora/rom/revision.py). The PRG1 emulator checks run the emulator suites with
ZORA_VANILLA_ROM naming the PRG1 file (tests/test_feature_patches.py's `vanilla`), so their ROMs
have PRG1's layout, where some of PRG0's offsets hold other bytes.

The product reads and writes in PRG0's layout and moves the result back
(serialize_to_rom, apply_player_settings); these do the same for a test's own raw reads and
writes, and on a PRG0 ROM they are plain reads and writes.
"""
from collections.abc import Callable

from zora.rom.revision import Revision, back_to_revision, layout_of, moved_to_prg0_layout


def prg0_view(rom: bytes | bytearray) -> bytes:
    """The ROM as PRG0's offsets read it: a ROM made from PRG1 with its moved code and data back
    at PRG0's offsets; any other ROM as it is."""
    return moved_to_prg0_layout(bytes(rom)) if layout_of(bytes(rom)) is Revision.PRG1 else bytes(rom)


def written_in_prg0_layout(rom: bytes | bytearray, write: Callable[[bytearray], object]) -> bytes:
    """The ROM after `write`, which writes at PRG0's offsets: on a ROM made from PRG1 it writes
    in the PRG0 view, and each byte it changed goes to its PRG1 offset (revision.back_to_revision,
    as apply_player_settings does)."""
    image = prg0_view(rom)
    after = bytearray(image)
    write(after)
    if layout_of(bytes(rom)) is Revision.PRG1:
        return back_to_revision(bytes(rom), Revision.PRG1, image, bytes(after))
    return bytes(after)
