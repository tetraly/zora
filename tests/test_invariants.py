"""
Invariant tests: validate_game_world passes on vanilla parsed data.
"""
import copy
from pathlib import Path

import pytest

from zora.parser import load_bin_files, parse_game_world
from zora.validator import validate_game_world

TEST_DATA = Path(__file__).parent.parent / "rom_data"


def test_vanilla_invariants():
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)
    validate_game_world(gw)  # must not raise


def test_shared_room_within_grid_rejected():
    bins = load_bin_files(TEST_DATA)
    gw = parse_game_world(bins)

    # Duplicate a room from level 1 into level 2 (both in the 1-6 grid)
    gw_bad = copy.deepcopy(gw)
    stolen_room = copy.deepcopy(gw_bad.levels[0].rooms[0])
    gw_bad.levels[1].rooms.append(stolen_room)

    with pytest.raises(ValueError, match="shared by levels"):
        validate_game_world(gw_bad)
