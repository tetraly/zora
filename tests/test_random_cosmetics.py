"""Random player settings (features-behavior.md FP-SET-01's rule for Random choices, FP-BEEP-01,
FP-SET-02, FP-SET-03, FP-LEVEL-01; reviews 77-78): the low-health beep, each tunic slot, the heart
color and the level label's word may be Random, resolved per seed from the seed number alone
(zora/rom/player_settings.py resolved_player_settings). A Random choice writes exactly what the
choice it resolves to writes, the same seed always gives the same, and generation, the seed's code
and the encoded level data never change."""
import re
from collections import Counter
from dataclasses import replace
from functools import cache
from pathlib import Path

import pytest

from tests.needs import needs_base_rom
from zora import archipelago
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.code_patches import seed_code
from zora.rom.player_settings import (
    BEEP_KEPT,
    BEEP_REMOVED,
    HEART_RANDOM_COLORS,
    LEVEL_WORD_CHOICES,
    RANDOM_COLOR,
    RANDOM_LEVEL_WORD,
    TUNIC_RANDOM_COLORS,
    PALETTE_SIZE,
    CharacterColors,
    LowHealthBeep,
    PlayerSettingError,
    PlayerSettings,
    apply_player_settings,
    parse_player_settings,
    player_settings_from_page,
    resolved_player_settings,
    title_seed_number,
    written_offsets,
)

SEEDS = range(1, 1001)
ALL_RANDOM = PlayerSettings(low_health_beep=LowHealthBeep.RANDOM, tunic_colors=(RANDOM_COLOR,) * 3,
                            heart_color=RANDOM_COLOR, level_word=RANDOM_LEVEL_WORD)
RANDOM_FIELDS = ("low_health_beep", "tunic_colors", "heart_color", "level_word")
CP5 = MVP_BASELINE_LEVEL_ENCODING_OFF          # the spec's CP-5 string


@cache
def finished(seed: int) -> bytes:
    return generate_rom(CP5, seed, remember_repo_base_rom()).rom


def test_the_lists() -> None:
    """A tunic's Random: each color the page's palette shows, once (the owner, 2026-10-24: any
    color, the original tunics' too); the heart's, the spec's seven."""
    page = (Path(__file__).resolve().parent.parent / "web" / "zora-web.js").read_text()
    listed = re.search(r"^const NES_PALETTE = \[(.*?)\];", page, re.MULTILINE | re.DOTALL)
    assert listed
    palette = re.findall(r'"(#[0-9a-f]{6})"', listed.group(1))
    assert len(palette) == PALETTE_SIZE
    looks = {palette[color] for color in range(PALETTE_SIZE)}
    assert len(TUNIC_RANDOM_COLORS) == len(looks) == 54
    assert {palette[color] for color in TUNIC_RANDOM_COLORS} == looks          # every look, each once
    assert {0x29, 0x32, 0x16, 0x0F, 0x30} <= set(TUNIC_RANDOM_COLORS)
    assert HEART_RANDOM_COLORS == (0x29, 0x22, 0x16, 0x0C, 0x1A, 0x03, 0x17)
    assert 0x0D not in TUNIC_RANDOM_COLORS + HEART_RANDOM_COLORS


def test_every_random_choice_is_drawn_from_its_list_with_each_value_seen() -> None:
    drawn = [resolved_player_settings(ALL_RANDOM, seed) for seed in SEEDS]
    for slot in range(3):
        assert {settings.tunic_colors[slot] for settings in drawn} == set(TUNIC_RANDOM_COLORS), slot
    assert all(len(set(settings.tunic_colors)) == 3 for settings in drawn)          # pairwise different
    assert {settings.heart_color for settings in drawn} == set(HEART_RANDOM_COLORS)
    assert {settings.level_word for settings in drawn} == set(LEVEL_WORD_CHOICES)
    beeps = Counter(settings.low_health_beep for settings in drawn)
    assert set(beeps) == {LowHealthBeep.REMOVED, LowHealthBeep.KEPT} and min(beeps.values()) > 400


def test_a_later_random_slot_never_repeats_an_earlier_slot() -> None:
    """FP-SET-02: slot 1 fixed at $32, slots 2 and 3 Random: never $32, and never each other's."""
    fixed_first = PlayerSettings(tunic_colors=(0x32, RANDOM_COLOR, RANDOM_COLOR))
    for seed in SEEDS:
        colors = resolved_player_settings(fixed_first, seed).tunic_colors
        assert colors[0] == 0x32 and 0x32 not in colors[1:] and colors[1] != colors[2]
    fixed_last = PlayerSettings(tunic_colors=(RANDOM_COLOR, 0x29, 0x16))     # a later fixed slot may repeat
    assert {resolved_player_settings(fixed_last, seed).tunic_colors[0] for seed in SEEDS} == set(TUNIC_RANDOM_COLORS)


