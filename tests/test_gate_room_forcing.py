"""Level 9's Triforce gate room's north, east and west sides (late-gate.md VA-REJ-19, A77 and A80):
forced to shutters unless walls right after the late gate's repair only where the walks then count
its shutters open, and in every seed by the end pass (post-shapes PS-MONRD-07)."""
import pytest

from zora.generate.boss_sounds import boss_sound_end_pass
from zora.generate.late_gate.fixes import GATE_ROOM_SIDES, _reforce_level9_person_sides
from zora.generate.late_gate.walk import level9_entry_room
from zora.generate.steps.monster_lists import RoomLists
from zora.generate.steps.swap_start_rooms import level_edges, swap_start_room
from zora.model.enums import RoomAction, Side, WallType
from zora.model.game_world import GameWorld
from zora.model.levels import L9_ENTRY_PERSON, LEVEL_9, Level
from zora.model.rooms import Room
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

LEVELS_7_TO_9_BLOCK = 1


def _gate_room(level: Level) -> Room:
    return next(room for number in level.room_nums if (room := level.block.room(number)).enemy == L9_ENTRY_PERSON)


def _second_quest_level_9_moved() -> tuple[GameWorld, Level, Room]:
    """PRG0's second-quest level 9 with its start room moved (B26) to the first edge whose gate
    room is not the walks' fixed cell $64 (VA-WALK-08's quirk), the gate room's east side open."""
    gw = parse_rom(remember_repo_base_rom())
    level = gw.levels_2q[LEVEL_9 - 1]
    assert level.is_second_quest and _gate_room(level).room_num == level9_entry_room(level)
    edge = next(edge for edge in level_edges(level) if edge.room - 16 != level9_entry_room(level))
    swap_start_room(level, LEVELS_7_TO_9_BLOCK, edge, [], RoomLists())
    gate = _gate_room(level)
    assert gate.room_num == level.entrance_room - 16 != level9_entry_room(level)
    gate.walls.east = WallType.OPEN_DOOR
    return gw, level, gate


def test_a_moved_second_quest_gate_room_with_trigger_0_keeps_its_open_side_through_the_gate() -> None:
    """A80: the walks would find a closed shutter there, where the original randomizer's open side passes."""
    _, level, gate = _second_quest_level_9_moved()
    gate.room_action = RoomAction.NONE
    _reforce_level9_person_sides(level)
    assert gate.walls.east == WallType.OPEN_DOOR


def test_a_moved_second_quest_gate_room_with_trigger_1_is_forced_after_the_repair() -> None:
    _, level, gate = _second_quest_level_9_moved()
    gate.room_action = RoomAction.ALL_DEAD
    _reforce_level9_person_sides(level)
    assert gate.walls.east == WallType.SHUTTER_DOOR


def test_the_walks_cell_is_forced_after_the_repair_whatever_its_trigger() -> None:
    gw = parse_rom(remember_repo_base_rom())
    level = gw.levels_2q[LEVEL_9 - 1]
    gate = _gate_room(level)
    gate.room_action = RoomAction.NONE
    gate.walls.east = WallType.OPEN_DOOR
    _reforce_level9_person_sides(level)
    assert gate.walls.east == WallType.SHUTTER_DOOR


def test_the_end_pass_forces_the_gate_room_sides() -> None:
    """A77: the end pass makes each of the three sides a shutter unless it is a wall."""
    gw, _, gate = _second_quest_level_9_moved()
    gate.room_action = RoomAction.NONE
    gate.walls.west = WallType.SOLID_WALL
    south = gate.walls[Side.SOUTH]
    boss_sound_end_pass(gw)
    assert gate.walls.east == WallType.SHUTTER_DOOR and gate.walls.west == WallType.SOLID_WALL
    assert all(gate.walls[side] in (WallType.SHUTTER_DOOR, WallType.SOLID_WALL) for side in GATE_ROOM_SIDES)
    assert gate.walls[Side.SOUTH] == south          # the end pass leaves the south side (PS-MONRD-07)
