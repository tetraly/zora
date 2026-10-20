"""Shop Items in the Item Pool's bait (ZORA 1.0's definition of the option, owner decision
2026-10-17; docs/zora-extras.md section 10): the baits and the fairy, the logic's bait rule, the
hints, the ROM's bait count, and in the emulator a bait picked up twice, a Goriya eating one and a
bought fairy refilling the hearts."""
import copy
from dataclasses import replace
from functools import cache

import pytest

from tests.emulator import (
    CUR_LEVEL,
    FACE_FRAMES,
    GAME_MODE,
    GAME_SUBMODE,
    ITEMS,
    OBJ_STATE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    ROOM_ITEM_SLOT,
    SELECTED_ITEM_SLOT,
    Button,
    Emulator,
    Mode,
)
from zora.flags import codec, zora_flags
from zora.flags.form import metadata
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.dungeon_walk import HUNGRY_GORIYA_ROW, entry_row
from zora.generate.pipeline import Built, build, extra_options, finish, plan
from zora.generate.places import read_item
from zora.generate.rng import Rng
from zora.generate.steps.bait_in_pool import bait_in_pool, bait_wares, hungry_goriyas
from zora.generate.steps.extra_pool_items import ExtraPoolItems
from zora.generate.steps.hint_text import hinted_level_records
from zora.generate.steps.item_shuffle_result import TrackedPlace
from zora.generate.steps.shuffle_shop_items import SHOPS
from zora.model.enums import Enemy, Item, Side
from zora.model.overworld import Shop
from zora.model.rooms import Room
from zora.rom.bait_count import BAIT_DESCRIPTOR, DEC_ABSOLUTE, GRUMBLE_FOOD_STORE, STA_ABSOLUTE
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.code_patches import ONE_TIME_WARES
from zora.rom.inventory import ITEM_TAKEN, room_flags

ON = zora_flags.encode(zora_flags.ZoraFlags(shop_items_in_pool=True))
DEFAULT_SETTINGS = codec.decode(metadata()["defaultFlags"])
SHAPES = codec.encode(DEFAULT_SETTINGS)                                   # one hungry Goriya
SECOND_QUEST = codec.encode(DEFAULT_SETTINGS.updated(options={"C02": 1}))  # two
SEEDS = (1, 2)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


@cache
def _built(flags: str, seed: int, zora: str = ON) -> Built:
    return build(plan(flags, seed, zora), remember_repo_base_rom())


def shop_wares(built: Built) -> list[tuple[Item, int]]:
    return [(ware.item, ware.price) for destination in SHOPS
            if isinstance(shop := built.world.overworld.get_cave(destination, Shop), Shop) for ware in shop.items]


# --- the baits and the fairy -----------------------------------------------------------------

@pytest.mark.parametrize("flags", [SHAPES, SECOND_QUEST])
@pytest.mark.parametrize("seed", SEEDS)
def test_one_bait_per_hungry_goriya_and_a_fairy_for_the_spare(base: bytes, flags: str, seed: int) -> None:
    built = _built(flags, seed)
    goriyas = hungry_goriyas(built.world.levels)
    baits = [place for place in built.places if read_item(built.world, place) == Item.BAIT]
    assert len(baits) == max(1, goriyas)
    wares = [item for item, _price in shop_wares(built)]
    assert wares.count(Item.FAIRY) == 2 - len(baits)
    # the option's other three items joined as before
    held = {read_item(built.world, place) for place in built.places}
    assert {Item.WOOD_ARROWS, Item.BLUE_CANDLE, Item.BLUE_RING} <= held
    # every bait in a shop is a pool place (a joined ware); no other shop sells one
    assert wares.count(Item.BAIT) == sum(place.is_shop for place in baits)
    tracked = built.result.item_shuffle_result
    assert tracked is not None and sum(record.item == Item.BAIT for record in tracked.tracked) == len(baits)


def test_the_spare_bait_becomes_a_fairy_at_20_to_40(base: bytes) -> None:
    """The step on a flag-off seed's world (two baits, one Goriya): the second bait's ware
    becomes a fairy priced 20-40 (tests/test_fairy_prices.py), the first joins the pool."""
    built = _built(SHAPES, 1, "")
    world, state = copy.deepcopy((built.world, built.result.item_shuffle_result))
    assert state is not None and hungry_goriyas(world.levels) == 1
    first, second = bait_wares(world.overworld)
    extras = ExtraPoolItems()
    bait_in_pool(world.levels, state, extras, world.overworld, Rng(1))
    assert second.get() == Item.FAIRY and 20 <= second.shop.ware(second.position).price <= 40
    assert extras.shop_items == [Item.BAIT] and extras.shop_wares[0].shop is first.shop
    assert sum(record.item == Item.BAIT for record in state.tracked) == 1


def test_a_joined_bait_ware_is_sold_once(base: bytes) -> None:
    """fp-prog-01's buy-once rule is written: a bait ware selling a pool item is a one-time ware."""
    built = _built(SHAPES, 1)
    rom = finish(built, base)
    assert any(rom[ONE_TIME_WARES:ONE_TIME_WARES + 3])


