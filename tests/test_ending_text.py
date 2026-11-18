"""The ending's last screen (docs/reports/ending-text.md): FP-LOCK-02 replaces credits lines 12-14
(the second-quest announcement; ZORA's lines 12 and 13 read A STATISTICS SCREEN / WILL NOW APPEAR.
and line 14 keeps PRESS THE START BUTTON., owner 2026-11-13) and MUST keep line 15, PRG0's copyright line. ZORA 2.0 beta 1
pointed line 15 at $AC72, $100 below PRG0's record at $AD72: the game then drew another credits
record there (25 tiles from column 27, past the 32-tile row), the copyright line was gone, and the
overrun broke DrawCredits' transfer buffer, which wrote stray bytes into the nametables and the
digit and letter patterns in CHR RAM.

Fixed: the tests check the bytes of line 15's entry and record, and, in the emulator, the
copyright row of the last screen against PRG0's, and the tile patterns in CHR RAM against the
same ROM with only line 15's entry restored (ZORA's own graphics differ from PRG0's elsewhere in
CHR RAM; the overrun hit the digits and letters, $00-$13, and Link's sprites)."""
from functools import cache

import pytest

from tests.emulator import GAME_MODE, GAME_SUBMODE, Emulator
from tests.test_feature_patches import vanilla
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.serialize.features import stats_announcement_records
from zora.rom.text_encoding import BYTE_TO_CHAR

SEED = 1
# CreditsTextAddrsLo/Hi (bank 2): 23 low bytes, then 23 high bytes.
CREDITS_POINTERS_LO = 0xAC3E
CREDITS_POINTERS_HI = 0xAC55
COPYRIGHT_LINE = 15
BANK_2_FILE_BASE = 0x10 + 2 * 0x4000
SWITCHED_BANK_BASE = 0x8000
CREDITS_ROW_TILES = 32

# The ending (mode $13), entered at submode 1 (after the curtain, which waits for the music).
IS_UPDATING_MODE = 0x11
ENDING_MODE = 0x13
ENDING_FIRST_SUBMODE = 1
ENDING_FRAMES = 4000                  # the credits scroll to the last screen in about 3,000
COPYRIGHT_ROW_PIXELS = slice(160, 184)


def line_pointer(rom: bytes, line: int) -> int:
    return rom[CREDITS_POINTERS_LO + line] | rom[CREDITS_POINTERS_HI + line] << 8


def record(rom: bytes, pointer: int) -> bytes:
    """A credits record: its length, its first column, then its tiles."""
    start = BANK_2_FILE_BASE + pointer - SWITCHED_BANK_BASE
    return rom[start:start + 2 + rom[start]]


@cache
def zora_rom() -> bytes:
    """Consternation without level encoding, every ZORA flag off (the tester's flags; the bug
    does not depend on level encoding, ZORA flags, hints or the seed)."""
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, vanilla()).rom


def test_line_15_points_at_prg0s_copyright_record() -> None:
    original = vanilla()
    assert line_pointer(zora_rom(), COPYRIGHT_LINE) == line_pointer(original, COPYRIGHT_LINE)


def test_line_15_draws_prg0s_copyright_inside_the_row() -> None:
    rom, original = zora_rom(), vanilla()
    copyright_record = record(rom, line_pointer(rom, COPYRIGHT_LINE))
    assert copyright_record == record(original, line_pointer(original, COPYRIGHT_LINE))
    length, column = copyright_record[0], copyright_record[1]
    assert column + length <= CREDITS_ROW_TILES


@cache
def last_screen(rom: bytes) -> tuple[bytes, bytes]:
    """Run the ending to its last screen: (the frame's copyright rows as RGB bytes, CHR RAM)."""
    pytest.importorskip("cynes")
    emu = Emulator(rom)
    emu.new_game()
    emu.run(30)
    emu[GAME_MODE] = ENDING_MODE
    emu[GAME_SUBMODE] = ENDING_FIRST_SUBMODE
    emu[IS_UPDATING_MODE] = 0
    emu.run(ENDING_FRAMES)
    return emu.last_frame[COPYRIGHT_ROW_PIXELS].tobytes(), emu.pattern_tables()


def test_the_last_screen_shows_the_copyright_line_as_prg0_does() -> None:
    assert last_screen(zora_rom())[0] == last_screen(vanilla())[0]


