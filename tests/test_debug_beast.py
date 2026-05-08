"""Tests for the debug_beast flag.

Verifies the flag's two effects in isolation:
  - swapping WOOD_SWORD_CAVE ↔ LEVEL_9 destinations on the overworld
  - opening every internal L9 wall (excluding entrance & gate rooms)

Both effects must be no-ops when the flag is off.
"""

from pathlib import Path

import pytest

from zora.data_model import (
    Destination,
    Direction,
    QuestVisibility,
    WallType,
    is_l9_entry_gate,
)
from zora.debug_beast import apply_debug_beast
from zora.game_config import GameConfig
from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng


ROM_DATA = Path(__file__).parent.parent / "rom_data"


@pytest.fixture
def world():
    bins = load_bin_files(ROM_DATA)
    return parse_game_world(bins)


def _ws_screen(world):
    return next(s for s in world.overworld.screens
                if s.destination == Destination.WOOD_SWORD_CAVE)


def _l9_screen_q1(world):
    """First-quest L9 entrance (vanilla has both Q1 and Q2 entrances)."""
    return next(s for s in world.overworld.screens
                if s.destination == Destination.LEVEL_9
                and s.quest_visibility != QuestVisibility.SECOND_QUEST)


def test_debug_beast_off_is_noop(world) -> None:
    ws_before = _ws_screen(world).screen_num
    l9_before = _l9_screen_q1(world).screen_num
    apply_debug_beast(world, GameConfig(debug_beast=False), SeededRng(0))
    assert _ws_screen(world).screen_num == ws_before
    assert _l9_screen_q1(world).screen_num == l9_before
    # Walls untouched: pick a known-non-OPEN_DOOR wall in vanilla L9 and assert.
    # (Don't pin a specific wall — just confirm not every wall is OPEN_DOOR.)
    l9 = world.levels[8]
    assert any(
        room.walls[d] != WallType.OPEN_DOOR
        for room in l9.rooms
        for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)
    )


def test_debug_beast_swaps_overworld_entrances(world) -> None:
    ws_screen_num_before = _ws_screen(world).screen_num
    l9_q1_screen_num_before = _l9_screen_q1(world).screen_num

    apply_debug_beast(world, GameConfig(debug_beast=True), SeededRng(0))

    # The Q1 L9 destination and the wood sword destination are now on each
    # other's old screens. (The Q2 L9 entrance is intentionally untouched.)
    assert _ws_screen(world).screen_num == l9_q1_screen_num_before
    assert _l9_screen_q1(world).screen_num == ws_screen_num_before


def test_debug_beast_opens_l9_internal_walls(world) -> None:
    apply_debug_beast(world, GameConfig(debug_beast=True), SeededRng(0))

    l9 = world.levels[8]
    rooms_by_num = {r.room_num: r for r in l9.rooms}
    excluded = {l9.entrance_room}
    for r in l9.rooms:
        if is_l9_entry_gate(l9, r):
            excluded.add(r.room_num)
    eligible = {r.room_num for r in l9.rooms if r.room_num not in excluded}

    offsets = {
        Direction.NORTH: -0x10,
        Direction.SOUTH: +0x10,
        Direction.EAST: +1,
        Direction.WEST: -1,
    }

    # Every wall between two eligible L9 rooms must be OPEN_DOOR on both sides.
    for room in l9.rooms:
        if room.room_num not in eligible:
            continue
        for direction, offset in offsets.items():
            neighbor_num = room.room_num + offset
            if neighbor_num not in eligible:
                continue
            assert room.walls[direction] == WallType.OPEN_DOOR, (
                f"L9 room {room.room_num:#x} wall {direction.name} not opened"
            )


def test_debug_beast_preserves_excluded_rooms(world) -> None:
    """Walls of the entrance room and gate room are NOT touched
    on the side that faces an excluded room."""
    l9 = world.levels[8]
    entrance_num = l9.entrance_room
    gate_num = entrance_num - 0x10

    # Snapshot the entrance room's walls before.
    rooms_by_num = {r.room_num: r for r in l9.rooms}
    entrance_room = rooms_by_num[entrance_num]
    walls_before = {
        d: entrance_room.walls[d]
        for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)
    }

    apply_debug_beast(world, GameConfig(debug_beast=True), SeededRng(0))

    # Entrance walls should be untouched (we treat it as out-of-level).
    for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
        assert entrance_room.walls[d] == walls_before[d], (
            f"entrance room wall {d.name} should not have been mutated"
        )

    # Gate room: same story.
    if gate_num in rooms_by_num:
        gate = rooms_by_num[gate_num]
        # All gate walls must still match their pre-apply values.
        # (We didn't snapshot earlier, so re-derive from a fresh world.)
        bins = load_bin_files(ROM_DATA)
        fresh = parse_game_world(bins)
        fresh_rooms_by_num = {r.room_num: r for r in fresh.levels[8].rooms}
        fresh_gate = fresh_rooms_by_num[gate_num]
        for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
            assert gate.walls[d] == fresh_gate.walls[d], (
                f"gate room wall {d.name} should not have been mutated"
            )
