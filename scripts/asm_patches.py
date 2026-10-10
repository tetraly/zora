"""Build ZORA's 6502 patches from ca65 source (asm/README.md, docs/rom-map.md).

    python3 scripts/asm_patches.py build            rebuild, write zora/rom/code_patch_data.py
    python3 scripts/asm_patches.py check            rebuild, exit 1 if the module differs
    python3 scripts/asm_patches.py edit NAME        write the pinned disassembly with the series applied
                                                    through NAME to temp/asm/edit/src, to read it in place
    python3 scripts/asm_patches.py refresh NAME     apply the series through NAME and list NAME's hook sites
    python3 scripts/asm_patches.py locate FILE LINE the file offset and length of a line of the pinned
                                                    disassembly (FILE as Z_05.asm), to write a hook

No disassembly text is tracked: each patch is a folder asm/NAME/ of ZORA's own code (asm/README.md),
listed in order in asm/series.txt. Its patch.toml names the patch's segments (bank free space,
src/Z.cfg), the symbols it imports and exports per bank, and its hooks: a hook replaces the PRG0
instructions at a file offset (the replaced length) with ZORA's code, so every following byte keeps
its place. Its bank_NN.s files hold ZORA's routines, which join bank NN's source file.

The builder fetches the pinned disassembly from git (AGENTS.md "Disassembly pin": commit
DISASSEMBLY_COMMIT of the clone at ../zelda1-disassembly, never its working tree; see
disassembly()), checks that it rebuilds PRG0, then applies the series one patch at a time: each
hook's offset is mapped to the source lines that assemble there (ca65/ld65 debug info of the
build before it), those lines are replaced by the hook's code, the routines are appended to their
bank's file and the segments added to Z.cfg. Each patch's changed bytes are recorded against the
build before it; what it keeps or moves of the original game is recorded as an Original piece, read
from the player's ROM when written. Exported labels named ZORA_* (data a ZORA pass fills per seed)
are recorded as file offsets.
"""
import argparse
import atexit
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora.rom.base_rom import Original, Piece, verify_base_rom  # noqa: E402
from zora.rom.layout import NES_HEADER_SIZE  # noqa: E402

# The pinned public disassembly (asm/README.md, "The disassembly"): the clone and the commit the
# patches are built on. Only that commit is read (git archive), so uncommitted edits, other
# branches and worktrees in the clone never reach a build. The clone sits next to this repo, or
# where ZORA_DISASSEMBLY points.
DISASSEMBLY_URL = "https://github.com/aldonunez/zelda1-disassembly"
DISASSEMBLY_REPO = Path(os.environ.get("ZORA_DISASSEMBLY", REPO.parent / "zelda1-disassembly"))
CLONE_HINT = (f"clone it with `git clone {DISASSEMBLY_URL} {REPO.parent / 'zelda1-disassembly'}`, "
              "or set ZORA_DISASSEMBLY to a clone (asm/README.md)")
DISASSEMBLY_COMMIT = "50a1c869a8d8e2eb8b5b60acea325f44b4341762"
DISASSEMBLY_FILES = ("src", "OriginalNesHeader.bin")
# Where the pinned files are exported: one folder per process (parallel test workers each
# have their own), removed when the process exits.
DISASSEMBLY_EXPORTS = REPO / "temp" / "disassembly"
# The generated modules' longest line (Archipelago's ruff line-length).
LINE_LIMIT = 120
ASM = REPO / "asm"
SERIES = ASM / "series.txt"
# `edit` writes the patched sources here, to read; every build works in a scratch() folder.
EDIT_TREE = REPO / "temp" / "asm" / "edit"
SCRATCH_ROOT = REPO / "temp"
OUTPUT = REPO / "zora" / "rom" / "code_patch_data.py"
BINS = re.compile(r"Offset='(\d+)' Length='(\d+)' FileName='([^']+)'")
EXPORT_PREFIX = "ZORA_"
DEBUG_FILE = "Z.dbg"
FIXED_BANK = 7
BANK_SIZE = 0x4000
SWITCHED_BANK_BASE = 0x8000
FIXED_BANK_BASE = 0xC000


def series() -> list[str]:
    return [line.strip() for line in SERIES.read_text().splitlines()
            if line.strip() and not line.startswith("#")]


