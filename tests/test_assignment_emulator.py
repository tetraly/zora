"""Archipelago Phase 2 test 6 (docs/archipelago.md), in the emulator (tests/emulator.py): with an
assignment, one place of each kind gives the assigned item. Room floor, room drop (trigger 7, the
item shown once the room's monsters are gone), item cellar, cave (the white-sword cave), and
joined shop ware (bought). Also test 9's emulator part: a magical sword assigned to a dungeon room
is picked up as the magical sword (the $0E remap is on).

Link is put in a level room by the level-load mode and then the enter-room mode on the room's
number, which loads a cellar too. He is put in a cave by the leave-cave mode on the cave's
screen, then the enter-cave mode (as tests/test_progressive_emulator.py does). A drop's monsters
are cleared by emptying their object slots. Each pickup is judged by the inventory byte it sets
(Items, src/Variables.inc)."""
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.emulator import (
    CUR_LEVEL,
    GAME_MODE,
    GAME_SUBMODE,
    ITEMS,
    OBJ_STATE,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    ROOM_ITEM_SLOT,
    Emulator,
    Mode,
)
from tests.test_assignment import identity
from zora.generate.finish import Foreign
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.places import Place, PlaceKind
from zora.model.enums import Destination, Item, RoomAction
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

IS_UPDATING_MODE = 0x11
UNDERGROUND_EXIT_TYPE = 0x5A
ENTER_ROOM_MODE = 0x04
LEAVE_CAVE_MODE = 0x0A
CAVE_MODE = 0x0B
CAVE_ITEM_IDS = 0x422
CAVE_WARE_XS = (0x58, 0x78, 0x98)        # CaveWareXs
CAVE_WARE_Y = 0x98
CAVE_INIT_FRAMES = 30
TAKE_WARE_FRAMES = 600
TAKEN = 0xFF                              # a taken ware's CaveItemIds entry; a taken room item's ObjState
INV_RUPEES = 0x66D
HEART_VALUES = 0x66F
FULL_RUPEES = 0xFF
MANY_HEARTS = 0xFF                        # 16 full heart containers: every sword cave lets Link in
MONSTER_SLOTS = range(1, 12)
CLEAR_FRAMES = 120
# Each test item's inventory byte (Items + index) and the value a pickup sets.
INVENTORY = {Item.RAFT: (0x09, 1), Item.BOOK: (0x0A, 1), Item.LADDER: (0x0C, 1), Item.MAGICAL_KEY: (0x0D, 1),
             Item.POWER_BRACELET: (0x0E, 1), Item.MAGICAL_SWORD: (0x00, 3)}
CASE = "every owner flag on"              # all five kinds of place, the shop wares joined
SEED = 1


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


@cache
def _built(case: str, seed: int) -> Built:
    flag_string, zora_flag_string = FLAG_CASES[case]
    return build(plan(flag_string, seed, zora_flag_string), remember_repo_base_rom())


def _room_action(built: Built, place: Place) -> RoomAction:
    assert place.level is not None and place.room_num is not None
    return built.world.levels[place.level - 1].block.room(place.room_num).room_action


def floor_room(built: Built) -> Place:
    """A room place whose item stands on the floor (no drop trigger)."""
    return next(place for place in built.places
                if place.kind == PlaceKind.ROOM and _room_action(built, place) != RoomAction.ALL_DEAD_ITEM)


def places_of_each_kind(built: Built) -> dict[str, Place]:
    rooms = [place for place in built.places if place.kind == PlaceKind.ROOM]
    return {
        "room floor": floor_room(built),
        "room drop": next(place for place in rooms if _room_action(built, place) == RoomAction.ALL_DEAD_ITEM),
        "cellar": next(place for place in built.places if place.kind == PlaceKind.CELLAR),
        "cave": next(place for place in built.places if place.destination == Destination.WHITE_SWORD_CAVE),
        "shop ware": next(place for place in built.places if place.kind == PlaceKind.SHOP_WARE),
    }


def with_items(built: Built, wanted: dict[str, Item]) -> dict[str, Item | Foreign]:
    """The identity assignment with each wanted item moved into its place (and the place's item
    moved to where the wanted item was)."""
    assignment = identity(built)
    for name, item in wanted.items():
        source = next(place for place, held in assignment.items() if held == item)
        assignment[source], assignment[name] = assignment[name], item
    return assignment


