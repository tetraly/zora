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
from dataclasses import replace
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
from tests.test_feature_patches import vanilla
from zora import archipelago
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, generate_world, plan
from zora.generate.steps.hint_text import UPGRADE_LINES, item_name
from zora.model.enums import Item
from zora.rom.layout import FP_LEVEL_DASH_TILE as DASH_TILE
from zora.rom.player_settings import (
    PlayerSettings,
    apply_player_settings,
    level_label,
    statistics_screen,
)
from zora.rom.player_settings_data import DEFAULTS
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom.text_encoding import CHAR_TO_BYTE

# The stats block (asm/fp-stats-01/bank_00.s).
STATS_BLOCK = 0x7F00
STATS_SIZE = 0x40
MAGIC, FLAGS, TOTAL, SUB_FRAME, TENTH_PHASE = 0x00, 0x01, 0x02, 0x04, 0x05
AREAS, LEVEL_STAMPS, ITEM_STAMPS, STABS, BOMBS, PREV_BOMBS, SCREEN_STATE = 0x06, 0x1A, 0x2C, 0x38, 0x3A, 0x3C, 0x3D
STATS_MAGIC, FINISHED = 0xA5, 0x80
NTSC_FPS = 60.0988                   # frames a second the clock's 601-per-10 rule stands for

# RAM (src/Variables.inc).
IS_UPDATING_MODE = 0x11
CUR_PPU_MASK = 0xFE
DEATH_COUNTS = 0x630
HEART_VALUES = 0x66F
HEART_PARTIAL = 0x670
INV_ARROW, INV_LADDER, INV_RAFT, INV_RING, INV_BOOMERANG = 0x659, 0x663, 0x660, 0x662, 0x674
VIDEO_ON = 0x1E
WIN_MODE, SAVE_MODE, LAST_WIN_SUBMODE = 0x13, 0x0D, 4

# The screen (asm/fp-stats-01/bank_02.s).
NAME_TABLE = 0x2000
ROWS, COLUMNS = 30, 32
LIST_FIRST_ROW, LIST_ROWS = 4, 16
LABEL_LENGTH = 9
HIDDEN_Y = 0xF8
CODE_ICON_Y = 7
ITEM_LABELS = ("SWORD", "LADDER", "BRACELET", "RAFT", "RECORDER", "S.ARROWS")
KEY_ITEMS = (Item.WOOD_SWORD, Item.LADDER, Item.POWER_BRACELET, Item.RAFT, Item.RECORDER, Item.SILVER_ARROWS)


# --- ROMs -----------------------------------------------------------------------------------------

@cache
def prg0_with_stats() -> bytes:
    """PRG0 with only the setting's bytes (no series patch, no seed code)."""
    rom = bytearray(vanilla())
    statistics_screen(rom, True)
    return bytes(rom)


@cache
def seed_rom(level_word: str = "LEVEL") -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla(),
                        PlayerSettings(level_word=level_word, statistics_screen=True)).rom


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


def count_text(value: int) -> str:
    return f"{value:>5}"


def expected_rows(data: bytes, name: bytes, level_record: bytes, deaths: int, hearts: int) -> list[bytes]:
    """The 30 nametable rows the screen draws for a block: the file name, the headings, the
    overworld, the stamped levels and items in stamp order, the levels entered and not completed,
    the counters and PUSH START BUTTON. A level's label is the status bar's record (its tiles
    but the number) and the level's number."""
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
        return tiles("  ") + label + tiles(f" {time_in_text} {completion}     ")

    blank = tiles(" " * COLUMNS)
    rows = [blank, tiles("  ") + name + tiles(" " * 22), blank,
            tiles(" " * 12 + "TIME IN CLEARED" + " " * 5),
            list_row(tiles("OVERWORLD"), at(AREAS), 0)]
    stamps = [(at(LEVEL_STAMPS + 2 * index), index) for index in range(15)]
    for stamp, index in sorted(entry for entry in stamps if entry[0]):
        if index < 9:
            rows.append(list_row(level_tiles(index + 1), at(AREAS + 2 * (index + 1)), stamp))
        else:
            rows.append(list_row(tiles(ITEM_LABELS[index - 9].ljust(LABEL_LENGTH)), None, stamp))
    rows += [list_row(level_tiles(index + 1), at(AREAS + 2 * (index + 1)), 0)
             for index in range(9) if not stamps[index][0] and at(AREAS + 2 * (index + 1))]
    rows += [blank] * (LIST_FIRST_ROW + LIST_ROWS - len(rows))
    rows.append(blank)
    counters = (("DEATHS", deaths), ("HEARTS", hearts), ("STABS ", at(STABS)), ("BOMBS ", at(BOMBS)))
    rows += [tiles("  " + label + " " + count_text(value) + " " * 18) for label, value in counters]
    rows += [blank, blank, tiles(" " * 7 + "PUSH START BUTTON" + " " * 8), blank, blank]
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
    """A finished run: levels 1, 3 and 9 completed, level 5 entered, four key items, counters."""
    data = bytearray(STATS_SIZE)
    data[MAGIC], data[FLAGS] = STATS_MAGIC, FINISHED

    def put(offset: int, value: int) -> None:
        data[offset:offset + 2] = value.to_bytes(2, "little")

    put(TOTAL, 9000)
    for area, seconds in ((0, 3000), (1, 700), (3, 900), (5, 65), (9, 1500)):
        put(AREAS + 2 * area, seconds)
    for level, stamp in ((1, 1200), (3, 2400), (9, 9000)):
        put(LEVEL_STAMPS + 2 * (level - 1), stamp)
    for item, stamp in ((0, 90), (1, 2400), (3, 3100), (5, 40000)):       # sword, ladder, raft, silver
        put(ITEM_STAMPS + 2 * item, stamp)
    put(STABS, 1234)
    put(BOMBS, 56)
    return bytes(data)


