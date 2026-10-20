"""The statistics screen (FP-STATS-01, asm/fp-stats-01/; docs/player-settings-patches.md
"Statistics screen"), a player setting off by default for now (owner ruling, beta 3): the
tests that need the screen turn it on, and a default ROM carries none of its code.

In the emulator, on PRG0 with only the setting's bytes written (the patch builds on the series
but uses none of it, so it runs on the original game) and on a generated seed: the stats block in
SRAM ($7F00-$7F3F) is initialized at first boot, cleared when a new file is registered and kept
otherwise (resets, the title screen's formatting of empty slots); the clock runs at 601 frames
per 10 seconds in the counted modes and charges the current area; levels, key items, bombs and
sword stabs are stamped or counted as the doc says; the win mode freezes it; after the credits
Start shows the screen, whose nametable is the rows this module builds from the block, and Start
again leaves as PRG0 does. The labels are the hints' item names; the level word is the status
bar's. A scripted session measures the clock against the frames played.

The bytes: off writes exactly the ROM without the setting, on only the setting's own bytes
(tests/test_player_settings_wiring.py); they touch no z1rr-coop block (tests/test_coop_reserved.py)
and no other patch's byte (tests/test_progressive_patches.py, test_asnb_patches.py,
test_flags2_patches.py)."""
from collections.abc import Sequence
from dataclasses import fields, replace
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.emulator import (
    CUR_LEVEL,
    CUR_SAVE_SLOT,
    GAME_MODE,
    GAME_SUBMODE,
    INV_BOMBS,
    INV_TRIFORCE,
    ITEMS,
    NAME_LENGTH,
    NAMES,
    OBJ_TIMER,
    Button,
    Emulator,
    Mode,
)
from tests.revision_layout import written_in_prg0_layout
from tests.test_feature_patches import vanilla
from zora import archipelago
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, generate_world, plan
from zora.generate.steps.hint_text import UPGRADE_LINES, item_name
from zora.model.enums import Item
from zora.rom.base_rom import PRG1_ROM_PATH, verify_base_rom
from zora.rom.code_patches import SEED_DIGITS_LENGTH, STATS_SEED_DIGITS, seed_code_items, seed_digit_tiles
from zora.rom.layout import FP_LEVEL_DASH_TILE as DASH_TILE
from zora.rom.player_settings import (
    Music,
    PlayerSettings,
    apply_player_settings,
    level_label,
    music,
    statistics_screen,
)
from zora.rom.player_settings_data import DEFAULTS
from zora.rom.revision import Revision
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom.text_encoding import BYTE_TO_CHAR, CHAR_TO_BYTE

# The stats block (asm/fp-stats-01/bank_00.s).
STATS_BLOCK = 0x7F00
STATS_SIZE = 0x40
MAGIC, FLAGS, TOTAL, SUB_FRAME, TENTH_PHASE = 0x00, 0x01, 0x02, 0x04, 0x05
AREAS, LEVEL_STAMPS, ITEM_STAMPS, STABS, BOMBS, PREV_BOMBS, SCREEN_STATE = 0x06, 0x1A, 0x2C, 0x3A, 0x3C, 0x3E, 0x3F
STATS_MAGIC, FINISHED = 0xA5, 0x80
NTSC_FPS = 60.0988                   # frames a second the clock's 601-per-10 rule stands for

# RAM (src/Variables.inc).
IS_UPDATING_MODE = 0x11
CUR_PPU_MASK = 0xFE
DEATH_COUNTS = 0x630
HEART_VALUES = 0x66F
HEART_PARTIAL = 0x670
INV_ARROW, INV_LADDER, INV_RAFT, INV_RING, INV_BOOMERANG = 0x659, 0x663, 0x660, 0x662, 0x674
INV_BOW = 0x65A
BOW_STAMP = 6                       # the bow's index among the key items' stamps
VIDEO_ON = 0x1E
WIN_MODE, SAVE_MODE, LAST_WIN_SUBMODE = 0x13, 0x0D, 4

# The screen (asm/fp-stats-01/bank_02.s).
NAME_TABLE = 0x2000
ROWS, COLUMNS = 30, 32
HEADINGS_ROW, LIST_FIRST_ROW, LIST_ROWS = 9, 10, 17
LEVELS = 9
ATTRIBUTE_TABLE = NAME_TABLE + 0x3C0     # one byte per 4x4 tiles, a 2-bit palette per 2x2 quadrant
LABEL_LENGTH = 9
HIDDEN_Y = 0xF8
# The top (owner's layout, 2026-10-19): the seed number (rows 1-2: SEED and 10 digits, the rest
# under them), then on the left the file name (row 3) and the counters, two cells a row, each an
# icon over two columns, the small x (background tile $70, its pattern written by the screen) and
# the count left-aligned (3 columns on the left, 4 on the right); on the right the passive items
# (rows 1-2) and the B items in a blue box (rows 3-8, columns 17-29); the headings (row 9).
NAME_ROW = 3
SEED_DIGITS_COLUMN = 7
NO_SEED_NUMBER = 0xFF
SMALL_X_TILE = 0x70
SHORT_COUNT_COLUMNS, COUNT_COLUMNS, MAX_COUNT = 3, 4, 9999
DEATHS_ROW, HEARTS_ROW, PUSH_START_ROW = 5, 7, 27      # the stabs share the deaths' row, the bombs the hearts'
SMALL_X_COLUMNS = (4, 10)
BOX_ROWS, BOX_COLUMNS = range(3, 9), range(17, 30)
BOX_TOP, BOX_SIDE, BOX_BOTTOM = bytes([0x69] + [0x6A] * 11 + [0x6B]), bytes([0x6C] + [0x24] * 11 + [0x6C]), \
    bytes([0x6E] + [0x6A] * 11 + [0x6D])
