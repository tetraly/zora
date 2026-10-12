"""Shuffle Dungeon Start Room (B26): the start-room swap (post-shapes-b9.md PS-START-01 to
PS-START-03), Link's arrival by the codes it writes (FP-ENTR-01, asm/fp-entr-01-sides) and E9
(acceptance.md VA-REJ-21)."""
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, LEVEL_1_MOUTH_X, LEVEL_1_TRIFORCE, OBJ_DIR, OBJ_X, OBJ_Y, Button, Emulator, Mode
from zora.generate.acceptance_check import start_room_is_own_door
from zora.generate.pipeline import generate_rom, plan
from zora.generate.steps.monster_lists import RoomLists
from zora.generate.steps.swap_start_rooms import ARRIVAL_CODES, Edge, level_edges, swap_start_room
from zora.model import room_grid
from zora.model.enums import Side, WallType
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.code_patches import ENTR_01_SIDES, left_out_patches, overworld_start_y
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora_measure.checkpoints.start_rooms import (
    START_ROOM_SWAP_FLAGS,
    arrival_code,
    exit_counts,
    start_rooms_open_on_their_side,
)

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

SEEDS = range(6)
# b26 seeds whose data level 8 (44) or 7 (147) start room opens west or east onto level 9's
# entrance, which late-gate step 5 must leave open (A63)
BESIDE_LEVEL_9_ENTRANCE = (44, 147)
# Where Link stands once he has walked in, for each arrival code (FP-ENTR-01 places him 16 pixels
# outside: Y $3D; X $00; X $F0; Y $DD), and the way he faces
WALKED_IN = {1: (0x78, 0x4D, 0x04), 2: (0x78, 0xCD, 0x08), 3: (0x10, 0x8D, 0x01), 4: (0xE0, 0x8D, 0x02)}


@cache
def _prg0() -> GameWorld:
    return parse_rom(remember_repo_base_rom())


@cache
def _finished(seed: int) -> GameWorld:
    config = plan(START_ROOM_SWAP_FLAGS, seed).config
    rom = generate_rom(START_ROOM_SWAP_FLAGS, seed, remember_repo_base_rom()).rom
    return parse_rom(rom, GameConfig(dungeon_nothing_code=config.dungeon_nothing_code, hint_mode=config.hint_mode))


def test_edges_are_listed_in_room_order_up_down_left_right() -> None:
    level = _prg0().levels[0]
    edges = level_edges(level)
    assert edges == sorted(edges, key=lambda edge: (edge.room, (Side.NORTH, Side.SOUTH, Side.WEST,
                                                                Side.EAST).index(edge.side)))
    for edge in edges:
        neighbour = room_grid.neighbour(edge.room, edge.side)
        owner = None if neighbour is None else level.block.owner_of(neighbour)
        assert edge.room in level.room_nums and (neighbour is None or owner not in (None, level))


def test_level_9_lists_only_downward_edges_below_its_own_rooms() -> None:
    level = _prg0().levels[8]
    edges = level_edges(level)
    assert edges and all(edge.side == Side.SOUTH for edge in edges)
    assert all(level.block.owner_of(edge.room - room_grid.COLUMNS) is level for edge in edges)


def test_the_swap_moves_the_contents_and_opens_the_drawn_side() -> None:
    world = parse_rom(remember_repo_base_rom())
    level = world.levels[0]
    old = level.entrance_room
    edge = next(edge for edge in level_edges(level) if edge.room != old)
    old_contents, new_contents = (level.block.room(room).layout_info for room in (old, edge.room))
    swap_start_room(level, 0, edge, [], RoomLists())
    assert (level.block.room(old).layout_info, level.block.room(edge.room).layout_info) == (
        new_contents, old_contents)
    assert level.block.room(old).walls.south == WallType.SOLID_WALL
    assert level.block.room(edge.room).walls[edge.side] == WallType.OPEN_DOOR
    assert (level.entrance_room, level.arrival_code) == (edge.room, ARRIVAL_CODES[edge.side])
    assert level.exit_room == edge.room + edge.side.delta or not 0 <= edge.room + edge.side.delta < 128


def test_a_move_past_the_block_stores_another_levels_first_room() -> None:
    world = parse_rom(remember_repo_base_rom())
    level = world.levels[0]
    edge = Edge(level.entrance_room, Side.SOUTH)          # PRG0's start rooms are on the bottom row
    swap_start_room(level, 0, edge, [], RoomLists())
    first_other = next(room for room in range(128) if level.block.owner_of(room) not in (None, level))
    assert level.exit_room == first_other