# --- the logic -------------------------------------------------------------------------------

def _goriya_room(built: Built) -> Room:
    return next(room for level in built.world.levels for room in level.rooms if room.enemy == Enemy.HUNGRY_GORIYA)


def test_a_hungry_goriya_blocks_the_north_side_until_fed(base: bytes) -> None:
    room = _goriya_room(_built(SHAPES, 1))
    assert entry_row(room, False, False) is None                       # the flag off: every side
    row = entry_row(room, False, False, goriya_hungry=True)
    assert row == HUNGRY_GORIYA_ROW
    assert all(Side.NORTH not in row[side] for side in (Side.SOUTH, Side.WEST, Side.EAST))


def _check(built: Built, tracked: list[TrackedPlace]) -> AcceptanceCheck:
    state, caves = built.result.item_shuffle_result, built.result.overworld
    assert state is not None and caves is not None
    return AcceptanceCheck(built.world.levels, replace(state, tracked=tracked), built.world.overworld, caves,
                           extra_options(built.plan).logic_rules)


def test_no_bait_is_usable_until_every_bait_is_found(base: bytes) -> None:
    built = _built(SECOND_QUEST, 1)
    state = built.result.item_shuffle_result
    assert state is not None
    held, _completed = _check(built, list(state.tracked)).closure()
    assert Item.BAIT in held
    unreachable = TrackedPlace(Item.BAIT, slot="nowhere")
    held, _completed = _check(built, [*state.tracked, unreachable]).closure()
    assert Item.BAIT not in held


def test_bait_is_never_hinted(base: bytes) -> None:
    built = _built(SECOND_QUEST, 1)
    state = built.result.item_shuffle_result
    assert state is not None
    in_a_level = TrackedPlace(Item.BAIT, level=1, room=0)
    assert all(record.item != Item.BAIT
               for record in hinted_level_records(replace(state, tracked=[*state.tracked, in_a_level])))


# --- the ROM ---------------------------------------------------------------------------------

def test_bait_is_a_count_only_with_the_flag(base: bytes) -> None:
    on = finish(_built(SHAPES, 1), base)
    off = finish(_built(SHAPES, 1, ""), base)
    assert (on[BAIT_DESCRIPTOR], on[GRUMBLE_FOOD_STORE]) == (0x11, DEC_ABSOLUTE)
    assert (off[BAIT_DESCRIPTOR], off[GRUMBLE_FOOD_STORE]) == (base[BAIT_DESCRIPTOR], STA_ABSOLUTE)


# --- the emulator ----------------------------------------------------------------------------

IS_UPDATING_MODE = 0x11
ENTER_ROOM_MODE = 0x04
INV_FOOD = ITEMS + 6                      # InvFood ($065D)
FOOD_SLOT = 5                             # SelectedItemSlot value of the bait
HEART_VALUES = 0x66F
MANY_HEARTS = 0xFF
LEVEL_BLOCK_ATTRS_E = 0x6A7E              # low 5 bits: the room item
LEVEL_BLOCK_ATTRS_F = 0x6AFE              # low 3 bits: the secret trigger
ROOM_ITEM_MASK = 0x1F
SECRET_TRIGGER_MASK = 0x07
ITEM_INACTIVE = 0xFF
FEED_FRAMES = 600
GORIYA_SLOT = 1                           # the person object's slot
UNDERGROUND_EXIT_TYPE = 0x5A
LEAVE_CAVE_MODE = 0x0A
CAVE_MODE = 0x0B
CAVE_ITEM_IDS = 0x422
CAVE_WARE_XS = (0x58, 0x78, 0x98)         # CaveWareXs
CAVE_WARE_Y = 0x98
CAVE_INIT_FRAMES = 30
TAKE_WARE_FRAMES = 600
REFILL_FRAMES = 600
INV_RUPEES = 0x66D
FULL_RUPEES = 0xFF
THREE_CONTAINERS_NO_HEARTS = 0x20         # HeartValues: containers - 1, high nibble; full hearts, low
CONTAINERS_MASK, HEARTS_MASK, CONTAINERS_SHIFT = 0xF0, 0x0F, 4
GRUMBLE_WAITS_FOR_FOOD = 1                # UpdateGrumble_Full_JumpTable's UpdateGrumble1


