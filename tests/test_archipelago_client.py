"""Archipelago's client tables (zora/archipelago.py pickup_checks and receive, zora/rom/inventory.py;
docs/archipelago.md "Interface"), Archipelago Phase 4a test 6 and the owner's addition 3:
  - every place of every case has a RamCheck, and no two places share one;
  - in the emulator, taking a room floor, room drop, cellar, cave, shop ware and the coast item
    sets exactly that place's check (the Armos item, revealed by pushing an Armos, takes the
    coast item's path: its screen's bit);
  - receive writes what the game itself writes when Link picks the same item up (a room's floor
    item, in the emulator), with Progressive Items on and off, for every line at every level
    (the sword's level 4 with Add L4 Sword), the letter, the magical key, the raft, the recorder,
    heart containers (and their cap), the blue potion (and its cap) and arrows without a bow;
  - the inventory tables are PRG0's own bytes."""
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.emulator import CUR_LEVEL, OBJ_STATE, ROOM_ID, ROOM_ITEM_SLOT, Mode
from tests.test_assignment import identity
from tests.test_assignment_emulator import (
    ENTER_ROOM_MODE,
    LEAVE_CAVE_MODE,
    UNDERGROUND_EXIT_TYPE,
    Console,
    places_of_each_kind,
    visit_and_take,
)
from zora import archipelago
from zora.generate.finish import Foreign
from zora.generate.pipeline import finish
from zora.generate.places import Place, PlaceKind
from zora.model.enums import Item
from zora.model.item_names import ITEM_NAMES
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

SEED = 1
LINK_INVINCIBILITY_TIMER = 0x4F0                 # ObjInvincibilityTimer, slot 0 (Link)
INVINCIBLE = 0xFF                                # frames; a take lasts far fewer
INVENTORY = range(inventory.ITEMS, inventory.MAX_BOMBS + 1)        # $0657-$067C
PROGRESSIVE_CASE = "every ZORA flag on"          # Progressive Items, Add L4 Sword, Four Potions, the shop items
PLAIN_CASE = "magical sword and letter"          # Progressive Items off
SWORD, CANDLE, ARROW, RING = (inventory.ITEMS + slot for slot in (0x00, 0x04, 0x02, 0x0B))
WOOD_BOOMERANG, MAGICAL_BOOMERANG = inventory.ITEMS + 0x1D, inventory.ITEMS + 0x1E
BOW, LETTER, MAGICAL_KEY, RAFT, RECORDER = (inventory.ITEMS + slot for slot in (0x03, 0x0F, 0x0D, 0x09, 0x05))
HEARTS, POTION = inventory.ITEMS + inventory.HEART_VALUES_SLOT, inventory.ITEMS + inventory.POTION_SLOT
# Each item to receive and the inventories to receive it in (address -> value before).
LINE_LEVELS = {SWORD: range(4), CANDLE: range(3), ARROW: range(3), RING: range(3)}


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


@cache
def built(case: str) -> archipelago.BuildResult:
    return archipelago.build_from_strings(*FLAG_CASES[case], SEED, remember_repo_base_rom())


# --- every place has a check --------------------------------------------------------------------

@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_every_place_has_its_own_check(base: bytes, case: str) -> None:
    for seed in (1, 2, 3):
        result = archipelago.build_from_strings(*FLAG_CASES[case], seed, base)
        checks = archipelago.pickup_checks(result)
        assert set(checks) == {place.name for place in result.places}
        assert len(set(checks.values())) == len(checks)


def test_the_inventory_tables_are_prg0s(base: bytes) -> None:
    """item_slots and item_descriptors read the player's ROM at ItemIdToSlot and ItemIdToDescriptor:
    each table once in PRG0, and the slots TakeItem gives a sword, a bomb and the boomerang."""
    for table in (inventory.item_slots(), inventory.item_descriptors()):
        assert len(table) == inventory.ITEM_CODES and base.count(table) == 1
    slots = inventory.item_slots()
    assert slots[Item.WOOD_SWORD] == inventory.SWORD_SLOT and slots[Item.BOMBS] == inventory.BOMB_SLOT
    assert slots[Item.WOOD_BOOMERANG] == inventory.WOOD_BOOMERANG_SLOT


# --- the checks flip in the emulator ----------------------------------------------------------------

def check_states(console: Console, checks: dict[str, archipelago.RamCheck]) -> set[str]:
    return {name for name, check in checks.items() if console.emu[check.address] & check.mask}


def test_taking_each_kind_of_item_sets_exactly_its_check(base: bytes) -> None:
    result = built("every owner flag on")
    places = places_of_each_kind(result.state)
    names = {name: ITEM_NAMES[item] if not isinstance(item, Foreign) else item
             for name, item in identity(result.state).items()}
    console = Console(archipelago.finish(result, names))
    checks = archipelago.pickup_checks(result)
    for kind, place in places.items():
        console.emu.load(console.start)
        before = check_states(console, checks)
        visit_and_take(console, kind, place)
        assert check_states(console, checks) - before == {place.name}, kind
    # the coast item, on its fixed screen (the leave-cave mode puts Link there)
    console.emu.load(console.start)
    before = check_states(console, checks)
    console.emu[ROOM_ID], console.emu[CUR_LEVEL], console.emu[UNDERGROUND_EXIT_TYPE] = inventory.COAST_SCREEN, 0, 1
    console._mode(LEAVE_CAVE_MODE)
    console._wait()
    console.emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
    console.take_room_item()
    assert check_states(console, checks) - before == {"Coast"}