# --- the pinned disassembly ---------------------------------------------------

class DisassemblyError(SystemExit):
    """The pinned disassembly cannot be read: the clone or the commit is missing."""


def export_disassembly(repo: Path, commit: str, dest: Path) -> Path:
    """`commit`'s src/ and NES header, read from the git repo at `repo` (git archive) into
    `dest`, which is replaced. The repo's working tree, index and branches are not read."""
    if not repo.is_dir():
        raise DisassemblyError(f"the pinned disassembly's clone {repo} is missing: {CLONE_HINT}")
    found = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
                           capture_output=True, text=True)
    if found.returncode != 0:
        is_repo = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-dir"], capture_output=True).returncode == 0
        raise DisassemblyError(f"{repo} has no commit {commit} (the pinned disassembly): "
                               f"`git -C {repo} fetch` it from {DISASSEMBLY_URL}"
                               if is_repo else f"{repo} is not a git repository: {CLONE_HINT}")
    archive = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit, *DISASSEMBLY_FILES],
                             capture_output=True, check=True).stdout
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")
    return dest


_exports: dict[tuple[Path, str], Path] = {}


def disassembly() -> Path:
    """The pinned disassembly (DISASSEMBLY_COMMIT of DISASSEMBLY_REPO) as files, exported from
    git once per process and repo/commit pair."""
    key = (DISASSEMBLY_REPO, DISASSEMBLY_COMMIT)
    if key not in _exports:
        if not _exports:
            atexit.register(_remove_exports)
        _exports[key] = export_disassembly(*key, DISASSEMBLY_EXPORTS / f"{os.getpid()}-{len(_exports)}")
    return _exports[key]


def _remove_exports() -> None:
    for path in _exports.values():
        shutil.rmtree(path, ignore_errors=True)


def scratch(name: str) -> Path:
    """A new folder of its own under temp/ for one build (temp/NAME-XXXXXXXX), removed when the
    process exits, so builds running at once (two sessions' tests) never share one."""
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=f"{name}-", dir=SCRATCH_ROOT))
    atexit.register(shutil.rmtree, path, ignore_errors=True)
    return path


# --- sources ------------------------------------------------------------------

def pristine_sources(dest: Path) -> None:
    """The pinned disassembly's src/, with LF line ends."""
    if dest.exists():
        shutil.rmtree(dest)
    pinned = disassembly() / "src"
    for path in sorted(pinned.rglob("*")):
        if path.is_file():
            target = dest / path.relative_to(pinned)
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix in (".asm", ".inc", ".cfg"):
                target.write_text(path.read_text().replace("\r\n", "\n"))
            else:
                target.write_bytes(path.read_bytes())


# --- patches ------------------------------------------------------------------

PATCH_FILE = "patch.toml"
ROUTINES = re.compile(r"bank_(\d\d)\.s")
LABEL_LINE = re.compile(r"^\s*(@?\w+:|:)")


def bank_file(bank: int) -> str:
    """The disassembly's source file for a bank."""
    return f"Z_{bank:02d}.asm"


@dataclass(frozen=True)
class Segment:
    """A segment of ZORA's code at a fixed address in a bank's free space (docs/rom-map.md)."""
    name: str
    bank: int
    start: int

    def config_line(self) -> str:
        return f"    {self.name}: load = ROM_{self.bank:02d}, type = ro, start = ${self.start:04X} ;"


@dataclass(frozen=True)
class Hook:
    """ZORA's code in place of the PRG0 instructions (or data) at `offset` (a headered file
    offset), `length` bytes long. Code of the same length keeps every following byte in place;
    a hook of length 0 inserts its code before the instruction at `offset`, and one with no
    code removes the instructions, which moves the code between (fp-fix-05)."""
    name: str
    offset: int
    length: int
    code: str
    note: str


@dataclass(frozen=True)
class Patch:
    """A patch folder: its segments, the symbols it imports and exports per bank, its hooks
    and its routines (bank -> ZORA's source). A player-setting choice may also leave out hooks
    of the series ("patch.hook") and replace a series patch's routines ((patch, bank) -> source)."""
    name: str
    segments: tuple[Segment, ...]
    imports: dict[int, tuple[str, ...]]
    exports: dict[int, tuple[str, ...]]
    hooks: tuple[Hook, ...]
    routines: dict[int, str]
    leave_out: frozenset[str] = frozenset()
    replaced_routines: dict[tuple[str, int], str] = field(default_factory=dict)


