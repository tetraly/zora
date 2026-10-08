"""The stable public interface of the zora package for the web page.

web/zora-worker.js runs Python glue inside Pyodide that needs exactly these
names: the flag form, the base ROM's expected hashes, generate_rom, the
page's player settings and the seed report (the seed document and spoiler
log). Keep them importable from here whenever modules move.
"""
import json
from collections.abc import Mapping
from typing import Any

from zora.export.seed_document import EncodedSeedRefused, seed_document_for
from zora.export.spoiler_log import spoiler_file_name, spoiler_log
from zora.flags import form as flag_form
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import EXPECTED_CRC32, EXPECTED_MD5, EXPECTED_SHA1
from zora.rom.player_settings import (
    DeathWarp,
    LowHealthBeep,
    Music,
    PlayerSettingError,
    PlayerSettings,
    SelectSwap,
)

__all__ = ["EXPECTED_CRC32", "EXPECTED_MD5", "EXPECTED_SHA1", "EncodedSeedRefused", "flag_form", "generate_rom",
           "player_settings_from_page", "seed_report"]

# The page's Cosmetic tab (web/zora-web.js PLAYER_CHOICES and PLAYER_COLOURS):
# its keys and choice values, as PlayerSettings fields.
PAGE_CHOICES: dict[str, tuple[str, dict[str, Any]]] = {
    "selectButton": ("select_swap", {"off": SelectSwap.OFF, "swap": SelectSwap.SWAP_ONLY,
                                     "toggle": SelectSwap.TOGGLE}),
    "lowHealthBeep": ("low_health_beep", {"removed": LowHealthBeep.REMOVED, "kept": LowHealthBeep.KEPT}),
    "deathWarp": ("death_warp", {"p2-up-a": DeathWarp.CONTROLLER2_UP_A, "p1-up-a": DeathWarp.CONTROLLER1_UP_A,
                                 "p1-up-select": DeathWarp.CONTROLLER1_UP_SELECT}),
    "reduceFlashing": ("reduce_flashing", {"off": False, "on": True}),
    "music": ("music", {"on": Music.ON, "off": Music.OFF}),
}
PAGE_TUNIC_SLOTS = ("greenTunic", "blueRingTunic", "redRingTunic")
PAGE_HEART_SLOT = "heart"


def player_settings_from_page(values: Mapping[str, Any]) -> PlayerSettings:
    """The page's playerSettings object as PlayerSettings. A key it leaves out
    takes the default; an unknown choice or a colour that is not an NES palette
    value (or is $0D) is refused with PlayerSettingError, never replaced."""
    defaults = PlayerSettings()
    chosen: dict[str, Any] = {}
    for key, (field, choices) in PAGE_CHOICES.items():
        if key in values:
            if not isinstance(values[key], str) or values[key] not in choices:
                raise PlayerSettingError(f"{key}: unknown choice {values[key]!r}")
            chosen[field] = choices[values[key]]
    tunics = tuple(values.get(slot, default)
                   for slot, default in zip(PAGE_TUNIC_SLOTS, defaults.tunic_colours, strict=True))
    return PlayerSettings(tunic_colours=tunics, heart_colour=values.get(PAGE_HEART_SLOT, defaults.heart_colour),
                          **chosen)


def seed_report(rom: bytes, flag_string: str, seed: int, zora_flag_string: str = "") -> dict[str, str]:
    """For a finished ROM made from these strings and seed: the seed document as JSON text (the
    "View in Visualizer" hand-off), the spoiler log and its file name. Reads the ROM only, after
    it is made; EncodedSeedRefused for a seed with level encoding on."""
    document = seed_document_for(rom, flag_string, seed, zora_flag_string)
    return {"json": json.dumps(document), "spoiler": spoiler_log(document),
            "spoilerName": spoiler_file_name(document)}
