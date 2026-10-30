"""lozft, Quantam's FamiTracker driver for The Legend of Zelda, on a finished ZORA ROM.

The patch (lozft.bps, made from PRG1) is a BPS patch of the original game, and its encoder may take
any byte from anywhere in the game it finds it (lozft of 2026-10-22 does, some 60 times), so it is
not applied to the finished ROM directly: that would copy ZORA's bytes, or PRG0's, where it expects
PRG1's. It is applied to the player's own ROM, unchanged, in PRG1's layout (vanilla_in_prg1_layout:
PRG0 with the code and data PRG1 moves at PRG1's offsets), which gives lozft's ROM as Quantam made
it. Where that differs from the game (or is in lozft's own banks 7-14), the byte is lozft's; every
other byte is the finished ROM's own, at the same place (source_place: banks 0-6 where they are,
the fixed bank moved from 7 to 15), ZORA's changes kept. A published lozft.bps encoded only with
same-place copies (ZeldaMusicRandomizer ed924c4's) gives the same as applying it directly. lozft's
bytes must match the pin (LOZFT_BYTES_SHA256, the same from either release), which a ROM with modified graphics
where the encoder took zeros from blank tiles does not. Two changes follow, 10 bytes of lozft's:

- PRG0 only: lozft's one PRG1-only site. It replaces PRG1's `LDA #$00 / STA Song` at bank 0 $9D42 with
  `JMP $8100` and returns from its glue with `JMP $9D45`; PRG0 has that code 4 bytes later
  (revision.PRG1_MOVES: -4 from 0x01BAF), so the jump goes to $9D46 and the return to $9D49, and
  $9D42-$9D45 get the ROM's own bytes back.
- lozft's glue calls the game's sound engine once a frame with `JSR DriveAudio` at bank 0 $828E;
  it calls the statistics screen's StatsTick instead, which ends by jumping to DriveAudio (lozft's
  new NMI code took over the game's `JSR DriveAudio` that StatsTick hooks without lozft). The ROM
  must hold the statistics screen's "music" choice (asm/fp-stats-01-music): its StatsTick is in
  bank 0 clear of lozft's song table. Its block stays in SRAM at $7F00-$7F3F, below lozft's
  driver's ($7F40-$7FFD; the driver's other variables are in the stack page, $0150-$01B9).
"""
import hashlib

from ..base_rom import PlayerRom, piece_bytes, player_rom_of, using_player_rom
from ..player_settings_data import SETTINGS
from ..revision import PRG1_MOVES, Revision, headered, identify_rom, move_of, prg1_offset
from ..sword_states import SET_ITEM_VALUE_STORE
from .importer import BANK_SIZE, HEADER
from .lozft_patch_data import PATCHES
from .pin import LOZFT_BYTES_SHA256

ROM_SIZE = HEADER + 8 * BANK_SIZE
LOZFT_ROM_SIZE = HEADER + 16 * BANK_SIZE
BPS_MAGIC = b"BPS1"
BPS_FOOTER = 12                      # source, target and patch CRC-32s
SOURCE_READ, TARGET_READ, SOURCE_COPY, TARGET_COPY = range(4)
SHARED_BANKS = 7                     # lozft's banks 0-6 are the game's, in the same place
FIXED_SOURCE_BANK, FIXED_TARGET_BANK = 7, 15


def _bank0(cpu: int) -> int:
    return HEADER + cpu - 0x8000


SONG_STOP = bytes.fromhex("a9008d0906")                  # LDA #$00 / STA Song
PRG1_SONG_STOP, PRG0_SONG_STOP = _bank0(0x9D42), _bank0(0x9D46)
LOZFT_SONG_STOP = bytes.fromhex("4c0081a900")            # JMP $8100 / LDA #$00 (lozft writes all but byte 1)
GLUE_RETURN = _bank0(0x811E)                             # JMP $9D45
SONG_STOP_RETURN = 3                                     # the return is the byte after the JMP
GLUE_DRIVE_AUDIO_CALL = _bank0(0x828E)
DRIVE_AUDIO = 0x9825
JSR, JMP = 0x20, 0x4C
STATS_TICK_HOOK = 0x1E571                                # IsrNmi's JSR (fp-stats-01's "tick" hook)
STATS_TICK_MUSIC_CHOICE = range(0xB000, 0xBF00)          # bank 0, where the "music" choice puts StatsTick


