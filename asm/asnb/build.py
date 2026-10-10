"""Build the ROM side of All Swords No Boards (docs/design/asnb.md section 3).

    python3 asm/asnb/build.py build           rebuild, write asm/asnb/asnb_data.py
    python3 asm/asnb/build.py check           rebuild, exit 1 if that module differs
    python3 asm/asnb/build.py edit NAME       write the sources with NAME applied to temp/asm-asnb/edit/src
    python3 asm/asnb/build.py refresh NAME    check NAME applies and list its hook sites

Three patches, each a folder asm/asnb/NAME/ in asm/'s format (asm/README.md: ZORA's code only,
no disassembly text), applied on its own on top of asm/series.txt (the "ZORA build"), as
asm/flags2/ does. zora/rom/owner_patches.py writes them, behind Add L4 Sword and Level 9
Entrance, from zora/rom/asnb_patch_data.py, a verbatim copy of asnb_data.py.

  take-l4       3a: TakeItem's graded store gives level 4 for the magical sword taken at sword
                level 3, through TakeGradeWithL4, one copy at $BFE0 in each of banks 0-6.
  sword-cap     3b: the sword line tops out at level 4 in the three ResolveProgressive copies,
                switched by the per-seed operand ZORA_B<bank>_SwordLineToL4 (one value, three
                places). Its hooks are inside fp-prog-01's and fp-prog-02's routines.
  level-9-gate  3c: the man at level 9's entrance opens the shutters for sword level 4.

`build` assembles the ZORA build, then each patch on it, and records what changed as pieces
(ZORA's bytes, or Original pieces read from the player's ROM). It checks that every new segment
is one of FREE_SPACE's, blank in the ZORA build, that a patch writes no other blank byte except
where it lengthens a ZORA segment inside that segment's slot (GROWTH), and that the three
applied together write exactly what each writes alone. It records the per-seed operands, the
three ResolveProgressive copies with sword-cap applied, and the seven TakeGradeWithL4 copies.

This script imports scripts/asm_patches.py for its assembling and patch helpers and does not
change it; each build works in a scratch folder of its own (scripts/asm_patches.py's scratch()).
"""
import argparse
import importlib.util
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

REPO = Path(__file__).resolve().parents[2]
ASNB_DIR = REPO / "asm" / "asnb"
OUTPUT = ASNB_DIR / "asnb_data.py"
# `edit` writes the sources with a patch applied here, to read; builds use scratch folders.
EDIT_TREE = REPO / "temp" / "asm-asnb" / "edit"
sys.path.insert(0, str(REPO))

from zora.rom import base_rom  # noqa: E402
from zora.rom.base_rom import Original, Piece, piece_bytes, piece_length  # noqa: E402


