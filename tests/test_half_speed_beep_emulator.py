"""The low-health beep's half speed (FP-BEEP-01's third choice, tetraly/zora#3;
asm/settings/half-speed-beep/) in the emulator: with no full heart left, Kept starts a beep every
BEEP_FRAMES frames, as PRG0 does, and Half speed every 2 x BEEP_FRAMES; refilled hearts stop it, and
it starts again at its own rate when they run low again. Removed, and Hidden Health (FP-HIDE-01)
over Half speed, never beep. The beep is read off the sound engine's tune channel 0 (Tune0 holds
HEART_WARNING while it plays), a beep starting on the frame Tune0 turns to it."""
from functools import cache
from itertools import pairwise

import pytest

from tests.emulator import Emulator
from tests.test_beta8_patches import B55_ON
from tests.test_revision import needs_both, prg1
from tests.test_stats_screen import HEART_PARTIAL, HEART_VALUES
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import build, finish, plan
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.layout import LOW_HEALTH_BEEP_OPERAND_ADDRESS
from zora.rom.player_settings import LowHealthBeep, PlayerSettings, written_offsets
from zora.rom.uphill_battle import BEEP_NEVER

pytestmark = pytest.mark.slow

TUNE_0 = 0x605
HEART_WARNING = 0x40
BEEP_FRAMES = 19                    # PRG0's heart warning: 18 frames of script and its closing frame
LOW_HEARTS = 0x20                   # three containers, no full heart: the warning's condition
FULL_HEARTS = 0x22
PARTIAL = 0x80                      # half a heart
WATCHED_FRAMES = 400
SEED = 1


@cache
def finished(beep: LowHealthBeep, flag_string: str = MVP_BASELINE_LEVEL_ENCODING_OFF, on_prg1: bool = False) -> bytes:
    base = prg1() if on_prg1 else remember_repo_base_rom()
    return finish(build(plan(flag_string, SEED), base), base, player_settings=PlayerSettings(low_health_beep=beep))


def beep_starts(emu: Emulator, frames: int) -> list[int]:
    """The frames, counted from now, on which a heart warning starts."""
    starts, before = [], emu[TUNE_0]
    for frame in range(frames):
        emu.run(1)
        if emu[TUNE_0] == HEART_WARNING and before != HEART_WARNING:
            starts.append(frame)
        before = emu[TUNE_0]
    return starts


def low_health(rom: bytes) -> Emulator:
    emu = Emulator(rom)
    emu.new_game()
    emu[HEART_VALUES], emu[HEART_PARTIAL] = LOW_HEARTS, PARTIAL
    return emu


def intervals(starts: list[int]) -> set[int]:
    return {later - earlier for earlier, later in pairwise(starts)}


@pytest.mark.parametrize(("beep", "period"), [(LowHealthBeep.KEPT, BEEP_FRAMES),
                                               (LowHealthBeep.HALF_SPEED, 2 * BEEP_FRAMES)])
def test_the_beep_starts_at_its_rate_and_stops_when_hearts_are_refilled(beep: LowHealthBeep, period: int) -> None:
    emu = low_health(finished(beep))
    starts = beep_starts(emu, WATCHED_FRAMES)
    assert len(starts) >= WATCHED_FRAMES // period - 1 and intervals(starts) == {period}, starts
    emu[HEART_VALUES] = FULL_HEARTS
    assert beep_starts(emu, WATCHED_FRAMES) == []
    assert emu[TUNE_0] != HEART_WARNING
    emu[HEART_VALUES] = LOW_HEARTS
    assert intervals(beep_starts(emu, WATCHED_FRAMES)) == {period}


def test_removed_never_beeps() -> None:
    assert beep_starts(low_health(finished(LowHealthBeep.REMOVED)), WATCHED_FRAMES) == []


def test_hidden_health_silences_half_speed() -> None:
    """FP-HIDE-01 (B55) writes the request's operand alone, after the player settings."""
    rom = finished(LowHealthBeep.HALF_SPEED, B55_ON)
    assert rom[LOW_HEALTH_BEEP_OPERAND_ADDRESS] == BEEP_NEVER
    assert beep_starts(low_health(rom), WATCHED_FRAMES) == []


def test_half_speed_changes_only_the_settings_bytes() -> None:
    kept, half = finished(LowHealthBeep.KEPT), finished(LowHealthBeep.HALF_SPEED)
    changed = {offset for offset, (a, b) in enumerate(zip(kept, half, strict=True)) if a != b}
    assert changed and changed <= written_offsets("low_health_beep")


@needs_both
def test_half_speed_on_prg1() -> None:
    """On PRG1 the routine sits in bank 0's free space after the audio code PRG1 moves."""
    starts = beep_starts(low_health(finished(LowHealthBeep.HALF_SPEED, on_prg1=True)), WATCHED_FRAMES)
    assert intervals(starts) == {2 * BEEP_FRAMES}
