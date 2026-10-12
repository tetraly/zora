"""z1rr-coop's SRAM page, $7F00-$7FFF (docs/rom-map.md "Reserved for z1rr-coop"): its EverDrive patch
uses the whole page (freeze slots, staging, flags, its USB message buffer), so ZORA must write
nothing there. The one exception is the statistics screen's counters, while that player setting
is On (STATS_ALLOWED; by owner ruling the statistics screen and co-op are incompatible for now, and a
co-op ROM must have the Statistics screen Off).

Two checks:
  - statically, every patch ZORA can write (the series, ASNB, the 2.0 flag patches, the overworld
    Wizzrobe routine and every choice of every player setting) holds no write instruction whose
    absolute operand can reach the page; with the Statistics screen On, its operands lie in
    STATS_ALLOWED. Bytes a patch keeps or moves from the original game (Original pieces) are not
    ZORA's and are not scanned; writes through a zero-page pointer cannot be read statically and
    are the emulator check's;
  - in the emulator, a finished seed is booted, the page is filled with a sentinel pattern, and
    every frame of a played session (registering a file, play with sword stabs and bombs, the item
    screen, saving, a reset and Continue, and the win mode with Start) is checked for a change on
    the page outside STATS_ALLOWED (with the setting Off: anywhere). Each run is made twice, with
    complementary patterns, so any write shows in one of them.

The original game itself writes $A5 to $7FFF at every power-on and reset (InitializeGameOrMode,
`SaveRamEnd`; InitSaveRam clears $6530-$7FFF when that marker or $6001's is missing), so the
pattern keeps $A5 there and a write of $A5 to $7FFF is left to the static check."""
from collections.abc import Iterator
from functools import cache

import pytest

from tests.emulator import GAME_MODE, GAME_SUBMODE, OBJ_TIMER, Button, Emulator
from tests.test_coop_reserved import FINISHED_CASES
from tests.test_feature_patches import vanilla
from tests.test_stats_screen import IS_UPDATING_MODE, LAST_WIN_SUBMODE, STATS_BLOCK, STATS_SIZE, WIN_MODE
from tests.test_stats_screen_play import play_a_session
from zora.generate.pipeline import generate_rom
from zora.rom import asnb_patch_data, code_patch_data, flags2_patch_data, player_settings_data
from zora.rom.base_rom import BASE_ROM_PATH, Piece
from zora.rom.layout import OVERWORLD_WIZZROBE_PATCH
from zora.rom.player_settings import PlayerSettings

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

COOP_PAGE = range(0x7F00, 0x8000)
# The statistics screen's counters: the only bytes of the page ZORA may write, and only with the
# setting On. The one place to change when the counters move.
STATS_ALLOWED = range(STATS_BLOCK, STATS_BLOCK + STATS_SIZE)
STATS_SETTING, STATS_ON = "statistics_screen", "on"
SAVE_RAM_END, SAVE_RAM_END_MARKER = 0x7FFF, 0xA5      # PRG0's own write at power-on and reset

# --- the static scan ------------------------------------------------------------------------------

# 6502 instructions that write memory with an absolute operand (lo, hi), by opcode: STA, STX, STY,
# INC, DEC, ASL, LSR, ROL and ROR; the indexed ones may reach up to $FF past their operand.
ABSOLUTE_WRITES = frozenset({0x8D, 0x8E, 0x8C, 0xEE, 0xCE, 0x0E, 0x4E, 0x2E, 0x6E})
INDEXED_WRITES = frozenset({0x9D, 0x99, 0xFE, 0xDE, 0x1E, 0x5E, 0x3E, 0x7E})
INDEX_REACH = 0xFF


def patch_tables() -> Iterator[tuple[str, tuple[tuple[int, Piece], ...]]]:
    """Every patch ZORA can write, by name ("setting/choice" for a player setting's choice)."""
    for table in (code_patch_data.PATCHES, asnb_patch_data.PATCHES, flags2_patch_data.PATCHES):
        yield from table.items()
    yield "overworld wizzrobe", OVERWORLD_WIZZROBE_PATCH
    for setting, choices in player_settings_data.SETTINGS.items():
        for choice, writes in choices.items():
            yield f"{setting}/{choice}", writes