class Console:
    """One console in play from a new file, with full rupees and hearts; each visit starts again
    from that state."""

    def __init__(self, rom: bytes) -> None:
        self.emu = Emulator(rom)
        self.emu.new_game()
        self.emu[INV_RUPEES] = FULL_RUPEES
        self.emu[HEART_VALUES] = MANY_HEARTS
        self.start = self.emu.save()

    def _wait(self, mode: int = Mode.PLAY) -> None:
        self.emu.run_until(lambda: self.emu.mode == mode and self.emu[IS_UPDATING_MODE] == 1, limit=900)

    def _mode(self, mode: int) -> None:
        self.emu[GAME_MODE] = mode
        self.emu[GAME_SUBMODE] = 0
        self.emu[IS_UPDATING_MODE] = 0

    def inventory(self, item: Item) -> int:
        return self.emu[ITEMS + INVENTORY[item][0]]

    def enter_room(self, level: int, room: int) -> None:
        self.emu.load(self.start)
        self.emu[CUR_LEVEL] = level
        self._mode(Mode.LOAD_LEVEL)
        self._wait()
        self.emu[ROOM_ID] = room
        self._mode(ENTER_ROOM_MODE)
        self._wait()
        self.emu.run(5)

    def clear_monsters(self) -> None:
        for slot in MONSTER_SLOTS:
            self.emu[OBJ_TYPE + slot] = 0
        self.emu.run(CLEAR_FRAMES)

    def take_room_item(self) -> None:
        self.emu[OBJ_X] = self.emu[OBJ_X + ROOM_ITEM_SLOT]
        self.emu[OBJ_Y] = self.emu[OBJ_Y + ROOM_ITEM_SLOT]
        self.emu.run_until(lambda: self.emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN, limit=120)
        self.emu.run(60)

    def enter_cave(self, screen: int) -> None:
        self.emu.load(self.start)
        self.emu[ROOM_ID] = screen
        self.emu[CUR_LEVEL] = 0
        self.emu[UNDERGROUND_EXIT_TYPE] = 1
        self._mode(LEAVE_CAVE_MODE)
        self._wait()
        self.emu.run(10)
        self._mode(CAVE_MODE)
        self._wait(CAVE_MODE)
        self.emu.run(CAVE_INIT_FRAMES)

    def take_ware(self, position: int) -> None:
        self.emu[OBJ_X] = CAVE_WARE_XS[position]
        self.emu[OBJ_Y] = CAVE_WARE_Y
        self.emu.run_until(lambda: self.emu[CAVE_ITEM_IDS + position] == TAKEN, limit=TAKE_WARE_FRAMES)
        self.emu.run(60)


def visit_and_take(console: Console, kind: str, place: Place) -> None:
    if place.is_dungeon:
        assert place.level is not None and place.room_num is not None
        console.enter_room(place.level, place.room_num)
        if kind == "room drop":
            assert console.emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN       # hidden until the monsters go
            console.clear_monsters()
        console.take_room_item()
        return
    console.enter_cave(place.screens[0])
    console.take_ware(1 if place.kind == PlaceKind.CAVE else place.position or 0)


def test_each_kind_of_place_gives_the_assigned_item(base: bytes) -> None:
    built = _built(CASE, SEED)
    places = places_of_each_kind(built)
    wanted = dict(zip(places, (Item.RAFT, Item.BOOK, Item.LADDER, Item.MAGICAL_KEY, Item.POWER_BRACELET), strict=True))
    console = Console(finish(built, base, with_items(built, {places[kind].name: item for kind, item in wanted.items()}),
                             check=False))
    for kind, place in places.items():
        item = wanted[kind]
        console.emu.load(console.start)
        assert console.inventory(item) == 0, (kind, item.name)          # not held before
        visit_and_take(console, kind, place)
        assert console.inventory(item) == INVENTORY[item][1], (kind, place.name, item.name)


def test_a_magical_sword_in_a_dungeon_room_is_picked_up(base: bytes) -> None:
    built = _built("magical sword and letter", SEED)
    room = floor_room(built)
    console = Console(finish(built, base, with_items(built, {room.name: Item.MAGICAL_SWORD}), check=False))
    visit_and_take(console, "room floor", room)
    assert console.inventory(Item.MAGICAL_SWORD) == INVENTORY[Item.MAGICAL_SWORD][1]