class LozftUnavailable(ValueError):
    """The ROM is not one lozft can go on."""


def _number(patch: bytes, offset: int) -> tuple[int, int]:
    """A BPS variable-length number at offset, and the offset after it."""
    value, shift = 0, 1
    while True:
        byte = patch[offset]
        offset += 1
        value += (byte & 0x7F) * shift
        if byte & 0x80:
            return value, offset
        shift <<= 7
        value += shift


def source_place(offset: int) -> int | None:
    """Where in the game's ROM a byte of lozft's ROM may come from: the same place in the header and
    banks 0-6, the fixed bank 7 for bank 15; None in lozft's own banks 7-14."""
    bank = (offset - HEADER) // BANK_SIZE
    if offset < HEADER or bank < SHARED_BANKS:
        return offset
    if bank == FIXED_TARGET_BANK:
        return offset - (FIXED_TARGET_BANK - FIXED_SOURCE_BANK) * BANK_SIZE
    return None


def vanilla_in_prg1_layout(base: bytes) -> bytes:
    """The player's ROM (a release, with or without its header) in PRG1's layout, where lozft's
    copies from elsewhere read: PRG1 as it is, PRG0 with the code and data PRG1 moves at PRG1's
    offsets (revision.PRG1_MOVES)."""
    rom = headered(base)
    if identify_rom(rom).revision is Revision.PRG1:
        return rom
    image = bytearray(rom)
    for move in PRG1_MOVES:
        image[move.start + move.shift:move.end + move.shift] = rom[move.start:move.end]
    return bytes(image)


def apply_bps(patch: bytes, source: bytes) -> bytearray:
    """A BPS1 patch applied (BpsFile.Apply; the source checksum is not checked)."""
    if patch[:4] != BPS_MAGIC:
        raise LozftUnavailable("the music patch is not a BPS patch")
    source_size, offset = _number(patch, len(BPS_MAGIC))
    target_size, offset = _number(patch, offset)
    metadata, offset = _number(patch, offset)
    offset += metadata
    if len(source) != source_size:
        raise LozftUnavailable(f"the music patch needs a {source_size}-byte ROM, not {len(source)}")
    target = bytearray(target_size)
    footer, out, source_at, target_at = len(patch) - BPS_FOOTER, 0, 0, 0
    while offset < footer:
        command, offset = _number(patch, offset)
        action, length = command & 3, (command >> 2) + 1
        if action == SOURCE_READ:
            target[out:out + length] = source[out:out + length]
        elif action == TARGET_READ:
            target[out:out + length] = patch[offset:offset + length]
            offset += length
        else:
            delta, offset = _number(patch, offset)
            delta = -(delta >> 1) if delta & 1 else delta >> 1
            if action == SOURCE_COPY:
                source_at += delta
                target[out:out + length] = source[source_at:source_at + length]
                source_at += length
            else:                                         # TARGET_COPY may overlap: byte by byte
                target_at += delta
                for index in range(length):
                    target[out + index] = target[target_at + index]
                target_at += length
        out += length
    return target


def lozft_bytes(patch: bytes, base: bytes) -> tuple[bytes, bytes]:
    """lozft's ROM made from the player's ROM `base` (PRG1's layout), and a mask of lozft's own
    bytes in it: 1 where it differs from the game at source_place or is in lozft's own banks."""
    vanilla = vanilla_in_prg1_layout(base)
    made = apply_bps(patch, vanilla)
    mask = bytearray(len(made))
    for offset, byte in enumerate(made):
        place = source_place(offset)
        mask[offset] = place is None or vanilla[place] != byte
    return bytes(made), bytes(mask)


def lozft_bytes_sha256(made: bytes, mask: bytes) -> str:
    """The SHA-256 of lozft's own bytes (the others zero)."""
    return hashlib.sha256(bytes(byte if own else 0 for byte, own in zip(made, mask, strict=True))).hexdigest()


