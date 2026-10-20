"""fp-start-02 (FP-START-02/03; asm/fp-start-02/): a seed's starting items, a 40-byte table copied
into the Items block of a new file and of a slot switched to the second quest.

The patch is inert by default: a finished ROM holds PRG0's code at its hooks and PRG0's free space
at its table. Written with PRG0's start as the table, a new file starts exactly as without it;
with a seed's table, a new file and the second quest start with that table, the statistics
screen's clear on registration (fp-stats-01, the hook after the starting values) still runs, and
the parser reads the table back (zora/rom/parse/features.py, FP-START-01's check). The generation
side and the serializer switch are in zora/rom/code_patches.py (START_ITEMS)."""
from functools import cache

import pytest

from tests.emulator import GAME_MODE, GAME_SUBMODE, ITEMS, OBJ_TIMER, Button, Emulator
from tests.test_feature_patches import vanilla
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import original_bytes
from zora.rom.code_patches import PRG0_START_ITEMS, START_ITEMS_SIZE, start_items_writes
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import PlayerSettings, apply_player_settings

STATS_BLOCK, STATS_MAGIC, STATS_STABS = 0x7F00, 0xA5, 0x3A
IS_UPDATING_MODE = 0x11
WIN_MODE, SAVE_MODE, LAST_WIN_SUBMODE = 0x13, 0x0D, 4

# A seed's start: the white sword, 4 bombs, the raft and the ladder, 5 hearts and containers,
# 12 maximum bombs (Items offsets: sword 0, bombs 1, raft 9, ladder $0C, HeartValues $18,
# HeartPartial $19, MaxBombs $25).
SEED_CHANGES = {0x00: 2, 0x01: 4, 0x09: 1, 0x0C: 1, 0x18: 0x44, 0x25: 12}
SEED_TABLE = bytes(SEED_CHANGES.get(offset, value) for offset, value in enumerate(PRG0_START_ITEMS))


@cache
def finished(statistics_screen: bool = True) -> bytes:
    """Seed 1's ROM, with the statistics screen (every ROM's) or without it (the co-op hook)."""
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, vanilla()).rom
    return rom if statistics_screen else apply_player_settings(rom, PlayerSettings(), coop=True)


@cache
def with_table(table: bytes, statistics_screen: bool = True) -> bytes:
    rom = bytearray(finished(statistics_screen))
    for offset, data in start_items_writes(table):
        rom[offset:offset + len(data)] = data
    return bytes(rom)


def items(emu: Emulator) -> bytes:
    return bytes(emu[ITEMS + i] for i in range(START_ITEMS_SIZE))


def test_inert_by_default() -> None:
    rom = finished()
    assert all(rom[offset:offset + len(data)] == original_bytes(offset, len(data))
               for offset, data in start_items_writes(PRG0_START_ITEMS))
    world = parse_rom(rom)
    assert world.starting_items_new_file == world.starting_items_second_quest == PRG0_START_ITEMS


@pytest.mark.parametrize("table", [PRG0_START_ITEMS, SEED_TABLE], ids=["prg0", "seed"])
def test_the_table_reads_back(table: bytes) -> None:
    world = parse_rom(with_table(table))
    assert world.starting_items_new_file == world.starting_items_second_quest == table


def new_game(rom: bytes) -> Emulator:
    emu = Emulator(rom)
    emu.new_game()
    return emu


def test_prg0s_table_starts_a_new_file_as_without_the_patch() -> None:
    assert items(new_game(with_table(PRG0_START_ITEMS))) == items(new_game(finished())) == PRG0_START_ITEMS


def test_a_seeds_table_starts_a_new_file() -> None:
    """The new file holds the table, and the statistics screen's clear on registration still ran."""
    emu = Emulator(with_table(SEED_TABLE))
    emu.boot_to_file_select()
    emu[STATS_BLOCK + STATS_STABS] = 0x77
    emu.register_file()
    assert emu[STATS_BLOCK] == STATS_MAGIC and emu[STATS_BLOCK + STATS_STABS] == 0
    emu.start_game()
    assert items(emu) == SEED_TABLE


@pytest.mark.parametrize("statistics_screen", [True, False], ids=["stats-screen", "no-stats-screen"])
def test_the_win_keeps_the_file_and_never_reaches_the_table(statistics_screen: bool) -> None:
    """After the win, Start (twice with the statistics screen: it shows, then leaves) goes to the
    save mode and keeps the file's Items block (FP-SAVE-01, 2026-10-17): it no longer switches the
    slot to the second quest, so fp-start-02's second-quest table is never reached."""
    emu = new_game(with_table(SEED_TABLE, statistics_screen))
    emu.run(10)
    for offset in range(START_ITEMS_SIZE):
        emu[ITEMS + offset] = 0x01
    emu[GAME_MODE] = WIN_MODE
    emu[IS_UPDATING_MODE] = 1
    emu[GAME_SUBMODE] = LAST_WIN_SUBMODE
    emu.run_until(lambda: emu[OBJ_TIMER] == 0, limit=2000)
    emu.run(5)
    for _ in range(2 if statistics_screen else 1):
        emu.press(Button.START, after=1)                        # the save mode takes a few frames
    assert emu[GAME_MODE] == SAVE_MODE
    assert items(emu) == bytes([0x01]) * START_ITEMS_SIZE
