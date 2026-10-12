"""The Archipelago client's smoke test, run before each beta (docs/releasing.md):

    python3 -m pytest tests/test_archipelago_beta_smoke.py -q

One console (cynes) runs the client loop of docs/archipelago.md "Interface" every frame: it
reports a place once its pickup check is set while checks_readable, and gives the server's next
item while checks_readable and may_receive, writing the received count with it. The console is
switched on with seeded random RAM and save RAM, registers a new file, takes one item (a room's
floor item, Link put in its room by the level-load and enter-room modes), receives one heart
container from the server, saves, is reset and continues the file. Exactly one check is sent, one
item is given, and nothing is given or sent twice."""
import random
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.emulator import CUR_LEVEL, OBJ_STATE, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID, ROOM_ITEM_SLOT, Emulator, Mode
from tests.test_archipelago_checks_readable import PLAY_FRAMES, RAM_SIZE, SAVE_RAM, Seen, Watched
from tests.test_archipelago_client_ram import CASE, SEED, built, zora_rom
from tests.test_assignment_emulator import (
    CLEAR_FRAMES,
    ENTER_ROOM_MODE,
    IS_UPDATING_MODE,
    MONSTER_SLOTS,
    TAKEN,
    floor_room,
)
from zora import archipelago
from zora.generate.places import Place
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

RANDOM_SEED = 2026
SERVER_ITEMS = ("Heart Container",)          # what the server holds for this player, in order
COUNT = archipelago.RECEIVED_COUNT
INVENTORY = range(inventory.ITEMS, inventory.MAX_BOMBS + 1)
LINK_INVINCIBILITY_TIMER = 0x4F0             # ObjInvincibilityTimer, slot 0 (Link)
INVINCIBLE = 0xFF
CONTAINER_SHIFT = 4
TAKE_FRAMES = 120
OVERWORLD = 0
WATCHED = sorted({*archipelago.CHECKS_STATE, *archipelago.RECEIVE_STATE})


class Client:
    """The client loop, one call per frame, with what the server has been told and has given."""

    def __init__(self, checks: dict[str, archipelago.RamCheck]) -> None:
        self.checks = checks
        self.sent: list[str] = []                 # every report, in order (a repeat would show)
        self.given = 0                            # receive writes made
        self.rules = archipelago.give_rules(
            archipelago.build_from_strings(*FLAG_CASES[CASE], SEED, remember_repo_base_rom()))

    def frame(self, emu: Emulator) -> None:
        state = {address: emu[address] for address in WATCHED}
        if not archipelago.checks_readable(state):
            return
        for name, check in self.checks.items():
            if name not in self.sent and emu[check.address] & check.mask:
                self.sent.append(name)
        count = emu[COUNT]
        if archipelago.may_receive(state) and count < len(SERVER_ITEMS):
            writes = archipelago.receive(SERVER_ITEMS[count], {address: emu[address] for address in INVENTORY},
                                         self.rules)
            writes[COUNT] = count + 1
            for address, value in writes.items():
                emu[address] = value
            self.given += 1


class ClientConsole(Watched):
    """A console whose every frame is followed by the client's."""

    def __init__(self, rom: bytes, client: Client) -> None:
        super().__init__(rom)
        self.client = client

    def look(self) -> Seen:
        self.client.frame(self)
        return super().look()


@cache
def checks() -> dict[str, archipelago.RamCheck]:
    return {place.name: archipelago.pickup_check(place) for place in built().places}


def switched_on(client: Client) -> ClientConsole:
    rng = random.Random(RANDOM_SEED)
    emu = ClientConsole(zora_rom(), client)
    for address in SAVE_RAM:
        emu[address] = rng.randrange(256)
    for address in range(RAM_SIZE):
        emu[address] = rng.randrange(256)
    return emu


def take_floor_item(emu: Watched, place: Place) -> None:
    """Link in the place's room (the level-load mode, then the enter-room mode), its monsters
    gone, then onto its item."""
    assert place.level is not None and place.room_num is not None
    emu[CUR_LEVEL] = place.level
    start_mode(emu, Mode.LOAD_LEVEL)
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)
    emu[ROOM_ID] = place.room_num
    start_mode(emu, ENTER_ROOM_MODE)
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)
    emu.run(5)
    for slot in MONSTER_SLOTS:
        emu[OBJ_TYPE + slot] = 0
    emu.run(CLEAR_FRAMES)
    emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
    emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + ROOM_ITEM_SLOT], emu[OBJ_Y + ROOM_ITEM_SLOT]
    emu.run_until(lambda: emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN, limit=TAKE_FRAMES)


def back_to_the_overworld(emu: Watched) -> None:
    """The level-load mode on the overworld. In a level reached by the mode jumps above the item
    screen never comes down (MenuState stops at 7), so the save starts outside."""
    emu[CUR_LEVEL] = OVERWORLD
    start_mode(emu, Mode.LOAD_LEVEL)
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)


def start_mode(emu: Emulator, mode: int) -> None:
    emu[inventory.GAME_MODE], emu[inventory.GAME_SUBMODE], emu[IS_UPDATING_MODE] = mode, 0, 0


def containers(emu: Emulator) -> int:
    return emu[inventory.ITEMS + inventory.HEART_VALUES_SLOT] >> CONTAINER_SHIFT


def test_one_check_one_item_nothing_twice() -> None:
    client = Client(checks())
    emu = switched_on(client)
    emu.boot_to_file_select()
    emu.register_file()
    emu.start_game()
    emu.run(PLAY_FRAMES)
    assert client.sent == [] and client.given == 1   # the server's item, once in play
    start = containers(emu) - 1
    place = floor_room(built())
    take_floor_item(emu, place)
    emu.run(PLAY_FRAMES)
    assert client.sent == [place.name]
    back_to_the_overworld(emu)
    emu.save_to_menu()
    emu.reset()
    emu.boot_to_file_select()
    emu.start_game()
    emu.run(PLAY_FRAMES)
    assert client.sent == [place.name]
    assert client.given == 1
    assert (emu[COUNT], containers(emu)) == (1, start + 1)
    assert emu[checks()[place.name].address] & checks()[place.name].mask
