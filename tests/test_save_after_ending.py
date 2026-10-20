"""FP-SAVE-01 (asm/fp-save-01/, owner 2026-10-17) in the emulator: Start after the ending saves the
file as SAVE does after a death or Up+A and returns to the file-select screen, instead of clearing
it for the second quest; the file then loads with its items, triforce pieces and hearts, in the
first quest. With the statistics screen (every ROM but the co-op hook's) Start first shows the
screen and then leaves this way; without it, Start leaves at once."""
import pytest

from tests.emulator import (
    CUR_SAVE_SLOT,
    GAME_MODE,
    GAME_SUBMODE,
    INV_BOMBS,
    INV_TRIFORCE,
    ITEMS,
    OBJ_TIMER,
    QUEST_NUMBERS,
    Button,
    Emulator,
    Mode,
)
from tests.test_stats_screen import (
    HEART_VALUES,
    INV_LADDER,
    INV_RAFT,
    IS_UPDATING_MODE,
    LAST_WIN_SUBMODE,
    SAVE_MODE,
    SCREEN_STATE,
    STATS_BLOCK,
    WIN_MODE,
    seed_rom,
)
from tests.test_stats_screen_play import finish_and_show
from zora.rom.player_settings import PlayerSettings, apply_player_settings

ALL_TRIFORCE_PIECES = 0xFF
WHITE_SWORD = 2
BOMBS = 7
HEART_CONTAINERS_9 = 0x88            # HeartValues: nine containers (high nibble), all full
SAVE_FRAMES = 900


def play_to_the_ending(emu: Emulator) -> dict[int, int]:
    """Start a file, give Link items and every triforce piece, and run the win mode to its last
    submode. Returns the inventory bytes the saved file must keep."""
    emu.new_game()
    kept = {ITEMS: WHITE_SWORD, INV_BOMBS: BOMBS, INV_LADDER: 1, INV_RAFT: 1,
            INV_TRIFORCE: ALL_TRIFORCE_PIECES, HEART_VALUES: HEART_CONTAINERS_9}
    for address, value in kept.items():
        emu[address] = value
    return kept


def leave_to_file_select_and_load(emu: Emulator) -> None:
    assert emu.mode == SAVE_MODE
    emu.run_until(lambda: emu.mode == Mode.FILE_SELECT, limit=SAVE_FRAMES)
    emu.reset()
    emu.boot_to_file_select()
    emu.start_game()


def assert_the_file_kept(emu: Emulator, kept: dict[int, int]) -> None:
    for address, value in kept.items():
        assert emu[address] == value, f"${address:04X}: {emu[address]:#04x}, saved {value:#04x}"
    assert emu[QUEST_NUMBERS + emu[CUR_SAVE_SLOT]] == 0              # still the first quest


@pytest.mark.parametrize("coop", [False, True], ids=["statistics screen", "co-op, no screen"])
def test_start_after_the_ending_saves_the_file(coop: bool) -> None:
    emu = Emulator(apply_player_settings(seed_rom(), PlayerSettings(), coop=coop))
    kept = play_to_the_ending(emu)
    if coop:
        finish_and_show_without_screen(emu)
    else:
        finish_and_show(emu)
        assert emu[STATS_BLOCK + SCREEN_STATE] == 1
        emu.press(Button.START, after=1)
    leave_to_file_select_and_load(emu)
    assert_the_file_kept(emu, kept)


def finish_and_show_without_screen(emu: Emulator) -> None:
    """finish_and_show's ending; with no screen, its Start goes straight to the save mode."""
    emu[GAME_MODE] = WIN_MODE
    emu[IS_UPDATING_MODE] = 1
    emu[GAME_SUBMODE] = LAST_WIN_SUBMODE
    emu.run_until(lambda: emu[OBJ_TIMER] == 0, limit=2000)
    emu.run(5)
    emu.press(Button.START, after=1)                            # the save mode takes a few frames
