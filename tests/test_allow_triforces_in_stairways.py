"""Allow Triforces in Stairways (a ZORA 1.0 flag recreated as a ZORA extra; docs/zora-extras.md
section 13; redesigned by the owner, 2026-10-18): before the item shuffle each Triforce of levels
1-8 trades places with a spot drawn uniformly from its level's item spots (zora/generate/steps/
place_triforces.py), and the shuffle runs over everything else under every Item Shuffle value.
Tested: the flag string and no dependency on Item Shuffle; each Triforce stays in its level, in a
room or an item cellar, spread over its level's spots; every item and every level's Triforce
reachable; the vanilla sets' fixed progression places follow a trade; the compass; Archipelago's
BuildResult.triforces; and in the emulator a Triforce picked up in an item cellar."""
from collections import Counter
from functools import cache

import pytest

from tests.emulator import (
    CUR_LEVEL,
    GAME_MODE,
    GAME_SUBMODE,
    INV_TRIFORCE,
    OBJ_STATE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    ROOM_ITEM_SLOT,
    Emulator,
    Mode,
)
from tests.test_coop_reserved import z1r_with
from zora import archipelago
from zora.flags import codec, zora_flags
from zora.flags.fields import DungeonLayoutSource, ItemShuffleScope, ThreeState
from zora.flags.form import metadata
from zora.generate.acceptance_check import AcceptanceCheck
from zora.generate.dungeon_walk import item_cellar, item_room
from zora.generate.logic import triforce_event
from zora.generate.pipeline import Built, build, extra_options, finish, plan
from zora.generate.places import all_place_names
from zora.generate.rng import Rng
from zora.generate.steps.item_shuffle_result import ItemShuffleResult
from zora.generate.steps.place_triforces import item_spots, place_triforces, set_index_of, triforce_room
from zora.generate.steps.shuffle_items import POOL_ORDER
from zora.model.enums import Item, RoomType
from zora.model.levels import Level
from zora.model.rooms import Room
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.levels import derive_triforce_room_ptr

FIELD = "allow_triforces_in_stairways"
ON = zora_flags.encode(zora_flags.ZoraFlags(allow_triforces_in_stairways=ThreeState.ON))
MAYBE = zora_flags.encode(zora_flags.ZoraFlags(allow_triforces_in_stairways=ThreeState.POSSIBLE))
DEFAULT_SETTINGS = codec.decode(metadata()["defaultFlags"])
SCOPES = (ItemShuffleScope.NONE, ItemShuffleScope.DUNGEON_ITEMS_ONLY, ItemShuffleScope.WITHIN_EACH_DUNGEON,
          ItemShuffleScope.FULL)
FULL = codec.encode(DEFAULT_SETTINGS)
SCOPE_FLAGS = {scope.name: codec.encode(DEFAULT_SETTINGS.updated(options={"C06": scope})) for scope in SCOPES}
FIRST_QUEST = {scope.name: z1r_with(options={"C06": scope, "C02": DungeonLayoutSource.FIRST_QUEST})
               for scope in SCOPES}
TRIFORCE_LEVELS = range(1, 9)
SEEDS = range(1, 9)
QUICK_SEEDS = range(1, 4)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


@cache
def _built(flags: str, seed: int, zora: str = ON) -> Built:
    return build(plan(flags, seed, zora), remember_repo_base_rom())


def triforce_place(level: Level) -> tuple[str, int]:
    """("room", room) or ("cellar", cellar) of the level's Triforce."""
    room = item_room(level, Item.TRIFORCE)
    if room is not None:
        return "room", room
    cellar = item_cellar(level, Item.TRIFORCE)
    assert cellar is not None, f"level {level.level_num} has no Triforce"
    return "cellar", cellar


def levels_of(built: Built) -> dict[int, Level]:
    return {level.level_num: level for level in built.world.levels}


# --- the flag string, under every Item Shuffle -----------------------------------------------

def test_the_flag_is_version_6_and_off_by_default() -> None:
    assert FIELD in zora_flags.ZORA_1_0_FIELDS
    assert next(field for field in zora_flags.FIELDS if field.name == FIELD).version == 6
    assert zora_flags.decode("").allow_triforces_in_stairways is ThreeState.OFF
    assert zora_flags.decode(ON).allow_triforces_in_stairways is ThreeState.ON


