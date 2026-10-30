"""A FamiTracker module in Dn-FamiTracker's BIN export, as lozft's driver (bhop) reads it: parsed for
its internal addresses, relocated to the address it is placed at, and with its two square channels
swapped where a song's primary square channel is not the game's. FtRandoLib's FtmBinary, ported.

Layout: a header of five addresses (song list, instrument list, sample map, samples, grooves), a
flags byte and two speeds; the instrument list (each instrument: flags, a channel mask, and one
sequence address per set bit); the song list (each song: its frame list address, then frame count,
pattern length, speed, tempo, groove position, initial bank); each frame holds one pattern
address per channel. Every address is absolute, for the module's base address.
"""
from dataclasses import dataclass

HEADER_ADDRESSES = 5
SEQUENCES = 5                         # volume, arpeggio, pitch, hi-pitch, duty
SQUARE_1, SQUARE_2 = 0, 1             # the channels' order in a frame
PATTERN_LENGTH_OFFSET = 3             # in a song's entry: frame list (2 bytes), frame count, pattern length

# bhop's pattern bytecode (lozft's bhop.s advance_channel_row, bhop/commands.asm). A row is any number of
# commands, then a note byte (below $80: a note, a rest, a note off or a release), then the row's duration
# byte unless a global duration is set. A command is a quick volume ($F0-$FF) or quick instrument
# ($E0-$EF), with no operand, or an entry of the command table ($80-$B4), most with one operand byte.
NOTE_LIMIT = 0x80
QUICK_COMMANDS = 0xE0
COMMAND_TABLE_END = 0xB5
SET_DURATION, RESET_DURATION = 0x82, 0x83
HALT = 0x88                           # Cxx: the tempo becomes 0 and rows stop for good
NO_OPERAND_COMMANDS = frozenset({0x81, RESET_DURATION, 0x8A, 0x92})   # hold, reset duration, clear, reset pitch


def _word(data: bytes | bytearray, offset: int) -> int:
    return data[offset] | data[offset + 1] << 8


def _put_word(data: bytearray, offset: int, value: int) -> None:
    data[offset] = value & 0xFF
    data[offset + 1] = value >> 8 & 0xFF


@dataclass
class _Instrument:
    address: int
    sequences: list[int | None]       # one per SEQUENCES slot; None where the mask bit is clear


@dataclass
class _Song:
    address: int
    frame_list: int
    pattern_length: int
    frames: list[int]                 # each frame's address
    patterns: list[list[int]]         # each frame's pattern addresses, as parsed (one list per frame index)


