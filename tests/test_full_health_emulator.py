"""Start With Full Health (ZORA flag full_health; asm/flags2/full-health/) in the emulator, on PRG0
and PRG1: the ROM with the flag on against one without it (a ZORA flag moves the seed, so the two are
different worlds; only the hearts are compared).

  - A five-container file saved at two hearts and a half (SAVE from the continue screen): with the
    flag it comes back with five full hearts and the partial heart full; without it, PRG0's three
    hearts (the death menu's reset, which SAVE goes through too).
  - A saved file whose hearts are lowered afterwards (checksum kept right): the file-select menu's
    load fills them with the flag, and leaves them without it."""
from functools import cache

import pytest

from tests.emulator import CONTINUE_MODE, CONTROLLER_2_SHIFT, GAME_SUBMODE, SAVE_CHOICE, Button, Emulator, Mode
from tests.needs import needs_base_rom
from tests.test_revision import prg1
from tests.test_stats_screen import HEART_PARTIAL, HEART_VALUES
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import build, finish, plan
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom

pytestmark = needs_base_rom

ON = zora_flags.encode(zora_flags.ZoraFlags(full_health=ThreeState.ON))
SEED = 1
FIVE_CONTAINERS_TWO_HEARTS = 0x41      # high nibble: containers less one; low nibble: full hearts less one
HALF_HEART = 0x80
FIVE_FULL = 0x44
THREE_FULL_OF_FIVE = 0x42              # PRG0's reset: three full hearts
ONE_FULL_OF_FIVE = 0x40
SETTLE_FRAMES = 60
SAVE_FILE_A_HEARTS = 0x601A + 0x18     # SaveFileAItems0 + the offset of HeartValues in the Items block
SAVE_FILE_A_CHECKSUM = 0x6524          # FileAChecksums: slot 0's [$0E], [$0F]: the 16-bit sum, high byte first
SAVE_LIMIT = 900


@cache
def rom(flag_on: bool, on_prg1: bool) -> bytes:
    base = prg1() if on_prg1 else remember_repo_base_rom()
    return finish(build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, ON if flag_on else ""), base), base)


def hearts(emu: Emulator) -> tuple[int, int]:
    return emu[HEART_VALUES], emu[HEART_PARTIAL]


def saved_game(flag_on: bool, on_prg1: bool) -> Emulator:
    """A new game at five containers and two and a half hearts, saved with Up and A and SAVE; the
    emulator stands on the file-select menu."""
    emu = Emulator(rom(flag_on, on_prg1))
    emu.new_game()
    emu.run(SETTLE_FRAMES)
    emu[HEART_VALUES], emu[HEART_PARTIAL] = FIVE_CONTAINERS_TWO_HEARTS, HALF_HEART
    emu.open_item_screen()
    combination = Button.UP | Button.A
    emu.nes.controller = combination << CONTROLLER_2_SHIFT | combination
    for _ in range(3):
        emu.nes.step(1)
    emu.nes.controller = 0
    emu.run_until(lambda: emu.mode == CONTINUE_MODE)
    emu.run(20)
    while emu[GAME_SUBMODE] != SAVE_CHOICE:
        emu.press(Button.SELECT)
    emu.press(Button.START)
    emu.run_until(lambda: emu.mode == Mode.FILE_SELECT, limit=SAVE_LIMIT)
    return emu


def start_slot_0(emu: Emulator) -> tuple[int, int]:
    emu.reset()
    emu.boot_to_file_select()
    emu.start_game()
    return hearts(emu)


PRG1_MARK = pytest.param(True, id="PRG1", marks=pytest.mark.skipif(not PRG1_ROM_PATH.exists(),
                                                                   reason="no PRG1 ROM beside the base"))


@pytest.mark.parametrize("on_prg1", [pytest.param(False, id="PRG0"), PRG1_MARK])
def test_saving_and_loading_restore_every_heart(on_prg1: bool) -> None:
    assert start_slot_0(saved_game(True, on_prg1)) == (FIVE_FULL, 0xFF)
    assert start_slot_0(saved_game(False, on_prg1)) == (THREE_FULL_OF_FIVE, 0xFF)


@pytest.mark.parametrize("on_prg1", [pytest.param(False, id="PRG0"), PRG1_MARK])
def test_loading_a_file_saved_at_low_health_fills_it(on_prg1: bool) -> None:
    results = {}
    for flag_on in (True, False):
        emu = saved_game(flag_on, on_prg1)
        lowered = emu[SAVE_FILE_A_HEARTS] - ONE_FULL_OF_FIVE
        total = emu[SAVE_FILE_A_CHECKSUM] * 256 + emu[SAVE_FILE_A_CHECKSUM + 1] - lowered
        emu[SAVE_FILE_A_HEARTS] = ONE_FULL_OF_FIVE
        emu[SAVE_FILE_A_CHECKSUM], emu[SAVE_FILE_A_CHECKSUM + 1] = total >> 8, total & 0xFF
        results[flag_on] = start_slot_0(emu)
    assert results == {True: (FIVE_FULL, 0xFF), False: (ONE_FULL_OF_FIVE, 0xFF)}