def _banks(table: dict[str, list[str]]) -> dict[int, tuple[str, ...]]:
    """{"bank_05": [...]} -> {5: (...)}."""
    return {int(key.removeprefix("bank_")): tuple(names) for key, names in table.items()}


def load_patch(folder: Path) -> Patch:
    """asm/NAME/ (or asm/settings/CHOICE/) as a Patch."""
    spec = tomllib.loads((folder / PATCH_FILE).read_text())
    routines = {int(match[1]): path.read_text() for path in sorted(folder.glob("bank_*.s"))
                if (match := ROUTINES.fullmatch(path.name))}
    series_changes = spec.get("series", {})
    replaced = {}
    for target, source in series_changes.get("routines", {}).items():
        patch, routine = target.split("/")
        match = ROUTINES.fullmatch(routine)
        if not match:
            raise SystemExit(f"{folder.name}: {target}: routines are bank_NN.s files")
        replaced[(patch, int(match[1]))] = (folder / source).read_text()
    return Patch(
        name=folder.name,
        segments=tuple(Segment(**segment) for segment in spec.get("segment", [])),
        imports=_banks(spec.get("imports", {})),
        exports=_banks(spec.get("exports", {})),
        hooks=tuple(Hook(hook["name"], hook["offset"], hook["length"], hook.get("code", ""), hook["note"])
                    for hook in spec.get("hook", [])),
        routines=routines,
        leave_out=frozenset(series_changes.get("leave_out", ())),
        replaced_routines=replaced,
    )


def series_patch(name: str) -> Patch:
    return load_patch(ASM / name)


# --- applying a patch to the sources ----------------------------------------------

@dataclass(frozen=True)
class SourceLine:
    """A source line of a bank file and the bytes it assembled to."""
    file: str
    line: int                  # 1-based
    offset: int                # headered file offset
    size: int


def source_lines(debug_file: Path) -> dict[int, SourceLine]:
    """ld65's debug file -> the bank files' lines by the file offset of their first byte."""
    records: dict[str, list[dict[str, str]]] = defaultdict(list)
    for text in debug_file.read_text().splitlines():
        kind, _, fields = text.partition("\t")
        records[kind].append(dict(item.split("=", 1) for item in fields.split(",")))
    files = {record["id"]: Path(record["name"].strip('"')).name for record in records["file"]}
    segments = {record["id"]: int(record["ooffs"]) for record in records["seg"] if "ooffs" in record}
    spans = {record["id"]: (segments.get(record["seg"]), int(record["start"]), int(record["size"]))
             for record in records["span"]}
    lines: dict[int, SourceLine] = {}
    for record in records["line"]:
        name = files[record["file"]]
        if "span" not in record or "type" in record or not re.fullmatch(r"Z_\d\d\.asm", name):
            continue
        for span_id in record["span"].split("+"):
            base, start, size = spans[span_id]
            if base is not None and size:
                offset = NES_HEADER_SIZE + base + start
                lines[offset] = SourceLine(name, int(record["line"]), offset, size)
    return lines


def hook_site(lines: dict[int, SourceLine], patch: str, hook: Hook) -> tuple[str, list[int]]:
    """The bank file and the lines whose bytes are exactly the hook's range (for a hook of
    length 0, the line it is inserted before)."""
    if hook.length == 0:
        if hook.offset not in lines:
            raise SystemExit(f"{patch}.{hook.name}: no instruction starts at 0x{hook.offset:05X}")
        return lines[hook.offset].file, [lines[hook.offset].line]
    covered, offset = [], hook.offset
    while offset < hook.offset + hook.length:
        if offset not in lines:
            raise SystemExit(f"{patch}.{hook.name}: 0x{offset:05X} is not the start of a source line")
        covered.append(lines[offset])
        offset += lines[offset].size
    if offset != hook.offset + hook.length:
        raise SystemExit(f"{patch}.{hook.name}: its {hook.length} bytes end inside an instruction")
    files = {line.file for line in covered}
    if len(files) != 1:
        raise SystemExit(f"{patch}.{hook.name}: its bytes span several source files")
    return files.pop(), [line.line for line in covered]