# --- receive writes what the game writes ------------------------------------------------------------

def floor_rooms(result: archipelago.BuildResult) -> list[Place]:
    """Places whose item lies on the floor at load: item cellars, and rooms without a drop
    trigger."""
    world = result.state.world
    rooms = [place for place in result.state.places if place.kind == PlaceKind.CELLAR]
    for place in result.state.places:
        if place.kind == PlaceKind.ROOM:
            assert place.level is not None and place.room_num is not None
            room = next(level for level in world.levels if level.level_num == place.level).block.room(place.room_num)
            if not room.item_hidden_at_load:
                rooms.append(place)
    return rooms


class Taker(Console):
    """A console that enters a level room with a chosen inventory and takes its floor item."""

    def take_with(self, place: Place, before: dict[int, int]) -> dict[int, int]:
        assert place.level is not None and place.room_num is not None
        self.emu.load(self.start)
        for address, value in before.items():
            self.emu[address] = value
        self.emu[CUR_LEVEL] = place.level
        self._mode(Mode.LOAD_LEVEL)
        self._wait()
        self.emu[ROOM_ID] = place.room_num
        self._mode(ENTER_ROOM_MODE)
        self._wait()
        self.emu.run(5)
        self.clear_monsters()                             # no damage while taking it
        snapshot = {address: self.emu[address] for address in INVENTORY}
        self.emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE   # nor from traps or shots left in the room
        self.take_room_item()
        assert self.emu[OBJ_STATE + ROOM_ITEM_SLOT] == 0xFF, "the item was not taken"
        return {address: self.emu[address] for address in INVENTORY if self.emu[address] != snapshot[address]}


def receive_cases(progressive: bool) -> list[tuple[Item, dict[int, int]]]:
    """Each item, and each inventory to take it with."""
    line_items = ({SWORD: Item.WHITE_SWORD, CANDLE: Item.BLUE_CANDLE, ARROW: Item.WOOD_ARROWS, RING: Item.BLUE_RING}
                  if progressive else
                  {SWORD: Item.WHITE_SWORD, CANDLE: Item.RED_CANDLE, ARROW: Item.SILVER_ARROWS, RING: Item.RED_RING})
    cases = [(item, {address: level, BOW: 1}) for address, item in line_items.items()
             for level in LINE_LEVELS[address]]
    if not progressive:
        cases += [(Item.MAGICAL_SWORD, {SWORD: level}) for level in range(4)]
    cases += [(Item.WOOD_BOOMERANG, {WOOD_BOOMERANG: wood, MAGICAL_BOOMERANG: magical})
              for wood, magical in ((0, 0), (1, 0), (1, 1))]
    cases += [(Item.MAGICAL_BOOMERANG, {WOOD_BOOMERANG: 0, MAGICAL_BOOMERANG: 0})]
    cases += [(Item.SILVER_ARROWS if not progressive else Item.WOOD_ARROWS, {ARROW: 0, BOW: 0})]   # no bow
    cases += [(Item.LETTER, {LETTER: 0}), (Item.MAGICAL_KEY, {MAGICAL_KEY: 0}), (Item.RAFT, {RAFT: 0}),
              (Item.RECORDER, {RECORDER: 0})]
    cases += [(Item.HEART_CONTAINER, {HEARTS: value}) for value in (0x22, 0x21, 0xE5, 0xFF)]
    if progressive:
        cases += [(Item.BLUE_POTION, {POTION: count}) for count in (0, 1, 3, 4)]
    return cases


def test_at_sword_level_4_receive_and_the_game_both_give_nothing(base: bytes) -> None:
    """With Add L4 Sword, a sword taken at level 4: ResolveProgressive steps back to the line's
    top, so the game shows the magical sword and taking it changes nothing (grade 3 is below 4);
    receive treats level 4 as the top too. (Before the fix the game stepped back only once and
    gave the bait.)"""
    result = built(PROGRESSIVE_CASE)
    room = floor_rooms(result)[0]
    taker = Taker(finish(result.state, base, {**identity(result.state), room.name: Item.WHITE_SWORD}, check=False))
    assert taker.take_with(room, {SWORD: 4}) == {}
    assert archipelago.receive("White Sword", EMPTY | {SWORD: 4}, archipelago.give_rules(result)) == {}


