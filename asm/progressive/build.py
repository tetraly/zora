"""Build the progressive-items patches (docs/progressive-patches.md).

    python3 asm/progressive/build.py build          rebuild, write asm/progressive/progressive_data.py
    python3 asm/progressive/build.py check          rebuild, exit 1 if that module differs

Two patches, at the end of asm/series.txt (wired 2026-10-05: ZORA writes them
behind the ZORA flags, zora/rom/code_patches.py PI-CODE-01), here applied on
top of the series before them:

  fp-prog-01  bank 1: cave and shop wares shown at their line's next level
              when the cave opens, and shop wares sold once
              (ZORA_B1_OneTimeWares, Items+$20..$22).
  fp-prog-02  banks 5 and 4: the room item, the coast item and the Armos
              item stored at their line's next level.

scripts/asm_patches.py builds them into zora/rom/code_patch_data.py with the
rest of the series. This script keeps what the tests need beyond that: `build`
assembles the ZORA build without them, then each patch on top of the one
before, checks every new segment
against the free space this script may use (FREE_SPACE, from
docs/rom-map.md) and records each patch's changed bytes, the per-seed data
labels (ZORA_B<bank>_*) and the extents of the three ResolveProgressive
copies.

The rest of this module is for the tests only (tests/test_progressive_*.py):
writing the patches and their per-seed bytes into a finished ROM, and
placing items in caves and rooms. The patches are the folders asm/fp-prog-01/
and asm/fp-prog-02/ (asm/README.md), like the rest of the series.

This script imports scripts/asm_patches.py for its assembling and patch
helpers and does not change it; each build works in a scratch folder of its own
(scripts/asm_patches.py's scratch()).
"""
import argparse
import importlib.util
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PROGRESSIVE_DIR = REPO / "asm" / "progressive"
OUTPUT = PROGRESSIVE_DIR / "progressive_data.py"
sys.path.insert(0, str(REPO))

from zora.rom.base_rom import Original, Piece, original_bytes, piece_bytes, piece_length  # noqa: E402
from zora.rom.layout import (  # noqa: E402
    ARMOS_ITEM_ADDRESS,
    ASM_NOTHING_CODE_PATCH_OFFSET,
    CAVE_ITEM_DATA_ADDRESS,
    CAVE_NOTHING_CODE,
    CAVE_PRICE_DATA_ADDRESS,
    COAST_ITEM_ADDRESS,
)


