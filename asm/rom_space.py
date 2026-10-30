"""ROM space: the free space, the reservations and every claim on them, from asm/rom_space.toml
(docs/rom-map.md; asm/README.md "Adding a patch").

One table holds PRG0's free ranges, the ranges reserved for others (z1rr-coop's), each segment's
slot, the bytes ZORA's Python writes in free space (sites) and the bytes two owners may both write
(shared). Owners are named "series:FOLDER", "flags2:FOLDER", "asnb:FOLDER", "setting:SETTING",
"site:NAME" and "z1rr-coop".

`problems()` is the one overlap check: every builder's bytes (zora/rom's generated patch data),
every slot, site and reservation together. A byte claimed by two owners must lie in a [[shared]]
row naming both, and a builder's byte in free space must lie in one of its owner's slots (or a
shared range naming it). tests/test_rom_space.py runs it; the builders read the slots and the
free ranges from here (scripts/asm_patches.py places new segments with them).

Imported by path (asm/ is not a package): scripts/asm_patches.py and the tests load it with
importlib, the repository root on sys.path for zora.rom's data modules.
"""
import tomllib
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

TABLE = Path(__file__).resolve().parent / "rom_space.toml"

NES_HEADER_SIZE = 0x10
BANK_SIZE = 0x4000
FIXED_BANK = 7
SWITCHED_BANK_BASE = 0x8000
FIXED_BANK_BASE = 0xC000
COOP = "z1rr-coop"


def file_offset(bank: int, cpu_address: int) -> int:
    """The headered file offset of a CPU address in a bank."""
    base = FIXED_BANK_BASE if bank == FIXED_BANK else SWITCHED_BANK_BASE
    return NES_HEADER_SIZE + bank * BANK_SIZE + cpu_address - base


def cpu_address(offset: int) -> tuple[int, int]:
    """(bank, CPU address) of a headered file offset."""
    bank, inside = divmod(offset - NES_HEADER_SIZE, BANK_SIZE)
    return bank, inside + (FIXED_BANK_BASE if bank == FIXED_BANK else SWITCHED_BANK_BASE)


@dataclass(frozen=True)
class Area:
    """CPU addresses `first`-`last` (inclusive) in `bank`, with its owner and what it is."""
    bank: int
    first: int
    last: int
    owner: str = ""
    what: str = ""
    # A free run inside the disassembly's own segments: no segment can be linked there.
    inside_code: bool = False

    def file_range(self) -> range:
        start = file_offset(self.bank, self.first)
        return range(start, start + self.last - self.first + 1)

    def __len__(self) -> int:
        return self.last - self.first + 1

    def __str__(self) -> str:
        label = f" {self.owner}" if self.owner else ""
        return f"bank {self.bank} ${self.first:04X}-${self.last:04X}{label}" + (f" ({self.what})" if self.what else "")


@dataclass(frozen=True)
class Slot(Area):
    """A segment's slot (`segment`), or the range of an in-place hook over PRG0's free bytes (`hook`)."""
    segment: str = ""
    hook: str = ""


@dataclass(frozen=True)
class Site(Area):
    """Bytes ZORA's Python writes in free space; `source` is "module:CONSTANT", the first byte's offset."""
    source: str = ""


@dataclass(frozen=True)
class Shared:
    """Bytes two or more owners may all write, and how they go together (asm/rom_space.toml)."""
    owners: frozenset[str]
    areas: tuple[Area, ...]
    together: str
    why: str
    flags: dict[str, dict[str, Any]] = field(default_factory=dict, compare=False, hash=False)

    def covers(self, owners: Iterable[str], offset: int) -> bool:
        return set(owners) <= self.owners and any(offset in area.file_range() for area in self.areas)


TOGETHER = ("chained", "exclusive", "retired")


