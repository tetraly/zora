"""Build the ZORA 2.0 flag patches (docs/design/zora-flags-2.0.md).

    python3 asm/flags2/build.py build           rebuild, write asm/flags2/flags2_data.py
    python3 asm/flags2/build.py check           rebuild, exit 1 if that module differs
    python3 asm/flags2/build.py edit NAME       write the sources with NAME applied to temp/asm-flags2/edit/src
    python3 asm/flags2/build.py refresh NAME    check NAME applies and list its hook sites
    python3 asm/flags2/build.py apply IN OUT NAME ...
                                                write IN with the named patches as OUT

Each patch is a folder asm/flags2/NAME/ (asm/README.md: ZORA's code only, no disassembly
text), applied on its own on top of asm/series.txt (the "ZORA build"). The patches are not
wired: ZORA's output does not change. Every patch is independent of the others, and no two of
them, nor any of them and a series patch or a player setting, write the same byte
(tests/test_flags2_patches.py).

A patch folder has hooks, segments and routines as in asm/, and may also have data edits,
for bytes the pinned disassembly includes as a binary (.INCBIN), where no source line can be
hooked: the overworld's screen layouts (RoomLayoutsOW). A data edit holds only ZORA's new
bytes:

    [[data]]
    offset = 0x154F8            # headered file offset
    bytes = "0C"                # the new bytes, hex
    note = "what it changes"

`build` assembles the ZORA build, then each patch on it, writes its data edits into the
image, and records what changed as pieces: ZORA's own bytes, or Original pieces for the bytes
of the original game a patch keeps, read from the player's ROM (never stored). It checks that
every data edit lies inside a binary include and that every new segment is in FREE_SPACE
(docs/rom-map.md), blank in the ZORA build.

This script imports scripts/asm_patches.py for its assembling and patch helpers and does not
change it; each build works in a scratch folder of its own (scripts/asm_patches.py's scratch()).
"""
import argparse
import importlib.util
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

REPO = Path(__file__).resolve().parents[2]
FLAGS2_DIR = REPO / "asm" / "flags2"
OUTPUT = FLAGS2_DIR / "flags2_data.py"
# `edit` writes the sources with a patch applied here, to read; builds use scratch folders.
EDIT_TREE = REPO / "temp" / "asm-flags2" / "edit"
sys.path.insert(0, str(REPO))

from zora.rom.base_rom import Original, Piece, piece_bytes, piece_length  # noqa: E402