def test_the_same_seed_always_resolves_the_same() -> None:
    assert [resolved_player_settings(ALL_RANDOM, seed) for seed in range(1, 6)] == \
        [resolved_player_settings(ALL_RANDOM, seed) for seed in range(1, 6)]


def test_fixed_choices_pass_through() -> None:
    fixed = PlayerSettings(tunic_colors=(0x24, 0x32, 0x16), heart_color=0x21, level_word="LAIR")
    assert resolved_player_settings(fixed, 7) == fixed


@needs_base_rom
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_random_writes_what_its_choice_writes(seed: int) -> None:
    """The finished ROM's title screen gives the seed number; Random writes the bytes of the choice it
    resolves to, and nothing outside the settings' own bytes changes."""
    rom = finished(seed)
    assert title_seed_number(rom) == seed
    chosen = resolved_player_settings(ALL_RANDOM, seed)
    random_rom = apply_player_settings(rom, ALL_RANDOM)
    assert random_rom == apply_player_settings(rom, chosen)
    own = set().union(*(written_offsets(field) for field in RANDOM_FIELDS))
    default = apply_player_settings(rom, PlayerSettings())
    assert {i for i, (a, b) in enumerate(zip(default, random_rom, strict=True)) if a != b} <= own


@needs_base_rom
def test_random_never_changes_generation_or_the_code() -> None:
    """FP-SET-01: the same flag string and seed give the same ROM twice, and the seed's code is the
    default's; against the default settings only the settings' own bytes differ."""
    base = remember_repo_base_rom()
    first = generate_rom(CP5, 4, base, ALL_RANDOM)
    assert first.rom == generate_rom(CP5, 4, base, ALL_RANDOM).rom
    default = generate_rom(CP5, 4, base)
    assert first.code == default.code == seed_code(first.rom)
    own = set().union(*(written_offsets(field) for field in RANDOM_FIELDS))
    assert {i for i, (a, b) in enumerate(zip(default.rom, first.rom, strict=True)) if a != b} <= own


@needs_base_rom
def test_the_beep_operand_is_one_of_the_two() -> None:
    from zora.rom.layout import LOW_HEALTH_BEEP_OPERAND_ADDRESS
    operands = {apply_player_settings(finished(seed), PlayerSettings(low_health_beep=LowHealthBeep.RANDOM))
                [LOW_HEALTH_BEEP_OPERAND_ADDRESS] for seed in (1, 2, 3)}
    assert operands <= {BEEP_REMOVED, BEEP_KEPT}


@needs_base_rom
def test_random_needs_a_seed_number() -> None:
    """A ROM whose title screen shows no seed number (the original game) has nothing to draw from."""
    with pytest.raises(PlayerSettingError, match="no seed number"):
        apply_player_settings(remember_repo_base_rom(), PlayerSettings(heart_color=RANDOM_COLOR))


def test_the_page_the_command_line_and_archipelago_name_random() -> None:
    # Random tunics are tunic colors of the player's own, so settings that do not name Playable
    # character's colors read as My own (dd2d7e7); without a sprite set that writes nothing more
    named = replace(ALL_RANDOM, character_colors=CharacterColors.MINE)
    page = {"lowHealthBeep": "random", "greenTunic": RANDOM_COLOR, "blueRingTunic": RANDOM_COLOR,
            "redRingTunic": RANDOM_COLOR, "heart": RANDOM_COLOR, "levelWord": RANDOM_LEVEL_WORD}
    assert player_settings_from_page(page) == named
    assert parse_player_settings(["low_health_beep=random", "tunic_colors=random,random,random", "heart_color=random",
                                  "level_word=random"]) == named
    yaml = {"low_health_beep": "random_choice", "green_tunic": "random_color", "blue_ring_tunic": "random_color",
            "red_ring_tunic": "random_color", "hearts": "random_color", "level_word": "random_word"}
    assert player_settings_from_page(archipelago.page_player_settings(yaml)) == named


def test_the_word_random_is_a_word_and_random_is_lowercase() -> None:
    """A typed "random" is the six-letter word RANDOM (the page keeps words in capitals); only the
    lowercase value is the Random choice."""
    assert player_settings_from_page({"levelWord": "random "}).level_word == "RANDOM"
    assert player_settings_from_page({"levelWord": RANDOM_LEVEL_WORD}).level_word == RANDOM_LEVEL_WORD
    assert replace(PlayerSettings(), level_word="RANDOM").level_word == "RANDOM"
