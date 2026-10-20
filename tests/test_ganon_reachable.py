"""E10, ZORA's own acceptance rule (docs/deviations.md "Ganon's room is reachable before the
last-boss shutters open"): a pass whose Ganon is reached only through Zelda's room is rejected.

Permanent Sword Beam (B52) seed 67, from the 2026-10-18 Archipelago logic scan, first showed it: its
first accepted pass put Ganon's room ($76) past Zelda's ($56), whose facing rooms ($46, $66) take
the last-boss trigger (3, VA-REJ-03 step 8). Later output changes moved that seed; seed 241 of the
same flags (found 2026-10-19 over seeds 0-299, the only one E10 rejects a pass of) has the same
case one column east: Ganon at $77 past Zelda at $58, her facing rooms $48 and $68. Their shutters open only once the Triforce of Power,
Ganon's own drop, is taken, so that ROM could not be beaten; the spec accepts it (E1 never
targets Ganon, E3 walks with those shutters open)."""
import pytest

from tests.emulator import CUR_OPENED_DOORS, LAST_BOSS_DEFEATED, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID, Button, Emulator
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import MONSTER_SLOTS
from tests.test_november_settings import _enter_room
from zora import archipelago
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.logic import TRIFORCE_OF_POWER_EVENT, sweep
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.places import read_item
from zora.model.enums import RoomAction
from zora.model.levels import GANON_LIST, LEVEL_9, ZELDA_LIST
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom

FLAGS, ZORA_FLAGS, SEED = "3yQgj9rNB6LCR7rTnBO2LzLDUB0uFfq4qcz8Kqca", "4.ApGzr", 241
GANON_ROOM, ZELDA_ROOM = 0x77, 0x58
# The rooms facing Zelda's, each with its shutter toward it: CurOpenedDoors' bit for that side,
# the button that walks Link through it, and Link's start, a few tiles inside the room
FACING_ZELDA = {0x48: (0x04, Button.DOWN, 0xB0), 0x68: (0x08, Button.UP, 0x60)}
DOORWAY_X = 0x78
CLEAR_FRAMES = 240                       # the shutters' trigger is judged once the room is clear
WALK_FRAMES = 120
TRIFORCE_OF_POWER_TAKEN = 2              # LastBossDefeated once the fanfare ends (tests/test_sword_states.py)


def built() -> Built:
    return build(plan(FLAGS, SEED, ZORA_FLAGS), remember_repo_base_rom())


def built_without_e10(monkeypatch: pytest.MonkeyPatch) -> Built:
    """The seed with E10 left out, the ROM before the fix. The monkeypatch fixture keeps the build
    out of the session's shared builds (tests/shared_builds.py)."""
    monkeypatch.setattr(AcceptanceCheck, "reaches_ganon_before_shutters_open", lambda self: True)
    return built()


def test_without_e10_ganon_sits_past_zeldas_last_boss_shutters(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pass E10 rejects: Ganon at $77, Zelda at $58, and trigger-3 rooms facing her."""
    level9 = next(level for level in built_without_e10(monkeypatch).world.levels if level.level_num == LEVEL_9)
    rooms = {room.room_num: room for room in level9.rooms}
    assert rooms[GANON_ROOM].enemy == GANON_LIST and rooms[ZELDA_ROOM].monster_byte == ZELDA_LIST
    assert all(rooms[room].room_action == RoomAction.LAST_BOSS for room in FACING_ZELDA)


def test_generation_rejects_the_pass_and_accepts_one_whose_ganon_is_reached() -> None:
    result = built().result
    assert result.acceptance_rejections["E10"] == 1


def test_archipelagos_logic_reaches_ganon_and_the_goal() -> None:
    """The scan's failing check: the Triforce of Power event and the goal are reached."""
    result = archipelago.build_from_strings(FLAGS, ZORA_FLAGS, SEED, remember_repo_base_rom())
    swept = sweep(result.logic, {}, [read_item(result.state.world, place) for place in result.state.places])
    assert TRIFORCE_OF_POWER_EVENT in swept.events and swept.reaches_goal


@pytest.mark.parametrize("defeated", [False, True], ids=["before-the-triforce-of-power", "after"])
@pytest.mark.parametrize("room", sorted(FACING_ZELDA), ids=lambda room: f"room-{room:02X}")
def test_the_shutters_facing_zelda_open_only_with_the_triforce_of_power(room: int, defeated: bool,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """In the emulator, on the ROM before the fix: in a room facing Zelda's, cleared, the shutter
    toward her stays shut and Link stays put, until LastBossDefeated is set (as the end of the
    Triforce of Power's fanfare sets it): then he walks into Zelda's room."""
    door, button, y = FACING_ZELDA[room]
    emu = Emulator(finish(built_without_e10(monkeypatch), remember_repo_base_rom()))
    emu.new_game()
    _enter_room(emu, LEVEL_9, room)
    emu[LAST_BOSS_DEFEATED] = TRIFORCE_OF_POWER_TAKEN if defeated else 0
    for _ in range(CLEAR_FRAMES):
        for slot in MONSTER_SLOTS:
            emu[OBJ_TYPE + slot] = 0
        emu.run(1)
    assert bool(emu[CUR_OPENED_DOORS] & door) == defeated
    emu[OBJ_X], emu[OBJ_Y] = DOORWAY_X, y
    emu.run(WALK_FRAMES, button)
    assert emu[ROOM_ID] == (ZELDA_ROOM if defeated else room)