@pytest.mark.parametrize("scope", [*SCOPES, ItemShuffleScope.RANDOM], ids=lambda scope: scope.name)
def test_every_item_shuffle_takes_it(base: bytes, scope: ItemShuffleScope) -> None:
    """Owner decision (2026-10-18): no dependency on Item Shuffle, so no refusal and no resolving off."""
    settings = DEFAULT_SETTINGS.updated(options={"C06": scope})
    assert not [names for _message, names in zora_flags.conflicts(zora_flags.decode(ON), settings) if FIELD in names]
    for seed in QUICK_SEEDS:
        assert plan(codec.encode(settings), seed, ON).zora_resolved.is_on(FIELD)


# --- the placement ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", QUICK_SEEDS)
@pytest.mark.parametrize("scope", [scope.name for scope in SCOPES])
def test_each_triforce_stays_in_its_level_and_everything_is_reachable(base: bytes, scope: str, seed: int) -> None:
    for flags in (SCOPE_FLAGS[scope], FIRST_QUEST[scope]):
        built = _built(flags, seed)
        for number, level in levels_of(built).items():
            if number in TRIFORCE_LEVELS:
                triforce_place(level)               # exactly where the walk finds it, in its own level
                rooms = sum(room.item == Item.TRIFORCE for room in level.rooms)
                cellars = sum(stair.item == Item.TRIFORCE for stair in level.block.staircases
                              if stair.room_type == RoomType.ITEM_STAIRCASE and stair.return_dest in level.room_nums)
                assert rooms + cellars == 1
        state, caves = built.result.item_shuffle_result, built.result.overworld
        assert state is not None and caves is not None
        held, completed = AcceptanceCheck(built.world.levels, state, built.world.overworld, caves,
                                          extra_options(built.plan).logic_rules).closure()
        assert completed == set(TRIFORCE_LEVELS), (scope, seed)
        assert {place.item for place in state.tracked} <= held, (scope, seed)


def test_triforces_land_in_cellars_and_in_rooms_under_full(base: bytes) -> None:
    kinds: Counter[str] = Counter(triforce_place(level)[0] for seed in SEEDS
                                  for number, level in levels_of(_built(FULL, seed)).items()
                                  if number in TRIFORCE_LEVELS)
    assert kinds["cellar"] and kinds["room"], kinds


def test_off_never_puts_a_triforce_in_a_cellar(base: bytes) -> None:
    for seed in SEEDS:
        for number, level in levels_of(_built(FULL, seed, "")).items():
            if number in TRIFORCE_LEVELS:
                assert triforce_place(level)[0] == "room"


def own_room(level: Level) -> Room:
    room = triforce_room(level)
    assert room is not None, f"level {level.level_num} has no Triforce room"
    return room


TRADES = 1200
# Each spot's share of the draws within about four standard deviations of a uniform share
SPREAD_SIGMAS = 4


def test_each_triforce_picks_uniformly_among_its_levels_spots(base: bytes) -> None:
    """On PRG0's 1st Quest levels: each Triforce's spot over many draws (each draw a fresh world),
    every spot of its level about equally often, its own room among them; only the item moves."""
    counts: dict[int, Counter[int]] = {level: Counter() for level in TRIFORCE_LEVELS}
    for seed in range(TRADES):
        levels = parse_rom(base).levels
        before = {level.level_num: {spot.cell: spot.item for spot in item_spots(level, own_room(level))}
                  for level in levels if level.level_num in TRIFORCE_LEVELS}
        own = {level.level_num: own_room(level).room_num for level in levels if level.level_num in TRIFORCE_LEVELS}
        bits = {(level.level_num, room.room_num): (room.item_info.boss_sound, room.item_info.is_dark)
                for level in levels for room in level.rooms}
        state = ItemShuffleResult()
        place_triforces(levels, state, Rng(seed))
        for level in levels:
            if level.level_num not in TRIFORCE_LEVELS:
                continue
            spot = triforce_room(level)
            cell = spot.room_num if spot is not None else next(
                stair.room_num for stair in level.block.staircases
                if stair.item == Item.TRIFORCE and stair.return_dest in level.room_nums)
            counts[level.level_num][cell] += 1
            if cell != own[level.level_num]:
                old = level.block.room(own[level.level_num])
                assert old.item == before[level.level_num][cell]          # the old room holds the spot's item
                assert state.triforce_origins[set_index_of(level), cell] == own[level.level_num]
        assert bits == {(level.level_num, room.room_num): (room.item_info.boss_sound, room.item_info.is_dark)
                        for level in levels for room in level.rooms}
    for level_num, by_cell in counts.items():
        spots = len(before[level_num])
        assert len(by_cell) == spots, (level_num, by_cell)
        assert own[level_num] in by_cell
        share, sigma = TRADES / spots, (TRADES * (1 / spots) * (1 - 1 / spots)) ** 0.5
        assert all(abs(count - share) <= SPREAD_SIGMAS * sigma for count in by_cell.values()), (level_num, by_cell)


