"""The web page's stable interface to ZORA: generation (zora/) and the seed report
(zora_export/), in a package of its own so that zora/ stays generation only.

web/zora-worker.js runs Python glue inside Pyodide that needs exactly these
names: the flag form, the base ROM's expected hashes and identify_rom, generate_rom, the
seed code's icons, the page's player settings, the seed report (the seed document and spoiler
log) and multiworld mode's Archipelago YAML (zora_web.multiworld). Keep
them importable from here whenever modules move.
"""
import json

from zora.flags import form as flag_form
from zora.generate.pipeline import generate_rom
from zora.rom import revision
from zora.rom.base_rom import EXPECTED_CRC32, EXPECTED_MD5, EXPECTED_SHA1
from zora.rom.player_settings import (
    PAGE_BOSS_SOUND_WORD,
    PAGE_CHOICES,
    PAGE_HEART_SLOT,
    PAGE_LEVEL_WORD,
    PAGE_TUNIC_SLOTS,
    PlayerSettingError,
    PlayerSettings,
    player_settings_from_page,
)
from zora.rom.seed_code_icons import seed_code_icons
from zora_export.seed_document import EncodedSeedRefused, seed_document_for
from zora_export.spoiler_log import spoiler_file_name, spoiler_log
from zora_web import multiworld

# The page's player-settings names live in zora/ (Archipelago's recipe uses them too); they are
# re-exported here under the names web/zora-worker.js and the scripts use.
__all__ = ["EXPECTED_CRC32", "EXPECTED_MD5", "EXPECTED_SHA1", "PAGE_BOSS_SOUND_WORD", "PAGE_CHOICES",
           "PAGE_HEART_SLOT", "PAGE_LEVEL_WORD", "PAGE_TUNIC_SLOTS", "EncodedSeedRefused", "PlayerSettingError",
           "PlayerSettings", "code_icons", "flag_form", "generate_rom", "identify_rom", "multiworld",
           "player_settings_from_page", "seed_report"]


def identify_rom(data: bytes) -> dict[str, object]:
    """The page's check of the ROM the player loads (zora.rom.revision.identify_rom, the one
    check generation, the scripts and Archipelago use): {"recognized": True, "revision": "PRG0"
    or "PRG1", "modifiedGraphics": bool, "message": ...}, or {"recognized": False, "message":
    "ROM not recognized. ..."}. generate_rom takes any recognized ROM."""
    try:
        identity = revision.identify_rom(data)
    except revision.RomNotRecognized as refused:
        return {"recognized": False, "message": str(refused)}
    return {"recognized": True, "revision": identity.revision.value,
            "modifiedGraphics": identity.modified_graphics, "message": identity.message}


def code_icons(rom: bytes) -> list[list[list[int]]]:
    """A finished ROM's seed code as its file-select screen draws it (zora.rom.seed_code_icons): four
    icons in screen order, each 16 rows of 16 NES palette values, for the page to paint."""
    return [[list(row) for row in icon.pixels] for icon in seed_code_icons(rom)]


def seed_report(rom: bytes, flag_string: str, seed: int, zora_flag_string: str = "") -> dict[str, str]:
    """For a finished ROM made from these strings and seed: the seed document as JSON text (the
    "View in Visualizer" hand-off), the spoiler log and its file name. Reads the ROM only, after
    it is made; EncodedSeedRefused for a seed with level encoding on."""
    document = seed_document_for(rom, flag_string, seed, zora_flag_string)
    return {"json": json.dumps(document), "spoiler": spoiler_log(document),
            "spoilerName": spoiler_file_name(document)}