BOX_PALETTE, HEADINGS_PALETTE = 2, 1
HEADINGS_COLUMNS = range(12, 30)
HEADINGS_CELL_ROWS = (8, 9)                # the headings' attribute cell, the box's bottom on row 8
# The bow joined the key items on 2026-10-17 (owner).
ITEM_LABELS = ("SWORD", "LADDER", "BRACELET", "RAFT", "RECORDER", "S.ARROWS", "BOW")
KEY_ITEMS = (Item.WOOD_SWORD, Item.LADDER, Item.POWER_BRACELET, Item.RAFT, Item.RECORDER, Item.SILVER_ARROWS,
             Item.BOW)


# --- ROMs -----------------------------------------------------------------------------------------

@cache
def prg0_with_stats() -> bytes:
    """PRG0 with only the setting's bytes (no series patch, no seed code)."""
    rom = bytearray(vanilla())
    statistics_screen(rom, True)
    return bytes(rom)


@cache
def seed_rom(level_word: str = "LEVEL") -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla(), PlayerSettings(level_word=level_word)).rom


ROMS = {"prg0": prg0_with_stats, "seed": seed_rom}


# --- the block ------------------------------------------------------------------------------------

def word(emu: Emulator, offset: int) -> int:
    return emu[STATS_BLOCK + offset] | emu[STATS_BLOCK + offset + 1] << 8


def put_word(emu: Emulator, offset: int, value: int) -> None:
    emu[STATS_BLOCK + offset] = value & 0xFF
    emu[STATS_BLOCK + offset + 1] = value >> 8


def block(emu: Emulator) -> bytes:
    return bytes(emu[STATS_BLOCK + i] for i in range(STATS_SIZE))


def cleared(prev_bombs: int) -> bytes:
    data = bytearray(STATS_SIZE)
    data[MAGIC], data[PREV_BOMBS] = STATS_MAGIC, prev_bombs
    return bytes(data)


@cache
def playing_state(name: str) -> bytes:
    emu = Emulator(ROMS[name]())
    emu.new_game()
    emu.run(10)
    return emu.save()


def playing(name: str) -> Emulator:
    emu = Emulator(ROMS[name]())
    emu.load(playing_state(name))
    return emu


@pytest.mark.parametrize("name", ROMS)
def test_first_boot_initializes_the_block(name: str) -> None:
    emu = Emulator(ROMS[name]())
    for i in range(STATS_SIZE):
        emu[STATS_BLOCK + i] = 0xFF
    emu.run(60)
    assert block(emu) == cleared(emu[INV_BOMBS])


@pytest.mark.parametrize("name", ROMS)
def test_register_clears_and_nothing_else_does(name: str) -> None:
    """A new file clears the block; a reset, the title screen (which formats the empty slots)
    and the file-select menu keep it."""
    emu = playing(name)
    emu.run(5 * 60)
    put_word(emu, STABS, 7)
    kept = block(emu)
    assert word(emu, TOTAL) >= 5
    emu.reset()
    emu.boot_to_file_select()
    assert block(emu)[:SUB_FRAME] == kept[:SUB_FRAME] and word(emu, STABS) == 7
    emu.register_file()
    assert block(emu) == cleared(emu[INV_BOMBS])
    assert emu[DEATH_COUNTS + 1] == 0


@pytest.mark.parametrize("name", ROMS)
def test_the_clock_charges_the_current_area(name: str) -> None:
    emu = playing(name)
    for offset in range(TOTAL, LEVEL_STAMPS):
        emu[STATS_BLOCK + offset] = 0
    emu[CUR_LEVEL] = 3
    emu.run(601)
    assert word(emu, TOTAL) == 10
    assert [word(emu, AREAS + 2 * area) for area in range(10)] == [0, 0, 0, 10, 0, 0, 0, 0, 0, 0]
    emu[CUR_LEVEL] = 0
    emu[GAME_MODE] = Mode.FILE_SELECT
    before = block(emu)
    emu.run(60)
    assert block(emu)[:LEVEL_STAMPS] == before[:LEVEL_STAMPS]


@pytest.mark.parametrize("name", ROMS)
def test_levels_items_and_bombs(name: str) -> None:
    emu = playing(name)
    emu[INV_TRIFORCE] = 0x04
    emu.run(1)
    level_3 = word(emu, LEVEL_STAMPS + 2 * 2)
    assert level_3 == max(word(emu, TOTAL), 1)
    emu.run(120)
    emu[INV_TRIFORCE] = 0x00
    emu.run(1)
    emu[INV_TRIFORCE] = 0x04
    emu.run(1)
    assert word(emu, LEVEL_STAMPS + 2 * 2) == level_3                     # never overwritten

    emu[INV_LADDER] = 1
    emu.run(1)
    assert word(emu, ITEM_STAMPS + 2 * 1) == max(word(emu, TOTAL), 1)
    emu[INV_ARROW] = 1                                                    # wooden arrows: no stamp
    emu.run(1)
    assert word(emu, ITEM_STAMPS + 2 * 5) == 0
    emu[INV_ARROW] = 2
    emu.run(1)
    assert word(emu, ITEM_STAMPS + 2 * 5) == max(word(emu, TOTAL), 1)
    assert word(emu, ITEM_STAMPS + 2 * BOW_STAMP) == 0
    emu[INV_BOW] = 1
    emu.run(1)
    assert word(emu, ITEM_STAMPS + 2 * BOW_STAMP) == max(word(emu, TOTAL), 1)

    emu[INV_BOMBS] = 5
    emu.run(1)
    emu[INV_BOMBS] = 3
    emu.run(1)
    assert word(emu, BOMBS) == 2
    emu[INV_BOMBS] = 8                                                    # bought
    emu.run(1)
    assert word(emu, BOMBS) == 2
    emu[GAME_MODE] = Mode.FILE_SELECT
    emu[INV_BOMBS] = 1
    emu.run(1)
    assert word(emu, BOMBS) == 2


