"""The visible effects of the reviews 77-78 player settings, in the emulator (cynes, tests/emulator.py),
on finished ROMs (CP-5, a seed number on the title screen for Random to draw from):

- a Link sprite set (FP-LINK-02) is what Link is drawn with in play, on the file-select screen and
  in the title story, and only Link changes;
- Random tunic and heart colors (FP-SET-02, FP-SET-03) reach the loaded palette as drawn;
- a Random level word (FP-LEVEL-01) is the status bar's label in level 1;
- a Random low-health beep (FP-BEEP-01) beeps exactly when it resolved to kept."""
from functools import cache

import numpy as np
import pytest

from tests.emulator import Button, Emulator
from tests.test_half_speed_beep_emulator import WATCHED_FRAMES, beep_starts, low_health
from tests.test_level_word import BLANK, LABEL_COLUMN, LABEL_ROW, ROW_TILES
from tests.test_link_sprite import TEST_SET, with_set
from tests.test_player_settings_wiring import HEART_ENTRY, LEVEL_INFO, TUNIC_ENTRY
from tests.test_ring_color import enter_level_1
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.layout import FP_LEVEL_DASH_TILE
from zora.rom.player_settings import (
    RANDOM_COLOR,
    RANDOM_LEVEL_WORD,
    LowHealthBeep,
    PlayerSettings,
    level_label,
    resolved_player_settings,
)
from zora.rom.text_encoding import BYTE_TO_CHAR

pytestmark = [pytest.mark.slow,
              pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")]

CP5 = MVP_BASELINE_LEVEL_ENCODING_OFF
SEED = 1
LINK_SIZE = 16                     # Link is one 16x16 object
TITLE_STORY_FRAMES = 6000          # the story reaches Link at about frame 4,380 on PRG0
RANDOM_COLORS = PlayerSettings(tunic_colors=(RANDOM_COLOR,) * 3, heart_color=RANDOM_COLOR)


DEFAULTS = PlayerSettings()


@cache
def finished(seed: int, settings: PlayerSettings = DEFAULTS) -> bytes:
    return generate_rom(CP5, seed, remember_repo_base_rom(), settings).rom


def differing_box(first: np.ndarray, second: np.ndarray) -> tuple[int, int, int, int] | None:
    """The smallest box (left, top, width, height) holding every pixel that differs."""
    ys, xs = np.nonzero(np.any(first != second, axis=-1))
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


def pair(settings: PlayerSettings) -> tuple[Emulator, Emulator]:
    """The same seed with PRG0's Link and with `settings`."""
    return Emulator(finished(SEED)), Emulator(finished(SEED, settings))


def test_link_is_drawn_from_the_set_in_play() -> None:
    link, styled = pair(with_set())
    for emu in (link, styled):
        emu.new_game()
        emu.run(30, Button.UP)
    box = differing_box(link.last_frame, styled.last_frame)
    assert box is not None and box[2] <= LINK_SIZE and box[3] <= LINK_SIZE
    assert TEST_SET.tiles[:28 * 16] in styled.pattern_tables()


def test_the_file_select_screen_draws_the_set() -> None:
    """Only the column where the file-select screen draws Link differs."""
    link, styled = pair(with_set())
    for emu in (link, styled):
        emu.boot_to_file_select()
        emu.register_file()
        emu.run(30)
    box = differing_box(link.last_frame, styled.last_frame)
    assert box is not None and box[2] <= LINK_SIZE


def test_the_title_story_draws_the_set() -> None:
    link, styled = pair(with_set())
    for _ in range(TITLE_STORY_FRAMES // 30):
        link.run(30)
        styled.run(30)
        if differing_box(link.last_frame, styled.last_frame) is not None:
            return
    raise AssertionError("the title story never drew Link differently")


@pytest.mark.parametrize("seed", [1, 2])
def test_random_colors_reach_the_loaded_palette(seed: int) -> None:
    drawn = resolved_player_settings(RANDOM_COLORS, seed)
    emu = Emulator(finished(seed, RANDOM_COLORS))
    emu.new_game()
    emu.run(30, Button.UP)
    assert (emu[LEVEL_INFO + TUNIC_ENTRY], emu[LEVEL_INFO + HEART_ENTRY]) == (drawn.tunic_colors[0], drawn.heart_color)


def test_a_random_level_word_is_the_label_in_level_1() -> None:
    settings = PlayerSettings(level_word=RANDOM_LEVEL_WORD)
    word = resolved_player_settings(settings, SEED).level_word
    emu = Emulator(finished(SEED, settings))
    emu.new_game()
    enter_level_1(emu)
    row = emu.nametable(LABEL_ROW, ROW_TILES)
    text = "".join("-" if tile == FP_LEVEL_DASH_TILE else BYTE_TO_CHAR.get(tile, "?") for tile in row)
    assert text.startswith(BLANK * LABEL_COLUMN + level_label(word))


def test_a_random_beep_beeps_exactly_when_it_resolved_kept() -> None:
    settings = PlayerSettings(low_health_beep=LowHealthBeep.RANDOM)
    resolved = {seed: resolved_player_settings(settings, seed).low_health_beep for seed in range(1, 21)}
    for choice in (LowHealthBeep.KEPT, LowHealthBeep.REMOVED):
        seed = next(seed for seed, drawn in resolved.items() if drawn is choice)
        starts = beep_starts(low_health(finished(seed, settings)), WATCHED_FRAMES)
        assert bool(starts) is (choice is LowHealthBeep.KEPT), choice
