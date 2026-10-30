"""Songs into a ROM that has lozft: the song table, the modules packed into the music banks.

lozft (ZeldaMusicRandomizer's patch) grows the ROM to 16 banks of 16 KB, the fixed bank moved to
the last. Its song table is in bank 0: SONG_TABLE has two bytes per song number (the bank, XORed
with $FF for a FamiTracker song, and the song's index in its module), MODULE_ADDRESSES one address
per song number (its module's). Where the modules go is the build's BankLayout (MusicImporter's
BankLayout "ft"): LOZFT_2026_10_22, the pinned lozft.bps, has music banks 7-14, each with a copy
of the driver, bank 7's first $1800 bytes, and modules after it; LOZFT2, lozft built from source,
has 8 KB banks $0F-$1D at $A000 and the driver in a bank of its own. A song for each area: the
overworld (song 0), the ending (4), level 9 (5) and one per level 1-8 (6, 11-17), lozft's own
song numbers (MusicImporter.UsageTrackIdcs), and the title screen (7), which ZORA adds: lozft's glue
plays the game's title request ($80) from song 7 (track 8: the request's highest bit, 5 + 3).

pack_songs is FtRandoLib's Importer.Import (ImportEngineModules and WritePrimarySongMap), ported
to give the same bytes for the same songs in the same song numbers; draw_songs is ZORA's own.
"""
from collections import deque
from dataclasses import dataclass

from ...generate.rng import Rng
from .ftm import FtmModule
from .library import DUNGEON, ENDING, LAST_DUNGEON, OVERWORLD, TITLE, LibraryError, MusicError, Song
from .lozft_patch_data import MUSIC_LAYOUT

HEADER = 0x10
BANK_SIZE = 0x4000
SONG_TABLE = HEADER + 0x00           # bank 0 $8000
MODULE_ADDRESSES = HEADER + 0x80     # bank 0 $8080
SONG_NUMBERS = 0x40
CHANNELS = 5                         # the 2A03's: two squares, triangle, noise, DPCM
GAME_PRIMARY_SQUARE = 1
FAMITRACKER_BANK_FLIP = 0xFF
SMALLEST_KEPT_GAP = 64               # ImportEngineModules' rngSizeThresh

# The song numbers each area uses, in MusicImporter's order (Overworld, Ending, LastDungeon,
# Dungeon), which is also the order pack_songs places modules in when sizes tie.
AREA_SONGS = {
    OVERWORLD: (0,),
    ENDING: (4,),
    LAST_DUNGEON: (5,),
    DUNGEON: (6, 11, 12, 13, 14, 15, 16, 17),
    TITLE: (7,),
}


@dataclass(frozen=True)
class BankLayout:
    """Where a lozft build keeps its modules (MusicImporter's BankSize, FreeBanks and BankLayout "ft";
    lozft's lozft.ftcfg): music banks of `bank_size` bytes, numbered in that size, switched in at
    `base`, each starting with a copy of the driver's first `driver_size` bytes from `driver_bank`
    (none when the driver has a bank of its own)."""
    bank_size: int
    banks: tuple[int, ...]
    base: int
    driver_bank: int
    driver_size: int
    song_table: int = SONG_TABLE                 # file offsets: two bytes per song number
    module_addresses: int = MODULE_ADDRESSES     # and one address per song number
    song_numbers: int = SONG_NUMBERS

    @property
    def room(self) -> int:
        """The bytes of modules the banks hold."""
        return len(self.banks) * (self.bank_size - self.driver_size)

    def offset(self, bank: int) -> int:
        return HEADER + bank * self.bank_size


# lozft of 2026-10-22 (the pinned lozft.bps): 16 KB banks 7-14 at $8000, each with the driver's $1800 bytes.
LOZFT_2026_10_22 = BankLayout(bank_size=0x4000, banks=tuple(range(7, 15)), base=0x8000, driver_bank=7,
                              driver_size=0x1800)