def _builder() -> ModuleType:
    """scripts/asm_patches.py, loaded read-only for its helpers."""
    spec = importlib.util.spec_from_file_location("asm_patches_tool", REPO / "scripts" / "asm_patches.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _builder()

# The patches, by the document's section order.
PATCHES = (
    "l4-sword-beam",            # 2  Add L4 Sword: the beam (docs/design/l4-sword.md R13)
    "l4-sword-take",            # 2  Add L4 Sword: level 4 from a level-9 room item (R14)
    "raft-blocks",              # 3  Extra Raft Blocks
    "bracelet-blocks",          # 4  Extra Power Bracelet Blocks
    "fast-dungeon-scroll",      # 5  Speed Up Dungeon Transitions
    "fast-heart-fill",          # 6  Speed Up Heart Fill (credit: snarfblam)
    "recorder-pols-voice",      # 7  Recorder Kills Dungeon Pols Voice (credit: Stratoform)
    "four-potions",             # 8  Four Potion Inventory
    "auto-show-letter",         # 9  Auto Show Letter
    "like-like-rupees",         # 10 Like-Like Eats Rupees
    "magic-boomerang-damage",   # 11 Magical Boomerang Does 1 HP Damage
    "lost-hills",               # 12 Randomize Lost Hills
    "dead-woods",               # 13 Randomize Dead Woods
)

# Community members who wrote a feature (the document's credits; docs/credits.md).
CREDITS = {
    "fast-heart-fill": "snarfblam",
    "recorder-pols-voice": "Stratoform",
}


@dataclass(frozen=True)
class FreeSpace:
    """A free-space range a patch segment may take: bank and CPU addresses, inclusive
    (docs/rom-map.md "Free space in PRG0")."""
    bank: int
    first: int
    last: int

    def file_range(self) -> range:
        return range(tool.file_offset(self.first, self.bank), tool.file_offset(self.last, self.bank) + 1)


# Bank 4's gap runs $B46F-$BF4F: z1rr-coop reserves $B46F-$B882, fp-prog-02's Armos slot is
# $B900-$B9FF and the overworld red Wizzrobe routine (PS-EGRP-05) starts at $BF00. Bank 7's $FF43-$FF4F is its last
# free gap; bank 1's $BFC0-$BFF9 lies between the ISR copy's code and its vectors.
FREE_SPACE = {
    "ZORA_F2_POLS_VOICE": FreeSpace(4, 0xBA00, 0xBA3F),
    "ZORA_F2_L4_TAKE_FIXED": FreeSpace(7, 0xFF43, 0xFF4F),
    "ZORA_F2_L4_TAKE": FreeSpace(1, 0xBFC0, 0xBFDF),
}


@dataclass(frozen=True)
class DataEdit:
    """New bytes at a headered file offset, inside a binary include of the pinned disassembly."""
    offset: int
    data: bytes
    note: str


def data_edits(name: str) -> tuple[DataEdit, ...]:
    spec = tomllib.loads((FLAGS2_DIR / name / tool.PATCH_FILE).read_text())
    return tuple(DataEdit(edit["offset"], bytes.fromhex(edit["bytes"]), edit["note"])
                 for edit in spec.get("data", []))


def load_patch(name: str) -> Any:
    """asm/flags2/NAME/ as a patch (scripts/asm_patches.py's Patch; its data edits apart)."""
    return tool.load_patch(FLAGS2_DIR / name)


# --- building ---------------------------------------------------------------

def zora_tree(work: Path) -> Any:
    """The pinned sources with all of asm/series.txt applied, in `work`."""
    tree = tool.SourceTree(work)
    for name in tool.series():
        tree.apply(tool.series_patch(name))
    return tree


def binary_ranges() -> list[range]:
    """The headered file ranges the pinned disassembly includes as binaries (src/bins.xml)."""
    text = (tool.disassembly() / "src" / "bins.xml").read_text()
    return [range(tool.NES_HEADER_SIZE + int(match[1]), tool.NES_HEADER_SIZE + int(match[1]) + int(match[2]))
            for match in tool.BINS.finditer(text)]


def with_data(image: bytes, name: str, binaries: list[range]) -> bytes:
    """`image` with the patch's data edits written; each must lie inside one binary include."""
    out = bytearray(image)
    for edit in data_edits(name):
        end = edit.offset + len(edit.data)
        if not any(edit.offset in binary and end - 1 in binary for binary in binaries):
            raise SystemExit(f"{name}: data at 0x{edit.offset:05X} is not inside a binary include: hook it")
        out[edit.offset:end] = edit.data
    return bytes(out)


def patch_image(tree: Any, name: str, binaries: list[range]) -> bytes:
    """The ZORA build in `tree` with patch `name` applied (the tree is changed)."""
    image = bytes(tree.apply(load_patch(name)))
    return with_data(image, name, binaries)


def build_all() -> tuple[bytes, dict[str, list[tuple[int, Piece]]]]:
    """The ZORA build and each patch's writes against it."""
    base = zora_tree(tool.scratch("asm-flags2"))
    zora = bytes(base.image)
    original = tool.verify_base_rom().read_bytes()
    binaries = binary_ranges()
    writes: dict[str, list[tuple[int, Piece]]] = {}
    for name in PATCHES:
        tree = base.copy(tool.scratch(f"asm-flags2-{name}"))
        patched = patch_image(tree, name, binaries)
        check_segments(name, zora, patched, tree.src)
        writes[name] = tool.patch_pieces(zora, patched, original)
    return zora, writes


def check_segments(name: str, zora: bytes, patched: bytes, src: Path) -> None:
    """Every segment the patch adds is one of FREE_SPACE's, at its start and within its range
    (blank in the ZORA build), and the patch writes no other byte that is blank there."""
    config = (src / "Z.cfg").read_text()
    patch = load_patch(name)
    spaces = []
    for segment in patch.segments:
        space = FREE_SPACE.get(segment.name)
        if space is None or (segment.bank, segment.start) != (space.bank, space.first):
            raise SystemExit(f"{name}: segment {segment.name} is not one of FREE_SPACE's")
        if f"{segment.name}: load = ROM_{segment.bank:02d}" not in config:
            raise SystemExit(f"{name}: {segment.name} is not in Z.cfg")
        if any(zora[offset] != tool.FREE_SPACE_FILL for offset in space.file_range()):
            raise SystemExit(f"{name}: the ZORA build is not blank at {segment.name}'s range")
        spaces.append(space.file_range())
    for offset in range(len(zora)):
        if zora[offset] != patched[offset] and zora[offset] == tool.FREE_SPACE_FILL:
            if not any(offset in space for space in spaces):
                raise SystemExit(f"{name}: 0x{offset:05X}, a byte outside its segments' ranges, was blank")


def segment_use(writes: dict[str, list[tuple[int, Piece]]]) -> dict[str, tuple[int, int]]:
    """Per segment: (bytes used, bytes in its range)."""
    use = {}
    for segment, space in FREE_SPACE.items():
        inside = sorted(offset for runs in writes.values() for start, piece in runs
                        for offset in range(start, start + piece_length(piece)) if offset in space.file_range())
        use[segment] = (inside[-1] - space.file_range().start + 1 if inside else 0, len(space.file_range()))
    return use


def render(writes: dict[str, list[tuple[int, Piece]]]) -> str:
    lines = ['"""The ZORA 2.0 flag patches as bytes (docs/design/zora-flags-2.0.md).',
             "",
             "Generated by `python3 asm/flags2/build.py build` from asm/flags2/; do not edit.",
             "PATCHES[name] is a tuple of (file offset, piece) writes against ZORA's code",
             "patches (asm/series.txt); each patch stands alone. A piece is ZORA's own bytes",
             "or an Original (source, length): the original game's bytes, read from the",
             "player's ROM when written (never stored here). Not wired into the serializer.",
             '"""',
             "from .base_rom import Original, Piece",
             "",
             "# Community members who wrote a feature (docs/credits.md).",
             "CREDITS: dict[str, str] = {"]
    lines.extend(f'    "{name}": "{author}",' for name, author in CREDITS.items())
    lines.append("}")
    lines.append("")
    lines.append("PATCHES: dict[str, tuple[tuple[int, Piece], ...]] = {")
    for name, pieces in writes.items():
        lines.append(f'    "{name}": (')
        for offset, piece in pieces:
            lines += tool.piece_lines("        ", offset, piece)
        lines.append("    ),")
    lines.append("}")
    return "\n".join(lines) + "\n"


def report(writes: dict[str, list[tuple[int, Piece]]]) -> None:
    for name, pieces in writes.items():
        own = sum(len(piece) for _, piece in pieces if not isinstance(piece, Original))
        print(f"{name}: {own} bytes of ZORA's in {len(pieces)} pieces")
        for offset, piece in pieces:
            shown = (f"original 0x{piece.source:05X} x{piece.length}" if isinstance(piece, Original)
                     else piece.hex())
            print(f"    0x{offset:05X}  {shown}")
    for segment, (used, size) in segment_use(writes).items():
        print(f"{segment}: {used} of {size} bytes")


# --- applying ---------------------------------------------------------------

def apply_patches(rom: bytes, names: list[str], patches: dict[str, Any]) -> bytes:
    """`rom` (ZORA's code patches applied) with the named patches written."""
    out = bytearray(rom)
    for name in names:
        for offset, piece in patches[name]:
            data = piece_bytes(piece)
            out[offset:offset + len(data)] = data
    return bytes(out)


def load_data() -> ModuleType:
    """OUTPUT as a module. It imports `.base_rom` relatively (it is copied into zora/rom/, whose
    imports are all relative so Archipelago can install zora/ under another name), so it is
    loaded as a submodule of zora.rom."""
    import zora.rom  # noqa: F401
    spec = importlib.util.spec_from_file_location("zora.rom._asm_flags2_data", OUTPUT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- editing ----------------------------------------------------------------

def edit(name: str) -> None:
    """Write the sources with the patch applied to temp/asm-flags2/edit/src, to read it in
    place (its data edits are not in the sources). Edits go to asm/flags2/NAME/, never there."""
    tree = zora_tree(tool.scratch("asm-flags2-edit"))
    tree.apply(load_patch(name))
    shutil.rmtree(EDIT_TREE, ignore_errors=True)
    shutil.copytree(tree.src, EDIT_TREE / "src")
    print(f"{name} on the ZORA build: {EDIT_TREE / 'src'}")


def refresh(name: str) -> None:
    """Check that the patch applies on the ZORA build, and list each hook's site."""
    patch = load_patch(name)
    tree = zora_tree(tool.scratch("asm-flags2-refresh"))
    lines = tree.lines()
    for hook in patch.hooks:
        file, site = tool.hook_site(lines, name, hook)
        print(f"{name}.{hook.name}: 0x{hook.offset:05X} +{hook.length}, {file} line {site[0]}: {hook.note}")
    for data in data_edits(name):
        print(f"{name} data: 0x{data.offset:05X} +{len(data.data)}: {data.note}")
    patch_image(tree, name, binary_ranges())
    print(f"{name} applies")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("build", "check", "edit", "refresh", "apply"))
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    if args.command in ("edit", "refresh"):
        if len(args.args) != 1 or args.args[0] not in PATCHES:
            parser.error(f"one NAME required: {', '.join(PATCHES)}")
        (edit if args.command == "edit" else refresh)(args.args[0])
        return 0
    if args.command == "apply":
        if len(args.args) < 3:
            parser.error("IN, OUT and at least one NAME required")
        source, target, *names = args.args
        rom = apply_patches(Path(source).read_bytes(), names, load_data().PATCHES)
        Path(target).write_bytes(rom)
        print(f"wrote {target}")
        return 0
    _, writes = build_all()
    report(writes)
    text = render(writes)
    if args.command == "build":
        OUTPUT.write_text(text)
        print(f"wrote {OUTPUT.relative_to(REPO)}")
        return 0
    if not OUTPUT.exists() or OUTPUT.read_text() != text:
        print(f"{OUTPUT.relative_to(REPO)} is out of date: run `asm/flags2/build.py build`")
        return 1
    print("up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