def with_prg0s_line_15(rom: bytes) -> bytes:
    """`rom` with line 15's pointer entry set back to PRG0's."""
    out, original = bytearray(rom), vanilla()
    for table in (CREDITS_POINTERS_LO, CREDITS_POINTERS_HI):
        out[table + COPYRIGHT_LINE] = original[table + COPYRIGHT_LINE]
    return bytes(out)


def test_the_ending_leaves_the_tile_patterns_alone() -> None:
    assert last_screen(zora_rom())[1] == last_screen(with_prg0s_line_15(zora_rom()))[1]


# --- FP-LOCK-02's rebuild condition (spec export 2026-10-08, F10), as ZORA rewrites it -------------
# Lines 12 and 13 announce the statistics screen (owner, 2026-11-13); lines 14 and 15 keep PRG0's
# records (PRESS THE START BUTTON. and the copyright line).

ANNOUNCEMENT_LINES = {12: "A STATISTICS SCREEN", 13: "WILL NOW APPEAR."}
PRG0_LINES = (14, 15)
LINE_15_ENTRIES = (0x72, 0xAD)              # low, high: PRG0's copyright record at $AD72
CONDITION_SEEDS = (0, 1, 12345)


def condition_cases() -> dict[str, tuple[str, str]]:
    """Flag settings across what the credits code could depend on: CP-5, the MVP baseline (level
    encoding on, when this build has it), Randomize Magical Sword, every owner flag on, the ASNB
    preset."""
    from tests.test_coop_reserved import FINISHED_CASES
    from zora.flags.presets import ASNB_FLAGS, ASNB_ZORA_FLAGS, MVP_BASELINE
    from zora.rom import level_encoding
    cases = {"CP-5": (MVP_BASELINE_LEVEL_ENCODING_OFF, ""), "magical sword": (MVP_BASELINE_LEVEL_ENCODING_OFF, "1.D"),
             "every owner flag on": FINISHED_CASES["every owner flag on"], "ASNB": (ASNB_FLAGS, ASNB_ZORA_FLAGS)}
    if level_encoding.is_available():
        cases["Consternation (level encoding)"] = (MVP_BASELINE, "")
    return cases


CONDITION_CASES = condition_cases()


@pytest.mark.parametrize("seed", CONDITION_SEEDS)
@pytest.mark.parametrize("case", list(CONDITION_CASES))
def test_every_rom_meets_fp_lock_02s_rebuild_condition(case: str, seed: int) -> None:
    """Lines 12 and 13 each address a record with n >= 1 and c + n <= 32 holding the statistics
    screen's announcement, centered as PRG0 centers its closing lines; lines 14 and 15 are PRG0's
    entries (line 15's are $72 low and $AD high)."""
    flags, zora = CONDITION_CASES[case]
    rom, original = generate_rom(flags, seed, vanilla(), zora_flag_string=zora).rom, vanilla()
    for line, text in ANNOUNCEMENT_LINES.items():
        announcement = record(rom, line_pointer(rom, line))
        length, column, tiles = announcement[0], announcement[1], announcement[2:]
        assert length >= 1 and column + length <= CREDITS_ROW_TILES, (line, length, column)
        assert "".join(BYTE_TO_CHAR[tile] for tile in tiles) == text
        assert column == (CREDITS_ROW_TILES - length + 1) // 2, (line, column)
    assert [line_pointer(rom, line) for line in PRG0_LINES] == [line_pointer(original, line) for line in PRG0_LINES]
    assert (rom[CREDITS_POINTERS_LO + COPYRIGHT_LINE], rom[CREDITS_POINTERS_HI + COPYRIGHT_LINE]) == LINE_15_ENTRIES


def test_the_announcement_is_centered_as_prg0s_lines_are() -> None:
    """PRG0's closing lines are centered in the 32-tile row (an odd leftover puts the extra column on
    the left), and ZORA's two lines the same way, no wider than PRG0's widest."""
    original = vanilla()
    prg0_lines = [record(original, line_pointer(original, line)) for line in (12, 13, 14)]
    assert [line[1] for line in prg0_lines] == [(CREDITS_ROW_TILES - line[0] + 1) // 2 for line in prg0_lines]
    records = stats_announcement_records()
    assert ["".join(BYTE_TO_CHAR[tile] for tile in line[2:]) for line in records] == list(ANNOUNCEMENT_LINES.values())
    assert [line[1] for line in records] == [(CREDITS_ROW_TILES - line[0] + 1) // 2 for line in records]
    assert all(line[0] <= max(prg0[0] for prg0 in prg0_lines) for line in records)
