"""Player settings (features-behavior.md FP-SET-01 to FP-SET-04, FP-HOT-01,
FP-RESET-01, FP-BEEP-01, FP-FIX-02; flags-behavior.md FL-SUP-05).

A player setting is not part of the flag string and never changes generation,
the seed, the seed's code (FP-HASH-01) or the level encoding (FP-TOURNEY-01).
apply_player_settings writes them into a FINISHED ROM: after level encoding
and after the seed's code is stamped, outside both. Each setting has one
function, called from apply_player_settings; at the defaults (the value
every corpus ROM carries) a finished ZORA ROM is unchanged.

Select swap, the death-warp mapping, reduce flashing and music off use the
patches assembled in asm/settings/ (docs/player-settings-patches.md);
player_settings_data.py is a verbatim copy of its output, which
tests/test_player_settings_wiring.py keeps equal. Select swap's off choice is
not assembled there: it is PRG0's own code at FP-HOT-01's four sites.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from zora.rom.base_rom import Piece, original_bytes, piece_bytes, piece_length
from zora.rom.code_patch_data import PATCHES
from zora.rom.layout import LEVEL_INFO_ADDRESS, LEVEL_INFO_SIZE, LOW_HEALTH_BEEP_OPERAND_ADDRESS
from zora.rom.player_settings_data import SETTINGS

# NES palette values (FP-SET-02): six bits, and $0D ("blacker than black",
# never used by PRG0, can upset a TV's picture sync) is refused.
PALETTE_SIZE = 0x40
BLACKER_THAN_BLACK = 0x0D

# FP-SET-02: the tunic colour of each ring state, in both copies PRG0 reads:
# the file-select copy (LinkColors) and the pickup copy (LinkColors_CommonCode,
# whose first entry is never read; the slot's value is written there too).
TUNIC_FILE_SELECT_COPY = 0xA297
TUNIC_PICKUP_COPY = 0x6BA5
TUNIC_SLOTS = 3                      # no ring, blue ring, red ring
# FP-SET-03: the heart colour, byte 8 of each of the ten level informations'
# palette records (the overworld's is k = 0).
HEART_COLOUR_OFFSET = 8
LEVEL_INFORMATIONS = 10
# FP-BEEP-01: the operand ORed into Tune0Request ($40 requests the tone).
BEEP_REMOVED, BEEP_KEPT = 0x00, 0x40
# FP-HOT-01's patch: select swap off restores PRG0 at every site of it that
# runs (its slot in bank 2, the item screen's call and heading pointer, and
# the play mode's Select test). Its bank-5 and bank-7 slots stay, unreachable.
HOT_KEY_PATCH = "fp-hot-01"
SELECT_SWAP_OFF_SITES = (0x0B010, 0x140E5, 0x1A040, 0x1EC46)


class PlayerSettingError(ValueError):
    """A player setting outside its choices."""


class SelectSwap(Enum):
    """FP-HOT-01."""
    OFF = "off"                  # PRG0: Select pauses
    SWAP_ONLY = "swap_only"
    TOGGLE = "toggle"


class LowHealthBeep(Enum):
    """FP-BEEP-01."""
    REMOVED = "removed"
    KEPT = "kept"                # PRG0


class DeathWarp(Enum):
    """FP-RESET-01: the combination that ends the game from the item screen."""
    CONTROLLER2_UP_A = "controller2_up_a"          # PRG0
    CONTROLLER1_UP_A = "controller1_up_a"
    CONTROLLER1_UP_SELECT = "controller1_up_select"


class Music(Enum):
    """FP-SET-04."""
    ON = "on"
    OFF = "off"


@dataclass(frozen=True)
class PlayerSettings:
    """The seven settings the MVP offers (FL-SUP-05), at the spec's defaults."""
    select_swap: SelectSwap = SelectSwap.TOGGLE
    low_health_beep: LowHealthBeep = LowHealthBeep.REMOVED
    death_warp: DeathWarp = DeathWarp.CONTROLLER1_UP_A
    reduce_flashing: bool = False
    # green tunic (no ring), blue ring, red ring: PRG0's
    tunic_colours: tuple[int, int, int] = (0x29, 0x32, 0x16)
    heart_colour: int = 0x16                        # PRG0's
    music: Music = Music.ON

    def __post_init__(self) -> None:
        if len(self.tunic_colours) != TUNIC_SLOTS:
            raise PlayerSettingError(f"tunic colours: three values, not {len(self.tunic_colours)}")
        for name, value in (("green tunic", self.tunic_colours[0]), ("blue ring", self.tunic_colours[1]),
                            ("red ring", self.tunic_colours[2]), ("heart colour", self.heart_colour)):
            check_palette_value(name, value)


def check_palette_value(name: str, value: int) -> None:
    """FP-SET-02 and FP-SET-03: $00-$3F, except $0D."""
    if not isinstance(value, int) or not 0 <= value < PALETTE_SIZE:
        raise PlayerSettingError(f"{name}: {value!r} is not an NES palette value ($00-$3F)")
    if value == BLACKER_THAN_BLACK:
        raise PlayerSettingError(f"{name}: $0D is not allowed (blacker than black)")


# The spec's defaults: what a finished ROM gets when the player chooses nothing.
DEFAULT_PLAYER_SETTINGS = PlayerSettings()