@dataclass(frozen=True)
class Table:
    free: tuple[Area, ...]
    reserved: tuple[Area, ...]
    reserved_instructions: tuple[Area, ...]
    slots: tuple[Slot, ...]
    sites: tuple[Site, ...]
    shared: tuple[Shared, ...]

    def reserved_bytes(self) -> dict[int, Area]:
        return {offset: area for area in self.reserved + self.reserved_instructions for offset in area.file_range()}

    def slot(self, segment: str, bank: int, start: int) -> Slot | None:
        """The slot of the segment that starts at `start` in `bank`."""
        return next((slot for slot in self.slots
                     if (slot.segment, slot.bank, slot.first) == (segment, bank, start)), None)


def _area(row: dict[str, Any], kind: type[Area] = Area, **extra: Any) -> Any:
    return kind(row["bank"], row["first"], row["last"], row.get("owner", ""), row.get("what", ""), **extra)


@cache
def table(path: Path = TABLE) -> Table:
    spec = tomllib.loads(path.read_text())
    shared = []
    for row in spec.get("shared", []):
        if row["together"] not in TOGETHER:
            raise ValueError(f"{path.name}: shared {row['owners']}: together is one of {TOGETHER}")
        shared.append(Shared(frozenset(row["owners"]), tuple(Area(*area) for area in row["ranges"]),
                             row["together"], row["why"], row.get("flags", {})))
    return Table(
        free=tuple(_area(row, inside_code=row.get("inside_code", False)) for row in spec.get("free", [])),
        reserved=tuple(_area(row) for row in spec.get("reserved", [])),
        reserved_instructions=tuple(_area(row) for row in spec.get("reserved_instructions", [])),
        slots=tuple(_area(row, Slot, segment=row.get("segment", ""), hook=row.get("hook", ""))
                    for row in spec.get("slot", [])),
        sites=tuple(Site(row["bank"], row["first"], row["last"], f"site:{row['name']}", row.get("what", ""),
                         row.get("source", "")) for row in spec.get("site", [])),
        shared=tuple(shared),
    )


# --- the builders' bytes ---------------------------------------------------------------------------

Pieces = tuple[tuple[int, Any], ...]


def _written(pieces: Pieces) -> set[int]:
    from zora.rom.base_rom import piece_length
    return {offset + index for offset, piece in pieces for index in range(piece_length(piece))}


def builder_bytes() -> dict[str, set[int]]:
    """Every byte each builder's patches may write, by owner: zora/rom's generated data for
    asm/series.txt (progressive items included), asm/flags2, asm/asnb and asm/settings (every choice of
    a setting). asm/progressive's harness builds the series' own fp-prog patches again."""
    from zora.rom.asnb_patch_data import PATCHES as ASNB
    from zora.rom.code_patch_data import PATCHES as SERIES
    from zora.rom.flags2_patch_data import PATCHES as FLAGS2
    from zora.rom.player_settings_data import SETTINGS
    owners: dict[str, set[int]] = defaultdict(set)
    for prefix, patches in (("series", SERIES), ("flags2", FLAGS2), ("asnb", ASNB)):
        for name, pieces in patches.items():
            owners[f"{prefix}:{name}"] |= _written(pieces)
    for setting, choices in SETTINGS.items():
        for pieces in choices.values():
            owners[f"setting:{setting}"] |= _written(pieces)
    return dict(owners)


# --- the check -----------------------------------------------------------------------------------

def claims(space: Table, written: dict[str, set[int]],
           placed: Iterable[Area] = ()) -> dict[int, set[str]]:
    """Each claimed byte's owners: the builders' bytes, the slots, the sites, the reservations and
    the placements of new segments (`placed`, owner set)."""
    claimed: dict[int, set[str]] = defaultdict(set)
    for owner, offsets in written.items():
        for offset in offsets:
            claimed[offset].add(owner)
    for area in (*space.slots, *space.sites, *space.reserved, *space.reserved_instructions, *placed):
        for offset in area.file_range():
            claimed[offset].add(area.owner)
    return claimed