def code_lines(code: str) -> list[str]:
    return [line.rstrip() + "\n" for line in code.strip("\n").splitlines()]


def _edit_file(text: list[str], patch: str, hook: Hook, site: list[int]) -> None:
    """Put the hook's code at its lines of `text` (in place)."""
    first = site[0] - 1
    if hook.length == 0:
        text[first:first] = code_lines(hook.code)
        return
    for number in range(site[0], site[-1] + 1):
        if number not in site and LABEL_LINE.match(text[number - 1]):
            raise SystemExit(f"{patch}.{hook.name}: a label lies between the instructions it replaces")
    for number in reversed(site[1:]):
        del text[number - 1]
    label = LABEL_LINE.match(text[first])
    text[first:first + 1] = ([label[1] + "\n"] if label else []) + code_lines(hook.code)


def add_segments(config: str, segments: tuple[Segment, ...]) -> str:
    """Z.cfg with each segment placed among its bank's segments in address order."""
    lines = config.splitlines(keepends=True)
    for segment in segments:
        bank = f"load = ROM_{segment.bank:02d},"
        after = None
        for index, line in enumerate(lines):
            if bank in line:
                start = re.search(r"start = \$([0-9A-Fa-f]+)", line)
                if not start or int(start[1], 16) < segment.start:
                    after = index
        if after is None:
            raise SystemExit(f"{segment.name}: Z.cfg has no segment of bank {segment.bank}")
        lines.insert(after + 1, segment.config_line() + "\n")
    return "".join(lines)


def apply_patch(src: Path, patch: Patch, lines: dict[int, SourceLine],
                leave_out: frozenset[str] = frozenset(),
                replaced_routines: dict[tuple[str, int], str] | None = None) -> None:
    """Apply `patch` to the sources in `src`, whose last build's lines are `lines`. Hooks named
    in leave_out ("patch.hook") are skipped and routines in replaced_routines swapped (a
    player-setting choice's changes to the series)."""
    edits: dict[str, list[tuple[Hook, list[int]]]] = defaultdict(list)
    for hook in patch.hooks:
        if f"{patch.name}.{hook.name}" in leave_out:
            continue
        file, site = hook_site(lines, patch.name, hook)
        edits[file].append((hook, site))
    for file, file_edits in edits.items():
        text = (src / file).read_text().splitlines(keepends=True)
        for hook, site in sorted(file_edits, key=lambda edit: edit[1][0], reverse=True):
            _edit_file(text, patch.name, hook, site)
        (src / file).write_text("".join(text))
    for bank in sorted({*patch.imports, *patch.exports, *patch.routines}):
        path = src / bank_file(bank)
        directives = [f".IMPORT {name}\n" for name in patch.imports.get(bank, ())]
        directives += [f".EXPORT {name}\n" for name in patch.exports.get(bank, ())]
        routine = (replaced_routines or {}).get((patch.name, bank), patch.routines.get(bank))
        appended = f"\n{routine}" if routine is not None else ""
        path.write_text("".join(directives) + path.read_text() + appended)
    config = src / "Z.cfg"
    config.write_text(add_segments(config.read_text(), patch.segments))


# --- assembling -------------------------------------------------------------

def extract_bins(rom: bytes, dest: Path) -> None:
    for match in BINS.finditer((disassembly() / "src" / "bins.xml").read_text()):
        offset, length, name = int(match[1]), int(match[2]), match[3]
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(rom[NES_HEADER_SIZE + offset:NES_HEADER_SIZE + offset + length])


