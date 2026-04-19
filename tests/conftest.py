"""Shared test fixtures — cached ROM data to avoid repeated disk I/O."""
import copy
from pathlib import Path

import pytest

from zora.parser import load_bin_files, parse_game_world

TEST_DATA = Path(__file__).parent.parent / "rom_data"


@pytest.fixture(scope="session")
def bins():
    """Session-scoped raw bin files (immutable bytes, safe to share)."""
    return load_bin_files(TEST_DATA)


@pytest.fixture(scope="session")
def vanilla_game_world(bins):
    """Session-scoped vanilla GameWorld. DO NOT mutate — use
    fresh_game_world for tests that modify state."""
    return parse_game_world(bins)


@pytest.fixture()
def fresh_game_world(bins):
    """Per-test fresh GameWorld (parsed from cached bins)."""
    return parse_game_world(bins)
