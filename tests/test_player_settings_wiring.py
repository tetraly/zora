"""The player settings wired into generation (zora/rom/player_settings.py;
features-behavior.md FP-SET-01 to FP-SET-04, FL-SUP-05).

tests/test_player_settings.py (the patches' own tests, in the emulator) writes
the assembled bytes with asm/settings/build.py; the wired path writes the same
bytes, which test_wired_path_writes_the_assembled_bytes checks, so those
emulator results hold for generate_rom's ROMs.
"""
import importlib.util
from dataclasses import fields, replace
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.emulator import Button, Emulator
from tests.test_feature_patches import BOOMERANG_SLOT, HOT_KEY_LABEL, INVENTORY_HEADING
from tests.test_player_settings import _armed_start, _select_presses
from zora_web.api import player_settings_from_page
from zora.flags.presets import MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, generate_world, plan
from zora.rom import level_encoding
from zora.rom.base_rom import piece_bytes, verify_base_rom
from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH, seed_code
from zora.rom.layout import LEVEL_LABEL_RECORD, LEVEL_LABEL_RECORD_SIZE, LOW_HEALTH_BEEP_OPERAND_ADDRESS
from zora.rom.link_art import offered_sprite_sets
from zora.rom.link_sprite import SpriteSet
from zora.rom.player_settings import (
    CharacterColors, DeathWarp, LinkSprite, LowHealthBeep, Music, PlayerSettingError, PlayerSettings, SelectSwap,
    apply_player_settings, written_offsets,
)
from zora.rom.serialize.rom_file import serialize_to_rom

REPO = Path(__file__).resolve().parent.parent
SEEDS = (1, 2, 3)
VIVID = 0x24
LEVEL_INFO = 0x6B7E                  # WRAM: the loaded level information
HEART_ENTRY, TUNIC_ENTRY = 8, 20     # its palette record's background 1.1 and sprite 0.1
# Every non-default choice of every setting
NON_DEFAULTS: dict[str, tuple[Any, ...]] = {
    "select_swap": (SelectSwap.OFF, SelectSwap.SWAP_ONLY),
    "low_health_beep": (LowHealthBeep.KEPT, LowHealthBeep.HALF_SPEED, LowHealthBeep.QUARTER_SPEED),
    "death_warp": (DeathWarp.CONTROLLER2_UP_A, DeathWarp.CONTROLLER1_UP_SELECT),
    "reduce_flashing": (True,),
    "tunic_colors": ((VIVID, 0x32, 0x16), (0x29, VIVID, 0x16), (0x29, 0x32, VIVID)),
    "heart_color": (VIVID,),
    "music": (Music.OFF,),
    "level_word": ("DEN", "PALACE"),
    "boss_sound_word": ("MEOW", "RANDOM", "HI !"),
    "link_sprite": (LinkSprite.SET,),
    "link_colors": ((VIVID, 0x17), (0x27, VIVID)),
    "link_sprite_swap": (True,),
}
# A Link sprite set for the cases (FP-LINK-02's Check: 640 bytes of any content), given with the
# Link sprite's choice: the set field alone writes nothing. Playable character's colors writes only
# with a set that has colors of its own (tests/test_character_colors.py), which the test set has not.
TEST_SPRITE_SET = SpriteSet("Test set", "ZORA tests", "made for this test", bytes(range(256)) * 2 + bytes(128))
WITH_ANOTHER = frozenset({"sprite_set", "character_colors"})
# Randomized music (docs/design/music-settings.md): applied after the player settings
# (zora.rom.music.randomize), so here a random Music value only chooses the statistics screen's music
# build and the switch beside it writes nothing (test_randomized_music_chooses_only_the_statistics_screen).
APPLIED_AFTER = frozenset({"music_streaming_safe_only"})
# Graphics theme (Halloween Mode): its tiles go in before generation, so it applies only when a ROM is
# generated (apply_player_settings refuses it) and has no apply-afterwards cases here;
# tests/test_graphics_theme.py checks it on generated ROMs.
GENERATED_ONLY = frozenset({"graphics_theme"})
# What every ROM gets besides the settings: the statistics screen (FP-STATS-01; a setting up to 2.0
# beta 6), left out only by the co-op hook (write_player_settings' coop).
STATISTICS_SCREEN = "statistics_screen"
CASES = [(name, value) for name, values in NON_DEFAULTS.items() for value in values]
CASE_IDS = [f"{name}={getattr(value, 'value', value)}" for name, value in CASES]