def show_screen(name: str, level_word: str = "LEVEL", credits: bool = True) -> Emulator:
    emu = Emulator(seed_rom(level_word) if name == "seed" else ROMS[name]())
    emu.load(ending_state(name, level_word, credits))
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


@pytest.mark.parametrize("name", ROMS)
def test_start_after_the_credits_shows_the_screen_and_start_leaves(name: str) -> None:
    emu = show_screen(name)
    assert emu[CUR_PPU_MASK] == VIDEO_ON and emu[STATS_BLOCK + SCREEN_STATE] == 1 and emu.mode == WIN_MODE
    slot = emu[CUR_SAVE_SLOT]
    file_name = bytes(emu[NAMES + slot * NAME_LENGTH + i] for i in range(NAME_LENGTH))
    record = bytes(emu[LEVEL_RECORD_RAM + i] for i in range(LEVEL_RECORD_SIZE))
    assert nametable_rows(emu) == expected_rows(prepared_block(), file_name, record, deaths=3, hearts=13)
    oam = emu.sprites()
    shown = [oam[i:i + 4] for i in range(0, len(oam), 4) if oam[i] != HIDDEN_Y]
    code_sprites = [record for record in shown if record[0] == CODE_ICON_Y]
    assert len(code_sprites) >= 4 if name == "seed" else not code_sprites  # PRG0 has no seed code
    assert len(shown) - len(code_sprites) >= 8                  # the eight items held, one or two sprites each
    emu.run(30)
    assert emu.mode == WIN_MODE                                           # it waits
    emu.press(Button.START, after=1)
    assert emu.mode == SAVE_MODE and emu[STATS_BLOCK + SCREEN_STATE] == 0


@pytest.mark.parametrize("level_word", ["PALACE", "DEN"])
def test_the_screen_takes_the_level_word(level_word: str) -> None:
    """The level rows read as the status bar does: PALACE1, DEN-1 (the status bar's dash)."""
    emu = show_screen("seed", level_word, credits=False)
    label = nametable_rows(emu)[LIST_FIRST_ROW + 2][2:2 + LABEL_LENGTH]       # level 1, after the sword
    expected = level_label(level_word)
    tiles = bytes(DASH_TILE if char == "-" else CHAR_TO_BYTE[char] for char in expected)
    assert label == tiles.ljust(LABEL_LENGTH, bytes([CHAR_TO_BYTE[" "]]))


def test_off_by_default() -> None:
    """Owner ruling (beta 3): the screen is off by default until it is better tested, an option
    players turn on. A ROM with the default player settings is the ROM without the setting: no
    patch, no hook, so nothing writes the stats block (tests/test_coop_page.py plays one)."""
    assert PlayerSettings().statistics_screen is False
    assert DEFAULTS["statistics_screen"] == "off"
    spec = next(spec for spec in archipelago.player_setting_fields() if spec.key == "statisticsScreen")
    assert (spec.yaml_key, spec.default, spec.value_keys) == ("statistics_screen", "off", (("on", "on"), ("off", "off")))
    default = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla()).rom
    assert default == generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla(),
                                   PlayerSettings(statistics_screen=False)).rom
    without = bytearray(default)
    statistics_screen(without, False)                # every byte the setting writes, as off writes it
    assert bytes(without) == default
    assert default != seed_rom()


def test_without_the_screen_start_goes_on_and_nothing_is_kept() -> None:
    """Off (the bytes of the ROM without it): the block is never written and Start after the
    credits goes straight to the save mode."""
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla(), PlayerSettings(statistics_screen=False)).rom
    assert rom == apply_player_settings(seed_rom(), replace(PlayerSettings(), statistics_screen=False))
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

def session(emu: Emulator, into_level_1: bool) -> None:
    """A scripted few minutes: walking across overworld screens (scrolls), the item screen, on
    PRG0's overworld a whirlwind to level 1 and rooms there, then a death and the continue screen."""
    for direction in (Button.LEFT, Button.UP, Button.RIGHT, Button.DOWN) * 3:
        emu.run(150, direction)
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