def assemble(src: Path, bins: Path, out: Path) -> tuple[bytes, dict[str, int]]:
    """Assemble and link src/; return the headered image and the exported
    ZORA_* labels as CPU addresses with their bank. The debug file (out/Z.dbg) maps
    each source line to its bytes (source_lines)."""
    out.mkdir(parents=True, exist_ok=True)
    objects = []
    for source in sorted(src.glob("*.asm")):
        obj = out / f"{source.stem}.o"
        subprocess.run(["ca65", "-g", str(source), "-o", str(obj), "--bin-include-dir", str(bins)],
                       check=True)
        objects.append(str(obj))
    image, labels = out / "Z.bin", out / "labels.txt"
    subprocess.run(["ld65", "-o", str(image), "-C", str(src / "Z.cfg"), *objects,
                    "-Ln", str(labels), "--dbgfile", str(out / DEBUG_FILE)], check=True)
    header = (disassembly() / "OriginalNesHeader.bin").read_bytes()
    exports = {}
    for line in labels.read_text().splitlines():
        _, value, label = line.split()
        if label.startswith("." + EXPORT_PREFIX):
            exports[label[1:]] = int(value, 16)
    return header + image.read_bytes(), exports


# Changed bytes closer than this join one run, so a run keeps the unchanged
# bytes inside a routine (an operand that happens to equal the old byte).
RUN_GAP = 8
# A patch that moves original code (fp-fix-05 shifts part of CheckShutters) records the
# moved bytes as an Original piece read from the player's ROM: a stretch of at least this
# many changed bytes equal to the original game's within MOVE_DISTANCE of where it lands.
MOVE_MIN = 8
MOVE_DISTANCE = 0x100
# PRG0's free space is filled with $FF: a written byte equal to it is ZORA's (an operand that
# happens to be $FF), not a kept piece of the game.
FREE_SPACE_FILL = 0xFF


def changed_runs(before: bytes, after: bytes) -> list[tuple[int, bytes, bytes]]:
    """(file offset, old bytes, new bytes) for each run of changed bytes."""
    changed = [offset for offset in range(len(after)) if before[offset] != after[offset]]
    spans: list[list[int]] = []
    for offset in changed:
        if spans and offset - spans[-1][1] <= RUN_GAP:
            spans[-1][1] = offset
        else:
            spans.append([offset, offset])
    return [(start, before[start:end + 1], after[start:end + 1]) for start, end in spans]


def _moved_from(original: bytes, after: bytes, start: int, dest: int) -> tuple[int, int] | None:
    """(source, length) of the longest stretch of after[start:] (with MOVE_MIN bytes or more
    that are not free-space fill) that the original game holds near `dest` but not at `dest`."""
    best: tuple[int, int] | None = None
    low, high = max(dest - MOVE_DISTANCE, 0), dest + MOVE_DISTANCE
    for length in range(len(after) - start, MOVE_MIN - 1, -1):
        stretch = after[start:start + length]
        if len(stretch) - stretch.count(FREE_SPACE_FILL) < MOVE_MIN:
            continue
        source = original.find(stretch, low, high + length)
        while source == dest:
            source = original.find(stretch, source + 1, high + length)
        if source >= 0:
            best = (source, length)
            break
    return best


def run_pieces(offset: int, before: bytes, after: bytes, original: bytes) -> list[tuple[int, Piece]]:
    """A run of written bytes as pieces: ZORA's own bytes, and Original pieces for the original
    game's bytes the run keeps (unchanged here and as in PRG0) or moves (MOVE_MIN or more)."""
    pieces: list[tuple[int, Piece]] = []
    own = bytearray()

    def flush(at: int) -> None:
        if own:
            pieces.append((at - len(own), bytes(own)))
            own.clear()

    i = 0
    while i < len(after):
        dest = offset + i
        kept = 0
        while (i + kept < len(after) and before[i + kept] == after[i + kept] == original[dest + kept]
               and original[dest + kept] != FREE_SPACE_FILL):
            kept += 1
        if kept:
            flush(dest)
            pieces.append((dest, Original(dest, kept)))
            i += kept
            continue
        moved = _moved_from(original, after, i, dest)
        if moved is not None:
            flush(dest)
            pieces.append((dest, Original(*moved)))
            i += moved[1]
            continue
        own.append(after[i])
        i += 1
    flush(offset + len(after))
    return pieces


def file_offset(cpu_address: int, bank: int) -> int:
    base = FIXED_BANK_BASE if bank == FIXED_BANK else SWITCHED_BANK_BASE
    return NES_HEADER_SIZE + bank * BANK_SIZE + cpu_address - base