class Console:
    def __init__(self, rom: bytes) -> None:
        self.emu = Emulator(rom)
        self.emu.new_game()
        self.emu[HEART_VALUES] = MANY_HEARTS
        self.emu[INV_RUPEES] = FULL_RUPEES

    def enter_cave(self, screen: int) -> None:
        """Come out on the cave's screen (the leave-cave mode), then go in (the enter-cave mode)."""
        self.emu[ROOM_ID] = screen
        self.emu[CUR_LEVEL] = 0
        self.emu[UNDERGROUND_EXIT_TYPE] = 1
        self._mode(LEAVE_CAVE_MODE)
        self.emu.run(10)
        self._mode(CAVE_MODE, CAVE_MODE)
        self.emu.run(CAVE_INIT_FRAMES)

    def take_ware(self, position: int) -> None:
        self.emu[OBJ_X] = CAVE_WARE_XS[position]
        self.emu[OBJ_Y] = CAVE_WARE_Y
        self.emu.run_until(lambda: self.emu[CAVE_ITEM_IDS + position] == ITEM_INACTIVE, limit=TAKE_WARE_FRAMES)

    def _mode(self, mode: int, wait_for: int = Mode.PLAY) -> None:
        self.emu[GAME_MODE] = mode
        self.emu[GAME_SUBMODE] = 0
        self.emu[IS_UPDATING_MODE] = 0
        self.emu.run_until(lambda: self.emu.mode == wait_for and self.emu[IS_UPDATING_MODE] == 1, limit=900)

    def enter_room(self, level: int, room: int) -> None:
        self.emu[CUR_LEVEL] = level
        self._mode(Mode.LOAD_LEVEL)
        self.emu[ROOM_ID] = room
        self._mode(ENTER_ROOM_MODE)
        self.emu.run(5)

    def take_bait_from_the_floor(self) -> None:
        """Put bait on this room's floor, the room's item not yet taken, enter it again and take it."""
        room = self.emu[ROOM_ID]
        self.emu[room_flags(self.emu[CUR_LEVEL]) + room] &= ~ITEM_TAKEN & 0xFF
        self.emu[LEVEL_BLOCK_ATTRS_E + room] = self.emu[LEVEL_BLOCK_ATTRS_E + room] & ~ROOM_ITEM_MASK & 0xFF | Item.BAIT
        self.emu[LEVEL_BLOCK_ATTRS_F + room] &= ~SECRET_TRIGGER_MASK & 0xFF
        self._mode(ENTER_ROOM_MODE)
        self.emu.run(5)
        self.emu[OBJ_X] = self.emu[OBJ_X + ROOM_ITEM_SLOT]
        self.emu[OBJ_Y] = self.emu[OBJ_Y + ROOM_ITEM_SLOT]
        self.emu.run_until(lambda: self.emu[OBJ_STATE + ROOM_ITEM_SLOT] == ITEM_INACTIVE, limit=120)
        self.emu.run(60)

    def throw_bait(self) -> None:
        """Once the Goriya's text is written (its state 1, UpdateGrumble1), throw the bait up."""
        self.emu.run_until(lambda: self.emu[OBJ_STATE + GORIYA_SLOT] == GRUMBLE_WAITS_FOR_FOOD, limit=FEED_FRAMES)
        self.emu[SELECTED_ITEM_SLOT] = FOOD_SLOT
        self.emu.run(FACE_FRAMES, Button.UP)
        self.emu.run(5)
        self.emu.press(Button.B)


@cache
def _rom(flags: str, zora: str) -> bytes:
    built = _built(flags, 1, zora)
    return finish(built, remember_repo_base_rom())


@pytest.mark.parametrize(("zora", "after_two"), [(ON, 2), ("", 1)])
def test_two_baits_picked_up_make_two(base: bytes, zora: str, after_two: int) -> None:
    console = Console(_rom(SHAPES, zora))
    level_1 = next(level for level in _built(SHAPES, 1, zora).world.levels if level.level_num == 1)
    console.enter_room(1, level_1.entrance_room)
    console.take_bait_from_the_floor()
    assert console.emu[INV_FOOD] == 1
    console.take_bait_from_the_floor()
    assert console.emu[INV_FOOD] == after_two


@pytest.mark.parametrize(("zora", "left"), [(ON, 1), ("", 0)])
def test_a_fed_goriya_eats_one_bait(base: bytes, zora: str, left: int) -> None:
    built = _built(SHAPES, 1, zora)
    level, room = next((level.level_num, room.room_num) for level in built.world.levels for room in level.rooms
                       if room.enemy == Enemy.HUNGRY_GORIYA)
    console = Console(_rom(SHAPES, zora))
    console.enter_room(level, room)
    console.emu[INV_FOOD] = 2
    console.throw_bait()
    console.emu.run_until(lambda: console.emu[INV_FOOD] != 2, limit=FEED_FRAMES)
    assert console.emu[INV_FOOD] == left


def test_a_fairy_bought_in_a_shop_refills_the_hearts(base: bytes) -> None:
    built = _built(SHAPES, 1)
    shop, position = next((shop, position) for destination in SHOPS
                          if isinstance(shop := built.world.overworld.get_cave(destination, Shop), Shop)
                          for position, ware in enumerate(shop.items) if ware.item == Item.FAIRY)
    screen = next(screen.screen_num for screen in built.world.overworld.screens
                  if screen.destination == shop.destination)
    console = Console(_rom(SHAPES, ON))
    console.emu[HEART_VALUES] = THREE_CONTAINERS_NO_HEARTS
    console.enter_cave(screen)
    assert console.emu[HEART_VALUES] & HEARTS_MASK == 0
    console.take_ware(position)
    def full() -> bool:
        hearts = console.emu[HEART_VALUES]
        return hearts & HEARTS_MASK == (hearts & CONTAINERS_MASK) >> CONTAINERS_SHIFT
    console.emu.run_until(full, limit=REFILL_FRAMES)