def apply_player_settings(rom: bytes, settings: PlayerSettings) -> bytes:
    """A finished ROM with the player settings written; nothing else changes."""
    out = bytearray(rom)
    select_swap(out, settings.select_swap)
    low_health_beep(out, settings.low_health_beep)
    death_warp(out, settings.death_warp)
    reduce_flashing(out, settings.reduce_flashing)
    tunic_colours(out, settings.tunic_colours)
    heart_colour(out, settings.heart_colour)
    music(out, settings.music)
    return bytes(out)


def _write(rom: bytearray, runs: tuple[tuple[int, Piece], ...]) -> None:
    for offset, piece in runs:
        run = piece_bytes(piece)
        rom[offset:offset + len(run)] = run


def _hot_key_extent(site: int) -> int:
    """How many bytes FP-HOT-01 writes from `site` on, without a gap."""
    lengths = {offset: piece_length(piece) for offset, piece in PATCHES[HOT_KEY_PATCH]}
    end = site
    while end in lengths:
        end += lengths[end]
    return end - site


def select_swap_off_runs() -> tuple[tuple[int, bytes], ...]:
    """PRG0's bytes at FP-HOT-01's running sites, read from the player's ROM."""
    return tuple((site, original_bytes(site, _hot_key_extent(site))) for site in SELECT_SWAP_OFF_SITES)


def select_swap(rom: bytearray, choice: SelectSwap) -> None:
    """FP-HOT-01: off (PRG0), swap-only or toggle."""
    if choice is SelectSwap.OFF:
        _write(rom, select_swap_off_runs())
    else:
        _write(rom, SETTINGS["select_swap"][choice.value])


def low_health_beep(rom: bytearray, choice: LowHealthBeep) -> None:
    """FP-BEEP-01: the tone request's operand."""
    rom[LOW_HEALTH_BEEP_OPERAND_ADDRESS] = BEEP_REMOVED if choice is LowHealthBeep.REMOVED else BEEP_KEPT


def death_warp(rom: bytearray, choice: DeathWarp) -> None:
    """FP-RESET-01: the death-warp combination."""
    _write(rom, SETTINGS["death_warp"][choice.value])


def reduce_flashing(rom: bytearray, on: bool) -> None:
    """FP-FIX-02's reduce-flashing setting: the four flashes."""
    _write(rom, SETTINGS["reduce_flashing"]["on" if on else "off"])


def tunic_colours(rom: bytearray, colours: tuple[int, int, int]) -> None:
    """FP-SET-02: each slot's value in both copies."""
    for copy in (TUNIC_FILE_SELECT_COPY, TUNIC_PICKUP_COPY):
        rom[copy:copy + len(colours)] = bytes(colours)


def heart_colour(rom: bytearray, colour: int) -> None:
    """FP-SET-03: all ten level informations' heart colour."""
    for level_information in range(LEVEL_INFORMATIONS):
        rom[LEVEL_INFO_ADDRESS + level_information * LEVEL_INFO_SIZE + HEART_COLOUR_OFFSET] = colour


def music(rom: bytearray, choice: Music) -> None:
    """FP-SET-04: on, or the three area songs never start."""
    _write(rom, SETTINGS["music"][choice.value])


def written_offsets(settings_field: str) -> set[int]:
    """Every file offset a setting's function may write, whatever its choice."""
    if settings_field == "select_swap":
        runs = [*select_swap_off_runs(), *(run for runs in SETTINGS["select_swap"].values() for run in runs)]
    elif settings_field == "low_health_beep":
        return {LOW_HEALTH_BEEP_OPERAND_ADDRESS}
    elif settings_field == "tunic_colours":
        return {copy + slot for copy in (TUNIC_FILE_SELECT_COPY, TUNIC_PICKUP_COPY) for slot in range(TUNIC_SLOTS)}
    elif settings_field == "heart_colour":
        return {LEVEL_INFO_ADDRESS + k * LEVEL_INFO_SIZE + HEART_COLOUR_OFFSET for k in range(LEVEL_INFORMATIONS)}
    else:
        runs = [run for runs in SETTINGS[settings_field].values() for run in runs]
    return {offset + i for offset, run in runs for i in range(piece_length(run))}


SETTING_CHOICES: dict[str, type[Enum]] = {"select_swap": SelectSwap, "low_health_beep": LowHealthBeep,
                                          "death_warp": DeathWarp, "music": Music}
SWITCH_WORDS = {"off": False, "on": True}


def parse_player_settings(pairs: list[str]) -> PlayerSettings:
    """Command-line settings, each `name=value` with PlayerSettings' field names: a choice by
    its value (music=off), reduce_flashing=on, heart_colour=0x21, tunic_colours=0x29,0x32,0x16."""
    chosen: dict[str, object] = {}
    for pair in pairs:
        name, _, text = pair.partition("=")
        try:
            if name in SETTING_CHOICES:
                chosen[name] = SETTING_CHOICES[name](text)
            elif name == "reduce_flashing":
                chosen[name] = SWITCH_WORDS[text]
            elif name == "heart_colour":
                chosen[name] = int(text, 0)
            elif name == "tunic_colours":
                chosen[name] = tuple(int(value, 0) for value in text.split(","))
            else:
                raise PlayerSettingError(f"unknown player setting {name!r}")
        except (KeyError, ValueError) as exc:
            if isinstance(exc, PlayerSettingError):
                raise
            raise PlayerSettingError(f"{pair!r}: not a choice of {name}") from exc
    return PlayerSettings(**chosen)  # type: ignore[arg-type]