def _module(name: str, path: Path) -> ModuleType:
    if not path.exists():
        # asm/ is left out of releases (release/allowlist.txt): what needs it skips there.
        pytest.skip(f"{path.relative_to(REPO)} is not in this tree", allow_module_level=True)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def base() -> bytes:
    return verify_base_rom().read_bytes()


@cache
def unset(flags: str, seed: int) -> bytes:
    """The finished ROM before any player setting is written."""
    chosen = plan(flags, seed)
    world, _ = generate_world(chosen, base())
    return serialize_to_rom(world, base(), config=chosen.config)


def test_data_is_the_assembled_copy() -> None:
    """zora/rom/player_settings_data.py is asm/settings/'s output, byte for byte."""
    assert (REPO / "zora/rom/player_settings_data.py").read_bytes() == \
        (REPO / "asm/settings/player_settings_data.py").read_bytes()


def test_every_setting_has_its_defaults_and_one_function() -> None:
    assert ({field.name for field in fields(PlayerSettings)} - APPLIED_AFTER - WITH_ANOTHER - GENERATED_ONLY
            == set(NON_DEFAULTS))


def test_randomized_music_chooses_only_the_statistics_screen() -> None:
    rom = apply_player_settings(unset(MVP_BASELINE_LEVEL_ENCODING_OFF, SEEDS[0]), PlayerSettings())
    for music in (Music.RANDOM_STANDARD, Music.RANDOM_LOCAL):
        changed = apply_player_settings(rom, PlayerSettings(music=music))
        differing = {i for i, (a, b) in enumerate(zip(rom, changed, strict=True)) if a != b}
        assert differing and differing <= written_offsets(STATISTICS_SCREEN)
    switches = PlayerSettings(music_streaming_safe_only=False)
    assert {name for name in APPLIED_AFTER if getattr(switches, name) != getattr(PlayerSettings(), name)} == APPLIED_AFTER
    assert apply_player_settings(rom, switches) == rom


# The defaults: with the co-op hook, a finished ROM as serialized, before any setting is written.
UNSET = PlayerSettings()


@pytest.mark.parametrize("seed", SEEDS)
def test_defaults_leave_finished_roms_byte_identical(seed: int) -> None:
    """The defaults change only the statistics screen's bytes, which every ROM has; with the co-op
    hook they change none."""
    for flags in (MVP_BASELINE_LEVEL_ENCODING_OFF, *((MVP_BASELINE,) if level_encoding.is_available() else ())):
        rom = unset(flags, seed)
        assert apply_player_settings(rom, UNSET, coop=True) == rom
        styled = generate_rom(flags, seed, base()).rom
        assert styled == generate_rom(flags, seed, base(), UNSET).rom == apply_player_settings(rom, UNSET)
        differing = {i for i, (a, b) in enumerate(zip(rom, styled, strict=True)) if a != b}
        assert differing and differing <= written_offsets(STATISTICS_SCREEN)


def beside(name: str) -> PlayerSettings:
    """What a setting's case starts from: the defaults, with the test set for the Link sprite's choice,
    and the Old Man's set chosen for the swap (refused without a person set)."""
    if name == "link_sprite":
        return replace(PlayerSettings(), sprite_set=TEST_SPRITE_SET)
    if name == "link_sprite_swap":
        return replace(PlayerSettings(), link_sprite=LinkSprite.SET, sprite_set=offered_sprite_sets()["old-man"])
    return PlayerSettings()


def one_setting(name: str, value: Any) -> PlayerSettings:
    """What a setting's case starts from with that one setting changed."""
    return replace(beside(name), **{name: value})


