"""
Invariant tests: validate_game_world passes on vanilla parsed data.
"""
import copy

import pytest

from zora.parser import parse_game_world
from zora.validator import validate_game_world


def test_vanilla_invariants(vanilla_game_world):
    validate_game_world(vanilla_game_world)  # must not raise


def test_shared_room_within_grid_rejected(bins):
    gw = parse_game_world(bins)

    # Duplicate a room from level 1 into level 2 (both in the 1-6 grid)
    gw_bad = copy.deepcopy(gw)
    stolen_room = copy.deepcopy(gw_bad.levels[0].rooms[0])
    gw_bad.levels[1].rooms.append(stolen_room)

    with pytest.raises(ValueError, match="shared by levels"):
        validate_game_world(gw_bad)