# lozft2, built from source: the driver has a bank of its own, and every number comes from its build
# (lozft.ftcfg and the link, scripts/lozft_build.py), so a change of lozft's layout only regenerates it.
LOZFT2 = BankLayout(bank_size=MUSIC_LAYOUT["bank_size"], banks=tuple(range(*MUSIC_LAYOUT["banks"])),
                    base=MUSIC_LAYOUT["base"], driver_bank=MUSIC_LAYOUT["driver_bank"], driver_size=0,
                    song_table=MUSIC_LAYOUT["song_table"], module_addresses=MUSIC_LAYOUT["module_addresses"],
                    song_numbers=MUSIC_LAYOUT["song_numbers"])
MUSIC_BANK_ROOM = LOZFT_2026_10_22.room


class RomFull(MusicError):
    """The chosen modules do not fit the music banks."""


@dataclass(frozen=True)
class Placed:
    song_number: int
    song: Song


def song_loops(song: Song) -> bool:
    """Whether a song plays on until its area's song changes, as every area's song does in the
    original game: no halt (Cxx) in its patterns. lozft's bhop stops a song for good on a halt and can
    leave a note held until the song changes (ISUMatt's level 9, docs/reports/bug-isumatt-1221053620.md);
    such a song is never drawn, and a playlist that names one is warned about (Quantam's advice,
    2026-10-30: tell the player, who probably picked it by mistake). The original game's songs loop."""
    if song.module is None:
        return True
    try:
        return not FtmModule(song.module.data, song.module.address, CHANNELS).halts(song.number)
    except ValueError:
        return True             # patterns that do not read as bhop's: not known to halt, as before the check


def draw_songs(songs: list[Song], rng: Rng, distinct: bool, areas: tuple[str, ...],
               fixed: dict[int, Song] | None = None) -> list[Placed]:
    """A song for each song number of `areas`, from the songs whose uses include the area. A
    shuffle of the area's candidates per area; with `distinct`, no song is used twice while unused
    candidates remain (so the overworld, level 9 and each level get their own track when the library
    has enough). An area with no candidate keeps the ROM's song. `fixed` (a playlist's songs, by
    song number) are placed as they are, in any area, and the draw avoids them too."""
    fixed = fixed or {}
    used: set[int] = {id(song) for song in fixed.values()}
    placed: list[Placed] = []
    for area, song_numbers in AREA_SONGS.items():
        placed.extend(Placed(number, fixed[number]) for number in song_numbers
                      if number in fixed and area not in areas)
        if area not in areas:
            continue
        candidates = [song for song in songs if area in song.uses]
        if not candidates:
            placed.extend(Placed(number, fixed[number]) for number in song_numbers if number in fixed)
            continue
        rng.shuffle(candidates)
        queue = deque(candidates)
        for song_number in song_numbers:
            if song_number in fixed:
                placed.append(Placed(song_number, fixed[song_number]))
                continue
            choice = next((song for song in queue if id(song) not in used), None) if distinct else None
            if choice is None:
                choice = queue[0]
            queue.remove(choice)
            queue.append(choice)            # a repeat, when one is needed, comes from the front again
            used.add(id(choice))
            placed.append(Placed(song_number, choice))
    return placed


@dataclass(eq=False)
class _ModuleInfo:
    """ImportedFtModuleInfo: a module, the songs placed from it, where it goes."""
    module_data: bytes
    module_base: int
    songs: list[Song]
    bank: int = -1
    address: int = -1

    @property
    def size(self) -> int:
        return len(self.module_data)

    def placed_data(self, address: int) -> bytes:
        module = FtmModule(self.module_data, self.module_base, CHANNELS)
        for song in self.songs:
            if song.primary_square_channel != GAME_PRIMARY_SQUARE:
                module.swap_square_channels(song.number)
        if address != self.module_base:
            module.rebase(address)
        return bytes(module.data)