@pytest.mark.parametrize("name", ROMS)
def test_sword_stabs(name: str) -> None:
    emu = playing(name)
    emu.run(8, Button.UP)                                                 # face a way first (FP-ENTR-01)
    emu[ITEMS] = 1
    emu.press(Button.A, after=30)
    assert word(emu, STABS) == 1
    emu.run(60, Button.A)                                                 # held: one more swing only
    assert word(emu, STABS) == 2
    emu.run(30)
    emu[ITEMS] = 0
    emu.press(Button.A, after=30)
    assert word(emu, STABS) == 2


@pytest.mark.parametrize("name", ROMS)
def test_the_win_mode_freezes_the_clock(name: str) -> None:
    emu = playing(name)
    emu.run(120)
    emu[GAME_MODE] = WIN_MODE
    emu.run(1)
    total = word(emu, TOTAL)
    assert word(emu, LEVEL_STAMPS + 2 * 8) == total and emu[STATS_BLOCK + FLAGS] & FINISHED
    emu[GAME_MODE] = Mode.PLAY
    emu.run(600)
    assert word(emu, TOTAL) == total


# --- the screen -----------------------------------------------------------------------------------

def time_text(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    return "9.59.59" if hours >= 10 else f"{hours}.{rest // 60:02d}.{rest % 60:02d}"


def counter_cells(left: int, right: int) -> bytes:
    """A row's two counter cells as the screen writes them: two blanks under each icon, the small x,
    the count left-aligned in 3 columns on the left and 4 on the right (more than 9999 shows 9999)."""
    return b"".join(bytes([CHAR_TO_BYTE[" "]] * 2 + [SMALL_X_TILE])
                    + bytes(CHAR_TO_BYTE[char] for char in f"{min(value, MAX_COUNT):<{columns}}")
                    for value, columns in ((left, SHORT_COUNT_COLUMNS), (right, COUNT_COLUMNS)))


def seed_digits_in(rom: bytes) -> bytes | None:
    """The seed number's digit tiles a PRG0-layout ROM carries (code_patches.STATS_SEED_DIGITS), or
    None without one."""
    digits = rom[STATS_SEED_DIGITS:STATS_SEED_DIGITS + SEED_DIGITS_LENGTH]
    return None if digits[0] == NO_SEED_NUMBER else digits


def expected_rows(data: bytes, name: bytes, level_record: bytes, deaths: int, hearts: int,
                  seed_digits: bytes | None = None) -> list[bytes]:
    """The 30 nametable rows the screen draws for a block: the seed number (`seed_digits`, the
    ROM's digit tiles; none, blank rows), the file name, the counters (deaths and stabs, heart
    containers and bombs) and the B items' box, the headings, the overworld, the
    stamped levels and items in stamp order, the levels entered and not completed, and PUSH START
    BUTTON. A level's label is the status bar's record (its tiles but the number) and the level's
    number."""
    def at(offset: int) -> int:
        return data[offset] | data[offset + 1] << 8

    def tiles(text: str) -> bytes:
        return bytes(CHAR_TO_BYTE[char] for char in text)

    def level_tiles(level: int) -> bytes:
        count = level_record[LEVEL_RECORD_COUNT]
        word_tiles = level_record[LEVEL_RECORD_TILES:LEVEL_RECORD_TILES + count - 1]
        return (word_tiles + bytes([level])).ljust(LABEL_LENGTH, tiles(" "))

    def list_row(label: bytes, time_in: int | None, stamp: int) -> bytes:
        time_in_text = time_text(time_in) if time_in is not None else " " * 7
        completion = time_text(stamp) if stamp else " " * 7
        return tiles("  ") + label + tiles(f"  {time_in_text}   {completion}  ")

    blank = tiles(" " * COLUMNS)

    def boxed(left: bytes, box_row: bytes) -> bytes:
        return left.ljust(BOX_COLUMNS.start, tiles(" ")) + box_row + tiles(" " * (COLUMNS - BOX_COLUMNS.stop))

    if seed_digits is None:
        seed_rows = [blank, blank]
    else:
        per_row = SEED_DIGITS_LENGTH // 2
        seed_rows = [(tiles("  SEED ") + seed_digits[:per_row]).ljust(COLUMNS, tiles(" ")),
                     (tiles(" " * SEED_DIGITS_COLUMN) + seed_digits[per_row:]).ljust(COLUMNS, tiles(" "))]
    rows = [blank, *seed_rows, boxed(tiles("  ") + name, BOX_TOP), boxed(b"", BOX_SIDE),
            boxed(tiles("  ") + counter_cells(deaths, at(STABS)), BOX_SIDE), boxed(b"", BOX_SIDE),
            boxed(tiles("  ") + counter_cells(hearts, at(BOMBS)), BOX_SIDE), boxed(b"", BOX_BOTTOM),
            tiles(" " * 13 + "TIME IN   CLEARED" + " " * 2),
            list_row(tiles("OVERWORLD"), at(AREAS), 0)]
    stamps = [(at(LEVEL_STAMPS + 2 * index), index) for index in range(9 + len(ITEM_LABELS))]
    for stamp, index in sorted(entry for entry in stamps if entry[0]):
        if index < 9:
            rows.append(list_row(level_tiles(index + 1), at(AREAS + 2 * (index + 1)), stamp))
        else:
            rows.append(list_row(tiles(ITEM_LABELS[index - 9].ljust(LABEL_LENGTH)), None, stamp))
    rows += [list_row(level_tiles(index + 1), at(AREAS + 2 * (index + 1)), 0)
             for index in range(9) if not stamps[index][0] and at(AREAS + 2 * (index + 1))]
    rows += [blank] * (PUSH_START_ROW - len(rows))
    rows += [tiles(" " * 7 + "PUSH START BUTTON" + " " * 8), blank, blank]
    return rows


# The status bar's level label record in RAM (LevelNumberTransferBuf): PPU address, count, tiles.
LEVEL_RECORD_RAM = 0x681C
LEVEL_RECORD_SIZE = 11
LEVEL_RECORD_COUNT, LEVEL_RECORD_TILES = 2, 3


@cache
def ending_state(name: str, level_word: str = "LEVEL", credits: bool = True) -> bytes:
    """The win mode's last submode (after the credits) with its wait over, entered from play:
    through the whole win sequence, or (credits False) straight into the last submode."""
    emu = Emulator(seed_rom(level_word) if name == "seed" else ROMS[name]())
    emu.new_game()
    emu.run(10)
    emu[GAME_MODE] = WIN_MODE
    emu[IS_UPDATING_MODE] = 1
    emu[GAME_SUBMODE] = 0 if credits else LAST_WIN_SUBMODE
    emu.run_until(lambda: emu[GAME_SUBMODE] == LAST_WIN_SUBMODE, limit=4000)
    emu.run_until(lambda: emu[OBJ_TIMER] == 0, limit=2000)
    emu.run(5)
    return emu.save()


def prepared_block() -> bytes:
    """A finished run: levels 1, 3 and 9 completed, level 5 entered, five key items, counters."""
    data = bytearray(STATS_SIZE)
    data[MAGIC], data[FLAGS] = STATS_MAGIC, FINISHED

    def put(offset: int, value: int) -> None:
        data[offset:offset + 2] = value.to_bytes(2, "little")

    put(TOTAL, 9000)
    for area, seconds in ((0, 3000), (1, 700), (3, 900), (5, 65), (9, 1500)):
        put(AREAS + 2 * area, seconds)
    for level, stamp in ((1, 1200), (3, 2400), (9, 9000)):
        put(LEVEL_STAMPS + 2 * (level - 1), stamp)
    for item, stamp in ((0, 90), (1, 2400), (3, 3100), (5, 40000), (BOW_STAMP, 3000)):
        put(ITEM_STAMPS + 2 * item, stamp)                                # sword, ladder, raft, silver, bow
    put(STABS, 1234)
    put(BOMBS, 56)
    return bytes(data)


def show_screen(name: str, level_word: str = "LEVEL", credits: bool = True) -> Emulator:
    emu = Emulator(seed_rom(level_word) if name == "seed" else ROMS[name]())
    emu.load(ending_state(name, level_word, credits))
    return shown_with_the_prepared_run(emu)


def shown_with_the_prepared_run(emu: Emulator) -> Emulator:
    """From the last win submode with its wait over: the prepared run's block and inventory, then
    Start, which shows the screen."""
    for i, value in enumerate(prepared_block()):
        emu[STATS_BLOCK + i] = value
    for address, value in ((ITEMS, 2), (INV_LADDER, 1), (INV_RAFT, 1), (INV_ARROW, 2), (INV_RING, 2),
                           (INV_BOOMERANG, 1), (INV_BOMBS, 4), (HEART_VALUES, 0xC9)):
        emu[address] = value
    emu[DEATH_COUNTS + emu[CUR_SAVE_SLOT]] = 3
    emu.press(Button.START, after=6)
    return emu


def nametable_rows(emu: Emulator) -> list[bytes]:
    table = emu.nametable(NAME_TABLE, ROWS * COLUMNS)
    return [table[row * COLUMNS:(row + 1) * COLUMNS] for row in range(ROWS)]


def palette_at(emu: Emulator, row: int, column: int) -> int:
    """The background palette of the tile at (row, column), from the attribute table."""
    attributes = emu.nametable(ATTRIBUTE_TABLE + row // 4 * 8 + column // 4, 1)[0]
    return attributes >> ((row % 4) // 2 * 4 + (column % 4) // 2 * 2) & 0x03


@pytest.mark.parametrize("name", ROMS)
def test_start_after_the_credits_shows_the_screen_and_start_leaves(name: str) -> None:
    emu = show_screen(name)
    assert emu[CUR_PPU_MASK] == VIDEO_ON and emu[STATS_BLOCK + SCREEN_STATE] == 1 and emu.mode == WIN_MODE
    slot = emu[CUR_SAVE_SLOT]
    file_name = bytes(emu[NAMES + slot * NAME_LENGTH + i] for i in range(NAME_LENGTH))
    record = bytes(emu[LEVEL_RECORD_RAM + i] for i in range(LEVEL_RECORD_SIZE))
    rom = seed_rom() if name == "seed" else ROMS[name]()
    assert nametable_rows(emu) == expected_rows(prepared_block(), file_name, record, deaths=3, hearts=13,
                                                seed_digits=seed_digits_in(rom))
    oam = emu.sprites()
    shown = [oam[i:i + 4] for i in range(0, len(oam), 4) if oam[i] != HIDDEN_Y]
    assert len(shown) >= len(FIXED_COUNTER_ICONS) + 1 + 6       # the counters' icons, the six other items held
    emu.run(30)
    assert emu.mode == WIN_MODE                                           # it waits
    emu.press(Button.START, after=1)
    assert emu.mode == SAVE_MODE and emu[STATS_BLOCK + SCREEN_STATE] == 0


# The audio driver's RAM (zelda1-disassembly Variables.inc): a request is read at the next NMI.
EFFECT_REQUEST, EFFECT, SONG = 0x603, 0x606, 0x609
SWORD_EFFECT = 0x01
ENDING_SONG, OVERWORLD_SONG = 0x10, 0x01
QUIET_FRAMES = 120
SAVE_FRAMES = 900                   # the save mode's run to the file-select screen


def assert_an_effect_plays(emu: Emulator) -> None:
    emu[EFFECT_REQUEST] = SWORD_EFFECT
    emu.run(1)
    assert emu[EFFECT] == SWORD_EFFECT


@cache
def music_rom(name: str, choice: Music) -> bytes:
    """A ROM of ROMS with the music setting's choice written (Music.ON is ROMS' own)."""
    if name == "seed":
        return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla(), PlayerSettings(music=choice)).rom
    rom = bytearray(ROMS[name]())
    music(rom, choice)
    return bytes(rom)


@cache
def music_ending_state(name: str, choice: Music) -> bytes:
    """ending_state's run (through the whole win sequence) on music_rom."""
    emu = Emulator(music_rom(name, choice))
    emu.new_game()
    emu.run(10)
    emu[GAME_MODE] = WIN_MODE
    emu[IS_UPDATING_MODE] = 1
    emu[GAME_SUBMODE] = 0
    emu.run_until(lambda: emu[GAME_SUBMODE] == LAST_WIN_SUBMODE, limit=4000)
    emu.run_until(lambda: emu[OBJ_TIMER] == 0, limit=2000)
    emu.run(5)
    return emu.save()


@pytest.mark.parametrize("choice", list(Music), ids=lambda choice: f"music-{choice.value}")
@pytest.mark.parametrize("name", ROMS)
def test_the_music_setting_decides_the_screens_song(name: str, choice: Music) -> None:
    """The ending's song plays until Start shows the screen. With music on it plays on there (as
    before beta 6); with music off ("Turn music off") the screen stops it for as long as it is
    shown (owner decision, 2026-10-19). Effects still play either way. After Start, the save mode
    and the file-select screen, the file starts with the overworld song (none with music off)
    and effects play."""
    emu = Emulator(music_rom(name, choice))
    emu.load(music_ending_state(name, choice))
    assert emu[SONG] == ENDING_SONG
    emu.press(Button.START, after=6)
    assert emu[STATS_BLOCK + SCREEN_STATE] == 1
    for _ in range(QUIET_FRAMES):
        emu.run(1)
        assert emu[SONG] == (ENDING_SONG if choice is Music.ON else 0)
    assert_an_effect_plays(emu)
    emu.press(Button.START, after=1)
    assert emu.mode == SAVE_MODE
    emu.run_until(lambda: emu.mode == Mode.FILE_SELECT, limit=SAVE_FRAMES)
    emu.run(20)
    emu.start_game()
    emu.run(QUIET_FRAMES)
    assert emu[SONG] == (OVERWORLD_SONG if choice is Music.ON else 0)
    assert_an_effect_plays(emu)


# A short label (up to 7 tiles) is PRG0's record from power-on; a long one is filled in at a level
# load (test_the_screen_takes_a_long_level_word).
@pytest.mark.parametrize("level_word", ["TOWER", "DEN"])
def test_the_screen_takes_the_level_word(level_word: str) -> None:
    """The level rows read as the status bar does: TOWER-1, DEN-1 (the status bar's dash)."""
    emu = show_screen("seed", level_word, credits=False)
    label = nametable_rows(emu)[LIST_FIRST_ROW + 2][2:2 + LABEL_LENGTH]       # level 1, after the sword
    expected = level_label(level_word)
    tiles = bytes(DASH_TILE if char == "-" else CHAR_TO_BYTE[char] for char in expected)
    assert label == tiles.ljust(LABEL_LENGTH, bytes([CHAR_TO_BYTE[" "]]))


@pytest.mark.parametrize("level_word", ["CASTLE", "DUNGEON"])
def test_the_screen_takes_a_long_level_word(level_word: str) -> None:
    """FP-LEVEL-02's 8-tile label (asm/fp-level-02/): its routine copies the label record over
    PRG0's RAM record at each level load, which the screen reads, so after level 1 the screen's
    level rows show the word as the status bar does (CASTLE-1, DUNGEON1)."""
    emu = Emulator(apply_player_settings(vanilla(), PlayerSettings(level_word=level_word)))
    emu.new_game()
    emu.walk_into_level_1()
    emu[GAME_MODE] = WIN_MODE
    emu[IS_UPDATING_MODE] = 1
    emu[GAME_SUBMODE] = LAST_WIN_SUBMODE
    emu.run_until(lambda: emu[OBJ_TIMER] == 0, limit=2000)
    emu.run(5)
    shown_with_the_prepared_run(emu)
    assert emu[STATS_BLOCK + SCREEN_STATE] == 1
    label = nametable_rows(emu)[LIST_FIRST_ROW + 2][2:2 + LABEL_LENGTH]       # level 1, after the sword
    tiles = bytes(DASH_TILE if char == "-" else CHAR_TO_BYTE[char] for char in level_label(level_word))
    assert len(tiles) == 8 and label == tiles.ljust(LABEL_LENGTH, bytes([CHAR_TO_BYTE[" "]]))


# --- the top: seed number, counters, inventory -----------------------------------------------------

# Every item slot the screen draws, held (the sword, bombs, arrows, bow, candle, recorder, food,
# potion, rod, raft, book, ring, ladder, magic key, bracelet, letter, both boomerangs): the most
# sprites the screen draws.
FULL_INVENTORY = {0x00: 2, 0x01: 4, 0x02: 2, 0x03: 1, 0x04: 2, 0x05: 1, 0x06: 1, 0x07: 2, 0x08: 1, 0x09: 1,
                  0x0A: 1, 0x0B: 2, 0x0C: 1, 0x0D: 1, 0x0E: 1, 0x0F: 1, 0x1D: 1, 0x1E: 1}
ITEM_SLOTS = 0x21
# asm/fp-stats-01/bank_02.s (sprite Y is the row's top minus 1): the passive row (rows 1-2), then the
# B items' rows in the box, which the counters' rows share (rows 4-5, 6-7).
PASSIVE_ROW_Y, UPPER_ROW_Y, LOWER_ROW_Y = 1 * 8 - 1, 4 * 8 - 1, 6 * 8 - 1
SPRITE_ROWS_Y = (PASSIVE_ROW_Y, UPPER_ROW_Y, LOWER_ROW_Y)
SPRITE_HEIGHT = 16
MAX_SPRITES_ON_A_LINE = 8
LONGEST_SEED = 2 ** 64 - 1                  # 20 digits (pipeline.SEED_LIMIT)


@cache
def code_rom(revision: Revision) -> bytes:
    """A generated seed (seed 1) on this revision: the screen with a seed number."""
    if revision is Revision.PRG1:
        if not PRG1_ROM_PATH.exists():
            pytest.skip("needs the PRG1 ROM")
        base = PRG1_ROM_PATH.read_bytes()
    else:
        base = verify_base_rom().read_bytes()
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base).rom


@cache
def code_ending_state(revision: Revision) -> bytes:
    """The win mode's last submode, its wait over, on this revision's seed (as ending_state)."""
    emu = Emulator(code_rom(revision))
    emu.new_game()
    emu.run(10)
    emu[GAME_MODE] = WIN_MODE
    emu[IS_UPDATING_MODE] = 1
    emu[GAME_SUBMODE] = LAST_WIN_SUBMODE
    emu.run_until(lambda: emu[OBJ_TIMER] == 0, limit=2000)
    emu.run(5)
    return emu.save()


def code_screen(revision: Revision, inventory: dict[int, int], full_list: bool = False,
                counts: dict[int, int] | None = None, seed: int | None = None) -> Emulator:
    """The screen on this revision's seed with only the items in `inventory` held; with
    `full_list`, every area entered and every level and key item stamped (the bow last), so the
    list fills all its rows; `counts` sets the stats block's words (STABS, BOMBS) and `seed` the
    seed number the ROM shows."""
    rom = code_rom(revision)
    if seed is not None:
        rom = written_in_prg0_layout(rom, lambda image: image.__setitem__(
            slice(STATS_SEED_DIGITS, STATS_SEED_DIGITS + SEED_DIGITS_LENGTH), seed_digit_tiles(seed)))
    emu = Emulator(rom)
    emu.load(code_ending_state(revision))
    for slot in range(ITEM_SLOTS):
        emu[ITEMS + slot] = inventory.get(slot, 0)
    if full_list:
        for area in range(1 + LEVELS):
            put_word(emu, AREAS + 2 * area, 60 + area)
        for index in range(LEVELS + len(ITEM_LABELS)):
            put_word(emu, LEVEL_STAMPS + 2 * index, 100 + index)
    for offset, value in (counts or {}).items():
        put_word(emu, offset, value)
    emu.press(Button.START, after=6)
    return emu


def shown_sprites(emu: Emulator) -> list[tuple[int, ...]]:
    oam = emu.sprites()
    return [tuple(oam[i:i + 4]) for i in range(0, len(oam), 4) if oam[i] != HIDDEN_Y]


def most_sprites_on_a_line(sprites: Sequence[tuple[int, ...]]) -> int:
    return max(sum(y < line <= y + SPRITE_HEIGHT for y, *_ in sprites) for line in range(256))


@pytest.mark.parametrize("revision", [Revision.PRG0, Revision.PRG1], ids=["prg0", "prg1"])
def test_a_full_inventory_keeps_every_sprite_in_its_row(revision: Revision) -> None:
    """Bug (beta 5, both releases): with a full inventory, DrawStatsItem's sprite index ran past
    SpriteOffsets' end and rewrote earlier sprites' fields (an icon drawn mid-screen, the bomb over
    the bow). With every item held, every sprite is on the passive row, a B row or a counter row,
    no two share a place, and no scanline has more than 8 sprites (the 9th would not be drawn)."""
    sprites = shown_sprites(code_screen(revision, FULL_INVENTORY))
    assert all(y in SPRITE_ROWS_Y for y, *_ in sprites)
    assert len({(y, x) for y, _, _, x in sprites}) == len(sprites)
    assert most_sprites_on_a_line(sprites) == MAX_SPRITES_ON_A_LINE


@pytest.mark.parametrize("revision", [Revision.PRG0, Revision.PRG1], ids=["prg0", "prg1"])
def test_the_layout(revision: Revision) -> None:
    """The owner's layout (2026-10-19), with the longest seed number, every level and key item
    stamped (17 list rows, the bow last) and a full inventory: the top rows as expected_rows draws
    them, the list on rows 10-26, PUSH START BUTTON under it, each counter cell's small x in its
    place, and the palettes: the box's blue around the box, the headings' orange (with the box's
    bottom line, palette 1 holding both) under the headings, white elsewhere."""
    emu = code_screen(revision, FULL_INVENTORY, full_list=True, seed=LONGEST_SEED)
    rows = nametable_rows(emu)
    slot = emu[CUR_SAVE_SLOT]
    name = bytes(emu[NAMES + slot * NAME_LENGTH + i] for i in range(NAME_LENGTH))
    top_rows = expected_rows(bytes(STATS_SIZE), name, bytes(LEVEL_RECORD_SIZE), emu[DEATH_COUNTS + slot],
                             (emu[HEART_VALUES] >> 4) + 1, seed_digit_tiles(LONGEST_SEED))[:LIST_FIRST_ROW]
    assert rows[:HEADINGS_ROW + 1] == top_rows[:HEADINGS_ROW + 1]
    text = ["".join(BYTE_TO_CHAR.get(tile, "?") for tile in row) for row in rows]
    last_list_row = LIST_FIRST_ROW + LIST_ROWS - 1
    assert text[last_list_row].startswith("  BOW ") and last_list_row + 1 == PUSH_START_ROW
    for row in (DEATHS_ROW, HEARTS_ROW):
        assert [column for column, tile in enumerate(rows[row]) if tile == SMALL_X_TILE] == list(SMALL_X_COLUMNS)
    assert text[PUSH_START_ROW].strip() == "PUSH START BUTTON"
    for row in range(ROWS):
        for column in range(2, COLUMNS - 2):
            expected = (HEADINGS_PALETTE if row in HEADINGS_CELL_ROWS and column in HEADINGS_COLUMNS
                        else BOX_PALETTE if row in BOX_ROWS and column in BOX_COLUMNS else None)
            if expected is not None:
                assert palette_at(emu, row, column) == expected, (row, column)
            elif row >= LIST_FIRST_ROW or column < BOX_COLUMNS.start - 1:
                assert palette_at(emu, row, column) == 0, (row, column)


@pytest.mark.parametrize("seed", [1, 3200278926, 8896983377507487750, LONGEST_SEED])
def test_the_seed_number(seed: int) -> None:
    """Owner request (2026-10-19): SEED and the first 10 digits on row 1, the rest under the
    digits on row 2 (at most 20: seeds are below 2^64)."""
    rows = nametable_rows(code_screen(Revision.PRG0, {}, seed=seed))
    digits = [CHAR_TO_BYTE[char] for char in str(seed)]
    blank = CHAR_TO_BYTE[" "]
    first, rest = digits[:10], digits[10:]
    assert rows[1] == bytes([blank] * 2 + [CHAR_TO_BYTE[c] for c in "SEED "] + first
                            + [blank] * (COLUMNS - SEED_DIGITS_COLUMN - len(first)))
    assert rows[2] == bytes([blank] * SEED_DIGITS_COLUMN + rest + [blank] * (COLUMNS - SEED_DIGITS_COLUMN - len(rest)))


def test_a_new_seed_carries_its_number_and_keeps_its_code() -> None:
    """Generation writes the seed number's tiles (ZORA mode); the seed's code never covers it, so
    a seed keeps its code; without a number (External mode) the bytes stay as they were."""
    rom = code_rom(Revision.PRG0)
    assert seed_digits_in(rom) == seed_digit_tiles(1)
    chosen = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1)
    base = verify_base_rom().read_bytes()
    world, _ = generate_world(chosen, base)
    unnumbered_config = replace(chosen.config, seed_number=None)
    assert chosen.config.seed_number == 1
    assert seed_code_items(world, chosen.config) == seed_code_items(world, unnumbered_config)
    unnumbered = serialize_to_rom(world, base, config=unnumbered_config)
    assert seed_digits_in(unnumbered) is None


