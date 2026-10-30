"""Build lozft, Quantam's FamiTracker driver for The Legend of Zelda, from its pinned source, and write
ZORA's patch data for it (docs/music.md "lozft from source"; docs/reports/research-lozft-from-source.md).

    python3 scripts/lozft_build.py              # build for PRG0 and PRG1, write zora/rom/music/lozft_patch_data.py
    python3 scripts/lozft_build.py --check      # build, and compare with the committed data (exit 1 if it differs)
    python3 scripts/lozft_build.py --upstream   # build the source as published (no defines) onto PRG1 and
                                                # compare with the source's own lozft.bps (exit 1 if it differs)

The source: lozft at LOZFT_COMMIT in LOZFT_REPOSITORY (Quantam's repository), with its submodule
bhop, exported from the clone music/lozft (ZORA_MUSIC names another music folder) by `git archive`,
never its working tree. The assembler: js65 JS65_VERSION, installed by npm into music/js65 with its
install scripts off and checked against JS65_INTEGRITY.
Node is needed here and nowhere else: the generated data is committed, so generation, the page,
the Archipelago world and releases never run this (owner decision, 2026-10-27).

The build, per release:
1. The base: the release grown to 256 KB, its fixed bank moved to bank 15 (lozft's Makefile's
   lozus1256k.nes, which its repository does not make).
2. ZORA's bytes kept from lozft: every byte asm/rom_space.py's claims name (each builder's patches,
   slots, sites, reservations), as fixed `.res` chunks, so js65 places lozft's relocatable code around
   them: on a music ROM (MUSIC_ROM_CHOICES), with MOVED's reserved where with_lozft_from_source
   moves them.
3. js65 assembles and links with ROM_256KB and, for PRG0, PRG0; no other define. ZORA's
   statistics screen counts frames from the end of the game's own DriveAudio, which lozft calls once
   a frame (asm/fp-stats-01-lozft2), and UpdateSoundPart2 stays at lozft's own $A000, ZORA's bank-0
   routines clear of it ($A200 on).
4. lozft's bytes are read from the link's debug file (each module's spans), never by diffing, and a
   module that overlaps a reservation stops the build: js65 lets fixed chunks overwrite each other.
5. The music layout the importer needs (the song table, the module addresses, the music banks and
   the songs' numbers) is read from lozft.ftcfg and the link's symbols, never written here, so a
   change of lozft's layout only means running this again.
6. They are encoded as ZORA's pieces: runs of MIN_COPY or more bytes equal to the game's own (code
   lozft moves) become Original copies read from the player's ROM, never from its tiles
   (revision.GRAPHICS_BLOCKS), so the data holds no byte of the original game; a literal left with a
   run the release scan would flag stops the build.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "asm"))
sys.path.insert(0, str(REPO / "scripts"))

import rom_space  # noqa: E402
from music_assets import music_folder  # noqa: E402

from zora.rom import base_rom  # noqa: E402
from zora.rom.base_rom import Original, Piece  # noqa: E402
from zora.rom.music import json5  # noqa: E402
from zora.rom.music.lozft import SET_ITEM_ROUTINES, SET_ITEM_ROUTINES_SHIFT, apply_bps  # noqa: E402
from zora.rom.player_settings_data import SETTINGS  # noqa: E402
from zora.rom.revision import (  # noqa: E402
    GRAPHICS_BLOCKS,
    NES_HEADER_SIZE,
    PRG1_MOVES,
    Revision,
    prg1_offset,
)

# --- the pin ---------------------------------------------------------------------------------------
UPSTREAM_REPOSITORY = "https://github.com/TheRealQuantam/lozft.git"
UPSTREAM_COMMIT = "638630aa43c8520bb8f67156021e1c4502ecc3b0"      # lozft as Quantam published it
LOZFT_REPOSITORY = UPSTREAM_REPOSITORY
# Quantam's main after his merge of pull request #1 (39d0025, 2026-10-28: the PRG0 option, -D PRG0,
# on his eb17d16, which has the header's battery bit; the same tree as ZORA's fork's 31e3bb7, the pin
# before it) and his hooks for other hosts (LOZFT_EXT_HOST, which ZORA does not define). Built as
# published it is his committed lozft.bps byte for byte; ZORA's build is 39d0025's.
LOZFT_COMMIT = "44b1bb5d97fb7e6946c28517d8104a176d693692"
BHOP_COMMIT = "fb1eef0c1ebad6adc56a8c8954bb366e844ed7d0"         # lozft's submodule at LOZFT_COMMIT
JS65_VERSION = "2.3.1"
JS65_INTEGRITY = ("sha512-NWgBcDdbwgkdprkzD1ttu2LjNIJ1f6vXpJNklwlAHqTaJVaxHvhEKrImaWhpel+QkMUxJGCD9Gcmi"
                  "+kMr033NQ==")

DATA_FILE = REPO / "zora" / "rom" / "music" / "lozft_patch_data.py"
SCRATCH = REPO / "temp" / "lozft-build"
SOURCE_FILES = ("clearoamopt", "config", "ctlropt", "lozft", "mmc3", "moncollopt", "preservesram")
ASSEMBLE = ("-Wno-jsr-rts-tail-call", "-c", "-g")        # the Makefile's JS65_ASM
BHOP_DEFINES = ("MMC=1",)
RESERVE_MODULE = "zora_reserved"

BANK_SIZE = 0x4000
GAME_BANKS = 8
LOZFT_BANKS = 16
FIXED_BANK, LOZFT_FIXED_BANK = 7, 15
SWITCHED_BASE, FIXED_BASE = 0x8000, 0xC000
PRG_BANKS_BYTE = 4               # the iNES header's count of 16 KB banks
EMPTY_BANK_FILL = 0xFF           # the base's new banks 7-14 (lozft fills them with $00 itself)

MIN_COPY = 6                     # a run this long equal to the game's own bytes is copied, not stored
SCAN_RUN = 8                     # make_release.py's MIN_GAME_BYTES: the release scan's hit length
FILLER_VALUES = 3                # make_release.py's: a run of at most this many values is filler

# The choice a lozft2 music ROM always has, for a setting whose choices differ in where they write:
# its own bytes are ZORA's claims there, not every choice's (the statistics screen's "lozft2" choice,
# with_lozft_from_source's, puts StatsTick at $B000 and leaves $8000-$8131 the game's own, where
# lozft's song table goes).
MUSIC_ROM_CHOICES = {"statistics_screen": "lozft2"}
# Where the importer finds lozft's song table and module addresses (lozft.ftcfg's offsets in bank 0),
# checked against the link's own symbols.
TABLE_SYMBOLS = {"track_map_tbl_offs": "TrackMapTable", "track_mod_tbl_offs": "TrackAddrTable"}
BANK_SWITCH = "Switch16kBank"            # lozft's bank switch, at the game's SwitchBank (MOVED's reason)
FTCFG = "lozft.ftcfg"
HEX_NUMBER = re.compile(r"\b0x([0-9A-Fa-f]+)\b")

# ZORA's code at the fixed bank's $FFC0-$FFD2 (fp-book-01 and the bomb upgrade's store and tail), which
# lozft's bank switch ($FFAC-$FFC2) overlaps: with_lozft_from_source moves it 3 bytes on
# (zora/rom/music/lozft.py SET_ITEM_ROUTINES), so it is reserved there.
MOVED = (FIXED_BANK, SET_ITEM_ROUTINES.start, SET_ITEM_ROUTINES.stop - 1, SET_ITEM_ROUTINES_SHIFT)


class BuildError(SystemExit):
    pass


# --- tools and source ------------------------------------------------------------------------------

def run(*command: str | Path) -> str:
    result = subprocess.run([str(part) for part in command], capture_output=True, text=True)
    if result.returncode:
        raise BuildError(f"{' '.join(map(str, command))}:\n{result.stdout}{result.stderr}")
    return result.stdout


def js65() -> Path:
    """The pinned js65's command line, installed into the music folder on first use."""
    prefix = music_folder() / "js65"
    entry = prefix / "node_modules" / "js65" / "integrations" / "npm" / "js65.mjs"
    if not entry.exists():
        run("npm", "install", "--prefix", prefix, "--ignore-scripts", "--no-audit", "--no-fund",
            f"js65@{JS65_VERSION}")
    lock = json.loads((prefix / "package-lock.json").read_text())["packages"]["node_modules/js65"]
    if (lock["version"], lock["integrity"]) != (JS65_VERSION, JS65_INTEGRITY):
        raise BuildError(f"{prefix}: js65 {lock['version']} is not the pinned {JS65_VERSION} "
                         "(remove the folder to reinstall)")
    return entry