def check_modules(songs: list[Song], layout: BankLayout = LOZFT_2026_10_22) -> None:
    """Each song's module relocated as the importer would place it (Z2R's TestSongs), so a module
    whose data the driver cannot use is refused before the draw, naming it."""
    by_module: dict[int, _ModuleInfo] = {}
    for song in songs:
        if song.module is not None:
            info = by_module.setdefault(id(song.module), _ModuleInfo(song.module.data, song.module.address, []))
            info.songs.append(song)
    for info in by_module.values():
        try:
            info.placed_data(layout.base + layout.driver_size)
        except (IndexError, ValueError, KeyError) as exc:
            raise LibraryError(f"{info.songs[0].title}: its module cannot be placed ({exc})") from exc


def modules_size(placed: list[Placed]) -> int:
    """The bytes of the placed songs' modules, each module once."""
    modules = {id(place.song.module): place.song.module for place in placed if place.song.module is not None}
    return sum(len(module.data) for module in modules.values())


def _first_fitting(infos: list[_ModuleInfo], start: int, room: int) -> int | None:
    """In infos (largest first), from start: the first whose size is room, else the first smaller
    (List.BinarySearch with ImportedModuleInfoSizeComparer, then the step back over equal sizes)."""
    for index in range(start, len(infos)):
        if infos[index].size <= room:
            return index
    return None


def pack_songs(rom: bytearray, placed: list[Placed], layout: BankLayout = LOZFT_2026_10_22) -> None:
    """Write the placed songs into a lozft ROM: their modules into the music banks, the song table
    and the module addresses. An original song (module None) takes the table entries the ROM has
    for its own song number."""
    infos: dict[int, _ModuleInfo] = {}
    for place in placed:
        module = place.song.module
        if module is None:
            continue
        info = infos.setdefault(id(module), _ModuleInfo(module.data, module.address, []))
        if place.song not in info.songs:
            info.songs.append(place.song)
    banks: dict[int, bytearray] = {}
    free_banks = deque(layout.banks)
    free_ranges: deque[tuple[int, int, int]] = deque()
    left = sorted(infos.values(), key=lambda info: -info.size)     # stable, as LINQ's OrderBy
    kept_gaps = []
    while left and (free_ranges or free_banks):
        if not free_ranges:
            free_ranges.append((free_banks.popleft(), layout.driver_size, layout.bank_size))
        bank, start, end = free_ranges.popleft()
        room = end - start
        data = banks.setdefault(bank, bytearray(layout.bank_size))
        index: int | None = 0
        while left and index is not None and index < len(left):
            index = _first_fitting(left, index, room)
            if index is None:
                break
            info = left.pop(index)
            room -= info.size
            info.bank, info.address = bank, layout.base + start + room     # the end of the free room
            data[start + room:start + room + info.size] = info.placed_data(info.address)
        if room >= SMALLEST_KEPT_GAP:
            kept_gaps.append((bank, start, start + room))
    if left:
        raise RomFull(f"{len(left)} modules do not fit the music banks")
    free_ranges.extend(kept_gaps)
    _write_song_table(rom, placed, infos, layout)
    for bank, data in banks.items():
        driver = layout.offset(layout.driver_bank)
        data[:layout.driver_size] = rom[driver:driver + layout.driver_size]
        rom[layout.offset(bank):layout.offset(bank) + layout.bank_size] = data


def _write_song_table(rom: bytearray, placed: list[Placed], infos: dict[int, _ModuleInfo],
                      layout: BankLayout) -> None:
    table, addresses = layout.song_table, layout.module_addresses
    original_table = bytes(rom[table:table + 2 * layout.song_numbers])
    original_addresses = bytes(rom[addresses:addresses + 2 * layout.song_numbers])
    for place in placed:
        entry = 2 * place.song_number
        module = place.song.module
        if module is None:
            source = 2 * place.song.number
            rom[table + entry:table + entry + 2] = original_table[source:source + 2]
            rom[addresses + entry:addresses + entry + 2] = original_addresses[source:source + 2]
            continue
        info = infos[id(module)]
        rom[table + entry] = info.bank ^ FAMITRACKER_BANK_FLIP
        rom[table + entry + 1] = place.song.number
        rom[addresses + entry] = info.address & 0xFF
        rom[addresses + entry + 1] = info.address >> 8