@pytest.mark.parametrize(("name", "value"), CASES, ids=CASE_IDS)
def test_each_setting_changes_only_its_own_bytes(name: str, value: Any) -> None:
    rom = apply_player_settings(unset(MVP_BASELINE_LEVEL_ENCODING_OFF, SEEDS[0]), beside(name))
    changed = apply_player_settings(rom, one_setting(name, value))
    differing = {i for i, (a, b) in enumerate(zip(rom, changed, strict=True)) if a != b}
    assert differing and differing <= written_offsets(name)
    for other in NON_DEFAULTS:
        if other != name:
            assert not differing & written_offsets(other), other


def test_settings_never_share_a_byte() -> None:
    for first in (*NON_DEFAULTS, STATISTICS_SCREEN):
        for second in (*NON_DEFAULTS, STATISTICS_SCREEN):
            if first < second:
                assert not written_offsets(first) & written_offsets(second), (first, second)


@pytest.mark.parametrize(("name", "value"), CASES, ids=CASE_IDS)
def test_no_setting_changes_the_code_or_the_encoded_range(name: str, value: Any) -> None:
    """FP-SET-01, FP-HASH-01, FP-TOURNEY-01: the seed's code and, with level encoding on, every
    byte the encoding may change are the same whatever the settings."""
    if not level_encoding.is_available():
        pytest.skip("needs the encoder")
    rom = unset(MVP_BASELINE, SEEDS[0])
    changed = apply_player_settings(rom, one_setting(name, value))
    assert seed_code(changed) == seed_code(rom)
    protected = [(SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH), *level_encoding.changed_ranges_allowed()]
    for start, end in protected:
        assert changed[start:end] == rom[start:end]


def test_generate_rom_applies_the_settings_and_keeps_the_code() -> None:
    settings = PlayerSettings(music=Music.OFF, heart_color=VIVID)
    plain = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, base())
    styled = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, base(), settings)
    assert styled.rom == apply_player_settings(plain.rom, settings) != plain.rom
    assert styled.code == plain.code


@pytest.mark.parametrize("value", [0x0D, 0x41, -1, 0x100])      # 0x40 is Random (RANDOM_COLOR)
def test_palette_values_outside_the_choices_are_refused(value: int) -> None:
    with pytest.raises(PlayerSettingError):
        PlayerSettings(heart_color=value)
    with pytest.raises(PlayerSettingError):
        PlayerSettings(tunic_colors=(0x29, value, 0x16))
    assert PlayerSettings(heart_color=0x0F).heart_color == 0x0F      # every other black is allowed


def test_the_pages_settings_map_to_player_settings() -> None:
    page = {"selectButton": "swap", "lowHealthBeep": "kept", "deathWarp": "p1-up-select", "reduceFlashing": "on",
            "music": "off", "greenTunic": 0x21, "blueRingTunic": 0x22, "redRingTunic": 0x23, "heart": 0x24,
            "levelWord": " palace ", "bossSoundWord": "meow", "statisticsScreen": "on"}
    # statisticsScreen: retired (every ROM has the screen), read by no one; tunic colors of its own and no
    # characterColors (a page saved before it): My own
    assert player_settings_from_page(page) == PlayerSettings(
        SelectSwap.SWAP_ONLY, LowHealthBeep.KEPT, DeathWarp.CONTROLLER1_UP_SELECT, True, (0x21, 0x22, 0x23),
        0x24, Music.OFF, "PALACE", "MEOW", character_colors=CharacterColors.MINE)
    assert player_settings_from_page({**page, "characterColors": "set"}).character_colors is CharacterColors.SET
    defaults = {"selectButton": "toggle", "lowHealthBeep": "removed", "deathWarp": "p1-up-a",
                "reduceFlashing": "off", "music": "on", "greenTunic": 0x29, "blueRingTunic": 0x32,
                "redRingTunic": 0x16, "heart": 0x16, "statisticsScreen": "off"}
    assert player_settings_from_page(defaults) == PlayerSettings() == player_settings_from_page({})
    assert player_settings_from_page({"selectButton": "off"}).select_swap is SelectSwap.OFF
    for bad in ({"music": "loud"}, {"heart": 0x0D}, {"deathWarp": 3}, {"levelWord": "DUNGEONS"},
                {"levelWord": 7}, {"levelWord": ""}, {"bossSoundWord": "MOO"}, {"bossSoundWord": "A~BC"}):
        with pytest.raises(PlayerSettingError):
            player_settings_from_page(bad)