# --- the counters' icons ----------------------------------------------------------------------------

# asm/fp-stats-01/bank_02.s: the counters' fixed icons (Y, tile, attributes, X): Link, a red heart
# container and a bomb; the sword is drawn as the items are, centered in its two columns.
COUNTER_LEFT_X, COUNTER_RIGHT_X = 0x10, 0x40
BOMB_TILE = 0x34
FIXED_COUNTER_ICONS = [(UPPER_ROW_Y, 0x5A, 0x00, COUNTER_LEFT_X), (UPPER_ROW_Y, 0x08, 0x40, COUNTER_LEFT_X + 8),
                       (LOWER_ROW_Y, 0x68, 0x02, COUNTER_LEFT_X), (LOWER_ROW_Y, 0x68, 0x42, COUNTER_LEFT_X + 7),
                       (LOWER_ROW_Y, BOMB_TILE, 0x01, COUNTER_RIGHT_X + 4)]
SWORD_X = COUNTER_RIGHT_X + 4
INVENTORY_BOMB = (UPPER_ROW_Y, 0x98 + 0x10 + 4)    # the item screen's place, one tile right
SWORD_PALETTES = {0: 0, 1: 0, 2: 1, 3: 2, 4: 2}  # none: the wooden sword's; level 4: the magical sword's
SMALL_X_PATTERN = bytes([0x00, 0x00, 0x44, 0x28, 0x10, 0x28, 0x44, 0x00]) + bytes(8)
BACKGROUND_PATTERNS, TILE_BYTES = 0x1000, 16      # CHR RAM: the background's pattern table, a tile's size


