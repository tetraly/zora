"""lozft, Quantam's FamiTracker driver for The Legend of Zelda, on a finished ZORA ROM.

lozft is built from its pinned source (scripts/lozft_build.py), and the build's writes for each release are
zora/rom/music/lozft_patch_data.py. The game's code it moves is read from the player's ROM, never its tiles, so
a ROM with modified graphics takes it as any other (docs/music.md).
"""
from ..base_rom import PlayerRom, piece_bytes, player_rom_of, using_player_rom
from ..player_settings_data import SETTINGS
from ..revision import Revision, move_of, prg1_offset
from ..sword_states import SET_ITEM_VALUE_STORE
from .importer import BANK_SIZE, HEADER
from .lozft_patch_data import PATCHES

ROM_SIZE = HEADER + 8 * BANK_SIZE
LOZFT_ROM_SIZE = HEADER + 16 * BANK_SIZE
FIXED_SOURCE_BANK, FIXED_TARGET_BANK = 7, 15
JSR, JMP = 0x20, 0x4C
STATS_TICK_HOOK = 0x1E571                                # IsrNmi's JSR (fp-stats-01's "tick" hook)
STATS_TICK_MUSIC_CHOICE = range(0xB000, 0xBF00)          # bank 0, where the "music" choice puts StatsTick


class LozftUnavailable(ValueError):
    """The ROM is not one lozft can go on."""


def stats_tick(rom: bytes) -> int:
    """StatsTick's address in a ROM with the statistics screen's "music" choice."""
    if rom[STATS_TICK_HOOK] != JSR:
        raise LozftUnavailable("the ROM has no statistics screen tick")
    address = rom[STATS_TICK_HOOK + 1] | rom[STATS_TICK_HOOK + 2] << 8
    if address not in STATS_TICK_MUSIC_CHOICE:
        raise LozftUnavailable("the ROM's statistics screen has StatsTick in lozft's song table: randomized "
                               "music needs its music choice (asm/fp-stats-01-music)")
    return address


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

    ZORA's code at the fixed bank's $FFC0-$FFD2 moves to $FFC3-$FFD5 (moved_set_item_routines)."""
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