# FP-LEVEL-02's label (asm/settings/build.py level_label) is no field of its own: the level word
# picks it, "long" for a seven-character label text (d579ad5). The word also goes into the label's
# record (the patch's own is a placeholder) and the hints, so a long word is compared on the
# patch's runs, its record aside; the default word gives the short label's ROM exactly.
LEVEL_LABEL = "level_label"
LABEL_WORDS = {"short": PlayerSettings().level_word, "long": "DUNGEON"}


def _check_level_label(rom: bytes, choice: str, assembled: bytes | bytearray,
                       runs: tuple[tuple[int, Any], ...]) -> None:
    wired = apply_player_settings(rom, replace(UNSET, level_word=LABEL_WORDS[choice]), coop=True)
    if choice == "short":
        assert wired == bytes(assembled), (LEVEL_LABEL, choice)
        return
    record = range(LEVEL_LABEL_RECORD, LEVEL_LABEL_RECORD + LEVEL_LABEL_RECORD_SIZE)
    offsets = [offset + i for offset, piece in runs for i in range(len(piece_bytes(piece)))]
    assert [hex(at) for at in offsets if at not in record and wired[at] != assembled[at]] == [], (LEVEL_LABEL, choice)


@pytest.mark.parametrize("seed", SEEDS)
def test_wired_path_writes_the_assembled_bytes(seed: int) -> None:
    """For every choice asm/settings/ assembles, the wired path gives the same ROM as its own
    build.apply_settings, so tests/test_player_settings.py's emulator results hold."""
    build = _module("player_settings_build", REPO / "asm" / "settings" / "build.py")
    data = build.load_data()
    rom = unset(MVP_BASELINE_LEVEL_ENCODING_OFF, seed)
    fields_of: dict[str, type[SelectSwap | LowHealthBeep | DeathWarp | Music]] = {
        "select_swap": SelectSwap, "low_health_beep": LowHealthBeep, "death_warp": DeathWarp, "music": Music}
    for name, choices in data.SETTINGS.items():
        for choice in choices:
            if name == STATISTICS_SCREEN and choice == "lozft2":
                # lozft built from source writes it over the music build (lozft.with_lozft2_statistics)
                from zora.rom.base_rom import player_rom_of, remember_repo_base_rom
                from zora.rom.music.lozft import with_lozft2_statistics
                music = apply_player_settings(rom, replace(UNSET, music=Music.RANDOM_STANDARD))
                lozft2 = with_lozft2_statistics(music, player_rom_of(remember_repo_base_rom()))
                assert lozft2 == bytes(build.apply_settings(music, {name: choice}, data.SETTINGS)), (name, choice)
                continue
            if name == STATISTICS_SCREEN:           # always on; off only through the co-op hook
                # the music build with Randomize music (docs/music.md)
                settings = replace(UNSET, music=Music.RANDOM_STANDARD) if choice == "music" else UNSET
                wired = apply_player_settings(rom, settings, coop=choice == "off")
                assert wired == bytes(build.apply_settings(rom, {name: choice}, data.SETTINGS)), (name, choice)
                continue
            if name == LEVEL_LABEL:
                _check_level_label(rom, choice, build.apply_settings(rom, {name: choice}, data.SETTINGS),
                                   data.SETTINGS[name][choice])
                continue
            value: Any = (choice == "on") if name == "reduce_flashing" else fields_of[name](choice)
            # the build writes this setting alone: the co-op hook keeps the screen out of the wired ROM
            wired = apply_player_settings(rom, replace(UNSET, **{name: value}), coop=True)
            assembled = bytearray(build.apply_settings(rom, {name: choice}, data.SETTINGS))
            if name == "low_health_beep":           # the request's operand is data, not assembled
                assembled[LOW_HEALTH_BEEP_OPERAND_ADDRESS] = wired[LOW_HEALTH_BEEP_OPERAND_ADDRESS]
                assert wired[LOW_HEALTH_BEEP_OPERAND_ADDRESS] == (0x00 if choice == "removed" else 0x40)
            assert wired == bytes(assembled), (name, choice)


