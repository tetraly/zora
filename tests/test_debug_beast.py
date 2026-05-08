"""Tests for the debug_beast flag.

Verifies the flag's two effects in isolation:
  - L9 (Q1) entrance is forced to overworld screen 0x77, the screen
    previously there is swapped onto L9's old slot.
  - Every internal L9 wall is opened to OPEN_DOOR, except for walls
    touching the entrance, the entry-gate, the THE_BEAST (Ganon) room,
    or the THE_KIDNAPPED (Zelda) room.

Both effects must be no-ops when the flag is off.
"""

from pathlib import Path

import pytest

from zora.data_model import (
    Destination,
    Direction,
    Enemy,
    QuestVisibility,
    WallType,
    is_l9_entry_gate,
)
from zora.debug_beast import apply_debug_beast
from zora.game_config import GameConfig
from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng


ROM_DATA = Path(__file__).parent.parent / "rom_data"
_VANILLA_WS_SCREEN = 0x77


@pytest.fixture
def world():
    bins = load_bin_files(ROM_DATA)
    return parse_game_world(bins)


def _screen_at(world, screen_num):
    return next(s for s in world.overworld.screens if s.screen_num == screen_num)


def _l9_screen_q1(world):
    """First-quest L9 entrance (vanilla has both Q1 and Q2 entrances)."""
    return next(s for s in world.overworld.screens
                if s.destination == Destination.LEVEL_9
                and s.quest_visibility != QuestVisibility.SECOND_QUEST)


def test_debug_beast_off_is_noop(world) -> None:
    ws_dest_before = _screen_at(world, _VANILLA_WS_SCREEN).destination
    l9_screen_before = _l9_screen_q1(world).screen_num
    apply_debug_beast(world, GameConfig(debug_beast=False), SeededRng(0))
    assert _screen_at(world, _VANILLA_WS_SCREEN).destination == ws_dest_before
    assert _l9_screen_q1(world).screen_num == l9_screen_before
    l9 = world.levels[8]
    assert any(
        room.walls[d] != WallType.OPEN_DOOR
        for room in l9.rooms
        for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)
    )


def test_debug_beast_forces_l9_to_screen_0x77(world) -> None:
    # Pre-condition: in vanilla, screen 0x77 holds the wood sword cave and
    # L9 (Q1) is at screen 0x05.
    pre_l9_screen = _l9_screen_q1(world).screen_num
    pre_77_dest = _screen_at(world, _VANILLA_WS_SCREEN).destination

    apply_debug_beast(world, GameConfig(debug_beast=True), SeededRng(0))

    # Post: L9 (Q1) is at 0x77, and the destination that was at 0x77 is now
    # at L9's old screen (preserving every overworld destination, just
    # swapped between two screens).
    assert _l9_screen_q1(world).screen_num == _VANILLA_WS_SCREEN
    assert _screen_at(world, _VANILLA_WS_SCREEN).destination == Destination.LEVEL_9
    assert _screen_at(world, pre_l9_screen).destination == pre_77_dest


def test_debug_beast_opens_l9_internal_walls(world) -> None:
    apply_debug_beast(world, GameConfig(debug_beast=True), SeededRng(0))

    l9 = world.levels[8]
    excluded = {l9.entrance_room}
    for r in l9.rooms:
        if is_l9_entry_gate(l9, r):
            excluded.add(r.room_num)
        if r.enemy_spec.enemy in (Enemy.THE_BEAST, Enemy.THE_KIDNAPPED):
            excluded.add(r.room_num)
    eligible = {r.room_num for r in l9.rooms if r.room_num not in excluded}

    offsets = {
        Direction.NORTH: -0x10,
        Direction.SOUTH: +0x10,
        Direction.EAST: +1,
        Direction.WEST: -1,
    }

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
    """Entrance, gate, beast, and kidnapped rooms must keep their walls
    untouched after debug_beast runs."""
    bins = load_bin_files(ROM_DATA)
    fresh = parse_game_world(bins)
    fresh_l9 = fresh.levels[8]
    fresh_by_num = {r.room_num: r for r in fresh_l9.rooms}

    entrance_num = fresh_l9.entrance_room
    gate_num = entrance_num - 0x10
    beast_num = next(r.room_num for r in fresh_l9.rooms
                     if r.enemy_spec.enemy == Enemy.THE_BEAST)
    kidnapped_num = next(
        (r.room_num for r in fresh_l9.rooms
         if r.enemy_spec.enemy == Enemy.THE_KIDNAPPED),
        None,
    )

    apply_debug_beast(world, GameConfig(debug_beast=True), SeededRng(0))

    l9 = world.levels[8]
    by_num = {r.room_num: r for r in l9.rooms}

    excluded_nums = [n for n in (entrance_num, gate_num, beast_num, kidnapped_num)
                     if n is not None and n in fresh_by_num]
    for rn in excluded_nums:
        room_after = by_num[rn]
        room_before = fresh_by_num[rn]
        for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
            assert room_after.walls[d] == room_before.walls[d], (
                f"room {rn:#x} wall {d.name} should not have been mutated"
            )
