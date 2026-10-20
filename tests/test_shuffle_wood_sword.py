"""Shuffle Wood Sword (a ZORA 1.0 flag recreated as a ZORA extra; docs/zora-extras.md section 13):
the flag string, the join and the sword-or-wand guarantee (the letter cave's fallback, the
restart, Randomize Letter alone untouched), the logic's tracked wood sword, the place, and in
the emulator the item the wood sword cave gives."""
import copy
from dataclasses import replace
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, ITEMS, OBJ_X, OBJ_Y, ROOM_ID, Emulator, Mode
from zora.flags import codec, zora_flags
from zora.flags.fields import ThreeState
from zora.flags.form import metadata
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.errors import GenerationFailure
from zora.generate.pipeline import Built, build, extra_options, finish, plan
from zora.generate.places import all_place_names, read_item
from zora.generate.rng import Rng
from zora.generate.steps.cave_entries import RAFT_SCREENS, WOOD_SWORD_SCREENS, CaveShuffle, Entry
from zora.generate.steps.extra_pool_items import ExtraPoolItems
from zora.generate.steps.item_shuffle_result import LETTER_SLOT, WOOD_SWORD_SLOT, ItemShuffleOptions
from zora.generate.steps.shuffle_wood_sword import WEAPONS, place_starting_weapon
from zora.model.enums import Destination, Item
from zora.model.overworld import ItemCave
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.inventory import item_slots

FIELD = "shuffle_wood_sword"
ON = zora_flags.encode(zora_flags.ZoraFlags(shuffle_wood_sword=ThreeState.ON))
WITH_MAGICAL_SWORD = zora_flags.encode(zora_flags.ZoraFlags(shuffle_wood_sword=ThreeState.ON,
                                                            randomize_magical_sword=True))
LETTER_ONLY = zora_flags.encode(zora_flags.ZoraFlags(randomize_letter=True))
FLAGS = codec.encode(codec.decode(metadata()["defaultFlags"]))
# Randomize Magical Sword asks for at most 12 hearts: Change Sword Hearts off
NO_SWORD_HEARTS = codec.encode(codec.decode(metadata()["defaultFlags"]).updated(toggles={"B10": ThreeState.OFF}))
SEEDS = range(1, 9)
OPEN_SCREEN = min(WOOD_SWORD_SCREENS)
BLOCKED_SCREEN = min(RAFT_SCREENS)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


@cache
def _built(flags: str, seed: int, zora: str = ON) -> Built:
    return build(plan(flags, seed, zora), remember_repo_base_rom())


def cave_item(built: Built, name: str) -> Item:
    return next(read_item(built.world, place) for place in built.places if place.name == name)


# --- the flag string -------------------------------------------------------------------------

def test_the_flag_is_version_6_and_off_by_default() -> None:
    assert FIELD in zora_flags.ZORA_1_0_FIELDS
    assert next(field for field in zora_flags.FIELDS if field.name == FIELD).version == 6
    assert zora_flags.decode("").shuffle_wood_sword is ThreeState.OFF
    assert zora_flags.decode(ON).shuffle_wood_sword is ThreeState.ON


# --- the join and the guarantee --------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_the_wood_sword_cave_always_holds_a_weapon(base: bytes, seed: int) -> None:
    built = _built(FLAGS, seed)
    assert cave_item(built, "Wood Sword Cave") in WEAPONS
    assert sum(read_item(built.world, place) == Item.WOOD_SWORD for place in built.places) == 1
    state = built.result.item_shuffle_result
    assert state is not None and any(record.item == Item.WOOD_SWORD for record in state.tracked)


def test_the_magical_sword_may_be_the_weapon(base: bytes) -> None:
    held = {cave_item(_built(NO_SWORD_HEARTS, seed, WITH_MAGICAL_SWORD), "Wood Sword Cave") for seed in range(1, 25)}
    assert Item.MAGICAL_SWORD in held and held <= set(WEAPONS)


def test_randomize_letter_alone_puts_no_weapon_anywhere(base: bytes) -> None:
    """The guarantee runs only with Shuffle Wood Sword (owner's choice): with Randomize Letter
    alone the wood sword stays in its cave and the letter cave holds any pool item."""
    held = {cave_item(_built(FLAGS, seed, LETTER_ONLY), "Letter Cave") for seed in SEEDS}
    assert not held <= set(WEAPONS)
    for seed in SEEDS:
        cave = _built(FLAGS, seed, LETTER_ONLY).world.overworld.get_cave(Destination.WOOD_SWORD_CAVE, ItemCave)
        assert cave is not None and cave.item == Item.WOOD_SWORD


