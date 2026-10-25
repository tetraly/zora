"""Songs into a ROM that has lozft: the song table, the modules packed into the music banks.

lozft (ZeldaMusicRandomizer's patch) grows the ROM to 16 banks of 16 KB, the fixed bank moved to
the last. Its song table is in bank 0: SONG_TABLE has two bytes per song number (the bank, XORed with
$FF for a FamiTracker song, and the song's index in its module), MODULE_ADDRESSES one address per song
number (its module's). Banks 7-14 are music banks: each holds a copy of the driver, bank 7's first
$1800 bytes, and modules after it (MusicImporter's BankLayout "ft"). A song for each area: the
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

HEADER = 0x10
BANK_SIZE = 0x4000
BANK_BASE = 0x8000                   # music banks are switched in at $8000
SONG_TABLE = HEADER + 0x00           # bank 0 $8000
MODULE_ADDRESSES = HEADER + 0x80     # bank 0 $8080
SONG_NUMBERS = 0x40
MUSIC_BANKS = tuple(range(7, 15))
DRIVER_BANK = 7
DRIVER_SIZE = 0x1800                 # the driver at the start of each music bank
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
# The use an area draws from when the library has no song of its own use: the title screen's songs
# are those tagged Title, else (a library made for the Zelda importer, which has no such use) the
# overworld's.
FALLBACK_USE = {TITLE: OVERWORLD}


MUSIC_BANK_ROOM = len(MUSIC_BANKS) * (BANK_SIZE - DRIVER_SIZE)     # bytes of modules the banks hold


class RomFull(MusicError):
    """The chosen modules do not fit the music banks."""


@dataclass(frozen=True)
class Placed:
    song_number: int
    song: Song


def area_uses(area: str) -> tuple[str, ...]:
    """The uses a song can be tagged with to play in an area: its own, then its FALLBACK_USE."""
    return (area, FALLBACK_USE[area]) if area in FALLBACK_USE else (area,)


def area_candidates(songs: list[Song], area: str) -> list[Song]:
    """The songs an area draws from: those tagged for it, else those of its FALLBACK_USE."""
    candidates = [song for song in songs if area in song.uses]
    if not candidates and area in FALLBACK_USE:
        candidates = [song for song in songs if FALLBACK_USE[area] in song.uses]
    return candidates


def draw_songs(songs: list[Song], rng: Rng, distinct: bool, areas: tuple[str, ...],
               fixed: dict[int, Song] | None = None) -> list[Placed]:
    """A song for each song number of `areas`, from the area's candidates (area_candidates). A
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
        candidates = area_candidates(songs, area)
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


def check_modules(songs: list[Song]) -> None:
    """Each song's module relocated as the importer would place it (Z2R's TestSongs), so a module
    whose data the driver cannot use is refused before the draw, naming it."""
    by_module: dict[int, _ModuleInfo] = {}
    for song in songs:
        if song.module is not None:
            info = by_module.setdefault(id(song.module), _ModuleInfo(song.module.data, song.module.address, []))
            info.songs.append(song)
    for info in by_module.values():
        try:
            info.placed_data(BANK_BASE + DRIVER_SIZE)
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


def pack_songs(rom: bytearray, placed: list[Placed]) -> None:
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
    free_banks = deque(MUSIC_BANKS)
    free_ranges: deque[tuple[int, int, int]] = deque()
    left = sorted(infos.values(), key=lambda info: -info.size)     # stable, as LINQ's OrderBy
    kept_gaps = []
    while left and (free_ranges or free_banks):
        if not free_ranges:
            free_ranges.append((free_banks.popleft(), DRIVER_SIZE, BANK_SIZE))
        bank, start, end = free_ranges.popleft()
        room = end - start
        data = banks.setdefault(bank, bytearray(BANK_SIZE))
        index: int | None = 0
        while left and index is not None and index < len(left):
            index = _first_fitting(left, index, room)
            if index is None:
                break
            info = left.pop(index)
            room -= info.size
            info.bank, info.address = bank, BANK_BASE + start + room       # the end of the free room
            data[start + room:start + room + info.size] = info.placed_data(info.address)
        if room >= SMALLEST_KEPT_GAP:
            kept_gaps.append((bank, start, start + room))
    if left:
        raise RomFull(f"{len(left)} modules do not fit the music banks")
    free_ranges.extend(kept_gaps)
    _write_song_table(rom, placed, infos)
    for bank, data in banks.items():
        driver = HEADER + DRIVER_BANK * BANK_SIZE
        data[:DRIVER_SIZE] = rom[driver:driver + DRIVER_SIZE]
        rom[HEADER + bank * BANK_SIZE:HEADER + (bank + 1) * BANK_SIZE] = data


def _write_song_table(rom: bytearray, placed: list[Placed], infos: dict[int, _ModuleInfo]) -> None:
    original_table = bytes(rom[SONG_TABLE:SONG_TABLE + 2 * SONG_NUMBERS])
    original_addresses = bytes(rom[MODULE_ADDRESSES:MODULE_ADDRESSES + 2 * SONG_NUMBERS])
    for place in placed:
        entry = 2 * place.song_number
        module = place.song.module
        if module is None:
            source = 2 * place.song.number
            rom[SONG_TABLE + entry:SONG_TABLE + entry + 2] = original_table[source:source + 2]
            rom[MODULE_ADDRESSES + entry:MODULE_ADDRESSES + entry + 2] = original_addresses[source:source + 2]
            continue
        info = infos[id(module)]
        rom[SONG_TABLE + entry] = info.bank ^ FAMITRACKER_BANK_FLIP
        rom[SONG_TABLE + entry + 1] = place.song.number
        rom[MODULE_ADDRESSES + entry] = info.address & 0xFF
        rom[MODULE_ADDRESSES + entry + 1] = info.address >> 8