@pytest.mark.parametrize("bombs", [0, 4], ids=["no-bombs-left", "bombs-left"])
@pytest.mark.parametrize("sword", sorted(SWORD_PALETTES))
def test_the_counters_icons(sword: int, bombs: int) -> None:
    """Owner requests (2026-10-19), as Z2Randomizer draws its containers: Link over the deaths, the
    sword Link holds over the stabs, a red heart container over the hearts and a bomb over the
    bombs used, all shown whatever is held; the small x's pattern in tile $70. The B items show a
    bomb too when some are left."""
    emu = code_screen(Revision.PRG0, FULL_INVENTORY | {0x00: sword, 0x01: bombs})
    sprites = shown_sprites(emu)
    assert sprites[:len(FIXED_COUNTER_ICONS)] == FIXED_COUNTER_ICONS
    assert [attributes for y, _, attributes, x in sprites if (y, x) == (UPPER_ROW_Y, SWORD_X)] == [
        SWORD_PALETTES[sword]]
    inventory_bombs = [(y, x) for y, tile, _, x in sprites[len(FIXED_COUNTER_ICONS):] if tile == BOMB_TILE]
    assert inventory_bombs == ([INVENTORY_BOMB] if bombs else [])
    start = BACKGROUND_PATTERNS + SMALL_X_TILE * TILE_BYTES
    assert emu.pattern_tables()[start:start + TILE_BYTES] == SMALL_X_PATTERN