@pytest.mark.parametrize("case", [PROGRESSIVE_CASE, PLAIN_CASE])
def test_receive_writes_what_the_game_writes(base: bytes, case: str) -> None:
    result = built(case)
    rules = archipelago.give_rules(result)
    assert rules.progressive_items == (case == PROGRESSIVE_CASE)
    assert rules.l4_sword == rules.four_potions == (case == PROGRESSIVE_CASE)
    cases = receive_cases(rules.progressive_items)
    items = list(dict.fromkeys(item for item, _before in cases))
    rooms = floor_rooms(result)
    for group in range(0, len(items), len(rooms)):          # as many items per ROM as floor places
        room_of = dict(zip(items[group:group + len(rooms)], rooms, strict=False))
        assignment = {**identity(result.state), **{room.name: item for item, room in room_of.items()}}
        taker = Taker(finish(result.state, base, assignment, check=False))
        taker.emu.load(taker.start)
        start = {address: taker.emu[address] for address in INVENTORY}
        for item, before in cases:
            if item in room_of:
                game = taker.take_with(room_of[item], before)
                assert archipelago.receive(ITEM_NAMES[item], start | before, rules) == game, (item.name, before)


# --- receive's rules, item by item (owner addition 3) -------------------------------------------------

EMPTY = dict.fromkeys(INVENTORY, 0) | {HEARTS: 0x22}
PROGRESSIVE = inventory.GiveRules(progressive_items=True)
L4 = inventory.GiveRules(progressive_items=True, l4_sword=True)


def receive(name: str, rules: inventory.GiveRules = archipelago.NO_RULES, **held: int) -> dict[int, int]:
    named = {"sword": SWORD, "candle": CANDLE, "arrow": ARROW, "ring": RING, "bow": BOW, "hearts": HEARTS,
             "potion": POTION, "wood": WOOD_BOOMERANG, "magical": MAGICAL_BOOMERANG}
    return archipelago.receive(name, EMPTY | {named[key]: value for key, value in held.items()}, rules)


def test_every_line_at_every_level() -> None:
    for name, address, top in (("White Sword", SWORD, 3), ("Blue Candle", CANDLE, 2),
                               ("Wooden Arrow", ARROW, 2), ("Blue Ring", RING, 2)):
        key = {SWORD: "sword", CANDLE: "candle", ARROW: "arrow", RING: "ring"}[address]
        for level in range(top + 1):
            after = min(level + 1, top)
            assert receive(name, PROGRESSIVE, **{key: level}) == ({address: after} if after != level else {})
    # the L4 cap: a sword at level 3 gives 4 with Add L4 Sword, and nothing more after
    assert receive("Magical Sword", L4, sword=3) == {SWORD: 4}
    assert receive("Wood Sword", L4, sword=2) == {SWORD: 3}
    assert receive("White Sword", L4, sword=4) == {}
    assert receive("White Sword", PROGRESSIVE, sword=3) == {}
    # boomerangs: the wooden one, then the magical one
    assert receive("Magical Boomerang", PROGRESSIVE) == {WOOD_BOOMERANG: 1}
    assert receive("Boomerang", PROGRESSIVE, wood=1) == {MAGICAL_BOOMERANG: 1}
    # Progressive Items off: the higher grade stays
    assert receive("White Sword", sword=3) == {} and receive("Magical Sword", sword=1) == {SWORD: 3}
    assert receive("Blue Ring", ring=2) == {} and receive("Red Candle") == {CANDLE: 2}


def test_items_beyond_an_inventory_bit() -> None:
    assert receive("Letter") == {LETTER: 1}               # shown to the old woman as ever (or Auto Show Letter)
    assert receive("Magical Key") == {MAGICAL_KEY: 1}
    assert receive("Raft") == {RAFT: 1} and receive("Recorder") == {RECORDER: 1}
    assert receive("Heart Container", hearts=0x22) == {HEARTS: 0x33}      # a container and a heart
    assert receive("Heart Container", hearts=0xF5) == {}                  # sixteen: the cap
    assert receive("Wooden Arrow", bow=0) == {ARROW: 1}                   # arrows without a bow
    assert receive("Blue Potion", potion=2) == {}
    assert receive("Blue Potion", inventory.GiveRules(four_potions=True), potion=2) == {POTION: 3}
    with pytest.raises(archipelago.UnknownItem):
        receive("Hookshot")


def test_may_receive_only_in_normal_play(base: bytes) -> None:
    result = built(PLAIN_CASE)
    console = Console(finish(result.state, base, identity(result.state), check=False))
    console.emu.load(console.start)                   # the play mode's first, initializing frame

    def state() -> dict[int, int]:
        return {address: console.emu[address] for address in inventory.RECEIVE_STATE}
    assert not archipelago.may_receive(state())
    console.emu.run(10)
    assert archipelago.may_receive(state())
    for address, value in ((inventory.PAUSED, 1), (inventory.MENU_STATE, 8), (inventory.ITEM_LIFT_TIMER, 0x80),
                           (inventory.LINK_STATE, inventory.HALTED), (inventory.GAME_MODE, 0x0B)):
        assert not archipelago.may_receive(state() | {address: value}), hex(address)