@pytest.mark.parametrize("seed", QUICK_SEEDS)
def test_the_vanilla_sets_fixed_places_follow_a_trade(base: bytes, seed: int) -> None:
    """1st Quest dungeons with Item Shuffle: None (PS-VAN-03's fixed places, no walk): every
    progression item still once in the levels, and every Triforce once."""
    world = _built(FIRST_QUEST["NONE"], seed).world
    found: Counter[Item] = Counter()
    for level in world.levels:
        found.update(room.item for room in level.rooms)
        found.update(stair.item for stair in level.block.staircases
                     if stair.room_type == RoomType.ITEM_STAIRCASE and stair.return_dest in level.room_nums
                     and stair.item is not None)
    assert all(found[Item(code)] == 1 for code in POOL_ORDER), found
    assert found[Item.TRIFORCE] == len(TRIFORCE_LEVELS)


def test_the_compass_points_at_a_cellar_triforces_stairway(base: bytes) -> None:
    for seed in SEEDS:
        for level in levels_of(_built(FULL, seed)).values():
            if level.level_num in TRIFORCE_LEVELS and triforce_place(level)[0] == "cellar":
                cellar = next(stair for stair in level.block.staircases if stair.item == Item.TRIFORCE)
                assert derive_triforce_room_ptr(level) == cellar.return_dest
                return
    pytest.fail("no Triforce in a cellar in the sample")


# --- Archipelago -----------------------------------------------------------------------------

@pytest.mark.parametrize("zora", [ON, ""], ids=["on", "off"])
def test_the_build_names_each_triforces_spot(base: bytes, zora: str) -> None:
    """BuildResult.triforces (agreed with the Archipelago world, 2026-10-18): (event, place name)
    per level 1-8, the name one of all_place_names and never one of the seed's places."""
    names = set(all_place_names())
    for seed in QUICK_SEEDS:
        result = archipelago.build_from_strings(FULL, zora, seed, base)
        assert [event for event, _place in result.triforces] == [triforce_event(level) for level in TRIFORCE_LEVELS]
        spots = {place for _event, place in result.triforces}
        assert spots <= names
        assert not spots & {place.name for place in result.places}
        assert set(result.logic.events) >= {event for event, _place in result.triforces}
        if not zora:
            assert all(place.endswith("Floor") for place in spots)


# --- the emulator ----------------------------------------------------------------------------

IS_UPDATING_MODE = 0x11
ENTER_ROOM_MODE = 0x04
ITEM_INACTIVE = 0xFF
HEART_VALUES = 0x66F
MANY_HEARTS = 0xFF
PICKUP_FRAMES = 1200


def cellar_triforce(base: bytes) -> tuple[Built, int, int]:
    for seed in SEEDS:
        built = _built(FULL, seed)
        for level in levels_of(built).values():
            if level.level_num in TRIFORCE_LEVELS and triforce_place(level)[0] == "cellar":
                return built, level.level_num, triforce_place(level)[1]
    pytest.fail("no Triforce in a cellar in the sample")


def test_a_triforce_picked_up_in_a_cellar_counts_and_takes_link_out(base: bytes) -> None:
    built, level, cellar = cellar_triforce(base)
    emu = Emulator(finish(built, base))
    emu.new_game()
    emu[HEART_VALUES] = MANY_HEARTS

    def mode(number: int) -> None:
        emu[GAME_MODE] = number
        emu[GAME_SUBMODE] = 0
        emu[IS_UPDATING_MODE] = 0
        emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)

    emu[CUR_LEVEL] = level
    mode(Mode.LOAD_LEVEL)
    emu[ROOM_ID] = cellar
    mode(ENTER_ROOM_MODE)
    emu.run(5)
    assert emu[INV_TRIFORCE] & (1 << (level - 1)) == 0
    emu[OBJ_X] = emu[OBJ_X + ROOM_ITEM_SLOT]
    emu[OBJ_Y] = emu[OBJ_Y + ROOM_ITEM_SLOT]
    emu.run_until(lambda: emu[OBJ_STATE + ROOM_ITEM_SLOT] == ITEM_INACTIVE, limit=120)
    assert emu[INV_TRIFORCE] & (1 << (level - 1))
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[CUR_LEVEL] == 0, limit=PICKUP_FRAMES)