@pytest.mark.parametrize(("stabs", "bombs"), [(0, 0), (7, 65), (1080, 9999), (12345, 65535)])
def test_the_counts_are_left_aligned_and_capped(stabs: int, bombs: int) -> None:
    """Each count follows its small x, left-aligned in its columns; more than 9999 shows 9999."""
    emu = code_screen(Revision.PRG0, {}, counts={STABS: stabs, BOMBS: bombs})
    rows = nametable_rows(emu)
    deaths, hearts = emu[DEATH_COUNTS + emu[CUR_SAVE_SLOT]], (emu[HEART_VALUES] >> 4) + 1
    cells = slice(2, 2 + len(counter_cells(0, 0)))
    assert rows[DEATHS_ROW][cells] == counter_cells(deaths, stabs)
    assert rows[HEARTS_ROW][cells] == counter_cells(hearts, bombs)


def test_every_rom_has_the_screen() -> None:
    """Owner decision (2026-10-17): the screen is no longer a setting (it was, off by default, up to
    2.0 beta 6). Every ROM has it, except through the co-op hook (write_player_settings' coop),
    which writes the bytes of the ROM without it, so nothing writes the stats block there
    (tests/test_coop_page.py plays one). asm/settings/ still assembles both choices: off is the
    ROM without the patch."""
    assert "statistics_screen" not in {field.name for field in fields(PlayerSettings)}
    assert "statisticsScreen" not in {spec.key for spec in archipelago.player_setting_fields()}
    assert DEFAULTS["statistics_screen"] == "off"
    default = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla()).rom
    assert default == seed_rom()
    # every byte the patch writes, as off writes it (at PRG0's offsets, moved on to PRG1's)
    without = written_in_prg0_layout(default, lambda image: statistics_screen(image, False))
    assert without != default
    assert apply_player_settings(default, PlayerSettings(), coop=True) == without