@pytest.mark.slow
def test_select_swap_off_is_prg0s_pause() -> None:
    """FP-HOT-01 off (not assembled in asm/settings): Select pauses and unpauses as in PRG0, and
    the item screen draws PRG0's heading. Control: PRG0 itself."""
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEEDS[0], base(),
                       PlayerSettings(select_swap=SelectSwap.OFF)).rom
    off = _armed_start(rom)
    assert _select_presses(off, 2) == _select_presses(_armed_start(base()), 2) == \
        [(BOOMERANG_SLOT, 1), (BOOMERANG_SLOT, 0)]
    off = _armed_start(rom)
    off.open_item_screen()
    assert off.nametable(*HOT_KEY_LABEL) == INVENTORY_HEADING


@pytest.mark.slow
def test_colors_reach_the_loaded_palette() -> None:
    """FP-SET-02 and FP-SET-03: in play, the loaded level information's palette (WRAM
    LevelInfo, $6B7E) holds the green tunic's value (entry +20, copied in on every load) and the
    heart color (entry +8)."""
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEEDS[0], base(),
                       PlayerSettings(tunic_colors=(VIVID, 0x32, 0x16), heart_color=0x21)).rom
    emu = Emulator(rom)
    emu.new_game()
    emu.run(30, Button.UP)
    assert (emu[LEVEL_INFO + TUNIC_ENTRY], emu[LEVEL_INFO + HEART_ENTRY]) == (VIVID, 0x21)
    control = Emulator(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEEDS[0], base()).rom)
    control.new_game()
    control.run(30, Button.UP)
    assert (control[LEVEL_INFO + TUNIC_ENTRY], control[LEVEL_INFO + HEART_ENTRY]) == (0x29, 0x16)


def test_command_line_settings() -> None:
    from zora.rom.player_settings import parse_player_settings
    assert parse_player_settings([]) == PlayerSettings()
    assert parse_player_settings(["select_swap=off", "music=off", "reduce_flashing=on", "heart_color=0x21",
                                  "tunic_colors=0x24,0x32,0x16", "death_warp=controller2_up_a", "level_word=lair",
                                  "boss_sound_word=random", "statistics_screen=on"]) == \
        PlayerSettings(SelectSwap.OFF, LowHealthBeep.REMOVED, DeathWarp.CONTROLLER2_UP_A, True,
                       (0x24, 0x32, 0x16), 0x21, Music.OFF, "LAIR", "RANDOM", character_colors=CharacterColors.MINE)
    # a tunic or Link color of the player's own means My own unless character_colors says otherwise
    assert parse_player_settings(["link_colors=0x36,0x0F"]) == PlayerSettings(
        link_colors=(0x36, 0x0F), character_colors=CharacterColors.MINE)
    assert parse_player_settings(["tunic_colors=0x24,0x32,0x16", "character_colors=set"]).character_colors \
        is CharacterColors.SET
    # the retired statistics_screen is ignored, whatever its value
    assert parse_player_settings(["statistics_screen=yes"]) == PlayerSettings()
    for bad in (["music=loud"], ["heart_color=0x0D"], ["volume=11"], ["reduce_flashing=maybe"],
                ["level_word=FORTRESS"], ["level_word=A~B"], ["boss_sound_word=GROWL"], ["character_colors=theirs"]):
        with pytest.raises(PlayerSettingError):
            parse_player_settings(bad)