@pytest.mark.parametrize("seed", [*SEEDS, *BESIDE_LEVEL_9_ENTRANCE])
def test_b26_seeds_move_start_rooms_to_open_sides_that_leave_the_level(seed: int) -> None:
    world = _finished(seed)
    assert start_rooms_open_on_their_side(world) == (9, 9)
    counts = exit_counts(world)
    assert counts["leaves"] == counts["levels"] == 9
    assert arrival_code(world.levels[8]) == 2
    assert not start_room_is_own_door(world.levels, world.overworld)


@pytest.mark.parametrize("seed", SEEDS)
def test_the_three_level_sets_first_level_keeps_row_7_column_6(seed: int) -> None:
    """SH-GRID-02 (U40): under B26 the three-level set's first level still starts at $76 and
    takes $66 above it, so both belong to one of levels 7 to 9."""
    block = _finished(seed).levels[8].block
    owner = block.owner_of(0x76)
    assert owner is not None and owner.level_num >= 7 and block.owner_of(0x66) is owner


@pytest.mark.parametrize("exit_room", [0x00, 0x7F])
def test_the_exit_room_reads_back(exit_room: int) -> None:
    """PS-START-03: +$23 holds E | $80, so room $7F is stored as $FF, PRG0's own byte there; the
    arrival code (+$3D) tells the patched ROM from PRG0 (seed 101 of a 2nd Quest case, whose
    data level 8 opens right at $7E into level 7's $7F, parsed with no exit room before)."""
    base = remember_repo_base_rom()
    world = parse_rom(base)
    world.levels[0].arrival_code, world.levels[0].exit_room = 4, exit_room
    config = GameConfig(features_b10=True)
    level = parse_rom(serialize_to_rom(world, base, config=config), config).levels[0]
    assert (level.arrival_code, level.exit_room) == (4, exit_room)
    assert _prg0().levels[0].exit_room is None


def test_the_overworld_start_y_reads_back_beside_the_side_patch() -> None:
    """FP-ENTR-01's start Y is found with fp-entr-01-sides written over fp-entr-01's jump (seed
    101 of the B26 invariant case read PRG0's Y instead, and the round trip differed)."""
    base = remember_repo_base_rom()
    world = parse_rom(base)
    world.levels[0].arrival_code = 4
    world.overworld.start_position_y = world.overworld.start_position_y - 0x10
    config = GameConfig(features_b10=True)
    rom = serialize_to_rom(world, base, config=config)
    assert overworld_start_y(rom) == world.overworld.start_position_y
    assert serialize_to_rom(parse_rom(rom, config), rom, config=config) == rom


def test_the_side_patch_is_written_only_when_a_start_room_moved() -> None:
    assert ENTR_01_SIDES in left_out_patches(False, False, False)
    assert ENTR_01_SIDES not in left_out_patches(False, False, False, start_rooms_moved=True)


def test_e9_rejects_a_start_room_on_its_own_door() -> None:
    world = parse_rom(remember_repo_base_rom())
    level = world.levels[0]
    door = next(screen for screen in world.overworld.screens if screen.destination == level.level_num)
    assert not start_room_is_own_door(world.levels, world.overworld)
    level.entrance_room = door.screen_num
    assert start_room_is_own_door(world.levels, world.overworld)


@pytest.mark.parametrize("code", sorted(WALKED_IN))
def test_link_enters_by_the_arrival_code(code: int) -> None:
    """FP-ENTR-01's codes 1-4: Link is placed outside the open side and walks in, facing into
    the room (level 1's start room keeps PRG0's doors; only the code is set)."""
    base = remember_repo_base_rom()
    world = parse_rom(base)
    world.levels[0].arrival_code = None if code == 2 else code
    emu = Emulator(serialize_to_rom(world, base, config=GameConfig(features_b10=True)))
    emu.new_game()
    emu.play_recorder(LEVEL_1_TRIFORCE)
    emu.run_until(lambda: emu[OBJ_X] <= LEVEL_1_MOUTH_X, buttons=Button.LEFT)
    emu.run_until(lambda: emu[CUR_LEVEL] == 1, buttons=Button.UP, limit=1000)
    emu.run_until(lambda: emu.mode == Mode.PLAY, limit=400)
    emu.run(60)
    assert (emu[OBJ_X], emu[OBJ_Y], emu[OBJ_DIR]) == WALKED_IN[code]