def test_without_the_screen_start_goes_on_and_nothing_is_kept() -> None:
    """Without it (the co-op hook: the bytes of the ROM without it): the block is never written and
    Start after the credits goes straight to the save mode."""
    rom = apply_player_settings(seed_rom(), PlayerSettings(), coop=True)
    emu = Emulator(rom)
    emu.new_game()                                  # the first power-on clears save RAM ($6530-$7FFF)
    for i in range(STATS_SIZE):
        emu[STATS_BLOCK + i] = 0x5A
    emu.run(600)
    assert block(emu) == bytes([0x5A]) * STATS_SIZE


def test_the_labels_are_the_hints_item_names() -> None:
    """The sword row names the line (any sword stamps it), the others the hints' names, shortened
    to nine tiles as S.ARROWS: a first word's initial and the last word, or the last word."""
    def short(name: str) -> str:
        if len(name) <= LABEL_LENGTH:
            return name
        first, *_, last = name.split()
        initialled = f"{first[0]}.{last}"
        return initialled if len(initialled) <= LABEL_LENGTH and first != "POWER" else last
    expected = [UPGRADE_LINES[Item.WOOD_SWORD], *(short(item_name(item)) for item in KEY_ITEMS[1:])]
    assert expected == list(ITEM_LABELS)