def page_writes(writes: tuple[tuple[int, Piece], ...]) -> list[tuple[int, int, int]]:
    """(file offset, opcode, operand) of each write instruction in the patch's own bytes whose
    operand, or for an indexed one any address up to $FF past it, falls on the co-op page."""
    found = []
    for offset, piece in writes:
        if not isinstance(piece, bytes):
            continue                                  # the original game's bytes, kept or moved
        for at in range(len(piece) - 2):
            opcode, operand = piece[at], piece[at + 1] | piece[at + 2] << 8
            reach = INDEX_REACH if opcode in INDEXED_WRITES else 0 if opcode in ABSOLUTE_WRITES else None
            if reach is not None and operand <= COOP_PAGE[-1] and operand + reach >= COOP_PAGE[0]:
                found.append((offset + at, opcode, operand))
    return found


def test_no_patch_writes_the_coop_page() -> None:
    """With the Statistics screen Off, and in every other patch of any configuration, no write
    instruction can reach $7F00-$7FFF."""
    found = {name: hits for name, writes in patch_tables()
             if name != f"{STATS_SETTING}/{STATS_ON}" and (hits := page_writes(writes))}
    assert found == {}


def test_the_statistics_screen_writes_only_its_counters() -> None:
    """With the Statistics screen On, every write operand on the page is in STATS_ALLOWED (and the
    scan finds its writes, so it reads the patch's code)."""
    hits = page_writes(player_settings_data.SETTINGS[STATS_SETTING][STATS_ON])
    assert hits
    assert [hit for hit in hits if hit[2] not in STATS_ALLOWED] == []


# --- the emulator run -----------------------------------------------------------------------------

SEED = 1
EMULATOR_CASES = {           # (flag case, Statistics screen on)
    "baseline, screen off": ("baseline", False),
    "baseline, screen on": ("baseline", True),
    "every owner flag on, screen off": ("every owner flag on", False),
}
PATTERN_STEP, PATTERN_START = 37, 0x5B
WIN_FRAMES = 300
NO_BUTTONS = Button(0)


def pattern(address: int, flipped: bool) -> int:
    """The sentinel at a page address: varied, and complemented in the second run; $A5 at $7FFF."""
    if address == SAVE_RAM_END:
        return SAVE_RAM_END_MARKER
    value = (address * PATTERN_STEP + PATTERN_START) & 0xFF
    return value ^ 0xFF if flipped else value


class PageWatch(Emulator):
    """An emulator that, once watching, checks the page after every frame it steps and records each
    address that changed outside the allowed range, with the first frame it did."""

    def __init__(self, rom: bytes, allowed: range) -> None:
        super().__init__(rom)
        self.allowed = allowed
        self.expected: dict[int, int] = {}
        self.changed: dict[int, int] = {}

    def watch(self, flipped: bool) -> None:
        self.expected = {address: pattern(address, flipped) for address in COOP_PAGE}
        for address, value in self.expected.items():
            self[address] = value

    def run(self, frames: int, buttons: Button = NO_BUTTONS) -> None:
        for _ in range(frames):
            super().run(1, buttons)
            for address, value in self.expected.items():
                if address not in self.allowed and address not in self.changed and self[address] != value:
                    self.changed[address] = self.frames


@cache
def finished(case: str, screen_on: bool) -> bytes:
    flag_string, zora_flag_string = FINISHED_CASES[case]
    return generate_rom(flag_string, SEED, vanilla(), PlayerSettings(statistics_screen=screen_on),
                        zora_flag_string=zora_flag_string).rom


def play_and_win(emu: PageWatch) -> None:
    """A new file registered and played (walks, sword stabs, bombs), the item screen, saved, reset
    and continued, then the win mode's last submode and Start."""
    emu.register_file()
    emu.start_game()
    play_a_session(emu)
    emu.run(30)
    emu.open_item_screen()
    emu.save_and_reload()
    emu.run(60)
    emu[GAME_MODE], emu[IS_UPDATING_MODE], emu[GAME_SUBMODE] = WIN_MODE, 1, LAST_WIN_SUBMODE
    emu.run_until(lambda: emu[OBJ_TIMER] == 0, limit=2000)
    emu.press(Button.START, after=WIN_FRAMES)


@pytest.mark.parametrize("flipped", [False, True])
@pytest.mark.parametrize("name", list(EMULATOR_CASES))
def test_a_played_session_leaves_the_coop_page_alone(name: str, flipped: bool) -> None:
    case, screen_on = EMULATOR_CASES[name]
    emu = PageWatch(finished(case, screen_on), STATS_ALLOWED if screen_on else range(0))
    emu.boot_to_file_select()                 # first boot: InitSaveRam, the stats block's first set-up
    emu.watch(flipped)
    play_and_win(emu)
    assert emu.changed == {}, {f"${address:04X}": frame for address, frame in emu.changed.items()}