def _runs(offsets: Iterable[int]) -> Iterator[tuple[int, int]]:
    """Consecutive offsets as (first, last) runs."""
    run: list[int] = []
    for offset in sorted(offsets):
        if run and offset != run[-1] + 1:
            yield run[0], run[-1]
            run = []
        run.append(offset)
    if run:
        yield run[0], run[-1]


def _describe(first: int, last: int) -> str:
    bank, start = cpu_address(first)
    return f"bank {bank} ${start:04X}-${cpu_address(last)[1]:04X} (0x{first:05X}-0x{last:05X})"


def problems(space: Table | None = None, written: dict[str, set[int]] | None = None,
             placed: Iterable[Area] = ()) -> list[str]:
    """The overlap check: every byte two owners claim lies in a shared row naming them, every
    builder byte in free space lies in its owner's slot or placement (or a shared range naming it),
    and the slots and placements lie in free space. `placed` defaults to asm/placements.toml's.
    Empty when everything fits."""
    space = space or table()
    written = builder_bytes() if written is None else written
    placed = tuple(placed) or tuple(area for row in placements() for area in row.areas())
    found: list[str] = []
    claimed = claims(space, written, placed)
    clashes: dict[frozenset[str], list[int]] = defaultdict(list)
    for offset, owners in claimed.items():
        if len(owners) > 1 and not any(shared.covers(owners, offset) for shared in space.shared):
            clashes[frozenset(owners)].append(offset)
    for clashing, clashed in sorted(clashes.items(), key=lambda item: min(item[1])):
        found += [f"{_describe(first, last)}: claimed by {', '.join(sorted(clashing))} with no [[shared]] row"
                  for first, last in _runs(clashed)]
    free = {offset for area in space.free for offset in area.file_range()}
    owned: dict[str, set[int]] = defaultdict(set)
    for area in (*space.slots, *placed):
        owned[area.owner] |= set(area.file_range())
    for owner, writes in sorted(written.items()):
        loose = {offset for offset in writes & free - owned[owner]
                 if not any(shared.covers((owner,), offset) for shared in space.shared)}
        for first, last in _runs(loose):
            found.append(f"{_describe(first, last)}: {owner} writes free space outside its slots")
    for area in (*space.slots, *placed):
        if not set(area.file_range()) <= free:
            found.append(f"{area}: a slot outside the free space")
    for shared in space.shared:
        named = set(shared.owners)
        known = set(written) | {area.owner for area in (*space.slots, *space.sites, *space.reserved)}
        if named - known:
            found.append(f"shared {sorted(shared.owners)}: no such owner {sorted(named - known)}")
        if not any(len(claimed.get(offset, set()) & shared.owners) > 1
                   for area in shared.areas for offset in area.file_range()):
            found.append(f"shared {sorted(shared.owners)}: no byte of its ranges is shared (stale row)")
    return found


# --- placing new segments --------------------------------------------------------------------------
# A segment that leaves out `start` gives its `size` and either `bank`, `banks` (any one of them,
# tried in order) or `mirrored` (the same address in each, a common window). The build places it in
# free space no claim touches, at the lowest address aligned to `align` (default $10), in the order
# the builders load their patches, and records the placement in asm/placements.toml. A recorded
# placement is kept on every later build, so adding a patch never moves an existing one; a placement
# moves only when its row is deleted.

PLACEMENTS = Path(__file__).resolve().parent / "placements.toml"
DEFAULT_ALIGN = 0x10
PLACEMENTS_HEADER = """\
# Where the build placed each segment that leaves out `start` (asm/rom_space.py, asm/README.md
# "Adding a patch"). Written by the builders, committed with the patch. A row is kept on every later
# build, so adding a patch never moves an existing one; delete a row only to move that segment on
# purpose (its ROM bytes change).
"""


class PlacementError(SystemExit):
    """A segment cannot be placed, or its recorded placement no longer matches it."""