def export_offsets(exports: dict[str, int]) -> dict[str, int]:
    """ZORA_<BANK>_<name> labels -> file offsets (the bank is in the name,
    since ld65's label file has CPU addresses only)."""
    offsets = {}
    for label, cpu_address in exports.items():
        match = re.match(rf"{EXPORT_PREFIX}B(\d)_", label)
        if not match:
            raise SystemExit(f"{label}: exported data labels are named ZORA_B<bank>_...")
        offsets[label] = file_offset(cpu_address, int(match[1]))
    return offsets


Patches = dict[str, list[tuple[int, Piece]]]


class SourceTree:
    """The pinned disassembly's sources in work/src, with patches applied one at a time, and
    the last build (image, exported labels, debug file)."""

    def __init__(self, work: Path) -> None:
        self.src, self.bins, self.obj = work / "src", work / "bin", work / "obj"
        rom = verify_base_rom().read_bytes()
        extract_bins(rom, self.bins)
        pristine_sources(self.src)
        self.image, self.exports = assemble(self.src, self.bins, self.obj)
        if self.image != rom:
            raise SystemExit("the pinned disassembly does not rebuild PRG0")

    def lines(self) -> dict[int, SourceLine]:
        return source_lines(self.obj / DEBUG_FILE)

    def apply(self, patch: Patch, leave_out: frozenset[str] = frozenset(),
              replaced_routines: dict[tuple[str, int], str] | None = None) -> bytes:
        """Apply `patch` and rebuild; return the new image."""
        apply_patch(self.src, patch, self.lines(), leave_out, replaced_routines)
        self.image, self.exports = assemble(self.src, self.bins, self.obj)
        return self.image

    def copy(self, work: Path) -> "SourceTree":
        """An independent copy in `work` (the same sources and last build)."""
        for part in ("src", "bin", "obj"):
            if (work / part).exists():
                shutil.rmtree(work / part)
            shutil.copytree(getattr(self, {"bin": "bins"}.get(part, part)), work / part)
        clone = object.__new__(SourceTree)
        clone.src, clone.bins, clone.obj = work / "src", work / "bin", work / "obj"
        clone.image, clone.exports = self.image, dict(self.exports)
        return clone


def patch_pieces(before: bytes, after: bytes, original: bytes) -> list[tuple[int, Piece]]:
    """What a patch writes: its changed runs against the build before it, as pieces."""
    return [piece for offset, old, new in changed_runs(before, after)
            for piece in run_pieces(offset, old, new, original)]


def build_all() -> tuple[Patches, dict[str, int]]:
    original = verify_base_rom().read_bytes()
    tree = SourceTree(scratch("asm"))
    patches: Patches = {}
    for name in series():
        before = tree.image
        patches[name] = patch_pieces(before, tree.apply(series_patch(name)), original)
    return patches, export_offsets(tree.exports)


def fromhex_lines(prefix: str, data: bytes, suffix: str) -> list[str]:
    """`prefix` + bytes.fromhex("...") + `suffix` as source lines of at most
    LINE_LIMIT characters (Archipelago's ruff line length): a long hex string
    goes on as adjacent string literals, each line aligned under its opening
    quote and holding whole bytes."""
    head, tail = f'{prefix}bytes.fromhex("', f'"){suffix}'
    text = data.hex()
    if len(head) + len(text) + len(tail) <= LINE_LIMIT:
        return [f"{head}{text}{tail}"]
    width = (LINE_LIMIT - len(head) - len(tail)) // 2 * 2
    chunks = [text[start:start + width] for start in range(0, len(text), width)]
    indent = " " * (len(head) - 1)
    lines = [f'{head}{chunks[0]}"'] + [f'{indent}"{chunk}"' for chunk in chunks[1:]]
    lines[-1] = lines[-1][:-1] + tail
    return lines


def piece_lines(indent: str, offset: int, piece: Piece) -> list[str]:
    """One (file offset, piece) entry as source lines."""
    if isinstance(piece, Original):
        return [f"{indent}(0x{offset:05X}, Original(0x{piece.source:05X}, {piece.length})),"]
    return fromhex_lines(f"{indent}(0x{offset:05X}, ", piece, "),")


