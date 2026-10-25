"""Gatekeeper Bosses in the emulator (docs/zora-extras.md section 19), on a generated ROM: in each level
1-8, Link enters the gatekeeper's room with the boss alive. Its shutters into the gated part are shut,
its item is hidden (trigger 7), and walking into a shutter leaves Link in the room. Once its monsters
are gone, those shutters open, the item appears, and the same walk takes Link into the gated part."""
from functools import cache

import pytest

from tests.emulator import CUR_OPENED_DOORS, OBJ_STATE, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID, ROOM_ITEM_SLOT, Button
from tests.needs import needs_base_rom
from tests.test_progressive_emulator import ENTER_ROOM_MODE, Game
from zora.flags import zora_flags
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import GatekeeperBosses, ZoraFlags
from zora.generate.late_gate.gatekeeper import GATEKEEPER_LEVELS, gated_part, level_neighbors
from zora.generate.pipeline import Built, build, finish, plan
from zora.model.enums import Side
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom

SEED = 1
MONSTER_SLOTS = range(1, 12)
HIDDEN_ITEM = 0xFF                    # a room item's ObjState while trigger 7 keeps it hidden
SHOWN_ITEM = 0x00
CLEAR_FRAMES = 90
# The game's door direction bits (CurOpenedDoors), by side
DOOR_BIT = {Side.NORTH: 0x08, Side.EAST: 0x01, Side.SOUTH: 0x04, Side.WEST: 0x02}
# Just below the north doorway, and how long Link walks up into it
NORTH_DOOR_APPROACH = (0x78, 0x65)
WALK_FRAMES = 150
SHUT_DOORWAY_Y = 0x5D                 # where a shut north door stops Link


@cache
def generated() -> tuple[Built, bytes]:
    base = remember_repo_base_rom()
    built = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED,
                       zora_flags.encode(ZoraFlags(gatekeeper_bosses=GatekeeperBosses.ANYWHERE))), base)
    return built, finish(built, base)


def gatekeeper_of(level_num: int) -> int:
    gatekeeper = generated()[0].world.levels[level_num - 1].gatekeeper_room
    assert gatekeeper is not None
    return gatekeeper


def in_gatekeeper_room(level_num: int, killed: bool) -> Game:
    game = Game(generated()[1])
    game.enter_level(level_num)
    game.emu[ROOM_ID] = gatekeeper_of(level_num)
    game.start_mode(ENTER_ROOM_MODE)
    game.wait_for_play()
    game.emu.run(10)
    if killed:
        for slot in MONSTER_SLOTS:
            game.emu[OBJ_TYPE + slot] = 0
        game.emu.run(CLEAR_FRAMES)
    return game


def shutters_into_the_part(level_num: int) -> dict[Side, int]:
    level = generated()[0].world.levels[level_num - 1]
    gatekeeper = gatekeeper_of(level_num)
    behind = gated_part(level, gatekeeper)
    return {side: other for side, other in level_neighbors(level, gatekeeper) if other in behind}


@pytest.mark.parametrize("level_num", GATEKEEPER_LEVELS)
def test_the_kill_opens_the_shutters_and_shows_the_item(level_num: int) -> None:
    doors = sum(DOOR_BIT[side] for side in shutters_into_the_part(level_num))
    alive = in_gatekeeper_room(level_num, killed=False)
    assert alive.emu[CUR_OPENED_DOORS] & doors == 0
    assert alive.emu[OBJ_STATE + ROOM_ITEM_SLOT] == HIDDEN_ITEM
    killed = in_gatekeeper_room(level_num, killed=True)
    assert killed.emu[CUR_OPENED_DOORS] & doors == doors
    assert killed.emu[OBJ_STATE + ROOM_ITEM_SLOT] == SHOWN_ITEM


@pytest.mark.parametrize("level_num", GATEKEEPER_LEVELS)
def test_the_gated_part_is_reached_only_after_the_kill(level_num: int) -> None:
    """Walked through a north shutter (seed 1: levels 1, 2, 3, 4, 7 and 8 have one)."""
    if Side.NORTH not in shutters_into_the_part(level_num):
        pytest.skip("no north shutter into the gated part")
    gatekeeper = gatekeeper_of(level_num)
    for killed, expected_room in ((False, gatekeeper), (True, shutters_into_the_part(level_num)[Side.NORTH])):
        game = in_gatekeeper_room(level_num, killed)
        game.emu[OBJ_X], game.emu[OBJ_Y] = NORTH_DOOR_APPROACH
        game.emu.run(WALK_FRAMES, Button.UP)
        assert game.emu[ROOM_ID] == expected_room
        if not killed:
            assert game.emu[OBJ_Y] == SHUT_DOORWAY_Y