def stats_tick(rom: bytes) -> int:
    """StatsTick's address in a ROM with the statistics screen's "music" choice."""
    if rom[STATS_TICK_HOOK] != JSR:
        raise LozftUnavailable("the ROM has no statistics screen tick")
    address = rom[STATS_TICK_HOOK + 1] | rom[STATS_TICK_HOOK + 2] << 8
    if address not in STATS_TICK_MUSIC_CHOICE:
        raise LozftUnavailable("the ROM's statistics screen has StatsTick in lozft's song table: randomized "
                               "music needs its music choice (asm/fp-stats-01-music)")
    return address


def with_lozft(rom: bytes, patch: bytes, base: bytes) -> bytearray:
    """The finished ROM (PRG0's or PRG1's layout) with lozft and its two changes; base is the
    player's ROM it was made from (a release, with or without its header)."""
    if len(rom) != ROM_SIZE:
        raise LozftUnavailable(f"randomized music needs a finished {ROM_SIZE}-byte ROM")
    tick = stats_tick(rom)
    prg0 = rom[PRG0_SONG_STOP:PRG0_SONG_STOP + len(SONG_STOP)] == SONG_STOP
    if not prg0 and rom[PRG1_SONG_STOP:PRG1_SONG_STOP + len(SONG_STOP)] != SONG_STOP:
        raise LozftUnavailable("the ROM's sound engine is neither PRG0's nor PRG1's")
    made, mask = lozft_bytes(patch, base)
    if lozft_bytes_sha256(made, mask) != LOZFT_BYTES_SHA256:
        raise LozftUnavailable("randomized music needs the original graphics where lozft takes bytes from the "
                               "game (blank tiles); this ROM's graphics are modified there")
    out = bytearray(made)
    for offset, own in enumerate(mask):
        if not own:
            place = source_place(offset)
            assert place is not None
            out[offset] = rom[place]
    if prg0:
        out[PRG1_SONG_STOP:PRG0_SONG_STOP] = rom[PRG1_SONG_STOP:PRG0_SONG_STOP]
        out[PRG0_SONG_STOP:PRG0_SONG_STOP + len(LOZFT_SONG_STOP)] = LOZFT_SONG_STOP
        back = 0x8000 - HEADER + PRG0_SONG_STOP + SONG_STOP_RETURN
        out[GLUE_RETURN:GLUE_RETURN + 3] = bytes([JMP, back & 0xFF, back >> 8])
    call = out[GLUE_DRIVE_AUDIO_CALL:GLUE_DRIVE_AUDIO_CALL + 3]
    if call != bytes([JSR, DRIVE_AUDIO & 0xFF, DRIVE_AUDIO >> 8]):
        raise LozftUnavailable("lozft's glue is not the pinned one")
    out[GLUE_DRIVE_AUDIO_CALL:GLUE_DRIVE_AUDIO_CALL + 3] = bytes([JSR, tick & 0xFF, tick >> 8])
    return out


LOZFT_BANKS = 16
MUSIC_BANKS = LOZFT_BANKS - 8                            # banks 7-14, zeroed before lozft's own bytes
FIXED_CPU_BASE = 0xC000
# ZORA's code at the fixed bank's $FFC0-$FFD2: fp-book-01's SetItemValueAndBookMap ($FFC0-$FFCA) and the
# bomb upgrade's store ($FFC8-$FFCA) and bomb-count tail ($FFCB-$FFD2; zora/rom/sword_states.py), all
# entered by one JMP at SetItemValue's store. lozft's bank switch runs from the game's $FFAC to $FFC2,
# so on a lozft ROM the code moves 3 bytes on, to $FFC3-$FFD5: z1rr-coop's reserve at $FFD4-$FFDB does
# not matter there, a co-op ROM never has custom music. Interim: the MMC3 layout's own placement
# replaces this (docs/reports/plan-mmc3-single-player.md section 2.3).
SET_ITEM_ROUTINES = range(0xFFC0, 0xFFD3)
SET_ITEM_ROUTINES_SHIFT = 3