def _guarantee(wood_screen: int, letter_screen: int | None) -> tuple[ExtraPoolItems, Item]:
    """place_starting_weapon on a built seed's pool, with the two caves on the given screens."""
    built = _built(FLAGS, 1, "")
    world, state = copy.deepcopy((built.world, built.result.item_shuffle_result))
    assert state is not None
    extras = ExtraPoolItems(caves={WOOD_SWORD_SLOT: Item.WOOD_SWORD})
    entries = [Entry(wood_screen, Destination.WOOD_SWORD_CAVE, 0)]
    if letter_screen is not None:
        extras.caves[LETTER_SLOT] = Item.LETTER
        entries.append(Entry(letter_screen, Destination.LETTER_CAVE, 0))
    rules = extra_options(built.plan).logic_rules
    place_starting_weapon(world.levels, state, extras, CaveShuffle(entries, 0), rules, Rng(1), ItemShuffleOptions())
    target = next(iter(extras.pinned))
    return extras, extras.caves[target]


def test_the_wood_sword_cave_is_filled_when_open() -> None:
    extras, weapon = _guarantee(OPEN_SCREEN, OPEN_SCREEN)
    assert extras.pinned == {WOOD_SWORD_SLOT} and weapon in WEAPONS


def test_a_blocked_wood_sword_cave_falls_back_to_the_letter_cave() -> None:
    extras, weapon = _guarantee(BLOCKED_SCREEN, OPEN_SCREEN)
    assert extras.pinned == {LETTER_SLOT} and weapon in WEAPONS


def test_no_open_cave_restarts_the_attempt() -> None:
    with pytest.raises(GenerationFailure):
        _guarantee(BLOCKED_SCREEN, BLOCKED_SCREEN)
    with pytest.raises(GenerationFailure):
        _guarantee(BLOCKED_SCREEN, None)


# --- the logic and the place ----------------------------------------------------------------

def test_the_wood_sword_is_no_longer_held_from_the_start(base: bytes) -> None:
    built = _built(FLAGS, 1)
    state, caves = built.result.item_shuffle_result, built.result.overworld
    assert state is not None and caves is not None
    rules = extra_options(built.plan).logic_rules
    assert rules.wood_sword_in_pool
    without = [record for record in state.tracked if record.item != Item.WOOD_SWORD]
    check = AcceptanceCheck(built.world.levels, replace(state, tracked=without), built.world.overworld, caves, rules)
    assert Item.WOOD_SWORD not in check.closure()[0]
    check = AcceptanceCheck(built.world.levels, state, built.world.overworld, caves, rules)
    assert Item.WOOD_SWORD in check.closure()[0]


def test_the_cave_is_a_place_named_after_every_earlier_place() -> None:
    names = all_place_names()
    assert names[-1] == "Wood Sword Cave" and names.count("Wood Sword Cave") == 1


# --- the emulator ----------------------------------------------------------------------------

IS_UPDATING_MODE = 0x11
UNDERGROUND_EXIT_TYPE = 0x5A
LEAVE_CAVE_MODE = 0x0A
CAVE_MODE = 0x0B
CAVE_ITEM_IDS = 0x422
CAVE_WARE_XS = (0x58, 0x78, 0x98)         # CaveWareXs
CAVE_WARE_Y = 0x98
ITEM_CAVE_WARE = 1                        # a one-item cave's ware
CAVE_INIT_FRAMES = 30
TAKE_WARE_FRAMES = 600
TAKEN = 0xFF
SWORD_LEVELS = {Item.WOOD_SWORD: 1, Item.WHITE_SWORD: 2, Item.MAGICAL_SWORD: 3}


def test_the_wood_sword_cave_gives_its_weapon(base: bytes) -> None:
    built = _built(FLAGS, 1)
    weapon = cave_item(built, "Wood Sword Cave")
    screen = next(screen.screen_num for screen in built.world.overworld.screens
                  if screen.destination == Destination.WOOD_SWORD_CAVE)
    emu = Emulator(finish(built, base))
    emu.new_game()

    def mode(number: int, wait_for: int = Mode.PLAY) -> None:
        emu[GAME_MODE] = number
        emu[GAME_SUBMODE] = 0
        emu[IS_UPDATING_MODE] = 0
        emu.run_until(lambda: emu.mode == wait_for and emu[IS_UPDATING_MODE] == 1, limit=900)

    emu[ROOM_ID] = screen
    emu[CUR_LEVEL] = 0
    emu[UNDERGROUND_EXIT_TYPE] = 1
    mode(LEAVE_CAVE_MODE)
    emu.run(10)
    mode(CAVE_MODE, CAVE_MODE)
    emu.run(CAVE_INIT_FRAMES)
    slot = item_slots()[weapon]
    before = emu[ITEMS + slot]
    emu[OBJ_X] = CAVE_WARE_XS[ITEM_CAVE_WARE]
    emu[OBJ_Y] = CAVE_WARE_Y
    emu.run_until(lambda: emu[CAVE_ITEM_IDS + ITEM_CAVE_WARE] == TAKEN, limit=TAKE_WARE_FRAMES)
    emu.run(60)
    assert before == 0 and emu[ITEMS + slot] == SWORD_LEVELS.get(weapon, 1)
