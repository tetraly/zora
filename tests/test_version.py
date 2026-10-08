"""ZORA's version (zora/version.py), as players read it, is the title screen's version line and the
newest entry of docs/CHANGELOG.md (version policy 2026-10-06: bumped at each published release;
a beta "2.0.0b1" reads "2.0 beta 1", owner decision 2026-10-07)."""
import re
from pathlib import Path

import pytest

from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.version import PLAYER_VERSION, ZORA_VERSION, player_version

CHANGELOG = Path(__file__).resolve().parents[1] / "docs" / "CHANGELOG.md"


def test_the_changelog_ends_at_this_version() -> None:
    versions = re.findall(r"^## (\d+\.\d+(?:\.\d+)?(?: beta \d+)?) ", CHANGELOG.read_text(), re.MULTILINE)
    assert versions and versions[0] == PLAYER_VERSION


@pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")
def test_the_title_screen_shows_the_version() -> None:
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, verify_base_rom().read_bytes()).rom
    assert parse_rom(rom).title_version_line == f"ZORA {PLAYER_VERSION}".upper() == "ZORA 2.0 BETA 1"


def test_players_read_a_beta_as_beta_n() -> None:
    assert ZORA_VERSION == "2.0.0b1" and PLAYER_VERSION == "2.0 beta 1"
    assert player_version("2.1.0b12") == "2.1 beta 12" and player_version("2.0.0") == "2.0.0"
