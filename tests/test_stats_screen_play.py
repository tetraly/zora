"""The statistics screen (FP-STATS-01, asm/fp-stats-01/) end to end in the emulator, slow: a file
registered over a dirty stats block clears it, a scripted session of real inputs moves the clock,
the overworld's time, the sword stabs and the bombs used, and Start after the credits shows those
values; Off writes nothing a build without the feature lacks and leaves the game's ending alone;
with fp-start-02's table (bank 2 $B700, just past the screen's code) both features run together.

tests/test_stats_screen.py covers each counter on its own with poked state; this module plays
through. The clock runs about 0.5% short (it misses the frames the game runs without its NMI;
test_stats_screen.test_the_clocks_error_over_a_session measures it), so the clock is checked
against the frames played within CLOCK_TOLERANCE, never as an exact frame count."""
from dataclasses import replace
from functools import cache

import pytest

from tests.emulator import (
    CUR_SAVE_SLOT,
    GAME_MODE,
    GAME_SUBMODE,
    INV_BOMBS,
    ITEMS,
    NAME_LENGTH,
    NAMES,
    OBJ_TIMER,
    SELECTED_ITEM_SLOT,
    Button,
    Emulator,
    Mode,
)
from tests.test_feature_patches import vanilla
from tests.test_start_items_patch import SEED_TABLE, items, with_table
from tests.test_stats_screen import (
    AREAS,
    BOMBS,
    CUR_PPU_MASK,
    DEATH_COUNTS,
    HEART_VALUES,
    IS_UPDATING_MODE,
    LAST_WIN_SUBMODE,
    LEVEL_RECORD_RAM,
    LEVEL_RECORD_SIZE,
    NTSC_FPS,
    SAVE_MODE,
    SCREEN_STATE,
    STABS,
    STATS_BLOCK,
    STATS_SIZE,
    SUB_FRAME,
    TOTAL,
    VIDEO_ON,
    WIN_MODE,
    block,
    cleared,
    count_text,
    expected_rows,
    nametable_rows,
    seed_rom,
    time_text,
    word,
)
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, generate_world, plan
from zora.rom.base_rom import original_bytes, piece_length
from zora.rom.player_settings import PlayerSettings, apply_player_settings, statistics_screen
from zora.rom.player_settings_data import SETTINGS
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom.text_encoding import BYTE_TO_CHAR

pytestmark = pytest.mark.slow

CLOCK_TOLERANCE = 0.01          # the clock may run short by up to 1% (measured about 0.5%), never long
FRAME_SECONDS = 2 / 60          # plus the clock's sub-second remainder at each end
DIRTY = 0x5A                    # what the stats block holds before a file is registered
BOMB_SLOT = 1                   # SelectedItemSlot of the bombs
STABS_SWUNG, BOMBS_PLACED = 3, 2
# The hooks the setting writes into the game's own code (asm/fp-stats-01/patch.toml), by file offset:
# the clock's JSR, the stab's JMP, the win mode's JSR operand and the registration's JSR.
HOOKS = {0x1E572: 2, 0x14E25: 5, 0x0AB90: 2, 0x09F80: 5}


def clock(emu: Emulator) -> float:
    return word(emu, TOTAL) + emu[STATS_BLOCK + SUB_FRAME] / 60


def register_over_a_dirty_block(emu: Emulator) -> None:
    """Power on, fill the stats block, register a new file and start it."""
    emu.boot_to_file_select()
    for offset in range(STATS_SIZE):
        emu[STATS_BLOCK + offset] = DIRTY
    emu.register_file()


def play_a_session(emu: Emulator) -> tuple[float, float]:
    """From the start of play: walk across overworld screens, swing the sword STABS_SWUNG times and
    place BOMBS_PLACED bombs. Returns the seconds played and the seconds the clock counted."""
    start_frame, start_clock = emu.frames, clock(emu)
    for direction in (Button.LEFT, Button.UP, Button.RIGHT, Button.DOWN) * 2:
        emu.run(150, direction)
    emu.run(8, Button.UP)                                       # face a way (FP-ENTR-01)
    for _ in range(STABS_SWUNG):
        emu.press(Button.A, after=30)
    emu[SELECTED_ITEM_SLOT] = BOMB_SLOT
    for _ in range(BOMBS_PLACED):
        emu.press(Button.B, after=150)                          # each bomb goes off before the next
    return (emu.frames - start_frame) / NTSC_FPS, clock(emu) - start_clock


def assert_the_clock_kept_time(played: float, counted: float) -> None:
    missed = played - counted
    assert -FRAME_SECONDS <= missed <= CLOCK_TOLERANCE * played + FRAME_SECONDS, (played, counted)


def finish_and_show(emu: Emulator) -> None:
    """Enter the win mode's last submode from play (the credits skipped), wait it out, check the
    screen is not up yet, and press Start."""
    emu[GAME_MODE] = WIN_MODE
    emu[IS_UPDATING_MODE] = 1
    emu[GAME_SUBMODE] = LAST_WIN_SUBMODE
    emu.run_until(lambda: emu[OBJ_TIMER] == 0, limit=2000)
    emu.run(5)
    assert emu[STATS_BLOCK + SCREEN_STATE] == 0
    emu.press(Button.START, after=6)