def render(patches: Patches, symbols: dict[str, int]) -> str:
    lines = ['"""ZORA\'s 6502 patches as bytes (docs/rom-map.md).',
             "",
             "Generated by `python3 scripts/asm_patches.py build` from asm/; do not edit.",
             "Each patch is a tuple of (file offset, piece) writes, against PRG0 with the",
             "patches before it applied: a piece is ZORA's own bytes, or an Original",
             "(source, length): bytes of the original game that the patch keeps or moves,",
             "read from the player's ROM when it is written (never stored here).",
             '"""',
             # zora/ imports itself relatively (scripts/check_imports.py)
             "from .base_rom import Original, Piece",
             "",
             "PATCHES: dict[str, tuple[tuple[int, Piece], ...]] = {"]
    for name, pieces in patches.items():
        lines.append(f'    "{name}": (')
        for offset, piece in pieces:
            lines += piece_lines("        ", offset, piece)
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    lines.append("# Data the passes fill per seed: exported label -> file offset.")
    lines.append("SYMBOLS: dict[str, int] = {")
    lines.extend(f'    "{label}": 0x{offset:05X},' for label, offset in sorted(symbols.items()))
    lines.append("}")
    return "\n".join(lines) + "\n"


def report(patches: Patches) -> None:
    for name, pieces in patches.items():
        own = sum(len(piece) for _, piece in pieces if not isinstance(piece, Original))
        print(f"{name}: {own} bytes of ZORA's in {len(pieces)} pieces")
        for offset, piece in pieces:
            shown = (f"original 0x{piece.source:05X} x{piece.length}" if isinstance(piece, Original)
                     else piece.hex())
            print(f"    0x{offset:05X}  {shown}")


# --- editing ----------------------------------------------------------------

def series_through(name: str, work: Path) -> SourceTree:
    """A source tree with the series applied up to, not including, `name` (all of it if
    `name` is not in the series)."""
    names = series()
    tree = SourceTree(work)
    for earlier in names[:names.index(name)] if name in names else names:
        tree.apply(series_patch(earlier))
    return tree


def edit(name: str) -> None:
    """Write the sources with the series applied through `name` to temp/asm/edit/src, to read
    a patch's hooks and routines in place. Edits go to asm/NAME/, never to that folder."""
    tree = series_through(name, scratch("asm-edit"))
    tree.apply(series_patch(name))
    shutil.rmtree(EDIT_TREE, ignore_errors=True)
    shutil.copytree(tree.src, EDIT_TREE / "src")
    print(f"the series through {name}: {EDIT_TREE / 'src'}")


def refresh(name: str) -> None:
    """Check that `name` applies on the series before it, and list each hook's site."""
    tree = series_through(name, scratch("asm-refresh"))
    patch = series_patch(name)
    lines = tree.lines()
    for hook in patch.hooks:
        file, site = hook_site(lines, name, hook)
        print(f"{name}.{hook.name}: 0x{hook.offset:05X} +{hook.length}, {file} line {site[0]}: {hook.note}")
    tree.apply(patch)
    print(f"{name} applies")


def locate(file: str, line: int) -> None:
    """The file offset and length of a line of the pinned disassembly."""
    tree = SourceTree(scratch("asm-locate"))
    found = [source for source in tree.lines().values() if source.file == file and source.line == line]
    if not found:
        raise SystemExit(f"{file} line {line} assembles to no bytes")
    for source in found:
        print(f"{file} line {line}: file offset 0x{source.offset:05X}, {source.size} bytes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("build", "check", "edit", "refresh", "locate"))
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    if args.command in ("edit", "refresh"):
        if len(args.args) != 1:
            parser.error("NAME required")
        (edit if args.command == "edit" else refresh)(args.args[0])
        return 0
    if args.command == "locate":
        if len(args.args) != 2:
            parser.error("FILE and LINE required")
        locate(args.args[0], int(args.args[1]))
        return 0
    patches, symbols = build_all()
    report(patches)
    text = render(patches, symbols)
    if args.command == "build":
        OUTPUT.write_text(text)
        print(f"wrote {OUTPUT.relative_to(REPO)}")
        return 0
    if OUTPUT.read_text() != text:
        print(f"{OUTPUT.relative_to(REPO)} is out of date: run `scripts/asm_patches.py build`")
        return 1
    print("up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