def export_source(commit: str, dest: Path) -> Path:
    """lozft at `commit` and bhop at the commit its tree names, exported from music/lozft's history."""
    clone = music_folder() / "lozft"
    if not (clone / ".git").exists():
        raise BuildError(f"no lozft clone at {clone}: git clone {LOZFT_REPOSITORY or UPSTREAM_REPOSITORY} "
                         f"{clone}, then git -C {clone} submodule update --init")
    if subprocess.run(["git", "-C", str(clone), "cat-file", "-e", f"{commit}^{{commit}}"]).returncode:
        run("git", "-C", clone, "fetch", "--quiet", LOZFT_REPOSITORY)
    bhop = run("git", "-C", clone, "ls-tree", commit, "bhop").split()[2]
    if commit == LOZFT_COMMIT and bhop != BHOP_COMMIT:
        raise BuildError(f"lozft {commit[:7]} names bhop {bhop[:7]}, not the pinned {BHOP_COMMIT[:7]}")
    dest.mkdir(parents=True, exist_ok=True)
    for repository, tree, folder in ((clone, commit, dest), (clone / "bhop", bhop, dest / "bhop")):
        folder.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(["git", "-C", str(repository), "archive", tree], capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", str(folder)], input=archive.stdout, check=True)
    return dest


# --- the base and ZORA's reservations ----------------------------------------------------------------

def release(revision: Revision) -> bytes:
    """The repo's own release of `revision` (AGENTS.md "Base ROM"), its hashes checked."""
    return (base_rom.verify_base_rom() if revision is Revision.PRG0 else base_rom.verify_prg1_rom()).read_bytes()


def prg0_offset(offset: int) -> int:
    """Where PRG1's file offset `offset` is in PRG0 (revision.prg1_offset's inverse)."""
    move = next((move for move in PRG1_MOVES if move.start + move.shift <= offset < move.end + move.shift), None)
    return offset - move.shift if move else offset


def grown(game: bytes) -> bytes:
    """The release as lozft's build base: 16 banks, the fixed bank last, banks 7-14 empty."""
    header = bytearray(game[:NES_HEADER_SIZE])
    header[PRG_BANKS_BYTE] = LOZFT_BANKS
    banks = game[NES_HEADER_SIZE:]
    fixed = FIXED_BANK * BANK_SIZE
    return (bytes(header) + banks[:fixed] + bytes([EMPTY_BANK_FILL]) * ((LOZFT_BANKS - GAME_BANKS) * BANK_SIZE)
            + banks[fixed:fixed + BANK_SIZE])


@dataclass(frozen=True)
class Claim:
    owner: str
    bank: int
    first: int       # CPU addresses, inclusive
    last: int

    def without(self, rule: tuple[str, int, int, int]) -> list[Claim]:
        """The claim with a rule's bytes taken out (none, one or two runs)."""
        owner, bank, first, last = rule
        if self.owner != owner or self.bank != bank or last < self.first or self.last < first:
            return [self]
        return [Claim(self.owner, self.bank, start, end)
                for start, end in ((self.first, first - 1), (last + 1, self.last)) if start <= end]


def music_rom_bytes() -> dict[str, set[int]]:
    """Each builder's bytes (asm/rom_space.py builder_bytes), a MUSIC_ROM_CHOICES setting's being that
    choice's alone where it differs from the game's own bytes."""
    written: dict[str, set[int]] = rom_space.builder_bytes()
    for setting, choice in MUSIC_ROM_CHOICES.items():
        offsets = set()
        for offset, piece in SETTINGS[setting][choice]:
            data = base_rom.piece_bytes(piece)
            offsets |= {offset + index for index, byte in enumerate(data)
                        if byte != base_rom.original_bytes(offset + index, 1)[0]}
        written[f"setting:{setting}"] = offsets
    return written


def zora_claims() -> list[Claim]:
    """Every byte ZORA may write on a music ROM (asm/rom_space.py's claims: builders, slots, sites,
    reservations and placements; music_rom_bytes), as runs per owner, PRG0 CPU addresses."""
    base_rom.remember_repo_base_rom()
    placed = [area for row in rom_space.placements() for area in row.areas()]
    written = music_rom_bytes()
    space = rom_space.table()
    # A MUSIC_ROM_CHOICES setting's slots: only those its music ROM's choice writes in (the statistics
    # screen's other StatsTick slot is for ROMs without music).
    music_owners = {f"setting:{setting}" for setting in MUSIC_ROM_CHOICES}
    slots = tuple(slot for slot in space.slots if slot.owner not in music_owners
                  or written[slot.owner] & set(slot.file_range()))
    claimed = rom_space.claims(dataclasses.replace(space, slots=slots), written, placed)
    by_owner: dict[str, set[int]] = defaultdict(set)
    for offset, owners in claimed.items():
        for owner in owners:
            by_owner[owner].add(offset)
    runs = []
    for owner, offsets in sorted(by_owner.items()):
        for first, last in rom_space._runs(offsets):
            bank, start = rom_space.cpu_address(first)
            runs.append(Claim(owner, bank, start, start + last - first))
    return runs


def reserved(claims: list[Claim]) -> list[Claim]:
    """The claims lozft must keep clear of, MOVED's where they move to."""
    kept = claims
    bank, first, last, shift = MOVED
    moved = [Claim(claim.owner, bank, max(claim.first, first) + shift, min(claim.last, last) + shift)
             for claim in kept if claim.bank == bank and claim.first <= last and first <= claim.last]
    kept = [part for claim in kept for part in claim.without((claim.owner, bank, first, last))]
    return kept + moved


def lozft_place(offset: int) -> str:
    """A file offset of lozft's 256 KB ROM as bank and CPU address."""
    bank, inside = divmod(offset - NES_HEADER_SIZE, BANK_SIZE)
    return f"bank {bank} ${inside + (FIXED_BASE if bank == LOZFT_FIXED_BANK else SWITCHED_BASE):04X}"


def reservation_source(claims: list[Claim], revision: Revision) -> str:
    """ZORA's claimed bytes as fixed js65 chunks, at the revision's own addresses."""
    lines = ["; ZORA's bytes, kept from lozft's relocatable code (generated by scripts/lozft_build.py)"]
    covered: dict[int, set[int]] = defaultdict(set)
    for claim in claims:
        for address in range(claim.first, claim.last + 1):
            offset = rom_space.file_offset(claim.bank, address)
            if revision is Revision.PRG1:
                offset = prg1_offset(offset)
            covered[claim.bank].add(rom_space.cpu_address(offset)[1])
    for bank, addresses in sorted(covered.items()):
        lines.append(f'.segment "BANK{bank}"')
        for first, last in rom_space._runs(addresses):
            lines.append(f".org ${first:04X}\n.res {last - first + 1}")
    return "\n".join(lines) + "\n"


# --- the link and its debug file ----------------------------------------------------------------------

def defines(revision: Revision) -> list[str]:
    names = ["ROM_256KB"]
    return names + (["PRG0"] if revision is Revision.PRG0 else [])


def link(source: Path, base: bytes, out: Path, chosen: list[str], extra: str | None = None) -> tuple[bytes, Path]:
    """lozft assembled with `chosen` defines and linked onto `base` (and `extra`, more source); the
    ROM and its debug file."""
    tool = js65()
    out.mkdir(parents=True, exist_ok=True)
    flags = [part for name in chosen for part in ("-D", name)]
    objects = []
    for name in SOURCE_FILES:
        run("node", tool, *ASSEMBLE, "-I", out, "-I", source / "bhop" / "bhop", "-o", out / f"{name}.o",
            *flags, source / f"{name}.s")
        objects.append(out / f"{name}.o")
    run("node", tool, *ASSEMBLE, "-o", out / "bhop.o", *[part for name in BHOP_DEFINES for part in ("-D", name)],
        source / "bhop" / "bhop.s")
    objects.append(out / "bhop.o")
    if extra is not None:
        (out / f"{RESERVE_MODULE}.s").write_text(extra)
        run("node", tool, "-c", "-o", out / f"{RESERVE_MODULE}.o", out / f"{RESERVE_MODULE}.s")
        objects.append(out / f"{RESERVE_MODULE}.o")
    (out / "base.nes").write_bytes(base)
    run("node", tool, "-r", out / "base.nes", "-m", out / "map.txt", "--dbgfile", out / "lozft.dbg",
        "-o", out / "lozft.nes", *objects)
    return (out / "lozft.nes").read_bytes(), out / "lozft.dbg"


def _fields(line: str) -> tuple[str, dict[str, str]]:
    kind, _, rest = line.partition("\t")
    return kind, {key: value.strip('"') for key, value in re.findall(r'(\w+)=("[^"]*"|[^,]*)', rest)}


def module_bytes(debug: Path) -> dict[str, set[int]]:
    """The file offsets each module wrote: its scopes' spans, placed by their segments' output offsets."""
    segments: dict[str, int] = {}
    spans: dict[str, tuple[str, int, int]] = {}
    modules: dict[str, str] = {}
    scopes: list[tuple[str, list[str]]] = []
    for line in debug.read_text().splitlines():
        kind, fields = _fields(line)
        if kind == "seg" and "ooffs" in fields:
            segments[fields["id"]] = int(fields["ooffs"])
        elif kind == "span":
            spans[fields["id"]] = (fields["seg"], int(fields["start"]), int(fields["size"]))
        elif kind == "mod":
            modules[fields["id"]] = Path(fields["name"]).stem
        elif kind == "scope" and "span" in fields and "mod" in fields:
            scopes.append((fields["mod"], fields["span"].split("+")))
    written: dict[str, set[int]] = defaultdict(set)
    for module, ids in scopes:
        for span in ids:
            segment, start, size = spans[span]
            if segment in segments:
                written[modules[module]].update(range(segments[segment] + start, segments[segment] + start + size))
    return dict(written)


def symbols(debug: Path) -> dict[str, tuple[int, int, int | None]]:
    """Each label of the link: (CPU address, size or 0, file offset or None for RAM)."""
    segments: dict[str, tuple[int, int]] = {}
    scope_sizes: dict[str, int] = {}
    labels = []
    for line in debug.read_text().splitlines():
        kind, fields = _fields(line)
        if kind == "seg" and "ooffs" in fields:
            segments[fields["id"]] = (int(fields["start"], 16), int(fields["ooffs"]))
        elif kind == "scope" and "size" in fields and "name" in fields:
            scope_sizes[fields["name"]] = int(fields["size"])
        elif kind == "sym" and fields.get("type") == "lab" and "seg" in fields:
            labels.append(fields)
    out = {}
    for fields in labels:
        value = int(fields["val"], 16)
        segment = segments.get(fields["seg"])
        offset = segment[1] + value - segment[0] if segment else None
        out[fields["name"]] = (value, int(fields.get("size", scope_sizes.get(fields["name"], 0))), offset)
    return out


def ftcfg(source: Path) -> dict[str, Any]:
    """lozft.ftcfg, the layout lozft's importer reads (JSON5 with hex numbers)."""
    text = HEX_NUMBER.sub(lambda match: str(int(match.group(1), 16)), (source / FTCFG).read_text())
    config: dict[str, Any] = json5.loads(text)
    return config


def music_layout(config: dict[str, Any], labels: dict[str, tuple[int, int, int | None]]) -> dict[str, Any]:
    """What the importer needs, from lozft.ftcfg, checked against the link: the song table and module
    addresses (file offsets), the music banks (in bank_size units, switched in at base), the driver's
    bank, the song count and each song name's number."""
    layout: dict[str, Any] = {}
    for key, name in TABLE_SYMBOLS.items():
        offset = labels[name][2]
        in_bank_0 = config[key] if key in config else config["ft"][key]
        if offset != NES_HEADER_SIZE + in_bank_0:
            raise BuildError(f"{FTCFG}'s {key} (0x{in_bank_0:X}) is not where the link put {name}")
        layout["song_table" if key == "track_map_tbl_offs" else "module_addresses"] = offset
    (first_bank, end_bank), = config["free_banks"]
    layout.update(bank_size=config["bank_size"], banks=(first_bank, end_bank), base=config["free_bank_base"],
                  driver_bank=config["ft"]["src_bank_idx"], song_numbers=config["max_tracks"],
                  songs={name: number for number, name in enumerate(config["track_names"])})
    return layout


def check_moved(labels: dict[str, tuple[int, int, int | None]]) -> None:
    """MOVED still matches lozft: its bank switch overlaps the code MOVED moves, and ends before
    where it moves to."""
    bank, first, _last, shift = MOVED
    address, size, _offset = labels[BANK_SWITCH]
    end = address + size - 1
    if not first <= end < first + shift:
        raise BuildError(f"{BANK_SWITCH} now ends at ${end:04X}: lozft.SET_ITEM_ROUTINES and its shift "
                         f"no longer match it")


# --- ZORA's pieces -------------------------------------------------------------------------------------

def is_filler(run_bytes: bytes) -> bool:
    """make_release.py's is_filler: a run of few values or a counting sequence says nothing."""
    steps = {b - a for a, b in zip(run_bytes, run_bytes[1:], strict=False)}
    return len(set(run_bytes)) <= FILLER_VALUES or len(steps) == 1


def tile_offsets() -> set[int]:
    return {NES_HEADER_SIZE + offset + index for _name, offset, length in GRAPHICS_BLOCKS for index in range(length)}


class Copies:
    """Where runs of the game's own bytes are in the player's ROM in PRG0's layout (base_rom.Original's
    offsets), tiles left out."""

    def __init__(self, layout: bytes) -> None:
        self.layout = layout
        tiles = tile_offsets()
        self.places: dict[bytes, list[int]] = defaultdict(list)
        for offset in range(NES_HEADER_SIZE, len(layout) - MIN_COPY + 1):
            if not any(offset + index in tiles for index in range(MIN_COPY)):
                self.places[layout[offset:offset + MIN_COPY]].append(offset)
        self.tiles = tiles

    def longest(self, data: bytes, prefer: int) -> tuple[int, int]:
        """The longest run at data's start found in the game (source, length), the same place first."""
        best = (0, 0)
        for source in self.places.get(data[:MIN_COPY], ()):
            length = MIN_COPY
            while (length < len(data) and source + length < len(self.layout)
                   and source + length not in self.tiles and self.layout[source + length] == data[length]):
                length += 1
            if length > best[1] or (length == best[1] and source == prefer):
                best = (source, length)
        return best


def pieces(rom: bytes, written: set[int], copies: Copies,
           prg0_offset_of: Callable[[int], int | None]) -> list[tuple[int, Piece]]:
    """lozft's bytes as (offset, piece) writes: game runs as Original copies, the rest as literals.
    prg0_offset_of maps a lozft ROM offset to PRG0's file offset there (None in lozft's own banks)."""
    out: list[tuple[int, Piece]] = []
    for first, last in rom_space._runs(written):
        data = rom[first:last + 1]
        literal_start, index = 0, 0
        while index < len(data):
            source, length = (0, 0)
            if not is_filler(data[index:index + MIN_COPY]):
                place = prg0_offset_of(first + index)
                source, length = copies.longest(data[index:], place if place is not None else -1)
            if length >= MIN_COPY:
                if literal_start < index:
                    out.append((first + literal_start, data[literal_start:index]))
                out.append((first + index, Original(source, length)))
                index += length
                literal_start = index
            else:
                index += 1
        if literal_start < len(data):
            out.append((first + literal_start, data[literal_start:]))
    return out


def scan_hits(patch: list[tuple[int, Piece]], releases: list[bytes]) -> list[str]:
    """Literal runs the release scan would flag: SCAN_RUN bytes equal to either release, not filler."""
    hits = []
    for offset, piece in patch:
        if not isinstance(piece, bytes):
            continue
        for index in range(len(piece) - SCAN_RUN + 1):
            window = piece[index:index + SCAN_RUN]
            if not is_filler(window) and any(window in game for game in releases):
                hits.append(f"0x{offset + index:05X}: {window.hex()}")
    return hits


def zero_banks() -> set[int]:
    """lozft's banks 7-14, which its config fills with $00 (ZORA's with_lozft zeroes them itself)."""
    start = NES_HEADER_SIZE + FIXED_BANK * BANK_SIZE
    return set(range(start, start + (LOZFT_BANKS - GAME_BANKS) * BANK_SIZE))


@dataclass
class Build:
    revision: Revision
    rom: bytes
    patch: list[tuple[int, Piece]]
    written: set[int]
    layout: dict[str, Any]


def build(revision: Revision, source: Path, claims: list[Claim]) -> Build:
    game = release(revision)
    player = base_rom.player_rom_of(game)
    keep = reserved(claims)
    rom, debug = link(source, grown(game), SCRATCH / revision.value, defines(revision),
                      reservation_source(keep, revision))
    labels = symbols(debug)
    check_moved(labels)
    layout = music_layout(ftcfg(source), labels)
    modules = module_bytes(debug)
    ours = modules.pop(RESERVE_MODULE, set())
    lozft_bytes = set().union(*modules.values())
    clashes = sorted(lozft_bytes & ours)
    if clashes:
        listing = ", ".join(f"{lozft_place(a)}-{lozft_place(b).split('$')[1]} (0x{a:05X})"
                            for a, b in rom_space._runs(clashes))
        raise BuildError(f"{revision.value}: lozft's fixed code overlaps ZORA's bytes at {listing} "
                         "(move ZORA's, or lozft's with a build option)")
    zeros = zero_banks()
    written = {offset for offset in lozft_bytes if not (offset in zeros and rom[offset] == 0)}

    def prg0_offset_of(offset: int) -> int | None:
        bank = (offset - NES_HEADER_SIZE) // BANK_SIZE
        if FIXED_BANK <= bank < LOZFT_FIXED_BANK or offset < NES_HEADER_SIZE:
            return None
        game_offset = offset - (LOZFT_FIXED_BANK - FIXED_BANK) * BANK_SIZE if bank == LOZFT_FIXED_BANK else offset
        return game_offset if revision is Revision.PRG0 else prg0_offset(game_offset)

    patch = pieces(rom, written, Copies(player.layout), prg0_offset_of)
    hits = scan_hits(patch, [release(Revision.PRG0), release(Revision.PRG1)])
    if hits:
        raise BuildError(f"{revision.value}: literals the release scan would flag:\n  " + "\n  ".join(hits[:20]))
    return Build(revision, rom, patch, written, layout)


def check_round_trip(result: Build) -> None:
    """The pieces, written as with_lozft writes them on the release, give the build's own bytes."""
    player = base_rom.player_rom_of(release(result.revision))
    with base_rom.using_player_rom(player):
        for offset, piece in result.patch:
            data = base_rom.piece_bytes(piece)
            if data != result.rom[offset:offset + len(data)]:
                raise BuildError(f"{result.revision.value}: the piece at 0x{offset:05X} does not give lozft's bytes")


# --- the data file ---------------------------------------------------------------------------------------

def _piece_text(piece: Piece) -> str:
    if isinstance(piece, Original):
        return f"Original(0x{piece.source:05X}, {piece.length})"
    chunks = [piece[index:index + 32].hex() for index in range(0, len(piece), 32)]
    if len(chunks) == 1:
        return f'bytes.fromhex("{chunks[0]}")'
    inner = "\n".join(f'            "{chunk}"' for chunk in chunks)
    return f"bytes.fromhex(\n{inner}\n        )"


LAYOUT_DIGITS = {"song_table": 5, "module_addresses": 5, "bank_size": 4, "base": 4}


def _layout_text(layout: dict[str, Any]) -> str:
    lines = []
    for key, item in layout.items():
        if isinstance(item, dict):
            lines.append(f'    "{key}": {{')
            lines += [f'        "{name}": 0x{number:02X},' for name, number in item.items()]
            lines.append("    },")
        elif isinstance(item, tuple):
            lines.append(f'    "{key}": (' + ", ".join(f"0x{part:02X}" for part in item) + "),")
        else:
            lines.append(f'    "{key}": 0x{item:0{LAYOUT_DIGITS.get(key, 2)}X},')
    return "{\n" + "\n".join(lines) + "\n}"


def data_text(builds: list[Build]) -> str:
    header = f'''"""lozft's bytes on a randomized-music ROM, per release (docs/music.md "lozft from source").

Generated by `python3 scripts/lozft_build.py` from lozft {LOZFT_COMMIT[:7]}
({LOZFT_REPOSITORY.removesuffix(".git")}; MPL 2.0) with bhop {BHOP_COMMIT[:7]} (MIT-0), js65
{JS65_VERSION}; do not edit. Music engine: lozft by TheRealQuantam (MPL 2.0), using bhop by zeta0134
(MIT-0); its source is the commit above.

Each patch is a tuple of (file offset, piece) writes on the 256 KB ROM (the fixed bank in bank 15,
banks 7-14 zeroed first): lozft's own bytes, or an Original (source, length), the game's own code
that lozft moves, read from the player's ROM in PRG0's layout when it is written (never stored here,
never from its tiles).
"""
from typing import Any

from ..base_rom import Original, Piece

# Where LOZFT_COMMIT's source is (MPL 2.0; the release notes name it)
LOZFT_SOURCE = "{LOZFT_REPOSITORY}"
LOZFT_COMMIT = "{LOZFT_COMMIT}"
# Where the importer puts songs (lozft.ftcfg, checked against the link): file offsets of the song table
# and the module addresses; music banks first..end-1 of bank_size bytes, switched in at base; the
# driver's bank; the song count; each song name's number.
MUSIC_LAYOUT: dict[str, Any] = {{layout}}

PATCHES: dict[str, tuple[tuple[int, Piece], ...]] = {{
'''
    layouts = {repr(result.layout) for result in builds}
    if len(layouts) != 1:
        raise BuildError("PRG0's and PRG1's builds put the music tables in different places")
    header = header.replace("{layout}", _layout_text(builds[0].layout))
    body = []
    for result in builds:
        lines = [f'    "{result.revision.value}": (']
        lines += [f"        (0x{offset:05X}, {_piece_text(piece)})," for offset, piece in result.patch]
        lines.append("    ),")
        body.append("\n".join(lines))
    return header + "\n".join(body) + "\n}\n"


# --- the upstream check ------------------------------------------------------------------------------------

def upstream_check(source: Path) -> list[str]:
    """The source built as published (no defines but ROM_256KB, no reservations) onto PRG1, against the
    source's own lozft.bps applied to PRG1: the offsets that differ, with both bytes."""
    prg1 = release(Revision.PRG1)
    rom, _debug = link(source, grown(prg1), SCRATCH / "upstream", ["ROM_256KB"])
    expected = apply_bps((source / "lozft.bps").read_bytes(), prg1)
    return [f"0x{offset:05X}: {expected[offset]:02X} -> {rom[offset]:02X}"
            for offset in range(len(rom)) if rom[offset] != expected[offset]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="compare with the committed data")
    group.add_argument("--upstream", metavar="COMMIT", nargs="?", const=LOZFT_COMMIT,
                       help="build COMMIT (default the pinned one) as published and compare with its lozft.bps")
    args = parser.parse_args()
    if args.upstream:
        source = export_source(args.upstream, SCRATCH / f"source-{args.upstream[:7]}")
        differences = upstream_check(source)
        print(f"lozft {args.upstream[:7]} built as published: {len(differences)} byte(s) differ from its lozft.bps")
        for line in differences[:20]:
            print(f"  {line}")
        sys.exit(1 if differences else 0)
    source = export_source(LOZFT_COMMIT, SCRATCH / "source")
    claims = zora_claims()
    builds = []
    for revision in (Revision.PRG0, Revision.PRG1):
        result = build(revision, source, claims)
        check_round_trip(result)
        copied = sum(piece.length for _offset, piece in result.patch if isinstance(piece, Original))
        literal = sum(len(piece) for _offset, piece in result.patch if isinstance(piece, bytes))
        print(f"{revision.value}: {len(result.written):,} bytes of lozft's in {len(result.patch)} pieces, "
              f"{literal:,} literal, {copied:,} copied from the player's ROM")
        builds.append(result)
    text = data_text(builds)
    if args.check:
        same = DATA_FILE.exists() and DATA_FILE.read_text() == text
        print(f"{DATA_FILE.relative_to(REPO)}: {'up to date' if same else 'DIFFERS from the build'}")
        sys.exit(0 if same else 1)
    DATA_FILE.write_text(text)
    print(f"wrote {DATA_FILE.relative_to(REPO)} (sha256 {hashlib.sha256(text.encode()).hexdigest()[:12]})")


if __name__ == "__main__":
    main()