def assert_the_screen_shows_the_block(emu: Emulator) -> None:
    """The screen is up, in the win mode, and its nametable is the rows built from the block, the
    file's name, the status bar's level record, the slot's deaths and the heart containers."""
    assert emu.mode == WIN_MODE and emu[STATS_BLOCK + SCREEN_STATE] == 1 and emu[CUR_PPU_MASK] == VIDEO_ON
    slot = emu[CUR_SAVE_SLOT]
    name = bytes(emu[NAMES + slot * NAME_LENGTH + i] for i in range(NAME_LENGTH))
    record = bytes(emu[LEVEL_RECORD_RAM + i] for i in range(LEVEL_RECORD_SIZE))
    hearts = (emu[HEART_VALUES] >> 4) + 1
    assert nametable_rows(emu) == expected_rows(block(emu), name, record, emu[DEATH_COUNTS + slot], hearts)


def screen_text(emu: Emulator) -> list[str]:
    return ["".join(BYTE_TO_CHAR.get(tile, "?") for tile in row) for row in nametable_rows(emu)]


def test_a_played_session_shows_on_the_screen() -> None:
    """Registration clears the block; the session's clock, overworld time, stabs and bombs are
    counted; the screen comes up only on Start after the credits and shows them; Start leaves."""
    emu = Emulator(seed_rom())
    register_over_a_dirty_block(emu)
    assert block(emu) == cleared(emu[INV_BOMBS])
    emu.start_game()
    emu[ITEMS] = 1                                              # the wooden sword
    emu[INV_BOMBS] = 4
    played, counted = play_a_session(emu)
    assert_the_clock_kept_time(played, counted)
    assert word(emu, AREAS) == word(emu, TOTAL) > 0             # all of it on the overworld
    assert (word(emu, STABS), word(emu, BOMBS)) == (STABS_SWUNG, BOMBS_PLACED)
    finish_and_show(emu)
    assert_the_screen_shows_the_block(emu)
    text = screen_text(emu)
    assert f"STABS  {count_text(STABS_SWUNG)}" in "".join(text)
    assert f"BOMBS  {count_text(BOMBS_PLACED)}" in "".join(text)
    assert any(row.strip().startswith(f"OVERWORLD {time_text(word(emu, AREAS))}") for row in text)
    emu.run(30)
    assert emu.mode == WIN_MODE                                 # it waits for Start
    emu.press(Button.START, after=1)
    assert emu.mode == SAVE_MODE and emu[STATS_BLOCK + SCREEN_STATE] == 0


@cache
def unfinished_rom() -> bytes:
    """Seed 1's ROM as serialized, before any player setting."""
    chosen = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1)
    world, _ = generate_world(chosen, vanilla())
    return serialize_to_rom(world, vanilla(), config=chosen.config)


def test_off_is_the_rom_without_the_feature() -> None:
    """Off: the hooks hold PRG0's instructions, every byte the setting writes is the serialized
    ROM's own, the finished ROM equals the build with the other player settings only, and On
    differs from it only at the setting's bytes."""
    off = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla(), PlayerSettings(statistics_screen=False)).rom
    for offset, size in HOOKS.items():
        assert off[offset:offset + size] == original_bytes(offset, size), hex(offset)
    untouched = bytearray(unfinished_rom())
    statistics_screen(untouched, False)
    assert bytes(untouched) == unfinished_rom()
    assert off == apply_player_settings(unfinished_rom(), replace(PlayerSettings(), statistics_screen=False))
    written = {offset + i for offset, piece in SETTINGS["statistics_screen"]["on"]
               for i in range(piece_length(piece))}
    on = seed_rom()
    changed = {i for i, (a, b) in enumerate(zip(off, on, strict=True)) if a != b}
    assert changed and changed <= written


def test_off_keeps_no_block_and_the_ending_goes_on() -> None:
    """Off, through the same session: the block is never written and Start after the credits goes
    straight to the save mode."""
    emu = Emulator(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla(),
                                PlayerSettings(statistics_screen=False)).rom)
    emu.new_game()                                              # the first power-on clears save RAM
    for offset in range(STATS_SIZE):
        emu[STATS_BLOCK + offset] = DIRTY
    emu[ITEMS] = 1
    emu[INV_BOMBS] = 4
    play_a_session(emu)
    emu[GAME_MODE] = WIN_MODE
    emu[IS_UPDATING_MODE] = 1
    emu[GAME_SUBMODE] = LAST_WIN_SUBMODE
    emu.run_until(lambda: emu[OBJ_TIMER] == 0, limit=2000)
    emu.run(5)
    emu.press(Button.START, after=6)
    assert emu.mode == SAVE_MODE
    assert block(emu) == bytes([DIRTY]) * STATS_SIZE


def test_with_start_items_both_features_work() -> None:
    """fp-start-02's table (the white sword, 4 bombs, 5 hearts): registration copies it and still
    clears the stats block; the session needs no poke (the table's sword and bombs), is counted,
    and the screen shows it with the table's five heart containers."""
    emu = Emulator(with_table(SEED_TABLE))
    register_over_a_dirty_block(emu)
    assert block(emu) == cleared(emu[INV_BOMBS])
    emu.start_game()
    assert items(emu) == SEED_TABLE
    assert emu.mode == Mode.PLAY
    played, counted = play_a_session(emu)
    assert_the_clock_kept_time(played, counted)
    assert (word(emu, STABS), word(emu, BOMBS)) == (STABS_SWUNG, BOMBS_PLACED)
    finish_and_show(emu)
    assert_the_screen_shows_the_block(emu)
    assert f"HEARTS {count_text(5)}" in "".join(screen_text(emu))