def _builder() -> ModuleType:
    """scripts/asm_patches.py, loaded read-only for its helpers."""
    spec = importlib.util.spec_from_file_location("asm_patches_tool", REPO / "scripts" / "asm_patches.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _builder()

PATCHES = ("fp-prog-01", "fp-prog-02")


@dataclass(frozen=True)
class FreeSpace:
    """A free-space range a patch segment may take: bank and CPU addresses,
    inclusive (docs/rom-map.md "Free space in PRG0")."""
    bank: int
    first: int
    last: int

    def file_range(self) -> range:
        return range(tool.file_offset(self.first, self.bank), tool.file_offset(self.last, self.bank) + 1)


# The plan's placements (docs/progressive-patches.md "Free space"). Bank 1's
# $BE40-$BEBF was inside the extended hint text's limit until PI-HINT-01 ended
# the text at $BE40.
FREE_SPACE = {
    "ZORA_FP_PROG_01_SHOP": FreeSpace(1, 0xBE40, 0xBEBF),      # up to fp-fix-02's slot at $BEC0
    "ZORA_FP_PROG_01_RESOLVE": FreeSpace(1, 0xBEE0, 0xBF4F),   # fp-fix-02's slot ends at $BEDF
    "ZORA_FP_PROG_02_ROOM": FreeSpace(5, 0xBB00, 0xBBFF),      # fp-entr-01's slot ends at $BAFF
    "ZORA_FP_PROG_02_ARMOS": FreeSpace(4, 0xB900, 0xB9FF),     # z1rr-coop reserves $B46F-$B882; Pols Voice's slot is at $BA00
}

# Exported labels the build records (bank in the name, as in scripts/asm_patches.py):
# the per-seed data, and the start and end of each copy of ResolveProgressive's
# shared body (bank 1's copy is its on/off check, then the same body).
DATA_LABEL = re.compile(r"ZORA_B(\d)_\w+")
RESOLVE_LABEL = re.compile(r"ResolveProgressive(Body|End)B(\d)")
NOTHING_CODE_LABEL = "RoomItemNothingCodeB5"


# --- building ---------------------------------------------------------------

def zora_tree(work: Path) -> Any:
    """The pinned sources with asm/series.txt applied up to, but without, the progressive
    patches, in `work` (scripts/asm_patches.py checks that the unpatched sources rebuild PRG0)."""
    tree = tool.SourceTree(work)
    for name in tool.series():
        if name in PATCHES:
            break
        tree.apply(tool.series_patch(name))
    return tree


def exported_labels(obj: Path) -> dict[str, int]:
    """Every exported label of the last link (ld65's label file) -> CPU address."""
    labels = {}
    for line in (obj / "labels.txt").read_text().splitlines():
        _, value, label = line.split()
        labels[label.lstrip(".")] = int(value, 16)
    return labels


@dataclass(frozen=True)
class Build:
    """The ZORA build and each patch's writes (file offset, piece) against the build before
    it (a piece: ZORA's bytes, or an Original read from the player's ROM); the per-seed data labels and
    the ResolveProgressive copies (bank -> file range of the shared body)
    as file offsets."""
    zora: bytes
    runs: dict[str, list[tuple[int, Piece]]]
    symbols: dict[str, int]
    resolve_copies: dict[int, tuple[int, int]]
    nothing_code_operand: int


def build_all() -> Build:
    tree = zora_tree(tool.scratch("asm-progressive"))
    image = zora = bytes(tree.image)
    original = tool.verify_base_rom().read_bytes()
    runs: dict[str, list[tuple[int, Piece]]] = {}
    for name in PATCHES:
        patched = bytes(tree.apply(tool.series_patch(name)))
        runs[name] = tool.patch_pieces(image, patched, original)
        image = patched
    labels = exported_labels(tree.obj)
    check_segments(zora, image, tree.src)
    # The series' own data labels (ZORA_B2_CodeIcons, ...) are in the label file too: keep ours.
    symbols = {label: offset for label, address in labels.items() if (match := DATA_LABEL.fullmatch(label))
               and any((offset := tool.file_offset(address, int(match[1]))) in space.file_range()
                       for space in FREE_SPACE.values())}
    ends: dict[int, dict[str, int]] = {}
    for label, address in labels.items():
        if match := RESOLVE_LABEL.fullmatch(label):
            bank = int(match[2])
            ends.setdefault(bank, {})[match[1]] = tool.file_offset(address, bank)
    resolve_copies = {bank: (found["Body"], found["End"]) for bank, found in sorted(ends.items())}
    nothing_code_operand = tool.file_offset(labels[NOTHING_CODE_LABEL], 5)
    return Build(zora, runs, symbols, resolve_copies, nothing_code_operand)


def check_segments(zora: bytes, patched: bytes, src: Path) -> None:
    """Every new segment is one of FREE_SPACE's, at its start address, and
    every byte the patches change outside PRG0's own routines lies in one of
    those ranges, which are all $FF in the ZORA build."""
    config = (src / "Z.cfg").read_text()
    for segment, space in FREE_SPACE.items():
        found = re.search(rf"{segment}: load = ROM_0(\d), type = ro, start = \$([0-9A-F]+) ;", config)
        if not found or int(found[1]) != space.bank or int(found[2], 16) != space.first:
            raise SystemExit(f"{segment}: not in Z.cfg at bank {space.bank} ${space.first:04X}")
        if any(zora[offset] != 0xFF for offset in space.file_range()):
            raise SystemExit(f"{segment}: the ZORA build is not blank at ${space.first:04X}-${space.last:04X}")
    new_segments = set(re.findall(r"(ZORA_FP_PROG_\w+):", config))
    if new_segments != set(FREE_SPACE):
        raise SystemExit(f"segments {sorted(new_segments ^ set(FREE_SPACE))} not in FREE_SPACE")
    blank = {offset for offset in range(len(zora)) if zora[offset] == 0xFF}
    for offset in range(len(zora)):
        if zora[offset] != patched[offset] and offset in blank:
            if not any(offset in space.file_range() for space in FREE_SPACE.values()):
                raise SystemExit(f"0x{offset:05X}: a free byte outside FREE_SPACE is written")


def segment_use(build: Build) -> dict[str, tuple[int, int]]:
    """Per segment: (bytes used, bytes in its range); a segment's bytes are
    the ones its patches change inside its range."""
    changed = {offset for runs in build.runs.values() for start, piece in runs
               for offset in range(start, start + piece_length(piece))}
    use = {}
    for segment, space in FREE_SPACE.items():
        inside = sorted(offset for offset in changed if offset in space.file_range())
        used = inside[-1] - space.file_range().start + 1 if inside else 0
        use[segment] = (used, len(space.file_range()))
    return use


def render(build: Build) -> str:
    lines = ['"""Progressive-items patches as bytes (docs/progressive-patches.md).',
             "",
             "Generated by `python3 asm/progressive/build.py build` from asm/fp-prog-0*/;",
             "do not edit. PATCHES[name] is a tuple of (file offset, piece) writes, against",
             "ZORA's code patches (asm/series.txt) with the patches before it applied:",
             "fp-prog-01, then fp-prog-02. A piece is ZORA's own bytes or an Original",
             "(source, length), read from the player's ROM when written.",
             '"""',
             "from zora.rom.base_rom import Original, Piece",
             "",
             "PATCHES: dict[str, tuple[tuple[int, Piece], ...]] = {"]
    for name, runs in build.runs.items():
        lines.append(f'    "{name}": (')
        for offset, piece in runs:
            lines += tool.piece_lines("        ", offset, piece)
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    lines.append("# Data written per seed: exported label -> file offset.")
    lines.append("SYMBOLS: dict[str, int] = {")
    lines.extend(f'    "{label}": 0x{offset:05X},' for label, offset in sorted(build.symbols.items()))
    lines.append("}")
    lines.append("")
    lines.append("# ResolveProgressive's shared body in each bank: (first file offset, end), end exclusive.")
    lines.append("RESOLVE_COPIES: dict[int, tuple[int, int]] = {")
    lines.extend(f"    {bank}: (0x{first:05X}, 0x{end:05X})," for bank, (first, end) in build.resolve_copies.items())
    lines.append("}")
    lines.append("")
    lines.append("# The operand bank 5's room hook reads as the \"no item\" code (CreateRoomObjects + 21).")
    lines.append(f"NOTHING_CODE_OPERAND = 0x{build.nothing_code_operand:05X}")
    return "\n".join(lines) + "\n"


def report(build: Build) -> None:
    for name, runs in build.runs.items():
        print(f"{name}: {len(runs)} pieces")
        for offset, piece in runs:
            shown = (f"original 0x{piece.source:05X} x{piece.length}" if isinstance(piece, Original)
                     else piece.hex())
            print(f"    0x{offset:05X}  {shown}")
    for segment, (used, size) in segment_use(build).items():
        space = FREE_SPACE[segment]
        print(f"{segment}: bank {space.bank} ${space.first:04X}, {used} of {size} bytes")


# --- applying (tests only) ------------------------------------------------------

def load_data() -> ModuleType:
    spec = importlib.util.spec_from_file_location("progressive_data", OUTPUT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_patches(rom: bytes, names: Iterable[str] = PATCHES) -> bytes:
    """`rom` (a finished ZORA ROM: PRG0 with ZORA's code patches) with the
    named patches written over it. Refuses a ROM that does not hold PRG0's
    bytes where a patch writes (every patch replaces PRG0 bytes only), read
    from the player's ROM."""
    data = load_data()
    out = bytearray(rom)
    for name in PATCHES:
        if name not in names:
            continue
        for offset, piece in data.PATCHES[name]:
            new = piece_bytes(piece)
            if out[offset:offset + len(new)] != original_bytes(offset, len(new)):
                raise ValueError(f"{name}: 0x{offset:05X} does not hold the bytes the patch replaces")
            out[offset:offset + len(new)] = new
    return bytes(out)


PROGRESSIVE_ITEMS_ON = 0x01
SHOP_WARES = 3
# Shop object types by shop number (the patch's ShopNumbers): the potion shop, shops A-D.
SHOP_TYPES = (0x74, 0x77, 0x78, 0x79, 0x7A)
FIRST_CAVE_TYPE = 0x6A
CAVE_ITEM_ID_MASK = 0x3F
CAVE_FLAG_MASK = 0xC0
# Shop wares sold again after each purchase: bombs, bait, key, the magical
# shield, the blue and red potions, a heart and a fairy (Item values).
REBUYABLE_ITEMS = frozenset({0x00, 0x04, 0x19, 0x1C, 0x1F, 0x20, 0x22, 0x23})


def ware_offset(cave_type: int, ware: int) -> int:
    return CAVE_ITEM_DATA_ADDRESS + (cave_type - FIRST_CAVE_TYPE) * SHOP_WARES + ware


def price_offset(cave_type: int, ware: int) -> int:
    return CAVE_PRICE_DATA_ADDRESS + (cave_type - FIRST_CAVE_TYPE) * SHOP_WARES + ware


def one_time_wares(rom: bytes) -> bytes:
    """ZORA_B1_OneTimeWares for the shop stock in `rom`: per ware position,
    one bit per shop (1 << shop number) for each ware not sold again."""
    wares = bytearray(SHOP_WARES)
    for shop_number, shop_type in enumerate(SHOP_TYPES):
        for ware in range(SHOP_WARES):
            item = rom[ware_offset(shop_type, ware)] & CAVE_ITEM_ID_MASK
            if item != CAVE_NOTHING_CODE and item not in REBUYABLE_ITEMS:
                wares[ware] |= 1 << shop_number
    return bytes(wares)


def write_seed_bytes(rom: bytes, progressive_items: bool = True, wares: bytes | None = None) -> bytes:
    """`rom` (patched) with the per-seed bytes: the on/off byte and the
    one-time wares (by default, from the shop stock in `rom`)."""
    data = load_data()
    out = bytearray(rom)
    out[data.SYMBOLS["ZORA_B1_ProgressiveItems"]] = PROGRESSIVE_ITEMS_ON if progressive_items else 0
    one_time = data.SYMBOLS["ZORA_B1_OneTimeWares"]
    out[one_time:one_time + SHOP_WARES] = wares if wares is not None else one_time_wares(rom)
    return bytes(out)


def progressive_rom(rom: bytes, progressive_items: bool = True) -> bytes:
    """A finished ZORA ROM with the progressive patches and their per-seed
    bytes: both patches with progressive items on; with them off, only
    fp-prog-01 (the bank 4 and 5 copies of ResolveProgressive do not read
    the on/off byte, so their hooks are left out)."""
    names = PATCHES if progressive_items else PATCHES[:1]
    return write_seed_bytes(apply_patches(rom, names), progressive_items)


def with_ware(rom: bytes, cave_type: int, ware: int, item: int, price: int | None = None) -> bytes:
    """`rom` with one cave ware replaced (its cave flags kept) and, given,
    its price."""
    out = bytearray(rom)
    offset = ware_offset(cave_type, ware)
    out[offset] = out[offset] & CAVE_FLAG_MASK | item
    if price is not None:
        out[price_offset(cave_type, ware)] = price
    return bytes(out)


def with_armos_item(rom: bytes, item: int) -> bytes:
    out = bytearray(rom)
    out[ARMOS_ITEM_ADDRESS] = item
    return bytes(out)


def with_coast_item(rom: bytes, item: int) -> bytes:
    out = bytearray(rom)
    out[COAST_ITEM_ADDRESS] = item
    return bytes(out)


def nothing_code(rom: bytes) -> int:
    """The "no item" code CreateRoomObjects compares with in `rom`."""
    return rom[ASM_NOTHING_CODE_PATCH_OFFSET]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("build", "check"))
    args = parser.parse_args()
    build = build_all()
    report(build)
    text = render(build)
    if args.command == "build":
        OUTPUT.write_text(text)
        print(f"wrote {OUTPUT.relative_to(REPO)}")
        return 0
    if not OUTPUT.exists() or OUTPUT.read_text() != text:
        print(f"{OUTPUT.relative_to(REPO)} is out of date: run `asm/progressive/build.py build`")
        return 1
    print("up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