def with_lozft_from_source(rom: bytes, base: bytes) -> bytearray:
    """The finished ROM (the player's own release's layout) with lozft built from its source
    (scripts/lozft_build.py, zora/rom/music/lozft_patch_data.py): grown to 256 KB, the fixed bank moved
    to bank 15, banks 7-14 zeroed, then lozft's writes for the player's release, the game's code it
    moves read from the player's ROM `base` (never its tiles). The ROM must hold the statistics
    screen's "music" choice, which becomes its "lozft2" one (with_lozft2_statistics): lozft2 replaces
    the NMI code where the music choice counts frames.

    ZORA's code at the fixed bank's $FFC0-$FFD2 moves to $FFC3-$FFD5 (moved_set_item_routines). Not
    used for players' ROMs yet (docs/reports/plan-mmc3-single-player.md)."""
    if len(rom) != ROM_SIZE:
        raise LozftUnavailable(f"randomized music needs a finished {ROM_SIZE}-byte ROM")
    stats_tick(rom)
    player = player_rom_of(base)
    rom = with_lozft2_statistics(rom, player)
    fixed = HEADER + FIXED_SOURCE_BANK * BANK_SIZE
    out = bytearray(rom[:fixed]) + bytearray(MUSIC_BANKS * BANK_SIZE) + bytearray(rom[fixed:fixed + BANK_SIZE])
    with using_player_rom(player):
        for offset, piece in PATCHES[player.revision.value]:
            data = piece_bytes(piece)
            out[offset:offset + len(data)] = data
    moved_set_item_routines(rom, out)
    return out


LOZFT2_STATISTICS = SETTINGS["statistics_screen"]["lozft2"]


def with_lozft2_statistics(rom: bytes, player: PlayerRom) -> bytes:
    """The ROM with the statistics screen's "lozft2" choice in place of its "music" one (both write
    every site of the setting): StatsTick runs from the end of the game's DriveAudio, which lozft2
    calls once a frame, instead of from IsrNmi's JSR DriveAudio, which lozft2 replaces
    (asm/fp-stats-01-lozft2). Its offsets are PRG0's; on PRG1 none is in code PRG1 moves but where
    revision.PRG1_MOVES says."""
    out = bytearray(rom)
    with using_player_rom(player):
        for offset, piece in LOZFT2_STATISTICS:
            data = piece_bytes(piece)
            at = offset
            if player.revision is Revision.PRG1:
                assert move_of(offset) is move_of(offset + len(data) - 1), "a piece across a PRG1 move"
                at = prg1_offset(offset)
            out[at:at + len(data)] = data
    return bytes(out)


def _fixed(bank: int, cpu: int) -> int:
    return HEADER + bank * BANK_SIZE + cpu - FIXED_CPU_BASE


def moved_set_item_routines(rom: bytes, out: bytearray) -> None:
    """SET_ITEM_ROUTINES moved SET_ITEM_ROUTINES_SHIFT bytes on in lozft's ROM `out`, and SetItemValue's
    JMP into them re-pointed; nothing when the store has no such JMP (neither Book is an Atlas nor the
    bomb upgrade). The code only branches within itself and stores to RAM, so it runs where it lands."""
    site = rom[SET_ITEM_VALUE_STORE:SET_ITEM_VALUE_STORE + 3]
    target = site[1] | site[2] << 8
    if site[0] != JMP or target not in SET_ITEM_ROUTINES:
        return
    source = _fixed(FIXED_SOURCE_BANK, SET_ITEM_ROUTINES.start)
    moved = _fixed(FIXED_TARGET_BANK, SET_ITEM_ROUTINES.start + SET_ITEM_ROUTINES_SHIFT)
    out[moved:moved + len(SET_ITEM_ROUTINES)] = rom[source:source + len(SET_ITEM_ROUTINES)]
    target += SET_ITEM_ROUTINES_SHIFT
    out[SET_ITEM_VALUE_STORE:SET_ITEM_VALUE_STORE + 3] = bytes([JMP, target & 0xFF, target >> 8])