class FtmModule:
    """One module's bytes and its parsed addresses, for a module built for `base`."""

    def __init__(self, data: bytes, base: int, channels: int) -> None:
        self.data = bytearray(data)
        self.base = base
        self.header = [_word(self.data, 2 * index) for index in range(HEADER_ADDRESSES)]
        song_list, instrument_list, sample_map = self.header[:3]
        self.instrument_list, self.song_list = instrument_list, song_list
        self.instruments: list[_Instrument] = []
        if instrument_list != sample_map:
            first = _word(self.data, instrument_list - base)
            for index in range((first - instrument_list) // 2):
                address = _word(self.data, instrument_list - base + 2 * index)
                self.instruments.append(self._instrument(address))
        self.songs: list[_Song] = []
        if song_list != instrument_list:
            first = _word(self.data, song_list - base)
            for index in range((first - song_list) // 2):
                address = _word(self.data, song_list - base + 2 * index)
                self.songs.append(self._song(address, channels))

    def _instrument(self, address: int) -> _Instrument:
        offset = address - self.base
        mask = self.data[offset + 1]
        sequences: list[int | None] = []
        cursor = offset + 2
        for slot in range(SEQUENCES):
            if mask >> slot & 1:
                sequences.append(_word(self.data, cursor))
                cursor += 2
            else:
                sequences.append(None)
        return _Instrument(address, sequences)

    def _song(self, address: int, channels: int) -> _Song:
        offset = address - self.base
        frame_list = _word(self.data, offset)
        frame_count = self.data[offset + 2]
        pattern_length = self.data[offset + PATTERN_LENGTH_OFFSET]
        frames = [_word(self.data, frame_list - self.base + 2 * index) for index in range(frame_count)]
        patterns = [[_word(self.data, frame - self.base + 2 * channel) for channel in range(channels)]
                    for frame in frames]
        return _Song(address, frame_list, pattern_length, frames, patterns)

    def halts(self, song_number: int) -> list[int]:
        """The offsets of the song's halts (Cxx) in its patterns. A halt stops the song instead of
        looping it, and lozft's bhop then leaves the room silent or holding notes until the song changes
        (ISUMatt's level 9, docs/reports/bug-isumatt-1221053620.md). A pattern whose bytes do not parse
        as bhop's bytecode raises ValueError."""
        song = self.songs[song_number]
        return [offset for pattern in sorted({pattern for patterns in song.patterns for pattern in patterns})
                for offset in self._pattern_halts(pattern, song.pattern_length)]

    def _pattern_halts(self, address: int, rows: int) -> list[int]:
        """Read one pattern's rows as bhop does, each frame starting without a global duration (bhop's
        cmd_eff_jump: "new frames expect to begin with global duration disabled"); the offset of each
        halt command."""
        offset, row, global_duration, halts = address - self.base, 0, None, []
        while row < rows:
            command = self.data[offset]
            offset += 1
            if command < NOTE_LIMIT:
                if global_duration is None:
                    duration = self.data[offset]
                    offset += 1
                else:
                    duration = global_duration
                row += 1 + duration
            elif command >= QUICK_COMMANDS:
                continue
            elif command >= COMMAND_TABLE_END:
                raise ValueError(f"pattern at ${address:04X}: command ${command:02X} is not bhop's")
            elif command == SET_DURATION:
                global_duration = self.data[offset]
                offset += 1
            elif command == RESET_DURATION:
                global_duration = None
            elif command not in NO_OPERAND_COMMANDS:
                if command == HALT:
                    halts.append(offset - 1)
                offset += 1
        return halts

    def swap_square_channels(self, song_number: int) -> None:
        """Swap the two square channels' pattern addresses in each of the song's frames, once per
        distinct frame address."""
        song = self.songs[song_number]
        done: set[int] = set()
        for frame, patterns in zip(song.frames, song.patterns, strict=True):
            if frame in done:
                continue
            done.add(frame)
            patterns[SQUARE_1], patterns[SQUARE_2] = patterns[SQUARE_2], patterns[SQUARE_1]
            offset = frame - self.base
            _put_word(self.data, offset, patterns[SQUARE_1])
            _put_word(self.data, offset + 2, patterns[SQUARE_2])

    def rebase(self, new_base: int) -> None:
        """Every internal address moved by new_base - base (FtmBinary.Rebase).

        Quirk (FtRandoLib): the frames are written back from the patterns as parsed per frame index,
        so where a song lists one frame address twice, the later copy (which swap_square_channels
        skipped) is what the frame holds afterwards: a repeated frame of a swapped song ends up
        unswapped. Kept, so the output matches Quantam's importer byte for byte."""
        delta = new_base - self.base
        for index, instrument in enumerate(self.instruments):
            cursor = instrument.address + 2 - self.base
            for slot, sequence in enumerate(instrument.sequences):
                if sequence is not None:
                    instrument.sequences[slot] = sequence + delta
                    _put_word(self.data, cursor, sequence + delta)
                    cursor += 2
            instrument.address += delta
            _put_word(self.data, self.instrument_list - self.base + 2 * index, instrument.address)
        for index, song in enumerate(self.songs):
            for frame_index, (frame, patterns) in enumerate(zip(song.frames, song.patterns, strict=True)):
                patterns[:] = [pattern + delta for pattern in patterns]
                for channel, pattern in enumerate(patterns):
                    _put_word(self.data, frame - self.base + 2 * channel, pattern)
                song.frames[frame_index] = frame + delta
            for frame_index, frame in enumerate(song.frames):
                _put_word(self.data, song.frame_list - self.base + 2 * frame_index, frame)
            song.frame_list += delta
            _put_word(self.data, song.address - self.base, song.frame_list)
            song.address += delta
            _put_word(self.data, self.song_list - self.base + 2 * index, song.address)
        self.header = [address + delta for address in self.header]
        for index, address in enumerate(self.header):
            _put_word(self.data, 2 * index, address)
        self.song_list += delta
        self.instrument_list += delta
        self.base = new_base