# --- the clock's error over a played session ------------------------------------------------------

SETTLE_FRAMES = 30


def session(emu: Emulator, into_level_1: bool) -> None:
    """A scripted few minutes: walking across overworld screens (scrolls), the item screen, on
    PRG0's overworld a whirlwind to level 1 and rooms there, then a death and the continue screen."""
    for direction in (Button.LEFT, Button.UP, Button.RIGHT, Button.DOWN) * 3:
        emu.run(150, direction)
    # A walk may end mid-scroll (seed 1 since 114f280), and Start does nothing until the scroll is
    # over and Link has stepped onto the new screen.
    emu.run_until(lambda: emu.mode == Mode.PLAY)
    emu.run(SETTLE_FRAMES)
    emu.open_item_screen()
    emu.close_item_screen()
    if into_level_1:
        emu.walk_into_level_1()
    for direction in (Button.UP, Button.LEFT, Button.RIGHT, Button.DOWN) * 2:
        emu.run(200, direction)
    emu[HEART_VALUES] = 0x20
    emu[HEART_PARTIAL] = 0                                               # one hit left
    emu.run(1200, Button.UP)


def clock_error(name: str) -> tuple[float, float]:
    emu = playing(name)
    put_word(emu, TOTAL, 0)
    emu[STATS_BLOCK + SUB_FRAME] = 0
    emu[STATS_BLOCK + TENTH_PHASE] = 0
    start = emu.frames
    session(emu, into_level_1=name == "prg0")
    played = (emu.frames - start) / NTSC_FPS
    counted = word(emu, TOTAL) + emu[STATS_BLOCK + SUB_FRAME] / 60
    return played, played - counted


@pytest.mark.slow
@pytest.mark.parametrize("name", ROMS)
def test_the_clocks_error_over_a_session(name: str) -> None:
    """The clock misses only the frames the game runs without its NMI: under a second a minute
    here (the measurement is printed)."""
    played, missed = clock_error(name)
    print(f"{name}: {played:.1f} s played, {missed:.2f} s not counted ({100 * missed / played:.2f}%)")  # noqa: T201
    assert 0 <= missed < played / 60


# --- nothing else writes the setting's bytes ------------------------------------------------------

@pytest.mark.slow
@pytest.mark.parametrize("case", sorted(FLAG_CASES))
def test_no_flag_writes_the_settings_bytes(case: str) -> None:
    """Every Archipelago flag case's finished ROM, before the player settings, holds the setting's
    off bytes at all its offsets: no flag, pass or per-seed write lands there, so off is the ROM
    without it and on overwrites nothing of the seed's."""
    flags, zora_flags = FLAG_CASES[case]
    chosen = plan(flags, 1, zora_flags)
    world, _ = generate_world(chosen, vanilla())
    rom = serialize_to_rom(world, vanilla(), config=chosen.config)
    unset = bytearray(rom)
    statistics_screen(unset, False)
    assert bytes(unset) == rom