@dataclass(frozen=True)
class Placement:
    """A placed segment: its banks (one, or each bank of a mirrored segment), start and size."""
    segment: str
    owner: str
    banks: tuple[int, ...]
    start: int
    size: int
    mirrored: bool = False

    def areas(self) -> tuple[Area, ...]:
        return tuple(Area(bank, self.start, self.start + self.size - 1, self.owner, self.segment)
                     for bank in self.banks)


@dataclass(frozen=True)
class Request:
    """A segment to place, as its patch.toml gives it."""
    segment: str
    owner: str
    banks: tuple[int, ...]
    size: int
    mirrored: bool = False
    align: int = DEFAULT_ALIGN

    def matches(self, placement: Placement) -> bool:
        if (placement.owner, placement.size, placement.mirrored) != (self.owner, self.size, self.mirrored):
            return False
        return placement.banks == self.banks if self.mirrored else placement.banks[0] in self.banks


def placements(path: Path = PLACEMENTS) -> tuple[Placement, ...]:
    if not path.exists():
        return ()
    return tuple(Placement(row["segment"], row["owner"], tuple(row["banks"]), row["start"], row["size"],
                           row.get("mirrored", False))
                 for row in tomllib.loads(path.read_text()).get("placement", []))


def write_placements(rows: Iterable[Placement], path: Path = PLACEMENTS) -> None:
    lines = [PLACEMENTS_HEADER]
    for row in rows:
        lines += ["", "[[placement]]", f'segment = "{row.segment}"', f'owner = "{row.owner}"',
                  f"banks = [{', '.join(str(bank) for bank in row.banks)}]", f"start = 0x{row.start:04X}",
                  f"size = 0x{row.size:02X}"]
        if row.mirrored:
            lines.append("mirrored = true")
    path.write_text("\n".join(lines) + "\n")


def _fits(claimed: dict[int, set[str]], free: set[int], bank: int, start: int, size: int) -> bool:
    return all(offset in free and offset not in claimed
               for offset in range(file_offset(bank, start), file_offset(bank, start) + size))


def find_space(request: Request, space: Table, claimed: dict[int, set[str]]) -> Placement | None:
    """The lowest aligned start, in the first of the request's banks that has room (every bank, for a
    mirrored segment), where `size` free bytes outside the disassembly's segments are claimed by nobody."""
    linkable = [area for area in space.free if not area.inside_code]
    free = {offset for area in linkable for offset in area.file_range()}
    candidates = [request.banks] if request.mirrored else [(bank,) for bank in request.banks]
    for banks in candidates:
        starts = sorted({start for area in linkable if area.bank == banks[0]
                         for start in range(area.first + -area.first % request.align, area.last + 1, request.align)})
        for start in starts:
            if all(_fits(claimed, free, bank, start, request.size) for bank in banks):
                return Placement(request.segment, request.owner, banks, start, request.size, request.mirrored)
    return None


def place(request: Request, path: Path = PLACEMENTS, space: Table | None = None,
          written: dict[str, set[int]] | None = None) -> Placement:
    """The request's recorded placement, or a new one, recorded in `path` (the lock file)."""
    recorded = placements(path)
    found = next((row for row in recorded if row.segment == request.segment), None)
    if found is not None:
        if not request.matches(found):
            raise PlacementError(
                f"{request.segment}: asm/placements.toml places it as {found}, which no longer matches its "
                f"patch.toml ({request}); delete the row to place it again (its bytes move)")
        return found
    space = space or table()
    written = builder_bytes() if written is None else written
    claimed = claims(space, {owner: offsets for owner, offsets in written.items() if owner != request.owner},
                     (area for row in recorded for area in row.areas()))
    placement = find_space(request, space, claimed)
    if placement is None:
        raise PlacementError(f"{request.segment}: no {request.size} free bytes in bank(s) {list(request.banks)}")
    write_placements((*recorded, placement), path)
    return placement