def _builder() -> ModuleType:
    """scripts/asm_patches.py, loaded read-only for its helpers."""
    spec = importlib.util.spec_from_file_location("asm_patches_tool", REPO / "scripts" / "asm_patches.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _builder()

# The patches, by the design's section order.
PATCHES = (
    "take-l4",          # 3a  level 4 from any pickup
    "sword-cap",        # 3b  the sword line tops out at level 4
    "level-9-gate",     # 3c  level 9 opens for sword level 4
)


@dataclass(frozen=True)
class FreeSpace:
    """A free-space range: bank and CPU addresses, inclusive (docs/rom-map.md "Free space in PRG0")."""
    bank: int
    first: int
    last: int

    def file_range(self) -> range:
        return range(tool.file_offset(self.first, self.bank), tool.file_offset(self.last, self.bank) + 1)


# Banks 0-6 hold TakeGradeWithL4 at one address: $BFC0-$BFF9 is $FF in each, between the ISR
# copy's code ($BF50-$BFBF) and the vectors ($BFFA). Bank 1's $BFC0-$BFDF is l4-sword-take's slot
# (asm/flags2/), so the copies take $BFE0-$BFF9 and both patches can be written while
# l4-sword-take is retired (asm/asnb/README.md).
TAKE_BANKS = range(7)
TAKE_ADDRESS = 0xBFE0
FREE_SPACE = {f"ZORA_ASNB_TAKE_B{bank}": FreeSpace(bank, TAKE_ADDRESS, 0xBFF9) for bank in TAKE_BANKS}

# The ZORA segments sword-cap lengthens, and the slots they may grow into (asm/progressive/build.py's
# FREE_SPACE, docs/rom-map.md).
GROWTH = {
    "ZORA_FP_PROG_01_RESOLVE": FreeSpace(1, 0xBEE0, 0xBF4F),
    "ZORA_FP_PROG_02_ARMOS": FreeSpace(4, 0xB900, 0xB9FF),
    "ZORA_FP_PROG_02_ROOM": FreeSpace(5, 0xBB00, 0xBBFF),
}

# The per-seed operands (one value, written to all three), and its two values.
SWORD_LINE_LABEL = re.compile(r"ZORA_B(\d)_SwordLineToL4")
SWORD_LINE_TO_L4 = 0x01
SWORD_LINE_AS_IS = 0x00
# The start and end of each ResolveProgressive copy's shared body (exported by fp-prog-01/02).
RESOLVE_LABEL = re.compile(r"ResolveProgressive(Body|End)B(\d)")


def load_patch(name: str) -> Any:
    """asm/asnb/NAME/ as a patch (scripts/asm_patches.py's Patch)."""
    return tool.load_patch(ASNB_DIR / name)


# --- building ---------------------------------------------------------------

def zora_tree(work: Path) -> Any:
    """The pinned sources with all of asm/series.txt applied, in `work`."""
    tree = tool.SourceTree(work)
    for name in tool.series():
        tree.apply(tool.series_patch(name))
    return tree


def labels(tree: Any) -> dict[str, int]:
    """Every exported label of the tree's last link (ld65's label file) -> CPU address."""
    found = {}
    for line in (tree.obj / "labels.txt").read_text().splitlines():
        _, value, label = line.split()
        found[label.lstrip(".")] = int(value, 16)
    return found


@dataclass(frozen=True)
class Build:
    """Each patch's writes against the ZORA build; the per-seed operands (label -> file offset);
    sword-cap's ResolveProgressive copies (bank -> file range of the shared body, end exclusive);
    the TakeGradeWithL4 copies (bank -> file range)."""
    writes: dict[str, list[tuple[int, Piece]]]
    symbols: dict[str, int]
    resolve_copies: dict[int, tuple[int, int]]
    take_copies: dict[int, tuple[int, int]]


def build_all() -> Build:
    base_rom.remember_repo_base_rom()
    base = zora_tree(tool.scratch("asm-asnb"))
    zora = bytes(base.image)
    original = tool.verify_base_rom().read_bytes()
    writes: dict[str, list[tuple[int, Piece]]] = {}
    symbols: dict[str, int] = {}
    resolve: dict[int, dict[str, int]] = {}
    for name in PATCHES:
        tree = base.copy(tool.scratch(f"asm-asnb-{name}"))
        patched = bytes(tree.apply(load_patch(name)))
        check_segments(name, zora, patched, tree.src)
        writes[name] = tool.patch_pieces(zora, patched, original)
        for label, address in labels(tree).items():
            if (match := SWORD_LINE_LABEL.fullmatch(label)) and name == "sword-cap":
                symbols[label] = tool.file_offset(address, int(match[1]))
            if (match := RESOLVE_LABEL.fullmatch(label)) and name == "sword-cap":
                resolve.setdefault(int(match[2]), {})[match[1]] = tool.file_offset(address, int(match[2]))
        if name == "sword-cap":
            check_operands(patched, symbols)
    check_together(base, zora, writes)
    take_copies = {}
    for bank in TAKE_BANKS:
        space = FREE_SPACE[f"ZORA_ASNB_TAKE_B{bank}"].file_range()
        inside = [offset for start, piece in writes["take-l4"] for offset in range(start, start + piece_length(piece))
                  if offset in space]
        take_copies[bank] = (space.start, max(inside) + 1)
    resolve_copies = {bank: (found["Body"], found["End"]) for bank, found in sorted(resolve.items())}
    return Build(writes, dict(sorted(symbols.items())), resolve_copies, take_copies)


def check_segments(name: str, zora: bytes, patched: bytes, src: Path) -> None:
    """Every segment the patch adds is one of FREE_SPACE's, at its start (blank in the ZORA
    build), and every other byte it writes that is blank ($FF) in the ZORA build lies in a GROWTH
    slot or in one of its hooks' replaced bytes."""
    config = (src / "Z.cfg").read_text()
    patch = load_patch(name)
    # A hook's own bytes may hold $FF (an operand) without being free space.
    allowed = [space.file_range() for space in GROWTH.values()]
    allowed += [range(hook.offset, hook.offset + hook.length) for hook in patch.hooks]
    for segment in patch.segments:
        space = FREE_SPACE.get(segment.name)
        if space is None or (segment.bank, segment.start) != (space.bank, space.first):
            raise SystemExit(f"{name}: segment {segment.name} is not one of FREE_SPACE's")
        if f"{segment.name}: load = ROM_{segment.bank:02d}" not in config:
            raise SystemExit(f"{name}: {segment.name} is not in Z.cfg")
        if any(zora[offset] != tool.FREE_SPACE_FILL for offset in space.file_range()):
            raise SystemExit(f"{name}: the ZORA build is not blank at {segment.name}'s range")
        allowed.append(space.file_range())
    for offset in range(len(zora)):
        if zora[offset] != patched[offset] and zora[offset] == tool.FREE_SPACE_FILL:
            if not any(offset in space for space in allowed):
                raise SystemExit(f"{name}: 0x{offset:05X}, a byte outside its segments' ranges, was blank")


CMP_IMMEDIATE = 0xC9


def check_operands(patched: bytes, symbols: dict[str, int]) -> None:
    """Each copy's per-seed label is the operand of a CMP #, $00 in this build."""
    if len(symbols) != len(GROWTH):
        raise SystemExit(f"sword-cap: {len(symbols)} per-seed operands, not {len(GROWTH)}")
    for label, offset in symbols.items():
        if (patched[offset - 1], patched[offset]) != (CMP_IMMEDIATE, SWORD_LINE_AS_IS):
            raise SystemExit(f"sword-cap: {label} (0x{offset:05X}) is not its CMP's operand")


def check_together(base: Any, zora: bytes, writes: dict[str, list[tuple[int, Piece]]]) -> None:
    """The three patches applied to one tree write what each writes alone, and no byte twice."""
    tree = base.copy(tool.scratch("asm-asnb-together"))
    for name in PATCHES:
        together = bytes(tree.apply(load_patch(name)))
    expected = bytearray(zora)
    owner: dict[int, str] = {}
    for name, pieces in writes.items():
        for start, piece in pieces:
            for offset in range(start, start + piece_length(piece)):
                if offset in owner:
                    raise SystemExit(f"0x{offset:05X}: written by {owner[offset]} and {name}")
                owner[offset] = name
            data = piece_bytes(piece)
            expected[start:start + len(data)] = data
    if bytes(expected) != together:
        raise SystemExit("the patches applied together differ from each applied alone")


def segment_use(build: Build) -> dict[str, tuple[int, int]]:
    """Per segment and grown slot: (bytes used, bytes in its range)."""
    use = {}
    for segment, space in {**FREE_SPACE, **GROWTH}.items():
        inside = sorted(offset for pieces in build.writes.values() for start, piece in pieces
                        for offset in range(start, start + piece_length(piece)) if offset in space.file_range())
        use[segment] = (inside[-1] - space.file_range().start + 1 if inside else 0, len(space.file_range()))
    return use


def render(build: Build) -> str:
    lines = ['"""The ROM side of All Swords No Boards as bytes (docs/design/asnb.md section 3).',
             "",
             "Generated by `python3 asm/asnb/build.py build` from asm/asnb/; do not edit.",
             "PATCHES[name] is a tuple of (file offset, piece) writes against ZORA's code",
             "patches (asm/series.txt, fp-prog-01 and fp-prog-02 included); each patch stands",
             "alone. A piece is ZORA's own bytes or an Original (source, length): the original",
             "game's bytes, read from the player's ROM when written (never stored here);",
             "written by zora/rom/owner_patches.py from its verbatim copy, zora/rom/asnb_patch_data.py.",
             '"""',
             "from .base_rom import Original, Piece",
             "",
             "PATCHES: dict[str, tuple[tuple[int, Piece], ...]] = {"]
    for name, pieces in build.writes.items():
        lines.append(f'    "{name}": (')
        for offset, piece in pieces:
            lines += tool.piece_lines("        ", offset, piece)
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    lines.append("# sword-cap's per-seed operand in each ResolveProgressive copy: label -> file offset.")
    lines.append("SYMBOLS: dict[str, int] = {")
    lines.extend(f'    "{label}": 0x{offset:05X},' for label, offset in build.symbols.items())
    lines.append("}")
    lines.append("")
    lines.append("# With sword-cap: ResolveProgressive's shared body per bank, (first file offset, end exclusive).")
    lines.append("RESOLVE_COPIES: dict[int, tuple[int, int]] = {")
    lines.extend(f"    {bank}: (0x{first:05X}, 0x{end:05X})," for bank, (first, end) in build.resolve_copies.items())
    lines.append("}")
    lines.append("")
    lines.append("# take-l4's TakeGradeWithL4 in each of banks 0-6: (first file offset, end), end exclusive.")
    lines.append("TAKE_COPIES: dict[int, tuple[int, int]] = {")
    lines.extend(f"    {bank}: (0x{first:05X}, 0x{end:05X})," for bank, (first, end) in build.take_copies.items())
    lines.append("}")
    return "\n".join(lines) + "\n"


def report(build: Build) -> None:
    for name, pieces in build.writes.items():
        own = sum(len(piece) for _, piece in pieces if not isinstance(piece, Original))
        print(f"{name}: {own} bytes of ZORA's in {len(pieces)} pieces")
        for offset, piece in pieces:
            shown = (f"original 0x{piece.source:05X} x{piece.length}" if isinstance(piece, Original)
                     else piece.hex())
            print(f"    0x{offset:05X}  {shown}")
    for segment, (used, size) in segment_use(build).items():
        print(f"{segment}: {used} of {size} bytes")
    for label, offset in build.symbols.items():
        print(f"{label}: 0x{offset:05X}")
    for bank, (first, end) in build.resolve_copies.items():
        print(f"ResolveProgressive body, bank {bank}: 0x{first:05X}-0x{end - 1:05X} ({end - first} bytes)")


# --- applying (tests only) --------------------------------------------------------------

def load_data() -> ModuleType:
    """OUTPUT as a module. It imports `.base_rom` relatively (zora/rom/asnb_patch_data.py is its
    verbatim copy, and zora/ imports itself only relatively so Archipelago can install it under
    another name), so it is loaded as a submodule of zora.rom."""
    import zora.rom  # noqa: F401
    spec = importlib.util.spec_from_file_location("zora.rom._asm_asnb_data", OUTPUT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_patches(rom: bytes, names: tuple[str, ...] = PATCHES, sword_line_to_l4: bool = True) -> bytes:
    """`rom` (ZORA's code patches applied, fp-prog-01 and fp-prog-02 included) with the named
    patches written and, with sword-cap, its per-seed operand in all three copies."""
    data = load_data()
    out = bytearray(rom)
    for name in names:
        for offset, piece in data.PATCHES[name]:
            new = piece_bytes(piece)
            out[offset:offset + len(new)] = new
    if "sword-cap" in names:
        for offset in data.SYMBOLS.values():
            out[offset] = SWORD_LINE_TO_L4 if sword_line_to_l4 else SWORD_LINE_AS_IS
    return bytes(out)


# --- editing ----------------------------------------------------------------

def edit(name: str) -> None:
    """Write the sources with the patch applied to temp/asm-asnb/edit/src, to read it in place.
    Edits go to asm/asnb/NAME/, never there."""
    tree = zora_tree(tool.scratch("asm-asnb-edit"))
    tree.apply(load_patch(name))
    shutil.rmtree(EDIT_TREE, ignore_errors=True)
    shutil.copytree(tree.src, EDIT_TREE / "src")
    print(f"{name} on the ZORA build: {EDIT_TREE / 'src'}")


def refresh(name: str) -> None:
    """Check that the patch applies on the ZORA build, and list each hook's site."""
    patch = load_patch(name)
    tree = zora_tree(tool.scratch("asm-asnb-refresh"))
    lines = tree.lines()
    for hook in patch.hooks:
        file, site = tool.hook_site(lines, name, hook)
        print(f"{name}.{hook.name}: 0x{hook.offset:05X} +{hook.length}, {file} line {site[0]}: {hook.note}")
    tree.apply(patch)
    print(f"{name} applies")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("build", "check", "edit", "refresh"))
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    if args.command in ("edit", "refresh"):
        if len(args.args) != 1 or args.args[0] not in PATCHES:
            parser.error(f"one NAME required: {', '.join(PATCHES)}")
        (edit if args.command == "edit" else refresh)(args.args[0])
        return 0
    build = build_all()
    report(build)
    text = render(build)
    if args.command == "build":
        OUTPUT.write_text(text)
        print(f"wrote {OUTPUT.relative_to(REPO)}")
        return 0
    if not OUTPUT.exists() or OUTPUT.read_text() != text:
        print(f"{OUTPUT.relative_to(REPO)} is out of date: run `asm/asnb/build.py build`")
        return 1
    print("up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
